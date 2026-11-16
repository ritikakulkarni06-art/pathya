import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.config import Settings
from app.db.connection import Database
from app.db.migrate import migrate
from app.errors import Problem
from app.logging import log_event


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        config.pathya_data_dir.mkdir(parents=True, exist_ok=True)
        assert config.pathya_db_path is not None
        migrate(Database(config.pathya_db_path))
        yield

    application = FastAPI(
        title="Pathya Backend",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.settings = config
    assert config.pathya_db_path is not None
    application.state.database = Database(config.pathya_db_path)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        log_event(
            request_id=request.state.request_id,
            route=getattr(route, "path", "unmatched"),
            status=response.status_code,
            duration_ms=round((time.monotonic() - start) * 1000, 2),
        )
        return response

    def problem_response(status: int, code: str, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            media_type="application/problem+json",
            content={
                "type": "urn:pathya:error:" + code,
                "title": code.replace("_", " ").capitalize(),
                "status": status,
                "detail": detail,
                "code": code,
            },
        )

    @application.exception_handler(Problem)
    async def handle_problem(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc.status, exc.code, exc.detail)

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            422, "invalid_request", "Some fields are invalid. Please check the request format."
        )

    @application.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException) -> JSONResponse:
        return problem_response(
            exc.status_code, "http_error", "The requested resource or method is unavailable."
        )

    @application.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return problem_response(
            500, "internal_error", "The request could not be completed. Please try again."
        )

    @application.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz")
    def ready() -> dict[str, str]:
        import sqlite3

        try:
            config.pathya_data_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(config.pathya_data_dir, os.W_OK):
                raise OSError("unwritable")
            assert config.pathya_db_path is not None
            with sqlite3.connect(config.pathya_db_path) as conn:
                conn.execute("SELECT 1")
            migrate(application.state.database, apply=False)
        except (OSError, sqlite3.Error, ValueError):
            raise Problem(
                503, "not_ready", "Storage is unavailable. Please contact the project maintainer."
            ) from None
        return {"status": "ready"}

    return application
