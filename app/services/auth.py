import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request

from app.config import Settings
from app.db.connection import Database
from app.db.repos import sessions, users
from app.errors import Problem
from app.services.access import DocumentRole, require_document

LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
SESSION_COOKIE = "pathya_session"
CSRF_COOKIE = "pathya_csrf"
PASSWORDS = PasswordHasher(type=Type.ID)
# Verification against the dummy hash keeps missing-account login failures comparable.
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.session_secret.get_secret_value().encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


class LoginLimiter:
    """Bounded single-process sliding windows. Entries contain only hashed identifiers."""

    def __init__(self, limit: int, window: int) -> None:
        self.limit = limit
        self.window = window
        self.events: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def check(self, ip: str, email: str) -> None:
        instant = time.monotonic()
        with self.lock:
            for key in list(self.events):
                while self.events[key] and self.events[key][0] <= instant - self.window:
                    self.events[key].popleft()
                if not self.events[key]:
                    del self.events[key]
            keys = [
                token_digest("ip:" + ip),
                token_digest("email:" + email),
                token_digest(ip + ":" + email),
            ]
            if (
                any(len(self.events.get(key, ())) >= self.limit for key in keys)
                or len(self.events) > 10000
            ):
                raise Problem(
                    429,
                    "login_rate_limited",
                    "Too many sign-in attempts. Please wait before retrying.",
                )
            for key in keys:
                self.events.setdefault(key, deque()).append(instant)


def seed_local(database: Database) -> None:
    with database.write_tx() as connection:
        if users.get_user(connection, LOCAL_USER_ID) is None:
            users.create(connection, LOCAL_USER_ID, "local@pathya.invalid", None, now_utc())


def current_user(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    database: Database = request.app.state.database
    if settings.auth_mode == "local":
        with database.read_conn() as connection:
            user = users.get_user(connection, LOCAL_USER_ID)
    else:
        token = request.cookies.get(SESSION_COOKIE, "")
        if not token or len(token) > 256:
            raise Problem(401, "authentication_required", "Please sign in to continue.")
        with database.read_conn() as connection:
            user = sessions.active_user(connection, token_digest(token), now_utc())
        if user is not None and request.method not in {"GET", "HEAD", "OPTIONS"}:
            provided = request.headers.get("X-CSRF-Token", "")
            cookie = request.cookies.get(CSRF_COOKIE, "")
            expected = csrf_token(token, settings)
            if (
                not provided
                or not hmac.compare_digest(provided, cookie)
                or not hmac.compare_digest(provided, expected)
            ):
                raise Problem(
                    403,
                    "csrf_failed",
                    "Refresh your session and send the CSRF token before changing data.",
                )
    if user is None:
        raise Problem(
            401, "authentication_required", "Your session has expired. Please sign in again."
        )
    return user


def require_doc_access(minimum: DocumentRole = "reader") -> Callable[..., dict[str, Any]]:
    def dependency(
        request: Request, user: dict[str, Any] = Depends(current_user)
    ) -> dict[str, Any]:
        document_id = request.path_params.get("document_id")
        if document_id is None:
            raise Problem(500, "access_configuration", "Document access could not be checked.")
        return require_document(request.app.state.database, str(document_id), user["id"], minimum)

    return dependency


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise Problem(403, "admin_required", "This operation requires a project administrator.")
    return user
