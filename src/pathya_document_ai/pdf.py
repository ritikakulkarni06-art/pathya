"""Native PDF inspection, text/word extraction and page rendering (Phase 2).

* Text and geometry come from pdfplumber (pdfminer.six); rendering from pypdfium2.
* Only PDFs are accepted, identified by file signature, never by extension.
* No embedded content is executed: pdfminer does not run scripts, and PDFium
  is used without a form environment (no JavaScript), so no URLs are fetched.
* Resource use is bounded by :class:`PdfLimits`. Files are streamed from disk
  rather than read into memory, and every PDFium object is closed explicitly.

Coordinates follow ``geometry.py``: normalized ``[x0, y0, x1, y1]`` over the
displayed page (after /Rotate and within the CropBox), top-left origin.
Native text has no engine confidence, so none is invented (see ``to_contract_document``).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import itertools
import math
from pathlib import Path
import time
from typing import Any
from uuid import UUID

import numpy as np

from pathya_document_ai.geometry import (
    Box,
    CoordinateTransform,
    Rotation,
    SourceCoordinateSpace,
    normalize_display_box,
)
from pathya_document_ai.quality import (
    NativeTextMetrics,
    OcrAssessment,
    OcrDecision,
    OcrReason,
    OcrThresholds,
    assess_ocr_need,
    is_unmapped_char,
)

PDF_SIGNATURE = b"%PDF-"
SIGNATURE_WINDOW = 1024  # the PDF header may be preceded by junk within the first 1 KiB
_HASH_CHUNK = 1 << 20
LINE_BREAK_GAP = 1.2  # word gap (in glyph heights) above which a line is split

# pdfplumber word-extraction parameters, recorded in provenance.
WORD_PARAMS: dict[str, Any] = {
    "x_tolerance": 3,
    "y_tolerance": 3,
    "keep_blank_chars": False,
    # use_text_flow=True mis-groups characters on /Rotate 90/270 pages, so words are
    # grouped geometrically and content-stream order is recovered from char positions.
    "use_text_flow": False,
}

def _direction_params(chars: list[dict[str, Any]]) -> dict[str, str]:
    """pdfplumber reading directions inferred from the characters' display-space matrices.

    The char matrix already includes /Rotate, so its signs tell how text runs on
    the displayed page: upright glyphs with a<0 run right-to-left and upside down
    (normal text on a /Rotate 180 page); vertical glyphs with b<0 run top-to-bottom
    (normal text on a /Rotate 90 page) and with b>0 bottom-to-top (/Rotate 270).
    Text drawn counter-rotated so that it displays upright keeps the defaults.
    """
    upright_sign = sum((1 if c["matrix"][0] >= 0 else -1) for c in chars if c.get("upright") and "matrix" in c)
    rotated_sign = sum((1 if c["matrix"][1] >= 0 else -1) for c in chars if not c.get("upright") and "matrix" in c)
    params: dict[str, str] = {}
    if upright_sign < 0:
        params.update(char_dir="rtl", line_dir="btt")
    if rotated_sign < 0:
        params.update(char_dir_rotated="ttb", line_dir_rotated="rtl")
    elif rotated_sign > 0:
        params.update(char_dir_rotated="btt", line_dir_rotated="ltr")
    return params


# ----------------------------------------------------------------------- errors


class PdfInputError(Exception):
    """Base class for rejected or unreadable PDF input."""


class NotPdfError(PdfInputError):
    """The file is empty or its signature is not a PDF signature."""


class PdfTooLargeError(PdfInputError):
    """The file exceeds ``PdfLimits.max_file_bytes``."""


class PdfEncryptedError(PdfInputError):
    """The PDF is encrypted and cannot be opened without a password."""


class PdfMalformedError(PdfInputError):
    """The PDF structure cannot be parsed or contains no pages."""


class PdfLimitError(PdfInputError):
    """A configured page-count, page-content, DPI or pixel limit was exceeded."""


class PdfTimeoutError(PdfInputError):
    """Processing exceeded ``PdfLimits.max_seconds``."""


# ------------------------------------------------------------------------ limits


@dataclass(frozen=True)
class PdfLimits:
    max_file_bytes: int = 200 * 1024 * 1024
    max_pages: int = 2000
    max_chars_per_page: int = 200_000
    max_seconds: float = 300.0  # checked between pages; a single page is not interrupted
    max_render_dpi: int = 600
    max_render_pixels: int = 50_000_000  # A4 at 600 DPI is ~34.8 MP


# ----------------------------------------------------------------------- results


class PageStatus(StrEnum):
    OK = "ok"
    TEXT_EXTRACTION_FAILED = "text_extraction_failed"


@dataclass(frozen=True)
class ExtractionWarning:
    code: str
    message: str
    page_index: int | None = None


@dataclass(frozen=True)
class NativeWord:
    index: int  # position in content-stream (extraction) order on the page
    text: str  # exactly as extracted
    bbox: Box | None  # normalized displayed-page box; None if outside the visible area
    display_box: Box  # (x0, top, x1, bottom) in points, pdfplumber display space
    fontname: str | None
    glyph_height: float  # points, across the line direction (approximates font size)
    upright: bool
    notes: frozenset[str] = frozenset()  # "clipped", "degenerate", "outside_visible_area"


@dataclass(frozen=True)
class TextLine:
    """A run of consecutive words on one baseline: the text-region unit of Phase 2."""

    index: int
    word_indices: tuple[int, ...]
    text: str  # words joined by single spaces
    bbox: Box | None  # union of the visible word boxes


@dataclass(frozen=True)
class PageExtraction:
    page_index: int  # zero-based physical index
    page_label: str | None  # only from the PDF's /PageLabels tree
    width: float  # displayed (cropped, rotated) width in points
    height: float
    rotation: Rotation
    transform: CoordinateTransform
    status: PageStatus
    text: str  # lines (geometric order) joined by "\n"; built from unmodified word text
    words: tuple[NativeWord, ...]
    lines: tuple[TextLine, ...]
    stream_order: tuple[int, ...]  # line indices in content-stream order
    geometric_order: tuple[int, ...]  # line indices top-to-bottom, left-to-right
    ocr: OcrAssessment
    warnings: tuple[ExtractionWarning, ...] = ()


@dataclass(frozen=True)
class PdfExtraction:
    source_path: str
    sha256: str
    file_bytes: int
    page_count: int
    pages: tuple[PageExtraction, ...]
    engine: str
    engine_version: str
    parameters: dict[str, Any]
    created_at: datetime
    warnings: tuple[ExtractionWarning, ...] = ()


@dataclass
class RenderedPage:
    """A page raster for Phase 3 OCR.

    ``image`` is a PIL image ("RGB" or "L") of the displayed page: /Rotate and
    the CropBox are already applied. Pixel ``(px, py)`` therefore maps to the
    normalized point ``(px / width_px, py / height_px)`` in contract coordinates,
    and ``transform`` maps that back to PDF user space.
    """

    page_index: int
    dpi: float
    width_px: int
    height_px: int
    image: Any  # PIL.Image.Image; typed loosely so importing this module stays light
    transform: CoordinateTransform = field(repr=False)


# ------------------------------------------------------------------- validation


def check_pdf_file(path: Path, limits: PdfLimits | None = None) -> int:
    """Validate size and signature without parsing. Returns the file size in bytes."""
    limits = limits or PdfLimits()
    path = Path(path)
    if not path.is_file():
        raise NotPdfError(f"{path} is not a file")
    size = path.stat().st_size
    if size == 0:
        raise NotPdfError(f"{path.name} is empty")
    if size > limits.max_file_bytes:
        raise PdfTooLargeError(f"{path.name} is {size} bytes; limit is {limits.max_file_bytes}")
    with path.open("rb") as handle:
        head = handle.read(SIGNATURE_WINDOW)
    if PDF_SIGNATURE not in head:
        raise NotPdfError(f"{path.name} does not have a PDF signature (only PDF input is supported)")
    return size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _is_encryption_error(exc: BaseException) -> bool:
    for item in _exception_chain(exc):
        name = type(item).__name__
        if name in {"PDFPasswordIncorrect", "PDFEncryptionError", "PDFEncryptionWarning"}:
            return True
        if "password" in str(item).lower():
            return True
    return False


# -------------------------------------------------------------------- extraction


def extract_native_pdf(
    path: Path | str,
    *,
    limits: PdfLimits | None = None,
    thresholds: OcrThresholds | None = None,
) -> PdfExtraction:
    """Extract page metadata, native words/lines and an OCR-needed decision per page."""
    import pdfplumber

    limits = limits or PdfLimits()
    path = Path(path)
    deadline = time.monotonic() + limits.max_seconds
    size = check_pdf_file(path, limits)
    sha = _sha256(path)

    try:
        pdf = pdfplumber.open(path)
    except Exception as exc:  # pdfminer raises many unrelated types for bad input
        if _is_encryption_error(exc):
            raise PdfEncryptedError(f"{path.name} is encrypted and needs a password") from exc
        raise PdfMalformedError(f"{path.name} could not be parsed: {exc}") from exc

    try:
        try:
            page_count = len(pdf.pages)
        except Exception as exc:
            if _is_encryption_error(exc):
                raise PdfEncryptedError(f"{path.name} is encrypted and needs a password") from exc
            raise PdfMalformedError(f"{path.name} page tree could not be read: {exc}") from exc
        if page_count == 0:
            raise PdfMalformedError(f"{path.name} contains no pages")
        if page_count > limits.max_pages:
            raise PdfLimitError(f"{path.name} has {page_count} pages; limit is {limits.max_pages}")

        doc_warnings: list[ExtractionWarning] = []
        labels = _page_labels(pdf, page_count, doc_warnings)
        pages: list[PageExtraction] = []
        for index in range(page_count):
            if time.monotonic() > deadline:
                raise PdfTimeoutError(f"extraction exceeded {limits.max_seconds}s at page {index}")
            page = pdf.pages[index]
            try:
                pages.append(_extract_page(page, index, labels[index], limits, thresholds))
            finally:
                page.close()  # release pdfplumber's per-page object cache
    finally:
        pdf.close()

    import pdfplumber as _p  # version for provenance

    return PdfExtraction(
        source_path=str(path),
        sha256=sha,
        file_bytes=size,
        page_count=page_count,
        pages=tuple(pages),
        engine="pdfplumber",
        engine_version=_p.__version__,
        parameters=dict(WORD_PARAMS),
        created_at=datetime.now(timezone.utc),
        warnings=tuple(doc_warnings),
    )


def _page_labels(pdf: Any, page_count: int, warnings: list[ExtractionWarning]) -> list[str | None]:
    """Labels from /PageLabels only; anything unreliable becomes None."""
    try:
        labels = list(itertools.islice(pdf.doc.get_page_labels(), page_count))
    except Exception as exc:  # PDFNoPageLabels or a malformed label tree
        if type(exc).__name__ != "PDFNoPageLabels":
            warnings.append(ExtractionWarning("page_labels_unreadable", f"Ignored /PageLabels: {exc}"))
        return [None] * page_count
    if len(labels) != page_count:
        warnings.append(ExtractionWarning("page_labels_incomplete", "Ignored incomplete /PageLabels"))
        return [None] * page_count
    return [label if isinstance(label, str) and label.strip() else None for label in labels]


def _page_geometry(page: Any, index: int) -> tuple[Box, Rotation, CoordinateTransform]:
    try:
        rotation = Rotation(int(page.rotation) % 360)
    except ValueError as exc:
        raise PdfMalformedError(f"page {index} has unsupported rotation {page.rotation}") from exc
    media = _ordered([float(v) for v in page.page_obj.mediabox])
    crop = _ordered([float(v) for v in page.page_obj.cropbox])
    # Effective visible region is CropBox ∩ MediaBox (PDF 32000-1 §14.11.2).
    user_box: Box = (max(crop[0], media[0]), max(crop[1], media[1]), min(crop[2], media[2]), min(crop[3], media[3]))
    if user_box[2] - user_box[0] <= 0 or user_box[3] - user_box[1] <= 0:
        raise PdfMalformedError(f"page {index} has an empty crop box")
    # pdfplumber's page.cropbox is not rotated correctly for /Rotate 180, so derive it.
    visible = _user_box_to_display(user_box, media, rotation)
    transform = CoordinateTransform(
        source_space=SourceCoordinateSpace.PDF_USER_SPACE, crop_box=user_box, rotation_applied=rotation
    )
    return visible, rotation, transform


def _ordered(values: list[float]) -> Box:
    return (min(values[0], values[2]), min(values[1], values[3]), max(values[0], values[2]), max(values[1], values[3]))


def _user_box_to_display(box: Box, media: Box, rotation: Rotation) -> Box:
    """Map a user-space box into pdfplumber's display space (rotated MediaBox, top-left origin)."""
    mx0, my0, mx1, my1 = media
    x0, y0, x1, y1 = box
    if rotation is Rotation.R0:
        xs, ys = (x0 - mx0, x1 - mx0), (my1 - y1, my1 - y0)
    elif rotation is Rotation.R90:
        xs, ys = (y0 - my0, y1 - my0), (x0 - mx0, x1 - mx0)
    elif rotation is Rotation.R180:
        xs, ys = (mx1 - x1, mx1 - x0), (y0 - my0, y1 - my0)
    else:
        xs, ys = (my1 - y1, my1 - y0), (mx1 - x1, mx1 - x0)
    return (min(xs), min(ys), max(xs), max(ys))


def _extract_page(
    page: Any, index: int, label: str | None, limits: PdfLimits, thresholds: OcrThresholds | None
) -> PageExtraction:
    visible, rotation, transform = _page_geometry(page, index)
    width, height = visible[2] - visible[0], visible[3] - visible[1]
    warnings: list[ExtractionWarning] = []

    try:
        chars = page.chars
        if len(chars) > limits.max_chars_per_page:
            raise PdfLimitError(
                f"page {index} has {len(chars)} characters; limit is {limits.max_chars_per_page}")
        raw_words = page.extract_words(**WORD_PARAMS, **_direction_params(chars),
                                       extra_attrs=["fontname"], return_chars=True)
        char_rank = {id(c): i for i, c in enumerate(chars)}
        images = page.images
        vector_count = len(page.lines) + len(page.rects) + len(page.curves)
    except PdfLimitError:
        raise
    except Exception as exc:
        if _is_encryption_error(exc):
            raise PdfEncryptedError(f"page {index} is encrypted") from exc
        warnings.append(ExtractionWarning("text_extraction_failed", f"{type(exc).__name__}: {exc}", index))
        metrics = NativeTextMetrics(0, 0, 0, 0, 0.0, 0, 0.0)
        ocr = OcrAssessment(OcrDecision.OCR_RECOMMENDED,
                            (OcrReason.NATIVE_EXTRACTION_FAILED,), metrics, thresholds or OcrThresholds())
        return PageExtraction(index, label, width, height, rotation, transform,
                              PageStatus.TEXT_EXTRACTION_FAILED, "", (), (), (), (), ocr, tuple(warnings))

    words, geometric_words = _build_words(raw_words, char_rank, visible, index, warnings)
    lines = _build_lines(geometric_words)
    visible_chars = [c for c in chars if c["text"].strip() and _intersects(_char_box(c), visible)]
    metrics = NativeTextMetrics(
        char_count=len(visible_chars),
        word_count=len(words),
        unmapped_char_count=sum(1 for c in visible_chars if is_unmapped_char(c["text"])),
        image_count=len(images),
        image_coverage=_coverage([(i["x0"], i["top"], i["x1"], i["bottom"]) for i in images], visible),
        vector_object_count=vector_count,
        text_coverage=_coverage([w.display_box for w in words], visible),
    )
    if metrics.unmapped_char_count:
        warnings.append(ExtractionWarning(
            "unmapped_glyphs", f"{metrics.unmapped_char_count} characters lack a Unicode mapping", index))
    return PageExtraction(
        page_index=index,
        page_label=label,
        width=width,
        height=height,
        rotation=rotation,
        transform=transform,
        status=PageStatus.OK,
        text="\n".join(line.text for line in lines),
        words=tuple(words),
        lines=tuple(lines),
        stream_order=_stream_order(lines),
        geometric_order=tuple(line.index for line in lines),
        ocr=assess_ocr_need(metrics, thresholds),
        warnings=tuple(warnings),
    )


def _char_box(c: dict[str, Any]) -> Box:
    return (c["x0"], c["top"], c["x1"], c["bottom"])


def _intersects(box: Box, visible: Box) -> bool:
    return not (box[2] < visible[0] or box[0] > visible[2] or box[3] < visible[1] or box[1] > visible[3])


def _build_words(
    raw_words: list[dict[str, Any]],
    char_rank: dict[int, int],
    visible: Box,
    index: int,
    warnings: list[ExtractionWarning],
) -> tuple[list[NativeWord], list[NativeWord]]:
    """Return words in content-stream order (``index``) and in pdfplumber's geometric order."""
    first_char = [min((char_rank.get(id(c), len(char_rank)) for c in w.get("chars", ())), default=len(char_rank))
                  for w in raw_words]
    stream_rank = {pos: rank for rank, pos in enumerate(sorted(range(len(raw_words)),
                                                               key=lambda p: (first_char[p], p)))}
    geometric: list[NativeWord] = []
    outside = clipped = 0
    for pos, w in enumerate(raw_words):
        i = stream_rank[pos]
        display_box: Box = (float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]))
        bbox, notes = normalize_display_box(display_box, visible)
        if bbox is None:
            notes = frozenset({"outside_visible_area"})
            outside += 1
        elif "clipped" in notes:
            clipped += 1
        geometric.append(NativeWord(
            index=i, text=w["text"], bbox=bbox, display_box=display_box,
            fontname=w.get("fontname"),
            glyph_height=(display_box[3] - display_box[1]) if w.get("upright", True)
            else (display_box[2] - display_box[0]),
            upright=bool(w.get("upright", True)), notes=notes,
        ))
    if outside:
        warnings.append(ExtractionWarning(
            "words_outside_crop", f"{outside} words lie outside the visible crop box (kept, bbox=None)", index))
    if clipped:
        warnings.append(ExtractionWarning("words_clipped", f"{clipped} word boxes clipped to the crop box", index))
    return sorted(geometric, key=lambda word: word.index), geometric


def _build_lines(geometric_words: list[NativeWord]) -> list[TextLine]:
    """Group consecutive words (pdfplumber's direction-aware order) sharing a baseline.

    Lines are indexed in that geometric order. Word text is never altered.
    """
    groups: list[list[NativeWord]] = []
    for word in geometric_words:
        if groups and _same_line(groups[-1][-1], word):
            groups[-1].append(word)
        else:
            groups.append([word])
    lines = []
    for i, group in enumerate(groups):
        boxes = [w.bbox for w in group if w.bbox is not None]
        bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
        lines.append(TextLine(i, tuple(w.index for w in group), " ".join(w.text for w in group), bbox))
    return lines


def _same_line(a: NativeWord, b: NativeWord) -> bool:
    if a.upright != b.upright:
        return False
    ax0, atop, ax1, abottom = a.display_box
    bx0, btop, bx1, bbottom = b.display_box
    if a.upright:  # horizontal runs share a vertical band
        overlap, extent = min(abottom, bbottom) - max(atop, btop), min(abottom - atop, bbottom - btop)
        gap = max(bx0 - ax1, ax0 - bx1)  # along the line, either direction
    else:  # vertical runs share a horizontal band
        overlap, extent = min(ax1, bx1) - max(ax0, bx0), min(ax1 - ax0, bx1 - bx0)
        gap = max(btop - abottom, atop - bbottom)
    # A gap wider than LINE_BREAK_GAP x glyph height is a column gutter or table
    # gap, not a word space: start a new line so columns are never merged.
    return extent > 0 and overlap >= 0.5 * extent and gap <= LINE_BREAK_GAP * extent


def _stream_order(lines: list[TextLine]) -> tuple[int, ...]:
    """Line indices ordered by their first word's content-stream position."""
    return tuple(sorted((line.index for line in lines), key=lambda i: min(lines[i].word_indices)))


def _coverage(boxes: Iterable[Box], visible: Box, grid: int = 200) -> float:
    """Fraction of the visible area covered by the union of ``boxes`` (grid estimate)."""
    mask = np.zeros((grid, grid), dtype=bool)
    vx0, vtop, vx1, vbottom = visible
    w, h = vx1 - vx0, vbottom - vtop
    any_box = False
    for x0, top, x1, bottom in boxes:
        c0 = max(0, math.floor((min(x0, x1) - vx0) / w * grid))
        c1 = min(grid, math.ceil((max(x0, x1) - vx0) / w * grid))
        r0 = max(0, math.floor((min(top, bottom) - vtop) / h * grid))
        r1 = min(grid, math.ceil((max(top, bottom) - vtop) / h * grid))
        if c1 > c0 and r1 > r0:
            mask[r0:r1, c0:c1] = True
            any_box = True
    return float(mask.mean()) if any_box else 0.0


# ---------------------------------------------------------------------- rendering


def _open_pdfium(path: Path, limits: PdfLimits) -> Any:
    import pypdfium2 as pdfium

    check_pdf_file(path, limits)
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise PdfEncryptedError(f"{path.name} is encrypted and needs a password") from exc
        raise PdfMalformedError(f"{path.name} could not be opened for rendering: {exc}") from exc


def iter_rendered_pages(
    path: Path | str,
    page_indices: Iterable[int] | None = None,
    *,
    dpi: float = 300,
    grayscale: bool = False,
    limits: PdfLimits | None = None,
) -> Iterator[RenderedPage]:
    """Render pages one at a time. Each PDFium page/bitmap is closed before yielding.

    The document is closed when the iterator is exhausted or closed early.
    """
    limits = limits or PdfLimits()
    path = Path(path)
    if not 0 < dpi <= limits.max_render_dpi:
        raise PdfLimitError(f"dpi {dpi} must be in (0, {limits.max_render_dpi}]")
    deadline = time.monotonic() + limits.max_seconds
    document = _open_pdfium(path, limits)
    try:
        count = len(document)
        if count == 0:
            raise PdfMalformedError(f"{path.name} contains no pages")
        if count > limits.max_pages:
            raise PdfLimitError(f"{path.name} has {count} pages; limit is {limits.max_pages}")
        indices = range(count) if page_indices is None else list(page_indices)
        for index in indices:
            if not 0 <= index < count:
                raise IndexError(f"page index {index} out of range 0..{count - 1}")
            if time.monotonic() > deadline:
                raise PdfTimeoutError(f"rendering exceeded {limits.max_seconds}s at page {index}")
            yield _render_one(document, index, dpi, grayscale, limits)
    finally:
        document.close()


def render_page(
    path: Path | str, page_index: int, *, dpi: float = 300, grayscale: bool = False,
    limits: PdfLimits | None = None,
) -> RenderedPage:
    iterator = iter_rendered_pages(path, [page_index], dpi=dpi, grayscale=grayscale, limits=limits)
    try:
        return next(iterator)
    finally:
        iterator.close()


def estimate_render_pixels(width_pt: float, height_pt: float, dpi: float) -> tuple[int, int]:
    scale = dpi / 72.0
    return max(1, math.ceil(width_pt * scale)), max(1, math.ceil(height_pt * scale))


def _render_one(document: Any, index: int, dpi: float, grayscale: bool, limits: PdfLimits) -> RenderedPage:
    page = bitmap = None
    try:
        page = document[index]
        width_pt, height_pt = page.get_size()  # displayed size: crop and rotation applied
        w_px, h_px = estimate_render_pixels(width_pt, height_pt, dpi)
        if w_px * h_px > limits.max_render_pixels:
            raise PdfLimitError(
                f"page {index} at {dpi} DPI needs {w_px}x{h_px} pixels; limit is {limits.max_render_pixels}")
        rotation = Rotation(page.get_rotation() % 360)
        crop = page.get_cropbox()
        transform = CoordinateTransform(
            source_space=SourceCoordinateSpace.PDF_USER_SPACE,
            crop_box=(min(crop[0], crop[2]), min(crop[1], crop[3]), max(crop[0], crop[2]), max(crop[1], crop[3])),
            rotation_applied=rotation,
            render_dpi=float(dpi),
        )
        bitmap = page.render(scale=dpi / 72.0, grayscale=grayscale, may_draw_forms=False)
        image = bitmap.to_pil().copy()  # detach from PDFium's buffer before closing it
        if grayscale and image.mode != "L":
            image = image.convert("L")
        return RenderedPage(index, float(dpi), image.width, image.height, image, transform)
    finally:
        for obj in (bitmap, page):
            if obj is not None:
                obj.close()


# ---------------------------------------------------------- Phase 1 conversion


NATIVE_CONFIDENCE_REASON = "Native PDF text layer; pdfplumber reports no confidence."


def to_contract_document(
    extraction: PdfExtraction,
    *,
    source_uri: str,
    document_id: UUID | None = None,
    source_asset_id: UUID | None = None,
    title: str | None = None,
) -> Any:
    """Convert to a Phase 1 ``Document``.

    Each visible text line becomes a provisional ``paragraph`` block:
    * language ``und`` with ``language_uncertain`` (no language detection yet);
    * ``reading_order_uncertain`` (stream order is only a candidate);
    * null confidence with origin ``not_available``.
    Lines entirely outside the crop box have no valid bbox and are omitted;
    they remain in ``PdfExtraction`` with a ``words_outside_crop`` warning.
    """
    from pathya_document_ai import models as m

    doc_id = document_id or m.new_id()
    asset = m.SourceAsset(id=source_asset_id or m.new_id(), uri=source_uri,
                          media_type=m.MediaType.PDF, sha256=extraction.sha256)
    provenance = m.Provenance(method=m.ExtractionMethod.NATIVE_PDF_TEXT, engine=extraction.engine,
                              engine_version=extraction.engine_version,
                              parameters={k: v for k, v in extraction.parameters.items()},
                              created_at=extraction.created_at)
    pages, blocks = [], []
    for pe in extraction.pages:
        page = m.Page(document_id=doc_id, page_index=pe.page_index, page_label=pe.page_label,
                      width=pe.width, height=pe.height, units="pt", rotation=pe.rotation,
                      source_asset_id=asset.id, transform=pe.transform)
        pages.append(page)
        order = 0
        for line_index in pe.stream_order:
            line = pe.lines[line_index]
            if line.bbox is None:
                continue
            flags = [m.QualityFlag.READING_ORDER_UNCERTAIN, m.QualityFlag.LANGUAGE_UNCERTAIN]
            if any(is_unmapped_char(ch) for ch in line.text):
                flags.append(m.QualityFlag.POSSIBLE_OCR_ERROR)
            blocks.append(m.Block(
                page_id=page.id, block_type=m.BlockType.PARAGRAPH, reading_order=order, bbox=line.bbox,
                raw_text=line.text, current_text=line.text, language=m.Language.UNDETERMINED,
                confidence=m.Confidence.unavailable(NATIVE_CONFIDENCE_REASON),
                quality_flags=flags, provenance=provenance,
            ))
            order += 1
    return m.Document(id=doc_id, title=title, languages=[m.Language.UNDETERMINED], source_asset=asset,
                      pages=pages, blocks=blocks, created_at=extraction.created_at)
