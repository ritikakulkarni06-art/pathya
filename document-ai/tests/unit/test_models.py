"""Phase 1 contract tests: Pydantic models, cross-references and JSON Schema."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema
from pydantic import ValidationError
import pytest

from pathya_document_ai.geometry import CoordinateTransform
from pathya_document_ai.models import (
    SCHEMA_VERSION,
    Block,
    BlockType,
    Confidence,
    ConfidenceOrigin,
    Correction,
    Document,
    Edge,
    EdgeType,
    EquationMeta,
    FigureMeta,
    Language,
    Provenance,
    ReviewStatus,
    TableCellMeta,
)
from pathya_document_ai.schema import build_json_schema, render_json_schema

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "contract" / "samples" / "sample_document_en_hi.json"
SCHEMA_FILE = ROOT / "contract" / "pathya_content.schema.json"
NOW = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
PAGE_ID = UUID("7d1e4c52-0000-4000-8000-0000000000a0")


@pytest.fixture()
def sample() -> dict[str, Any]:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _block(**overrides: Any) -> Block:
    data: dict[str, Any] = {
        "page_id": PAGE_ID,
        "block_type": "paragraph",
        "reading_order": 0,
        "bbox": [0.1, 0.1, 0.9, 0.2],
        "raw_text": "Hello",
        "current_text": "Hello",
        "language": "en",
        "confidence": {"origin": "not_available", "reason": "native PDF text"},
        "provenance": {"method": "native_pdf_text", "engine": "pdfplumber",
                       "engine_version": "0.11.9", "created_at": NOW},
    }
    data.update(overrides)
    return Block.model_validate(data)


def _find(doc: dict[str, Any], suffix: str) -> dict[str, Any]:
    return next(b for b in doc["blocks"] if b["id"].endswith(suffix))


def _invalid(doc: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Document.model_validate(doc)


# ------------------------------------------------------------------ bounding boxes


@pytest.mark.parametrize("bbox", [[0, 0, 1, 1], [0.1, 0.2, 0.3, 0.4], [0.0, 0.5, 0.0001, 0.5001]])
def test_valid_bboxes(bbox: list[float]) -> None:
    assert _block(bbox=bbox).bbox == tuple(bbox)


@pytest.mark.parametrize(
    ("bbox", "match"),
    [
        ([0.5, 0.1, 0.4, 0.2], "x0 < x1"),
        ([0.1, 0.3, 0.2, 0.3], "y0 < y1"),
        ([-0.1, 0.1, 0.2, 0.2], "greater than or equal to 0"),
        ([0.1, 0.1, 1.2, 0.2], "less than or equal to 1"),
        ([0.1, 0.1, 0.2], "Field required|at least 4|4 items"),
        ([0.1, 0.1, 0.2, 0.3, 0.4], "at most 4|4 items"),
        ([0.1, float("nan"), 0.2, 0.3], "finite"),
    ],
)
def test_invalid_bboxes(bbox: list[float], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _block(bbox=bbox)


def test_degenerate_crop_box_rejected() -> None:
    with pytest.raises(ValidationError, match="x0 < x1"):
        CoordinateTransform(source_space="pdf_user_space", crop_box=(10, 0, 10, 800), rotation_applied=0)


# ---------------------------------------------------------------------- stable IDs


def test_ids_are_uuid_and_independent_of_text() -> None:
    a, b = _block(), _block()
    assert isinstance(a.id, UUID) and a.id.version == 4
    assert a.id != b.id  # identical text, distinct identity


def test_ids_survive_serialization_round_trip(sample: dict[str, Any]) -> None:
    doc = Document.model_validate(sample)
    again = Document.model_validate_json(doc.model_dump_json())
    assert [b.id for b in again.blocks] == [b.id for b in doc.blocks]
    assert again == doc


def test_text_correction_does_not_change_id() -> None:
    block = _block()
    corrected = Block.model_validate({**block.model_dump(), "current_text": "Hello, world", "revision": 2})
    assert corrected.id == block.id and corrected.raw_text == "Hello"


def test_non_uuid_id_rejected() -> None:
    with pytest.raises(ValidationError, match="UUID"):
        _block(id="block-hello")


# ------------------------------------------------------------------------ language


@pytest.mark.parametrize("lang", ["en", "hi", "mul", "und"])
def test_supported_languages(lang: str) -> None:
    assert _block(language=lang).language is Language(lang)


def test_hindi_text_preserved_exactly() -> None:
    text = "प्रकाश का परावर्तन"
    block = _block(raw_text=text, current_text=text, language="hi")
    assert json.loads(block.model_dump_json())["raw_text"] == text


@pytest.mark.parametrize("lang", ["hindi", "EN", "en-US", "fr", ""])
def test_unsupported_language_rejected(lang: str) -> None:
    with pytest.raises(ValidationError, match="language"):
        _block(language=lang)


# ---------------------------------------------------------------------- confidence


def test_native_text_confidence_is_null_not_full() -> None:
    conf = Confidence.unavailable("native PDF text layer")
    assert conf.score is None and conf.origin is ConfidenceOrigin.NOT_AVAILABLE


def test_not_available_with_score_rejected() -> None:
    with pytest.raises(ValidationError, match="requires score to be null"):
        Confidence(score=1.0, origin="not_available", reason="native")


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"score": None, "origin": "engine_reported"}, "requires a score"),
        ({"score": None, "origin": "not_available"}, "requires a reason"),
        ({"score": 0.5, "origin": "heuristic"}, "heuristic confidence requires a reason"),
        ({"score": 1.5, "origin": "engine_reported"}, "less than or equal to 1"),
    ],
)
def test_invalid_confidence(data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Confidence.model_validate(data)


def test_engine_confidence_accepted() -> None:
    assert Confidence(score=0.81, origin="engine_reported").score == 0.81


# ------------------------------------------------------- block types and relations


def test_supported_block_types_and_edges_are_exact() -> None:
    assert {t.value for t in BlockType} == {
        "heading", "paragraph", "list_item", "table", "table_cell", "equation", "figure", "caption"}
    assert {e.value for e in EdgeType} == {
        "contains", "precedes", "caption_of", "refers_to", "header_for", "supersedes"}


def test_unknown_block_type_rejected() -> None:
    with pytest.raises(ValidationError, match="block_type"):
        _block(block_type="sidebar")


def test_type_specific_metadata_required_and_exclusive() -> None:
    with pytest.raises(ValidationError, match="requires 'figure' metadata"):
        _block(block_type="figure", raw_text=None, current_text=None)
    with pytest.raises(ValidationError, match="only allowed on 'figure'"):
        _block(figure=FigureMeta())


def test_edge_self_loop_rejected() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        Edge(edge_type="precedes", source_id=PAGE_ID, target_id=PAGE_ID,
             provenance=Provenance(method="derived", created_at=NOW))


def test_unknown_edge_type_rejected() -> None:
    with pytest.raises(ValidationError, match="edge_type"):
        Edge.model_validate({"edge_type": "follows", "source_id": str(PAGE_ID),
                             "target_id": "7d1e4c52-0000-4000-8000-0000000000a1",
                             "provenance": {"method": "derived", "created_at": NOW}})


def test_caption_of_must_start_at_caption(sample: dict[str, Any]) -> None:
    edge = next(e for e in sample["edges"] if e["edge_type"] == "caption_of")
    edge["source_id"] = "7d1e4c52-0000-4000-8000-0000000000a2"  # paragraph
    _invalid(sample, "source must be a caption")


def test_edge_to_unknown_block_rejected(sample: dict[str, Any]) -> None:
    sample["edges"][0]["target_id"] = "7d1e4c52-0000-4000-8000-00000000ffff"
    _invalid(sample, "unknown block")


def test_parent_cycle_rejected(sample: dict[str, Any]) -> None:
    table = _find(sample, "a4")
    table["parent_id"] = "7d1e4c52-0000-4000-8000-0000000000a5"
    _invalid(sample, "cycle")


def test_duplicate_reading_order_rejected(sample: dict[str, Any]) -> None:
    _find(sample, "a2")["reading_order"] = 0
    _invalid(sample, "duplicate reading_order")


# --------------------------------------------------------------------------- tables


def test_table_metadata_parsed(sample: dict[str, Any]) -> None:
    doc = Document.model_validate(sample)
    table = next(b for b in doc.blocks if b.block_type is BlockType.TABLE)
    cells = [b for b in doc.blocks if b.table_cell and b.table_cell.table_id == table.id]
    assert table.table is not None and len(cells) == 4
    assert {(c.table_cell.row_index, c.table_cell.column_index) for c in cells} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    body = next(c for c in cells if c.current_text == "Acceleration")
    assert body.table_cell.header_cell_ids == [next(c.id for c in cells if c.current_text == "Quantity")]


def test_cell_span_beyond_table_rejected(sample: dict[str, Any]) -> None:
    _find(sample, "a8")["table_cell"]["column_span"] = 2
    _invalid(sample, "column span exceeds")


def test_header_reference_must_be_header_cell(sample: dict[str, Any]) -> None:
    _find(sample, "a8")["table_cell"]["header_cell_ids"] = ["7d1e4c52-0000-4000-8000-0000000000a7"]
    _invalid(sample, "is not a header cell")


def test_cell_missing_from_table_rejected(sample: dict[str, Any]) -> None:
    _find(sample, "a4")["table"]["cell_ids"].pop()
    _invalid(sample, "missing from table")


def test_cell_span_and_index_bounds() -> None:
    with pytest.raises(ValidationError):
        TableCellMeta(table_id=PAGE_ID, row_index=-1, column_index=0)
    with pytest.raises(ValidationError):
        TableCellMeta(table_id=PAGE_ID, row_index=0, column_index=0, row_span=0)


# --------------------------------------------------------------- equations, figures


def test_equation_without_mathml_is_valid_and_keeps_source() -> None:
    eq = EquationMeta(source_text="v = u + at", spoken_fallback="v equals u plus a t",
                      spoken_fallback_origin="human")
    assert eq.mathml is None and eq.source_text == "v = u + at"


def test_unreviewed_mathml_rejected() -> None:
    with pytest.raises(ValidationError, match="approved"):
        EquationMeta(mathml="<math><mi>x</mi></math>", mathml_review_status="needs_review")


def test_mathml_must_be_math_element() -> None:
    with pytest.raises(ValidationError, match="<math>"):
        EquationMeta(mathml="x + 1", mathml_review_status="approved")


def test_spoken_fallback_requires_origin() -> None:
    with pytest.raises(ValidationError, match="set together"):
        EquationMeta(spoken_fallback="x squared")


def test_figure_text_fields_are_separate(sample: dict[str, Any]) -> None:
    fig = next(b for b in Document.model_validate(sample).blocks if b.figure).figure
    assert fig is not None and fig.source_caption and fig.alt_text and fig.extended_description
    assert fig.alt_text.origin.value == "model_generated"
    assert fig.alt_text.review_status is ReviewStatus.NEEDS_REVIEW
    assert fig.extended_description.origin.value == "human"


def test_overlong_alt_text_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 250"):
        FigureMeta(alt_text={"text": "x" * 251, "language": "en", "origin": "human"})


def test_figure_caption_block_must_be_caption(sample: dict[str, Any]) -> None:
    _find(sample, "b3")["figure"]["caption_block_id"] = "7d1e4c52-0000-4000-8000-0000000000b2"
    _invalid(sample, "caption block")


# ---------------------------------------------------- revisions and required fields


@pytest.mark.parametrize("revision", [0, -1])
def test_non_positive_revision_rejected(revision: int) -> None:
    with pytest.raises(ValidationError, match="revision"):
        _block(revision=revision)


def test_revision_one_must_be_unedited() -> None:
    with pytest.raises(ValidationError, match="revision 1 is unedited"):
        _block(current_text="Edited")
    assert _block(current_text="Edited", revision=2).current_text == "Edited"


def test_correction_base_revision_must_precede_block_revision(sample: dict[str, Any]) -> None:
    sample["corrections"][0]["base_revision"] = 2
    _invalid(sample, "base_revision 2 must be below")


def test_correction_payload_matches_operation() -> None:
    with pytest.raises(ValidationError, match="requires 'new_text'"):
        Correction(document_id=PAGE_ID, block_id=PAGE_ID, base_revision=1,
                   operation="replace_text", created_at=NOW)
    with pytest.raises(ValidationError, match="does not accept 'new_language'"):
        Correction(document_id=PAGE_ID, block_id=PAGE_ID, base_revision=1, operation="replace_text",
                   new_text="x", new_language="hi", created_at=NOW)


@pytest.mark.parametrize("field", ["page_id", "block_type", "bbox", "language", "confidence", "provenance"])
def test_missing_required_block_field(field: str) -> None:
    data = _block().model_dump()
    del data[field]
    with pytest.raises(ValidationError, match="Field required"):
        Block.model_validate(data)


def test_text_block_requires_text() -> None:
    with pytest.raises(ValidationError, match="requires raw_text"):
        _block(raw_text=None, current_text=None)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        _block(confidence_pct=100)


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        Provenance(method="derived", created_at=datetime(2026, 1, 1))


def test_ocr_provenance_requires_engine_version() -> None:
    with pytest.raises(ValidationError, match="engine_version"):
        Provenance(method="ocr", engine="tesseract", created_at=NOW)


def test_block_on_unknown_page_rejected(sample: dict[str, Any]) -> None:
    _find(sample, "a1")["page_id"] = "7d1e4c52-0000-4000-8000-00000000dead"
    _invalid(sample, "unknown page")


def test_page_index_and_label_are_distinct(sample: dict[str, Any]) -> None:
    doc = Document.model_validate(sample)
    assert [(p.page_index, p.page_label) for p in doc.pages] == [(0, "48"), (1, "49")]
    bad = copy.deepcopy(sample)
    bad["pages"][1]["page_index"] = 0
    _invalid(bad, "duplicate page_index")
    sample["pages"][0]["page_index"] = -1
    _invalid(sample, "greater than or equal to 0")


@pytest.mark.parametrize("rotation", [45, 360])
def test_invalid_rotation_rejected(sample: dict[str, Any], rotation: int) -> None:
    sample["pages"][0]["rotation"] = rotation
    _invalid(sample, "rotation")


# ---------------------------------------------------------- serialization / schema


def test_sample_is_valid_bilingual_document(sample: dict[str, Any]) -> None:
    doc = Document.model_validate(sample)
    assert doc.schema_version == "1.0.0"  # kept at 1.0.0 as the backward-compatibility fixture
    assert SCHEMA_VERSION == "1.1.0"
    assert {b.language for b in doc.blocks} >= {Language.ENGLISH, Language.HINDI}


def test_wrong_schema_version_rejected(sample: dict[str, Any]) -> None:
    sample["schema_version"] = "2.0.0"
    _invalid(sample, "schema_version")


def test_committed_schema_is_current() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == render_json_schema(), \
        "run scripts/export_schema.py"


def test_schema_is_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(build_json_schema())


def test_sample_and_round_trip_validate_against_schema(sample: dict[str, Any]) -> None:
    validator = jsonschema.Draft202012Validator(build_json_schema(), format_checker=jsonschema.FormatChecker())
    validator.validate(sample)
    validator.validate(json.loads(Document.model_validate(sample).model_dump_json()))


@pytest.mark.parametrize(
    ("mutate", "path"),
    [
        (lambda d: d["blocks"][0].__setitem__("bbox", [0.1, 0.1, 1.5, 0.2]), "bbox"),
        (lambda d: d["blocks"][0].__setitem__("language", "hindi"), "language"),
        (lambda d: d["blocks"][0].__setitem__("revision", 0), "revision"),
        (lambda d: d["blocks"][0].pop("provenance"), "provenance"),
        (lambda d: d["blocks"][0].__setitem__("block_type", "sidebar"), "block_type"),
    ],
)
def test_schema_rejects_invalid_shapes(sample: dict[str, Any], mutate: Any, path: str) -> None:
    mutate(sample)
    validator = jsonschema.Draft202012Validator(build_json_schema())
    errors = list(validator.iter_errors(sample))
    assert errors, f"schema accepted invalid {path}"
