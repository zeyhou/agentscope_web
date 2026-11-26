"""初始化或迁移账号库，以及管理旧业务身份绑定。"""
import argparse
import asyncio
import json
from pathlib import Path

from redis.asyncio import Redis

from .accounts import MAX_STORAGE_USER_ID_BYTES, AccountStore
from .config import AuthSettings, backend_path, business_redis_url


async def resource_counts(redis, user_id):
    # 只统计键和索引，不读取、更不打印模型 API Key 或文档正文。
    keys = [key async for key in redis.scan_iter(match=f"agentscope:user:{user_id}:*")]
    return len(keys)


async def run(args):
    settings = AuthSettings()
    if args.command == "list-legacy":
        async with Redis.from_url(business_redis_url(), decode_responses=True) as redis:
            owners = {key.split(":")[2] async for key in redis.scan_iter(match="agentscope:user:*:*")}
            for owner in sorted(owners):
                print(json.dumps({"legacy_user_id": owner, "redis_keys": await resource_counts(redis, owner)}, ensure_ascii=False))
        return

    accounts = AccountStore(settings.mysql_url)
    try:
        if args.command == "init-db":
            await accounts.init_schema()
            print("MySQL 账号表和旧工作区映射表已就绪。")
        elif args.command == "import-sqlite":
            from .legacy_import import read_sqlite_accounts

            users, workspaces = read_sqlite_accounts(args.source)
            await accounts.import_legacy_rows(users, workspaces)
            print(f"已导入 {len(users)} 个账号和 {len(workspaces)} 条旧工作区映射。")
        else:
            await bind_legacy(args, accounts, settings)
    finally:
        await accounts.close()


async def bind_legacy(args, accounts, settings):
    workspace_dir = backend_path("AGENTSCOPE_WORKSPACES_DIR", "workspaces").resolve()
    async with Redis.from_url(business_redis_url(), decode_responses=True) as redis:
        account = await accounts.get(username=args.username)
        if account is None:
            raise ValueError("请先在页面注册该账号。")
        if account["storage_user_id"] != account["id"]:
            raise ValueError("该账号已绑定旧业务身份，未进行修改。")
        if await resource_counts(redis, account["storage_user_id"]):
            raise ValueError("新账号已经产生业务数据；请先处理归属，不能直接覆盖身份映射。")
        if not 1 <= len(args.legacy_id) <= MAX_STORAGE_USER_ID_BYTES or not args.legacy_id.isascii() or any(c in args.legacy_id for c in ":*?[]"):
            raise ValueError("旧业务身份应为 1–1024 个 ASCII 字符，且不能含 Redis 模式字符。")
        if not await resource_counts(redis, args.legacy_id):
            raise ValueError("找不到该旧业务身份的数据。")
        roots = {}
        # 旧目录采用显式映射，历史消息里的文件路径和会话 cwd 无需重写。
        for agent_id in await redis.smembers(f"agentscope:user:{args.legacy_id}:agents"):
            root = (workspace_dir / agent_id).resolve()
            if root.is_dir() and root.parent == workspace_dir:
                roots[agent_id] = root
        print(json.dumps({"username": account["username"], "legacy_user_id": args.legacy_id,
                          "workspace_count": len(roots), "apply": args.apply}, ensure_ascii=False))
        if args.apply:
            await accounts.bind_legacy(account["id"], args.legacy_id, roots)
            # 旧身份绑定后撤销该账号现有登录，要求刷新身份和工作区视图。
            async with Redis.from_url(settings.redis_url, decode_responses=True) as sessions:
                async for key in sessions.scan_iter(match=settings.prefix + "session:*"):
                    raw = await sessions.get(key)
                    if raw and json.loads(raw)["account_id"] == account["id"]:
                        await sessions.delete(key)
            print("绑定完成，请重新登录；原业务数据与向量集合均未移动。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="在配置的 MySQL 数据库中创建项目账号表")
    import_cmd = commands.add_parser("import-sqlite", help="离线导入已有 SQLite 账号库到空 MySQL 账号表")
    import_cmd.add_argument("--source", type=Path, required=True)
    commands.add_parser("list-legacy")
    bind = commands.add_parser("bind-legacy")
    bind.add_argument("--username", required=True)
    bind.add_argument("--legacy-id", required=True)
    bind.add_argument("--apply", action="store_true", help="不传此参数时仅预览绑定")
    asyncio.run(run(parser.parse_args()))
