"""Regenerate contract/segmentation/: pathya-sentences/3 fixtures and the bulk-response example.

Every fixture's expected sentences are written by hand below. The script
derives code-point offsets, UTF-16 offsets and SHA-256 hashes from them and
refuses to write (or ``--check`` fails) if the reference implementation
(``pathya_document_ai.sentences``) produces different ranges. So the fixtures
are an independent statement of the rules, not a dump of the implementation.

Usage: python scripts/make_segmentation_fixtures.py [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from pathya_document_ai.models import Document, upgrade_document_data
from pathya_document_ai.sentences import (
    ABBREVIATIONS,
    SEGMENTER,
    document_sentence_ranges,
    segment_sentences,
    text_sha256,
    to_utf16_ranges,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contract" / "segmentation"
FIXTURES = "pathya-sentences-3.fixtures.json"
EXAMPLE = "example_sentence_ranges_response.json"
SAMPLE = ROOT / "contract" / "samples" / "sample_document_en_hi.json"
EXAMPLE_REVISION = 3

# (id, category, text, expected sentences). "".join(sentences) must equal text.
CASES: list[tuple[str, str, str, list[str]]] = [
    # --- regression cases kept from pathya-sentences/2 (tests/unit/test_contract_v1_2.py)
    ("regression_mixed_script_decimal", "regression", "Speed is 4.5 m/s.  वेग दिशा बताता है। See Fig. 4.2 next.",
     ["Speed is 4.5 m/s.  ", "वेग दिशा बताता है। ", "See Fig. 4.2 next."]),
    ("regression_leading_trailing_space", "regression", "  Lead. Tail  ", ["  Lead. ", "Tail  "]),
    ("regression_empty", "regression", "", []),
    ("regression_no_terminator", "regression", "No terminator", ["No terminator"]),
    ("regression_astral_code_points", "regression", "𝑥 = 2. Next.", ["𝑥 = 2. ", "Next."]),
    ("regression_corrected_heading", "regression", "4.2 Equations of Motion. Revised.",
     ["4.2 Equations of Motion. ", "Revised."]),
    ("regression_simple_two", "regression", "He saw it. A dog ran.", ["He saw it. ", "A dog ran."]),
    ("regression_ends_with_space", "regression", "Ends with space. ", ["Ends with space. "]),
    ("regression_quote_closer", "regression", 'He said "stop." Then left.', ['He said "stop." ', "Then left."]),
    ("regression_decimal_unit", "regression", "Total is 4.5 m. Next.", ["Total is 4.5 m. ", "Next."]),
    ("regression_p3_reader_emoji", "regression", "\U0001f4da First.  Second.", ["\U0001f4da First.  ", "Second."]),
    # --- numbered list markers
    ("list_arabic_single", "list_marker", "1. Distance is the length of the path travelled.",
     ["1. Distance is the length of the path travelled."]),
    ("list_arabic_two_sentences", "list_marker", "2. Displacement is shortest. It has direction.",
     ["2. Displacement is shortest. ", "It has direction."]),
    ("list_arabic_two_digits", "list_marker", "10. Tenth item. Second sentence.",
     ["10. Tenth item. ", "Second sentence."]),
    ("list_arabic_bracket", "list_marker", "1) Bracket item. More.", ["1) Bracket item. ", "More."]),
    ("list_arabic_parenthesised", "list_marker", "(2) Paren item. More.", ["(2) Paren item. ", "More."]),
    ("list_step_is_a_sentence", "list_marker", "Step 3. Mix well.", ["Step 3. ", "Mix well."]),
    ("list_step_then_number", "list_marker", "Step 3. 4 apples fell. Next.", ["Step 3. ", "4 apples fell. ", "Next."]),
    # --- Roman numerals
    ("roman_lower", "roman_numeral", "iv. Roman numbered item.", ["iv. Roman numbered item."]),
    ("roman_upper_two_sentences", "roman_numeral", "IV. Upper Roman item. Second.",
     ["IV. Upper Roman item. ", "Second."]),
    ("roman_parenthesised", "roman_numeral", "(iv) Item text. More.", ["(iv) Item text. ", "More."]),
    ("roman_long", "roman_numeral", "viii. Eighth point. Next.", ["viii. Eighth point. ", "Next."]),
    # --- lettered items
    ("letter_lower", "lettered_item", "a. Lettered item.", ["a. Lettered item."]),
    ("letter_upper", "lettered_item", "B. Capital letter item.", ["B. Capital letter item."]),
    ("letter_parenthesised", "lettered_item", "(a) Lettered in brackets. Next.",
     ["(a) Lettered in brackets. ", "Next."]),
    ("letter_not_marker_mid_text", "lettered_item", "She got an A. Then left.", ["She got an A. ", "Then left."]),
    # --- Devanagari numerals and Hindi punctuation
    ("devanagari_numeral", "devanagari", "१. प्रकाश सीधी रेखा में चलता है। यह परावर्तित होता है।",
     ["१. प्रकाश सीधी रेखा में चलता है। ", "यह परावर्तित होता है।"]),
    ("devanagari_two_digit_numeral", "devanagari", "१०. दसवाँ बिंदु। अगला।", ["१०. दसवाँ बिंदु। ", "अगला।"]),
    ("devanagari_question", "devanagari", "क्या यह सही है? हाँ।", ["क्या यह सही है? ", "हाँ।"]),
    ("devanagari_double_danda", "devanagari", "वह आया॥ फिर गया।", ["वह आया॥ ", "फिर गया।"]),
    # --- textbook abbreviations
    ("abbrev_pp", "abbreviation", "See pp. 12 for more. Next.", ["See pp. 12 for more. ", "Next."]),
    ("abbrev_ch", "abbreviation", "Read Ch. 4 now. Next.", ["Read Ch. 4 now. ", "Next."]),
    ("abbrev_vol", "abbreviation", "Vol. 2 is long. Next.", ["Vol. 2 is long. ", "Next."]),
    ("abbrev_figs", "abbreviation", "Use figs. 2 and 3. Next.", ["Use figs. 2 and 3. ", "Next."]),
    ("abbrev_cf", "abbreviation", "Compare cf. Table 2. Next.", ["Compare cf. Table 2. ", "Next."]),
    ("abbrev_fig_decimal", "abbreviation", "See Fig. 4.2 for details. Next one.",
     ["See Fig. 4.2 for details. ", "Next one."]),
    ("abbrev_eg", "abbreviation", "Use e.g. a ruler. Then measure.", ["Use e.g. a ruler. ", "Then measure."]),
    ("abbrev_titles", "abbreviation", "Mr. Rao and Dr. Sen met. Then left.", ["Mr. Rao and Dr. Sen met. ", "Then left."]),
    ("abbrev_in_brackets", "abbreviation", "Speed (cf. Table 2) varies. Next.", ["Speed (cf. Table 2) varies. ", "Next."]),
    # --- guillemets
    ("guillemet_closing", "guillemet", "He said «stop.» Then left.", ["He said «stop.» ", "Then left."]),
    ("guillemet_reversed", "guillemet", "Er sagte »Halt.« Dann ging er.", ["Er sagte »Halt.« ", "Dann ging er."]),
    ("guillemet_abbreviation", "guillemet", "See «cf. Table 2» here. Next.", ["See «cf. Table 2» here. ", "Next."]),
    # --- other rules
    ("lowercase_continuation", "other", "It rained. then it stopped.", ["It rained. then it stopped."]),
    ("multiple_terminators", "other", "Wow! Really?! Yes.", ["Wow! ", "Really?! ", "Yes."]),
    ("newline_whitespace", "other", "Line one.\nLine two.", ["Line one.\n", "Line two."]),
]

RULES = [
    "A sentence may end after one or more of . ! ? । ॥, optionally followed by closing quotes or brackets "
    "\" ' ) ] } ’ ” » «, when the next character is whitespace or the end of the text.",
    "Not after a listed abbreviation (case-insensitive, ignoring a leading ( \" ' « »).",
    "Not when the text since the previous cut is only a list marker: 1-3 digits in any script, a Roman "
    "numeral of up to six letters, or one Latin letter, optionally opened by ( and closed by . or ).",
    "Not when the next word starts with a lowercase ASCII letter.",
    "Whitespace after the cut joins the sentence that ended; leading whitespace joins the first sentence.",
]


def _fixture(case_id: str, category: str, text: str, sentences: list[str]) -> dict[str, object]:
    if "".join(sentences) != text:
        raise ValueError(f"{case_id}: expected sentences do not concatenate to the text")
    ranges, start = [], 0
    for sentence in sentences:
        ranges.append((start, start + len(sentence)))
        start += len(sentence)
    actual = segment_sentences(text)
    if actual != ranges:
        got = [text[s:e] for s, e in actual]
        raise ValueError(f"{case_id}: {SEGMENTER} gives {got!r}, fixture expects {sentences!r}")
    return {
        "id": case_id,
        "category": category,
        "text": text,
        "text_sha256": text_sha256(text),
        "length_code_points": len(text),
        "length_utf16": len(text.encode("utf-16-le")) // 2,
        "ranges": [{"start": s, "end": e} for s, e in ranges],
        "utf16_ranges": [{"start": s, "end": e} for s, e in to_utf16_ranges(text, ranges)],
        "sentences": sentences,
        "sentence_sha256": [text_sha256(s) for s in sentences],
    }


def build() -> dict[str, str]:
    ids = [c[0] for c in CASES]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate fixture id")
    fixtures = {
        "segmenter": SEGMENTER,
        "offset_unit": "unicode_code_point",
        "range_convention": "half-open [start, end); ranges cover the text contiguously from 0 to its length",
        "text_sha256": "lowercase hex SHA-256 of the exact UTF-8 bytes of the text",
        "utf16_ranges": "the same ranges as JavaScript (UTF-16 code unit) indices, for readers",
        "abbreviations": sorted(ABBREVIATIONS),
        "rules": RULES,
        "fixtures": [_fixture(*case) for case in CASES],
    }
    sample = Document.model_validate(upgrade_document_data(json.loads(SAMPLE.read_text(encoding="utf-8"))))
    example = document_sentence_ranges(sample, EXAMPLE_REVISION)
    return {FIXTURES: json.dumps(fixtures, ensure_ascii=False, indent=2) + "\n",
            EXAMPLE: json.dumps(example, ensure_ascii=False, indent=2) + "\n"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        files = build()
    except ValueError as exc:
        print(f"FIXTURE MISMATCH: {exc}")
        return 1
    if args.check:
        stale = [n for n, text in files.items()
                 if not (OUT / n).exists() or (OUT / n).read_text(encoding="utf-8") != text]
        extra = sorted(p.name for p in OUT.glob("*") if p.name not in files) if OUT.exists() else []
        if stale or extra:
            print("STALE segmentation files:", stale, "unexpected:", extra)
            return 1
        count = len(json.loads(files[FIXTURES])["fixtures"])
        digest = hashlib.sha256(files[FIXTURES].encode("utf-8")).hexdigest()
        print(f"OK: {count} {SEGMENTER} fixtures match the reference implementation; "
              f"{len(files)} files current (fixtures sha256 {digest}).")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
