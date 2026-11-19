"""REAL engines through the public entry point (Tesseract eng+hin and Docling).

Skipped when engines are missing, unless PATHYA_REQUIRE_REAL_ENGINES=1 (CI),
which turns a missing engine into a failure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unicodedata

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engines import unavailable  # noqa: E402
from _layout_fixtures import write_textbook  # noqa: E402

from pathya_document_ai.pipeline import (  # noqa: E402
    EngineUnavailableError,
    ExtractionOptions,
    extract_document,
    producer_violations,
    validate_document_json,
)

pytestmark = pytest.mark.integration


def _options(**kw: object) -> ExtractionOptions:
    tessdata = Path(os.environ.get("PATHYA_TESSDATA_DIR", ROOT / "local" / "tessdata"))
    artifacts = Path(os.environ.get("PATHYA_DOCLING_ARTIFACTS", ROOT / "local" / "docling-models"))
    return ExtractionOptions(tessdata_dir=tessdata if tessdata.is_dir() else None, docling_artifacts=artifacts,
                             ocr="always" if kw.pop("force_ocr", False) else "auto", layout="required", **kw)  # type: ignore[arg-type]


def _run(source: Path, **kw: object) -> object:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        return extract_document(source, _options(**kw))
    except EngineUnavailableError as exc:
        unavailable(f"REAL ENGINES UNAVAILABLE: {exc}")


def test_real_pdf_to_validated_document(tmp_path: Path) -> None:
    result = _run(write_textbook(tmp_path / "tb.pdf"), source_uri="asset://synthetic/tb")
    doc = result.document  # type: ignore[attr-defined]
    assert result.engines["layout"].startswith("docling ") and result.engines["ocr"].startswith("tesseract ")  # type: ignore[attr-defined]
    assert doc.schema_version == "1.2.0" and producer_violations(doc) == []
    levels = {b.raw_text: b.heading_level for b in doc.blocks if b.block_type.value == "heading"}
    assert levels["Chapter 4 Motion"] == 1  # largest heading glyphs in the document
    assert min(v for v in levels.values() if v) == 1 and all(1 <= v <= 6 for v in levels.values() if v)
    equation = next(b for b in doc.blocks if b.block_type.value == "equation")
    assert equation.review_status.value == "needs_review"  # math_needs_review
    assert validate_document_json(result.to_json()) == doc  # type: ignore[attr-defined]


def test_real_png_image_to_validated_document() -> None:
    result = _run(ROOT / "tests" / "fixtures" / "ocr" / "hindi.png", force_ocr=True)
    doc = result.document  # type: ignore[attr-defined]
    page = doc.pages[0]
    assert doc.source_asset.media_type.value == "image/png" and page.units == "px"
    assert page.transform.source_space.value == "image_pixels" and page.status.value == "ok"
    text = unicodedata.normalize("NFC", " ".join(b.raw_text or "" for b in doc.blocks))
    expected = json.loads((ROOT / "tests" / "fixtures" / "ocr" / "expected.json").read_text(encoding="utf-8"))
    assert unicodedata.normalize("NFC", expected["hindi"][0]) in text
    assert {b.language.value for b in doc.blocks} == {"hi"} and producer_violations(doc) == []
