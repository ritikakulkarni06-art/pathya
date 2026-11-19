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


def test_upgrade_preserves_content_and_adds_only_page_status(v10: dict[str, Any]) -> None:
    upgraded = upgrade_document_data(v10, "1.1.0")  # pinned: this test covers the 1.0.0 -> 1.1.0 step
    assert upgraded["schema_version"] == "1.1.0"
    assert v10["schema_version"] == "1.0.0" and "status" not in v10["pages"][0]  # input not mutated
    old, new = Document.model_validate(v10), Document.model_validate(upgraded)
    assert [p.status.value for p in new.pages] == ["ok", "ok"] and all(not p.warnings for p in new.pages)
    strip = {"schema_version": True, "pages": {"__all__": {"status", "warnings"}}}
    assert old.model_dump(exclude=strip) == new.model_dump(exclude=strip)


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
    schema = build_json_schema("1.1.0")  # the frozen 1.1.0 artifact
    assert schema["x-pathya-schema-version"] == "1.1.0"
    assert set(schema["properties"]["schema_version"]["enum"]) == {"1.0.0", "1.1.0"}
    assert schema["x-pathya-invariants"]  # Python-only rules are listed, not implied


# ------------------------------------------------ versioned schemas (audit C3)

CONFORMANCE = ROOT / "contract" / "conformance"


def _vectors() -> list[dict[str, Any]]:
    return json.loads((CONFORMANCE / "index.json").read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["file"])
def test_conformance_vectors(vector: dict[str, Any]) -> None:
    doc = json.loads((CONFORMANCE / vector["file"]).read_text(encoding="utf-8"))
    got = {}
    for version in ("1.0.0", "1.1.0"):
        validator = jsonschema.Draft202012Validator(build_json_schema(version),
                                                    format_checker=jsonschema.FormatChecker())
        got[f"schema_{version.replace('.', '_')}"] = validator.is_valid(doc)
    try:
        Document.model_validate(doc)
        got["python"] = True
    except ValidationError:
        got["python"] = False
    assert got == vector["expected_valid"], vector["description"]


def test_conformance_vectors_and_schemas_are_committed_and_current() -> None:
    import subprocess
    import sys

    for script in ("export_schema.py", "make_conformance.py"):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--check"],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr


def test_v1_0_0_schema_artifact_is_frozen_to_1_0_rules() -> None:
    old = json.loads((ROOT / "contract" / "schemas" / "pathya_content.v1.0.0.schema.json").read_text(encoding="utf-8"))
    assert old["properties"]["schema_version"]["const"] == "1.0.0"
    assert not QUALITY_FLAGS_ADDED_IN_1_1.intersection(old["$defs"]["QualityFlag"]["enum"])
    assert "status" not in old["$defs"]["Page"]["properties"]
    assert old["$defs"]["TableMeta"]["properties"]["cell_ids"]["minItems"] == 1


# ---------------------------------------------- version policy and export


def _status_doc(v10: dict[str, Any], status: str = "ok", warnings: list[Any] | None = None) -> Document:
    data = upgrade_document_data(v10)
    for page in data["pages"]:
        page.update(status=status, warnings=warnings or [])
    return Document.model_validate(data)


def test_required_version_reflects_content(v10: dict[str, Any]) -> None:
    from pathya_document_ai.models import required_version

    assert required_version(Document.model_validate(v10)) == "1.0.0"
    assert required_version(_status_doc(v10)) == "1.1.0"  # page status is 1.1.0 information


def test_export_to_1_0_0_only_when_nothing_is_lost(v10: dict[str, Any]) -> None:
    from pathya_document_ai.models import IncompatibleVersionError, export_document_data

    clean = export_document_data(_status_doc(v10), "1.0.0")
    assert clean["schema_version"] == "1.0.0" and "status" not in clean["pages"][0]
    jsonschema.Draft202012Validator(build_json_schema("1.0.0")).validate(clean)

    warned = _status_doc(v10, warnings=[{"stage": "ocr", "code": "ocr_applied", "message": "x"}])
    with pytest.raises(IncompatibleVersionError, match="warnings"):
        export_document_data(warned, "1.0.0")
    failed = upgrade_document_data(v10)
    failed["pages"][0]["status"] = "needs_ocr"
    with pytest.raises(IncompatibleVersionError, match="needs_ocr"):
        export_document_data(Document.model_validate(failed), "1.0.0")
    flagged = upgrade_document_data(v10)
    _block(flagged, "a2")["quality_flags"].append("orphan_caption")
    with pytest.raises(IncompatibleVersionError, match="orphan_caption"):
        export_document_data(Document.model_validate(flagged), "1.0.0")


def test_export_1_1_0_validates_against_both_layers(v10: dict[str, Any]) -> None:
    from pathya_document_ai.models import export_document_data

    data = export_document_data(_status_doc(v10), "1.1.0")
    jsonschema.Draft202012Validator(build_json_schema("1.1.0"), format_checker=jsonschema.FormatChecker()).validate(data)
    assert not jsonschema.Draft202012Validator(build_json_schema("1.0.0")).is_valid(data)
    assert Document.model_validate(data).schema_version == "1.1.0"


# ------------------------------------------------ ids, pages and parents


def test_serialized_documents_must_carry_ids(v10: dict[str, Any]) -> None:
    v10["pages"][1].pop("id")
    with pytest.raises(ValidationError, match=r"pages\[1\]\.id"):
        Document.model_validate(v10)


def test_child_block_must_be_on_its_parents_page(v10: dict[str, Any]) -> None:
    _block(v10, "a5")["page_id"] = "7d1e4c52-0000-4000-8000-0000000000b0"
    with pytest.raises(ValidationError):
        Document.model_validate(v10)


@pytest.mark.parametrize("status", ["ok", "blank", "needs_ocr", "partial", "failed"])
def test_page_status_values(v10: dict[str, Any], status: str) -> None:
    data = upgrade_document_data(v10, "1.1.0")  # validated against the frozen 1.1.0 schema below
    if status == "blank":  # a blank page has no blocks
        page_id = data["pages"][1]["id"]
        dropped = {b["id"] for b in data["blocks"] if b["page_id"] == page_id}
        data["blocks"] = [b for b in data["blocks"] if b["id"] not in dropped]
        data["edges"] = [e for e in data["edges"] if e["source_id"] not in dropped and e["target_id"] not in dropped]
        data["corrections"] = [c for c in data["corrections"] if c["block_id"] not in dropped]
        data["pages"][1]["status"] = "blank"
    else:
        data["pages"][1]["status"] = status
    assert Document.model_validate(data).pages[1].status.value == status
    jsonschema.Draft202012Validator(build_json_schema("1.1.0")).validate(json.loads(json.dumps(data, default=str)))


def test_page_warning_codes_are_machine_readable(v10: dict[str, Any]) -> None:
    data = upgrade_document_data(v10)
    data["pages"][0]["warnings"] = [{"stage": "layout", "code": "Bad Code!", "message": "x"}]
    with pytest.raises(ValidationError, match="pattern"):
        Document.model_validate(data)
