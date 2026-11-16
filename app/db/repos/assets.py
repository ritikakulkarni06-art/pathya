import sqlite3
from typing import Any


def get_asset(connection: sqlite3.Connection, asset_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM assets WHERE id=? AND deleted_at IS NULL", (asset_id,)
    ).fetchone()
    return row
