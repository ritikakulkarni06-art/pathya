import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.db.repos import jobs
from app.errors import Problem

ACTIVE = {"validating", "extracting", "building"}


class LeaseLost(Exception):
    pass


def reap_expired(database: Database) -> int:
    now = now_utc()
    with database.write_tx() as connection:
        expired = list(
            connection.execute(
                "SELECT * FROM jobs WHERE state IN ('validating','extracting','building') AND lease_expires_at<=?",
                (now,),
            )
        )
        for job in expired:
            failed = job["attempts"] >= job["max_attempts"]
            connection.execute(
                "UPDATE jobs SET state=?,lease_owner=NULL,lease_expires_at=NULL,error_code='lease_expired',error_message=?,updated_at=? WHERE id=?",
                (
                    "failed" if failed else "queued",
                    "The worker stopped. The attempt limit was reached."
                    if failed
                    else "The worker stopped. This job will retry.",
                    now,
                    job["id"],
                ),
            )
            if failed and job["document_id"] and job["kind"] != "delete":
                connection.execute(
                    "UPDATE documents SET state='failed',updated_at=? WHERE id=? AND state NOT IN ('deleting','deleted')",
                    (now, job["document_id"]),
                )
    return len(expired)


def claim_next(
    database: Database, settings: Settings, worker_id: str | None = None
) -> dict[str, Any] | None:
    reap_expired(database)
    owner = worker_id or str(uuid4())
    now = datetime.now(UTC)
    with database.write_tx() as connection:
        job = connection.execute(
            "SELECT jobs.* FROM jobs LEFT JOIN documents ON documents.id=jobs.document_id WHERE jobs.state='queued' AND jobs.attempts<jobs.max_attempts AND (jobs.document_id IS NULL OR jobs.kind='delete' OR documents.state NOT IN ('deleting','deleted')) ORDER BY jobs.created_at,jobs.id LIMIT 1"
        ).fetchone()
        if job is None:
            return None
        connection.execute(
            "UPDATE jobs SET state='validating',attempts=attempts+1,lease_owner=?,lease_expires_at=?,updated_at=? WHERE id=? AND state='queued'",
            (
                owner,
                (now + timedelta(seconds=settings.job_lease_seconds)).isoformat(),
                now.isoformat(),
                job["id"],
            ),
        )
        return jobs.get_job(connection, job["id"])


def heartbeat(database: Database, job_id: str, owner: str, seconds: int) -> bool:
    now = datetime.now(UTC)
    with database.write_tx() as connection:
        cursor = connection.execute(
            "UPDATE jobs SET lease_expires_at=?,updated_at=? WHERE id=? AND lease_owner=? AND state IN ('validating','extracting','building') AND lease_expires_at>?",
            (
                (now + timedelta(seconds=seconds)).isoformat(),
                now.isoformat(),
                job_id,
                owner,
                now.isoformat(),
            ),
        )
        return cursor.rowcount == 1


def progress(
    database: Database, job_id: str, owner: str, state: str, total: int, done: int, message: str
) -> None:
    now = now_utc()
    with database.write_tx() as connection:
        cursor = connection.execute(
            "UPDATE jobs SET state=?,progress_json=?,updated_at=? WHERE id=? AND lease_owner=? AND state IN ('validating','extracting','building') AND lease_expires_at>?",
            (
                state,
                json.dumps({"pages_total": total, "pages_done": done, "message": message}),
                now,
                job_id,
                owner,
                now,
            ),
        )
        if cursor.rowcount != 1:
            raise LeaseLost()


def finish(database: Database, job_id: str, owner: str, state: str, message: str) -> None:
    now = now_utc()
    with database.write_tx() as connection:
        job = jobs.get_job(connection, job_id)
        if (
            job is None
            or job["lease_owner"] != owner
            or job["state"] not in ACTIVE
            or job["lease_expires_at"] <= now
        ):
            raise LeaseLost()
        body = json.loads(job["progress_json"])
        body["message"] = message
        connection.execute(
            "UPDATE jobs SET state=?,progress_json=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?",
            (state, json.dumps(body), now, job_id),
        )


def fail(database: Database, job_id: str, owner: str, code: str, message: str) -> None:
    with database.write_tx() as connection:
        job = jobs.get_job(connection, job_id)
        if job is None or job["lease_owner"] != owner or job["state"] not in ACTIVE:
            return
        terminal = job["attempts"] >= job["max_attempts"] or code in {
            "budget_exhausted",
            "pricing_unverified",
        }
        connection.execute(
            "UPDATE jobs SET state=?,lease_owner=NULL,lease_expires_at=NULL,error_code=?,error_message=?,updated_at=? WHERE id=?",
            ("failed" if terminal else "queued", code, message, now_utc(), job_id),
        )
        if terminal and job["document_id"] and job["kind"] != "delete":
            connection.execute(
                "UPDATE documents SET state='failed',updated_at=? WHERE id=? AND state NOT IN ('deleting','deleted')",
                (now_utc(), job["document_id"]),
            )


def cancel(database: Database, job_id: str) -> None:
    with database.write_tx() as connection:
        job = jobs.get_job(connection, job_id)
        if job is None:
            raise Problem(404, "job_not_found", "This processing job is unavailable.")
        if job["state"] in {"ready", "review_required", "failed", "cancelled"}:
            return
        connection.execute(
            "UPDATE jobs SET state='cancelled',lease_owner=NULL,lease_expires_at=NULL,updated_at=?,error_code='cancelled',error_message='The owner cancelled processing.' WHERE id=?",
            (now_utc(), job_id),
        )
        if job["kind"] == "extract":
            connection.execute(
                "UPDATE documents SET state='failed',updated_at=? WHERE id=? AND state NOT IN ('deleting','deleted')",
                (now_utc(), job["document_id"]),
            )
