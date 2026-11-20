import copy
import json
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.db.connection import Database
from app.errors import Problem
from app.schemas.content import ExtractionResult
from app.services.manifests import assert_job_lease


def reconcile(existing: list[dict[str, Any]], result: ExtractionResult) -> dict[str, Any]:
    page_indexes = {page.id: page.pdf_index_0 for page in result.pages}
    used = set()
    matches = []
    unmatched = []
    for block in result.blocks:
        candidates = []
        for old in existing:
            if old["id"] in used or old["pdf_index_0"] != page_indexes[block.page_id]:
                continue
            a = json.loads(old["bbox_json"])
            b = block.bbox
            intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1])
            )
            union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
            geometry = intersection / union if union else 0
            text = SequenceMatcher(
                None, old["text_current"], block.text_current, autojunk=False
            ).ratio()
            if geometry >= 0.5 and (text >= 0.7 or old["status"] in {"corrected", "reviewed"}):
                candidates.append((geometry + text, old))
        candidates.sort(key=lambda item: (-item[0], item[1]["id"]))
        if not candidates or (
            len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 0.05
        ):
            unmatched.append(block.id)
            continue
        old = candidates[0][1]
        used.add(old["id"])
        protected = old["status"] in {"corrected", "reviewed"}
        matches.append(
            {
                "block_id": old["id"],
                "candidate_block_id": block.id,
                "action": "preserve_correction" if protected else "review_candidate",
                "text": old["text_current"] if protected else block.text_current,
            }
        )
    return {
        "matches": matches,
        "unmatched_candidate_ids": unmatched,
        "unmatched_existing_ids": [old["id"] for old in existing if old["id"] not in used],
        "requires_reconciliation": True,
    }


def propose_candidate(
    database: Database,
    document_id: str,
    result: ExtractionResult,
    *,
    lease: tuple[str, str] | None = None,
    producer_document: dict[str, Any] | None = None,
) -> str:
    with database.write_tx() as connection:
        assert_job_lease(connection, lease)
        if lease is not None:
            receipt = connection.execute(
                "SELECT id FROM reextraction_candidates WHERE job_id=?", (lease[0],)
            ).fetchone()
            if receipt is not None:
                return str(receipt["id"])
        document = connection.execute(
            "SELECT * FROM documents WHERE id=? AND state NOT IN ('deleting','deleted')",
            (document_id,),
        ).fetchone()
        if document is None:
            raise Problem(404, "document_not_found", "This document is unavailable.")
        existing = list(
            connection.execute(
                "SELECT blocks.*,pages.pdf_index_0 FROM blocks JOIN pages ON pages.id=blocks.page_id WHERE blocks.document_id=? AND json_array_length(successor_ids_json)=0",
                (document_id,),
            )
        )
        body = {
            "extraction": copy.deepcopy(result.model_dump(mode="json")),
            "reconciliation": reconcile(existing, result),
        }
        if producer_document is not None:
            body["producer_document"] = producer_document
        candidate_id = str(uuid4())
        connection.execute(
            "INSERT INTO reextraction_candidates(id,document_id,base_revision,proposed_revision,body_json,state,created_at,job_id) VALUES (?,?,?,?,?,'review_required',?,?)",
            (
                candidate_id,
                document_id,
                document["current_revision"],
                document["current_revision"] + 1,
                json.dumps(body),
                now_utc(),
                lease[0] if lease else None,
            ),
        )
        return candidate_id
