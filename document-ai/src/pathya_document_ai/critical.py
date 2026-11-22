"""Critical-symbol uncertainty (contract 1.2.0 flag ``critical_symbol_uncertain``).

A *critical token* carries meaning that a small recognition error inverts or
scales: mathematical signs (+ - − × ÷ = < > ≤ ≥ ± ^), decimal points between
digits, exponents and super/subscripts, percent/degree signs, and units next
to numbers (``m/s``, ``cm²``, ``kg``, ``°C`` …).

A critical token is *uncertain* when:

* it came from OCR and Tesseract's confidence is missing or below
  ``CRITICAL_CONFIDENCE`` (0.90), or
* it came from the native text layer and contains an undecodable glyph, or
* the block is an equation whose text came from OCR (OCR of math is not
  trusted regardless of score).

The flag is never removed once set. Review is recorded separately in
``review_status``; see ``is_trusted_evidence`` for how consumers must treat it.
This detector cannot see what OCR did not output: a faint minus sign that was
dropped entirely leaves no token to flag. That gap is why equations from OCR
are always flagged.
"""

from __future__ import annotations

import re
from typing import Any

CRITICAL_CONFIDENCE = 0.90

_SIGNS = set("+-−–×÷=<>≤≥±^%°√≈≠/")
_SUPERSUB = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
                "₀₁₂₃₄₅₆₇₈₉")
_DECIMAL = re.compile(r"\d[.,]\d")
_EXPONENT = re.compile(r"\d\s*(?:\^|\*\*|e[+-]?\d)", re.IGNORECASE)
_UNITS = {"m", "cm", "mm", "km", "kg", "g", "mg", "s", "ms", "h", "min", "n", "j", "w", "kw", "pa", "k", "mol",
          "a", "v", "hz", "l", "ml", "m/s", "m/s2", "m/s²", "km/h", "cm²", "m²", "m³", "°c", "°f", "kj", "kwh"}


def is_critical_token(text: str, previous: str | None = None) -> bool:
    """True if ``text`` (one word) carries a sign, decimal point, exponent or unit."""
    if not text:
        return False
    if any(ch in _SIGNS or ch in _SUPERSUB for ch in text):
        return True
    if _DECIMAL.search(text) or _EXPONENT.search(text):
        return True
    word = text.strip(".,;:()[]").lower()
    if word in _UNITS and (previous is not None and any(ch.isdigit() for ch in previous)):
        return True
    return bool(re.fullmatch(r"\d+(?:[.,]\d+)?[a-zA-Z°%²³/]+", text.strip(".,;:()")))  # 4.5m/s, 30°C


def critical_uncertain(tokens: list[tuple[str, str, float | None]], *, equation: bool = False) -> bool:
    """``tokens`` are ``(text, source, confidence)`` in reading order; source is 'native' or 'ocr'."""
    from pathya_document_ai.quality import is_unmapped_char

    if equation and any(source == "ocr" for _, source, _ in tokens):
        return True
    previous: str | None = None
    for text, source, confidence in tokens:
        if source == "native" and any(is_unmapped_char(ch) for ch in text) and any(ch.isdigit() for ch in text):
            return True  # an undecodable glyph inside a number may be a lost sign or decimal point
        if is_critical_token(text, previous):
            if source == "ocr" and (confidence is None or confidence < CRITICAL_CONFIDENCE):
                return True
            if source == "native" and any(is_unmapped_char(ch) for ch in text):
                return True
        previous = text
    return False


def is_trusted_evidence(block: Any, page: Any) -> bool:
    """Whether a block may be used as trusted evidence for search and answers (1.2.0 policy).

    Approved by P2 and P3 (21 Nov 2026). A block is **not** trusted evidence when:

    * its page is not ``ok`` (``needs_ocr``, ``partial``, ``failed``; ``blank``
      pages have no blocks);
    * it is ``needs_review`` or ``rejected``;
    * it carries ``unsupported_content`` and has not been ``approved``;
      approval permits eligibility but preserves the flag and review marker;
    * it carries ``block_type_uncertain`` and the type has not been verified,
      i.e. a human has not ``approved`` the block (``mark_reviewed`` in P3);
    * it carries ``critical_symbol_uncertain`` and has not been ``approved``.

    This governs retrieval and answering only. Every block stays in the
    Document and the reader still displays it, with the warning for its flags.
    """
    from pathya_document_ai import models as m

    if page.status is not None and page.status is not m.PageStatus.OK:
        return False
    if block.review_status in (m.ReviewStatus.NEEDS_REVIEW, m.ReviewStatus.REJECTED):
        return False
    gated_until_approved = {m.QualityFlag.CRITICAL_SYMBOL_UNCERTAIN, m.QualityFlag.BLOCK_TYPE_UNCERTAIN,
                            m.QualityFlag.UNSUPPORTED_CONTENT}
    if gated_until_approved.intersection(block.quality_flags) and block.review_status is not m.ReviewStatus.APPROVED:
        return False
    return True


def critical_flag(block: Any) -> bool:
    """P3's ``critical_flag``: the block carries an unresolved critical-symbol uncertainty."""
    from pathya_document_ai import models as m

    return (m.QualityFlag.CRITICAL_SYMBOL_UNCERTAIN in block.quality_flags
            and block.review_status is not m.ReviewStatus.APPROVED)
