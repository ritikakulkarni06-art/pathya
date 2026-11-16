import sqlite3
from typing import Any


def get_document(connection: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM documents WHERE id=?", (document_id,)
    ).fetchone()
    return row


def get_grant(
    connection: sqlite3.Connection, document_id: str, user_id: str
) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM document_grants WHERE document_id=? AND user_id=?", (document_id, user_id)
    ).fetchone()
    return row
