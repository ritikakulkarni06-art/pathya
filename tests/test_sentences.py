import pytest

from app.adapters.speech import segment
from app.config import Settings
from app.services.sentences import sentence_ranges


@pytest.mark.parametrize(
    "parts",
    [
        ["गति क्या है? ", "यह स्थिति में परिवर्तन है। ", "चाल 3.5 m/s है।"],
        ["See Fig. 2.1 for details. ", "It shows v = u + at."],
        ["1. Define speed. ", "2. Define velocity."],
        ['He said "Stop!" ', "Then he left."],
        ["  Read this (carefully!).\t", "Then read that॥  "],
        ["📚 A value of 3. 5 is joined. ", "Done"],
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
    assert settings.active_segmenter_version == "pathya-reader-v1"
    assert [(unit.offset_start, unit.offset_end) for unit in units] == sentence_ranges(text)
    assert all(unit.text == text[unit.offset_start : unit.offset_end] for unit in units)
