import json
import sqlite3
from typing import Any
from uuid import UUID, uuid5

from app.db.repos.extraction import identifier_map, receipt
from app.schemas import content
from app.schemas.p1.geometry import SourceCoordinateSpace
from app.schemas.p1.models import Document, Page, Provenance, ReviewStatus, export_document_data

INCOMPLETE_STATES = {"needs_ocr", "partial", "failed"}
REVIEW_FLAGS = {
    "reading_order_uncertain",
    "math_needs_review",
    "table_structure_uncertain",
    "missing_geometry",
    "geometry_uncertain",
    "orphan_caption",
    "overlapping_regions",
    "duplicate_content",
    "block_type_uncertain",
    "unsupported_content",
    "low_confidence",
    "possible_ocr_error",
    "critical_symbol_uncertain",
}


def _affine(page: Page) -> tuple[float, float, float, float, float, float]:
    x0, y0, x1, y1 = page.transform.crop_box
    w, h = x1 - x0, y1 - y0
    rotation = page.transform.rotation_applied
    a, b, c, d, x, y = {
        0: (w, 0.0, 0.0, h, x0, y0),
        90: (0.0, -h, w, 0.0, x0, y1),
        180: (-w, 0.0, 0.0, -h, x1, y1),
        270: (0.0, h, -w, 0.0, x1, y0),
    }[rotation]
    if page.transform.source_space == SourceCoordinateSpace.PDF_USER_SPACE:
        return a, -b, c, -d, x, y0 + y1 - y
    return a, b, c, d, x, y


def _provenance(producer: Provenance, *, incomplete: bool) -> content.Provenance:
    return content.Provenance(
        parser="p1_incomplete_page" if incomplete else "p1",
        model=producer.model[:128] if producer.model else None,
        version=(producer.engine_version or "1.1.0")[:128],
        reviewer=None,
        changed_at=producer.created_at,
    )


def project_p1(document: Document, source_asset_id: str) -> content.ExtractionResult:
    """Project fields needed by existing jobs. The complete producer JSON is stored separately."""
    pages = [
        content.Page(
            id=str(page.id),
            pdf_index_0=page.page_index,
            printed_label=(page.page_label or "Printed label unavailable")[:64],
            width=page.width,
            height=page.height,
            rotation=page.rotation.value,
            source_asset_id=source_asset_id,
            transform=_affine(page),
        )
        for page in document.pages
    ]
    page_states = {page.id: page.status for page in document.pages}
    by_id = {block.id: block for block in document.blocks}
    review_ids = {
        block.id
        for block in document.blocks
        if REVIEW_FLAGS.intersection(block.quality_flags)
        or block.review_status in {ReviewStatus.NEEDS_REVIEW, ReviewStatus.REJECTED}
    }
    blocks = []
    for block in document.blocks:
        incomplete = page_states[block.page_id] in INCOMPLETE_STATES
        metadata = content.BlockMetadata()
        if block.table_cell and block.parent_id is not None:
            metadata.header_cell_ids = [
                str(item)
                for item in block.table_cell.header_cell_ids
                if by_id[item].parent_id == block.parent_id
            ]
        parent = block.table_cell.table_id if block.table_cell else block.parent_id
        review = incomplete or block.id in review_ids or parent in review_ids
        score = block.confidence.score
        text = block.current_text or ""
        language = project_language(block.language, text)
        blocks.append(
            {
                "id": str(block.id),
                "page_id": str(block.page_id),
                "type": block.block_type,
                "parent_id": str(block.parent_id) if block.parent_id else None,
                "order_key": block.reading_order,
                "bbox": block.bbox,
                "text_raw": block.raw_text or "",
                "text_current": text,
                "lang": language,
                "status": "needs_review" if review else "not_scored" if score is None else "ok",
                "confidence": {
                    "engine": (block.provenance.engine or "p1")[:128],
                    "score": score,
                    "flags": block.quality_flags,
                },
                "provenance": _provenance(block.provenance, incomplete=incomplete),
                "critical_flag": "critical_symbol_uncertain" in block.quality_flags,
                "metadata": metadata,
            }
        )
    edges = {
        (str(edge.source_id), edge.edge_type.value, str(edge.target_id)) for edge in document.edges
    }
    return content.parse_extraction(
        {
            "schema_version": "1.0.0",
            "pages": pages,
            "blocks": blocks,
            "edges": [
                {"from_id": left, "relation": kind, "to_id": right}
                for left, kind, right in sorted(edges)
            ],
            "quality_flags": sorted(
                {flag for block in document.blocks for flag in block.quality_flags}
            ),
            "parser_versions": {"p1": document.schema_version},
        }
    )


def canonical_content(
    connection: sqlite3.Connection, document_id: str, rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    imported = receipt(connection, document_id)
    if imported is None or imported["p1_source_json"] is None:
        return None
    original = Document.model_validate_json(imported["p1_source_json"])
    body = original.model_dump(mode="json")
    ids = identifier_map(connection, document_id)
    current = {row["id"]: row for row in rows}
    source = connection.execute(
        "SELECT id FROM assets WHERE document_id=? AND kind='source' AND deleted_at IS NULL",
        (document_id,),
    ).fetchone()
    assert source is not None
    body["id"] = document_id
    body["source_asset"].update(id=source["id"], uri=f"/assets/{source['id']}")
    for page in body["pages"]:
        page.update(id=ids[page["id"]], document_id=document_id, source_asset_id=source["id"])
    for block in body["blocks"]:
        row = current[ids[block["id"]]]
        block.update(id=row["id"], page_id=row["page_id"], parent_id=row["parent_id"])
        if row["revision"] > 1:
            block["revision"] = row["revision"]
            if block["current_text"] is not None:
                block["current_text"] = row["text_current"]
            block["review_status"] = {
                "needs_review": "needs_review",
                "reviewed": "approved",
            }.get(row["status"], "unreviewed")
        if block["table"]:
            block["table"]["cell_ids"] = [ids[item] for item in block["table"]["cell_ids"]]
        if block["table_cell"]:
            cell = block["table_cell"]
            cell["table_id"] = ids[cell["table_id"]]
            cell["header_cell_ids"] = [ids[item] for item in cell["header_cell_ids"]]
        if block["figure"] and block["figure"]["caption_block_id"]:
            block["figure"]["caption_block_id"] = ids[block["figure"]["caption_block_id"]]
        if block["equation"]:
            block["equation"]["source_crop_uri"] = None
    for edge in body["edges"]:
        edge.update(source_id=ids[edge["source_id"]], target_id=ids[edge["target_id"]])
    _add_corrections(connection, document_id, body)
    return export_document_data(Document.model_validate(body), original.schema_version)


def project_language(language: str, text: str) -> str:
    if language in {"en", "hi"}:
        return language
    hindi = sum("\u0900" <= char <= "\u097f" for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return "hi" if hindi > latin else "en"


def _add_corrections(
    connection: sqlite3.Connection, document_id: str, body: dict[str, Any]
) -> None:
    changes = connection.execute(
        "SELECT * FROM corrections WHERE document_id=? AND state='accepted' ORDER BY accepted_revision,id",
        (document_id,),
    )
    blocks = {block["id"]: block for block in body["blocks"]}
    for change in changes:
        for index, op in enumerate(json.loads(change["operations_json"])):
            if op["op"] == "replace_text":
                payload = {"operation": "replace_text", "new_text": op["text"]}
            elif op["op"] == "set_language":
                payload = {"operation": "set_language", "new_language": op["lang"]}
                blocks[change["block_id"]]["language"] = op["lang"]
            else:
                payload = {"operation": "set_review_status", "new_review_status": "approved"}
            body["corrections"].append(
                {
                    "id": change["id"]
                    if index == 0
                    else str(uuid5(UUID(change["id"]), str(index))),
                    "document_id": document_id,
                    "block_id": change["block_id"],
                    "base_revision": change["base_revision"],
                    "reason": change["reason"],
                    "created_at": change["created_at"],
                    **payload,
                }
            )
