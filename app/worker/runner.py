import json
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from app.config import Settings
from app.db.connection import Database
from app.db.migrate import migrate
from app.db.repos import jobs
from app.errors import Problem
from app.services.jobs import LeaseLost, claim_next, fail, finish, heartbeat
from app.worker.handlers.extract import handle as extract


def execute_claimed(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    try:
        if job["kind"] == "extract":
            extract(database, settings, job)
        elif job["kind"] in {"build_audio", "build_index"}:
            finish(
                database,
                job["id"],
                job["lease_owner"],
                "ready",
                "This derivative handler is not installed yet; source text remains the fallback.",
            )
        else:
            raise Problem(
                422, "handler_unavailable", "This processing stage is not implemented yet."
            )
    except LeaseLost:
        return
    except Problem as error:
        fail(database, job["id"], job["lease_owner"], error.code, error.detail)
    except Exception:
        fail(
            database,
            job["id"],
            job["lease_owner"],
            "processing_failed",
            "Processing could not finish. Check the adapter and retry limit.",
        )


def run_once(database: Database, settings: Settings) -> bool:
    """In-process integration helper. The CLI uses a child process for hard timeout control."""
    job = claim_next(database, settings)
    if job is None:
        return False
    stopped = threading.Event()

    def keep_lease() -> None:
        while not stopped.wait(settings.job_lease_seconds / 3):
            if not heartbeat(database, job["id"], job["lease_owner"], settings.job_lease_seconds):
                break

    keeper = threading.Thread(target=keep_lease, daemon=True)
    keeper.start()
    try:
        execute_claimed(database, settings, job)
    finally:
        stopped.set()
        keeper.join(timeout=5)
    return True


def child_environment(settings: Settings) -> dict[str, str]:
    environment = os.environ.copy()
    for key, value in settings.model_dump(mode="json").items():
        if value is None:
            environment.pop(key.upper(), None)
        else:
            environment[key.upper()] = (
                json.dumps(value) if isinstance(value, (list, dict)) else str(value)
            )
    environment["SESSION_SECRET"] = settings.session_secret.get_secret_value()
    environment["GEMINI_API_KEY"] = settings.gemini_api_key.get_secret_value()
    return environment


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        process.kill()
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_worker(settings: Settings, *, once: bool = False) -> None:
    assert settings.pathya_db_path is not None
    database = Database(settings.pathya_db_path)
    migrate(database)
    stopping = threading.Event()

    def shutdown(signum: int, frame: Any) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stopping.is_set():
        job = claim_next(database, settings)
        if job is None:
            if once:
                return
            stopping.wait(0.5)
            continue
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(
            [sys.executable, "-m", "app.worker.execute", job["id"], job["lease_owner"]],
            env=child_environment(settings),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
            creationflags=flags,
        )
        started = time.monotonic()
        last_heartbeat = started
        while process.poll() is None:
            instant = time.monotonic()
            if stopping.is_set() or instant - started >= settings.job_timeout_seconds:
                stop_process(process)
                fail(
                    database,
                    job["id"],
                    job["lease_owner"],
                    "worker_stopped" if stopping.is_set() else "job_timeout",
                    "Processing stopped. The visible retry policy will be applied.",
                )
                break
            if instant - last_heartbeat >= settings.job_lease_seconds / 3:
                if not heartbeat(
                    database, job["id"], job["lease_owner"], settings.job_lease_seconds
                ):
                    stop_process(process)
                    break
                last_heartbeat = instant
            stopping.wait(0.05)
        with database.read_conn() as connection:
            remaining = jobs.get_job(connection, job["id"])
        if remaining and remaining["lease_owner"] == job["lease_owner"]:
            fail(
                database,
                job["id"],
                job["lease_owner"],
                "worker_exit",
                "The worker exited before completing this attempt.",
            )
        if once:
            return
