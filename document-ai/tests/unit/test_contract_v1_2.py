"""Contract 1.2.0: producer fields, backend integration fields, sentences, audio,
critical-symbol uncertainty, correction policy and version boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError
import pytest

from pathya_document_ai.corrections import CorrectionConflictError, CorrectionError, apply_correction
from pathya_document_ai.critical import critical_flag, critical_uncertain, is_critical_token, is_trusted_evidence
from pathya_document_ai.models import (
    CONTRACT_FAMILY,
    AudioReference,
    BlockIntegration,
    SCHEMA_VERSION,
    BlockRole,
    BlockType,
    Correction,
    Document,
    IncompatibleVersionError,
    QualityFlag,
    ReviewStatus,
    export_document_data,
    pipeline_review_status,
    required_version,
    upgrade_document_data,
)
from pathya_document_ai.schema import build_json_schema
from pathya_document_ai.sentences import SEGMENTER, attach_sentences, segment_sentences, to_utf16_ranges

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
CONFORMANCE = ROOT / "contract" / "conformance"

# Hashes of the artifacts published at 39331e4 (P3 integrates against these). Line endings normalized.
FROZEN_SHA256 = {
    "contract/schemas/pathya_content.v1.0.0.schema.json": "5542a4e0718ce092f2fb68b5ce590bffbcac1f6f21b11011160ae250cf9ebdd3",
    "contract/schemas/pathya_content.v1.1.0.schema.json": "1fbad2da07ec8cb155c0c5be9d6fcbc7448ebb5f8353415f9bed0683bf3c28e5",
    "contract/pathya_content.schema.json": "1fbad2da07ec8cb155c0c5be9d6fcbc7448ebb5f8353415f9bed0683bf3c28e5",
    "src/pathya_document_ai/frozen_schemas/pathya_content.v1.0.0.schema.json": "5542a4e0718ce092f2fb68b5ce590bffbcac1f6f21b11011160ae250cf9ebdd3",
    "src/pathya_document_ai/frozen_schemas/pathya_content.v1.1.0.schema.json": "1fbad2da07ec8cb155c0c5be9d6fcbc7448ebb5f8353415f9bed0683bf3c28e5",
    "contract/conformance/index.json": "ce600043fe1978bfa5d373a84f7706edbe32022578894b151f9f0126412f8522",
    "contract/conformance/valid_v1_0_0_sample.json": "34a414e6ddfc7f6e2b14695155a3314391bab542b82ee45c7afcd29cdb414689",
    "contract/conformance/valid_v1_1_0_status_and_flags.json": "f44a5f3cc8515fd3d0bbb8c6a632ceb7390d037401f7be6bd80455b026e43f94",
    "contract/conformance/valid_v1_1_0_uncertain_table.json": "83652627d9311b3ef977b576041ff301b26fd921f190c9cfb7938e551629eea4",
    "contract/samples/sample_document_en_hi.json": "81b8cab1de3058a3b270476be7c5d38b91cfd2f5671cee7daaf44c2fc5e12ec2",
}
THREE_PAYLOADS = ["valid_v1_0_0_sample.json", "valid_v1_1_0_status_and_flags.json", "valid_v1_1_0_uncertain_table.json"]


def _load(name: str) -> dict[str, Any]:
    return json.loads((CONFORMANCE / name).read_text(encoding="utf-8"))


def _v12() -> Document:
    return Document.model_validate(upgrade_document_data(_load("valid_v1_0_0_sample.json")))


def _block(doc: Document, suffix: str) -> Any:
    return next(b for b in doc.blocks if str(b.id).endswith(suffix))


def _replace(doc: Document, block: Any) -> Document:
    data = doc.model_dump()
    data["blocks"] = [block.model_dump() if b["id"] == block.id else b for b in data["blocks"]]
    return Document.model_validate(data)


def _correction(doc: Document, block: Any, **kw: Any) -> Correction:
    return Correction(document_id=doc.id, block_id=block.id, base_revision=block.revision, created_at=NOW, **kw)


def _schema(version: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(build_json_schema(version), format_checker=jsonschema.FormatChecker())


# --------------------------------------------------------- frozen 1.1.0 baseline


@pytest.mark.parametrize("path", sorted(FROZEN_SHA256))
def test_published_v1_1_artifacts_are_byte_identical(path: str) -> None:
    data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == FROZEN_SHA256[path]


@pytest.mark.parametrize("name", THREE_PAYLOADS)
def test_three_existing_payloads_valid_as_is_and_after_upgrade(name: str) -> None:
    data = _load(name)
    assert Document.model_validate(data).schema_version == data["schema_version"]
    assert _schema("1.1.0").is_valid(data) and _schema("1.2.0").is_valid(data)
    upgraded = json.loads(json.dumps(upgrade_document_data(data), default=str))
    doc = Document.model_validate(upgraded)
    assert doc.schema_version == "1.2.0" and doc.contract_family == CONTRACT_FAMILY
    assert all(b.role is BlockRole.BODY and b.heading_level is None and b.integration is None for b in doc.blocks)
    _schema("1.2.0").validate(upgraded)
    assert not _schema("1.1.0").is_valid(upgraded)  # 1.1.0-only readers reject 1.2.0 (not forward-compatible)


def test_old_vectors_keep_their_verdicts_under_the_1_2_schema() -> None:
    index = json.loads((CONFORMANCE / "index.json").read_text(encoding="utf-8"))
    for vector in index["vectors"]:
        doc = _load(vector["file"])
        # The 1.2.0 schema applies the same rules to 1.0.0/1.1.0 documents as the frozen 1.1.0 schema.
        assert _schema("1.2.0").is_valid(doc) == vector["expected_valid"]["schema_1_1_0"], vector["file"]


# ------------------------------------------------------------- producer fields


def test_contract_family_required_in_1_2() -> None:
    data = upgrade_document_data(_load("valid_v1_0_0_sample.json"))
    data.pop("contract_family")
    with pytest.raises(ValidationError, match="contract_family"):
        Document.model_validate(data)
    assert not _schema("1.2.0").is_valid(json.loads(json.dumps(data, default=str)))


def test_heading_level_only_on_headings() -> None:
    doc = _v12()
    heading = _block(doc, "a1").model_copy(update={"heading_level": 2})
    assert _replace(doc, heading).blocks[0].heading_level == 2
    with pytest.raises(ValidationError, match="heading_level"):
        _replace(doc, _block(doc, "a2").model_copy(update={"heading_level": 1}))
    for bad in (0, 7):
        with pytest.raises(ValidationError):
            data = doc.model_dump(mode="json")
            data["blocks"][0]["heading_level"] = bad
            Document.model_validate(data)


@pytest.mark.parametrize("role", ["body", "page_header", "page_footer", "footnote"])
def test_semantic_roles(role: str) -> None:
    doc = _replace(_v12(), _block(_v12(), "a2").model_copy(update={"role": BlockRole(role)}))
    assert {b.role for b in doc.blocks} >= {BlockRole(role)}
    _schema("1.2.0").validate(json.loads(doc.model_dump_json()))


def test_role_required_in_1_2_and_forbidden_beyond_body_in_1_1() -> None:
    data = upgrade_document_data(_load("valid_v1_0_0_sample.json"))
    data["blocks"][0]["role"] = None
    with pytest.raises(ValidationError, match="role"):
        Document.model_validate(data)
    old = _load("valid_v1_1_0_status_and_flags.json")
    old["blocks"][0]["role"] = "page_footer"
    with pytest.raises(ValidationError, match="1.2.0 features"):
        Document.model_validate(old)
    assert not _schema("1.2.0").is_valid(old)


def test_upgrade_derives_roles_from_layout_labels() -> None:
    data = _load("valid_v1_1_0_status_and_flags.json")
    data["blocks"][0]["provenance"]["parameters"]["layout_label"] = "page_header"
    data["blocks"][1]["provenance"]["parameters"]["layout_label"] = "Page-footer"
    up = Document.model_validate(upgrade_document_data(data))
    assert [up.blocks[0].role, up.blocks[1].role, up.blocks[2].role] == [
        BlockRole.PAGE_HEADER, BlockRole.PAGE_FOOTER, BlockRole.BODY]


@pytest.mark.parametrize(("flags", "status"), [
    ([], ReviewStatus.UNREVIEWED),
    ([QualityFlag.LANGUAGE_UNCERTAIN, QualityFlag.MIXED_SCRIPT], ReviewStatus.UNREVIEWED),
    ([QualityFlag.READING_ORDER_UNCERTAIN], ReviewStatus.NEEDS_REVIEW),  # written P1 decision
    ([QualityFlag.MISSING_GEOMETRY], ReviewStatus.NEEDS_REVIEW),
    ([QualityFlag.CRITICAL_SYMBOL_UNCERTAIN], ReviewStatus.NEEDS_REVIEW),
    ([QualityFlag.LOW_CONFIDENCE], ReviewStatus.NEEDS_REVIEW),
    ([QualityFlag.TABLE_STRUCTURE_UNCERTAIN], ReviewStatus.NEEDS_REVIEW),
])
def test_pipeline_review_status_rule(flags: list[QualityFlag], status: ReviewStatus) -> None:
    assert pipeline_review_status(flags) is status


# ------------------------------------------------- critical-symbol uncertainty


@pytest.mark.parametrize(("token", "previous", "critical"), [
    ("4.5", None, True), ("m/s", "4.5", True), ("−3", None, True), ("x²", None, True), ("=", None, True),
    ("10^3", None, True), ("30°C", None, True), ("kg", "5", True), ("Speed", None, False), ("m", "the", False),
    ("2024", None, False),
])
def test_critical_tokens(token: str, previous: str | None, critical: bool) -> None:
    assert is_critical_token(token, previous) is critical


def test_critical_uncertainty_rules() -> None:
    assert critical_uncertain([("v", "ocr", 0.99), ("=", "ocr", 0.95), ("4.5", "ocr", 0.72)])
    assert critical_uncertain([("4.5", "ocr", None)])  # missing confidence is uncertain
    assert not critical_uncertain([("4.5", "ocr", 0.97), ("m/s", "ocr", 0.95)])
    assert not critical_uncertain([("4.5", "native", None)])  # native digits are reliable
    assert critical_uncertain([("4�5", "native", None)])  # undecodable glyph inside a number
    assert critical_uncertain([("v", "ocr", 0.99), ("u", "ocr", 0.99)], equation=True)  # OCR maths always


def test_critical_block_cannot_be_unreviewed_and_flag_is_kept_after_approval() -> None:
    doc = _v12()
    para = _block(doc, "a2")
    flagged = para.model_copy(update={"quality_flags": [QualityFlag.CRITICAL_SYMBOL_UNCERTAIN],
                                      "review_status": ReviewStatus.UNREVIEWED})
    with pytest.raises(ValidationError, match="critical_symbol_uncertain"):
        _replace(doc, flagged)
    bad = json.loads(_replace(doc, flagged.model_copy(update={"review_status": ReviewStatus.NEEDS_REVIEW}))
                     .model_dump_json())
    bad["blocks"][1]["review_status"] = "unreviewed"
    assert not _schema("1.2.0").is_valid(bad)  # also enforced in JSON Schema

    doc = _replace(doc, flagged.model_copy(update={"review_status": ReviewStatus.NEEDS_REVIEW}))
    page = doc.pages[0]
    block = _block(doc, "a2")
    assert critical_flag(block) and not is_trusted_evidence(block, page)
    approved = apply_correction(doc, _correction(doc, block, operation="set_review_status",
                                                 new_review_status="approved", author_ref="reviewer:1"))
    block = _block(approved, "a2")
    assert QualityFlag.CRITICAL_SYMBOL_UNCERTAIN in block.quality_flags  # original flag preserved
    assert not critical_flag(block) and is_trusted_evidence(block, approved.pages[0])


def test_incomplete_pages_are_never_trusted_evidence() -> None:
    doc = _v12()
    block = _block(doc, "a2")
    for status in ("needs_ocr", "partial", "failed"):
        page = doc.pages[0].model_copy(update={"status": status})
        assert not is_trusted_evidence(block, page)
    assert is_trusted_evidence(block, doc.pages[0])


# ------------------------------------------------------------- sentence offsets


def _covers(text: str, ranges: list[tuple[int, int]]) -> bool:
    return (not text and not ranges) or (ranges[0][0] == 0 and ranges[-1][1] == len(text)
                                         and all(a[1] == b[0] for a, b in zip(ranges, ranges[1:])))


def test_sentence_offsets_cover_current_text_with_trailing_whitespace_to_preceding_range() -> None:
    text = "Speed is 4.5 m/s.  वेग दिशा बताता है। See Fig. 4.2 next."
    ranges = segment_sentences(text)
    assert [text[s:e] for s, e in ranges] == ["Speed is 4.5 m/s.  ", "वेग दिशा बताता है। ", "See Fig. 4.2 next."]
    assert _covers(text, ranges)  # no gaps: every code point belongs to exactly one range
    assert segment_sentences("  Lead. Tail  ") == [(0, 8), (8, 14)]  # leading ws -> first, trailing -> previous
    assert segment_sentences("") == [] and segment_sentences("No terminator") == [(0, 13)]
    astral = "𝑥 = 2. Next."
    assert segment_sentences(astral) == [(0, 7), (7, 12)]  # code points
    assert to_utf16_ranges(astral, segment_sentences(astral)) == [(0, 8), (8, 13)]  # JavaScript indices


@pytest.mark.parametrize(("text", "expected"), [
    ("1. Distance is the length of the path travelled.", ["1. Distance is the length of the path travelled."]),
    ("2. Displacement is shortest. It has direction.", ["2. Displacement is shortest. ", "It has direction."]),
    ("iv. Roman numbered item.", ["iv. Roman numbered item."]),
    ("a. Lettered item.", ["a. Lettered item."]),
    ("He saw it. A dog ran.", ["He saw it. ", "A dog ran."]),
])
def test_list_markers_are_not_sentences(text: str, expected: list[str]) -> None:
    assert [text[s:e] for s, e in segment_sentences(text)] == expected


def test_sentences_bound_to_revision_and_exact_text() -> None:
    doc = _v12()
    block = attach_sentences(_block(doc, "a2"))
    seg = block.integration.sentences
    assert seg.segmenter == SEGMENTER == "pathya-sentences/2" and seg.text_revision == block.revision
    assert seg.text_sha256 == hashlib.sha256(block.current_text.encode("utf-8")).hexdigest()
    assert _covers(block.current_text, [(r.start, r.end) for r in seg.ranges])
    doc = _replace(doc, block)
    stale = block.model_copy(update={"current_text": block.current_text + " Extra.", "revision": 2})
    with pytest.raises(ValidationError, match="stale sentence ranges"):
        _replace(doc, stale)


@pytest.mark.parametrize(("ranges", "match"), [
    ([{"start": 1, "end": 10}], "without gaps"),        # does not start at 0
    ([{"start": 0, "end": 5}, {"start": 6, "end": 10}], "without gaps"),  # gap
    ([{"start": 0, "end": 5}], "must end at"),          # stops short of the text
    ([{"start": 0, "end": 10_000}], "must end at"),     # beyond the text
])
def test_sentence_ranges_must_cover_without_gaps(ranges: list[dict[str, int]], match: str) -> None:
    doc = _replace(_v12(), attach_sentences(_block(_v12(), "a2")))
    data = json.loads(doc.model_dump_json())
    data["blocks"][1]["integration"]["sentences"]["ranges"] = ranges
    with pytest.raises(ValidationError, match=match):
        Document.model_validate(data)


def test_sentence_ranges_only_on_headings_paragraphs_and_list_items() -> None:
    from pathya_document_ai.sentences import build_segmentation

    doc = _v12()
    for suffix in ("a1", "a2", "b5"):  # heading, paragraph, list item
        assert build_segmentation(_block(doc, suffix)) is not None
    caption, cell = _block(doc, "a9"), _block(doc, "a5")
    assert build_segmentation(caption) is None and build_segmentation(cell) is None
    from pathya_document_ai.models import SentenceSegmentation

    forced = SentenceSegmentation(
        text_revision=caption.revision, segmenter=SEGMENTER,
        text_sha256=hashlib.sha256(caption.current_text.encode("utf-8")).hexdigest(),
        ranges=[{"start": 0, "end": len(caption.current_text)}])
    with pytest.raises(ValidationError, match="only allowed on headings"):
        _replace(doc, caption.model_copy(update={"integration": BlockIntegration(sentences=forced)}))


def test_offsets_regenerated_after_text_correction() -> None:
    doc = _v12()
    doc = _replace(doc, attach_sentences(_block(doc, "a1")))
    block = _block(doc, "a1")
    corrected = apply_correction(doc, _correction(doc, block, operation="replace_text",
                                                  new_text="4.2 Equations of Motion. Revised."))
    after = _block(corrected, "a1")
    assert after.revision == 2 and after.integration is None  # stale ranges removed by the correction
    regenerated = attach_sentences(after)
    assert regenerated.integration.sentences.text_revision == 2
    assert [after.current_text[r.start:r.end] for r in regenerated.integration.sentences.ranges] == [
        "4.2 Equations of Motion. ", "Revised."]
    assert after.raw_text == "4.2 Equations of Motion"  # offsets never index raw_text


def _with_audio(doc: Document, suffix: str, voice: str | None = "en", sentences: bool = True,
                backend_id: str | None = "p3-blk-1") -> Document:
    block = _block(doc, suffix)
    block = attach_sentences(block) if sentences else block.model_copy(update={"integration": BlockIntegration()})
    clip = AudioReference(key=f"{suffix}-r{block.revision}-s0", url="audio://p3/opaque-1", bytes=48213,
                          text_revision=block.revision,
                          text_sha256=hashlib.sha256(block.current_text.encode("utf-8")).hexdigest())
    integration = block.integration.model_copy(update={"audio": [clip], "voice_language": voice,
                                                       "backend_block_id": backend_id})
    return _replace(doc, block.model_copy(update={"integration": integration}))


def test_audio_entries_are_key_url_bytes_and_unique() -> None:
    doc = _with_audio(_v12(), "a2")
    data = json.loads(doc.model_dump_json())
    clip = data["blocks"][1]["integration"]["audio"][0]
    assert set(clip) == {"key", "url", "bytes", "text_revision", "text_sha256"}
    data["blocks"][1]["integration"]["audio"].append(dict(clip))
    with pytest.raises(ValidationError, match="unique"):
        Document.model_validate(data)
    legacy = json.loads(doc.model_dump_json())
    legacy["blocks"][1]["integration"]["audio"][0]["uri"] = legacy["blocks"][1]["integration"]["audio"][0].pop("url")
    with pytest.raises(ValidationError):
        Document.model_validate(legacy)
    assert not _schema("1.2.0").is_valid(legacy)


def test_audio_is_invalidated_when_the_revision_changes() -> None:
    whole = _with_audio(_v12(), "a2", sentences=False)
    block = _block(whole, "a2")
    with pytest.raises(ValidationError, match="stale audio"):
        _replace(whole, block.model_copy(update={"revision": 2, "current_text": block.current_text + "!"}))
    with pytest.raises(ValidationError, match="stale audio"):  # same text, new revision: still stale
        _replace(whole, block.model_copy(update={"revision": 2}))

    doc = _with_audio(_v12(), "a2")
    block = _block(doc, "a2")
    corrected = apply_correction(doc, _correction(doc, block, operation="set_language", new_language="mul"))
    after = _block(corrected, "a2")
    assert after.integration.audio == [] and after.integration.sentences is None  # any revision change
    assert after.integration.voice_language == "en"  # a reader choice, not derived from the text
    assert after.integration.backend_block_id == "p3-blk-1"  # P3 identity survives corrections


def test_backend_block_id_is_p3_owned_and_optional() -> None:
    doc = _with_audio(_v12(), "a2", backend_id="p3-blk-a2")
    assert _block(doc, "a2").integration.backend_block_id == "p3-blk-a2"
    assert _block(doc, "a2").id != "p3-blk-a2"  # separate from the producer UUID
    with pytest.raises(ValidationError):
        data = json.loads(doc.model_dump_json())
        data["blocks"][1]["integration"]["backend_block_id"] = ""
        Document.model_validate(data)


def test_voice_language_never_replaces_language() -> None:
    doc = _with_audio(_v12(), "a2", voice="hi")
    block = _block(doc, "a2")
    assert block.language.value == "en" and block.integration.voice_language == "hi"
    with pytest.raises(ValidationError):
        data = json.loads(doc.model_dump_json())
        data["blocks"][1]["integration"]["voice_language"] = "mul"  # voices are en/hi only
        Document.model_validate(data)


# ----------------------------------------------------------- correction policy


def test_block_type_correction_keeps_id_and_provenance() -> None:
    doc = _v12()
    block = _block(doc, "a2")
    out = apply_correction(doc, _correction(doc, block, operation="set_block_type", new_block_type="heading"))
    after = _block(out, "a2")
    assert after.id == block.id and after.block_type is BlockType.HEADING and after.heading_level is None
    assert after.provenance == block.provenance and after.raw_text == block.raw_text
    assert after.revision == 2 and after.review_status is block.review_status  # never changed implicitly
    assert out.corrections[-1].operation.value == "set_block_type"
    for bad_type in ("table", "figure"):
        with pytest.raises((CorrectionError, ValidationError)):
            apply_correction(doc, _correction(doc, block, operation="set_block_type", new_block_type=bad_type))


def test_linked_caption_cannot_be_retyped_silently() -> None:
    doc = _v12()
    caption = _block(doc, "a9")  # caption_of -> table a4
    with pytest.raises(CorrectionError, match="caption link"):
        apply_correction(doc, _correction(doc, caption, operation="set_block_type", new_block_type="paragraph"))
    figure_caption = _block(doc, "b4")  # referenced by figure b3's caption_block_id
    with pytest.raises(CorrectionError, match="caption link"):
        apply_correction(doc, _correction(doc, figure_caption, operation="set_block_type", new_block_type="heading"))


def test_reading_order_correction_renumbers_siblings_and_rebuilds_precedes() -> None:
    doc = _v12()
    page0 = doc.pages[0].id
    top = sorted((b for b in doc.blocks if b.page_id == page0 and b.parent_id is None), key=lambda b: b.reading_order)
    moved = top[2]
    out = apply_correction(doc, _correction(doc, moved, operation="set_reading_order", new_reading_order=0))
    after = sorted((b for b in out.blocks if b.page_id == page0 and b.parent_id is None), key=lambda b: b.reading_order)
    assert [b.id for b in after] == [moved.id, top[0].id, top[1].id, *[b.id for b in top[3:]]]
    assert [b.reading_order for b in after] == list(range(len(after)))
    assert _block(out, str(moved.id)[-2:]).revision == 2
    assert all(b.revision == 1 for b in after[1:3])  # siblings renumbered without a revision change
    precedes = [(e.source_id, e.target_id) for e in out.edges if e.edge_type.value == "precedes"]
    assert (moved.id, top[0].id) in precedes
    with pytest.raises(CorrectionError):
        apply_correction(doc, _correction(doc, moved, operation="set_reading_order", new_reading_order=99))


def test_correction_conflicts_and_text_rules() -> None:
    doc = _v12()
    block = _block(doc, "a2")
    stale = Correction(document_id=doc.id, block_id=block.id, base_revision=5, operation="replace_text",
                       new_text="x", created_at=NOW)
    with pytest.raises(CorrectionConflictError):
        apply_correction(doc, stale)
    figure = _block(doc, "b3")
    with pytest.raises(CorrectionError, match="without text"):
        apply_correction(doc, _correction(doc, figure, operation="replace_text", new_text="invented"))
    old = Document.model_validate(_load("valid_v1_1_0_status_and_flags.json"))
    with pytest.raises(CorrectionError, match="upgrade"):
        apply_correction(old, _correction(old, old.blocks[1], operation="replace_text", new_text="x"))


# ----------------------------------------------------- versions and exports


def test_backend_fields_block_export_to_1_1_and_heading_levels_need_explicit_drop() -> None:
    doc = _replace(_v12(), _block(_v12(), "a1").model_copy(update={"heading_level": 1}))
    assert required_version(doc) == "1.2.0"
    with pytest.raises(IncompatibleVersionError, match="heading_level"):
        export_document_data(doc, "1.1.0")
    v11 = export_document_data(doc, "1.1.0", drop={"heading_level"})
    assert "heading_level" not in v11["blocks"][0] and "contract_family" not in v11
    _schema("1.1.0").validate(v11)
    with pytest.raises(IncompatibleVersionError, match="integration"):
        export_document_data(_with_audio(_v12(), "a2"), "1.1.0", drop={"heading_level", "role"})
    with pytest.raises(ValueError, match="only heading_level and role"):
        export_document_data(doc, "1.1.0", drop={"integration"})


def test_critical_flag_cannot_be_exported_to_1_1() -> None:
    doc = _v12()
    flagged = _block(doc, "a2").model_copy(update={"quality_flags": [QualityFlag.CRITICAL_SYMBOL_UNCERTAIN],
                                                    "review_status": ReviewStatus.NEEDS_REVIEW})
    with pytest.raises(IncompatibleVersionError, match="critical_symbol_uncertain"):
        export_document_data(_replace(doc, flagged), "1.1.0", drop={"heading_level", "role"})


def test_upgrade_never_downgrades_and_round_trips() -> None:
    doc = _v12()
    with pytest.raises(ValueError, match="cannot go from 1.2.0 down"):
        upgrade_document_data(json.loads(doc.model_dump_json()), "1.1.0")
    data = export_document_data(doc)
    assert data["schema_version"] == SCHEMA_VERSION and Document.model_validate(data) == doc


def test_producer_fields_survive_serialization() -> None:
    doc = _with_audio(_replace(_v12(), _block(_v12(), "a1").model_copy(
        update={"heading_level": 2, "role": BlockRole.PAGE_HEADER})), "a2")
    again = Document.model_validate_json(doc.model_dump_json())
    assert again == doc
    a1 = _block(again, "a1")
    assert (a1.heading_level, a1.role) == (2, BlockRole.PAGE_HEADER)
    clip = _block(again, "a2").integration.audio[0]
    assert (clip.key, clip.url, clip.bytes) == ("a2-r1-s0", "audio://p3/opaque-1", 48213)
    assert _block(again, "a2").integration.backend_block_id == "p3-blk-1"


# ------------------------------------------------------ 1.2.0 conformance set

V12 = CONFORMANCE / "v1.2.0"


def _v12_vectors() -> list[dict[str, Any]]:
    return json.loads((V12 / "index.json").read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("vector", _v12_vectors(), ids=lambda v: v["file"])
def test_v1_2_conformance_vectors(vector: dict[str, Any]) -> None:
    doc = json.loads((V12 / vector["file"]).read_text(encoding="utf-8"))
    got = {f"schema_{v.replace('.', '_')}": _schema(v).is_valid(doc) for v in ("1.0.0", "1.1.0", "1.2.0")}
    try:
        Document.model_validate(doc)
        got["python"] = True
    except ValidationError:
        got["python"] = False
    assert got == vector["expected_valid"], vector["description"]
