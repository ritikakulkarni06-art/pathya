import hashlib
import io
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db.connection import Database
from app.db.migrate import migrate
from app.errors import Problem
from app.services.auth import current_user
from app.services.backups import create_backup, prune_backups, restore_backup
from app.services.deletions import (
    purge_document,
    request_delete,
    schedule_daily_sweep,
    sweep_retention,
)
from app.services.retrieval.index import build_index
from app.services.storage import DeletionResult, FileStore
from app.worker.runner import run_once
from tests.test_auth import session_app as session_app
from tests.test_auth import signed_client
from tests.test_jobs import worker_client as worker_client
from tests.test_uploads import pdf_bytes, upload


@pytest.fixture
def deletion_client(seeded, worker_client):
    worker_client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    store = FileStore(worker_client.app.state.settings.pathya_data_dir, seeded, min_free_bytes=0)
    asset, _, _ = store.put_source("d", io.BytesIO(b"synthetic original"), 100)
    derived, _, _ = store.put_derived("d", "audio", io.BytesIO(b"synthetic audio"), 100)
    with seeded.write_tx() as c:
        c.execute("UPDATE pages SET source_asset_id=? WHERE id='p'", (asset,))
        c.execute(
            "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,status,asset_id,created_at,updated_at) VALUES ('a','d','audio_block','b','{\"b\":1}','ready',?,'now','now')",
            (derived,),
        )
        c.execute("INSERT INTO audio_manifests VALUES ('a','cache','{}','glossary','now')")
        c.execute("INSERT INTO artifact_clips VALUES ('a',?)", (derived,))
        c.execute("INSERT INTO packages VALUES ('pkg','d',1,'m','a','{}','digest',0,'now')")
    build_index(seeded, worker_client.app.state.settings, "d")
    answer = worker_client.post(
        "/questions", json={"document_id": "d", "question": "Synthetic"}
    ).json()
    return worker_client, asset, derived, answer["id"]


def test_delete_revokes_reads_then_purges_files_rows_and_immutable_history(deletion_client):
    client, source, audio, answer = deletion_client
    database, settings = client.app.state.database, client.app.state.settings
    response = client.delete("/documents/d")
    assert response.status_code == 202
    receipt = response.json()
    assert receipt["purge_local_copy"] and receipt["status"] == "pending"
    assert datetime.fromisoformat(receipt["completes_by"]) - datetime.fromisoformat(
        receipt["requested_at"]
    ) <= timedelta(days=7)
    for path in [
        "/documents/d",
        "/documents/d/content",
        "/blocks/b",
        "/documents/d/search?q=Synthetic",
        "/assets/" + source,
        "/assets/" + audio,
        "/artifacts/a",
        "/answers/" + answer,
    ]:
        assert client.get(path).status_code == 404, path
    manifest = client.get("/documents/d/manifest")
    assert manifest.status_code == 410 and manifest.json()["purge_local_copy"]
    assert (
        client.post("/questions", json={"document_id": "d", "question": "Synthetic"}).status_code
        == 404
    )
    assert client.get("/documents").json()["documents"] == []
    with pytest.raises(Problem, match="document_not_found"):
        FileStore(settings.pathya_data_dir, database, min_free_bytes=0).put_derived(
            "d", "late", io.BytesIO(b"late"), 10
        )
    assert run_once(database, settings)
    final = client.get(receipt["status_url"]).json()
    assert final["status"] == "complete" and final["counts"]["blocks"] == 1
    assert final["counts"]["audio_manifests"] == 1 and final["counts"]["packages"] == 1
    assert final["counts"]["files_removed"] == 2
    assert not (settings.pathya_data_dir / "sources" / "d").exists()
    assert not (settings.pathya_data_dir / "derived" / "d").exists()
    with database.read_conn() as c:
        assert c.execute("SELECT COUNT(*) n FROM blocks").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM assets").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM chunks_fts").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM chunk_metadata").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM answers").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM revisions").fetchone()["n"] == 0
        assert c.execute("SELECT COUNT(*) n FROM purge_guards").fetchone()["n"] == 0
        tombstone = c.execute("SELECT * FROM documents WHERE id='d'").fetchone()
        assert (
            tombstone["state"] == "deleted" and tombstone["title"] == tombstone["rights_note"] == ""
        )
        assert "Synthetic" not in json.dumps(tombstone)
    assert purge_document(database, settings, "d")
    assert client.delete("/documents/d").json()["receipt_id"] == receipt["receipt_id"]
    assert client.get("/documents/d/manifest").status_code == 410


@pytest.mark.parametrize(
    "user,status",
    [(None, 401), ("u", 202), ("reader", 403), ("reviewer", 403), ("other", 404), ("admin", 404)],
)
def test_only_document_owner_can_request_delete(session_app, user, status):
    with signed_client(session_app, user) as client:
        assert client.delete("/documents/d").status_code == status


def test_receipts_do_not_grant_admin_or_former_reviewer_access(session_app):
    with signed_client(session_app, "u") as client:
        receipt = client.delete("/documents/d").json()
    for user in ["reader", "reviewer", "other", "admin"]:
        with signed_client(session_app, user) as client:
            assert client.get(receipt["status_url"]).status_code == 404
            assert client.get("/documents/d/manifest").status_code == 404
            assert client.post(receipt["status_url"] + "/retry").status_code == 404


def test_immutable_history_cannot_be_purged_without_deleting_guard(seeded, worker_client):
    with pytest.raises(sqlite3.IntegrityError):
        with seeded.write_tx() as c:
            c.execute("INSERT INTO purge_guards VALUES ('d')")
    request_delete(seeded, worker_client.app.state.settings, "d", "u")
    with pytest.raises(sqlite3.IntegrityError):
        with seeded.write_tx() as c:
            c.execute("DELETE FROM block_versions WHERE block_id='b'")
    assert purge_document(seeded, worker_client.app.state.settings, "d")


def test_failed_file_removal_is_visible_and_explicitly_resumable(deletion_client, monkeypatch):
    client, *_ = deletion_client
    settings, database = client.app.state.settings, client.app.state.database
    settings.job_max_attempts = 1
    original = FileStore.secure_delete_document
    monkeypatch.setattr(
        FileStore,
        "secure_delete_document",
        lambda *args: DeletionResult(failures=["file_removal_failed"]),
    )
    receipt = client.delete("/documents/d").json()
    assert run_once(database, settings)
    assert client.get(receipt["status_url"]).json()["status"] == "failed"
    assert client.get("/documents/d/content").status_code == 404
    monkeypatch.setattr(FileStore, "secure_delete_document", original)
    assert client.post(receipt["status_url"] + "/retry").status_code == 202
    assert run_once(database, settings)
    assert client.get(receipt["status_url"]).json()["status"] == "complete"


def test_document_temporaries_are_purged_without_removing_other_requests(deletion_client):
    client, *_ = deletion_client
    settings, database = client.app.state.settings, client.app.state.database
    temporary = settings.pathya_data_dir / "tmp"
    owned = temporary / (hashlib.sha256(b"d").hexdigest() + "-abandoned")
    owned.write_bytes(b"private temporary")
    other = temporary / (hashlib.sha256(b"d-other").hexdigest() + "-abandoned")
    other.write_bytes(b"unrelated")
    client.delete("/documents/d")
    assert run_once(database, settings)
    assert not owned.exists() and other.read_bytes() == b"unrelated"


def test_daily_sweep_is_idempotent_and_retention_can_be_extended(seeded, worker_client):
    settings = worker_client.app.state.settings
    with seeded.write_tx() as c:
        c.execute("UPDATE documents SET retention_until='2000-01-01' WHERE id='d'")
    worker_client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    assert worker_client.patch("/documents/d/retention", json={"days": 30}).status_code == 200
    assert sweep_retention(seeded, settings) == 0
    assert worker_client.patch("/documents/d/retention", json={"days": 999}).status_code == 422
    with seeded.write_tx() as c:
        c.execute("UPDATE documents SET retention_until='2000-01-01' WHERE id='d'")
    assert sweep_retention(seeded, settings) == 1
    assert sweep_retention(seeded, settings) == 0
    assert schedule_daily_sweep(seeded, settings) == schedule_daily_sweep(seeded, settings)
    for _ in range(5):
        if not run_once(seeded, settings):
            break
    with seeded.read_conn() as c:
        assert (
            c.execute("SELECT state FROM documents WHERE id='d'").fetchone()["state"] == "deleted"
        )


def test_backup_restore_integrity_content_and_pruning(seeded, tmp_path):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=tmp_path / "live",
        pathya_db_path=seeded.path,
        backup_dir=tmp_path / "backups",
    )
    store = FileStore(settings.pathya_data_dir, seeded, min_free_bytes=0)
    asset, _, _ = store.put_source("d", io.BytesIO(b"synthetic original"), 100)
    with seeded.write_tx() as c:
        c.execute("INSERT INTO sessions VALUES ('old-session','u','old-token','now','2099',NULL)")
    snapshot = create_backup(settings)
    restored_dir = tmp_path / "restored"
    restore_backup(snapshot, restored_dir)
    restored = Database(restored_dir / "pathya.sqlite3")
    migrate(restored, apply=False)
    with FileStore(restored_dir, restored, min_free_bytes=0).open_asset(asset, "u") as stream:
        assert stream.read() == b"synthetic original"
    with restored.read_conn() as c:
        assert (
            c.execute("SELECT text_current FROM blocks WHERE id='b'").fetchone()["text_current"]
            == "Synthetic text"
        )
        assert c.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"] == 0
    with pytest.raises(ValueError):
        restore_backup(snapshot, restored_dir)
    with pytest.raises(ValueError):
        restore_backup(snapshot, snapshot / "nested")
    marker = snapshot / "backup.json"
    metadata = json.loads(marker.read_text())
    metadata["created_at"] = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    marker.write_text(json.dumps(metadata))
    unrelated = settings.backup_dir / "personal-folder"
    unrelated.mkdir()
    assert prune_backups(settings) == 1
    assert not snapshot.exists() and unrelated.is_dir()
    settings.backup_dir = settings.pathya_data_dir / "inside"
    with pytest.raises(ValueError):
        create_backup(settings)


def test_reupload_waits_for_purge_then_creates_a_new_document(worker_client):
    client = worker_client
    first = upload(client, pdf_bytes(1)).json()
    assert client.delete("/documents/" + first["document_id"]).status_code == 202
    pending = upload(client, pdf_bytes(1))
    assert pending.status_code == 409 and pending.json()["code"] == "deletion_in_progress"
    assert run_once(client.app.state.database, client.app.state.settings)
    later = upload(client, pdf_bytes(1))
    assert later.status_code == 202 and later.json()["document_id"] != first["document_id"]


def test_deletion_during_upload_cannot_resurrect_the_document(worker_client, monkeypatch):
    client = worker_client
    database, settings = client.app.state.database, client.app.state.settings
    owner = client.get("/auth/me").json()["id"]
    original = FileStore.put_source
    receipts = []

    def delete_during_publication(self, document_id, *args, **kwargs):
        result = original(self, document_id, *args, **kwargs)
        receipts.append(request_delete(database, settings, document_id, owner))
        return result

    monkeypatch.setattr(FileStore, "put_source", delete_during_publication)
    response = upload(client, pdf_bytes(1))
    assert response.status_code == 404
    assert receipts and client.get(receipts[0]["status_url"]).json()["status"] == "pending"
    assert run_once(database, settings)
    assert client.get(receipts[0]["status_url"]).json()["status"] == "complete"
    assert client.get("/documents/" + receipts[0]["document_id"]).status_code == 404
