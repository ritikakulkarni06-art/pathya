"""Native-text diagnostics: a conservative, explainable OCR-needed decision.

No OCR runs here. The decision is made from measurements of the native text
layer and page objects, and every outcome carries machine-readable reasons.
Short text on its own is never treated as evidence of a scanned page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class OcrDecision(StrEnum):
    NATIVE_TEXT = "native_text"  # native text layer is usable; OCR not needed
    BLANK = "blank"  # no text and nothing that could contain text
    OCR_RECOMMENDED = "ocr_recommended"  # text may be hidden in images/vectors; OCR advisable
    OCR_REQUIRED = "ocr_required"  # no usable native text and image content present


class OcrReason(StrEnum):
    NO_NATIVE_TEXT = "no_native_text"
    IMAGE_ONLY_PAGE = "image_only_page"
    PARTIAL_IMAGE_NO_TEXT = "partial_image_no_text"
    VECTOR_HEAVY_NO_TEXT = "vector_heavy_no_text"  # possibly text converted to outlines
    UNMAPPED_GLYPHS = "unmapped_glyphs"  # text present but not decodable to Unicode
    IMAGE_HEAVY_SPARSE_TEXT = "image_heavy_sparse_text"
    SUFFICIENT_NATIVE_TEXT = "sufficient_native_text"
    SHORT_TEXT_NOT_SCAN_EVIDENCE = "short_text_not_scan_evidence"
    FULL_PAGE_IMAGE_UNDER_TEXT = "full_page_image_under_text"  # text may be a prior OCR layer
    EMPTY_PAGE = "empty_page"
    NATIVE_EXTRACTION_FAILED = "native_extraction_failed"


@dataclass(frozen=True)
class OcrThresholds:
    image_only_coverage: float = 0.25  # no text + images covering at least this -> required
    image_heavy_coverage: float = 0.5  # with sparse text -> recommended
    sparse_text_chars: int = 200
    short_text_chars: int = 40
    unmapped_glyph_ratio: float = 0.25
    unmapped_min_chars: int = 10
    vector_heavy_objects: int = 50
    full_page_image_coverage: float = 0.9


@dataclass(frozen=True)
class NativeTextMetrics:
    """Measurements of one page's visible area."""

    char_count: int  # non-whitespace characters in the native text layer
    word_count: int
    unmapped_char_count: int  # '(cid:N)', U+FFFD, private-use and control characters
    image_count: int
    image_coverage: float  # 0..1 union of image area over visible page area
    vector_object_count: int  # lines + rects + curves
    text_coverage: float  # 0..1 union of word boxes over visible area

    @property
    def unmapped_ratio(self) -> float:
        return self.unmapped_char_count / self.char_count if self.char_count else 0.0


@dataclass(frozen=True)
class OcrAssessment:
    decision: OcrDecision
    reasons: tuple[OcrReason, ...]
    metrics: NativeTextMetrics
    thresholds: OcrThresholds = field(default_factory=OcrThresholds)

    @property
    def needs_ocr(self) -> bool:
        return self.decision in (OcrDecision.OCR_REQUIRED, OcrDecision.OCR_RECOMMENDED)


def assess_ocr_need(metrics: NativeTextMetrics, thresholds: OcrThresholds | None = None) -> OcrAssessment:
    t = thresholds or OcrThresholds()
    m = metrics

    def result(decision: OcrDecision, *reasons: OcrReason) -> OcrAssessment:
        return OcrAssessment(decision, reasons, m, t)

    if m.char_count == 0:
        if m.image_coverage >= t.image_only_coverage:
            return result(OcrDecision.OCR_REQUIRED, OcrReason.NO_NATIVE_TEXT, OcrReason.IMAGE_ONLY_PAGE)
        if m.image_count > 0:
            return result(OcrDecision.OCR_RECOMMENDED, OcrReason.NO_NATIVE_TEXT, OcrReason.PARTIAL_IMAGE_NO_TEXT)
        if m.vector_object_count >= t.vector_heavy_objects:
            return result(OcrDecision.OCR_RECOMMENDED, OcrReason.NO_NATIVE_TEXT, OcrReason.VECTOR_HEAVY_NO_TEXT)
        return result(OcrDecision.BLANK, OcrReason.NO_NATIVE_TEXT, OcrReason.EMPTY_PAGE)

    if m.char_count >= t.unmapped_min_chars and m.unmapped_ratio >= t.unmapped_glyph_ratio:
        return result(OcrDecision.OCR_REQUIRED, OcrReason.UNMAPPED_GLYPHS)

    if m.image_coverage >= t.image_heavy_coverage and m.char_count < t.sparse_text_chars:
        return result(OcrDecision.OCR_RECOMMENDED, OcrReason.IMAGE_HEAVY_SPARSE_TEXT)

    reasons = [OcrReason.SUFFICIENT_NATIVE_TEXT]
    if m.char_count < t.short_text_chars:
        reasons.append(OcrReason.SHORT_TEXT_NOT_SCAN_EVIDENCE)
    if m.image_coverage >= t.full_page_image_coverage:
        reasons.append(OcrReason.FULL_PAGE_IMAGE_UNDER_TEXT)
    return result(OcrDecision.NATIVE_TEXT, *reasons)


def is_unmapped_char(text: str) -> bool:
    """True for a pdfminer char that did not decode to meaningful Unicode."""
    if text.startswith("(cid:"):
        return True
    return any(
        ch == "�" or 0xE000 <= ord(ch) <= 0xF8FF or (ord(ch) < 32 and ch not in "\t\n\r")
        for ch in text
    )
