from typing import Any

from fastapi import APIRouter, Depends, Request

from app.services.auth import require_admin
from app.services.costs import usage_summary

router = APIRouter()


@router.get("/admin/usage")
def usage(request: Request, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return usage_summary(request.app.state.database)
