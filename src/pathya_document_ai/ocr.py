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
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import math
from pathlib import Path
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
    tessdata_arg,
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
        if self.info.tessdata_dir is not None:
            flag, path = tessdata_arg(self.info.tessdata_dir)
            if any(ch.isspace() for ch in path):
                # pytesseract splits config with shlex(posix=False) on Windows, which keeps
                # quote characters, so a quoted path would be passed literally.
                raise OcrEngineError(f"tessdata directory path must not contain whitespace: {path}")
            args.append(f"{flag} {path}")
        # pytesseract keeps the executable in a module global; set it for this call.
        pytesseract.pytesseract.tesseract_cmd = str(self.info.executable)
        try:
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


def merge_ocr_into_document(document: Any, results: Iterable[OcrPageResult], *,
                            overlap_threshold: float = 0.5, low_confidence: float = 0.60) -> tuple[Any, list[str]]:
    """Add OCR line blocks to a Phase 2 ``Document``; return ``(document, notes)``.

    OCR lines overlapping existing native-text blocks on the same page by more
    than ``overlap_threshold`` of their area are not added (the native text is
    kept as the source); each such skip is reported in ``notes``.
    """
    from pathya_document_ai import models as m

    pages = {p.page_index: p for p in document.pages}
    blocks = list(document.blocks)
    notes: list[str] = []
    for result in results:
        if result.page_index is None or result.page_index not in pages:
            raise ValueError(f"OCR result page {result.page_index} is not in the document")
        page = pages[result.page_index]
        existing = [b for b in blocks if b.page_id == page.id]
        start = max((b.reading_order for b in existing if b.parent_id is None), default=-1) + 1
        candidates = to_contract_blocks(result, page.id, start_order=start, low_confidence=low_confidence)
        kept = []
        for block in candidates:
            if any(_overlap_fraction(block.bbox, b.bbox) > overlap_threshold for b in existing):
                notes.append(f"page {result.page_index}: OCR line {block.raw_text!r} overlaps native text; not added")
                continue
            kept.append(block)
        for offset, block in enumerate(kept):
            blocks.append(block.model_copy(update={"reading_order": start + offset}))
    languages = sorted({b.language for b in blocks} - {m.Language.UNDETERMINED}) or [m.Language.UNDETERMINED]
    data = document.model_dump()
    data.update(blocks=[b.model_dump() for b in blocks], languages=languages)
    return m.Document.model_validate(data), notes


def _overlap_fraction(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    area = (a[2] - a[0]) * (a[3] - a[1])
    return (w * h) / area if w > 0 and h > 0 and area > 0 else 0.0


__all__ = [
    "OcrConfig", "OcrEngine", "OcrEngineError", "OcrImageError", "OcrLine", "OcrPageResult", "OcrRun",
    "OcrTimeoutError", "OcrWord", "Script", "TesseractEngine", "classify_script", "language_for",
    "merge_ocr_into_document", "ocr_image", "ocr_pdf_pages", "select_ocr_pages", "to_contract_blocks",
]
