import sqlite3
from typing import Any


def get_job(connection: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    return row


def for_document(
    connection: sqlite3.Connection, document_id: str, kind: str
) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM jobs WHERE document_id=? AND kind=? ORDER BY created_at LIMIT 1",
        (document_id, kind),
    ).fetchone()
    return row


def enqueue(
    connection: sqlite3.Connection,
    document_id: str | None,
    kind: str,
    payload: dict[str, Any],
    max_attempts: int,
    idempotency_key: str | None,
    now: str,
) -> str:
    import json
    from uuid import uuid4

    if idempotency_key:
        existing = connection.execute(
            "SELECT id FROM jobs WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if existing:
            return str(existing["id"])
    job_id = str(uuid4())
    connection.execute(
        "INSERT INTO jobs(id,document_id,kind,state,payload_json,max_attempts,idempotency_key,created_at,updated_at) VALUES (?,?,?,'queued',?,?,?,?,?)",
        (job_id, document_id, kind, json.dumps(payload), max_attempts, idempotency_key, now, now),
    )
    return job_id
