import sqlite3
from typing import Any

from app.db.repos.content import NEEDS_REVIEW

DOCUMENT_COUNTS = f"""
SELECT documents.*,
    (SELECT count(*) FROM pages WHERE pages.document_id=documents.id) AS pages_count,
    (SELECT count(*) FROM blocks WHERE blocks.document_id=documents.id) AS blocks_count,
    (SELECT count(*) FROM blocks WHERE blocks.document_id=documents.id
        AND {NEEDS_REVIEW}) AS review_count
FROM documents
"""


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


def by_source(connection: sqlite3.Connection, owner_id: str, sha256: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM documents WHERE owner_id=? AND source_sha256=? AND deleted_at IS NULL",
        (owner_id, sha256),
    ).fetchone()
    return row


def create_document(
    connection: sqlite3.Connection,
    document_id: str,
    owner_id: str,
    title: str,
    sha256: str,
    rights_note: str,
    languages: list[str],
    retention_until: str,
    now: str,
) -> None:
    import json

    connection.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?,0,'uploading',?,?,?,NULL)",
        (
            document_id,
            owner_id,
            title,
            sha256,
            rights_note,
            json.dumps(languages),
            retention_until,
            now,
            now,
        ),
    )


def set_state(connection: sqlite3.Connection, document_id: str, state: str, now: str) -> None:
    connection.execute(
        "UPDATE documents SET state=?,updated_at=? WHERE id=?", (state, now, document_id)
    )


def accessible(connection: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    return list(
        connection.execute(
            DOCUMENT_COUNTS
            + """WHERE state NOT IN ('deleting','deleted') AND (owner_id=? OR EXISTS (
                SELECT 1 FROM document_grants WHERE document_grants.document_id=documents.id
                AND user_id=?)) ORDER BY created_at DESC""",
            (user_id, user_id),
        )
    )


def with_counts(connection: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        DOCUMENT_COUNTS + "WHERE id=?",
        (document_id,),
    ).fetchone()
    return row
