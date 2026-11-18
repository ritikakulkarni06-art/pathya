from typing import Any

from fastapi import APIRouter, Depends, Request

from app.schemas.answers import QuestionRequest
from app.services.answers import ask, get_answer
from app.services.auth import current_user, require_doc_access
from app.services.limits import rate_limit

router = APIRouter()


@router.post("/questions")
def question(
    payload: QuestionRequest,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    limited: None = Depends(rate_limit("question")),
) -> dict[str, Any]:
    return ask(
        request.app.state.database,
        request.app.state.settings,
        user["id"],
        payload,
        llm=getattr(request.app.state, "llm_client", None),
        embedder=getattr(request.app.state, "embedding_provider", None),
    )


@router.get("/answers/{answer_id}")
def explanation(
    answer_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("reader")),
) -> dict[str, Any]:
    return get_answer(request.app.state.database, answer_id, document["_access_user_id"])
