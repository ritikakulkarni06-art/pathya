import json
from typing import Any


def metadata(block: dict[str, Any]) -> dict[str, Any]:
    value = block.get("metadata", block.get("metadata_json", {}))
    return dict(json.loads(value) if isinstance(value, str) else value)


def is_eligible(block: dict[str, Any], expected_revision: int | None = None) -> bool:
    """Current means active block identity and matching dependency, not doc rev == block rev."""
    provenance = block.get("provenance", block.get("provenance_json", {}))
    if isinstance(provenance, str):
        provenance = json.loads(provenance)
    successors = block.get("successor_ids", block.get("successor_ids_json", []))
    if isinstance(successors, str):
        successors = json.loads(successors)
    if (
        block.get("status") not in {"ok", "corrected", "reviewed", "not_scored"}
        or block.get("critical_flag")
        or successors
        or block.get("origin") in {"ai_explanation", "teacher_note"}
        or provenance.get("parser") in {"ai_explanation", "teacher_note"}
        or (expected_revision is not None and block["revision"] != expected_revision)
    ):
        return False
    if block["type"] == "equation":
        return block["status"] == "reviewed" and bool(metadata(block).get("spoken_fallback"))
    if block["type"] == "figure":
        return block["status"] == "reviewed" and bool(metadata(block).get("alt_text_short"))
    return True
