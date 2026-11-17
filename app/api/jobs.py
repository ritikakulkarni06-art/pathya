import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.db.repos.jobs import get_job
from app.errors import Problem
from app.services.auth import require_doc_access
from app.services.jobs import cancel

router = APIRouter()


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str, request: Request, document: dict[str, Any] = Depends(require_doc_access("reader"))
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        job = get_job(connection, job_id)
    if job is None:
        raise Problem(404, "job_not_found", "This processing job is unavailable.")
    progress = json.loads(job["progress_json"])
    return {
        "id": job_id,
        "document_id": job["document_id"],
        "state": job["state"],
        "attempts": job["attempts"],
        "max_attempts": job["max_attempts"],
        "last_error_code": job["error_code"],
        "reason": progress.get("message") or job["error_message"] or "Waiting for a worker.",
        "progress": progress,
    }


@router.post("/jobs/{job_id}/cancel", status_code=204)
def cancel_job(
    job_id: str, request: Request, document: dict[str, Any] = Depends(require_doc_access("owner"))
) -> None:
    cancel(request.app.state.database, job_id)
