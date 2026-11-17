import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response

from app.db.repos import jobs
from app.errors import Problem
from app.schemas.corrections import CorrectionRequest
from app.services.access import check_document
from app.services.auth import current_user, now_utc, require_doc_access
from app.services.manifests import artifact_current
from app.services.revisions import correct_block
from app.services.storage import FileStore

router = APIRouter()


def public_block(row: dict[str, Any]) -> dict[str, Any]:
    body = {
        key: row[key]
        for key in (
            "id",
            "page_id",
            "type",
            "parent_id",
            "order_key",
            "text_current",
            "lang",
            "revision",
            "status",
        )
    }
    for name in ("bbox", "confidence", "provenance", "successor_ids", "metadata"):
        body[name] = json.loads(row[name + "_json"])
    body["critical_flag"] = bool(row["critical_flag"])
    body["historical"] = bool(body["successor_ids"])
    body["origin"] = "source_text"
    return body


@router.get("/documents/{document_id}/content")
def chapter_content(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, document["_access_user_id"])
        rows = connection.execute(
            "SELECT blocks.* FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(successor_ids_json)=0 ORDER BY pages.pdf_index_0,order_key,blocks.id",
            (document_id,),
        ).fetchall()
    return {
        "document_id": document_id,
        "revision": document["current_revision"],
        "blocks": [public_block(row) for row in rows],
    }


@router.get("/blocks/{block_id}")
def get_block(
    block_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document["id"], document["_access_user_id"])
        row = connection.execute(
            "SELECT * FROM blocks WHERE id=? AND document_id=?", (block_id, document["id"])
        ).fetchone()
    if row is None:
        raise Problem(404, "block_not_found", "This passage is unavailable.")
    return {**public_block(row), "document_revision": document["current_revision"]}


@router.patch("/blocks/{block_id}")
def patch_block(
    block_id: str,
    payload: CorrectionRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reviewer")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return correct_block(
        request.app.state.database, request.app.state.settings, block_id, user["id"], payload
    )


@router.get("/documents/{document_id}/manifest")
def manifest(
    document_id: str,
    request: Request,
    revision: int | None = Query(default=None, ge=1),
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> Response:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, document["_access_user_id"])
        selected = revision or document["current_revision"]
        row = connection.execute(
            "SELECT * FROM manifests WHERE document_id=? AND revision=? ORDER BY build_seq DESC LIMIT 1",
            (document_id, selected),
        ).fetchone()
    if row is None:
        raise Problem(
            409,
            "manifest_pending",
            "The chapter manifest is being prepared. Its text remains available.",
        )
    etag = '"' + row["sha256"] + '"'
    if request.headers.get("if-none-match") in {etag, "*"}:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private"})
    return Response(
        row["body_json"],
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": "private",
            "X-Build-Sequence": str(row["build_seq"]),
        },
    )


@router.get("/documents/{document_id}/review-queue")
def review_queue(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reviewer")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, document["_access_user_id"], "reviewer")
        rows = connection.execute(
            "SELECT blocks.*,pages.printed_label,pages.pdf_index_0 FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(successor_ids_json)=0 AND (critical_flag=1 OR status='needs_review') ORDER BY pages.pdf_index_0,order_key",
            (document_id,),
        ).fetchall()
    return {
        "blocks": [
            {
                **public_block(row),
                "printed_label": row["printed_label"],
                "reason": "A critical extraction symbol needs review."
                if row["critical_flag"]
                else "The extracted passage needs review.",
                "crop_reference": None,
            }
            for row in rows
        ]
    }


@router.get("/assets/{asset_id}")
def download_asset(
    asset_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> FileResponse:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document["id"], document["_access_user_id"])
        asset = connection.execute(
            "SELECT * FROM assets WHERE id=? AND document_id=? AND deleted_at IS NULL",
            (asset_id, document["id"]),
        ).fetchone()
        if asset is None:
            raise Problem(404, "asset_not_found", "This file is unavailable.")
        if asset["kind"] == "audio":
            linked = connection.execute(
                "SELECT * FROM artifacts WHERE asset_id=?", (asset_id,)
            ).fetchall()
            if not any(artifact_current(connection, item) for item in linked):
                raise Problem(
                    409,
                    "audio_stale",
                    "This audio is outdated or unavailable. Read the current text while it rebuilds.",
                )
    store = FileStore(
        request.app.state.settings.pathya_data_dir, request.app.state.database, min_free_bytes=0
    )
    path = store.safe_path(*asset["private_path"].split("/"))
    if not path.is_file():
        raise Problem(404, "asset_not_found", "This file is missing. Please request a rebuild.")
    return FileResponse(
        path,
        media_type=asset["mime"],
        headers={
            "ETag": '"' + asset["sha256"] + '"',
            "Cache-Control": "private",
            "Content-Length": str(asset["bytes"]),
        },
    )


@router.post("/documents/{document_id}/reextract", status_code=202)
def reextract(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reviewer")),
) -> dict[str, str]:
    with request.app.state.database.write_tx() as connection:
        document = check_document(connection, document_id, document["_access_user_id"], "reviewer")
        count = connection.execute(
            "SELECT count(*) AS n FROM pages WHERE document_id=?", (document_id,)
        ).fetchone()["n"]
        if not count:
            raise Problem(
                409,
                "content_pending",
                "Wait for initial extraction before requesting another candidate.",
            )
        job_id = jobs.enqueue(
            connection,
            document_id,
            "extract",
            {
                "mode": "reextract",
                "pages_total": count,
                "languages": json.loads(document["languages_json"]),
            },
            request.app.state.settings.job_max_attempts,
            None,
            now_utc(),
        )
    return {
        "job_id": job_id,
        "message": "A separate candidate will be prepared. Accepted corrections remain unchanged.",
    }


@router.get("/documents/{document_id}/candidates/{candidate_id}")
def get_candidate(
    document_id: str,
    candidate_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reviewer")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, document["_access_user_id"], "reviewer")
        row = connection.execute(
            "SELECT * FROM reextraction_candidates WHERE id=? AND document_id=?",
            (candidate_id, document_id),
        ).fetchone()
    if row is None:
        raise Problem(404, "candidate_not_found", "This extraction candidate is unavailable.")
    return {
        "id": candidate_id,
        "base_revision": row["base_revision"],
        "proposed_revision": row["proposed_revision"],
        "state": "stale" if row["base_revision"] != document["current_revision"] else row["state"],
        "body": json.loads(row["body_json"]),
    }
