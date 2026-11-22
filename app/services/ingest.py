import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.adapters.p1 import validate_p1_initial_import
from app.clock import now_utc
from app.db.connection import Database
from app.db.repos import documents, extraction
from app.errors import Problem
from app.schemas.content import ExtractionResult, parse_extraction
from app.services.jobs import LeaseLost
from app.services.p1_content import INCOMPLETE_STATES, project_p1


@dataclass(frozen=True)
class ImportResult:
    document_revision: int
    id_map: dict[str, str]


def import_extraction(
    database: Database,
    document_id: str,
    result: ExtractionResult | dict[str, Any] | bytes,
    *,
    lease: tuple[str, str] | None = None,
) -> ImportResult:
    try:
        with database.write_tx() as connection:
            if lease is not None:
                active = connection.execute(
                    "SELECT * FROM jobs WHERE id=? AND lease_owner=?", lease
                ).fetchone()
                if (
                    active is None
                    or active["state"] not in {"extracting", "building"}
                    or active["lease_expires_at"] <= now_utc()
                ):
                    raise LeaseLost()
            document = documents.get_document(connection, document_id)
            if document is None or document["state"] in {"deleting", "deleted"}:
                raise Problem(404, "document_not_found", "This document is unavailable.")
            producer_json = result if isinstance(result, bytes) else None
            producer_version: str | None = None
            needs_review = False
            if isinstance(result, bytes):
                source = connection.execute(
                    "SELECT id,sha256,mime FROM assets WHERE document_id=? AND kind='source' AND deleted_at IS NULL",
                    (document_id,),
                ).fetchone()
                if source is None or source["sha256"] != document["source_sha256"]:
                    raise Problem(
                        422, "invalid_source_asset", "The original chapter file is unavailable."
                    )
                parsed = validate_p1_initial_import(result, source["sha256"])
                if parsed.document.source_asset.media_type != source["mime"]:
                    raise Problem(
                        422, "invalid_source_asset", "Extraction refers to a different source type."
                    )
                validated = project_p1(parsed.document, source["id"])
                producer_version = parsed.document.schema_version
                needs_review = any(
                    page.status in INCOMPLETE_STATES for page in parsed.document.pages
                )
                digest = hashlib.sha256(result).hexdigest()
            else:
                validated = parse_extraction(result)
                encoded = json.dumps(
                    validated.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                )
                digest = hashlib.sha256(encoded.encode()).hexdigest()
            existing = extraction.receipt(connection, document_id)
            if existing is not None and existing["payload_sha256"] == digest:
                return ImportResult(1, extraction.identifier_map(connection, document_id))
            if document["current_revision"] != 0:
                raise Problem(
                    409,
                    "initial_already_imported",
                    "This chapter already has content. Use the re-extraction reconciliation workflow.",
                )
            ids = {page.id: str(uuid4()) for page in validated.pages}
            ids.update({block.id: str(uuid4()) for block in validated.blocks})
            extraction.insert_identifiers(connection, document_id, ids)
            now = now_utc()
            extraction.insert_revision(connection, document_id, document["owner_id"], now)
            for page in validated.pages:
                extraction.insert_page(connection, document_id, page, ids)
            for block in validated.blocks:
                extraction.insert_block(
                    connection, document_id, block, ids, document["owner_id"], now
                )
            for edge in validated.edges:
                extraction.insert_edge(connection, document_id, edge, ids)
            extraction.finish_import(
                connection,
                document_id,
                validated,
                digest,
                now,
                producer_json=producer_json,
                producer_version=producer_version,
                needs_review=needs_review,
            )
    except sqlite3.IntegrityError:
        raise Problem(
            422,
            "extraction_integrity",
            "Extraction could not be imported. Check the contract identifiers and references.",
        ) from None
    except ValueError:
        raise Problem(
            422,
            "invalid_source_asset",
            "A source asset is unavailable or belongs to another document.",
        ) from None
    return ImportResult(1, ids)
