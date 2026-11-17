import json

import pytest

from app.adapters.embeddings import E5Provider, FakeEmbeddingProvider, pack, unpack
from app.errors import Problem
from app.services.retrieval.chunker import chunk_blocks, tokens
from app.services.retrieval.eligibility import is_eligible
from app.services.retrieval.evaluation import recall_at_five
from app.services.retrieval.index import build_index
from app.services.retrieval.search import search
from app.worker.runner import run_once
from tests.test_jobs import worker_client as worker_client
from tests.test_revisions import chapter as chapter
from tests.test_revisions import edit


@pytest.mark.parametrize(
    "status,critical,expected",
    [
        ("ok", 0, True),
        ("corrected", 0, True),
        ("reviewed", 0, True),
        ("not_scored", 0, True),
        ("needs_review", 0, False),
        ("unsupported", 0, False),
        ("reviewed", 1, False),
        ("ok", 1, False),
    ],
)
def test_eligibility(status, critical, expected):
    b = {"id": "b", "type": "paragraph", "status": status, "critical_flag": critical, "revision": 2}
    assert is_eligible(b, 2) is expected
    assert not is_eligible(b, 1)
    assert not is_eligible({**b, "origin": "ai_explanation"}, 2)
    assert not is_eligible({**b, "successor_ids": ["next"]}, 2)
    assert not is_eligible({**b, "type": "equation", "status": "not_scored"}, 2)
    assert not is_eligible({**b, "type": "figure", "status": "ok"}, 2)


def setup_index(chapter, embedder=None):
    client, ids, mapping = chapter
    db, settings = client.app.state.database, client.app.state.settings
    count = build_index(db, settings, ids["document_id"], embedder=embedder)
    return client, ids, mapping, db, settings, count


def test_structured_rows_reviewed_media_and_idempotent_index(chapter):
    client, ids, mapping, db, settings, count = setup_index(chapter)
    assert count > 5
    with db.read_conn() as c:
        rows = list(
            c.execute("SELECT c.*,m.* FROM chunks c JOIN chunk_metadata m ON c.id=m.chunk_id")
        )
        row = next(r for r in rows if mapping["cell-count"] in json.loads(r["block_ids_json"]))
        assert mapping["header-count"] in json.loads(row["block_ids_json"])
        assert mapping["cell-kind"] in json.loads(row["block_ids_json"])
        assert "Count" in row["text"] and "Bean" in row["text"]
        assert all(mapping["damaged-minus"] not in json.loads(r["block_ids_json"]) for r in rows)
        assert any(mapping["equation-1"] in json.loads(r["block_ids_json"]) for r in rows)
        assert any(mapping["figure-1"] in json.loads(r["block_ids_json"]) for r in rows)
        assert any("not_scored" in json.loads(r["markers_json"]) for r in rows)
        before = {r["id"] for r in rows}
    assert build_index(db, settings, ids["document_id"]) == count
    with db.read_conn() as c:
        assert {r["id"] for r in c.execute("SELECT id FROM chunks")} == before


@pytest.mark.parametrize("vector", [False, True])
def test_hindi_retrieval_revision_and_scope(chapter, vector):
    embedder = FakeEmbeddingProvider() if vector else None
    client, ids, mapping, db, settings, count = setup_index(chapter, embedder)
    owner = client.get("/auth/me").json()["id"]
    query = "\u092a\u094d\u0930\u0915\u093e\u0936"
    results = search(db, settings, ids["document_id"], owner, query, embedder=embedder)
    assert results
    assert any(mapping["paragraph-7"] in r["block_ids"] for r in results)
    assert all(r["document_revision"] == 1 for r in results)
    assert (
        client.get("/documents/" + ids["document_id"] + "/search", params={"q": query}).status_code
        == 200
    )
    assert not search(db, settings, ids["document_id"], owner, query, block_scope=["not-a-block"])
    response = edit(client, mapping["paragraph-7"], 1, "Unique corrected synthetic lunar phrase.")
    assert response.status_code == 200
    assert search(db, settings, ids["document_id"], owner, query, embedder=embedder) == []
    assert run_once(db, settings)
    current = search(db, settings, ids["document_id"], owner, "lunar")
    assert current and current[0]["document_revision"] == 2
    assert any(
        e["rev"] == 2 for e in current[0]["evidence"] if e["block_id"] == mapping["paragraph-7"]
    )
    with db.read_conn() as c:
        assert (
            c.execute(
                "SELECT COUNT(*) n FROM chunks_fts WHERE chunk_id IN (SELECT id FROM chunks WHERE status='stale')"
            ).fetchone()["n"]
            == 0
        )


def test_cross_document_and_user_filtered_before_ranking(chapter):
    client, ids, mapping, db, settings, count = setup_index(chapter, FakeEmbeddingProvider())
    owner = client.get("/auth/me").json()["id"]
    with db.write_tx() as c:
        c.execute("INSERT INTO users VALUES ('other','other@example.test',NULL,'user','now')")
        c.execute(
            "INSERT INTO documents SELECT 'otherdoc','other',title,'othersha',rights_note,languages_json,current_revision,state,retention_until,created_at,updated_at,deleted_at FROM documents WHERE id=?",
            (ids["document_id"],),
        )
        c.execute("INSERT INTO revisions VALUES ('otherdoc',1,'initial',NULL,'now','other')")
        c.execute(
            "INSERT INTO chunks VALUES ('foreign','otherdoc',1,'[]','','sunlight private textbook',3,'[]',1,'current')"
        )
        c.execute("INSERT INTO chunk_metadata VALUES ('foreign','{}','[]','[]')")
    with pytest.raises(Problem, match="document_not_found"):
        search(
            db, settings, ids["document_id"], "other", "sunlight", embedder=FakeEmbeddingProvider()
        )
    with pytest.raises(Problem, match="document_not_found"):
        search(db, settings, ids["document_id"], "other", "!!!")
    with pytest.raises(Problem, match="document_not_found"):
        search(db, settings, "otherdoc", owner, "sunlight")
    assert all(
        r["id"] != "foreign"
        for r in search(
            db, settings, ids["document_id"], owner, "sunlight", embedder=FakeEmbeddingProvider()
        )
    )


def test_long_paragraph_bounded_exact_offsets_and_heading_dependency(chapter):
    client, ids, mapping, db, settings, count = setup_index(chapter)
    with db.read_conn() as c:
        b = dict(c.execute("SELECT * FROM blocks WHERE id=?", (mapping["column-left"],)).fetchone())
        page = dict(
            c.execute(
                "SELECT id,pdf_index_0,printed_label FROM pages WHERE id=?", (b["page_id"],)
            ).fetchone()
        )
    b["text_current"] = "alpha beta gamma delta " * 600
    chunks = chunk_blocks([b], {b["page_id"]: page})
    assert len(chunks) > 5 and all(tokens(r["text"]) <= 350 for r in chunks)
    for chunk in chunks:
        o = chunk["offsets"][0]
        assert chunk["text"] == b["text_current"][o["start"] : o["end"]]


def test_embedding_shape_prefixes_offline_and_recall(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = []

    class Model:
        tokenizer = SimpleNamespace(encode=lambda text, **kw: [1] * 10)

        def __init__(self, path, **kwargs):
            calls.append(kwargs)

        def get_sentence_embedding_dimension(self):
            return 384

        def encode(self, texts, **kwargs):
            calls.append(texts)
            return SimpleNamespace(tolist=lambda: [[0.0] * 384 for _ in texts])

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model)
    )
    provider = E5Provider(tmp_path)
    provider.encode(["hello"])
    provider.encode(["hello"], query=True)
    assert calls[0]["local_files_only"] is True and calls[0]["trust_remote_code"] is False
    assert calls[1] == ["passage: hello"] and calls[2] == ["query: hello"]
    vector = FakeEmbeddingProvider().encode(["hello"])[0]
    assert len(pack(vector)) == 1536 and len(unpack(pack(vector))) == 384
    with pytest.raises(Problem, match="invalid_embedding"):
        pack([1.0])
    questions = tmp_path / "q.jsonl"
    questions.write_text(json.dumps({"question": "hello", "gold_block_ids": ["a", "b"]}) + "\n")
    assert recall_at_five(questions, lambda q: ["a"]) == {"found": 1, "gold": 2, "recall_at_5": 0.5}


@pytest.mark.parametrize("vectors", [False, True])
def test_index_table_hindi_idempotency_and_staleness(chapter, vectors):
    client, ids, mapping = chapter
    db, settings = client.app.state.database, client.app.state.settings
    owner = client.get("/auth/me").json()["id"]
    embedder = FakeEmbeddingProvider() if vectors else None
    count = build_index(db, settings, ids["document_id"], embedder=embedder)
    with db.read_conn() as c:
        before = {r["id"] for r in c.execute("SELECT id FROM chunks WHERE status='current'")}
    assert count > 5
    assert build_index(db, settings, ids["document_id"], embedder=embedder) == count
    with db.read_conn() as c:
        assert before == {
            r["id"] for r in c.execute("SELECT id FROM chunks WHERE status='current'")
        }
        table_chunks = [
            json.loads(r["block_ids_json"])
            for r in c.execute("SELECT block_ids_json FROM chunks")
            if mapping["cell-count"] in json.loads(r["block_ids_json"])
        ]
        assert table_chunks and all(
            mapping["header-count"] in row and mapping["cell-kind"] in row for row in table_chunks
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM chunk_metadata WHERE markers_json LIKE '%not_scored%'"
            ).fetchone()["n"]
            > 0
        )
    query = "\u092a\u094d\u0930\u0915\u093e\u0936"
    result = search(db, settings, ids["document_id"], owner, query, embedder=embedder)
    assert result
    assert any(mapping["paragraph-7"] in row["block_ids"] for row in result)
    assert not any(mapping["damaged-minus"] in row["block_ids"] for row in result)
    assert (
        client.get(
            "/documents/" + ids["document_id"] + "/search", params={"q": "sunlight"}
        ).status_code
        == 200
    )
    result = search(db, settings, ids["document_id"], owner, "sunlight", embedder=embedder)
    assert any(mapping["column-left"] in row["block_ids"] for row in result)
    assert (
        edit(client, mapping["column-left"], 1, "Verified new chlorophyll passage.").status_code
        == 200
    )
    assert not search(db, settings, ids["document_id"], owner, "sunlight", embedder=embedder)
    assert run_once(db, settings)
    result = search(db, settings, ids["document_id"], owner, "chlorophyll", embedder=embedder)
    assert result and result[0]["document_revision"] == 2
    assert result[0]["block_revisions"][mapping["column-left"]] == 2


def test_another_document_with_identical_text_cannot_enter_rankings(chapter):
    from tests.test_uploads import pdf_bytes, upload

    client, ids, mapping = chapter
    db, settings = client.app.state.database, client.app.state.settings
    owner = client.get("/auth/me").json()["id"]
    build_index(db, settings, ids["document_id"])
    other = upload(client, pdf_bytes(10)).json()
    # Same bytes dedupe for one owner; use another user to exercise real isolation.
    assert other["document_id"] == ids["document_id"]
    with db.write_tx() as c:
        c.execute("INSERT INTO users VALUES ('other','other@test.invalid',NULL,'user','now')")
        c.execute(
            "INSERT INTO documents VALUES ('foreign','other','Other','other-sha','synthetic','[]',1,'ready','later','now','now',NULL)"
        )
        c.execute("INSERT INTO revisions VALUES ('foreign',1,'initial',NULL,'now','other')")
        c.execute(
            "INSERT INTO chunks VALUES ('foreign-chunk','foreign',1,'[]','','sunlight sunlight sunlight',4,'[]',1,'current')"
        )
        c.execute("INSERT INTO chunk_metadata VALUES ('foreign-chunk','{}','[]','[]')")
    assert all(
        row["id"] != "foreign-chunk"
        for row in search(db, settings, ids["document_id"], owner, "sunlight")
    )
    with pytest.raises(Problem, match="document_not_found"):
        search(db, settings, "foreign", owner, "sunlight")


def test_unchanged_embeddings_reused_across_document_revisions(chapter):
    class Counting(FakeEmbeddingProvider):
        calls = 0

        def encode(self, texts, **kwargs):
            self.calls += len(texts)
            return super().encode(texts, **kwargs)

    client, ids, mapping = chapter
    db, settings = client.app.state.database, client.app.state.settings
    provider = Counting()
    count = build_index(db, settings, ids["document_id"], embedder=provider)
    assert provider.calls == count
    assert edit(client, mapping["paragraph-7"], 1, "New reviewed lunar pigment.").status_code == 200
    provider.calls = 0
    build_index(db, settings, ids["document_id"], embedder=provider)
    assert 0 < provider.calls < count
    job = client.post("/documents/" + ids["document_id"] + "/reindex")
    assert job.status_code == 202 and job.json()["job_id"]


def test_unchanged_vectors_reused_after_another_block_changes(chapter):
    class CountingEmbeddings(FakeEmbeddingProvider):
        def __init__(self):
            self.calls = 0

        def encode(self, texts, *, query=False):
            self.calls += len(texts)
            return super().encode(texts, query=query)

    client, ids, mapping = chapter
    db, settings = client.app.state.database, client.app.state.settings
    embedder = CountingEmbeddings()
    count = build_index(db, settings, ids["document_id"], embedder=embedder)
    assert embedder.calls == count
    build_index(db, settings, ids["document_id"], embedder=embedder)
    assert embedder.calls == count
    assert (
        edit(client, mapping["column-left"], 1, "Synthetic chlorophyll correction.").status_code
        == 200
    )
    build_index(db, settings, ids["document_id"], embedder=embedder)
    assert 0 < embedder.calls - count < count
    with db.read_conn() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM chunks WHERE status='stale'").fetchone()["n"]
            >= count
        )


def test_neighbors_respect_block_scope(seeded, tmp_path):
    from app.config import Settings

    settings = Settings(_env_file=None, pathya_data_dir=tmp_path)
    with seeded.write_tx() as c:
        c.execute(
            "INSERT INTO blocks SELECT 'neighbor',document_id,page_id,type,parent_id,2,bbox_json,text_raw,text_current,lang,revision,status,confidence_json,provenance_json,critical_flag,successor_ids_json,metadata_json FROM blocks WHERE id='b'"
        )
        c.execute("INSERT INTO edges VALUES ('b','precedes','neighbor','d')")
    build_index(seeded, settings, "d")
    # Both passages share a chunk, so explicitly index just b to isolate neighbor expansion.
    with seeded.write_tx() as c:
        c.execute("UPDATE chunks SET status='stale',eligible=0 WHERE document_id='d'")
        c.execute(
            "INSERT INTO chunks VALUES ('scoped','d',1,'[\"b\"]','','Synthetic text',2,'[]',1,'current')"
        )
        c.execute("INSERT INTO chunk_metadata VALUES ('scoped','{\"b\":1}','[]','[]')")
    unscoped = search(seeded, settings, "d", "u", "Synthetic", neighbors=True)
    assert unscoped[0]["neighbor_block_ids"] == ["neighbor"]
    scoped = search(seeded, settings, "d", "u", "Synthetic", block_scope=["b"], neighbors=True)
    assert scoped and scoped[0]["neighbor_block_ids"] == []


def test_api_revision_comes_from_search_snapshot(seeded, worker_client, monkeypatch):
    from app.api import search as search_api
    from app.services.auth import current_user

    worker_client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    original = search_api.search_snapshot

    def correct_between_authorization_and_search(*args, **kwargs):
        assert edit(worker_client, "b", 1, "Updated source passage.").status_code == 200
        return original(*args, **kwargs)

    monkeypatch.setattr(search_api, "search_snapshot", correct_between_authorization_and_search)
    response = worker_client.get("/documents/d/search", params={"q": "Synthetic"})
    assert response.status_code == 200
    assert response.json() == {"document_revision": 2, "results": []}
