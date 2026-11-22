"""pathya-sentences/3: fixtures, reference implementation and the P3 bulk-response checker."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from pathya_document_ai.models import Document, upgrade_document_data
from pathya_document_ai.sentences import (
    SEGMENTER,
    check_sentence_ranges_response,
    coverage_problems,
    document_sentence_ranges,
    segment_sentences,
    text_sha256,
    to_utf16_ranges,
)

ROOT = Path(__file__).resolve().parents[2]
SEGMENTATION = ROOT / "contract" / "segmentation"
FIXTURES = json.loads((SEGMENTATION / "pathya-sentences-3.fixtures.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((SEGMENTATION / "example_sentence_ranges_response.json").read_text(encoding="utf-8"))


def _generator() -> Any:
    spec = importlib.util.spec_from_file_location("make_segmentation_fixtures",
                                                  ROOT / "scripts" / "make_segmentation_fixtures.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sample() -> Document:
    data = json.loads((ROOT / "contract" / "samples" / "sample_document_en_hi.json").read_text(encoding="utf-8"))
    return Document.model_validate(upgrade_document_data(data))


# ------------------------------------------------------------------ fixtures


def test_fixture_file_describes_pathya_sentences_3() -> None:
    assert FIXTURES["segmenter"] == SEGMENTER == "pathya-sentences/3"
    assert FIXTURES["offset_unit"] == "unicode_code_point"
    categories = {f["category"] for f in FIXTURES["fixtures"]}
    assert categories >= {"regression", "list_marker", "roman_numeral", "lettered_item", "devanagari",
                          "abbreviation", "guillemet"}
    assert {"pp.", "ch.", "vol.", "figs.", "cf."} <= set(FIXTURES["abbreviations"])


@pytest.mark.parametrize("fixture", FIXTURES["fixtures"], ids=lambda f: f["id"])
def test_fixture_matches_reference_implementation(fixture: dict[str, Any]) -> None:
    text = fixture["text"]
    ranges = [(r["start"], r["end"]) for r in fixture["ranges"]]
    assert segment_sentences(text) == ranges
    assert [text[s:e] for s, e in ranges] == fixture["sentences"]
    assert coverage_problems(text, ranges) == []
    assert fixture["text_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest() == text_sha256(text)
    assert fixture["sentence_sha256"] == [hashlib.sha256(s.encode("utf-8")).hexdigest() for s in fixture["sentences"]]
    assert fixture["length_code_points"] == len(text)
    assert [(r["start"], r["end"]) for r in fixture["utf16_ranges"]] == to_utf16_ranges(text, ranges)
    assert fixture["length_utf16"] == len(text.encode("utf-16-le")) // 2


def test_existing_regression_cases_are_all_fixtures() -> None:
    texts = {f["text"] for f in FIXTURES["fixtures"]}
    for text in ["1. Distance is the length of the path travelled.", "2. Displacement is shortest. It has direction.",
                 "iv. Roman numbered item.", "a. Lettered item.", "He saw it. A dog ran.",
                 "10. Tenth item. Second sentence.", "1) Bracket item. More.", "Step 3. Mix well.",
                 "१. प्रकाश सीधी रेखा में चलता है। यह परावर्तित होता है।", "  Lead. Tail  ", "", "No terminator",
                 "Speed is 4.5 m/s.  वेग दिशा बताता है। See Fig. 4.2 next.", "𝑥 = 2. Next."]:
        assert text in texts, text


def test_generated_files_are_current() -> None:
    files = _generator().build()  # raises if a hand-written expectation disagrees with the implementation
    for name, text in files.items():
        assert (SEGMENTATION / name).read_text(encoding="utf-8") == text, f"run scripts/make_segmentation_fixtures.py ({name})"
    assert sorted(p.name for p in SEGMENTATION.iterdir()) == sorted(files)


def test_p3_reader_test_example_agrees() -> None:
    """P3's own bulk-route test text (person-3 14d9aee, tests/test_reader_handoff.py)."""
    text = "\U0001f4da First.  Second."
    assert segment_sentences(text) == [(0, 10), (10, 17)]


# ----------------------------------------------------- bulk response checker


def test_example_response_conforms() -> None:
    doc = _sample()
    assert EXAMPLE == document_sentence_ranges(doc, 3)
    assert check_sentence_ranges_response(EXAMPLE, doc, document_revision=3) == []
    assert {e["block_id"] for e in EXAMPLE["blocks"]} == {str(b.id) for b in doc.blocks}  # every current block
    empty = [e for e in EXAMPLE["blocks"] if e["text_sha256"] == hashlib.sha256(b"").hexdigest()]
    assert empty and all(e["ranges"] == [] for e in empty)  # null current_text hashes as ""


def _broken(change: Any) -> list[str]:
    response = copy.deepcopy(EXAMPLE)
    change(response)
    return check_sentence_ranges_response(response, _sample(), document_revision=3)


def _first_split(response: dict[str, Any]) -> dict[str, Any]:
    return next(e for e in response["blocks"] if e["ranges"])


@pytest.mark.parametrize(("change", "message"), [
    (lambda r: r.update(document_revision=2), "does not match the content revision"),
    (lambda r: r.update(document_revision=-1), "non-negative"),
    (lambda r: r["blocks"].pop(), "missing"),
    (lambda r: r["blocks"].append(dict(r["blocks"][0])), "more than once"),
    (lambda r: r["blocks"][0].update(block_id="p3-unknown"), "not a current block"),
    (lambda r: _first_split(r).update(text_sha256="0" * 64), "text_sha256"),
    (lambda r: _first_split(r)["ranges"][0].update(start=1), "gap or overlap"),
    (lambda r: _first_split(r)["ranges"][-1].update(end=_first_split(r)["ranges"][-1]["end"] - 1), "text length"),
    (lambda r: _first_split(r).update(ranges=[]), "at least one range"),
    (lambda r: next(e for e in r["blocks"] if not e["ranges"] and e["text_sha256"] != hashlib.sha256(b"").hexdigest())
     .update(ranges=[{"start": 0, "end": 1}]), "no sentence ranges"),
    (lambda r: _first_split(r).update(segmenter=""), "segmenter is missing"),
])
def test_checker_reports_each_violation(change: Any, message: str) -> None:
    problems = _broken(change)
    assert any(message in p for p in problems), problems


def test_checker_compares_exact_ranges_only_for_the_reference_segmenter() -> None:
    doc = _sample()
    text = "One. Two. Three."
    block = next(b for b in doc.blocks if b.block_type.value == "paragraph")
    data = doc.model_dump(mode="json")
    for b in data["blocks"]:
        if b["id"] == str(block.id):
            b["raw_text"] = b["current_text"] = text
    doc = Document.model_validate(data)
    response = document_sentence_ranges(doc, 3)
    entry = next(e for e in response["blocks"] if e["block_id"] == str(block.id))
    entry["ranges"] = [{"start": 0, "end": 9}, {"start": 9, "end": 16}]  # full coverage, different split
    assert any("differ from the pathya-sentences/3 reference" in p for p in check_sentence_ranges_response(response, doc))
    entry["segmenter"] = "pathya-reader-v1"  # another segmenter: only the coverage rules apply
    assert check_sentence_ranges_response(response, doc) == []
