import json
from typing import Any

from app.config import Settings
from app.db.connection import Database
from app.services.jobs import finish, progress
from app.services.retrieval.index import build_index


def handle(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    lease = (job["id"], job["lease_owner"])
    payload = json.loads(job["payload_json"])
    with database.read_conn() as connection:
        current = connection.execute(
            "SELECT current_revision FROM documents WHERE id=?", (job["document_id"],)
        ).fetchone()
    if (
        current
        and payload.get("revision", current["current_revision"]) != current["current_revision"]
    ):
        finish(database, *lease, "ready", "A newer chapter revision superseded this index request.")
        return
    progress(database, *lease, "building", 0, 0, "Building the current eligible evidence index.")
    count = build_index(database, settings, job["document_id"], lease=lease)
    finish(
        database,
        *lease,
        "ready",
        "The current chapter search index is ready: " + str(count) + " chunks.",
    )
