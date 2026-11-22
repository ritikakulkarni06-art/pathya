import sqlite3
from typing import Any


def put(
    connection: sqlite3.Connection,
    document_id: str,
    user_id: str,
    role: str,
    granted_by: str,
    now: str,
) -> None:
    connection.execute(
        "INSERT INTO document_grants(document_id,user_id,role,granted_by,created_at) VALUES (?,?,?,?,?) ON CONFLICT(document_id,user_id) DO UPDATE SET role=excluded.role,granted_by=excluded.granted_by,created_at=excluded.created_at",
        (document_id, user_id, role, granted_by, now),
    )


def remove(connection: sqlite3.Connection, document_id: str, user_id: str) -> None:
    connection.execute(
        "DELETE FROM document_grants WHERE document_id=? AND user_id=?", (document_id, user_id)
    )


def list_for_document(connection: sqlite3.Connection, document_id: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT document_grants.user_id,users.email,document_grants.role,document_grants.created_at FROM document_grants JOIN users ON users.id=document_grants.user_id WHERE document_grants.document_id=? ORDER BY users.email",
            (document_id,),
        )
    ]
