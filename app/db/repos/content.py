import sqlite3
from typing import Any


def get_block(connection: sqlite3.Connection, block_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM blocks WHERE id=?", (block_id,)
    ).fetchone()
    return row
