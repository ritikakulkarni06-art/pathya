"""English/Hindi OCR on rendered page images (Phase 3).

Flow for one page: rendered displayed-page image (Phase 2) -> ``preprocess``
derivative -> Tesseract word data -> boxes mapped back to original pixels ->
normalized displayed-page boxes (``geometry.py`` convention) -> language per
word/line from Unicode script -> optional conversion to Phase 1 blocks.

Nothing is translated or silently dropped. Raw Tesseract text is kept;
``text`` is only its Unicode NFC form. Confidence is Tesseract's own value
divided by 100, or null when Tesseract reports none (-1) or an invalid value.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import math
import os
from pathlib import Path
import threading
import time
from typing import Any, Protocol
import unicodedata

import numpy as np

from pathya_document_ai.geometry import Box, CoordinateTransform, normalize_display_box
from pathya_document_ai.preprocess import (
    ImageLimits,
    OcrImageError,
    PreprocessConfig,
    ProcessedImage,
    check_image,
    preprocess,
)
from pathya_document_ai.tesseract import (
    OcrError,
    TesseractConfig,
    TesseractInfo,
    check_languages,
    detect_tesseract,
)


class OcrTimeoutError(OcrError):
    """Tesseract exceeded its time limit; the subprocess was terminated."""


class OcrEngineError(OcrError):
    """Tesseract failed or returned unusable output."""


# ------------------------------------------------------------------ engine layer

TESSERACT_KEYS = ("level", "block_num", "par_num", "line_num", "word_num",
                  "left", "top", "width", "height", "conf", "text")


class OcrEngine(Protocol):
    """Anything that returns Tesseract ``image_to_data`` style column lists."""

    info: TesseractInfo

    def image_to_data(self, image: Any, *, languages: tuple[str, ...], psm: int, oem: int,
                      dpi: int | None, timeout_s: float) -> dict[str, list[Any]]: ...


class TesseractEngine:
    """Real engine: pytesseract driving the detected native executable."""

    def __init__(self, config: TesseractConfig | None = None) -> None:
        self.config = config or TesseractConfig()
        self.info = detect_tesseract(self.config)

    def image_to_data(self, image: Any, *, languages: tuple[str, ...], psm: int, oem: int,
                      dpi: int | None, timeout_s: float) -> dict[str, list[Any]]:
        import pytesseract

        check_languages(self.info, languages)
        args = [f"--oem {oem}", f"--psm {psm}"]
        if dpi:
            args.append(f"--dpi {dpi}")
        # The tessdata directory is passed via TESSDATA_PREFIX, not --tessdata-dir: pytesseract
        # splits the config string with shlex(posix=False) on Windows, which keeps quote
        # characters, so paths with spaces cannot be passed on the command line.
        try:
            with _PYTESSERACT_LOCK, _environment(TESSDATA_PREFIX=_tessdata_prefix(self.info.tessdata_dir)):
                # pytesseract keeps the executable in a module global; set it for this call.
                pytesseract.pytesseract.tesseract_cmd = str(self.info.executable)
                return pytesseract.image_to_data(image, lang="+".join(languages), config=" ".join(args),
                                                 timeout=timeout_s, output_type=pytesseract.Output.DICT)
        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                raise OcrTimeoutError(f"Tesseract exceeded {timeout_s}s") from exc
            raise OcrEngineError(f"Tesseract failed: {exc}") from exc
        except pytesseract.TesseractError as exc:
            raise OcrEngineError(f"Tesseract failed: {exc}") from exc
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrEngineError(f"Tesseract executable could not be started: {exc}") from exc


_PYTESSERACT_LOCK = threading.Lock()  # pytesseract uses a module-global executable path


def _tessdata_prefix(tessdata_dir: Path | None) -> str | None:
    if tessdata_dir is None:
        return None
    return str(tessdata_dir.resolve()) + os.sep  # Tesseract 5 accepts the tessdata dir itself


@contextlib.contextmanager
def _environment(**values: str | None) -> Iterator[None]:
    """Temporarily set (or leave unset when None) environment variables; always restored."""
    saved = {k: os.environ.get(k) for k in values}
    try:
        for key, value in values.items():
            if value is not None:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------------- config


@dataclass(frozen=True)
class OcrConfig:
    languages: tuple[str, ...] = ("hin", "eng")
    psm: int = 3
    oem: int = 1
    timeout_s: float = 120.0  # per page Tesseract call
    max_total_seconds: float = 1800.0  # across pages, checked between pages
    low_confidence: float = 0.60
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    limits: ImageLimits = field(default_factory=ImageLimits)


# -------------------------------------------------------------------- results


class Script(StrEnum):
    DEVANAGARI = "devanagari"
    LATIN = "latin"
    MIXED = "mixed"
    OTHER = "other"  # letters of another script
    NONE = "none"  # digits, punctuation, symbols only


class OcrPageStatus(StrEnum):
    OK = "ok"
    BLANK_IMAGE = "blank_image"  # uniform image; Tesseract not run


@dataclass(frozen=True)
class OcrWord:
    index: int
    raw_text: str  # exactly as Tesseract returned it
    text: str  # NFC-normalized raw_text; no other changes
    bbox: Box | None  # normalized displayed-page box; None when outside the image
    image_box: Box  # original (pre-preprocessing) pixel box
    confidence: float | None  # Tesseract conf / 100; None if absent or invalid
    raw_confidence: str  # Tesseract's conf value as text, e.g. "-1" or "91.5"
    script: Script
    language: str  # contract tag: en, hi, mul or und
    line_key: tuple[int, int, int]  # Tesseract (block, paragraph, line)
    notes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OcrLine:
    index: int
    word_indices: tuple[int, ...]
    raw_text: str
    text: str
    bbox: Box | None
    language: str
    confidence: float | None  # mean of non-null word confidences
    scripts: frozenset[Script]


@dataclass(frozen=True)
class OcrDiagnostics:
    word_count: int
    line_count: int
    null_confidence_count: int
    low_confidence_count: int
    mean_confidence: float | None
    script_counts: dict[str, int]
    elapsed_s: float


@dataclass(frozen=True)
class OcrPageResult:
    page_index: int | None
    width_px: int  # original rendered image size
    height_px: int
    dpi: float | None
    transform: CoordinateTransform | None  # Phase 2 page transform (normalized <-> PDF)
    status: OcrPageStatus
    words: tuple[OcrWord, ...]
    lines: tuple[OcrLine, ...]
    languages: tuple[str, ...]
    engine: str
    engine_version: str
    language_data: str  # traineddata fingerprint, e.g. "hin:4c73ffc59d49,eng:7d4322bd2a77"
    psm: int
    oem: int
    preprocessing: tuple[str, ...]
    diagnostics: OcrDiagnostics
    created_at: datetime
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------- script/lang


def classify_script(text: str) -> Script:
    deva = latin = other = False
    for ch in text:
        if not unicodedata.category(ch).startswith(("L", "M")):
            continue
        code = ord(ch)
        if 0x0900 <= code <= 0x097F or 0xA8E0 <= code <= 0xA8FF or 0x1CD0 <= code <= 0x1CFF:
            deva = True
        elif ch.isascii() or 0x00C0 <= code <= 0x024F:
            latin = True
        else:
            other = True
    if deva and latin:
        return Script.MIXED
    if deva:
        return Script.DEVANAGARI
    if latin:
        return Script.LATIN
    return Script.OTHER if other else Script.NONE


def language_for(script: Script, languages: tuple[str, ...]) -> str:
    """Contract language tag from script, limited to the configured OCR languages."""
    if script is Script.MIXED:
        return "mul"
    if script is Script.DEVANAGARI and "hin" in languages:
        return "hi"
    if script is Script.LATIN and "eng" in languages:
        return "en"
    return "und"


def _line_language(word_languages: Iterable[str]) -> str:
    tags = {tag for tag in word_languages if tag != "und"}
    if not tags:
        return "und"
    if len(tags) == 1:
        return tags.pop()
    return "mul"


def _parse_confidence(value: Any) -> tuple[float | None, str | None]:
    raw = str(value).strip()
    try:
        number = float(raw)
    except ValueError:
        return None, f"non-numeric confidence {raw!r}"
    if number == -1:
        return None, None
    if not math.isfinite(number) or not 0 <= number <= 100:
        return None, f"out-of-range confidence {raw!r}"
    return number / 100.0, None


# ---------------------------------------------------------------- core run


def ocr_image(
    image: Any,
    *,
    engine: OcrEngine,
    config: OcrConfig | None = None,
    page_index: int | None = None,
    dpi: float | None = None,
    transform: CoordinateTransform | None = None,
) -> OcrPageResult:
    """OCR one displayed-page image. ``image`` itself is never modified."""
    config = config or OcrConfig()
    started = time.monotonic()
    check_image(image, config.limits)
    check_languages(engine.info, config.languages)
    width, height = image.size
    common = dict(page_index=page_index, width_px=width, height_px=height, dpi=dpi, transform=transform,
                  languages=config.languages, engine="tesseract", engine_version=engine.info.version,
                  language_data=engine.info.language_fingerprint(config.languages),
                  psm=config.psm, oem=config.oem, created_at=datetime.now(timezone.utc))

    gray = np.asarray(image.convert("L"))
    if int(gray.max()) - int(gray.min()) < 8:
        diag = OcrDiagnostics(0, 0, 0, 0, None, {}, time.monotonic() - started)
        return OcrPageResult(status=OcrPageStatus.BLANK_IMAGE, words=(), lines=(), preprocessing=(),
                             diagnostics=diag, warnings=("uniform image; OCR not run",), **common)

    processed = preprocess(image, config.preprocess, source_dpi=dpi, limits=config.limits)
    effective_dpi = None
    if dpi:
        effective_dpi = round(dpi * float(np.hypot(processed.forward[0, 0], processed.forward[1, 0])))
    data = engine.image_to_data(processed.image, languages=config.languages, psm=config.psm, oem=config.oem,
                                dpi=effective_dpi, timeout_s=config.timeout_s)
    words, warnings = _parse_words(data, processed, width, height, config.languages)
    lines = _group_lines(words)
    diag = _diagnostics(words, lines, config.low_confidence, time.monotonic() - started)
    return OcrPageResult(status=OcrPageStatus.OK, words=tuple(words), lines=tuple(lines),
                         preprocessing=tuple(op.describe() for op in processed.operations),
                         diagnostics=diag, warnings=tuple(warnings), **common)


def _parse_words(
    data: dict[str, list[Any]], processed: ProcessedImage, width: int, height: int, languages: tuple[str, ...]
) -> tuple[list[OcrWord], list[str]]:
    missing = [key for key in TESSERACT_KEYS if key not in data]
    if missing:
        raise OcrEngineError(f"Tesseract output lacks columns {missing}")
    count = len(data["text"])
    if any(len(data[key]) != count for key in TESSERACT_KEYS):
        raise OcrEngineError("Tesseract output columns have different lengths")

    words: list[OcrWord] = []
    warnings: list[str] = []
    outside = clipped = 0
    for row in range(count):
        if int(data["level"][row]) != 5:
            continue
        raw = str(data["text"][row])
        if not raw.strip():
            continue
        left, top = float(data["left"][row]), float(data["top"][row])
        w, h = float(data["width"][row]), float(data["height"][row])
        if w < 0 or h < 0:
            warnings.append(f"word {raw!r} has negative size; geometry rejected")
            image_box: Box = (left, top, left, top)
            bbox, notes = None, frozenset({"invalid_geometry"})
        else:
            image_box = processed.to_original((left, top, left + w, top + h))
            bbox, notes = normalize_display_box(image_box, (0.0, 0.0, float(width), float(height)))
            if bbox is None:
                notes = frozenset({"outside_image"})
                outside += 1
            elif "clipped" in notes:
                clipped += 1
        confidence, problem = _parse_confidence(data["conf"][row])
        if problem:
            warnings.append(f"word {raw!r}: {problem}; confidence set to null")
        script = classify_script(raw)
        words.append(OcrWord(
            index=len(words), raw_text=raw, text=unicodedata.normalize("NFC", raw), bbox=bbox,
            image_box=image_box, confidence=confidence, raw_confidence=str(data["conf"][row]),
            script=script, language=language_for(script, languages),
            line_key=(int(data["block_num"][row]), int(data["par_num"][row]), int(data["line_num"][row])),
            notes=notes,
        ))
    if outside:
        warnings.append(f"{outside} words lie outside the image (kept, bbox=None)")
    if clipped:
        warnings.append(f"{clipped} word boxes clipped to the image")
    return words, warnings


def _group_lines(words: list[OcrWord]) -> list[OcrLine]:
    groups: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:  # Tesseract emits words in its reading order
        groups.setdefault(word.line_key, []).append(word)
    lines = []
    for index, group in enumerate(groups.values()):
        boxes = [w.bbox for w in group if w.bbox is not None]
        bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
        confs = [w.confidence for w in group if w.confidence is not None]
        lines.append(OcrLine(
            index=index, word_indices=tuple(w.index for w in group),
            raw_text=" ".join(w.raw_text for w in group), text=" ".join(w.text for w in group),
            bbox=bbox, language=_line_language(w.language for w in group),
            confidence=sum(confs) / len(confs) if confs else None,
            scripts=frozenset(w.script for w in group),
        ))
    return lines


def _diagnostics(words: list[OcrWord], lines: list[OcrLine], low: float, elapsed: float) -> OcrDiagnostics:
    confs = [w.confidence for w in words if w.confidence is not None]
    return OcrDiagnostics(
        word_count=len(words), line_count=len(lines),
        null_confidence_count=sum(1 for w in words if w.confidence is None),
        low_confidence_count=sum(1 for c in confs if c < low),
        mean_confidence=sum(confs) / len(confs) if confs else None,
        script_counts=dict(Counter(w.script.value for w in words)), elapsed_s=round(elapsed, 3),
    )


# ---------------------------------------------------- Phase 2 integration


@dataclass(frozen=True)
class OcrRun:
    results: tuple[OcrPageResult, ...]
    skipped: dict[int, str]  # page_index -> why OCR was not run


def select_ocr_pages(extraction: Any, *, force_pages: Iterable[int] = (),
                     include_recommended: bool = False) -> tuple[list[int], dict[int, str]]:
    """Pages to OCR: those forced by the caller, plus Phase 2 ``ocr_required`` pages.

    ``ocr_recommended`` pages are included only when ``include_recommended`` is set.
    """
    from pathya_document_ai.quality import OcrDecision

    forced = set(force_pages)
    selected, skipped = [], {}
    for page in extraction.pages:
        decision = page.ocr.decision
        if page.page_index in forced:
            selected.append(page.page_index)
        elif decision is OcrDecision.OCR_REQUIRED:
            selected.append(page.page_index)
        elif decision is OcrDecision.OCR_RECOMMENDED and include_recommended:
            selected.append(page.page_index)
        else:
            skipped[page.page_index] = f"phase 2 decision {decision.value}; not requested"
    unknown = forced - {p.page_index for p in extraction.pages}
    if unknown:
        raise IndexError(f"force_pages contains unknown page indices {sorted(unknown)}")
    return selected, skipped


def ocr_pdf_pages(
    path: Path | str,
    extraction: Any,
    *,
    engine: OcrEngine,
    config: OcrConfig | None = None,
    dpi: float = 300,
    force_pages: Iterable[int] = (),
    include_recommended: bool = False,
    pdf_limits: Any = None,
) -> OcrRun:
    """Render and OCR the selected pages one at a time (only one page image in memory)."""
    from pathya_document_ai.pdf import iter_rendered_pages

    config = config or OcrConfig()
    selected, skipped = select_ocr_pages(extraction, force_pages=force_pages,
                                         include_recommended=include_recommended)
    deadline = time.monotonic() + config.max_total_seconds
    results = []
    if selected:
        for rendered in iter_rendered_pages(path, selected, dpi=dpi, limits=pdf_limits):
            if time.monotonic() > deadline:
                raise OcrTimeoutError(f"OCR exceeded {config.max_total_seconds}s before page {rendered.page_index}")
            try:
                results.append(ocr_image(rendered.image, engine=engine, config=config,
                                         page_index=rendered.page_index, dpi=rendered.dpi,
                                         transform=rendered.transform))
            finally:
                rendered.image.close()
    return OcrRun(tuple(results), skipped)


# ------------------------------------------------------- Phase 1 conversion


def to_contract_blocks(result: OcrPageResult, page_id: Any, *, start_order: int = 0,
                       low_confidence: float = 0.60) -> list[Any]:
    """OCR lines -> provisional ``paragraph`` blocks (lines, not true paragraphs).

    ``raw_text`` and ``current_text`` are both Tesseract's raw line text so the
    block stays a revision-1 (unedited) record; the NFC form stays in ``OcrLine.text``.
    """
    from pathya_document_ai import models as m

    provenance = m.Provenance(
        method=m.ExtractionMethod.OCR, engine=result.engine, engine_version=result.engine_version,
        model="+".join(result.languages) + " traineddata", model_version=result.language_data,
        parameters={"lang": "+".join(result.languages), "psm": result.psm, "oem": result.oem,
                    "dpi": result.dpi, "preprocessing": ";".join(result.preprocessing) or "none"},
        created_at=result.created_at)
    blocks = []
    order = start_order
    for line in result.lines:
        if line.bbox is None:
            continue
        flags = [m.QualityFlag.READING_ORDER_UNCERTAIN]
        if line.language == "und":
            flags.append(m.QualityFlag.LANGUAGE_UNCERTAIN)
        if Script.MIXED in line.scripts or {Script.DEVANAGARI, Script.LATIN} <= line.scripts:
            flags.append(m.QualityFlag.MIXED_SCRIPT)
        if line.confidence is None:
            confidence = m.Confidence.unavailable("Tesseract reported no word confidence for this line.")
        else:
            confidence = m.Confidence(
                score=round(line.confidence, 4), origin=m.ConfidenceOrigin.ENGINE_REPORTED,
                reason=f"Mean Tesseract word confidence / 100 over {len(line.word_indices)} words.")
            if line.confidence < low_confidence:
                flags += [m.QualityFlag.LOW_CONFIDENCE, m.QualityFlag.POSSIBLE_OCR_ERROR]
        blocks.append(m.Block(
            page_id=page_id, block_type=m.BlockType.PARAGRAPH, reading_order=order, bbox=line.bbox,
            raw_text=line.raw_text, current_text=line.raw_text, language=m.Language(line.language),
            confidence=confidence, quality_flags=flags, provenance=provenance))
        order += 1
    return blocks


def merge_ocr_into_document(
    document: Any,
    results: Iterable[OcrPageResult],
    *,
    extraction: Any = None,
    duplicate_word_fraction: float = 0.5,
    low_confidence: float = 0.60,
) -> tuple[Any, list[str]]:
    """Add OCR line blocks to a Phase 2 (line-level) ``Document``; return ``(document, notes)``.

    Merge policy, shared with ``layout._collect_tokens`` (see docs/ocr.md):

    * Native text is **unreliable** for a page when Phase 2 decided
      ``ocr_required`` for it (needs ``extraction``), and for an individual native
      block flagged ``possible_ocr_error`` (e.g. unmapped glyphs).
    * An OCR word is *covered* when its centre lies inside a native block.
    * OCR line with no covered words: added as new content.
    * OCR line covering unreliable native blocks: OCR **replaces** those blocks
      at their reading position (the native text remains in ``PdfExtraction``);
      the OCR block is flagged ``duplicate_content``.
    * OCR line covering reliable native text with at least
      ``duplicate_word_fraction`` of its words: not added; the native block is
      flagged ``duplicate_content``.
    * OCR line only partly covering reliable native text: added and flagged
      ``duplicate_content`` (possible partial duplicate for review).

    Every decision is listed in ``notes``. Only page-level (top-level) native
    blocks are compared; use ``layout.build_layout_document`` for layout output.
    """
    from pathya_document_ai import models as m
    from pathya_document_ai.quality import OcrDecision

    unreliable_pages = set()
    if extraction is not None:
        unreliable_pages = {p.page_index for p in extraction.pages if p.ocr.decision is OcrDecision.OCR_REQUIRED}
    pages = {p.page_index: p for p in document.pages}
    blocks = list(document.blocks)
    notes: list[str] = []
    dup = m.QualityFlag.DUPLICATE_CONTENT
    for result in results:
        if result.page_index is None or result.page_index not in pages:
            raise ValueError(f"OCR result page {result.page_index} is not in the document")
        page = pages[result.page_index]
        tag = f"page {result.page_index}"
        first_note = len(notes)
        natives = [b for b in blocks if b.page_id == page.id and b.parent_id is None
                   and b.provenance.method is m.ExtractionMethod.NATIVE_PDF_TEXT]

        def unreliable(block: Any) -> bool:
            return result.page_index in unreliable_pages or m.QualityFlag.POSSIBLE_OCR_ERROR in block.quality_flags

        lines = [line for line in result.lines if line.bbox is not None]
        candidates = to_contract_blocks(result, page.id, low_confidence=low_confidence)
        replaced: dict[Any, list[Any]] = {}  # native block id -> OCR blocks replacing it
        flag_native: set[Any] = set()
        additions: list[Any] = []
        for line, block in zip(lines, candidates):
            boxes = [result.words[i].bbox for i in line.word_indices if result.words[i].bbox is not None]
            covering = [[n for n in natives if _center_inside(b, n.bbox)] for b in boxes]
            hit = {n.id: n for group in covering for n in group}
            covered = sum(1 for group in covering if group) / len(boxes) if boxes else 0.0
            if not hit:
                additions.append(block)
            elif all(unreliable(n) for n in hit.values()):
                flagged = block.model_copy(update={"quality_flags": [*block.quality_flags, dup]})
                anchor = min(hit.values(), key=lambda n: n.reading_order)
                replaced.setdefault(anchor.id, []).append(flagged)
                for n in hit.values():
                    replaced.setdefault(n.id, [])
                notes.append(f"{tag}: OCR line {block.raw_text!r} replaces unreliable native text "
                             f"{[n.raw_text for n in hit.values()]!r}")
            elif covered >= duplicate_word_fraction:
                flag_native.update(n.id for n in hit.values() if not unreliable(n))
                notes.append(f"{tag}: OCR line {block.raw_text!r} duplicates native text; not added")
            else:
                additions.append(block.model_copy(update={"quality_flags": [*block.quality_flags, dup]}))
                notes.append(f"{tag}: OCR line {block.raw_text!r} partly overlaps native text "
                             f"({covered:.0%} of words); added and flagged duplicate_content")

        # Rebuild this page's top-level order: native blocks (or their OCR replacements) in
        # their original order, then genuinely new OCR lines.
        page_top = sorted((b for b in blocks if b.page_id == page.id and b.parent_id is None),
                          key=lambda b: b.reading_order)
        ordered: list[Any] = []
        for b in page_top:
            if b.id in replaced:
                ordered += replaced[b.id]
            elif b.id in flag_native and dup not in b.quality_flags:
                ordered.append(b.model_copy(update={"quality_flags": [*b.quality_flags, dup]}))
            else:
                ordered.append(b)
        ordered += additions
        renumbered = [b.model_copy(update={"reading_order": i}) for i, b in enumerate(ordered)]
        removed = set(replaced)
        blocks = [b for b in blocks if not (b.page_id == page.id and b.parent_id is None)] + renumbered
        blocks = [b for b in blocks if b.id not in removed]
        has_blocks = any(b.page_id == page.id for b in blocks)
        merge_warnings = [m.PageWarning(stage=m.ProcessingStage.MERGE, code="ocr_merge_decision", message=n)
                          for n in notes[first_note:]]
        pages[result.page_index] = apply_ocr_status(page, result, has_blocks, m, extra=merge_warnings)
    kept_ids = {b.id for b in blocks}
    edges = [e for e in document.edges if e.source_id in kept_ids and e.target_id in kept_ids]
    if len(edges) != len(document.edges):
        notes.append(f"{len(document.edges) - len(edges)} edges to replaced native blocks were removed")
    languages = sorted({b.language for b in blocks} - {m.Language.UNDETERMINED}) or [m.Language.UNDETERMINED]
    data = document.model_dump()
    if data["schema_version"] == "1.0.0":
        # Merging adds 1.1.0 information (page status/warnings, duplicate_content); upgrade
        # explicitly and report it rather than emitting an invalid 1.0.0 document.
        data = m.upgrade_document_data(data)
        notes.append("document upgraded from schema 1.0.0 to 1.1.0 to record OCR status and flags")
    ordered_pages = [pages[p.page_index].model_dump() if p.page_index in pages else p.model_dump()
                     for p in document.pages]
    status_by_index = {p["page_index"]: p for p in data["pages"]}
    for page_data in ordered_pages:
        if page_data.get("status") is None:
            page_data["status"] = status_by_index[page_data["page_index"]].get("status") or "ok"
    data.update(pages=ordered_pages, blocks=[b.model_dump() for b in blocks], edges=[e.model_dump() for e in edges],
                languages=languages)
    return m.Document.model_validate(data), notes


def apply_ocr_status(page: Any, result: OcrPageResult, has_blocks: bool, m: Any, extra: list[Any] = ()) -> Any:  # type: ignore[assignment]
    """Return ``page`` with status/warnings updated after OCR was run on it."""
    warnings = list(page.warnings) + [m.PageWarning(
        stage=m.ProcessingStage.OCR, code="ocr_applied",
        message=f"Tesseract {result.engine_version} ({'+'.join(result.languages)}): "
                f"{result.diagnostics.word_count} words, mean confidence "
                f"{'n/a' if result.diagnostics.mean_confidence is None else round(result.diagnostics.mean_confidence, 3)}")]
    warnings += [m.PageWarning(stage=m.ProcessingStage.OCR, code="ocr_warning", message=w) for w in result.warnings]
    warnings += list(extra)
    status = page.status
    if status in (None, m.PageStatus.NEEDS_OCR, m.PageStatus.BLANK, m.PageStatus.OK):
        status = m.PageStatus.OK if has_blocks else m.PageStatus.BLANK
        if not has_blocks:
            warnings.append(m.PageWarning(stage=m.ProcessingStage.OCR, code="ocr_found_no_text",
                                          message="OCR ran and found no text on this page"))
    return page.model_copy(update={"status": status, "warnings": warnings})


def _center_inside(box: Box, region: Box, pad: float = 0.002) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return region[0] - pad <= cx <= region[2] + pad and region[1] - pad <= cy <= region[3] + pad


__all__ = [
    "OcrConfig", "OcrEngine", "OcrEngineError", "OcrImageError", "OcrLine", "OcrPageResult", "OcrRun",
    "OcrTimeoutError", "OcrWord", "Script", "TesseractEngine", "classify_script", "language_for",
    "merge_ocr_into_document", "ocr_image", "ocr_pdf_pages", "select_ocr_pages", "to_contract_blocks",
]
