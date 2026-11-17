"""JSON Schema export for the shared P1 content contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pathya_document_ai.models import SCHEMA_VERSION, Document

SCHEMA_ID = f"https://pathya.local/schemas/p1-content/{SCHEMA_VERSION}/document.schema.json"


def build_json_schema() -> dict[str, Any]:
    """Return the Draft 2020-12 JSON Schema for a serialized ``Document``.

    JSON Schema covers shapes, enums and ranges. Cross-references (page/block
    IDs, table spans, caption targets, revisions) are enforced by the Pydantic
    ``Document`` validator; consumers must not rely on the schema alone.
    """
    schema = Document.model_json_schema(mode="serialization")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "x-pathya-schema-version": SCHEMA_VERSION,
        **schema,
    }


def render_json_schema() -> str:
    return json.dumps(build_json_schema(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_json_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json_schema(), encoding="utf-8", newline="\n")
