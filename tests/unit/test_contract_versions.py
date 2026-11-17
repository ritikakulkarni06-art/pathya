"""Contract 1.0.0 -> 1.1.0 versioning and migration tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError
import pytest

from pathya_document_ai.models import (
    QUALITY_FLAGS_ADDED_IN_1_1,
    SCHEMA_VERSION,
    Document,
    QualityFlag,
    TableMeta,
    upgrade_document_data,
)
from pathya_document_ai.schema import build_json_schema

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "contract" / "samples" / "sample_document_en_hi.json"


@pytest.fixture()
def v10() -> dict[str, Any]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _block(doc: dict[str, Any], suffix: str) -> dict[str, Any]:
    return next(b for b in doc["blocks"] if b["id"].endswith(suffix))


def test_v1_0_documents_still_validate_unchanged(v10: dict[str, Any]) -> None:
    assert v10["schema_version"] == "1.0.0"
    assert Document.model_validate(v10).schema_version == "1.0.0"
    jsonschema.Draft202012Validator(build_json_schema()).validate(v10)


def test_upgrade_relabels_and_preserves_content(v10: dict[str, Any]) -> None:
    upgraded = upgrade_document_data(v10)
    assert upgraded["schema_version"] == SCHEMA_VERSION == "1.1.0"
    assert v10["schema_version"] == "1.0.0"  # input not mutated
    old, new = Document.model_validate(v10), Document.model_validate(upgraded)
    assert old.model_dump(exclude={"schema_version"}) == new.model_dump(exclude={"schema_version"})


@pytest.mark.parametrize("version", ["0.9.0", "2.0.0", None])
def test_upgrade_rejects_unknown_versions(v10: dict[str, Any], version: str | None) -> None:
    v10["schema_version"] = version
    with pytest.raises(ValueError, match="unsupported schema_version"):
        upgrade_document_data(v10)


@pytest.mark.parametrize("flag", sorted(f.value for f in QUALITY_FLAGS_ADDED_IN_1_1))
def test_new_flags_need_1_1(v10: dict[str, Any], flag: str) -> None:
    _block(v10, "a2")["quality_flags"] = [flag]
    with pytest.raises(ValidationError, match="1.1.0 quality flags"):
        Document.model_validate(v10)
    assert QualityFlag(flag) in Document.model_validate(upgrade_document_data(v10)).blocks[1].quality_flags


def _uncertain_table(doc: dict[str, Any]) -> dict[str, Any]:
    table = _block(doc, "a4")
    table["table"] = {"row_count": None, "column_count": None, "cell_ids": []}
    table["quality_flags"] = ["table_structure_uncertain"]
    doc["blocks"] = [b for b in doc["blocks"] if b["block_type"] != "table_cell"]
    doc["edges"] = [e for e in doc["edges"] if e["edge_type"] not in ("header_for", "contains")]
    return doc


def test_uncertain_table_candidate_requires_1_1_and_flag(v10: dict[str, Any]) -> None:
    doc = _uncertain_table(copy.deepcopy(v10))
    with pytest.raises(ValidationError, match="requires 1.1.0"):
        Document.model_validate(doc)
    upgraded = upgrade_document_data(doc)
    table = next(b for b in Document.model_validate(upgraded).blocks if b.table)
    assert table.table.is_uncertain_candidate and table.table.row_count is None  # type: ignore[union-attr]
    _block(upgraded, "a4")["quality_flags"] = []
    with pytest.raises(ValidationError, match="table_structure_uncertain"):
        Document.model_validate(upgraded)


def test_table_meta_counts_are_never_guessed() -> None:
    with pytest.raises(ValidationError, match="must leave row_count"):
        TableMeta(row_count=2, column_count=2, cell_ids=[])
    with pytest.raises(ValidationError, match="requires row_count"):
        TableMeta(cell_ids=["7d1e4c52-0000-4000-8000-0000000000a5"])


def test_schema_documents_both_versions() -> None:
    schema = build_json_schema()
    assert schema["x-pathya-schema-version"] == "1.1.0"
    assert set(schema["properties"]["schema_version"]["enum"]) == {"1.0.0", "1.1.0"}
