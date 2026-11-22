import importlib
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.errors import Problem
from app.schemas.p1.models import Document

PRODUCER_COMMIT = "39331e4291d2af6b68654dead2e9e8b9595de32f"


@dataclass(frozen=True)
class P1Payload:
    document: Document
    source_json: bytes


def parse_p1_payload(payload: bytes) -> P1Payload:
    """Validate the pinned producer format and retain its exact source representation."""
    try:
        document = Document.model_validate_json(payload)
    except ValidationError:
        raise Problem(
            422,
            "invalid_p1_document",
            "The extracted chapter does not meet the supported Person 1 content contract.",
        ) from None
    return P1Payload(document, payload)


def validate_p1_initial_import(payload: bytes, owned_source_sha256: str) -> P1Payload:
    """Check initial-import rules against a checksum taken from backend-owned storage."""
    parsed = parse_p1_payload(payload)
    if parsed.document.source_asset.sha256 != owned_source_sha256:
        raise Problem(
            422, "source_checksum_mismatch", "Extraction refers to a different source file."
        )
    if parsed.document.corrections or any(block.revision != 1 for block in parsed.document.blocks):
        raise Problem(
            422,
            "producer_revision_history",
            "Import an unedited extraction. Apply corrections through the backend.",
        )
    return parsed


def run_p1_extractor(specification: str, path: Path, languages: list[str], max_bytes: int) -> bytes:
    """Call the configured trusted whole-document producer inside the worker."""
    try:
        module, name = specification.removeprefix("p1:").rsplit(":", 1)
        extract = getattr(importlib.import_module(module), name)
    except (ValueError, ImportError, AttributeError):
        raise Problem(
            503, "p1_extractor_unavailable", "Configure the verified Person 1 extractor."
        ) from None
    if not callable(extract):
        raise Problem(503, "p1_extractor_unavailable", "Configure the verified Person 1 extractor.")
    payload = extract(path, languages)
    if not isinstance(payload, bytes) or len(payload) > max_bytes:
        raise Problem(
            422, "p1_output_invalid", "The extractor returned an invalid or oversized chapter."
        )
    return payload
