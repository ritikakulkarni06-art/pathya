import json
import sqlite3
from typing import Any

from app.schemas.content import Block, Edge, ExtractionResult, Page


def receipt(connection: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    row: dict[str, Any] | None = connection.execute(
        "SELECT * FROM extraction_imports WHERE document_id=?", (document_id,)
    ).fetchone()
    return row


def has_incomplete_p1_pages(connection: sqlite3.Connection, document_id: str) -> bool:
    return (
        connection.execute(
            """
        SELECT 1 FROM extraction_imports i,
        json_each(CAST(i.p1_source_json AS TEXT),'$.pages') p
        WHERE i.document_id=? AND json_extract(p.value,'$.status') IN ('needs_ocr','partial','failed')
        LIMIT 1
        """,
            (document_id,),
        ).fetchone()
        is not None
    )


def insert_revision(
    connection: sqlite3.Connection, document_id: str, author_id: str, now: str
) -> None:
    connection.execute(
        "INSERT INTO revisions VALUES (?,1,'initial',NULL,?,?)", (document_id, now, author_id)
    )


def insert_page(
    connection: sqlite3.Connection, document_id: str, page: Page, ids: dict[str, str]
) -> None:
    if page.source_asset_id is not None:
        source = connection.execute(
            "SELECT id FROM assets WHERE id=? AND document_id=? AND deleted_at IS NULL",
            (page.source_asset_id, document_id),
        ).fetchone()
        if source is None:
            raise ValueError("invalid_source_asset")
    connection.execute(
        "INSERT INTO pages VALUES (?,?,?,?,?,?,?,?,?)",
        (
            ids[page.id],
            document_id,
            page.pdf_index_0,
            page.printed_label,
            page.width,
            page.height,
            page.rotation,
            page.source_asset_id,
            json.dumps(page.transform),
        ),
    )


def insert_block(
    connection: sqlite3.Connection,
    document_id: str,
    block: Block,
    ids: dict[str, str],
    author_id: str,
    now: str,
) -> None:
    metadata = block.metadata.model_dump(mode="json")
    metadata["header_cell_ids"] = [ids[item] for item in block.metadata.header_cell_ids]
    metadata["caption_block_ids"] = [ids[item] for item in block.metadata.caption_block_ids]
    connection.execute(
        "INSERT INTO blocks(id,document_id,page_id,type,parent_id,order_key,bbox_json,text_raw,text_current,lang,revision,status,confidence_json,provenance_json,critical_flag,successor_ids_json,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)",
        (
            ids[block.id],
            document_id,
            ids[block.page_id],
            block.type,
            ids[block.parent_id] if block.parent_id else None,
            block.order_key,
            json.dumps(block.bbox),
            block.text_raw,
            block.text_current,
            block.lang,
            block.status,
            block.confidence.model_dump_json(),
            block.provenance.model_dump_json(),
            int(block.critical_flag),
            json.dumps([ids[item] for item in block.successor_ids]),
            json.dumps(metadata),
        ),
    )
    connection.execute(
        "INSERT INTO block_versions VALUES (?,1,1,?,'[]',?,?)",
        (ids[block.id], block.text_current, author_id, now),
    )


def insert_edge(
    connection: sqlite3.Connection, document_id: str, edge: Edge, ids: dict[str, str]
) -> None:
    connection.execute(
        "INSERT INTO edges VALUES (?,?,?,?)",
        (ids[edge.from_id], edge.relation, ids[edge.to_id], document_id),
    )


def finish_import(
    connection: sqlite3.Connection,
    document_id: str,
    result: ExtractionResult,
    digest: str,
    now: str,
    *,
    producer_json: bytes | None = None,
    producer_version: str | None = None,
    needs_review: bool = False,
) -> None:
    review = needs_review or any(
        block.critical_flag or block.status == "needs_review" for block in result.blocks
    )
    connection.execute(
        "UPDATE documents SET current_revision=1,state=?,updated_at=? WHERE id=?",
        ("review_required" if review else "building", now, document_id),
    )
    connection.execute(
        "INSERT INTO extraction_imports(document_id,schema_version,payload_sha256,metadata_json,created_at,p1_source_json) VALUES (?,?,?,?,?,?)",
        (
            document_id,
            producer_version or result.schema_version,
            digest,
            json.dumps(
                {"quality_flags": result.quality_flags, "parser_versions": result.parser_versions}
            ),
            now,
            producer_json,
        ),
    )


def identifier_map(connection: sqlite3.Connection, document_id: str) -> dict[str, str]:
    return {
        row["external_id"]: row["internal_id"]
        for row in connection.execute(
            "SELECT external_id,internal_id FROM extraction_identifiers WHERE document_id=?",
            (document_id,),
        )
    }


def insert_identifiers(
    connection: sqlite3.Connection, document_id: str, ids: dict[str, str]
) -> None:
    connection.executemany(
        "INSERT INTO extraction_identifiers VALUES (?,?,?)",
        [(document_id, external, internal) for external, internal in ids.items()],
    )
