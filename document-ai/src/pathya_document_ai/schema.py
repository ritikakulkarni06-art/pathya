"""Versioned JSON Schemas for the shared P1 content contract.

* ``1.0.0`` and ``1.1.0`` are **frozen**: loaded byte-for-byte from
  ``frozen_schemas/`` (copies of the files published at commit 39331e4, which
  P2/P3 integrate against). They are never regenerated from the models.
* ``1.2.0`` (current) is generated from the models. It accepts 1.0.0, 1.1.0
  and 1.2.0 documents and applies each version's restrictions with
  ``if``/``then`` on ``schema_version``.

JSON Schema cannot compare array items, follow ID references or hash text, so
some rules are enforced only by the Python validator (``models.Document``).
They are listed under ``x-pathya-invariants`` and covered by the conformance
vectors in ``contract/conformance/``.
"""

from __future__ import annotations

import copy
from importlib import resources
import json
from pathlib import Path
from typing import Any

from pathya_document_ai.models import (
    CONTRACT_FAMILY,
    CORRECTION_OPERATIONS_ADDED_IN_1_2,
    QUALITY_FLAGS_ADDED_IN_1_1,
    QUALITY_FLAGS_ADDED_IN_1_2,
    SCHEMA_VERSION,
    CorrectionOperation,
    Document,
    QualityFlag,
)

SCHEMA_VERSIONS = ("1.0.0", "1.1.0", "1.2.0")
FROZEN_VERSIONS = ("1.0.0", "1.1.0")
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
    "1.2.0: integration.sentences and every audio reference carry the block's current revision and the "
    "SHA-256 of its exact current_text (otherwise stale); sentence ranges are ordered, non-overlapping "
    "code-point ranges within current_text; audio sentence_index references an existing range.",
    "1.0.0/1.1.0 documents use no 1.2.0 feature (role other than body, heading_level, integration, "
    "critical_symbol_uncertain, set_block_type/set_reading_order corrections).",
]


def _frozen(version: str) -> dict[str, Any]:
    text = resources.files("pathya_document_ai").joinpath(
        f"frozen_schemas/pathya_content.v{version}.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


def _drop_required(node: dict[str, Any], *names: str) -> None:
    node["required"] = [f for f in node.get("required", []) if f not in names]


def _v1_2() -> dict[str, Any]:
    schema = copy.deepcopy(Document.model_json_schema(mode="serialization"))
    defs = schema["$defs"]
    for node in [schema, *defs.values()]:  # every serialized id is required
        if "id" in node.get("properties", {}) and "id" not in node.setdefault("required", []):
            node["required"].append("id")
    # Fields introduced after 1.0.0 may be absent in older documents; per-version rules below.
    _drop_required(defs["Page"], "status", "warnings")
    _drop_required(schema, "contract_family", "integration")
    _drop_required(defs["Block"], "heading_level", "role", "integration")
    _drop_required(defs["Correction"], "new_block_type", "new_reading_order")

    defs["TableMeta"]["oneOf"] = [
        {"title": "structured table",
         "properties": {"row_count": {"type": "integer"}, "column_count": {"type": "integer"},
                        "cell_ids": {"minItems": 1}}},
        {"title": "uncertain table candidate (1.1.0+)",
         "properties": {"row_count": {"type": "null"}, "column_count": {"type": "null"},
                        "cell_ids": {"maxItems": 0}}},
    ]
    defs["Block"]["allOf"] = [
        {"if": {"required": ["quality_flags"],
                "properties": {"quality_flags": {"contains": {"const": "critical_symbol_uncertain"}}}},
         "then": {"properties": {"review_status": {"not": {"const": "unreviewed"}}}}},
        {"if": {"required": ["heading_level"], "properties": {"heading_level": {"type": "integer"}}},
         "then": {"properties": {"block_type": {"const": "heading"}}}},
    ]

    v1_0_flags = sorted(f.value for f in QualityFlag
                        if f not in QUALITY_FLAGS_ADDED_IN_1_1 and f not in QUALITY_FLAGS_ADDED_IN_1_2)
    v1_1_flags = sorted(f.value for f in QualityFlag if f not in QUALITY_FLAGS_ADDED_IN_1_2)
    old_ops = sorted(o.value for o in CorrectionOperation if o not in CORRECTION_OPERATIONS_ADDED_IN_1_2)

    def pre_1_2(flags: list[str], *, page_status: bool) -> dict[str, Any]:
        page: dict[str, Any] = ({"required": ["status", "warnings"], "properties": {"status": {"$ref": "#/$defs/PageStatus"}}}
                                if page_status else
                                {"properties": {"status": {"type": "null"}, "warnings": {"maxItems": 0}}})
        block_props: dict[str, Any] = {
            "quality_flags": {"items": {"enum": flags}},
            "role": {"anyOf": [{"type": "null"}, {"const": "body"}]},
            "heading_level": {"type": "null"},
            "integration": {"type": "null"},
        }
        if not page_status:  # 1.0.0: every table has cells
            block_props["table"] = {"anyOf": [{"type": "null"}, {"properties": {"cell_ids": {"minItems": 1}}}]}
        return {"properties": {
            "contract_family": {"type": "null"},
            "integration": {"type": "null"},
            "pages": {"items": page},
            "blocks": {"items": {"properties": block_props}},
            "corrections": {"items": {"properties": {"operation": {"enum": old_ops}}}},
        }}

    schema["allOf"] = [
        {"if": {"required": ["schema_version"], "properties": {"schema_version": {"const": "1.0.0"}}},
         "then": pre_1_2(v1_0_flags, page_status=False)},
        {"if": {"required": ["schema_version"], "properties": {"schema_version": {"const": "1.1.0"}}},
         "then": pre_1_2(v1_1_flags, page_status=True)},
        {"if": {"required": ["schema_version"], "properties": {"schema_version": {"const": "1.2.0"}}},
         "then": {"required": ["contract_family"], "properties": {
             "contract_family": {"const": CONTRACT_FAMILY},
             "pages": {"items": {"required": ["status", "warnings"],
                                 "properties": {"status": {"$ref": "#/$defs/PageStatus"}}}},
             "blocks": {"items": {"required": ["role"], "properties": {"role": {"$ref": "#/$defs/BlockRole"}}}},
         }}},
    ]
    header = {
        "$schema": _DRAFT,
        "$id": f"https://pathya.local/schemas/p1-content/{SCHEMA_VERSION}/document.schema.json",
        "x-pathya-schema-version": SCHEMA_VERSION,
        "x-pathya-contract-family": CONTRACT_FAMILY,
        "x-pathya-invariants": PYTHON_ONLY_INVARIANTS,
    }
    return {**header, **schema}


def build_json_schema(version: str = SCHEMA_VERSION) -> dict[str, Any]:
    """Return the Draft 2020-12 JSON Schema for contract ``version``."""
    if version not in SCHEMA_VERSIONS:
        raise ValueError(f"unknown schema version {version!r}; known: {SCHEMA_VERSIONS}")
    if version in FROZEN_VERSIONS:
        return _frozen(version)
    return _v1_2()


def render_json_schema(version: str = SCHEMA_VERSION) -> str:
    if version in FROZEN_VERSIONS:  # exact published bytes, not a re-serialization
        return resources.files("pathya_document_ai").joinpath(
            f"frozen_schemas/pathya_content.v{version}.schema.json").read_text(encoding="utf-8")
    return json.dumps(build_json_schema(version), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_json_schema(path: Path, version: str = SCHEMA_VERSION) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_schema(version), encoding="utf-8", newline="\n")
