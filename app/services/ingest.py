import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.db.connection import Database
from app.db.repos import documents, extraction
from app.errors import Problem
from app.schemas.content import ExtractionResult, parse_extraction
from app.services.jobs import LeaseLost


@dataclass(frozen=True)
class ImportResult:
    document_revision: int
    id_map: dict[str, str]


def import_extraction(
    database: Database,
    document_id: str,
    result: ExtractionResult | dict[str, Any],
    *,
    lease: tuple[str, str] | None = None,
) -> ImportResult:
    validated = parse_extraction(result)
    encoded = json.dumps(validated.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
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
            extraction.finish_import(connection, document_id, validated, digest, now)
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
