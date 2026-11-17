import json
from typing import Any

from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.jobs import finish, progress
from app.services.manifests import publish_manifest
from app.services.speech import build_block


def handle(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    payload = json.loads(job["payload_json"])
    with database.read_conn() as connection:
        document = connection.execute(
            "SELECT * FROM documents WHERE id=?", (job["document_id"],)
        ).fetchone()
        blocks = list(
            connection.execute(
                "SELECT id FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0 ORDER BY page_id,order_key",
                (job["document_id"],),
            )
        )
    if document is None:
        return
    revision = document["current_revision"]
    selected = set(payload.get("block_ids") or [row["id"] for row in blocks])
    total = len(selected)
    done = 0
    failure: Problem | None = None
    for block in blocks:
        if block["id"] not in selected:
            continue
        progress(
            database,
            job["id"],
            job["lease_owner"],
            "building",
            total,
            done,
            "Preparing sentence audio. Text remains available.",
        )
        try:
            build_block(
                database,
                settings,
                block["id"],
                payload.get("voice") or settings.speech_voice,
                user_id=payload.get("user_id"),
                lease=(job["id"], job["lease_owner"]),
            )
        except Problem as error:
            failure = error
            break
        done += 1
    # Shared manifests exclude private per-user overrides.
    publish_manifest(
        database,
        settings.pathya_data_dir,
        job["document_id"],
        revision,
        lease=(job["id"], job["lease_owner"]),
    )
    if failure is not None:
        raise failure
    finish(
        database,
        job["id"],
        job["lease_owner"],
        "ready",
        "Audio processing completed with explicit availability labels.",
    )
