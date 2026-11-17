"""Versioned JSON Schemas for the shared P1 content contract.

* ``build_json_schema("1.1.0")`` - current contract. Accepts 1.0.0 and 1.1.0
  documents and applies the 1.0.0 restrictions when ``schema_version`` is
  ``"1.0.0"`` (via ``if``/``then``).
* ``build_json_schema("1.0.0")`` - the 1.0.0 contract as a frozen artifact
  for consumers that only support 1.0.0. It rejects every 1.1.0 document.

JSON Schema cannot compare array items or follow ID references, so some
rules are enforced only by the Python validator (``models.Document``). They
are listed under ``x-pathya-invariants`` and covered by the language-neutral
conformance vectors in ``contract/conformance/``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from pathya_document_ai.models import QUALITY_FLAGS_ADDED_IN_1_1, SCHEMA_VERSION, Document, QualityFlag

SCHEMA_VERSIONS = ("1.0.0", "1.1.0")
_DRAFT = "https://json-schema.org/draft/2020-12/schema"

PYTHON_ONLY_INVARIANTS = [
    "bbox: x0 < x1 and y0 < y1 (ranges 0..1 are in the schema).",
    "Unique ids across pages, blocks, edges and corrections; unique page_index.",
    "page.document_id equals document.id; page.source_asset_id equals source_asset.id.",
    "block.page_id and block.parent_id reference existing pages/blocks; parent on the same page; no cycles.",
    "reading_order is unique per (page_id, parent_id).",
    "Table cells reference their table, appear in its cell_ids, fit within row/column counts, and "
    "header_cell_ids reference header cells of the same table.",
    "An uncertain table (no cells) carries the table_structure_uncertain flag.",
    "Edge endpoints exist; caption_of goes caption -> figure/table/equation; header_for goes header cell -> cell.",
    "figure.caption_block_id references a caption block.",
    "Revision 1 blocks have current_text == raw_text; correction base_revision < block revision.",
    "A page with status 'blank' has no blocks.",
    "Confidence: origin 'not_available' iff score is null; null score and heuristic origin need a reason.",
]


def _base() -> dict[str, Any]:
    return Document.model_json_schema(mode="serialization")


def _require_ids(schema: dict[str, Any]) -> None:
    for node in [schema, *schema["$defs"].values()]:
        if "id" in node.get("properties", {}):
            required = node.setdefault("required", [])
            if "id" not in required:
                required.append("id")


def _v1_1(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema["$defs"]
    _require_ids(schema)
    # Page status/warnings may be absent only in 1.0.0 documents (enforced below).
    defs["Page"]["required"] = [f for f in defs["Page"]["required"] if f not in ("status", "warnings")]
    defs["TableMeta"]["oneOf"] = [
        {"title": "structured table",
         "properties": {"row_count": {"type": "integer"}, "column_count": {"type": "integer"},
                        "cell_ids": {"minItems": 1}}},
        {"title": "uncertain table candidate (1.1.0)",
         "properties": {"row_count": {"type": "null"}, "column_count": {"type": "null"},
                        "cell_ids": {"maxItems": 0}}},
    ]
    v1_0_flags = sorted(f.value for f in QualityFlag if f not in QUALITY_FLAGS_ADDED_IN_1_1)
    schema["allOf"] = [{
        "if": {"properties": {"schema_version": {"const": "1.0.0"}}, "required": ["schema_version"]},
        "then": {"properties": {
            "pages": {"items": {"properties": {"status": {"type": "null"}, "warnings": {"maxItems": 0}}}},
            "blocks": {"items": {"properties": {
                "quality_flags": {"items": {"enum": v1_0_flags}},
                "table": {"anyOf": [{"type": "null"}, {"properties": {"cell_ids": {"minItems": 1}}}]},
            }}},
        }},
        "else": {"properties": {"pages": {"items": {
            "required": ["status", "warnings"],
            "properties": {"status": {"$ref": "#/$defs/PageStatus"}},
        }}}},
    }]
    return schema


def _v1_0(schema: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct the 1.0.0 schema: the contract before any 1.1.0 addition.

    The original 1.0.0 file was regenerated in place before the repository's
    first commit, so it is rebuilt here from the 1.0.0 rules (documented in
    docs/p1_contract.md and the 1.0.0 conformance vectors) rather than copied.
    Like the original, it does not mark ``id`` fields as required.
    """
    defs = schema["$defs"]
    schema["properties"]["schema_version"] = {"const": "1.0.0", "default": "1.0.0", "title": "Schema Version",
                                              "type": "string"}
    defs["QualityFlag"]["enum"] = [f for f in defs["QualityFlag"]["enum"]
                                   if QualityFlag(f) not in QUALITY_FLAGS_ADDED_IN_1_1]
    page = defs["Page"]
    for name in ("status", "warnings"):
        page["properties"].pop(name)
    page["required"] = [f for f in page["required"] if f not in ("status", "warnings")]
    for name in ("PageStatus", "PageWarning", "ProcessingStage"):
        defs.pop(name, None)
    table = defs["TableMeta"]
    table["properties"]["row_count"] = {"minimum": 1, "title": "Row Count", "type": "integer"}
    table["properties"]["column_count"] = {"minimum": 1, "title": "Column Count", "type": "integer"}
    table["properties"]["cell_ids"]["minItems"] = 1
    table["description"] = "Attached to blocks of type ``table``."
    return schema


def build_json_schema(version: str = SCHEMA_VERSION) -> dict[str, Any]:
    """Return the Draft 2020-12 JSON Schema for contract ``version``."""
    if version not in SCHEMA_VERSIONS:
        raise ValueError(f"unknown schema version {version!r}; known: {SCHEMA_VERSIONS}")
    schema = copy.deepcopy(_base())
    schema = _v1_1(schema) if version == "1.1.0" else _v1_0(schema)
    header: dict[str, Any] = {
        "$schema": _DRAFT,
        "$id": f"https://pathya.local/schemas/p1-content/{version}/document.schema.json",
        "x-pathya-schema-version": version,
        "x-pathya-invariants": PYTHON_ONLY_INVARIANTS,
    }
    if version == "1.0.0":
        header["x-pathya-reconstructed"] = (
            "Rebuilt from the 1.0.0 rules after the original file was overwritten before the first commit.")
    return {**header, **schema}


def render_json_schema(version: str = SCHEMA_VERSION) -> str:
    return json.dumps(build_json_schema(version), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_json_schema(path: Path, version: str = SCHEMA_VERSION) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_schema(version), encoding="utf-8", newline="\n")
