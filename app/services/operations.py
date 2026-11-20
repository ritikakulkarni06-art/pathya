import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.logging import log_event


def record_job_metric(database: Database, job: dict[str, Any], duration_ms: int) -> None:
    try:
        with database.write_tx() as c:
            row = c.execute("SELECT state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            c.execute(
                "INSERT INTO job_metrics VALUES (?,?,?,?,?)",
                (
                    str(uuid4()),
                    job["kind"],
                    row["state"] if row else "unavailable",
                    max(0, duration_ms),
                    now_utc(),
                ),
            )
    except sqlite3.Error:
        log_event(event="job_metric_write_failed", stage=job["kind"])


def prune_metrics(database: Database) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    with database.write_tx() as c:
        c.execute("DELETE FROM job_metrics WHERE created_at<?", (cutoff,))
        c.execute("DELETE FROM upload_usage WHERE day<?", (cutoff[:10],))
        c.execute("DELETE FROM question_usage WHERE day<?", (cutoff[:10],))


def job_statuses(database: Database) -> list[dict[str, Any]]:
    with database.read_conn() as c:
        return list(
            c.execute(
                "SELECT id,document_id,kind,state,attempts,max_attempts,lease_expires_at,error_code,created_at,updated_at FROM jobs WHERE state='failed' OR (state IN ('validating','extracting','building') AND lease_expires_at<=?) ORDER BY updated_at DESC LIMIT 100",
                (now_utc(),),
            )
        )


def storage_status(database: Database, settings: Settings) -> dict[str, Any]:
    with database.read_conn() as c:
        rows = list(
            c.execute(
                "SELECT document_id,COUNT(*) AS files,COALESCE(SUM(bytes),0) AS bytes FROM assets WHERE deleted_at IS NULL GROUP BY document_id"
            )
        )
    return {
        "documents": rows,
        "bytes_stored": sum(r["bytes"] for r in rows),
        "free_bytes": shutil.disk_usage(settings.pathya_data_dir).free,
    }


def metrics(database: Database) -> dict[str, Any]:
    with database.read_conn() as c:
        c.execute("BEGIN")
        states = list(
            c.execute("SELECT kind,state,COUNT(*) AS count FROM jobs GROUP BY kind,state")
        )
        stages = list(
            c.execute(
                "SELECT kind,outcome,COUNT(*) AS attempts,SUM(duration_ms) AS duration_ms,AVG(duration_ms) AS average_duration_ms FROM job_metrics GROUP BY kind,outcome"
            )
        )
        stored = c.execute(
            "SELECT COALESCE(SUM(bytes),0) AS bytes FROM assets WHERE deleted_at IS NULL"
        ).fetchone()["bytes"]
        usage = c.execute(
            "SELECT COUNT(*) AS attempts,COALESCE(SUM(cost_inr_micro),0) AS cost_inr_micro FROM usage_events"
        ).fetchone()
    return {
        "queue_depth": sum(r["count"] for r in states if r["state"] == "queued"),
        "failures": sum(r["count"] for r in states if r["state"] == "failed"),
        "jobs": states,
        "observed_stage_durations": stages,
        "bytes_stored": stored,
        "usage": usage,
    }
