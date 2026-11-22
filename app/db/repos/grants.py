import sqlite3


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
