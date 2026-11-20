import hashlib
import io
import json
import math
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from PIL import Image

from app.db.repos import jobs
from app.errors import Problem
from app.schemas.corrections import CorrectionRequest
from app.services.access import check_document
from app.services.auth import current_user, now_utc, require_doc_access
from app.services.limits import rate_limit
from app.services.manifests import artifact_current
from app.services.p1_content import canonical_content
from app.services.page_images import parse_bbox, render_page
from app.services.revisions import correct_block
from app.services.sentences import sentence_ranges
from app.services.storage import FileStore

router = APIRouter()


def public_block(row: dict[str, Any], *, include_sentences: bool = False) -> dict[str, Any]:
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
    body["synthetic"] = str(body["provenance"].get("parser", "")).startswith("synthetic")
    if include_sentences and row["type"] in {"heading", "paragraph", "list_item"}:
        body["sentences"] = [
            {"start": start, "end": end} for start, end in sentence_ranges(row["text_current"])
        ]
    return body


@router.get("/documents/{document_id}/content")
def chapter_content(
    document_id: str,
    request: Request,
    response: Response,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, document["_access_user_id"])
        rows = connection.execute(
            "SELECT blocks.* FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(successor_ids_json)=0 ORDER BY pages.pdf_index_0,order_key,blocks.id",
            (document_id,),
        ).fetchall()
        canonical = canonical_content(connection, document_id, rows)
    if canonical is not None:
        response.headers["X-Document-Revision"] = str(document["current_revision"])
        return canonical
    return {
        "document_id": document_id,
        "revision": document["current_revision"],
        "blocks": [
            public_block(row, include_sentences=request.app.state.settings.segmenter == "pathya")
            for row in rows
        ],
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
    return {
        **public_block(row, include_sentences=request.app.state.settings.segmenter == "pathya"),
        "document_revision": document["current_revision"],
    }


@router.patch("/blocks/{block_id}")
def patch_block(
    block_id: str,
    payload: CorrectionRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reviewer")),
    user: dict[str, Any] = Depends(current_user),
    limited: None = Depends(rate_limit("correction")),
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
            "SELECT blocks.*,pages.printed_label,pages.pdf_index_0,pages.rotation FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(successor_ids_json)=0 AND (critical_flag=1 OR status='needs_review') ORDER BY pages.pdf_index_0,order_key",
            (document_id,),
        ).fetchall()
        has_image = (
            connection.execute(
                "SELECT 1 FROM assets WHERE document_id=? AND kind='crop' AND deleted_at IS NULL AND private_path LIKE '%/working-image/%'",
                (document_id,),
            ).fetchone()
            is not None
        )
    return {
        "blocks": [
            {
                **public_block(row),
                "printed_label": row["printed_label"],
                "reason": "A critical extraction symbol needs review."
                if row["critical_flag"]
                else "The extracted passage needs review.",
                "crop_reference": f"/blocks/{row['id']}/crop"
                if has_image and row["pdf_index_0"] == 0 and row["rotation"] == 0
                else None,
            }
            for row in rows
        ]
    }


@router.get("/documents/{document_id}/revisions")
def correction_history(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=2_147_483_647),
) -> list[dict[str, Any]]:
    user_id = document["_access_user_id"]
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        check_document(connection, document_id, user_id)
        rows = connection.execute(
            """
            SELECT c.*, old.text AS before_text, new.text AS after_text
            FROM corrections c
            LEFT JOIN block_versions old ON old.block_id=c.block_id AND old.revision=c.base_revision
            LEFT JOIN block_versions new ON new.block_id=c.block_id AND new.document_revision=c.accepted_revision
            WHERE c.document_id=? AND c.state='accepted'
            ORDER BY c.accepted_revision DESC,c.id DESC LIMIT ? OFFSET ?
            """,
            (document_id, limit, offset),
        ).fetchall()
    return [
        {
            "revision": row["accepted_revision"],
            "block_id": row["block_id"],
            "at": row["created_at"],
            "by": "You" if row["author_id"] == user_id else "Reviewer",
            "reason": row["reason"],
            "before": row["before_text"],
            "after": row["after_text"],
            "changes": _correction_changes(json.loads(row["operations_json"])),
        }
        for row in rows
    ]


def _correction_changes(operations: list[dict[str, Any]]) -> list[str]:
    labels = {
        "set_type": "Changed the passage type.",
        "reorder": "Changed the reading order.",
        "split": "Split the passage.",
        "merge": "Merged passages.",
        "mark_reviewed": "Marked the passage reviewed.",
        "set_alt_text": "Updated the image description.",
        "set_mathml": "Updated the equation and its spoken description.",
        "set_table_headers": "Updated the table headers.",
    }
    changes = []
    for operation in operations:
        kind = operation["op"]
        if kind == "set_language":
            language = "Hindi" if operation["lang"] == "hi" else "English"
            changes.append(f"Changed the language to {language}.")
        elif kind in labels:
            changes.append(labels[kind])
    return changes


def _preview_info(
    connection: Any, document_id: str, page: dict[str, Any], *, pdf_preview: bool = False
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT id,kind,mime,private_path FROM assets
        WHERE document_id=? AND deleted_at IS NULL
          AND (kind='source' OR (kind='crop' AND private_path LIKE '%/working-image/%'))
        """,
        (document_id,),
    ).fetchall()
    source = next((item for item in rows if item["kind"] == "source"), None)
    image = next((item for item in rows if item["kind"] == "crop"), None)
    number = page["pdf_index_0"] + 1
    image_url = f"/assets/{image['id']}" if image and number == 1 else None
    if pdf_preview and source and source["mime"] == "application/pdf":
        image_url = f"/documents/{document_id}/pages/{page['pdf_index_0']}/image"
    return {
        "page_id": page["id"],
        "page_index": page["pdf_index_0"],
        "image_url": image_url,
        "source_url": (
            f"/assets/{source['id']}"
            + (f"#page={number}" if source["mime"] == "application/pdf" else "")
            if source
            else None
        ),
        "image": image if number == 1 else None,
    }


@router.get("/documents/{document_id}/pages/{page_id}/preview")
def page_preview(
    document_id: str,
    page_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        check_document(connection, document_id, document["_access_user_id"])
        page = connection.execute(
            "SELECT * FROM pages WHERE id=? AND document_id=?", (page_id, document_id)
        ).fetchone()
        if page is None:
            raise Problem(404, "page_not_found", "This source page is unavailable.")
        preview = _preview_info(
            connection,
            document_id,
            page,
            pdf_preview=request.app.state.settings.pdf_preview_enabled,
        )
    preview.pop("image")
    return preview


@router.get("/documents/{document_id}/pages/{page_index}/image", response_class=Response)
def page_image(
    document_id: str,
    page_index: int,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
    bbox: str | None = Query(default=None, max_length=128),
) -> Response:
    box = parse_bbox(bbox)
    database = request.app.state.database
    settings = request.app.state.settings
    user_id = document["_access_user_id"]
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        check_document(connection, document_id, user_id)
        page = connection.execute(
            "SELECT id FROM pages WHERE document_id=? AND pdf_index_0=?", (document_id, page_index)
        ).fetchone()
        if page is None:
            raise Problem(404, "page_not_found", "This source page is unavailable.")
        asset = connection.execute(
            """
            SELECT mime,private_path FROM assets WHERE document_id=? AND deleted_at IS NULL
            AND ((kind='source' AND mime='application/pdf')
                OR (kind='crop' AND mime='image/png' AND ?=0 AND private_path LIKE '%/working-image/%'))
            ORDER BY kind LIMIT 1
            """,
            (document_id, page_index),
        ).fetchone()
    if asset is None:
        raise Problem(
            404,
            "page_image_unavailable",
            "This source image is unavailable. Open the source page or read the text.",
        )
    store = FileStore(settings.pathya_data_dir, database, min_free_bytes=0)
    path = store.safe_path(*asset["private_path"].split("/"))
    data = render_page(path, asset["mime"], page_index, box, settings)
    with database.read_conn() as connection:
        check_document(connection, document_id, user_id)
    tag = '"' + hashlib.sha256(data).hexdigest() + '"'
    headers = {"ETag": tag, "Cache-Control": "private, no-cache"}
    validators = request.headers.get("If-None-Match", "").split(",")
    if any(value.strip().removeprefix("W/") in {tag, "*"} for value in validators):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="image/png", headers=headers)


@router.get("/blocks/{block_id}/crop", response_class=Response)
def block_crop(
    block_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> Response:
    with request.app.state.database.read_conn() as connection:
        connection.execute("BEGIN")
        check_document(connection, document["id"], document["_access_user_id"])
        row = connection.execute(
            """
            SELECT p.*,b.bbox_json,EXISTS(
                SELECT 1 FROM extraction_imports i
                WHERE i.document_id=p.document_id AND i.p1_source_json IS NOT NULL
            ) AS p1 FROM blocks b JOIN pages p ON p.id=b.page_id
            WHERE b.id=? AND b.document_id=? AND json_array_length(b.successor_ids_json)=0
            """,
            (block_id, document["id"]),
        ).fetchone()
        page = None if row is None else _preview_info(connection, document["id"], row)["image"]
    if (
        row is None
        or page is None
        or row["rotation"] != 0
        or row["p1"]
        and json.loads(row["transform_json"]) != [row["width"], 0, 0, row["height"], 0, 0]
    ):
        raise Problem(
            404,
            "crop_unavailable",
            "This crop is unavailable. Open the source page or read the text.",
        )
    settings = request.app.state.settings
    store = FileStore(settings.pathya_data_dir, request.app.state.database, min_free_bytes=0)
    try:
        with Image.open(store.safe_path(*page["private_path"].split("/"))) as image:
            if image.size != (row["width"], row["height"]):
                raise Problem(
                    404,
                    "crop_unavailable",
                    "This crop is unavailable. Open the source page or read the text.",
                )
            left, top, right, bottom = json.loads(row["bbox_json"])
            cropped = image.crop(
                (
                    math.floor(left * image.width),
                    math.floor(top * image.height),
                    math.ceil(right * image.width),
                    math.ceil(bottom * image.height),
                )
            )
            cropped.thumbnail((1600, 1600))
            output = io.BytesIO()
            cropped.save(output, format="PNG")
    except (OSError, ValueError):
        raise Problem(
            404,
            "crop_unavailable",
            "This crop is unavailable. Open the source page or read the text.",
        ) from None
    return Response(
        output.getvalue(), media_type="image/png", headers={"Cache-Control": "private, no-store"}
    )


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
        if asset["kind"] in {"audio", "package"}:
            linked = connection.execute(
                "SELECT * FROM artifacts WHERE asset_id=? OR id IN (SELECT artifact_id FROM artifact_clips WHERE asset_id=?)",
                (asset_id, asset_id),
            ).fetchall()
            allowed = [
                item
                for item in linked
                if item["scope_user_id"] is None
                or item["scope_user_id"] == document["_access_user_id"]
            ]
            if not allowed:
                raise Problem(404, "asset_not_found", "This file is unavailable.")
            if not any(artifact_current(connection, item) for item in allowed):
                raise Problem(
                    409,
                    "package_stale" if asset["kind"] == "package" else "audio_stale",
                    "This output is outdated. Request a current version or continue reading the text.",
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
