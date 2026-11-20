from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.schemas.answers import QuestionRequest
from app.services.answers import ask, get_answer
from app.services.auth import current_user, require_doc_access
from app.services.limits import question_usage, rate_limit

router = APIRouter()


@router.get("/usage")
def usage(request: Request, user: dict[str, Any] = Depends(current_user)) -> dict[str, int]:
    with request.app.state.database.read_conn() as connection:
        return question_usage(
            connection,
            user["id"],
            request.app.state.settings.daily_question_limit,
            datetime.now(UTC),
        )


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
