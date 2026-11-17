import hashlib
import json
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.services.jobs import finish, progress
from app.services.manifests import artifact_current, assert_job_lease, publish_manifest


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
            audio = connection.execute(
                "SELECT * FROM artifacts WHERE document_id=? AND block_id=? AND kind='audio_block'",
                (job["document_id"], block["id"]),
            ).fetchall()
            if not any(artifact_current(connection, item) for item in audio) and not any(
                item["status"] == "failed"
                and json.loads(item["dependency_revisions_json"]).get(block["id"])
                == block["revision"]
                for item in audio
            ):
                now = now_utc()
                connection.execute(
                    "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,content_hash,language,status,created_at,updated_at,stale_reason) VALUES (?,?,'audio_block',?,?,?,?,'failed',?,?,'speech_adapter_unavailable')",
                    (
                        str(uuid4()),
                        job["document_id"],
                        block["id"],
                        json.dumps({block["id"]: block["revision"]}),
                        hashlib.sha256(block["text_current"].encode()).hexdigest(),
                        block["lang"],
                        now,
                        now,
                    ),
                )
    publish_manifest(database, settings.pathya_data_dir, job["document_id"], revision, lease=lease)
    finish(
        database,
        *lease,
        "ready",
        "Current text and manifest are ready. Unavailable audio has an explicit text fallback.",
    )
