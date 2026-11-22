import sqlite3
from typing import Any


def create(
    connection: sqlite3.Connection,
    session_id: str,
    user_id: str,
    token_hash: str,
    created_at: str,
    expires_at: str,
) -> None:
    connection.execute(
        "INSERT INTO sessions(id,user_id,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)",
        (session_id, user_id, token_hash, created_at, expires_at),
    )


def active_user(connection: sqlite3.Connection, token_hash: str, now: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.revoked_at IS NULL AND sessions.expires_at>?",
        (token_hash, now),
    ).fetchone()
    return row


def revoke(connection: sqlite3.Connection, token_hash: str, now: str) -> None:
    connection.execute(
        "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
        (now, token_hash),
    )


def revoke_all(connection: sqlite3.Connection, user_id: str, now: str) -> None:
    connection.execute(
        "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now, user_id)
    )
