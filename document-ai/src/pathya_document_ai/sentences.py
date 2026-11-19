"""Sentence ranges over a block's ``current_text`` (contract 1.2.0).

Offset rules (normative, see docs/p1_contract.md "Sentence offsets"):

* Offsets count **Unicode code points** (Python ``str`` indices), not bytes
  and not UTF-16 units. JavaScript readers must convert with
  :func:`to_utf16_ranges` (they differ for characters outside the BMP).
* Offsets index the exact ``current_text`` of the block, never ``raw_text``.
  No normalization (NFC or otherwise) is applied before counting.
* Ranges are half-open ``[start, end)`` and cover the whole ``current_text``
  contiguously: the first starts at 0, each starts where the previous ended,
  and the last ends at ``len(current_text)``. Whitespace after a sentence
  belongs to that sentence's range (leading whitespace belongs to the first).
  Empty text has no ranges.
* Only headings, paragraphs and list items carry ranges (P2 decision).
* A segmentation is bound to one block revision and the SHA-256 of
  ``current_text``. Any correction that increments the revision makes it (and
  every audio reference bound to it) stale; it must be regenerated.

Segmentation (segmenter ``pathya-sentences/2``) is deliberately simple and
deterministic: a sentence ends after ``.``, ``!``, ``?``, ``।`` (danda) or
``॥`` (double danda), optionally followed by closing quotes or brackets, when
the next character is whitespace or the end of the text. It does not end on a
decimal point (no following space), after a listed abbreviation, after a list
marker that opens the text (``1.``, ``iv.``, ``a.``), or when the next word
starts with a lowercase Latin letter.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

SEGMENTER = "pathya-sentences/2"  # /2: ranges cover the whole text (P2 decision)
_TERMINATORS = ".!?।॥"
_CLOSERS = "\"')]}’”"
_ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "etc.", "fig.", "figs.", "eq.", "eqs.", "no.", "nos.", "dr.", "mr.", "mrs.", "ms.",
    "vs.", "approx.", "p.", "pp.", "vol.", "ch.", "sec.",
})
_LIST_MARKER = re.compile(r"\(?(?:\d{1,3}|[ivxlcdm]{1,6}|[a-z])[.)]", re.IGNORECASE)
_BOUNDARY = re.compile(rf"[{re.escape(_TERMINATORS)}]+[{re.escape(_CLOSERS)}]*(?=\s|$)")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def segment_sentences(text: str) -> list[tuple[int, int]]:
    """Return contiguous ``[(start, end), ...]`` code-point ranges covering all of ``text``."""
    cuts: list[int] = []
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        if _is_abbreviation(text, match.start()) or _continues_lowercase(text, end):
            continue
        if _LIST_MARKER.fullmatch(text[cuts[-1] if cuts else 0:end].strip()):
            continue  # "1.", "iv.", "a." opening a list item is not a sentence of its own
        while end < len(text) and text[end].isspace():  # trailing whitespace joins this sentence
            end += 1
        if end < len(text):
            cuts.append(end)
    bounds = [0, *cuts, len(text)] if text else []
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if b > a]


def _is_abbreviation(text: str, terminator_index: int) -> bool:
    if text[terminator_index] != ".":
        return False
    word_start = terminator_index
    while word_start > 0 and not text[word_start - 1].isspace():
        word_start -= 1
    word = text[word_start:terminator_index + 1].lower().lstrip("(\"'")
    return word in _ABBREVIATIONS


def _continues_lowercase(text: str, end: int) -> bool:
    rest = text[end:].lstrip()
    return bool(rest) and rest[0].isascii() and rest[0].islower()


def to_utf16_ranges(text: str, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Convert code-point ranges to UTF-16 code-unit ranges (for JavaScript string indices)."""
    prefix = [0]
    for ch in text:
        prefix.append(prefix[-1] + (2 if ord(ch) > 0xFFFF else 1))
    return [(prefix[s], prefix[e]) for s, e in ranges]


def build_segmentation(block: Any) -> Any:
    """``SentenceSegmentation`` for the block's current revision; None if it has no text or
    is not a heading, paragraph or list item."""
    from pathya_document_ai import models as m

    if block.current_text is None or block.block_type not in m.SENTENCE_BLOCK_TYPES:
        return None
    return m.SentenceSegmentation(
        text_revision=block.revision, text_sha256=text_sha256(block.current_text), segmenter=SEGMENTER,
        ranges=[m.SentenceRange(start=s, end=e) for s, e in segment_sentences(block.current_text)])


def attach_sentences(block: Any) -> Any:
    """Return ``block`` with fresh sentence ranges (backend helper; keeps other integration fields)."""
    from pathya_document_ai import models as m

    integration = block.integration or m.BlockIntegration()
    return block.model_copy(update={"integration": integration.model_copy(
        update={"sentences": build_segmentation(block)})})
