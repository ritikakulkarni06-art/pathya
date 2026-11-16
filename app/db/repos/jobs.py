import sqlite3
from typing import Any


def get_job(connection: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    return row
