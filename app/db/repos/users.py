import sqlite3
from typing import Any


def get_user(connection: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return row


def by_email(connection: sqlite3.Connection, email: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM users WHERE email=?", (email,)
    ).fetchone()
    return row


def create(
    connection: sqlite3.Connection,
    user_id: str,
    email: str,
    password_hash: str | None,
    created_at: str,
) -> None:
    connection.execute(
        "INSERT INTO users(id,email,password_hash,role,created_at) VALUES (?,?,?,'user',?)",
        (user_id, email, password_hash, created_at),
    )
