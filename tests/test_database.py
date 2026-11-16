import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.connection import Database
from app.db.migrate import MIGRATIONS, _statements, migrate
from app.db.repos import answers, assets, content, documents, jobs, users


def test_fresh_and_reapply(database):
    migrate(database)
    migrate(database, apply=False)
    with database.read_conn() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()["journal_mode"] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()["timeout"] == 5000
        assert conn.execute("SELECT count(*) AS n FROM schema_migrations").fetchone()["n"] == 1


def test_changed_and_missing_migration(database, tmp_path):
    directory = tmp_path / "migrations"
    directory.mkdir()
    original = MIGRATIONS / "001_initial.sql"
    (directory / original.name).write_bytes(original.read_bytes() + b"\n-- changed")
    with pytest.raises(ValueError, match="checksum"):
        migrate(database, directory)
    (directory / original.name).unlink()
    with pytest.raises(ValueError, match="missing"):
        migrate(database, directory)


def test_unapplied_readiness_and_rollback(tmp_path):
    db = Database(tmp_path / "fresh.sqlite3")
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001_bad.sql").write_text("CREATE TABLE before_failure(id TEXT);\nINVALID SQL;\n")
    with pytest.raises(sqlite3.OperationalError):
        migrate(db, directory)
    with db.read_conn() as conn:
        assert (
            conn.execute("SELECT name FROM sqlite_master WHERE name='before_failure'").fetchone()
            is None
        )
    with db.write_tx() as conn:
        conn.execute("CREATE TABLE schema_migrations(name TEXT, checksum TEXT)")
    with pytest.raises(ValueError, match="not been applied"):
        migrate(db, apply=False)
    with pytest.raises(ValueError, match="incomplete"):
        _statements("CREATE TABLE broken(id)")


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE block_versions SET text='tampered'",
        "DELETE FROM block_versions",
        "UPDATE manifests SET body_json='[]'",
        "DELETE FROM manifests",
    ],
)
def test_immutable_history(seeded, sql):
    with pytest.raises(sqlite3.IntegrityError):
        with seeded.write_tx() as conn:
            conn.execute(sql)


def test_foreign_keys_and_aggregate_reads(seeded):
    with pytest.raises(sqlite3.IntegrityError):
        with seeded.write_tx() as conn:
            conn.execute("INSERT INTO sessions VALUES ('s','missing','hash','now','later',NULL)")
    with seeded.write_tx() as conn:
        users.create(conn, "u2", "reader@example.test", None, "now")
        assert users.by_email(conn, "reader@example.test")["id"] == "u2"
        assert users.get_user(conn, "u")["role"] == "user"
        assert documents.get_document(conn, "d")["current_revision"] == 1
        assert documents.get_grant(conn, "d", "u2") is None
        assert content.get_block(conn, "b")["text_current"] == "Synthetic text"
        assert assets.get_asset(conn, "missing") is None
        assert jobs.get_job(conn, "missing") is None
        assert answers.get_answer(conn, "missing") is None


def test_fts_follows_eligibility_and_staleness(seeded):
    with seeded.write_tx() as conn:
        conn.execute(
            "INSERT INTO chunks VALUES ('c','d',1,'[\"b\"]','','photosynthesis',2,'[]',1,'current')"
        )
        assert (
            conn.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'photosynthesis'"
            ).fetchone()["chunk_id"]
            == "c"
        )
        conn.execute("UPDATE chunks SET status='stale',eligible=0 WHERE id='c'")
        assert conn.execute("SELECT * FROM chunks_fts").fetchall() == []
        conn.execute("UPDATE chunks SET status='current',eligible=1 WHERE id='c'")
        assert len(conn.execute("SELECT * FROM chunks_fts").fetchall()) == 1
        conn.execute("DELETE FROM chunks WHERE id='c'")
        assert conn.execute("SELECT * FROM chunks_fts").fetchall() == []


def test_concurrent_writes_serialize(database):
    entered = threading.Event()

    def first():
        with database.write_tx() as conn:
            users.create(conn, "u1", "one@example.test", None, "now")
            entered.set()
            time.sleep(0.15)

    def second():
        assert entered.wait(timeout=5)
        with database.write_tx() as conn:
            assert users.get_user(conn, "u1") is not None
            users.create(conn, "u2", "two@example.test", None, "now")

    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(first), pool.submit(second)]
        for task in tasks:
            task.result(timeout=10)
