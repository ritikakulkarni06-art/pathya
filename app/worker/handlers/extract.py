import json
from typing import Any

from app.adapters.extraction import get_extraction_adapter
from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.db.repos import jobs
from app.errors import Problem
from app.schemas.content import ExtractionResult
from app.services.ingest import import_extraction
from app.services.jobs import LeaseLost, finish, progress
from app.services.manifests import publish_manifest
from app.services.reconcile import propose_candidate
from app.services.storage import FileStore


def handle(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    document_id = job["document_id"]
    owner = job["lease_owner"]
    payload = json.loads(job["payload_json"])
    total = int(payload["pages_total"])
    if total < 1 or total > settings.max_pages:
        raise Problem(
            422, "invalid_page_count", "This extraction request has an invalid page count."
        )
    with database.write_tx() as connection:
        owned = jobs.get_job(connection, job["id"])
        if (
            owned is None
            or owned["lease_owner"] != owner
            or owned["state"] not in {"validating", "extracting", "building"}
            or owned["lease_expires_at"] <= now_utc()
        ):
            raise LeaseLost()
        source = connection.execute(
            "SELECT * FROM assets WHERE document_id=? AND kind='source' AND deleted_at IS NULL",
            (document_id,),
        ).fetchone()
        connection.execute(
            "UPDATE documents SET state='processing',updated_at=? WHERE id=? AND current_revision=0 AND state NOT IN ('deleting','deleted')",
            (now_utc(), document_id),
        )
    if source is None:
        raise Problem(
            404, "source_unavailable", "The source file is missing. Upload the chapter again."
        )
    store = FileStore(settings.pathya_data_dir, database, settings.storage_min_free_bytes)
    source_path = store.safe_path(*source["private_path"].split("/"))
    adapter = get_extraction_adapter(settings)
    collected: dict[str, Any] = {
        "schema_version": "1.0.0",
        "pages": [],
        "blocks": [],
        "edges": [],
        "quality_flags": [],
        "parser_versions": {},
    }
    flags = set()
    for index in range(total):
        progress(
            database, job["id"], owner, "extracting", total, index, "Extracting the next page."
        )

        def report(done: int, local_total: int, page_index: int = index) -> None:
            progress(
                database,
                job["id"],
                owner,
                "extracting",
                total,
                page_index,
                "Processing a page. Text will remain available after publication.",
            )

        result = adapter.extract(source_path, payload["languages"], [index], report)
        if {page.pdf_index_0 for page in result.pages} != {index}:
            raise Problem(
                422,
                "invalid_page_range",
                "The extraction adapter returned an unexpected page range.",
            )
        for key in ("pages", "blocks", "edges"):
            collected[key].extend(result.model_dump(mode="json")[key])
        flags.update(result.quality_flags)
        collected["parser_versions"].update(result.parser_versions)
        progress(
            database, job["id"], owner, "extracting", total, index + 1, "Page extraction completed."
        )
    collected["quality_flags"] = sorted(flags)
    validated = ExtractionResult.model_validate(collected)
    progress(database, job["id"], owner, "building", total, total, "Saving the extracted chapter.")
    if payload.get("mode") == "reextract":
        candidate_id = propose_candidate(database, document_id, validated, lease=(job["id"], owner))
        with database.write_tx() as connection:
            connection.execute(
                "UPDATE jobs SET progress_json=? WHERE id=? AND lease_owner=?",
                (
                    json.dumps(
                        {"candidate_id": candidate_id, "pages_total": total, "pages_done": total}
                    ),
                    job["id"],
                    owner,
                ),
            )
        finish(
            database,
            job["id"],
            owner,
            "review_required",
            "A separate extraction candidate is ready for reconciliation; accepted corrections were preserved.",
        )
        return
    import_extraction(database, document_id, validated, lease=(job["id"], owner))
    with database.read_conn() as connection:
        current = connection.execute(
            "SELECT current_revision FROM documents WHERE id=?", (document_id,)
        ).fetchone()
    if current is not None and current["current_revision"] == 1:
        publish_manifest(
            database, settings.pathya_data_dir, document_id, 1, lease=(job["id"], owner)
        )
    needs_review = any(
        block.critical_flag or block.status == "needs_review" for block in validated.blocks
    )
    # Eligible passages remain searchable while flagged passages await review.
    with database.write_tx() as connection:
        owned = jobs.get_job(connection, job["id"])
        if (
            owned is None
            or owned["lease_owner"] != owner
            or owned["state"] != "building"
            or owned["lease_expires_at"] <= now_utc()
        ):
            raise LeaseLost()
        for kind in ("build_index",) if needs_review else ("build_audio", "build_index"):
            jobs.enqueue(
                connection,
                document_id,
                kind,
                {"revision": 1},
                settings.job_max_attempts,
                document_id + ":1:" + kind,
                now_utc(),
            )
    finish(
        database,
        job["id"],
        owner,
        "review_required" if needs_review else "ready",
        "Extraction completed. Review flagged passages before using them as evidence."
        if needs_review
        else "Extraction completed; derivative work is queued.",
    )
