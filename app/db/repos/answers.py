import sqlite3
from typing import Any


def get_answer(connection: sqlite3.Connection, answer_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM answers WHERE id=?", (answer_id,)
    ).fetchone()
    return row
