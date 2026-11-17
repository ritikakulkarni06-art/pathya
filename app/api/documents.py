import hashlib
import io
import json
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db.repos import audit, documents, jobs
from app.errors import Problem
from app.services.auth import current_user, now_utc, require_doc_access
from app.services.storage import FileStore
from app.services.uploads import inspect_upload

router = APIRouter()


def public_document(row: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: row[key]
        for key in (
            "id",
            "title",
            "rights_note",
            "current_revision",
            "state",
            "retention_until",
            "created_at",
            "updated_at",
        )
    }
    result["languages"] = json.loads(row["languages_json"])
    result["counts"] = {"pages": row.get("pages_count", 0), "blocks": row.get("blocks_count", 0)}
    return result


@router.post("/documents", status_code=202)
async def upload_document(
    request: Request,
    file: UploadFile = File(),
    title: str = Form(min_length=1, max_length=200),
    languages: str = Form(default="en,hi", max_length=16),
    rights_note: str | None = Form(default=None, max_length=2000),
    user: dict[str, Any] = Depends(current_user),
) -> JSONResponse:
    settings: Settings = request.app.state.settings
    if not rights_note or not rights_note.strip():
        raise Problem(
            422,
            "rights_note_required",
            "Add a note confirming your permission to use this chapter.",
        )
    if not title.strip():
        raise Problem(422, "title_required", "Give this chapter a short title.")
    selected = [language.strip() for language in languages.split(",")]
    if not selected or set(selected) - {"en", "hi"} or len(selected) != len(set(selected)):
        raise Problem(422, "unsupported_language", "Select English, Hindi or both.")
    store = FileStore(
        settings.pathya_data_dir, request.app.state.database, settings.storage_min_free_bytes
    )
    store.safe_path("tmp").mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    maximum = settings.max_upload_mb * 1024 * 1024
    with tempfile.TemporaryFile(dir=store.safe_path("tmp")) as temporary:
        staged = cast(BinaryIO, temporary)
        while True:
            chunk = await file.read(min(65536, maximum - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum:
                raise Problem(413, "too_large", "This file is too large. Upload a smaller chapter.")
            store._space(len(chunk))
            digest.update(chunk)
            staged.write(chunk)
        inspected = inspect_upload(staged, file.filename, settings)
        source_hash = digest.hexdigest()
        with request.app.state.database.write_tx() as connection:
            existing = documents.by_source(connection, user["id"], source_hash)
            if existing:
                job = jobs.for_document(connection, existing["id"], "extract")
                if existing["state"] in {"deleting", "deleted"}:
                    raise Problem(
                        409,
                        "deletion_in_progress",
                        "This copy is being deleted. Wait for deletion to finish before uploading again.",
                    )
                if job is None:
                    raise Problem(
                        409,
                        "upload_in_progress",
                        "This upload is still being saved. Please retry shortly.",
                    )
                return JSONResponse(
                    status_code=200,
                    content={"document_id": existing["id"], "job_id": job["id"], "duplicate": True},
                )
            document_id = str(uuid4())
            now = now_utc()
            retention = (
                datetime.now(UTC) + timedelta(days=settings.retention_days_after_end)
            ).isoformat()
            documents.create_document(
                connection,
                document_id,
                user["id"],
                title.strip(),
                source_hash,
                rights_note.strip(),
                selected,
                retention,
                now,
            )
        try:
            staged.seek(0)
            store.put_source(document_id, staged, maximum, inspected.mime)
            if inspected.working_image is not None:
                store.put_derived(
                    document_id,
                    "working-image",
                    io.BytesIO(inspected.working_image),
                    max(settings.max_pixels * 4, 1048576),
                    "crop",
                    "image/png",
                )
            with request.app.state.database.write_tx() as connection:
                job_id = jobs.enqueue(
                    connection,
                    document_id,
                    "extract",
                    {"languages": selected, "pages_total": inspected.pages},
                    settings.job_max_attempts,
                    document_id + ":" + source_hash,
                    now,
                )
                documents.set_state(connection, document_id, "queued", now)
                audit.record(
                    connection,
                    user["id"],
                    "upload",
                    document_id,
                    document_id,
                    now,
                    {"kind": inspected.mime},
                )
        except BaseException:
            removed = store.secure_delete_document(document_id)
            with request.app.state.database.write_tx() as connection:
                if not removed.failures:
                    connection.execute("DELETE FROM assets WHERE document_id=?", (document_id,))
                    connection.execute("DELETE FROM documents WHERE id=?", (document_id,))
                else:
                    documents.set_state(connection, document_id, "failed", now_utc())
            raise
    return JSONResponse(status_code=202, content={"document_id": document_id, "job_id": job_id})


@router.get("/documents")
def list_documents(
    request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        rows = documents.accessible(connection, user["id"])
    return {"documents": [public_document(row) for row in rows]}


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        row = documents.with_counts(connection, document_id)
    assert row is not None
    return public_document(row)
