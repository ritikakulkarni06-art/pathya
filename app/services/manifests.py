import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.db.connection import Database
from app.db.repos.extraction import has_incomplete_p1_pages
from app.errors import Problem
from app.services.jobs import LeaseLost
from app.services.storage import FileStore


def assert_job_lease(connection: sqlite3.Connection, lease: tuple[str, str] | None) -> None:
    if lease is None:
        return
    row = connection.execute("SELECT * FROM jobs WHERE id=? AND lease_owner=?", lease).fetchone()
    if (
        row is None
        or row["state"] not in {"validating", "extracting", "building"}
        or row["lease_expires_at"] <= now_utc()
    ):
        raise LeaseLost()


def artifact_current(connection: sqlite3.Connection, artifact: dict[str, Any]) -> bool:
    if artifact["status"] != "ready":
        return False
    dependencies = json.loads(artifact["dependency_revisions_json"])
    if not dependencies:
        return False
    for block_id, revision in dependencies.items():
        row = connection.execute(
            "SELECT revision,successor_ids_json FROM blocks WHERE id=? AND document_id=?",
            (block_id, artifact["document_id"]),
        ).fetchone()
        if row is None or row["revision"] != revision or json.loads(row["successor_ids_json"]):
            return False
    return True


def _audio_entry(
    connection: sqlite3.Connection, store: FileStore, block: dict[str, Any]
) -> dict[str, Any]:
    entries = connection.execute(
        "SELECT * FROM artifacts WHERE document_id=? AND block_id=? AND kind='audio_block' AND scope_user_id IS NULL ORDER BY updated_at DESC,id DESC",
        (block["document_id"], block["id"]),
    ).fetchall()
    for artifact in entries:
        if artifact_current(connection, artifact):
            asset = connection.execute(
                "SELECT * FROM assets WHERE id=? AND document_id=? AND deleted_at IS NULL",
                (artifact["asset_id"], block["document_id"]),
            ).fetchone()
            if asset is None:
                raise Problem(
                    409,
                    "manifest_asset_invalid",
                    "An audio file is missing. Rebuild it; chapter text remains available.",
                )
            path = store.safe_path(*asset["private_path"].split("/"))
            if not path.is_file() or path.stat().st_size != asset["bytes"]:
                raise Problem(
                    409,
                    "manifest_asset_invalid",
                    "An audio file could not be verified. Rebuild it; chapter text remains available.",
                )
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != asset["sha256"] or artifact["content_hash"] != digest:
                raise Problem(
                    409,
                    "manifest_asset_invalid",
                    "An audio checksum is invalid. Rebuild it; chapter text remains available.",
                )
            sentence_manifest = connection.execute(
                "SELECT body_json FROM audio_manifests WHERE artifact_id=?", (artifact["id"],)
            ).fetchone()
            if sentence_manifest is not None:
                for unit in json.loads(sentence_manifest["body_json"])["units"]:
                    clip = connection.execute(
                        "SELECT * FROM assets WHERE id=? AND document_id=? AND deleted_at IS NULL",
                        (unit["clip_asset_id"], block["document_id"]),
                    ).fetchone()
                    if (
                        clip is None
                        or clip["bytes"] != unit["bytes"]
                        or clip["sha256"] != unit["hash"]
                    ):
                        raise Problem(
                            409,
                            "manifest_asset_invalid",
                            "An audio clip could not be verified. Request a rebuild; text remains available.",
                        )
                    clip_path = store.safe_path(*clip["private_path"].split("/"))
                    if not clip_path.is_file() or clip_path.stat().st_size != clip["bytes"]:
                        raise Problem(
                            409,
                            "manifest_asset_invalid",
                            "An audio clip is missing. Request a rebuild; text remains available.",
                        )
                    with clip_path.open("rb") as clip_stream:
                        if hashlib.file_digest(clip_stream, "sha256").hexdigest() != clip["sha256"]:
                            raise Problem(
                                409,
                                "manifest_asset_invalid",
                                "An audio clip could not be verified. Request a rebuild; text remains available.",
                            )
            return {
                "block_id": block["id"],
                "artifact_id": artifact["id"],
                "asset_id": asset["id"],
                "hash": digest,
                "bytes": asset["bytes"],
                "status": "ready",
                "voice": artifact["voice"],
                "engine_version": artifact["engine_version"],
                "synthetic": str(artifact["engine_version"] or "").startswith("stub-"),
            }
    failed = next(
        (
            entry
            for entry in entries
            if entry["status"] == "failed"
            and json.loads(entry["dependency_revisions_json"]).get(block["id"]) == block["revision"]
        ),
        None,
    )
    return {
        "block_id": block["id"],
        "status": "text_only" if failed else "pending",
        "reason": failed["stale_reason"] if failed else "audio_pending",
        "text_available": True,
    }


def publish_manifest(
    database: Database,
    data_dir: Path,
    document_id: str,
    revision: int,
    *,
    lease: tuple[str, str] | None = None,
) -> dict[str, Any]:
    store = FileStore(data_dir, database, min_free_bytes=0)
    with database.write_tx() as connection:
        assert_job_lease(connection, lease)
        document = connection.execute(
            "SELECT * FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if document is None or document["state"] in {"deleting", "deleted"}:
            raise Problem(404, "document_not_found", "This document is unavailable.")
        if document["current_revision"] != revision:
            raise Problem(
                409,
                "stale_revision",
                "The chapter changed before publication. Rebuild the current revision.",
            )
        blocks = list(
            connection.execute(
                "SELECT blocks.*,pages.pdf_index_0 FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(blocks.successor_ids_json)=0 ORDER BY pages.pdf_index_0,blocks.order_key,blocks.id",
                (document_id,),
            )
        )
        ids = {block["id"] for block in blocks}
        orders = set()
        for block in blocks:
            key = (block["page_id"], block["parent_id"], block["order_key"])
            if key in orders or (block["parent_id"] and block["parent_id"] not in ids):
                raise Problem(
                    409,
                    "manifest_structure_invalid",
                    "The reading structure needs reconciliation before publication.",
                )
            orders.add(key)
        summaries = []
        for block in blocks:
            metadata = json.loads(block["metadata_json"])
            if block["status"] != "reviewed":
                metadata = {
                    key: value
                    for key, value in metadata.items()
                    if key
                    not in {"mathml", "spoken_fallback", "alt_text_short", "alt_text_extended"}
                }
            summaries.append(
                {
                    "id": block["id"],
                    "page_id": block["page_id"],
                    "revision": block["revision"],
                    "type": block["type"],
                    "parent_id": block["parent_id"],
                    "order_key": block["order_key"],
                    "lang": block["lang"],
                    "status": block["status"],
                    "critical_flag": bool(block["critical_flag"]),
                    "text_hash": hashlib.sha256(block["text_current"].encode()).hexdigest(),
                    "metadata": metadata,
                }
            )
        edges = [
            dict(edge)
            for edge in connection.execute(
                "SELECT from_id,relation,to_id FROM edges WHERE document_id=? ORDER BY from_id,relation,to_id",
                (document_id,),
            )
            if edge["from_id"] in ids and edge["to_id"] in ids
        ]
        import_metadata = connection.execute(
            "SELECT metadata_json FROM extraction_imports WHERE document_id=?", (document_id,)
        ).fetchone()
        quality = (
            json.loads(import_metadata["metadata_json"]).get("quality_flags", [])
            if import_metadata
            else []
        )
        body = {
            "demo_mode": "synthetic_demo_only" in quality,
            "import_quality_flags": quality,
            "document_id": document_id,
            "revision": revision,
            "pages": list(
                connection.execute(
                    "SELECT id,pdf_index_0,printed_label,width,height,rotation FROM pages WHERE document_id=? ORDER BY pdf_index_0",
                    (document_id,),
                )
            ),
            "blocks": summaries,
            "edges": edges,
            "artifacts": [_audio_entry(connection, store, block) for block in blocks],
            "packages": [],
            "text_available": True,
        }
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        sha256 = hashlib.sha256(encoded.encode()).hexdigest()
        latest = connection.execute(
            "SELECT * FROM manifests WHERE document_id=? AND revision=? ORDER BY build_seq DESC LIMIT 1",
            (document_id, revision),
        ).fetchone()
        if latest is not None and latest["sha256"] == sha256:
            return dict(latest)
        manifest_id = str(uuid4())
        sequence = latest["build_seq"] + 1 if latest else 1
        connection.execute(
            "INSERT INTO manifests VALUES (?,?,?,?,?,?,?)",
            (manifest_id, document_id, revision, sequence, encoded, sha256, now_utc()),
        )
        review = has_incomplete_p1_pages(connection, document_id) or any(
            block["critical_flag"] or block["status"] == "needs_review" for block in blocks
        )
        connection.execute(
            "UPDATE documents SET state=?,updated_at=? WHERE id=?",
            ("review_required" if review else "ready", now_utc(), document_id),
        )
        result = connection.execute("SELECT * FROM manifests WHERE id=?", (manifest_id,)).fetchone()
        assert result is not None
        return dict(result)
