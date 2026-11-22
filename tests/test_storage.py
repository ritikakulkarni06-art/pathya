import io

import pytest

from app.errors import Problem
from app.services.storage import FileStore


@pytest.fixture
def store(tmp_path, seeded):
    return FileStore(tmp_path / "private", seeded, min_free_bytes=0)


def test_dedupe_and_authorized_read(store):
    first = store.put_source("d", io.BytesIO(b"synthetic bytes"), 100)
    assert store.put_source("d", io.BytesIO(b"synthetic bytes"), 100) == first
    with store.open_asset(first[0], "u") as stream:
        assert stream.read() == b"synthetic bytes"
    with pytest.raises(Problem) as error:
        store.open_asset(first[0], "other")
    assert error.value.status == 404
    with store.database.read_conn() as connection:
        assert connection.execute("SELECT count(*) AS n FROM assets").fetchone()["n"] == 1


def test_derived_dedupes_and_delete_is_idempotent(store):
    store.put_source("d", io.BytesIO(b"source"), 100)
    derived = store.put_derived("d", "artifact", io.BytesIO(b"audio"), 100)
    assert store.put_derived("d", "artifact", io.BytesIO(b"audio"), 100) == derived
    removed = store.secure_delete_document("d")
    assert removed.files_removed == 2
    assert removed.bytes_removed == 11
    assert not removed.failures
    assert store.secure_delete_document("d").files_removed == 0


@pytest.mark.parametrize("identifier", ["..", "../outside", "a/b", r"a\b", "C:", "", "/absolute"])
def test_path_traversal(store, identifier):
    with pytest.raises(Problem, match="invalid_path"):
        store.put_source(identifier, io.BytesIO(b"x"), 1)


def test_symlink_escape(store, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (store.root / "sources").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit directory symlinks")
    with pytest.raises(Problem, match="invalid_path"):
        store.put_source("d", io.BytesIO(b"x"), 1)


def test_oversize_aborts_early_and_cleans_up(store):
    stream = io.BytesIO(b"x" * 100000)
    with pytest.raises(Problem, match="too_large"):
        store.put_source("d", stream, 10)
    assert stream.tell() == 11
    assert list((store.root / "tmp").iterdir()) == []
    assert not (store.root / "sources").exists()


def test_crashed_stream_leaves_no_visible_source(store):
    class BrokenStream(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("simulated interrupted stream")
            return super().read(2)

    with pytest.raises(OSError):
        store.put_source("d", BrokenStream(b"bytes"), 100)
    assert list((store.root / "tmp").iterdir()) == []
    assert not (store.root / "sources").exists()


def test_storage_full_and_database_failure(store, monkeypatch):
    store.min_free_bytes = 10**30
    with pytest.raises(Problem, match="storage_full"):
        store.put_source("d", io.BytesIO(b"x"), 10)
    store.min_free_bytes = 0
    with pytest.raises(Problem, match="document_not_found"):
        store.put_source("missing", io.BytesIO(b"x"), 10)
    assert list((store.root / "tmp").iterdir()) == []


def test_reader_grant_and_deleted_document(store):
    asset = store.put_source("d", io.BytesIO(b"x"), 10)
    with store.database.write_tx() as conn:
        conn.execute("INSERT INTO users VALUES ('reader','reader@example.test',NULL,'user','now')")
        conn.execute("INSERT INTO document_grants VALUES ('d','reader','reader','u','now')")
    with store.open_asset(asset[0], "reader") as stream:
        assert stream.read() == b"x"
    with store.database.write_tx() as conn:
        conn.execute("UPDATE documents SET state='deleting' WHERE id='d'")
    with pytest.raises(Problem, match="document_not_found"):
        store.open_asset(asset[0], "u")


def test_database_write_failure_removes_published_file(store):
    import sqlite3

    with store.database.write_tx() as conn:
        conn.execute(
            "CREATE TRIGGER injected_asset_failure BEFORE INSERT ON assets BEGIN SELECT RAISE(ABORT,'injected failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store.put_source("d", io.BytesIO(b"never published"), 100)
    assert list((store.root / "sources" / "d").iterdir()) == []
    assert list((store.root / "tmp").iterdir()) == []
