import json
import sqlite3
from uuid import uuid4

from app.logging import scrub


def record(
    connection: sqlite3.Connection,
    actor_id: str,
    action: str,
    document_id: str | None,
    target_id: str | None,
    now: str,
    metadata: dict[str, str],
) -> None:
    connection.execute(
        "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?)",
        (str(uuid4()), actor_id, action, document_id, target_id, now, json.dumps(scrub(metadata))),
    )
