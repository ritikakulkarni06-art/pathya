from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.services.auth import current_user, require_doc_access
from app.services.deletions import extend_retention, get_receipt, request_delete, retry_delete

router = APIRouter()


class RetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    days: int = Field(ge=1, le=36500)


@router.delete("/documents/{document_id}", status_code=202)
def delete_document(
    document_id: str, request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    return request_delete(
        request.app.state.database, request.app.state.settings, document_id, user["id"]
    )


@router.get("/deletions/{receipt_id}")
def deletion_status(
    receipt_id: str, request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    return get_receipt(request.app.state.database, receipt_id, user["id"])


@router.post("/deletions/{receipt_id}/retry", status_code=202)
def retry(
    receipt_id: str, request: Request, user: dict[str, Any] = Depends(current_user)
) -> dict[str, Any]:
    return retry_delete(
        request.app.state.database, request.app.state.settings, receipt_id, user["id"]
    )


@router.patch("/documents/{document_id}/retention")
def retention(
    document_id: str,
    payload: RetentionRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("owner")),
) -> dict[str, str]:
    return extend_retention(
        request.app.state.database,
        request.app.state.settings,
        document_id,
        document["_access_user_id"],
        payload.days,
    )
