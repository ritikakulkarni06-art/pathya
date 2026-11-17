import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response

from app.config import Settings
from app.db.repos import audit, grants, sessions, users
from app.errors import Problem
from app.schemas.auth import Credentials, GrantRequest, UserView
from app.services.access import check_document
from app.services.auth import (
    CSRF_COOKIE,
    DUMMY_HASH,
    PASSWORDS,
    SESSION_COOKIE,
    csrf_token,
    current_user,
    now_utc,
    require_doc_access,
    token_digest,
    verify_password,
)

router = APIRouter()


def session_mode(request: Request) -> None:
    if request.app.state.settings.auth_mode != "session":
        raise Problem(
            409, "session_mode_required", "Account sign-in is disabled in local demo mode."
        )
    origin = request.headers.get("origin")
    allowed = request.app.state.settings.cors_origins
    if origin and origin not in allowed and origin != str(request.base_url).rstrip("/"):
        raise Problem(
            403, "untrusted_origin", "Open this service from an approved application address."
        )
    settings: Settings = request.app.state.settings
    if request.url.scheme != "https" and settings.pathya_env == "prod":
        raise Problem(400, "https_required", "Use a secure HTTPS connection to sign in.")


def limit_login(request: Request, email: str) -> None:
    request.app.state.login_limiter.check(
        request.client.host if request.client else "unknown", email
    )


@router.post("/auth/register", status_code=201, response_model=UserView)
def register(payload: Credentials, request: Request) -> dict[str, Any]:
    session_mode(request)
    limit_login(request, payload.email)
    user_id = str(uuid4())
    password_hash = PASSWORDS.hash(payload.password)
    with request.app.state.database.write_tx() as connection:
        try:
            users.create(connection, user_id, payload.email, password_hash, now_utc())
        except sqlite3.IntegrityError:
            raise Problem(
                409, "account_unavailable", "This account cannot be registered. Try signing in."
            ) from None
    return {"id": user_id, "email": payload.email, "role": "user"}


@router.post("/auth/login", response_model=UserView)
def login(payload: Credentials, request: Request, response: Response) -> dict[str, Any]:
    session_mode(request)
    limit_login(request, payload.email)
    with request.app.state.database.read_conn() as connection:
        user = users.by_email(connection, payload.email)
    candidate = user["password_hash"] if user and user["password_hash"] else DUMMY_HASH
    valid = verify_password(candidate, payload.password)
    if user is None or not valid:
        raise Problem(401, "invalid_credentials", "The email or password is incorrect.")
    token = secrets.token_urlsafe(32)
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    with request.app.state.database.write_tx() as connection:
        sessions.create(
            connection,
            str(uuid4()),
            user["id"],
            token_digest(token),
            now.isoformat(),
            (now + timedelta(seconds=settings.session_ttl_seconds)).isoformat(),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_seconds,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token(token, settings),
        max_age=settings.session_ttl_seconds,
        secure=True,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return {key: user[key] for key in ("id", "email", "role")}


@router.get("/auth/me", response_model=UserView)
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {key: user[key] for key in ("id", "email", "role")}


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request, response: Response, user: dict[str, Any] = Depends(current_user)
) -> None:
    if request.app.state.settings.auth_mode == "session":
        with request.app.state.database.write_tx() as connection:
            sessions.revoke(
                connection, token_digest(request.cookies.get(SESSION_COOKIE, "")), now_utc()
            )
    response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, secure=True, samesite="lax")


@router.post("/documents/{document_id}/grants", status_code=204)
def grant(
    document_id: str,
    payload: GrantRequest,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("owner")),
    user: dict[str, Any] = Depends(current_user),
) -> None:
    with request.app.state.database.write_tx() as connection:
        check_document(connection, document_id, user["id"], "owner")
        if users.get_user(connection, payload.user_id) is None:
            raise Problem(404, "user_not_found", "The requested account is unavailable.")
        grants.put(connection, document_id, payload.user_id, payload.role, user["id"], now_utc())
        audit.record(
            connection,
            user["id"],
            "grant",
            document_id,
            payload.user_id,
            now_utc(),
            {"role": payload.role},
        )


@router.delete("/documents/{document_id}/grants/{user_id}", status_code=204)
def revoke_grant(
    document_id: str,
    user_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("owner")),
    user: dict[str, Any] = Depends(current_user),
) -> None:
    with request.app.state.database.write_tx() as connection:
        check_document(connection, document_id, user["id"], "owner")
        grants.remove(connection, document_id, user_id)
        audit.record(connection, user["id"], "revoke_grant", document_id, user_id, now_utc(), {})
