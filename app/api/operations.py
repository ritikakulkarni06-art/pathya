from typing import Any

from fastapi import APIRouter, Depends, Request

from app.services.auth import require_admin
from app.services.operations import job_statuses, metrics, storage_status

router = APIRouter()


@router.get("/admin/jobs")
def jobs(request: Request, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return {"jobs": job_statuses(request.app.state.database)}


@router.get("/admin/storage")
def storage(request: Request, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return storage_status(request.app.state.database, request.app.state.settings)


@router.get("/admin/metrics")
def counters(request: Request, user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
    return metrics(request.app.state.database)
