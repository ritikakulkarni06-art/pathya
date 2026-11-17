import json
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.jobs import finish, progress
from app.services.manifests import assert_job_lease, publish_manifest


def handle(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    payload = json.loads(job["payload_json"])
    revision = int(payload["revision"])
    lease = (job["id"], job["lease_owner"])
    with database.read_conn() as connection:
        document = connection.execute(
            "SELECT * FROM documents WHERE id=?", (job["document_id"],)
        ).fetchone()
    if document is None or document["current_revision"] != revision:
        finish(database, *lease, "ready", "A newer correction superseded this rebuild.")
        return
    progress(
        database,
        *lease,
        "building",
        0,
        0,
        "Rebuilding current chapter outputs; text remains available.",
    )
    with database.write_tx() as connection:
        assert_job_lease(connection, lease)
        current = connection.execute(
            "SELECT current_revision FROM documents WHERE id=?", (job["document_id"],)
        ).fetchone()
        if current is None or current["current_revision"] != revision:
            connection.execute(
                "UPDATE jobs SET state='ready',lease_owner=NULL,lease_expires_at=NULL,progress_json=?,updated_at=? WHERE id=? AND lease_owner=?",
                (
                    json.dumps({"message": "A newer correction superseded this rebuild."}),
                    now_utc(),
                    job["id"],
                    job["lease_owner"],
                ),
            )
            return
        blocks = list(
            connection.execute(
                "SELECT * FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0 ORDER BY page_id,order_key,id",
                (job["document_id"],),
            )
        )
        connection.execute(
            "UPDATE chunks SET status='stale',eligible=0 WHERE document_id=? AND revision<>?",
            (job["document_id"], revision),
        )
        # P8 baseline indexes prose only. P10 replaces this with the full structured chunker.
        for block in blocks:
            if (
                block["type"] in {"heading", "paragraph", "list_item", "caption"}
                and block["status"] in {"ok", "corrected", "reviewed", "not_scored"}
                and not block["critical_flag"]
            ):
                ids = json.dumps([block["id"]])
                existing = connection.execute(
                    "SELECT id FROM chunks WHERE document_id=? AND revision=? AND block_ids_json=? AND text=?",
                    (job["document_id"], revision, ids, block["text_current"]),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?, ?,1,'current')",
                        (
                            str(uuid4()),
                            job["document_id"],
                            revision,
                            ids,
                            "",
                            block["text_current"],
                            max(1, len(block["text_current"].split())),
                            json.dumps([block["page_id"]]),
                        ),
                    )
            if payload.get("block_ids") and block["id"] not in payload["block_ids"]:
                continue
    from app.services.speech import build_block

    failure: Problem | None = None
    for block in blocks:
        if payload.get("block_ids") and block["id"] not in payload["block_ids"]:
            continue
        try:
            build_block(database, settings, block["id"], settings.speech_voice, lease=lease)
        except Problem as error:
            failure = error
            break
    publish_manifest(database, settings.pathya_data_dir, job["document_id"], revision, lease=lease)
    if failure is not None:
        raise failure
    finish(
        database,
        *lease,
        "ready",
        "Current text and manifest are ready. Unavailable audio has an explicit text fallback.",
    )
