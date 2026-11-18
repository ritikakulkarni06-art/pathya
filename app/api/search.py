from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.services.auth import require_doc_access
from app.services.retrieval.search import search_snapshot

router = APIRouter()


@router.get("/documents/{document_id}/search")
def search_chapter(
    document_id: str,
    request: Request,
    q: str = Query(min_length=1, max_length=2000),
    k: int = Query(default=5, ge=1, le=20),
    block_scope: list[str] | None = Query(default=None, max_length=200),
    neighbors: bool = False,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    return search_snapshot(
        request.app.state.database,
        request.app.state.settings,
        document_id,
        document["_access_user_id"],
        q,
        k,
        block_scope,
        neighbors=neighbors,
        embedder=getattr(request.app.state, "embedding_provider", None),
    )


@router.post("/documents/{document_id}/reindex", status_code=202)
def request_index(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("owner")),
) -> dict[str, str]:
    from app.clock import now_utc
    from app.db.repos.jobs import enqueue
    from app.services.access import check_document

    with request.app.state.database.write_tx() as connection:
        current = check_document(connection, document_id, document["_access_user_id"], "owner")
        job_id = enqueue(
            connection,
            document_id,
            "build_index",
            {"revision": current["current_revision"]},
            request.app.state.settings.job_max_attempts,
            None,
            now_utc(),
        )
    return {"job_id": job_id, "message": "The current eligible chapter text will be indexed."}
