"""``pathya-sentences/3``: reference sentence segmenter and bulk-response checker.

Sentence ranges are **not** part of the P1 Document. P3 computes and serves
them (``GET /documents/{id}/sentence-ranges``); this module is the shared
reference implementation P3 adopts, and the fixtures in
``contract/segmentation/`` pin its behaviour. See docs/p3_verification_guide.md.

Offset rules (normative):

* Offsets count **Unicode code points** (Python ``str`` indices), not bytes
  and not UTF-16 units. JavaScript readers convert with
  :func:`to_utf16_ranges` (they differ for characters outside the BMP).
* Offsets index the exact ``current_text`` of the block, never ``raw_text``,
  before pronunciation substitutions. No normalization (NFC or otherwise).
* Ranges are half-open ``[start, end)``, start < end, and cover the whole text
  contiguously: the first starts at 0, each starts where the previous ended,
  the last ends at ``len(text)``. Whitespace after a sentence belongs to that
  sentence; leading whitespace belongs to the first. Empty text has no ranges.
* Only headings, paragraphs and list items are split (P2 decision); every
  other block, and a block without text, has an empty range list.
* ``text_sha256`` is the lowercase hex SHA-256 of the exact UTF-8 bytes of
  ``current_text``; a block whose ``current_text`` is null hashes as ``""``.

Segmentation rules of ``pathya-sentences/3``:

1. A sentence may end after one or more of ``. ! ? । ॥`` optionally followed
   by closing quotes or brackets ``" ' ) ] } ’ ” » «``, when the next character
   is whitespace or the end of the text (so ``4.5`` and ``4.2`` never split).
2. Not after a listed abbreviation (``e.g. i.e. etc. vs. cf. fig. figs. eq.
   eqs. no. nos. dr. mr. mrs. ms. approx. p. pp. vol. ch. sec.``, any case,
   ignoring a leading ``( " ' « »``).
3. Not when the text since the previous cut is only a list marker: 1-3 digits
   (any script, e.g. Devanagari ``१``), a Roman numeral of up to six letters,
   or one Latin letter, optionally opened by ``(`` and closed by ``.`` or
   ``)``: ``1.``, ``10.``, ``1)``, ``(2)``, ``iv.``, ``IV.``, ``a.``, ``(a)``, ``१.``.
4. Not when the next word starts with a lowercase ASCII letter (guards
   against OCR line breaks such as ``It rained. then``).
5. Whitespace after the cut joins the sentence that ended.

Changes from ``/2``: ``cf.`` is an abbreviation; ``«`` and ``»`` close a
sentence like other quotes. Everything else is unchanged.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

SEGMENTER = "pathya-sentences/3"
_TERMINATORS = ".!?।॥"
_CLOSERS = "\"')]}’”»«"
_OPENERS_BEFORE_WORD = "(\"'«»"
ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "fig.", "figs.", "eq.", "eqs.", "no.", "nos.", "dr.", "mr.", "mrs.",
    "ms.", "approx.", "p.", "pp.", "vol.", "ch.", "sec.",
})
_LIST_MARKER = re.compile(r"\(?(?:\d{1,3}|[ivxlcdm]{1,6}|[a-z])[.)]", re.IGNORECASE)
_BOUNDARY = re.compile(rf"[{re.escape(_TERMINATORS)}]+[{re.escape(_CLOSERS)}]*(?=\s|$)")
SENTENCE_BLOCK_TYPES = frozenset({"heading", "paragraph", "list_item"})


def text_sha256(text: str | None) -> str:
    """Lowercase hex SHA-256 of the exact UTF-8 bytes of ``text`` (``None`` hashes as ``""``)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def segment_sentences(text: str) -> list[tuple[int, int]]:
    """Return contiguous ``[(start, end), ...]`` code-point ranges covering all of ``text``."""
    cuts: list[int] = []
    for match in _BOUNDARY.finditer(text):
        end = match.end()
        if _is_abbreviation(text, match.start()) or _continues_lowercase(text, end):
            continue
        if _LIST_MARKER.fullmatch(text[cuts[-1] if cuts else 0:end].strip()):
            continue  # "1.", "iv.", "a.", "१." opening a list item is not a sentence of its own
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
    word = text[word_start:terminator_index + 1].lower().lstrip(_OPENERS_BEFORE_WORD)
    return word in ABBREVIATIONS


def _continues_lowercase(text: str, end: int) -> bool:
    rest = text[end:].lstrip()
    return bool(rest) and rest[0].isascii() and rest[0].islower()


def to_utf16_ranges(text: str, ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Convert code-point ranges to UTF-16 code-unit ranges (for JavaScript string indices)."""
    prefix = [0]
    for ch in text:
        prefix.append(prefix[-1] + (2 if ord(ch) > 0xFFFF else 1))
    return [(prefix[s], prefix[e]) for s, e in ranges]


def coverage_problems(text: str, ranges: list[tuple[int, int]]) -> list[str]:
    """Why ``ranges`` do not cover ``text`` as the offset rules require (empty list: they do)."""
    if not text:
        return [] if not ranges else ["empty text must have no ranges"]
    if not ranges:
        return ["non-empty text needs at least one range"]
    problems, expected = [], 0
    for start, end in ranges:
        if start != expected:
            problems.append(f"range starts at {start}, expected {expected} (gap or overlap)")
        if end <= start:
            problems.append(f"range [{start}, {end}) is empty or reversed")
        expected = end
    if expected != len(text):
        problems.append(f"ranges end at {expected}, text length is {len(text)} code points")
    return problems


# ------------------------------------------------------------ P3 bulk endpoint


def _block_type(block: Any) -> str:
    value = getattr(block, "block_type", None)
    return str(getattr(value, "value", value))


def block_sentence_ranges(block: Any, segmenter: str = SEGMENTER) -> dict[str, Any]:
    """One entry of the bulk response for ``block`` (a ``models.Block``)."""
    text = block.current_text or ""
    ranges = segment_sentences(text) if _block_type(block) in SENTENCE_BLOCK_TYPES else []
    return {"block_id": str(block.id), "text_sha256": text_sha256(block.current_text), "segmenter": segmenter,
            "ranges": [{"start": s, "end": e} for s, e in ranges]}


def document_sentence_ranges(document: Any, document_revision: int) -> dict[str, Any]:
    """Reference body of ``GET /documents/{id}/sentence-ranges`` for one Document snapshot.

    ``document`` is the canonical Document served by ``/content`` at
    ``document_revision`` (its block IDs are P3's). Blocks keep Document order.
    """
    return {"document_revision": document_revision,
            "blocks": [block_sentence_ranges(b) for b in document.blocks]}


def check_sentence_ranges_response(response: dict[str, Any], document: Any, *,
                                   document_revision: int | None = None) -> list[str]:
    """Check a bulk sentence-ranges response against the Document of the same revision.

    Returns a list of problems (empty: the response conforms). Checks the
    revision, that every current block appears exactly once, each hash, that
    non-sentence blocks have no ranges, full coverage, and -- for entries
    labelled ``pathya-sentences/3`` -- the exact reference ranges.
    """
    problems: list[str] = []
    revision = response.get("document_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        problems.append(f"document_revision must be a non-negative integer, got {revision!r}")
    elif document_revision is not None and revision != document_revision:
        problems.append(f"document_revision {revision} does not match the content revision {document_revision}")
    blocks = {str(b.id): b for b in document.blocks}
    entries = response.get("blocks")
    if not isinstance(entries, list):
        return [*problems, "blocks must be a list"]
    seen: set[str] = set()
    for entry in entries:
        block_id = str(entry.get("block_id"))
        if block_id in seen:
            problems.append(f"block {block_id} appears more than once")
        seen.add(block_id)
        block = blocks.get(block_id)
        if block is None:
            problems.append(f"block {block_id} is not a current block of the Document")
            continue
        text = block.current_text or ""
        if entry.get("text_sha256") != text_sha256(block.current_text):
            problems.append(f"block {block_id}: text_sha256 does not match the UTF-8 bytes of current_text")
        if not entry.get("segmenter"):
            problems.append(f"block {block_id}: segmenter is missing")
        try:
            ranges = [(int(r["start"]), int(r["end"])) for r in entry.get("ranges", [])]
        except (KeyError, TypeError, ValueError):
            problems.append(f"block {block_id}: ranges must be objects with integer start and end")
            continue
        if _block_type(block) not in SENTENCE_BLOCK_TYPES:
            if ranges:
                problems.append(f"block {block_id}: {_block_type(block)} blocks have no sentence ranges")
            continue
        problems += [f"block {block_id}: {p}" for p in coverage_problems(text, ranges)]
        if entry.get("segmenter") == SEGMENTER and ranges != segment_sentences(text):
            problems.append(f"block {block_id}: ranges differ from the {SEGMENTER} reference")
    missing = sorted(set(blocks) - seen)
    if missing:
        problems.append(f"{len(missing)} current block(s) missing, e.g. {missing[0]}")
    return problems
