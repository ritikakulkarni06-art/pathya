from dataclasses import dataclass

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
