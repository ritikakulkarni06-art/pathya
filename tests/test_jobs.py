import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.repos import jobs
from app.main import create_app
from app.services.auth import current_user, now_utc
from app.services.jobs import LeaseLost, cancel, claim_next, fail, heartbeat, progress, reap_expired
from app.worker.runner import child_environment, run_once
from tests.test_uploads import pdf_bytes, upload


@pytest.fixture
def worker_client(tmp_path, database):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path,
        pathya_db_path=database.path,
        storage_min_free_bytes=0,
        job_lease_seconds=30,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_claim_race_and_idempotency(seeded):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=seeded.path.parent,
        pathya_db_path=seeded.path,
    )
    with seeded.write_tx() as conn:
        first = jobs.enqueue(conn, "d", "build_index", {}, 3, "same", now_utc())
        assert jobs.enqueue(conn, "d", "build_index", {}, 3, "same", now_utc()) == first
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: claim_next(seeded, settings), range(2)))
    assert sum(item is not None for item in claimed) == 1
    active = next(item for item in claimed if item is not None)
    assert active["attempts"] == 1
    assert heartbeat(seeded, first, active["lease_owner"], 10)
    assert not heartbeat(seeded, first, "wrong", 10)


def test_expiry_retry_and_terminal_failure(seeded):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=seeded.path.parent,
        pathya_db_path=seeded.path,
    )
    with seeded.write_tx() as conn:
        job_id = jobs.enqueue(conn, "d", "build_index", {}, 2, "retry", now_utc())
    active = claim_next(seeded, settings)
    with seeded.write_tx() as conn:
        conn.execute("UPDATE jobs SET lease_expires_at='2000-01-01' WHERE id=?", (job_id,))
    assert reap_expired(seeded) == 1
    with pytest.raises(LeaseLost):
        progress(seeded, job_id, active["lease_owner"], "building", 1, 0, "Old worker")
    retry = claim_next(seeded, settings)
    assert retry["attempts"] == 2
    fail(seeded, job_id, retry["lease_owner"], "test_failure", "The attempt failed.")
    with seeded.read_conn() as conn:
        result = jobs.get_job(conn, job_id)
    assert result["state"] == "failed"
    assert result["error_code"] == "test_failure"
    assert claim_next(seeded, settings) is None


def test_cancellation_and_job_authorization(worker_client):
    response = upload(worker_client, pdf_bytes(10)).json()
    job_id = response["job_id"]
    database = worker_client.app.state.database
    settings = worker_client.app.state.settings
    active = claim_next(database, settings)
    assert worker_client.get("/jobs/" + job_id).status_code == 200
    worker_client.app.dependency_overrides[current_user] = lambda: {"id": "other", "role": "admin"}
    assert worker_client.get("/jobs/" + job_id).status_code == 404
    assert worker_client.post("/jobs/" + job_id + "/cancel").status_code == 404
    worker_client.app.dependency_overrides.clear()
    assert worker_client.post("/jobs/" + job_id + "/cancel").status_code == 204
    assert not heartbeat(database, job_id, active["lease_owner"], 10)
    with pytest.raises(LeaseLost):
        progress(database, job_id, active["lease_owner"], "extracting", 10, 1, "Page completed")
    cancel(database, job_id)
    assert worker_client.get("/jobs/" + job_id).json()["state"] == "cancelled"


def test_fixture_extract_and_idempotent_retry(worker_client):
    response = upload(worker_client, pdf_bytes(10)).json()
    database = worker_client.app.state.database
    settings = worker_client.app.state.settings
    assert run_once(database, settings)
    result = worker_client.get("/jobs/" + response["job_id"]).json()
    assert result["state"] == "review_required"
    assert result["progress"]["pages_done"] == 10
    with database.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"] == 10
        count = conn.execute("SELECT count(*) AS n FROM blocks").fetchone()["n"]
    with database.write_tx() as conn:
        conn.execute("UPDATE jobs SET state='queued' WHERE id=?", (response["job_id"],))
    for _ in range(5):
        assert run_once(database, settings)
        with database.read_conn() as connection:
            if jobs.get_job(connection, response["job_id"])["state"] == "review_required":
                break
    else:
        raise AssertionError("The extraction retry did not complete")
    with database.read_conn() as conn:
        assert conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"] == 10
        assert conn.execute("SELECT count(*) AS n FROM blocks").fetchone()["n"] == count


def test_real_worker_crash_and_restart(worker_client):
    response = upload(worker_client, pdf_bytes(10)).json()
    settings = worker_client.app.state.settings.model_copy(
        update={
            "job_lease_seconds": 30,
            "extraction_adapter": "python:tests.fixtures.slow_adapter:SlowFixture",
        }
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "app.worker", "--once"],
        env=child_environment(settings),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    database = worker_client.app.state.database
    try:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with database.read_conn() as conn:
                job = jobs.get_job(conn, response["job_id"])
            if json.loads(job["progress_json"]).get("pages_done", 0) >= 1:
                break
            if process.poll() is not None:
                raise AssertionError("Worker exited before crash injection")
            time.sleep(0.1)
        else:
            raise AssertionError(
                "No extraction progress before deadline: "
                + str(
                    {key: job[key] for key in ("state", "attempts", "error_code", "progress_json")}
                )
            )
        process.kill()
        process.wait(timeout=5)
        with database.write_tx() as conn:
            conn.execute(
                "UPDATE jobs SET lease_expires_at='2000-01-01' WHERE id=?", (response["job_id"],)
            )
        restarted = settings.model_copy(update={"extraction_adapter": "fixture"})
        subprocess.run(
            [sys.executable, "-m", "app.worker", "--once"],
            env=child_environment(restarted),
            check=True,
            timeout=60,
            creationflags=flags,
        )
        with database.read_conn() as conn:
            result = jobs.get_job(conn, response["job_id"])
            assert result["state"] == "review_required"
            assert result["attempts"] == 2
            assert conn.execute("SELECT count(*) AS n FROM pages").fetchone()["n"] == 10
            assert conn.execute("SELECT count(*) AS n FROM revisions").fetchone()["n"] == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_cli_timeout_is_visible_and_does_not_remove_source(worker_client):
    response = upload(worker_client, pdf_bytes(10)).json()
    settings = worker_client.app.state.settings.model_copy(
        update={
            "job_timeout_seconds": 1,
            "job_max_attempts": 1,
            "extraction_adapter": "python:tests.fixtures.slow_adapter:SlowFixture",
        }
    )
    with worker_client.app.state.database.write_tx() as conn:
        conn.execute("UPDATE jobs SET max_attempts=1 WHERE id=?", (response["job_id"],))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(
        [sys.executable, "-m", "app.worker", "--once"],
        env=child_environment(settings),
        check=True,
        timeout=45,
        creationflags=flags,
    )
    result = worker_client.get("/jobs/" + response["job_id"]).json()
    assert result["state"] == "failed"
    assert result["last_error_code"] == "job_timeout"
    assert worker_client.get("/documents/" + response["document_id"]).status_code == 200


def test_cancelled_worker_cannot_change_document_state(worker_client):
    from app.worker.runner import execute_claimed

    response = upload(worker_client, pdf_bytes(10)).json()
    database = worker_client.app.state.database
    settings = worker_client.app.state.settings
    active = claim_next(database, settings)
    cancel(database, response["job_id"])
    execute_claimed(database, settings, active)
    with database.read_conn() as conn:
        assert (
            conn.execute(
                "SELECT state FROM documents WHERE id=?", (response["document_id"],)
            ).fetchone()["state"]
            == "failed"
        )
        assert conn.execute("SELECT count(*) AS n FROM blocks").fetchone()["n"] == 0
        assert jobs.get_job(conn, response["job_id"])["state"] == "cancelled"


def test_heartbeat_busy_retries_without_claiming_ownership_or_exposing_errors(seeded, monkeypatch):
    import sqlite3

    import app.worker.runner as runner

    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=seeded.path.parent,
        pathya_db_path=seeded.path,
    )
    with seeded.write_tx() as connection:
        identifier = jobs.enqueue(
            connection, "d", "build_index", {}, 3, "busy-heartbeat", now_utc()
        )
    job = claim_next(seeded, settings)
    real_heartbeat = runner.heartbeat

    def busy(*args):
        error = sqlite3.OperationalError("busy")
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise error

    monkeypatch.setattr(runner, "heartbeat", busy)
    assert runner.renew_lease(seeded, job, settings) is None
    monkeypatch.setattr(runner, "heartbeat", real_heartbeat)
    assert runner.renew_lease(seeded, job, settings) is True
    cancel(seeded, identifier)
    assert runner.renew_lease(seeded, job, settings) is False


def test_busy_heartbeat_is_distinguished_from_lost_lease(database, monkeypatch):
    import sqlite3

    import app.worker.runner as runner

    settings = Settings(_env_file=None)
    busy = sqlite3.OperationalError("busy")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY

    def raise_busy(*args):
        raise busy

    monkeypatch.setattr(runner, "heartbeat", raise_busy)
    assert runner.renew_lease(database, {"id": "job", "lease_owner": "worker"}, settings) is None
    monkeypatch.setattr(runner, "heartbeat", lambda *args: False)
    assert runner.renew_lease(database, {"id": "job", "lease_owner": "worker"}, settings) is False
