"""Project accounts and legacy workspace mappings stored in MySQL."""

from hashlib import sha256
from pathlib import Path
import time
import unicodedata
import uuid

from fastapi import HTTPException
from sqlalchemy import BigInteger, Boolean, Column, MetaData, Table, Text, literal, select, text
from sqlalchemy.dialects.mysql import BINARY, CHAR, LONGTEXT, VARBINARY
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, DBAPIError, IntegrityError, TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import create_async_engine


ACCOUNT_DB_ERRORS = (DBAPIError, PoolTimeoutError)
MAX_STORAGE_USER_ID_BYTES = 1024
_DUPLICATE_ENTRY = 1062

metadata = MetaData()
accounts = Table(
    "accounts", metadata,
    Column("id", CHAR(32, charset="ascii", collation="ascii_bin"), primary_key=True),
    Column("username", Text, nullable=False),
    Column("username_key", VARBINARY(256), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("storage_user_id", VARBINARY(MAX_STORAGE_USER_ID_BYTES), nullable=False, unique=True),
    Column("enabled", Boolean, nullable=False, server_default=text("1")),
    Column("created_at", BigInteger, nullable=False),
    mysql_engine="InnoDB", mysql_charset="utf8mb4",
)
legacy_workspaces = Table(
    "legacy_workspaces", metadata,
    Column("storage_user_id", VARBINARY(MAX_STORAGE_USER_ID_BYTES), primary_key=True),
    Column("agent_id", VARBINARY(512), primary_key=True),
    Column("path", LONGTEXT, nullable=False),
    Column("path_digest", BINARY(32), nullable=False, unique=True),
    mysql_engine="InnoDB", mysql_charset="utf8mb4",
)


def username_key(username: str) -> str:
    return unicodedata.normalize("NFKC", username).strip().casefold()


def _workspace_values(storage_user_id: str, agent_id: str, path: str) -> dict:
    # Index the exact UTF-8 path without imposing MySQL's index size limit on paths.
    return {
        "storage_user_id": storage_user_id.encode(),
        "agent_id": agent_id.encode(),
        "path": path,
        "path_digest": sha256(path.encode()).digest(),
    }


class AccountStore:
    def __init__(self, mysql_url: str):
        error_message = "请设置 AUTH_MYSQL_URL，格式为 mysql+asyncmy://用户:密码@主机:端口/数据库。"
        try:
            url = make_url(mysql_url)
        except ArgumentError:
            raise ValueError(error_message) from None
        if url.drivername != "mysql+asyncmy" or not url.database:
            raise ValueError(error_message)
        self.engine = create_async_engine(
            url.update_query_dict({"charset": "utf8mb4"}),
            pool_pre_ping=True,
            pool_timeout=5,
            connect_args={"connect_timeout": 5},
            hide_parameters=True,
        )

    async def init_schema(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)

    async def check_ready(self):
        async with self.engine.connect() as connection:
            await connection.execute(select(literal(1)).select_from(accounts).limit(1))
            await connection.execute(select(literal(1)).select_from(legacy_workspaces).limit(1))

    async def close(self):
        await self.engine.dispose()

    async def create(self, username: str, password_hash: str):
        identifier = uuid.uuid4().hex
        try:
            async with self.engine.begin() as connection:
                await connection.execute(accounts.insert().values(
                    id=identifier,
                    username=username.strip(),
                    username_key=username_key(username).encode(),
                    password_hash=password_hash,
                    storage_user_id=identifier.encode(),
                    created_at=int(time.time()),
                ))
        except IntegrityError as error:
            if error.orig.args[0] != _DUPLICATE_ENTRY:
                raise
            raise HTTPException(409, "用户名已被使用。") from error
        return identifier

    async def get(self, identifier: str = "", *, username: str | None = None):
        condition = (
            accounts.c.username_key == username_key(username).encode()
            if username is not None else accounts.c.id == identifier
        )
        async with self.engine.connect() as connection:
            result = await connection.execute(select(accounts).where(condition))
            row = result.mappings().one_or_none()
        if row is None:
            return None
        return {
            **row,
            "username_key": row["username_key"].decode(),
            "storage_user_id": row["storage_user_id"].decode(),
        }

    async def legacy_root(self, storage_user_id: str, agent_id: str):
        async with self.engine.connect() as connection:
            result = await connection.execute(select(legacy_workspaces.c.path).where(
                legacy_workspaces.c.storage_user_id == storage_user_id.encode(),
                legacy_workspaces.c.agent_id == agent_id.encode(),
            ))
            path = result.scalar_one_or_none()
        return Path(path) if path is not None else None

    async def bind_legacy(self, identifier: str, legacy_id: str, roots: dict[str, Path]):
        """Atomically bind an account and its legacy workspace mappings."""
        try:
            async with self.engine.begin() as connection:
                result = await connection.execute(
                    select(accounts.c.storage_user_id).where(accounts.c.id == identifier).with_for_update()
                )
                if result.scalar_one_or_none() != identifier.encode():
                    raise ValueError("该账号不存在或已绑定旧业务身份。")
                await connection.execute(accounts.update().where(accounts.c.id == identifier).values(
                    storage_user_id=legacy_id.encode(),
                ))
                if roots:
                    await connection.execute(legacy_workspaces.insert(), [
                        _workspace_values(legacy_id, agent_id, str(path)) for agent_id, path in roots.items()
                    ])
        except IntegrityError as error:
            if error.orig.args[0] != _DUPLICATE_ENTRY:
                raise
            raise ValueError("旧业务身份或目录已经绑定到其他账号。") from error

    async def import_legacy_rows(self, users: list[dict], workspaces: list[dict]):
        async with self.engine.begin() as connection:
            for table in (accounts, legacy_workspaces):
                result = await connection.execute(select(literal(1)).select_from(table).limit(1))
                if result.scalar_one_or_none() is not None:
                    raise ValueError("MySQL 账号库已有数据，导入仅支持空库。")
            if users:
                await connection.execute(accounts.insert(), [
                    {**row, "username_key": row["username_key"].encode(),
                     "storage_user_id": row["storage_user_id"].encode()}
                    for row in users
                ])
            if workspaces:
                await connection.execute(legacy_workspaces.insert(), [_workspace_values(**row) for row in workspaces])


def public_account(account: dict) -> dict:
    return {key: account[key] for key in ("id", "username", "created_at")}
