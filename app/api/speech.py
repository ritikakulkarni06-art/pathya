import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response

from app.adapters.speech import provider
from app.api.content import download_asset
from app.clock import now_utc
from app.db.repos import jobs
from app.errors import Problem
from app.schemas.speech import AudioRequest, GlossaryRequest
from app.services.access import check_document
from app.services.auth import current_user, require_doc_access
from app.services.manifests import artifact_current
from app.services.packages import build_package
from app.services.speech import cache_key, delete_glossary, glossary, set_glossary

router = APIRouter()


@router.get("/documents/{document_id}/glossary")
def get_glossary(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return {"terms": glossary(request.app.state.database, document_id, user["id"])}


@router.put("/documents/{document_id}/glossary")
def put_glossary(
    document_id: str,
    payload: GlossaryRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, str]:
    return {
        "id": set_glossary(
            request.app.state.database, document_id, user["id"], payload, request.app.state.settings
        )
    }


@router.delete("/documents/{document_id}/glossary/{term_id}", status_code=204)
def remove_glossary(
    document_id: str,
    term_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> None:
    delete_glossary(
        request.app.state.database, document_id, user["id"], term_id, request.app.state.settings
    )


@router.delete("/documents/{document_id}/glossary", status_code=204)
def remove_glossary_by_query(
    document_id: str,
    request: Request,
    term_id: str = Query(min_length=1, max_length=128),
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> None:
    delete_glossary(
        request.app.state.database, document_id, user["id"], term_id, request.app.state.settings
    )


@router.get("/blocks/{block_id}/audio")
def get_audio(
    block_id: str,
    request: Request,
    voice: str | None = Query(default=None, max_length=64),
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    database = request.app.state.database
    settings = request.app.state.settings
    speaker = provider(settings)
    with database.read_conn() as connection:
        block = connection.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
        if block is None:
            raise Problem(404, "block_not_found", "This passage is unavailable.")
        terms = glossary(database, document["id"], user["id"])
        selected = voice or settings.speech_voice
        key, _ = cache_key(
            block, terms, selected, speaker.engine_version, settings.active_segmenter_version
        )
        # Both private and shared variants are checked; source input hashes must match.
        private_key = hashlib.sha256((key + ":" + user["id"]).encode()).hexdigest()
        candidates = connection.execute(
            "SELECT artifacts.*,audio_manifests.body_json FROM artifacts JOIN audio_manifests ON audio_manifests.artifact_id=artifacts.id WHERE block_id=? AND voice=? AND (scope_user_id IS NULL OR scope_user_id=?) ORDER BY artifacts.created_at DESC",
            (block_id, selected, user["id"]),
        ).fetchall()
        for item in candidates:
            body = json.loads(item["body_json"])
            row_key, _ = cache_key(
                block, terms, selected, item["engine_version"], settings.active_segmenter_version
            )
            if item["scope_user_id"] is not None:
                row_key = hashlib.sha256((row_key + ":" + user["id"]).encode()).hexdigest()
            stored = connection.execute(
                "SELECT cache_key FROM audio_manifests WHERE artifact_id=?", (item["id"],)
            ).fetchone()
            if (
                stored["cache_key"] in {key, private_key}
                and stored["cache_key"] == row_key
                and artifact_current(connection, item)
            ):
                return {
                    **body,
                    "text_sha256": hashlib.sha256(
                        block["text_current"].encode("utf-8")
                    ).hexdigest(),
                    "segmenter": settings.active_segmenter_version,
                }
        fallback = connection.execute(
            "SELECT * FROM artifacts WHERE block_id=? AND kind='audio_block' AND status='failed' AND voice=? AND (scope_user_id IS NULL OR scope_user_id=?) ORDER BY updated_at DESC LIMIT 1",
            (block_id, selected, user["id"]),
        ).fetchone()
        if (
            fallback is not None
            and json.loads(fallback["dependency_revisions_json"]).get(block_id) == block["revision"]
        ):
            return {
                "status": "text_only",
                "reason": fallback["stale_reason"],
                "block_id": block_id,
                "text_available": True,
            }
        if candidates:
            raise Problem(
                409,
                "audio_stale",
                "This audio is outdated. Read the current text while a rebuild is requested.",
            )
    raise Problem(
        404, "audio_pending", "Audio is not ready. Read the text or request an audio build."
    )


@router.post("/blocks/{block_id}/audio", status_code=202)
def request_audio(
    block_id: str,
    payload: AudioRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, str]:
    with request.app.state.database.write_tx() as connection:
        check_document(connection, document["id"], user["id"])
        job_id = jobs.enqueue(
            connection,
            document["id"],
            "build_audio",
            {
                "block_ids": [block_id],
                "user_id": user["id"],
                "voice": payload.voice or request.app.state.settings.speech_voice,
            },
            request.app.state.settings.job_max_attempts,
            None,
            now_utc(),
        )
    return {"job_id": job_id}


@router.get("/artifacts/{artifact_id}")
def artifact_download(
    artifact_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> FileResponse:
    with request.app.state.database.read_conn() as connection:
        item = connection.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if item is None or (
            item["scope_user_id"] is not None and item["scope_user_id"] != user["id"]
        ):
            raise Problem(404, "artifact_not_found", "This artifact is unavailable.")
        if not artifact_current(connection, item):
            raise Problem(
                409,
                "artifact_stale",
                "This output is outdated or unavailable. Use current text while it rebuilds.",
            )
    return download_asset(item["asset_id"], request, document)


@router.post("/documents/{document_id}/packages", status_code=201)
def package(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return build_package(
        request.app.state.database, request.app.state.settings, document_id, user["id"]
    )


@router.get("/documents/{document_id}/packages/{package_id}")
def get_package(
    document_id: str,
    package_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> Response:
    with request.app.state.database.read_conn() as connection:
        item = connection.execute(
            "SELECT packages.*,artifacts.status,artifacts.dependency_revisions_json,artifacts.kind,artifacts.block_id FROM packages JOIN artifacts ON artifacts.id=packages.artifact_id WHERE packages.id=? AND packages.document_id=?",
            (package_id, document_id),
        ).fetchone()
        if item is None:
            raise Problem(404, "package_not_found", "This package is unavailable.")
        if item["revision"] != document["current_revision"] or not artifact_current(
            connection, item
        ):
            raise Problem(
                409,
                "package_stale",
                "This package belongs to older content. Request a current download.",
            )
    return Response(
        item["body_json"],
        media_type="application/json",
        headers={"ETag": '"' + item["sha256"] + '"', "Cache-Control": "private"},
    )
