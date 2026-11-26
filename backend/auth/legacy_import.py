"""Read a SQLite account snapshot for the offline MySQL import command."""

from contextlib import closing
from pathlib import Path
import sqlite3


def read_sqlite_accounts(source: Path):
    uri = source.resolve(strict=True).as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        accounts = connection.execute(
            "SELECT id, username, username_key, password_hash, storage_user_id, enabled, created_at FROM accounts"
        )
        workspaces = connection.execute("SELECT storage_user_id, agent_id, path FROM legacy_workspaces")
        return [dict(row) for row in accounts], [dict(row) for row in workspaces]
