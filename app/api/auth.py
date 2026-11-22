import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response

from app.config import Settings
from app.db.repos import audit, grants, sessions, users
from app.errors import Problem
from app.schemas.auth import (
    Credentials,
    GrantList,
    GrantRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserView,
)
from app.services import mail
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


RESET_SUBJECT = "Reset your Pathya password"


@router.post("/auth/password-reset", status_code=204)
def request_password_reset(payload: PasswordResetRequest, request: Request) -> None:
    """Always 204, so the answer never reveals whether an account exists."""
    session_mode(request)
    limit_login(request, payload.email)
    settings: Settings = request.app.state.settings
    with request.app.state.database.write_tx() as connection:
        user = users.by_email(connection, payload.email)
        if user is None or not user["password_hash"]:
            return
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        connection.execute(
            "UPDATE password_resets SET used_at=? WHERE user_id=? AND used_at IS NULL",
            (now.isoformat(), user["id"]),
        )
        connection.execute(
            "INSERT INTO password_resets(id,user_id,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)",
            (
                str(uuid4()),
                user["id"],
                token_digest(token),
                now.isoformat(),
                (now + timedelta(seconds=settings.password_reset_ttl_seconds)).isoformat(),
            ),
        )
        audit.record(
            connection, user["id"], "password_reset_requested", None, user["id"], now_utc(), {}
        )
    base = (settings.public_app_url or str(request.base_url)).rstrip("/")
    minutes = settings.password_reset_ttl_seconds // 60
    mail.send(
        settings,
        payload.email,
        RESET_SUBJECT,
        f"Someone asked to reset the password for this Pathya account.\n\n"
        f"Open this link within {minutes} minutes to choose a new password:\n"
        f"{base}/reset-password?token={token}\n\n"
        "If it was not you, ignore this message; your password stays the same.\n",
    )


@router.post("/auth/password-reset/confirm", status_code=204)
def confirm_password_reset(payload: PasswordResetConfirm, request: Request) -> None:
    """Sets the new password and signs the account out everywhere. A link works once."""
    session_mode(request)
    now = datetime.now(UTC)
    with request.app.state.database.write_tx() as connection:
        row = connection.execute(
            "SELECT * FROM password_resets WHERE token_hash=? AND used_at IS NULL",
            (token_digest(payload.token),),
        ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= now:
            raise Problem(
                400,
                "reset_link_invalid",
                "This reset link has expired or was already used. Ask for a new one.",
            )
        connection.execute(
            "UPDATE password_resets SET used_at=? WHERE id=?", (now.isoformat(), row["id"])
        )
        connection.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (PASSWORDS.hash(payload.password), row["user_id"]),
        )
        sessions.revoke_all(connection, row["user_id"], now.isoformat())
        audit.record(
            connection, row["user_id"], "password_reset", None, row["user_id"], now_utc(), {}
        )


@router.get("/documents/{document_id}/grants", response_model=GrantList)
def list_grants(
    document_id: str,
    request: Request,
    document: dict[str, Any] = Depends(require_doc_access("owner")),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    with request.app.state.database.read_conn() as connection:
        check_document(connection, document_id, user["id"], "owner")
        return {"grants": grants.list_for_document(connection, document_id)}


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
        target = (
            users.get_user(connection, payload.user_id)
            if payload.user_id
            else users.by_email(connection, payload.email or "")
        )
        if target is None:
            raise Problem(
                404,
                "user_not_found",
                "No Pathya account uses that address. Ask your classmate to create one first.",
            )
        if target["id"] == user["id"]:
            raise Problem(409, "grant_to_owner", "You already own this chapter.")
        grants.put(connection, document_id, target["id"], payload.role, user["id"], now_utc())
        audit.record(
            connection,
            user["id"],
            "grant",
            document_id,
            target["id"],
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
