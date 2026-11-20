import copy
import json
import sqlite3
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.db.repos import audit, jobs
from app.db.repos.extraction import has_incomplete_p1_pages
from app.errors import Problem
from app.schemas.content import BlockMetadata
from app.schemas.corrections import CorrectionRequest
from app.services.access import check_document

TEXT_TYPES = {"heading", "paragraph", "list_item", "caption"}


def _persist(
    connection: sqlite3.Connection,
    row: dict[str, Any],
    document_revision: int,
    author: str,
    operations: str,
    created: bool,
) -> None:
    if created:
        connection.execute(
            "INSERT INTO blocks(id,document_id,page_id,type,parent_id,order_key,bbox_json,text_raw,text_current,lang,revision,status,confidence_json,provenance_json,critical_flag,successor_ids_json,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(
                row[key]
                for key in (
                    "id",
                    "document_id",
                    "page_id",
                    "type",
                    "parent_id",
                    "order_key",
                    "bbox_json",
                    "text_raw",
                    "text_current",
                    "lang",
                    "revision",
                    "status",
                    "confidence_json",
                    "provenance_json",
                    "critical_flag",
                    "successor_ids_json",
                    "metadata_json",
                )
            ),
        )
    else:
        connection.execute(
            "UPDATE blocks SET type=?,parent_id=?,order_key=?,text_current=?,lang=?,revision=?,status=?,provenance_json=?,critical_flag=?,successor_ids_json=?,metadata_json=? WHERE id=?",
            tuple(
                row[key]
                for key in (
                    "type",
                    "parent_id",
                    "order_key",
                    "text_current",
                    "lang",
                    "revision",
                    "status",
                    "provenance_json",
                    "critical_flag",
                    "successor_ids_json",
                    "metadata_json",
                    "id",
                )
            ),
        )
    connection.execute(
        "INSERT INTO block_versions(block_id,revision,document_revision,text,ops_json,author_id,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            row["id"],
            row["revision"],
            document_revision,
            row["text_current"],
            operations,
            author,
            now_utc(),
        ),
    )


def _reading_rank(
    connection: sqlite3.Connection,
    block: dict[str, Any],
    parent_id: str | None,
    anchor_id: str,
    before: bool,
) -> float:
    anchor = connection.execute(
        "SELECT * FROM blocks WHERE id=? AND document_id=?", (anchor_id, block["document_id"])
    ).fetchone()
    if (
        anchor is None
        or anchor_id == block["id"]
        or anchor["page_id"] != block["page_id"]
        or anchor["parent_id"] != parent_id
        or json.loads(anchor["successor_ids_json"])
    ):
        raise Problem(
            422,
            "invalid_order",
            "Choose an active anchor on the same page and under the selected parent.",
        )
    parent = parent_id
    seen = {block["id"]}
    while parent:
        if parent in seen:
            raise Problem(
                422, "parent_cycle", "A passage cannot be placed inside itself or its descendants."
            )
        seen.add(parent)
        row = connection.execute(
            "SELECT * FROM blocks WHERE id=? AND document_id=?", (parent, block["document_id"])
        ).fetchone()
        if (
            row is None
            or row["page_id"] != block["page_id"]
            or json.loads(row["successor_ids_json"])
        ):
            raise Problem(422, "invalid_parent", "Choose an active parent on the same page.")
        parent = row["parent_id"]
    siblings = list(
        connection.execute(
            "SELECT id,order_key FROM blocks WHERE document_id=? AND page_id=? AND parent_id IS ? AND id<>? AND json_array_length(successor_ids_json)=0 ORDER BY order_key,id",
            (block["document_id"], block["page_id"], parent_id, block["id"]),
        )
    )
    index = next(index for index, item in enumerate(siblings) if item["id"] == anchor_id)
    if before:
        high = float(anchor["order_key"])
        low = float(siblings[index - 1]["order_key"]) if index else high - 2
    else:
        low = float(anchor["order_key"])
        high = float(siblings[index + 1]["order_key"]) if index + 1 < len(siblings) else low + 2
    value = (low + high) / 2
    if not low < value < high:
        raise Problem(
            409,
            "order_conflict",
            "These reading positions need reconciliation before another reorder.",
        )
    return value


def _structural(
    connection: sqlite3.Connection,
    block: dict[str, Any],
    operation: dict[str, Any],
    request: CorrectionRequest,
    changed: dict[str, dict[str, Any]],
    created: set[str],
) -> None:
    if (
        block["type"] not in TEXT_TYPES
        or connection.execute(
            "SELECT 1 FROM blocks WHERE parent_id=? LIMIT 1", (block["id"],)
        ).fetchone()
    ):
        raise Problem(
            422,
            "unsupported_structure",
            "Split and merge currently support text blocks without child blocks.",
        )
    if len(request.operations) != 1:
        raise Problem(
            422, "unsupported_combination", "Submit split or merge as a separate correction."
        )
    originals = [block]
    texts: list[str]
    if operation["op"] == "split":
        offsets = operation["at_offsets"]
        if offsets != sorted(set(offsets)) or offsets[-1] >= len(block["text_current"]):
            raise Problem(
                422,
                "invalid_split",
                "Choose unique increasing offsets inside the passage, measured in Unicode code points.",
            )
        positions = [0, *offsets, len(block["text_current"])]
        texts = [block["text_current"][a:b] for a, b in zip(positions, positions[1:], strict=False)]
    else:
        other = connection.execute(
            "SELECT * FROM blocks WHERE id=? AND document_id=?",
            (operation["with_block_id"], block["document_id"]),
        ).fetchone()
        expected = operation.get("with_base_revision") or request.base_revision
        if (
            other is None
            or other["id"] == block["id"]
            or other["page_id"] != block["page_id"]
            or other["parent_id"] != block["parent_id"]
            or other["type"] != block["type"]
            or other["lang"] != block["lang"]
            or json.loads(other["successor_ids_json"])
        ):
            raise Problem(
                422,
                "invalid_merge",
                "Choose another active passage with the same page, type, language and parent.",
            )
        if other["revision"] != expected:
            raise Problem(
                409,
                "merge_revision_conflict",
                "The second passage has changed. Supply its current with_base_revision.",
            )
        if connection.execute(
            "SELECT 1 FROM blocks WHERE parent_id=? LIMIT 1", (other["id"],)
        ).fetchone():
            raise Problem(
                422,
                "unsupported_structure",
                "A block with children cannot be merged as plain text.",
            )
        low, high = sorted([block["order_key"], other["order_key"]])
        if connection.execute(
            "SELECT 1 FROM blocks WHERE document_id=? AND page_id=? AND parent_id IS ? AND order_key>? AND order_key<? AND json_array_length(successor_ids_json)=0",
            (block["document_id"], block["page_id"], block["parent_id"], low, high),
        ).fetchone():
            raise Problem(422, "invalid_merge", "Only adjacent passages can be merged.")
        originals.append(other)
        originals.sort(key=lambda item: item["order_key"])
        texts = ["\n\n".join(item["text_current"] for item in originals)]
        changed[other["id"]] = other
    high_row = connection.execute(
        "SELECT min(order_key) AS rank FROM blocks WHERE document_id=? AND page_id=? AND parent_id IS ? AND order_key>? AND json_array_length(successor_ids_json)=0",
        (
            block["document_id"],
            block["page_id"],
            block["parent_id"],
            max(item["order_key"] for item in originals),
        ),
    ).fetchone()
    start = max(float(item["order_key"]) for item in originals)
    high_rank = float(high_row["rank"]) if high_row["rank"] is not None else start + 1
    successors = []
    for index, text in enumerate(texts, 1):
        successor = copy.deepcopy(block)
        successor.update(
            id=str(uuid4()),
            revision=0,
            text_raw=text,
            text_current=text,
            status="corrected",
            successor_ids_json="[]",
            order_key=start + (high_rank - start) * index / (len(texts) + 1),
        )
        if successor["order_key"] <= start or successor["order_key"] >= high_rank:
            raise Problem(
                409, "order_conflict", "The reading sequence needs reconciliation before splitting."
            )
        if operation["op"] == "merge":
            boxes = [json.loads(item["bbox_json"]) for item in originals]
            successor["bbox_json"] = json.dumps(
                [
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ]
            )
        created.add(successor["id"])
        changed[successor["id"]] = successor
        successors.append(successor["id"])
    for original in originals:
        original.update(
            status="unsupported", critical_flag=1, successor_ids_json=json.dumps(successors)
        )


def _apply(
    connection: sqlite3.Connection,
    block: dict[str, Any],
    request: CorrectionRequest,
    changed: dict[str, dict[str, Any]],
    created: set[str],
) -> bool:
    structural = False
    for item in request.operations:
        operation = item.model_dump(mode="json")
        kind = operation["op"]
        metadata = json.loads(block["metadata_json"])
        if kind == "replace_text":
            block.update(text_current=operation["text"], critical_flag=0)
        elif kind == "set_language":
            block["lang"] = operation["lang"]
        elif kind == "set_type":
            block["type"] = operation["type"]
            structural = True
        elif kind == "mark_reviewed":
            block.update(status="reviewed", critical_flag=0)
        elif kind == "set_alt_text":
            if block["type"] != "figure":
                raise Problem(
                    422, "invalid_operation", "Descriptions can be changed only on figure blocks."
                )
            metadata.update(
                alt_text_short=operation["short"], alt_text_extended=operation["extended"]
            )
        elif kind == "set_mathml":
            if block["type"] != "equation":
                raise Problem(
                    422, "invalid_operation", "MathML can be changed only on equation blocks."
                )
            metadata.update(
                mathml=operation["mathml"], spoken_fallback=operation["spoken_fallback"]
            )
        elif kind == "reorder":
            anchor = operation["before_block_id"] or operation["after_block_id"]
            block["order_key"] = _reading_rank(
                connection,
                block,
                operation["parent_id"],
                anchor,
                operation["before_block_id"] is not None,
            )
            block["parent_id"] = operation["parent_id"]
            structural = True
        elif kind in {"split", "merge"}:
            _structural(connection, block, operation, request, changed, created)
            structural = True
        elif kind == "set_table_headers":
            if block["type"] not in {"table", "table_cell"}:
                raise Problem(
                    422, "invalid_operation", "Header references require a table or table cell."
                )
            table_id = block["id"] if block["type"] == "table" else block["parent_id"]
            header_ids = operation["header_cell_ids"]
            if len(set(header_ids)) != len(header_ids):
                raise Problem(422, "invalid_headers", "Choose each header cell once.")
            for header_id in header_ids:
                header = connection.execute(
                    "SELECT * FROM blocks WHERE id=? AND document_id=?",
                    (header_id, block["document_id"]),
                ).fetchone()
                if (
                    header is None
                    or header["type"] != "table_cell"
                    or header["parent_id"] != table_id
                ):
                    raise Problem(422, "invalid_headers", "Headers must be cells in this table.")
            metadata["header_cell_ids"] = header_ids
            if block["type"] == "table":
                cells = list(
                    connection.execute(
                        "SELECT * FROM blocks WHERE document_id=? AND parent_id=? AND type='table_cell' AND json_array_length(successor_ids_json)=0 ORDER BY order_key,id",
                        (block["document_id"], table_id),
                    )
                )
                values = [cell for cell in cells if cell["id"] not in header_ids]
                if len(values) % len(header_ids):
                    raise Problem(
                        422,
                        "unsupported_table",
                        "Automatic header assignment supports complete rows under one header row only.",
                    )
                for index, cell in enumerate(values):
                    cell_metadata = json.loads(cell["metadata_json"])
                    cell_metadata["header_cell_ids"] = [header_ids[index % len(header_ids)]]
                    cell["metadata_json"] = json.dumps(cell_metadata)
                    changed[cell["id"]] = cell
            structural = True
        block["metadata_json"] = BlockMetadata.model_validate(metadata).model_dump_json()
    return structural


def _refresh_structure(
    connection: sqlite3.Connection, document_id: str, changed: dict[str, dict[str, Any]]
) -> None:
    rows = {
        row["id"]: row
        for row in connection.execute("SELECT * FROM blocks WHERE document_id=?", (document_id,))
    }
    rows.update(changed)
    successors = {
        key: json.loads(row["successor_ids_json"])
        for key, row in rows.items()
        if json.loads(row["successor_ids_json"])
    }
    active = {key: row for key, row in rows.items() if key not in successors}
    for row in active.values():
        metadata = json.loads(row["metadata_json"])
        modified = False
        for field in ("header_cell_ids", "caption_block_ids"):
            original = metadata.get(field, [])
            rewritten = [
                successor for item in original for successor in successors.get(item, [item])
            ]
            if original != rewritten:
                metadata[field] = rewritten
                modified = True
            for reference in rewritten:
                target = active.get(reference)
                expected = "table_cell" if field == "header_cell_ids" else "caption"
                if target is None or target["type"] != expected:
                    raise Problem(
                        422,
                        "unsupported_structure",
                        "Resolve the table or caption references before changing this block type.",
                    )
        if modified:
            row["metadata_json"] = json.dumps(metadata)
            changed[row["id"]] = row


def _rebuild_edges(connection: sqlite3.Connection, document_id: str) -> None:
    connection.execute(
        "DELETE FROM edges WHERE document_id=? AND relation IN ('contains','precedes','caption_of','header_for')",
        (document_id,),
    )
    rows = list(
        connection.execute(
            "SELECT * FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0 ORDER BY page_id,parent_id,order_key,id",
            (document_id,),
        )
    )
    previous: dict[tuple[str, str | None], str] = {}
    for row in rows:
        if row["parent_id"]:
            connection.execute(
                "INSERT OR IGNORE INTO edges VALUES (?,'contains',?,?)",
                (row["parent_id"], row["id"], document_id),
            )
        group = (row["page_id"], row["parent_id"])
        if group in previous:
            connection.execute(
                "INSERT OR IGNORE INTO edges VALUES (?,'precedes',?,?)",
                (previous[group], row["id"], document_id),
            )
        previous[group] = row["id"]
        metadata = json.loads(row["metadata_json"])
        if row["type"] == "table_cell":
            for header_id in metadata.get("header_cell_ids", []):
                connection.execute(
                    "INSERT OR IGNORE INTO edges VALUES (?,'header_for',?,?)",
                    (header_id, row["id"], document_id),
                )
        if row["type"] == "figure":
            for caption_id in metadata.get("caption_block_ids", []):
                connection.execute(
                    "INSERT OR IGNORE INTO edges VALUES (?,'caption_of',?,?)",
                    (caption_id, row["id"], document_id),
                )


def _cited_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {str(value["block_id"])} if "block_id" in value else set()
        for nested in value.values():
            found.update(_cited_ids(nested))
        return found
    if isinstance(value, list):
        return set().union(*(_cited_ids(item) for item in value)) if value else set()
    return set()


def _invalidate(
    connection: sqlite3.Connection, document_id: str, affected: set[str], structural: bool
) -> dict[str, int]:
    counts = {"audio": 0, "chunks": 0, "embeddings": 0, "answers": 0}
    for artifact in connection.execute(
        "SELECT * FROM artifacts WHERE document_id=? AND status<>'stale'", (document_id,)
    ).fetchall():
        dependencies = json.loads(artifact["dependency_revisions_json"])
        if set(dependencies) & affected or (
            structural and artifact["kind"] in {"package", "chunk_index", "embedding"}
        ):
            connection.execute(
                "UPDATE artifacts SET status='stale',stale_reason='content_corrected',updated_at=? WHERE id=?",
                (now_utc(), artifact["id"]),
            )
            counts["audio"] += int(artifact["kind"] == "audio_block")
    for chunk in connection.execute(
        "SELECT * FROM chunks WHERE document_id=? AND status='current'", (document_id,)
    ).fetchall():
        if structural or set(json.loads(chunk["block_ids_json"])) & affected:
            connection.execute(
                "UPDATE chunks SET status='stale',eligible=0 WHERE id=?", (chunk["id"],)
            )
            counts["chunks"] += 1
            counts["embeddings"] += connection.execute(
                "UPDATE chunk_embeddings SET status='stale' WHERE chunk_id=? AND status='current'",
                (chunk["id"],),
            ).rowcount
    for answer in connection.execute(
        "SELECT * FROM answers WHERE document_id=? AND status='current'", (document_id,)
    ).fetchall():
        if structural or _cited_ids(json.loads(answer["response_json"])) & affected:
            connection.execute("UPDATE answers SET status='stale' WHERE id=?", (answer["id"],))
            counts["answers"] += 1
    return counts


def correct_block(
    database: Database, settings: Settings, block_id: str, user_id: str, request: CorrectionRequest
) -> dict[str, Any]:
    conflict: dict[str, Any] | None = None
    result: dict[str, Any] = {}
    operations = json.dumps([item.model_dump(mode="json") for item in request.operations])
    try:
        with database.write_tx() as connection:
            block = connection.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
            if block is None:
                raise Problem(404, "block_not_found", "This passage is unavailable.")
            document = check_document(connection, block["document_id"], user_id, "reviewer")
            p1 = (
                connection.execute(
                    "SELECT 1 FROM extraction_imports WHERE document_id=? AND p1_source_json IS NOT NULL",
                    (block["document_id"],),
                ).fetchone()
                is not None
            )
            if p1 and (
                block["type"] not in {"heading", "paragraph", "list_item", "caption"}
                or any(
                    op.op not in {"replace_text", "set_language", "mark_reviewed"}
                    for op in request.operations
                )
            ):
                raise Problem(
                    422,
                    "p1_correction_unsupported",
                    "This chapter supports text, language, and review corrections on text passages.",
                )
            incomplete_page = p1 and (
                json.loads(block["provenance_json"]).get("parser") == "p1_incomplete_page"
            )
            if incomplete_page and any(op.op == "mark_reviewed" for op in request.operations):
                raise Problem(
                    422,
                    "page_review_required",
                    "Review the incomplete source page before approving this passage.",
                )
            if json.loads(block["successor_ids_json"]):
                raise Problem(
                    409,
                    "block_superseded",
                    "This historical passage has successor blocks. Review those blocks before editing.",
                )
            correction_id = str(uuid4())
            if block["revision"] != request.base_revision:
                connection.execute(
                    "INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?,NULL,'conflict')",
                    (
                        correction_id,
                        block["document_id"],
                        block_id,
                        request.base_revision,
                        operations,
                        user_id,
                        request.reason,
                        now_utc(),
                    ),
                )
                your_text = next(
                    (item.text for item in request.operations if item.op == "replace_text"), None
                )
                conflict = {
                    "current_revision": block["revision"],
                    "your_base": request.base_revision,
                    "current_text": block["text_current"],
                    "your_text": your_text,
                    "field_hints": [
                        "Compare both versions, reconcile the text, then retry with current_revision as base_revision."
                    ],
                }
            else:
                original_status = block["status"]
                original_critical = block["critical_flag"]
                block["status"] = "corrected"
                changed = {block_id: block}
                created: set[str] = set()
                structural = _apply(connection, block, request, changed, created)
                if p1 and (
                    incomplete_page
                    or (original_status == "needs_review" and block["status"] != "reviewed")
                ):
                    block.update(status="needs_review", critical_flag=original_critical)
                if structural:
                    _refresh_structure(connection, document["id"], changed)
                document_revision = int(document["current_revision"]) + 1
                for row in changed.values():
                    row["revision"] += 1
                    if row["status"] == "reviewed" and row["type"] == "equation":
                        metadata = json.loads(row["metadata_json"])
                        if not metadata.get("mathml") or not metadata.get("spoken_fallback"):
                            raise Problem(
                                422,
                                "needs_math_review",
                                "Review the equation markup and spoken fallback before marking it reviewed.",
                            )
                    if (
                        row["status"] == "reviewed"
                        and row["type"] == "figure"
                        and not json.loads(row["metadata_json"]).get("alt_text_short")
                    ):
                        raise Problem(
                            422,
                            "needs_description_review",
                            "Add a figure description before marking it reviewed.",
                        )
                    provenance = json.loads(row["provenance_json"])
                    provenance.update(reviewer=user_id, changed_at=now_utc())
                    row["provenance_json"] = json.dumps(provenance)
                    _persist(
                        connection,
                        row,
                        document_revision,
                        user_id,
                        operations,
                        row["id"] in created,
                    )
                for row in changed.values():
                    for successor_id in json.loads(row["successor_ids_json"]):
                        connection.execute(
                            "INSERT OR IGNORE INTO edges VALUES (?,'supersedes',?,?)",
                            (successor_id, row["id"], document["id"]),
                        )
                if structural:
                    _rebuild_edges(connection, document["id"])
                connection.execute(
                    "INSERT INTO revisions VALUES (?,?,'correction',?,?,?)",
                    (
                        document["id"],
                        document_revision,
                        document["current_revision"],
                        now_utc(),
                        user_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO corrections VALUES (?,?,?,?,?,?,?,?,?,'accepted')",
                    (
                        correction_id,
                        document["id"],
                        block_id,
                        request.base_revision,
                        operations,
                        user_id,
                        request.reason,
                        now_utc(),
                        document_revision,
                    ),
                )
                stale = _invalidate(connection, document["id"], set(changed), structural)
                pending = connection.execute(
                    "SELECT 1 FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0 AND (critical_flag=1 OR status='needs_review') LIMIT 1",
                    (document["id"],),
                ).fetchone()
                connection.execute(
                    "UPDATE documents SET current_revision=?,state=?,updated_at=? WHERE id=?",
                    (
                        document_revision,
                        "review_required"
                        if pending or has_incomplete_p1_pages(connection, document["id"])
                        else "building",
                        now_utc(),
                        document["id"],
                    ),
                )
                rebuild_id = jobs.enqueue(
                    connection,
                    document["id"],
                    "rebuild",
                    {"revision": document_revision, "block_ids": list(changed)},
                    settings.job_max_attempts,
                    document["id"] + ":" + str(document_revision) + ":rebuild",
                    now_utc(),
                )
                audit.record(
                    connection,
                    user_id,
                    "correction",
                    document["id"],
                    block_id,
                    now_utc(),
                    {
                        "revision": str(document_revision),
                        "operations": ",".join(item.op for item in request.operations),
                    },
                )
                result = {
                    "document_revision": document_revision,
                    "block_revision": block["revision"],
                    "stale": stale,
                    "rebuild_job_id": rebuild_id,
                    "successor_ids": json.loads(block["successor_ids_json"]),
                }
    except ValidationError:
        raise Problem(
            422,
            "invalid_correction",
            "The correction metadata is invalid. Check the markup and references.",
        ) from None
    if conflict is not None:
        raise Problem(
            409,
            "revision_conflict",
            "This passage changed while you were editing. Compare both versions before retrying.",
            extra=conflict,
        )
    return result
