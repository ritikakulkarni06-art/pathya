import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, Request

from app.config import Settings
from app.errors import Problem
from app.services.auth import LoginLimiter, current_user


class ActionLimiter:
    """One-process, bounded per-IP and per-user windows; identifiers are hashed."""

    def __init__(self, settings: Settings) -> None:
        self.window = settings.request_rate_window_seconds
        self.limiters = {
            "upload": LoginLimiter(settings.upload_rate_limit, self.window),
            "question": LoginLimiter(settings.question_rate_limit, self.window),
            "correction": LoginLimiter(settings.correction_rate_limit, self.window),
        }

    def check(self, action: str, ip: str, user_id: str) -> None:
        try:
            self.limiters[action].check(ip, user_id)
        except Problem:
            raise Problem(
                429,
                action + "_rate_limited",
                "Too many requests for this action. Please wait before trying again.",
                extra={"retry_after": self.window},
            ) from None


def question_usage(
    connection: sqlite3.Connection,
    user_id: str,
    limit: int,
    instant: datetime,
    *,
    spend: bool = False,
) -> dict[str, int]:
    day = instant.date().isoformat()
    if spend:
        updated = connection.execute(
            """
            INSERT INTO question_usage(user_id,day,count) VALUES (?,?,1)
            ON CONFLICT(user_id,day) DO UPDATE SET count=count+1 WHERE count<?
            """,
            (user_id, day, limit),
        )
        if updated.rowcount == 0:
            reset = datetime.combine(instant.date() + timedelta(days=1), datetime.min.time(), UTC)
            raise Problem(
                429,
                "daily_question_limit",
                "The daily question limit is reached.",
                extra={
                    "limit": limit,
                    "remaining": 0,
                    "retry_after": int((reset - instant).total_seconds()) + 1,
                },
            )
    row = connection.execute(
        "SELECT count FROM question_usage WHERE user_id=? AND day=?", (user_id, day)
    ).fetchone()
    return {"limit": limit, "remaining": max(0, limit - (row["count"] if row else 0))}


def rate_limit(action: str) -> Callable[..., None]:
    def dependency(request: Request, user: dict[str, Any] = Depends(current_user)) -> None:
        ip = request.client.host if request.client else "unknown"
        request.app.state.action_limiter.check(action, ip, user["id"])

    return dependency


def reserve_upload(
    connection: sqlite3.Connection, settings: Settings, user_id: str, pages: int, instant: str
) -> None:
    active = connection.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE owner_id=? AND state='uploading'", (user_id,)
    ).fetchone()["n"]
    if active >= settings.max_concurrent_uploads:
        raise Problem(
            429,
            "upload_concurrency",
            "Finish or remove an existing upload before starting another.",
            extra={"retry_after": 1},
        )
    day = instant[:10]
    row = connection.execute(
        "SELECT pages FROM upload_usage WHERE user_id=? AND day=?", (user_id, day)
    ).fetchone()
    used = row["pages"] if row else 0
    if used + pages > settings.daily_page_quota:
        now = datetime.now(UTC)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        raise Problem(
            429,
            "daily_page_quota",
            "Today's page allowance has been reached. Try again after the next UTC day begins.",
            extra={"retry_after": max(1, int((tomorrow - now).total_seconds()))},
        )
    connection.execute(
        "INSERT INTO upload_usage VALUES (?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET pages=pages+excluded.pages",
        (user_id, day, pages),
    )
    cutoff = (datetime.now(UTC) - timedelta(days=30)).date().isoformat()
    connection.execute("DELETE FROM upload_usage WHERE day<?", (cutoff,))
