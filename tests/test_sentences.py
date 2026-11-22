import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.adapters.speech import segment
from app.api.content import block_ranges
from app.config import Settings
from app.services.sentences import sentence_ranges

FIXTURES = json.loads(
    Path(__file__).with_name("fixtures").joinpath("pathya-sentences-3.fixtures.json").read_bytes()
)


@pytest.mark.parametrize(
    "parts",
    [
        ["गति क्या है? ", "यह स्थिति में परिवर्तन है। ", "चाल 3.5 m/s है।"],
        ["See Fig. 2.1 for details. ", "It shows v = u + at."],
        ["1. Define speed. ", "2. Define velocity."],
        ['He said "Stop!" ', "Then he left."],
        ["  Read this (carefully!).\t", "Then read that॥  "],
        ["📚 A value of 3. ", "5 is joined. ", "Done"],
        ["A sentence without punctuation  "],
        ["  "],
        [],
    ],
)
def test_reader_sentence_ranges(parts):
    text = "".join(parts)
    ranges = sentence_ranges(text)
    assert [text[start:end] for start, end in ranges] == parts
    if ranges:
        assert ranges[0][0] == 0 and ranges[-1][1] == len(text)
        assert all(left[1] == right[0] for left, right in zip(ranges, ranges[1:], strict=False))


def test_builtin_speech_segmenter_uses_the_same_ranges_and_a_distinct_version():
    settings = Settings(_env_file=None, segmenter="pathya", segmenter_version="legacy")
    text = "📖 First.  Second."
    units = segment({"id": "block", "text_current": text, "lang": "en"}, settings)
    assert settings.active_segmenter_version == "pathya-sentences/3"
    assert [(unit.offset_start, unit.offset_end) for unit in units] == sentence_ranges(text)
    assert all(unit.text == text[unit.offset_start : unit.offset_end] for unit in units)


@pytest.mark.parametrize("case", FIXTURES["fixtures"], ids=lambda case: case["id"])
def test_p1_sentence_fixture(case: dict[str, Any]) -> None:
    text: str = case["text"]
    block = {"id": "block", "type": "paragraph", "text_current": text, "lang": "en"}
    settings = Settings(_env_file=None, segmenter="pathya")
    assert settings.active_segmenter_version == FIXTURES["segmenter"] == "pathya-sentences/3"
    ranges = block_ranges(block)
    assert ranges == case["ranges"]
    assert hashlib.sha256(text.encode()).hexdigest() == case["text_sha256"]
    assert len(text) == case["length_code_points"]
    assert len(text.encode("utf-16-le")) // 2 == case["length_utf16"]

    units = segment(block, settings)
    assert [(unit.offset_start, unit.offset_end) for unit in units] == [
        (r["start"], r["end"]) for r in ranges
    ]
    assert [unit.text for unit in units] == case["sentences"]
    assert "".join(unit.text for unit in units) == text
    assert [hashlib.sha256(unit.text.encode()).hexdigest() for unit in units] == case[
        "sentence_sha256"
    ]
    assert [
        {
            "start": len(text[: unit.offset_start].encode("utf-16-le")) // 2,
            "end": len(text[: unit.offset_end].encode("utf-16-le")) // 2,
        }
        for unit in units
    ] == case["utf16_ranges"]
