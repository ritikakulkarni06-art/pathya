import json
import math
from typing import Any

from app.adapters.embeddings import E5Provider, EmbeddingProvider, cosine, unpack
from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.access import check_document
from app.services.retrieval.chunker import grams, words
from app.services.retrieval.eligibility import is_eligible


def search_snapshot(
    database: Database,
    settings: Settings,
    document_id: str,
    user_id: str,
    query: str,
    k: int = 5,
    block_scope: list[str] | None = None,
    *,
    neighbors: bool = False,
    embedder: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    if not query.strip() or len(query) > 2000 or not 1 <= k <= 20:
        raise Problem(
            422,
            "invalid_search",
            "Use a query of 1 to 2000 characters and a result limit from 1 to 20.",
        )
    query_words = words(query)
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        doc = check_document(connection, document_id, user_id)
        if not query_words:
            return {"document_revision": doc["current_revision"], "results": []}
        blocks = {
            b["id"]: b
            for b in connection.execute("SELECT * FROM blocks WHERE document_id=?", (document_id,))
        }
        pool = []
        for row in connection.execute(
            "SELECT c.*,m.dependency_revisions_json,m.markers_json,m.offsets_json FROM chunks c JOIN chunk_metadata m ON m.chunk_id=c.id WHERE c.document_id=? AND c.revision=? AND c.status='current' AND c.eligible=1",
            (document_id, doc["current_revision"]),
        ):
            deps = json.loads(row["dependency_revisions_json"])
            if not deps or (block_scope is not None and not set(deps).issubset(block_scope)):
                continue
            if all(bid in blocks and is_eligible(blocks[bid], rev) for bid, rev in deps.items()):
                pool.append(row)
        ids = [r["id"] for r in pool]
        expression = " OR ".join('"' + w.replace('"', '""') + '"' for w in query_words[:64])
        matches = {
            r["chunk_id"]
            for r in connection.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? AND document_id=? AND chunk_id IN (SELECT value FROM json_each(?))",
                (expression, document_id, json.dumps(ids)),
            )
        }
        lexical = []
        qgrams = grams(query)
        hindi = any(0x900 <= ord(c) <= 0x97F for c in query)
        for row in pool:
            text_words = words(row["text"] + " " + row["heading_context"])
            overlap = sum(min(text_words.count(w), 3) for w in query_words)
            lexical_score = overlap / max(1, len(query_words))
            if hindi:
                seen = {
                    r["gram"]
                    for r in connection.execute(
                        "SELECT gram FROM chunk_ngrams WHERE chunk_id=? AND gram IN (SELECT value FROM json_each(?))",
                        (row["id"], json.dumps(sorted(qgrams))),
                    )
                }
                lexical_score = max(lexical_score, len(seen) / max(1, len(qgrams)))
            if (
                row["id"] in matches
                or (hindi and lexical_score >= 0.3)
                or set(query_words) & set(words(row["heading_context"]))
            ):
                lexical.append((row["id"], lexical_score))
        lexical.sort(key=lambda x: (-x[1], x[0]))
        vector = []
        if settings.embeddings_enabled or embedder is not None:
            if embedder is None:
                assert settings.embedding_model_path is not None
                embedder = E5Provider(settings.embedding_model_path)
            qvector = embedder.encode([query], query=True)[0]
            for row in connection.execute(
                "SELECT chunk_id,vector FROM chunk_embeddings WHERE chunk_id IN (SELECT value FROM json_each(?)) AND model_id=? AND dim=384 AND status='current'",
                (json.dumps(ids), embedder.model_id),
            ):
                score = cosine(
                    qvector, unpack(row["vector"]), numpy=isinstance(embedder, E5Provider)
                )
                if math.isfinite(score) and score > 0:
                    vector.append((row["chunk_id"], score))
            vector.sort(key=lambda x: (-x[1], x[0]))
        scores: dict[str, float] = {}
        for ranking in [lexical, vector]:
            for rank, (cid, _) in enumerate(ranking, 1):
                scores[cid] = scores.get(cid, 0) + 1 / (60 + rank)
        by_id = {r["id"]: r for r in pool}
        result = []
        lexical_scores = dict(lexical)
        for cid in sorted(scores, key=lambda x: (-scores[x], x))[:k]:
            row = by_id[cid]
            deps = json.loads(row["dependency_revisions_json"])
            near: list[str] = []
            if neighbors:
                for edge in connection.execute(
                    "SELECT from_id,to_id FROM edges WHERE document_id=? AND relation='precedes' AND (from_id IN (SELECT value FROM json_each(?)) OR to_id IN (SELECT value FROM json_each(?)))",
                    (document_id, json.dumps(list(deps)), json.dumps(list(deps))),
                ):
                    near.extend(
                        bid
                        for bid in (edge["from_id"], edge["to_id"])
                        if bid not in deps
                        and bid in blocks
                        and (block_scope is None or bid in block_scope)
                        and is_eligible(blocks[bid])
                    )
            result.append(
                {
                    "id": cid,
                    "document_revision": doc["current_revision"],
                    "text": row["text"],
                    "heading_context": row["heading_context"],
                    "block_ids": list(deps),
                    "block_revisions": deps,
                    "page_refs": json.loads(row["page_refs_json"]),
                    "markers": json.loads(row["markers_json"]),
                    "offsets": json.loads(row["offsets_json"]),
                    "evidence": [
                        {
                            "block_id": bid,
                            "rev": rev,
                            "text": blocks[bid]["text_current"],
                            "page_id": blocks[bid]["page_id"],
                        }
                        for bid, rev in deps.items()
                    ],
                    "score": scores[cid],
                    "lexical_score": lexical_scores.get(cid, 0),
                    "neighbor_block_ids": sorted(set(near)),
                }
            )
        return {"document_revision": doc["current_revision"], "results": result}


def search(
    database: Database,
    settings: Settings,
    document_id: str,
    user_id: str,
    query: str,
    k: int = 5,
    block_scope: list[str] | None = None,
    *,
    neighbors: bool = False,
    embedder: EmbeddingProvider | None = None,
) -> list[dict[str, Any]]:
    snapshot = search_snapshot(
        database,
        settings,
        document_id,
        user_id,
        query,
        k,
        block_scope,
        neighbors=neighbors,
        embedder=embedder,
    )
    results: list[dict[str, Any]] = snapshot["results"]
    return results


def recall_at_5(results: list[dict[str, Any]], gold_block_ids: list[str]) -> tuple[int, int]:
    found = {bid for row in results[:5] for bid in row["block_ids"]}
    gold = set(gold_block_ids)
    return len(found & gold), len(gold)
