import json
import sqlite3
import traceback
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.db.repos.jobs import enqueue
from app.errors import Problem
from app.main import create_app
from app.services.auth import current_user
from app.services.deletions import request_delete
from app.services.limits import ActionLimiter
from app.services.operations import metrics, prune_metrics
from app.worker.runner import run_once
from scripts.reset_demo import reset_demo
from scripts.seed_demo import demo_settings, seed_demo
from tests.test_auth import session_app as session_app
from tests.test_auth import signed_client
from tests.test_jobs import worker_client as worker_client
from tests.test_revisions import edit
from tests.test_uploads import pdf_bytes, upload


def test_rate_limits_separate_actions_but_share_user_and_ip_windows(tmp_path, monkeypatch):
    instant = [10.0]
    monkeypatch.setattr("app.services.auth.time.monotonic", lambda: instant[0])
    settings = Settings(_env_file=None, pathya_data_dir=tmp_path, question_rate_limit=1)
    limiter = ActionLimiter(settings)
    limiter.check("question", "ip1", "u1")
    for ip, user in [("ip2", "u1"), ("ip1", "u2")]:
        with pytest.raises(Problem, match="question_rate_limited"):
            limiter.check("question", ip, user)
    limiter.check("upload", "ip1", "u1")
    instant[0] += 61
    limiter.check("question", "ip1", "u1")


@pytest.mark.parametrize("action", ["upload", "question", "correction"])
def test_action_routes_return_retry_after(seeded, worker_client, action):
    client = worker_client
    settings = client.app.state.settings
    setattr(settings, action + "_rate_limit", 1)
    client.app.state.action_limiter = ActionLimiter(settings)
    client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    if action == "upload":
        first = upload(client, pdf_bytes(1))
        second = upload(client, pdf_bytes(2))
    elif action == "question":
        payload = {"document_id": "d", "question": "Synthetic"}
        first = client.post("/questions", json=payload)
        second = client.post("/questions", json=payload)
    else:
        first = edit(client, "b", 1, "New reviewed source text.")
        second = edit(client, "b", 2, "Another reviewed source text.")
    assert first.status_code in {200, 202}
    assert second.status_code == 429
    assert second.json()["code"] == action + "_rate_limited"
    assert int(second.headers["Retry-After"]) == settings.request_rate_window_seconds


def test_daily_page_quota_counts_new_uploads_without_duplicate_charges(worker_client):
    client = worker_client
    client.app.state.settings.daily_page_quota = 2
    first = upload(client, pdf_bytes(2))
    assert first.status_code == 202
    assert upload(client, pdf_bytes(2)).status_code == 200
    rejected = upload(client, pdf_bytes(1))
    assert rejected.status_code == 429 and rejected.json()["code"] == "daily_page_quota"
    assert int(rejected.headers["Retry-After"]) > 0
    with client.app.state.database.read_conn() as c:
        assert c.execute("SELECT pages FROM upload_usage").fetchone()["pages"] == 2
    assert client.delete("/documents/" + first.json()["document_id"]).status_code == 202
    assert upload(client, pdf_bytes(1)).json()["code"] == "daily_page_quota"


def test_concurrent_upload_allocation_cap(worker_client):
    client = worker_client
    first = upload(client, pdf_bytes(1)).json()
    with client.app.state.database.write_tx() as c:
        c.execute(
            "INSERT INTO documents SELECT 'pending0',owner_id,title,'pending-hash-0',rights_note,languages_json,0,'uploading',retention_until,created_at,updated_at,NULL FROM documents WHERE id=?",
            (first["document_id"],),
        )
        c.execute(
            "INSERT INTO documents SELECT 'pending1',owner_id,title,'pending-hash-1',rights_note,languages_json,0,'uploading',retention_until,created_at,updated_at,NULL FROM documents WHERE id=?",
            (first["document_id"],),
        )
    refused = upload(client, pdf_bytes(2))
    assert refused.status_code == 429 and refused.json()["code"] == "upload_concurrency"
    assert client.delete("/documents/pending0").status_code == 202
    assert upload(client, pdf_bytes(2)).status_code == 202


def test_json_body_limit_headers_and_safe_busy_errors(seeded, worker_client, caplog):
    client = worker_client
    client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    client.app.state.settings.max_json_body_bytes = 1024
    oversized = client.post("/questions", json={"document_id": "d", "question": "private" * 200})
    assert oversized.status_code == 413
    normal = client.get("/documents/d/content")
    assert normal.status_code == 200
    assert normal.headers["Cache-Control"] == "no-store"
    assert normal.headers["X-Content-Type-Options"] == "nosniff"
    assert normal.headers["Referrer-Policy"] == "no-referrer"

    @client.app.get("/synthetic-busy")
    def busy():
        error = sqlite3.OperationalError("PRIVATE QUERY OR KEY")
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        raise error

    response = client.get("/synthetic-busy")
    assert response.status_code == 503 and response.json()["code"] == "storage_busy"
    assert response.headers["Retry-After"] == "1"
    assert "PRIVATE QUERY OR KEY" not in response.text + caplog.text
    assert "privateprivate" not in caplog.text


@pytest.mark.parametrize("user,status", [(None, 401), ("u", 403), ("reader", 403), ("admin", 200)])
def test_operational_routes_are_admin_only(session_app, user, status):
    with signed_client(session_app, user) as client:
        for path in ["/admin/jobs", "/admin/storage", "/admin/metrics"]:
            response = client.get(path)
            assert response.status_code == status
            if status == 200:
                assert "text_current" not in response.text and "private_path" not in response.text


def test_worker_metrics_measure_attempts_without_content(seeded, worker_client):
    with seeded.write_tx() as c:
        enqueue(c, "d", "build_index", {}, 1, None, "2026-01-01")
    assert run_once(seeded, worker_client.app.state.settings)
    values = metrics(seeded)
    stage = values["observed_stage_durations"][0]
    assert stage["kind"] == "build_index" and stage["attempts"] == 1
    assert stage["duration_ms"] >= 0 and stage["outcome"] == "ready"
    assert "Synthetic text" not in json.dumps(values)


def test_daily_metadata_pruning_preserves_current_counters(seeded):
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    current = datetime.now(UTC).isoformat()
    with seeded.write_tx() as c:
        c.execute("INSERT INTO upload_usage VALUES ('u',?,1)", (old[:10],))
        c.execute("INSERT INTO upload_usage VALUES ('u',?,1)", (current[:10],))
        c.execute("INSERT INTO job_metrics VALUES ('old','extract','ready',1,?)", (old,))
        c.execute("INSERT INTO job_metrics VALUES ('current','extract','ready',1,?)", (current,))
    prune_metrics(seeded)
    with seeded.read_conn() as c:
        assert c.execute("SELECT day FROM upload_usage").fetchall() == [{"day": current[:10]}]
        assert c.execute("SELECT id FROM job_metrics").fetchall() == [{"id": "current"}]


@pytest.mark.parametrize("action", ["grant", "audio"])
def test_revocation_between_dependency_and_write_cannot_add_grants_or_jobs(
    seeded, worker_client, monkeypatch, action
):
    from app.services import auth

    client = worker_client
    client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    with seeded.write_tx() as c:
        c.execute("INSERT INTO users VALUES ('other','other@test.invalid',NULL,'user','now')")
    original = auth.require_document

    def delete_after_authorization(database, document_id, user_id, minimum):
        document = original(database, document_id, user_id, minimum)
        request_delete(database, client.app.state.settings, document_id, user_id)
        return document

    monkeypatch.setattr(auth, "require_document", delete_after_authorization)
    result = (
        client.post("/documents/d/grants", json={"user_id": "other", "role": "reader"})
        if action == "grant"
        else client.post("/blocks/b/audio", json={})
    )
    assert result.status_code == 404
    with seeded.read_conn() as c:
        assert c.execute("SELECT COUNT(*) n FROM document_grants").fetchone()["n"] == 0
        assert c.execute("SELECT kind FROM jobs").fetchall() == [{"kind": "delete"}]


def test_invalid_startup_configuration_never_prints_environment_secrets(monkeypatch):
    monkeypatch.setenv("PATHYA_ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "session")
    monkeypatch.setenv("SESSION_SECRET", "short-private-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "another-private-key")
    with pytest.raises(ValueError) as captured:
        load_settings()
    rendered = "".join(traceback.format_exception(captured.value))
    assert "short-private-secret" not in rendered and "another-private-key" not in rendered
    assert "Configuration is invalid" in rendered
    with pytest.raises(ValueError, match="Configuration is invalid"):
        create_app()


def test_synthetic_seed_and_reset_work_offline(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Synthetic demo must stay offline")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    directory = tmp_path / "demo"
    info = seed_demo(directory)
    assert info["synthetic_audio"] and info["llm_enabled"] is False
    with TestClient(create_app(demo_settings(directory))) as client:
        audio = client.get("/blocks/" + info["block_id"] + "/audio")
        assert audio.status_code == 200 and audio.json()["synthetic"] is True
        answer = client.post(
            "/questions", json={"document_id": info["document_id"], "question": "sunlight"}
        )
        assert answer.status_code == 200 and answer.json()["reason"] == "assistant_disabled"
    assert reset_demo(directory) == 1
    assert reset_demo(directory) == 0
    assert not (directory / "sources" / info["document_id"]).exists()
