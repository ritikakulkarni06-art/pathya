"""REAL Docling layout integration tests (Phase 4).

Run Docling 2.70 with the locally downloaded layout/TableFormer weights on
synthetic pages. Skipped, with the reason shown, when Docling models are not
available. Model directory: PATHYA_DOCLING_ARTIFACTS, else ``local/docling-models``.
These verify behaviour on clean synthetic pages only, not accuracy on real textbooks.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))
from _layout_fixtures import scanned_page_from_image, write_textbook  # noqa: E402
from _pdf_factory import PageSpec, upright_text, write_pdf  # noqa: E402

from pathya_document_ai.layout import LayoutStatus, build_layout_document  # noqa: E402
from pathya_document_ai.layout_docling import (  # noqa: E402
    DoclingConfig,
    DoclingLayoutEngine,
    DoclingUnavailableError,
    docling_versions,
)
from pathya_document_ai.models import BlockType, EdgeType, Language, QualityFlag  # noqa: E402
from pathya_document_ai.pdf import extract_native_pdf  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engines import unavailable  # noqa: E402

pytestmark = pytest.mark.integration


def _artifacts() -> Path:
    return Path(os.environ.get("PATHYA_DOCLING_ARTIFACTS", ROOT / "local" / "docling-models"))


@pytest.fixture(scope="module")
def engine() -> DoclingLayoutEngine:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # weights are local; never download during tests
    try:
        return DoclingLayoutEngine(DoclingConfig(artifacts_path=_artifacts()))
    except DoclingUnavailableError as exc:
        unavailable(f"REAL DOCLING UNAVAILABLE: {exc}")


@pytest.fixture(scope="module")
def textbook(engine: DoclingLayoutEngine, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    path = write_textbook(tmp_path_factory.mktemp("docling") / "textbook.pdf")
    extraction = extract_native_pdf(path)
    layouts = engine.analyze_document(path, extraction)
    result = build_layout_document(extraction, layouts, source_uri="asset://synthetic/textbook.pdf")
    return {"layouts": layouts, "result": result, "doc": result.document}


def _page_blocks(doc: Any, index: int) -> list[Any]:
    pid = next(p.id for p in doc.pages if p.page_index == index)
    return sorted((b for b in doc.blocks if b.page_id == pid and b.parent_id is None), key=lambda b: b.reading_order)


def test_real_docling_version(engine: DoclingLayoutEngine) -> None:
    versions = docling_versions()
    assert versions["docling"] == "2.70.0" and versions["docling-ibm-models"] == "3.9.1"
    assert engine.model_fingerprint != "unknown"


def test_real_all_native_pages_use_direct_mode(textbook: dict[str, Any]) -> None:
    assert {p.mode for p in textbook["layouts"].values()} == {"docling_pdf"}
    assert all(p.status is LayoutStatus.OK for p in textbook["layouts"].values())


def test_real_headings_paragraphs_lists(textbook: dict[str, Any]) -> None:
    blocks = _page_blocks(textbook["doc"], 0)
    assert [(b.block_type, b.raw_text[:12]) for b in blocks] == [
        (BlockType.HEADING, "Chapter 4 Mo"), (BlockType.HEADING, "4.1 Describi"),
        (BlockType.PARAGRAPH, "Motion is th"), (BlockType.PARAGRAPH, "Speed tells "),
        (BlockType.HEADING, "Key ideas"), (BlockType.LIST_ITEM, "1. Distance "),
        (BlockType.LIST_ITEM, "2. Displacem"), (BlockType.LIST_ITEM, "3. Speed is "),
        (BlockType.PARAGRAPH, "Acceleration")]
    assert all(b.language is Language.ENGLISH and b.confidence.score is None for b in blocks)
    assert blocks[0].provenance.engine == "docling" and blocks[0].provenance.engine_version == "2.70.0"


def test_real_two_column_reading_order(textbook: dict[str, Any]) -> None:
    blocks = _page_blocks(textbook["doc"], 1)
    sides = ["L" if (b.bbox[0] + b.bbox[2]) / 2 < 0.5 else "R" for b in blocks[1:]]
    assert blocks[0].raw_text == "4.2 Speed and Velocity"
    assert sides == sorted(sides) and sides.count("L") == 3 and sides.count("R") == 3
    report = textbook["result"].reports[1].order
    assert report.selected == "layout_engine" and report.columns == 2 and not report.ambiguous
    assert report.discordant_pairs.get("geometric_columns") == 0


def test_real_table_cells_and_headers(textbook: dict[str, Any]) -> None:
    doc = textbook["doc"]
    table = next(b for b in _page_blocks(doc, 2) if b.block_type is BlockType.TABLE)
    assert (table.table.row_count, table.table.column_count) == (4, 3)
    cells = {c.id: c for c in doc.blocks if c.parent_id == table.id}
    grid = {(c.table_cell.row_index, c.table_cell.column_index): c for c in cells.values()}
    assert [grid[(0, i)].raw_text for i in range(3)] == ["Quantity", "SI unit", "Symbol"]
    assert grid[(3, 1)].raw_text == "metre per second"
    assert all(grid[(0, i)].table_cell.is_header for i in range(3))
    assert [cells[h].raw_text for h in grid[(2, 2)].table_cell.header_cell_ids] == ["Symbol"]
    caption = next(b for b in _page_blocks(doc, 2) if b.block_type is BlockType.CAPTION)
    assert any(e.edge_type is EdgeType.CAPTION_OF and e.source_id == caption.id and e.target_id == table.id
               for e in doc.edges)


def test_real_figure_and_caption(textbook: dict[str, Any]) -> None:
    blocks = _page_blocks(textbook["doc"], 3)
    figure = next(b for b in blocks if b.block_type is BlockType.FIGURE)
    caption = next(b for b in blocks if b.block_type is BlockType.CAPTION)
    assert figure.figure.caption_block_id == caption.id
    assert figure.figure.source_caption == "Figure 4.2 Distance-time graph of a moving bicycle"
    assert figure.figure.alt_text is None


def test_real_equation_region(textbook: dict[str, Any]) -> None:
    eq = next(b for b in _page_blocks(textbook["doc"], 4) if b.block_type is BlockType.EQUATION)
    assert eq.equation.source_text.startswith("v = u + a t") and eq.equation.mathml is None
    assert QualityFlag.MATH_NEEDS_REVIEW in eq.quality_flags


def test_real_image_mode_rotated_page(engine: DoclingLayoutEngine, tmp_path: Path) -> None:
    lines = [upright_text(90, 130 + i * 16, 120, f"Body text line {i} on a rotated page about motion.", 11)
             for i in range(6)]
    spec = PageSpec(texts=[upright_text(90, 100, 120, "4.6 Rotated Section", 18), *lines], rotate=90)
    path = write_pdf(tmp_path / "rot.pdf", [spec])
    extraction = extract_native_pdf(path)
    layout = engine.analyze_page(path, extraction.pages[0])
    assert layout.mode == "docling_image" and layout.status is LayoutStatus.OK
    blocks = _page_blocks(build_layout_document(extraction, {0: layout}, source_uri="asset://r").document, 0)
    assert blocks[0].raw_text == "4.6 Rotated Section"
    body = " ".join(b.raw_text for b in blocks[1:])
    assert [f"line {i}" in body for i in range(6)] == [True] * 6
    assert body.index("line 0") < body.index("line 5")


def test_real_scanned_hindi_and_mixed_with_ocr(engine: DoclingLayoutEngine, tmp_path: Path) -> None:
    from pathya_document_ai.ocr import TesseractEngine, ocr_pdf_pages
    from pathya_document_ai.tesseract import OcrError, TesseractConfig

    tessdata = Path(os.environ.get("PATHYA_TESSDATA_DIR", ROOT / "local" / "tessdata"))
    try:
        ocr_engine = TesseractEngine(TesseractConfig(tessdata_dir=tessdata if tessdata.is_dir() else None))
    except OcrError as exc:
        unavailable(f"REAL TESSERACT UNAVAILABLE: {exc}")

    def gray(name: str) -> tuple[int, int, bytes]:
        img = Image.open(ROOT / "tests" / "fixtures" / "ocr" / f"{name}.png").convert("L")
        return img.width, img.height, img.tobytes()

    path = write_pdf(tmp_path / "scan.pdf", [scanned_page_from_image(gray("hindi")),
                                              scanned_page_from_image(gray("mixed"))])
    extraction = extract_native_pdf(path)
    run = ocr_pdf_pages(path, extraction, engine=ocr_engine, dpi=300, include_recommended=True)
    layouts = engine.analyze_document(path, extraction)
    assert {p.mode for p in layouts.values()} == {"docling_image"}
    doc = build_layout_document(extraction, layouts, {r.page_index: r for r in run.results},
                                source_uri="asset://scan").document
    hindi = " ".join(b.raw_text for b in _page_blocks(doc, 0))
    assert "प्रकाश का परावर्तन" in hindi and "सूर्य" in hindi
    assert {b.language for b in _page_blocks(doc, 0)} == {Language.HINDI}
    mixed = _page_blocks(doc, 1)
    assert any(b.language is Language.MULTIPLE and QualityFlag.MIXED_SCRIPT in b.quality_flags for b in mixed)
    assert all(b.provenance.parameters.get("ocr_engine", "").startswith("tesseract 5.") for b in mixed)
    assert all(b.confidence.score is not None for b in mixed)  # OCR confidence carried through


def test_real_failure_is_reported_not_raised(engine: DoclingLayoutEngine, tmp_path: Path) -> None:
    good = write_pdf(tmp_path / "ok.pdf", [PageSpec(texts=[upright_text(0, 72, 700, "Some heading text", 14)])])
    extraction = extract_native_pdf(good)
    good.unlink()  # the file disappears before layout analysis
    page = engine.analyze_page(good, extraction.pages[0])
    assert page.status is LayoutStatus.FAILED and page.warnings
