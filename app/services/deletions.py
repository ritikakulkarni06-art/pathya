import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.db.repos.jobs import enqueue
from app.errors import Problem
from app.services.access import check_document
from app.services.manifests import assert_job_lease
from app.services.storage import FileStore


def public_receipt(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "receipt_id": row["id"],
        "document_id": row["document_id"],
        "requested_at": row["requested_at"],
        "completes_by": row["completes_by"],
        "status": row["status"],
        "status_url": "/deletions/" + row["id"],
        "completed_at": row["completed_at"],
        "counts": json.loads(row["counts_json"]),
        "error_code": row["error_code"],
        "purge_local_copy": True,
        "overdue": row["status"] != "complete" and row["completes_by"] < now_utc(),
    }


def _request(
    c: sqlite3.Connection,
    settings: Settings,
    document_id: str,
    owner_id: str,
    *,
    only_expired: bool = False,
) -> dict[str, Any] | None:
    doc = c.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
    if doc is None:
        raise Problem(404, "document_not_found", "This document is unavailable.")
    if doc["owner_id"] != owner_id:
        check_document(c, document_id, owner_id, "owner")
    old = c.execute(
        "SELECT * FROM deletion_receipts WHERE document_id=?", (document_id,)
    ).fetchone()
    if old:
        return public_receipt(old)
    if only_expired and doc["retention_until"] > now_utc():
        return None
    check_document(c, document_id, owner_id, "owner")
    instant = datetime.now(UTC)
    receipt_id = str(uuid4())
    c.execute(
        "INSERT INTO deletion_receipts(id,document_id,owner_id,requested_at,completes_by,status) VALUES (?,?,?,?,?,'pending')",
        (
            receipt_id,
            document_id,
            owner_id,
            instant.isoformat(),
            (instant + timedelta(days=settings.deletion_sla_days)).isoformat(),
        ),
    )
    c.execute(
        "UPDATE documents SET state='deleting',updated_at=? WHERE id=?",
        (instant.isoformat(), document_id),
    )
    c.execute("DELETE FROM document_grants WHERE document_id=?", (document_id,))
    c.execute(
        "UPDATE jobs SET state='cancelled',lease_owner=NULL,lease_expires_at=NULL,updated_at=?,error_code='deletion_requested',error_message='Deletion was requested. Processing stopped.' WHERE document_id=? AND state IN ('queued','validating','extracting','building')",
        (instant.isoformat(), document_id),
    )
    c.execute(
        "UPDATE artifacts SET status='stale',stale_reason='deletion_requested' WHERE document_id=?",
        (document_id,),
    )
    c.execute("UPDATE chunks SET status='stale',eligible=0 WHERE document_id=?", (document_id,))
    c.execute(
        "UPDATE chunk_embeddings SET status='stale' WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)",
        (document_id,),
    )
    c.execute("UPDATE answers SET status='stale' WHERE document_id=?", (document_id,))
    enqueue(
        c,
        document_id,
        "delete",
        {"receipt_id": receipt_id},
        settings.job_max_attempts,
        "delete:" + receipt_id,
        instant.isoformat(),
    )
    c.execute(
        "INSERT INTO audit_log VALUES (?,?, 'deletion_requested',?,?,?, '{}')",
        (str(uuid4()), owner_id, document_id, receipt_id, instant.isoformat()),
    )
    return public_receipt(
        c.execute("SELECT * FROM deletion_receipts WHERE id=?", (receipt_id,)).fetchone()
    )


def request_delete(
    database: Database, settings: Settings, document_id: str, owner_id: str
) -> dict[str, Any]:
    with database.write_tx() as c:
        result = _request(c, settings, document_id, owner_id)
    assert result is not None
    return result


def get_receipt(database: Database, receipt_id: str, owner_id: str) -> dict[str, Any]:
    with database.read_conn() as c:
        row = c.execute(
            "SELECT * FROM deletion_receipts WHERE id=? AND owner_id=?", (receipt_id, owner_id)
        ).fetchone()
    if row is None:
        raise Problem(404, "receipt_not_found", "This deletion receipt is unavailable.")
    return public_receipt(row)


def retry_delete(
    database: Database, settings: Settings, receipt_id: str, owner_id: str
) -> dict[str, Any]:
    with database.write_tx() as c:
        row = c.execute(
            "SELECT * FROM deletion_receipts WHERE id=? AND owner_id=?", (receipt_id, owner_id)
        ).fetchone()
        if row is None:
            raise Problem(404, "receipt_not_found", "This deletion receipt is unavailable.")
        if row["status"] == "failed":
            enqueue(
                c,
                row["document_id"],
                "delete",
                {"receipt_id": receipt_id},
                settings.job_max_attempts,
                None,
                now_utc(),
            )
            c.execute(
                "UPDATE deletion_receipts SET status='pending',error_code=NULL WHERE id=?",
                (receipt_id,),
            )
            row = c.execute("SELECT * FROM deletion_receipts WHERE id=?", (receipt_id,)).fetchone()
    return public_receipt(row)


PURGE_QUERIES = [
    ("packages", "DELETE FROM packages WHERE document_id=?"),
    (
        "audio_manifests",
        "DELETE FROM audio_manifests WHERE artifact_id IN (SELECT id FROM artifacts WHERE document_id=?)",
    ),
    (
        "artifact_clips",
        "DELETE FROM artifact_clips WHERE artifact_id IN (SELECT id FROM artifacts WHERE document_id=?)",
    ),
    ("artifacts", "DELETE FROM artifacts WHERE document_id=?"),
    (
        "embeddings",
        "DELETE FROM chunk_embeddings WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)",
    ),
    (
        "chunk_metadata",
        "DELETE FROM chunk_metadata WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)",
    ),
    (
        "chunk_ngrams",
        "DELETE FROM chunk_ngrams WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=?)",
    ),
    ("chunks", "DELETE FROM chunks WHERE document_id=?"),
    ("answers", "DELETE FROM answers WHERE document_id=?"),
    ("candidates", "DELETE FROM reextraction_candidates WHERE document_id=?"),
    ("corrections", "DELETE FROM corrections WHERE document_id=?"),
    (
        "block_versions",
        "DELETE FROM block_versions WHERE block_id IN (SELECT id FROM blocks WHERE document_id=?)",
    ),
    ("edges", "DELETE FROM edges WHERE document_id=?"),
    ("blocks", "DELETE FROM blocks WHERE document_id=?"),
    ("pages", "DELETE FROM pages WHERE document_id=?"),
    ("assets", "DELETE FROM assets WHERE document_id=?"),
    ("import_receipts", "DELETE FROM extraction_imports WHERE document_id=?"),
    ("identifier_maps", "DELETE FROM extraction_identifiers WHERE document_id=?"),
    ("glossary_terms", "DELETE FROM glossary_terms WHERE document_id=?"),
    ("manifests", "DELETE FROM manifests WHERE document_id=?"),
    ("revisions", "DELETE FROM revisions WHERE document_id=?"),
]


def purge_document(
    database: Database,
    settings: Settings,
    document_id: str,
    *,
    lease: tuple[str, str] | None = None,
) -> bool:
    with database.read_conn() as c:
        assert_job_lease(c, lease)
        doc = c.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if doc is None or doc["state"] not in {"deleting", "deleted"}:
            raise Problem(
                409, "deletion_not_requested", "Request deletion before purging this document."
            )
        if doc["state"] == "deleted":
            return True
    store = FileStore(settings.pathya_data_dir, database, min_free_bytes=0)
    removed = store.secure_delete_document(document_id)
    absent = all(
        not store.safe_path(section, document_id).exists() for section in ("sources", "derived")
    )
    with database.write_tx() as c:
        assert_job_lease(c, lease)
        if (
            c.execute("SELECT state FROM documents WHERE id=?", (document_id,)).fetchone()["state"]
            == "deleted"
        ):
            return True
        c.execute("PRAGMA secure_delete=ON")
        row = c.execute(
            "SELECT * FROM deletion_receipts WHERE document_id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise Problem(
                409, "receipt_not_found", "A deletion receipt is required before purging."
            )
        counts = json.loads(row["counts_json"])
        counts["files_removed"] = counts.get("files_removed", 0) + removed.files_removed
        counts["bytes_removed"] = counts.get("bytes_removed", 0) + removed.bytes_removed
        if removed.failures or not absent:
            c.execute(
                "UPDATE deletion_receipts SET status='failed',counts_json=?,error_code='file_removal_failed' WHERE id=?",
                (json.dumps(counts), row["id"]),
            )
            return False
        c.execute("INSERT INTO purge_guards VALUES (?)", (document_id,))
        for label, query in PURGE_QUERIES:
            counts[label] = c.execute(query, (document_id,)).rowcount
        c.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        c.execute("UPDATE audit_log SET meta_json='{}' WHERE document_id=?", (document_id,))
        # Keep only the active deletion job needed for lease/final-state publication.
        if lease:
            c.execute("DELETE FROM jobs WHERE document_id=? AND id<>?", (document_id, lease[0]))
        else:
            c.execute("DELETE FROM jobs WHERE document_id=?", (document_id,))
        c.execute("DELETE FROM purge_guards WHERE document_id=?", (document_id,))
        instant = now_utc()
        c.execute(
            "UPDATE documents SET title='',source_sha256=?,rights_note='',languages_json='[]',current_revision=0,state='deleted',retention_until=?,updated_at=?,deleted_at=? WHERE id=?",
            ("deleted:" + document_id, instant, instant, instant, document_id),
        )
        c.execute(
            "UPDATE deletion_receipts SET status='complete',completed_at=?,counts_json=?,error_code=NULL WHERE id=?",
            (instant, json.dumps(counts), row["id"]),
        )
    return True


def sweep_retention(database: Database, settings: Settings) -> int:
    with database.read_conn() as c:
        rows = list(
            c.execute(
                "SELECT id,owner_id FROM documents WHERE retention_until<=? AND state NOT IN ('deleting','deleted')",
                (now_utc(),),
            )
        )
    count = 0
    for doc in rows:
        with database.write_tx() as c:
            result = _request(c, settings, doc["id"], doc["owner_id"], only_expired=True)
            count += result is not None
    return count


def extend_retention(
    database: Database, settings: Settings, document_id: str, owner_id: str, days: int
) -> dict[str, str]:
    if not 1 <= days <= settings.retention_extension_max_days:
        raise Problem(
            422, "invalid_retention", "Choose a retention period within the configured maximum."
        )
    until = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    with database.write_tx() as c:
        doc = check_document(c, document_id, owner_id, "owner")
        if until <= doc["retention_until"]:
            raise Problem(
                422,
                "retention_not_extended",
                "Choose a date later than the current retention date.",
            )
        c.execute(
            "UPDATE documents SET retention_until=?,updated_at=? WHERE id=?",
            (until, now_utc(), document_id),
        )
    return {"retention_until": until}


def schedule_daily_sweep(database: Database, settings: Settings) -> str:
    instant = now_utc()
    with database.write_tx() as c:
        return enqueue(
            c,
            None,
            "retention_sweep",
            {},
            settings.job_max_attempts,
            "retention:" + instant[:10],
            instant,
        )
