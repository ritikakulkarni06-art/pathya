import json
from uuid import uuid4

from app.adapters.embeddings import E5Provider, EmbeddingProvider, pack
from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.manifests import assert_job_lease
from app.services.retrieval.chunker import chunk_blocks, grams, tokens


def build_index(
    database: Database,
    settings: Settings,
    document_id: str,
    *,
    lease: tuple[str, str] | None = None,
    embedder: EmbeddingProvider | None = None,
) -> int:
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        doc = connection.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not doc or doc["state"] in {"deleting", "deleted"}:
            raise Problem(404, "document_not_found", "This document is unavailable.")
        revision = doc["current_revision"]
        blocks = list(
            connection.execute(
                "SELECT b.* FROM blocks b JOIN pages p ON p.id=b.page_id WHERE b.document_id=? AND json_array_length(b.successor_ids_json)=0 ORDER BY p.pdf_index_0,b.order_key,b.id",
                (document_id,),
            )
        )
        pages = {
            p["id"]: dict(p)
            for p in connection.execute(
                "SELECT id,pdf_index_0,printed_label FROM pages WHERE document_id=?", (document_id,)
            )
        }
        generated = chunk_blocks(blocks, pages)
        previous = list(
            connection.execute(
                "SELECT c.*,m.dependency_revisions_json,m.markers_json,m.offsets_json FROM chunks c JOIN chunk_metadata m ON m.chunk_id=c.id WHERE c.document_id=? ORDER BY c.revision DESC,c.id",
                (document_id,),
            )
        )
        embeddings = {
            (r["chunk_id"], r["model_id"]): r
            for r in connection.execute(
                "SELECT e.* FROM chunk_embeddings e JOIN chunks c ON c.id=e.chunk_id WHERE c.document_id=?",
                (document_id,),
            )
        }
    if settings.embeddings_enabled and embedder is None:
        assert settings.embedding_model_path is not None
        embedder = E5Provider(settings.embedding_model_path)
    prepared = []
    for chunk in generated:
        matching = next(
            (
                p
                for p in previous
                if p["text"] == chunk["text"]
                and p["heading_context"] == chunk["heading_context"]
                and json.loads(p["dependency_revisions_json"]) == chunk["dependencies"]
                and json.loads(p["offsets_json"]) == chunk["offsets"]
            ),
            None,
        )
        old = (
            matching
            if matching and matching["revision"] == revision and matching["status"] == "current"
            else None
        )
        chunk_id = old["id"] if old else str(uuid4())
        vector = None
        if embedder is not None:
            reusable = embeddings.get((matching["id"], embedder.model_id)) if matching else None
            if reusable is None:
                vector = pack(embedder.encode([chunk["heading_context"] + "\n" + chunk["text"]])[0])
            elif old is None or reusable["status"] != "current":
                vector = reusable["vector"]
        prepared.append((chunk_id, chunk, old, vector))
    with database.write_tx() as connection:
        assert_job_lease(connection, lease)
        current = connection.execute(
            "SELECT * FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if (
            not current
            or current["state"] in {"deleting", "deleted"}
            or current["current_revision"] != revision
        ):
            raise Problem(
                409,
                "stale_revision",
                "The chapter changed before indexing. Rebuild the current revision.",
            )
        keep = [p[0] for p in prepared]
        connection.execute(
            "UPDATE chunk_embeddings SET status='stale' WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id=? AND id NOT IN (SELECT value FROM json_each(?)))",
            (document_id, json.dumps(keep)),
        )
        connection.execute(
            "UPDATE chunks SET status='stale',eligible=0 WHERE document_id=? AND id NOT IN (SELECT value FROM json_each(?))",
            (document_id, json.dumps(keep)),
        )
        for chunk_id, chunk, old, vector in prepared:
            if old is None:
                connection.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,1,'current')",
                    (
                        chunk_id,
                        document_id,
                        revision,
                        json.dumps(list(chunk["dependencies"])),
                        chunk["heading_context"],
                        chunk["text"],
                        tokens(chunk["text"]),
                        json.dumps(chunk["page_refs"]),
                    ),
                )
                connection.execute(
                    "INSERT INTO chunk_metadata VALUES (?,?,?,?)",
                    (
                        chunk_id,
                        json.dumps(chunk["dependencies"]),
                        json.dumps(chunk["markers"]),
                        json.dumps(chunk["offsets"]),
                    ),
                )
                connection.executemany(
                    "INSERT INTO chunk_ngrams VALUES (?,?)",
                    [(chunk_id, g) for g in grams(chunk["text"] + " " + chunk["heading_context"])],
                )
            if vector is not None and embedder is not None:
                connection.execute(
                    "INSERT INTO chunk_embeddings(chunk_id,model_id,dim,vector,status) VALUES (?,?,384,?,'current') ON CONFLICT(chunk_id,model_id) DO UPDATE SET vector=excluded.vector,status='current'",
                    (chunk_id, embedder.model_id, vector),
                )
    return len(prepared)
