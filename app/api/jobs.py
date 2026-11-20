import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.clock import now_utc
from app.db.repos.extraction import receipt
from app.db.repos.jobs import enqueue, get_job
from app.errors import Problem
from app.services.access import check_document
from app.services.auth import current_user, require_doc_access
from app.services.jobs import cancel

router = APIRouter()


def _check_job(job: dict[str, Any] | None, user_id: str) -> dict[str, Any]:
    if job is None or json.loads(job["payload_json"]).get("user_id") not in (None, user_id):
        raise Problem(404, "job_not_found", "This processing job is unavailable.")
    return job


def _job_view(job: dict[str, Any], title: str) -> dict[str, Any]:
    progress = json.loads(job["progress_json"])
    return {
        "id": job["id"],
        "document_id": job["document_id"],
        "title": title,
        "created_at": job["created_at"],
        "kind": job["kind"],
        "state": job["state"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "last_error_code": job["error_code"],
        "reason": (job["error_message"] if job["state"] in {"failed", "cancelled"} else None)
        or progress.get("message")
        or job["error_message"]
        or "Waiting for a worker.",
        "pages_total": progress.get("pages_total", 0),
        "pages_done": progress.get("pages_done", 0),
        **(
            {"failed_at": progress["failed_at"]}
            if job["state"] == "failed" and "failed_at" in progress
            else {}
        ),
        "progress": progress,
    }


@router.get("/jobs")
def list_jobs(
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
) -> list[dict[str, Any]]:
    with request.app.state.database.read_conn() as connection:
        rows = connection.execute(
            """
            SELECT j.*, d.title FROM jobs j JOIN documents d ON d.id=j.document_id
            WHERE d.state NOT IN ('deleting','deleted') AND j.kind<>'delete'
              AND (d.owner_id=? OR EXISTS (
                SELECT 1 FROM document_grants g WHERE g.document_id=d.id AND g.user_id=?
              ))
              AND (json_extract(j.payload_json,'$.user_id') IS NULL
                   OR json_extract(j.payload_json,'$.user_id')=?)
            ORDER BY j.created_at DESC,j.id DESC LIMIT ? OFFSET ?
            """,
            (user["id"], user["id"], user["id"], limit, offset),
        ).fetchall()
    return [_job_view(row, row["title"]) for row in rows]


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str, request: Request, document: dict[str, Any] = Depends(require_doc_access("reader"))
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        current = check_document(connection, document["id"], document["_access_user_id"])
        job = _check_job(get_job(connection, job_id), document["_access_user_id"])
    return _job_view(job, current["title"])


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(
    job_id: str, request: Request, document: dict[str, Any] = Depends(require_doc_access("reader"))
) -> dict[str, Any]:
    user_id = document["_access_user_id"]
    with request.app.state.database.write_tx() as connection:
        job = _check_job(get_job(connection, job_id), user_id)
        payload = json.loads(job["payload_json"])
        current = check_document(
            connection, document["id"], user_id, "reader" if payload.get("user_id") else "owner"
        )
        if job["state"] != "failed" or job["kind"] not in {
            "extract",
            "build_audio",
            "build_index",
            "rebuild",
        }:
            raise Problem(409, "job_not_retryable", "Only a failed processing job can be retried.")
        retry_key = "manual-retry:" + job_id
        existing = connection.execute(
            "SELECT * FROM jobs WHERE idempotency_key=?", (retry_key,)
        ).fetchone()
        if existing is not None:
            return _job_view(existing, current["title"])
        revision = current["current_revision"]
        initial_extract = job["kind"] == "extract" and payload.get("mode") != "reextract"
        partial = receipt(connection, current["id"]) if initial_extract and revision == 1 else None
        stale = (
            payload.get("revision", revision) != revision
            or initial_extract
            and revision != 0
            and (partial is None or partial["p1_source_json"] is None)
        )
        if stale:
            raise Problem(409, "job_revision_stale", "This job is for an older chapter revision.")
        new_id = enqueue(
            connection,
            current["id"],
            job["kind"],
            payload,
            job["max_attempts"],
            retry_key,
            now_utc(),
        )
        replacement = get_job(connection, new_id)
        assert replacement is not None
        if replacement["state"] == "queued" and job["kind"] == "extract" and revision == 0:
            connection.execute(
                "UPDATE documents SET state='queued',updated_at=? WHERE id=?",
                (now_utc(), current["id"]),
            )
    return _job_view(replacement, current["title"])


@router.post("/jobs/{job_id}/cancel", status_code=204)
def cancel_job(
    job_id: str, request: Request, document: dict[str, Any] = Depends(require_doc_access("owner"))
) -> None:
    cancel(request.app.state.database, job_id, user_id=document["_access_user_id"])
