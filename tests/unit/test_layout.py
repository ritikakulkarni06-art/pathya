"""Phase 4 layout tests with MOCKED layout regions (no Docling models).

Regions are hand-built around Phase 2 word geometry from synthetic PDFs. These
test assembly, reading order, tables, captions, flags and contract output; they
say nothing about Docling's real detection quality (see tests/integration).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from _fake_ocr import FakeEngine, W
from _layout_fixtures import write_textbook
from _pdf_factory import Image as PdfImage, PageSpec, Text, write_pdf
from pathya_document_ai import layout_docling as ld
from pathya_document_ai.layout import (
    LayoutConfig,
    LayoutPage,
    LayoutRegion,
    LayoutStatus,
    RegionKind,
    TableCandidate,
    TableCellCandidate,
    build_layout_document,
    clean_bbox,
)
from pathya_document_ai.models import BlockType, Document, EdgeType, Language, QualityFlag
from pathya_document_ai.ocr import OcrConfig, ocr_pdf_pages
from pathya_document_ai.pdf import extract_native_pdf
from pathya_document_ai.preprocess import PreprocessConfig
from pathya_document_ai.schema import build_json_schema

NO_PREP = OcrConfig(preprocess=PreprocessConfig(deskew=False, contrast="none"))


def _layout(page_index: int, regions: list[LayoutRegion], status: LayoutStatus = LayoutStatus.OK) -> LayoutPage:
    return LayoutPage(page_index, status, "mock", tuple(regions), "mock-layout", "0.0", "mock-model", {}, 0.01)


def _around(boxes: list[Any], pad: float = 0.004) -> tuple[float, float, float, float]:
    return (min(b[0] for b in boxes) - pad, min(b[1] for b in boxes) - pad,
            max(b[2] for b in boxes) + pad, max(b[3] for b in boxes) + pad)


def _region(i: int, kind: RegionKind, box: Any, conf: float | None = 0.95, **kw: Any) -> LayoutRegion:
    return LayoutRegion(index=i, kind=kind, source_label=kind.value, bbox=box, confidence=conf, **kw)


def _lines_matching(page: Any, prefix: str) -> list[Any]:
    return [line.bbox for line in page.lines if line.text.startswith(prefix)]


def _blocks(result: Any, page_index: int = 0) -> list[Any]:
    doc = result.document
    pid = next(p.id for p in doc.pages if p.page_index == page_index)
    top = [b for b in doc.blocks if b.page_id == pid and b.parent_id is None]
    return sorted(top, key=lambda b: b.reading_order)


@pytest.fixture(scope="module")
def textbook(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    path = write_textbook(tmp_path_factory.mktemp("tb") / "tb.pdf")
    return path, extract_native_pdf(path)


def _paragraph_groups(page: Any, keep: Any = lambda box: True) -> list[tuple[str, Any]]:
    """Group Phase 2 lines into blocks by vertical gap (what a layout model would box)."""
    lines = sorted((l for l in page.lines if l.bbox is not None and keep(l.bbox)), key=lambda l: l.bbox[1])
    groups: list[list[Any]] = []
    for line in lines:
        height = line.bbox[3] - line.bbox[1]
        if groups and line.bbox[1] - groups[-1][-1].bbox[3] < 0.4 * height:
            groups[-1].append(line)
        else:
            groups.append([line])
    return [(" ".join(l.text for l in g), _around([l.bbox for l in g])) for g in groups]


def _kind_for(text: str) -> RegionKind:
    if text.startswith("Chapter"):
        return RegionKind.TITLE
    if text[:3] in ("4.1", "4.2", "Key"):
        return RegionKind.SECTION_HEADER
    if text[:2] in ("1.", "2.", "3."):
        return RegionKind.LIST_ITEM
    return RegionKind.TEXT


def _single_column_regions(page: Any, with_order: bool = True, skip_last: bool = False) -> list[LayoutRegion]:
    groups = _paragraph_groups(page)
    if skip_last:
        groups = groups[:-1]
    return [_region(i, _kind_for(text), box, engine_order=i if with_order else None)
            for i, (text, box) in enumerate(groups)]


# --------------------------------------------------------------- block types


def test_headings_paragraphs_and_lists(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    result = build_layout_document(ex, {0: _layout(0, _single_column_regions(ex.pages[0]))}, source_uri="asset://t")
    blocks = _blocks(result)
    kinds = [b.block_type for b in blocks]
    assert kinds == [BlockType.HEADING, BlockType.HEADING, BlockType.PARAGRAPH, BlockType.PARAGRAPH,
                     BlockType.HEADING, BlockType.LIST_ITEM, BlockType.LIST_ITEM, BlockType.LIST_ITEM,
                     BlockType.PARAGRAPH]
    assert not any(QualityFlag.BLOCK_TYPE_UNCERTAIN in b.quality_flags for b in blocks)
    assert blocks[0].raw_text == "Chapter 4 Motion"
    assert blocks[5].raw_text.startswith("1. Distance")  # list marker kept from native text
    assert blocks[2].raw_text.startswith("Motion is the change") and blocks[2].raw_text.endswith("velocity.")
    assert all(b.language is Language.ENGLISH for b in blocks)
    assert all(b.confidence.score is None for b in blocks)  # native text: no invented confidence
    assert blocks[0].provenance.parameters["layout_label"] == "title"


def test_unassigned_text_is_kept_as_uncertain_paragraph(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    regions = _single_column_regions(ex.pages[0], skip_last=True)  # final paragraph has no region
    result = build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t")
    blocks = _blocks(result)
    fallback = [b for b in blocks if QualityFlag.BLOCK_TYPE_UNCERTAIN in b.quality_flags]
    assert fallback and fallback == blocks[-len(fallback):]  # placed after the list, by geometry
    assert " ".join(b.raw_text for b in fallback).startswith("Acceleration measures")
    assert all(b.block_type is BlockType.PARAGRAPH for b in fallback)
    assert result.reports[0].unassigned_token_count > 0


def test_low_confidence_and_unsupported_regions_are_flagged(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[0]
    regions = [_region(0, RegionKind.TEXT, _around(_lines_matching(page, "Chapter 4")), conf=0.35),
               _region(1, RegionKind.OTHER, _around(_lines_matching(page, "4.1")), conf=0.9)]
    blocks = _blocks(build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t"))
    assert QualityFlag.BLOCK_TYPE_UNCERTAIN in blocks[0].quality_flags
    assert {QualityFlag.UNSUPPORTED_CONTENT, QualityFlag.BLOCK_TYPE_UNCERTAIN} <= set(blocks[1].quality_flags)
    assert blocks[1].raw_text == "4.1 Describing Motion"  # preserved, not discarded


def test_unknown_docling_labels_map_to_other() -> None:
    assert ld.map_label("Section-header") is RegionKind.SECTION_HEADER
    assert ld.map_label("list_item") is RegionKind.LIST_ITEM
    assert ld.map_label("Key-Value Region") is RegionKind.OTHER
    assert ld.map_label("checkbox_selected") is RegionKind.OTHER


# ------------------------------------------------------------- reading order


def test_single_column_order_without_engine_order(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    regions = list(reversed(_single_column_regions(ex.pages[0], with_order=False)))
    result = build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t")
    texts = [b.raw_text for b in _blocks(result)]
    assert texts[0] == "Chapter 4 Motion" and texts[1] == "4.1 Describing Motion"
    assert result.reports[0].order.selected == "geometric_columns" and result.reports[0].order.columns == 1


def _two_column_regions(page: Any, engine_order: list[int] | None = None) -> list[LayoutRegion]:
    """Heading + 3 paragraphs in the left column + 3 in the right column (7 regions)."""
    left = _paragraph_groups(page, lambda b: b[2] < 0.5)  # includes the heading (it sits top-left)
    right = _paragraph_groups(page, lambda b: b[0] > 0.5)
    groups = left + right
    order = engine_order or [None] * len(groups)
    return [_region(i, _kind_for(text), box, engine_order=order[i]) for i, (text, box) in enumerate(groups)]


def test_two_column_reading_order(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[1]
    result = build_layout_document(ex, {1: _layout(1, _two_column_regions(page))}, source_uri="asset://t")
    blocks = _blocks(result, 1)
    assert len(blocks) == 7 and result.reports[1].unassigned_token_count == 0
    sides = ["L" if (b.bbox[0] + b.bbox[2]) / 2 < 0.5 else "R" for b in blocks]
    assert blocks[0].raw_text == "4.2 Speed and Velocity"
    assert sides == ["L", "L", "L", "L", "R", "R", "R"]  # whole left column before the right one
    assert [b.bbox[1] for b in blocks[1:4]] == sorted(b.bbox[1] for b in blocks[1:4])
    assert blocks[4].raw_text.startswith("Acceleration") and blocks[5].raw_text.startswith("Movement")
    report = result.reports[1].order
    assert report.columns == 2 and not report.ambiguous
    assert "geometric_columns" in report.candidates and "native_stream" in report.candidates


def test_engine_order_is_selected_and_disagreement_flagged(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    # Engine claims row-wise reading (left, right, left, right): conflicts with columns.
    regions = _two_column_regions(ex.pages[1], engine_order=[0, 1, 4, 2, 5, 3, 6])
    result = build_layout_document(ex, {1: _layout(1, regions)}, source_uri="asset://t")
    report = result.reports[1].order
    assert report.selected == "layout_engine" and report.ambiguous
    assert report.discordant_pairs["geometric_columns"] > 0
    flagged = [b for b in _blocks(result, 1) if QualityFlag.READING_ORDER_UNCERTAIN in b.quality_flags]
    assert flagged and len(flagged) < 7  # only the disputed blocks, not the heading
    assert QualityFlag.READING_ORDER_UNCERTAIN not in _blocks(result, 1)[0].quality_flags


def test_region_straddling_gutter_is_ambiguous(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    regions = _two_column_regions(ex.pages[1])
    regions.append(_region(9, RegionKind.TEXT, (0.40, 0.70, 0.60, 0.75)))  # narrow box across the gutter
    result = build_layout_document(ex, {1: _layout(1, regions)}, source_uri="asset://t")
    assert result.reports[1].order.ambiguous


# -------------------------------------------------------------------- tables


def _table_regions(page: Any, cells: list[TableCellCandidate], rows: int | None = 4, cols: int | None = 3) -> list[LayoutRegion]:
    table_words = [w.bbox for w in page.words if 0.15 < w.bbox[0] < 0.86 and 0.18 < w.bbox[1] < 0.33]
    caption = _around(_lines_matching(page, "Table 4.1"))
    table_box = _around(table_words, pad=0.01)
    return [_region(0, RegionKind.TABLE, table_box, table=TableCandidate(rows, cols, tuple(cells))),
            _region(1, RegionKind.CAPTION, caption, caption_targets=(0,))]


def _grid_cells(page: Any) -> list[TableCellCandidate]:
    rows = sorted({round(w.bbox[1], 3) for w in page.words if 0.18 < w.bbox[1] < 0.33})
    cols = [(0.16, 0.39), (0.39, 0.69), (0.69, 0.85)]
    cells = []
    for r, top in enumerate(rows):
        for c, (x0, x1) in enumerate(cols):
            cells.append(TableCellCandidate(r, c, 1, 1, r == 0, False, (x0, top - 0.008, x1, top + 0.02)))
    return cells


def test_table_cells_headers_and_caption(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[2]
    result = build_layout_document(ex, {2: _layout(2, _table_regions(page, _grid_cells(page)))}, source_uri="asset://t")
    doc = result.document
    table = next(b for b in doc.blocks if b.block_type is BlockType.TABLE)
    cells = {b.id: b for b in doc.blocks if b.block_type is BlockType.TABLE_CELL}
    assert table.table.row_count == 4 and table.table.column_count == 3 and len(cells) == 12
    by_pos = {(c.table_cell.row_index, c.table_cell.column_index): c for c in cells.values()}
    assert by_pos[(0, 0)].raw_text == "Quantity" and by_pos[(0, 0)].table_cell.is_header
    assert by_pos[(3, 1)].raw_text == "metre per second"
    assert [cells[h].raw_text for h in by_pos[(3, 1)].table_cell.header_cell_ids] == ["SI unit"]
    assert all(c.parent_id == table.id for c in cells.values())
    assert sum(1 for e in doc.edges if e.edge_type is EdgeType.HEADER_FOR) == 9
    caption = next(b for b in doc.blocks if b.block_type is BlockType.CAPTION)
    assert any(e.edge_type is EdgeType.CAPTION_OF and e.source_id == caption.id and e.target_id == table.id
               for e in doc.edges)
    assert QualityFlag.ORPHAN_CAPTION not in caption.quality_flags


def test_inconsistent_table_becomes_uncertain_candidate(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[2]
    cells = _grid_cells(page)
    cells.append(TableCellCandidate(0, 0, 2, 1, False, False, cells[0].bbox))  # overlaps (0,0)
    result = build_layout_document(ex, {2: _layout(2, _table_regions(page, cells))}, source_uri="asset://t")
    table = next(b for b in result.document.blocks if b.block_type is BlockType.TABLE)
    assert table.table.cell_ids == [] and table.table.row_count is None
    assert QualityFlag.TABLE_STRUCTURE_UNCERTAIN in table.quality_flags
    assert "Quantity" in table.raw_text and "m/s" in table.raw_text  # text preserved, no cells invented
    assert table.raw_text.startswith("Quantity SI unit Symbol Distance metre m")  # row by row, not by column
    assert not any(b.block_type is BlockType.TABLE_CELL for b in result.document.blocks)


def test_table_without_structure_and_cell_without_geometry(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[2]
    no_cells = build_layout_document(ex, {2: _layout(2, _table_regions(page, [], None, None))}, source_uri="asset://t")
    t = next(b for b in no_cells.document.blocks if b.block_type is BlockType.TABLE)
    assert t.table.is_uncertain_candidate and QualityFlag.TABLE_STRUCTURE_UNCERTAIN in t.quality_flags

    cells = _grid_cells(page)
    c = cells[4]
    cells[4] = TableCellCandidate(c.row, c.col, 1, 1, False, False, None, engine_text="metre")
    result = build_layout_document(ex, {2: _layout(2, _table_regions(page, cells))}, source_uri="asset://t")
    cell = next(b for b in result.document.blocks if b.table_cell and b.table_cell.row_index == 1
                and b.table_cell.column_index == 1)
    assert QualityFlag.MISSING_GEOMETRY in cell.quality_flags and cell.raw_text == "metre"


# ----------------------------------------------------- figures and equations


def test_figure_caption_link_and_orphan_caption(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[3]
    caption = _around(_lines_matching(page, "Figure 4.2"))
    figure = (0.27, 0.31, 0.74, 0.56)
    linked = build_layout_document(ex, {3: _layout(3, [_region(0, RegionKind.PICTURE, figure),
                                                       _region(1, RegionKind.CAPTION, caption, caption_targets=(0,))])},
                                   source_uri="asset://t")
    fig = next(b for b in linked.document.blocks if b.block_type is BlockType.FIGURE)
    cap = next(b for b in linked.document.blocks if b.block_type is BlockType.CAPTION)
    assert fig.figure.caption_block_id == cap.id
    assert fig.figure.source_caption == "Figure 4.2 Distance-time graph of a moving bicycle"
    assert fig.figure.alt_text is None and fig.figure.extended_description is None  # nothing invented

    orphan = build_layout_document(ex, {3: _layout(3, [_region(0, RegionKind.PICTURE, figure),
                                                       _region(1, RegionKind.CAPTION, caption)])},
                                   source_uri="asset://t")
    cap = next(b for b in orphan.document.blocks if b.block_type is BlockType.CAPTION)
    assert QualityFlag.ORPHAN_CAPTION in cap.quality_flags
    assert not any(e.edge_type is EdgeType.CAPTION_OF for e in orphan.document.edges)


def test_equation_region(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[4]
    eq = _around(_lines_matching(page, "v = u"))
    result = build_layout_document(ex, {4: _layout(4, [_region(0, RegionKind.FORMULA, eq)])}, source_uri="asset://t")
    block = next(b for b in result.document.blocks if b.block_type is BlockType.EQUATION)
    assert block.equation.source_text.startswith("v = u + a t")
    assert block.equation.mathml is None and block.equation.spoken_fallback is None
    assert QualityFlag.MATH_NEEDS_REVIEW in block.quality_flags


# --------------------------------------------------- geometry and overlaps


@pytest.mark.parametrize("box", [None, (0.5, 0.5, 0.4, 0.6), (float("nan"), 0, 1, 1), (2.0, 2.0, 3.0, 3.0)])
def test_invalid_region_geometry_is_reported_and_text_kept(textbook: tuple[Path, Any], box: Any) -> None:
    _, ex = textbook
    regions = [_region(0, RegionKind.SECTION_HEADER, box)]
    result = build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t")
    assert result.reports[0].rejected_regions
    texts = " ".join(b.raw_text for b in _blocks(result))
    assert "Chapter 4 Motion" in texts  # words fall back to uncertain paragraphs


def test_partially_outside_region_is_clipped_and_flagged() -> None:
    box, flags = clean_bbox((-0.1, 0.2, 0.5, 0.3))
    assert box == (0.0, 0.2, 0.5, 0.3) and flags == {"geometry_uncertain"}


def test_overlapping_regions_flagged(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[0]
    a = _around(_lines_matching(page, "Chapter 4"))
    b = _around(_lines_matching(page, "4.1"))
    big = (a[0], a[1], a[2], b[3])
    regions = [_region(0, RegionKind.TITLE, a), _region(1, RegionKind.PICTURE, big)]
    blocks = _blocks(build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t"))
    assert all(QualityFlag.OVERLAPPING_REGIONS in x.quality_flags for x in blocks if x.block_type
               in (BlockType.HEADING, BlockType.FIGURE))


def test_duplicate_same_type_predictions_merged(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    box = _around(_lines_matching(ex.pages[0], "Chapter 4"))
    regions = [_region(0, RegionKind.TITLE, box, 0.9), _region(1, RegionKind.SECTION_HEADER, box, 0.6),
               _region(2, RegionKind.TEXT, box, 0.55)]
    result = build_layout_document(ex, {0: _layout(0, regions)}, source_uri="asset://t")
    heading = _blocks(result)[0]
    assert heading.raw_text == "Chapter 4 Motion" and heading.block_type is BlockType.HEADING
    assert QualityFlag.BLOCK_TYPE_UNCERTAIN in heading.quality_flags  # conflicting TEXT prediction
    assert len(result.reports[0].merged_predictions) == 2


# --------------------------------------------- OCR, Hindi and duplicates


def _scan_pdf(tmp_path: Path) -> Path:
    return write_pdf(tmp_path / "scan.pdf", [
        PageSpec(images=[PdfImage(0, 0, 612, 792)]),
        PageSpec(texts=[Text(72, 700, "Native heading")]),
    ])


def test_mixed_hindi_english_ocr_page(tmp_path: Path) -> None:
    path = _scan_pdf(tmp_path)
    ex = extract_native_pdf(path)
    words = [W("आपतन", 100, 100, 80, 30), W("कोण", 190, 100, 60, 30), W("(angle)", 260, 100, 90, 30, 55),
             W("प्रकाश", 100, 200, 90, 30, 90, line=(2, 1, 1))]
    run = ocr_pdf_pages(path, ex, engine=FakeEngine(words), config=NO_PREP, dpi=72)
    result = build_layout_document(ex, {0: _layout(0, [_region(0, RegionKind.TEXT, (0.1, 0.1, 0.7, 0.2)),
                                                       _region(1, RegionKind.TEXT, (0.1, 0.24, 0.7, 0.31))])},
                                   {0: run.results[0]}, source_uri="asset://s")
    first, second = _blocks(result)[:2]
    assert first.raw_text == "आपतन कोण (angle)" and first.language is Language.MULTIPLE
    assert QualityFlag.MIXED_SCRIPT in first.quality_flags and QualityFlag.LOW_CONFIDENCE in first.quality_flags
    assert second.raw_text == "प्रकाश" and second.language is Language.HINDI
    assert first.confidence.score == pytest.approx((0.95 + 0.95 + 0.55) / 3, abs=1e-4)
    assert first.provenance.parameters["ocr_engine"] == "tesseract 5.4.0-fake"
    assert first.provenance.parameters["text_source"] == "ocr"


def test_duplicate_native_and_ocr_text_used_once(tmp_path: Path) -> None:
    path = _scan_pdf(tmp_path)
    ex = extract_native_pdf(path)
    nb = ex.pages[1].words[0].bbox

    def words(img: Any) -> list[W]:
        w, h = img.size
        return [W("Native", nb[0] * w, nb[1] * h, (nb[2] - nb[0]) * w, (nb[3] - nb[1]) * h)]

    run = ocr_pdf_pages(path, ex, engine=FakeEngine(words), config=NO_PREP, dpi=72, force_pages=[1])
    region = _around([l.bbox for l in ex.pages[1].lines], pad=0.01)
    result = build_layout_document(ex, {1: _layout(1, [_region(0, RegionKind.SECTION_HEADER, region)])},
                                   {1: run.results[0]}, source_uri="asset://s")
    block = _blocks(result, 1)[0]
    assert block.raw_text == "Native heading"  # not "Native Native heading"
    assert QualityFlag.DUPLICATE_CONTENT in block.quality_flags
    assert result.reports[1].duplicate_token_count == 1


# -------------------------------------------- failures and Phase 1-3 compat


def test_failed_layout_keeps_all_text(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    failed = LayoutPage(0, LayoutStatus.FAILED, "docling_pdf", (), "docling", "2.70.0", None, {}, 0.0, ("boom",))
    result = build_layout_document(ex, {0: failed}, source_uri="asset://t")
    blocks = _blocks(result)
    native = " ".join(line.text for line in ex.pages[0].lines)
    assert all(b.block_type is BlockType.PARAGRAPH for b in blocks)
    assert all({QualityFlag.BLOCK_TYPE_UNCERTAIN, QualityFlag.READING_ORDER_UNCERTAIN} <= set(b.quality_flags)
               for b in blocks)
    assert sorted(" ".join(b.raw_text for b in blocks).split()) == sorted(native.split())
    assert blocks[0].provenance.method.value == "derived"
    assert "boom" in result.reports[0].warnings
    page = result.document.pages[0]
    assert page.status.value == "partial"  # text kept, structure missing: not "ok", not "blank"
    assert any(w.code == "layout_failed" and "boom" in w.message for w in page.warnings)


def test_adapter_failure_and_fallback(monkeypatch: pytest.MonkeyPatch, textbook: tuple[Path, Any]) -> None:
    path, ex = textbook
    engine = object.__new__(ld.DoclingLayoutEngine)
    engine.config, engine.versions, engine.model_fingerprint = ld.DoclingConfig(), {"docling": "2.70.0",
                                                                                     "docling-ibm-models": "3.9.1"}, "x"

    def boom(*args: Any) -> Any:
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(engine, "_direct", boom, raising=False)
    page = engine.analyze_page(path, ex.pages[0])
    assert page.status is LayoutStatus.FAILED and "parser crashed" in page.warnings[-1]

    def mismatch(*args: Any) -> Any:
        raise ld._FallBack("page size mismatch")

    monkeypatch.setattr(engine, "_direct", mismatch, raising=False)
    monkeypatch.setattr(engine, "_image", lambda *a: ([], 3), raising=False)
    page = engine.analyze_page(path, ex.pages[0])
    assert page.status is LayoutStatus.OK and page.mode == "docling_image"
    assert any("direct mode unusable" in w for w in page.warnings)
    assert any("3 raw layout predictions" in w for w in page.warnings)


def test_adapter_requires_local_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATHYA_DOCLING_ARTIFACTS", raising=False)
    with pytest.raises(ld.DoclingUnavailableError, match="No Docling model directory"):
        ld.DoclingLayoutEngine(ld.DoclingConfig())
    with pytest.raises(ld.DoclingUnavailableError, match="not found"):
        ld.DoclingLayoutEngine(ld.DoclingConfig(artifacts_path=tmp_path))


def test_mode_selection(textbook: tuple[Path, Any], tmp_path: Path) -> None:
    _, ex = textbook
    engine = object.__new__(ld.DoclingLayoutEngine)
    engine.config = ld.DoclingConfig()
    assert engine.choose_mode(ex.pages[0]) == "docling_pdf"
    rotated = extract_native_pdf(write_pdf(tmp_path / "r.pdf", [PageSpec(texts=[Text(72, 700, "x" * 50)], rotate=90)]))
    scanned = extract_native_pdf(_scan_pdf(tmp_path))
    assert engine.choose_mode(rotated.pages[0]) == "docling_image"
    assert engine.choose_mode(scanned.pages[0]) == "docling_image"


def test_docling_box_and_table_conversion() -> None:
    from docling_core.types.doc import BoundingBox, CoordOrigin

    bottom_left = BoundingBox(l=61.2, t=712.8, r=306.0, b=633.6, coord_origin=CoordOrigin.BOTTOMLEFT)
    assert ld._to_normalized(bottom_left, 612, 792) == pytest.approx((0.1, 0.1, 0.5, 0.2))
    top_left = BoundingBox(l=61.2, t=79.2, r=306.0, b=158.4, coord_origin=CoordOrigin.TOPLEFT)
    assert ld._to_normalized(top_left, 612, 792) == pytest.approx((0.1, 0.1, 0.5, 0.2))

    class Cell:
        def __init__(self, r: int, c: int, header: bool) -> None:
            self.start_row_offset_idx, self.end_row_offset_idx = r, r + 1
            self.start_col_offset_idx, self.end_col_offset_idx = c, c + 2
            self.column_header, self.row_header, self.text = header, False, "t"
            self.bbox = None

    class Data:
        num_rows, num_cols = 2, 2
        table_cells = [Cell(0, 0, True), Cell(1, 0, False)]

    t = ld._table_candidate(Data(), 612, 792)
    assert (t.rows, t.cols) == (2, 2) and t.cells[0].col_span == 2 and t.cells[0].bbox is None


def test_document_validates_against_schema(textbook: tuple[Path, Any]) -> None:
    _, ex = textbook
    page = ex.pages[2]
    layouts = {0: _layout(0, _single_column_regions(ex.pages[0])),
               2: _layout(2, _table_regions(page, _grid_cells(page)))}
    doc = build_layout_document(ex, layouts, source_uri="asset://t").document
    assert doc.schema_version == "1.1.0"
    payload = json.loads(doc.model_dump_json())
    jsonschema.Draft202012Validator(build_json_schema(), format_checker=jsonschema.FormatChecker()).validate(payload)
    assert Document.model_validate(payload) == doc
    assert len({p.page_index for p in doc.pages}) == 5  # page order separate from within-page order
    precedes = [e for e in doc.edges if e.edge_type is EdgeType.PRECEDES]
    page_of = {b.id: b.page_id for b in doc.blocks}
    assert all(page_of[e.source_id] == page_of[e.target_id] for e in precedes)


# ------------------------------------------- word order inside a block (audit C1)


def _paragraph_doc(tmp_path: Path, texts: list[Text]) -> tuple[Any, Any]:
    ex = extract_native_pdf(write_pdf(tmp_path / "p.pdf", [PageSpec(texts=texts)]))
    box = _around([w.bbox for w in ex.pages[0].words], pad=0.01)
    result = build_layout_document(ex, {0: _layout(0, [_region(0, RegionKind.TEXT, box)])}, source_uri="asset://p")
    return ex, _blocks(result)[0]


def test_lines_drawn_in_reverse_visual_order_read_top_to_bottom(tmp_path: Path) -> None:
    # The content stream draws the bottom line first (common in edited/InDesign PDFs).
    texts = [Text(72, 680, "second line of the paragraph"), Text(72, 700, "first line of the paragraph")]
    ex, block = _paragraph_doc(tmp_path, texts)
    assert ex.pages[0].words[0].text == "second"  # stream order really is reversed
    assert block.raw_text == "first line of the paragraph second line of the paragraph"


def test_words_drawn_right_to_left_within_a_line_read_left_to_right(tmp_path: Path) -> None:
    texts = [Text(200, 700, "world"), Text(150, 700, "brave"), Text(72, 700, "Hello")]
    _, block = _paragraph_doc(tmp_path, texts)
    assert block.raw_text == "Hello brave world"


def test_normal_multi_line_paragraph_unchanged(tmp_path: Path) -> None:
    lines = ["Motion is the change in position", "of an object over time and is", "described by speed."]
    _, block = _paragraph_doc(tmp_path, [Text(72, 700 - i * 14.5, t, 11) for i, t in enumerate(lines)])
    assert block.raw_text == " ".join(lines)


def test_superscript_and_mixed_sizes_stay_on_their_line(tmp_path: Path) -> None:
    texts = [Text(72, 700, "area is 4 m", 12), Text(140, 705, "2", 7), Text(150, 700, "here", 12),
             Text(72, 684, "next line", 12)]
    _, block = _paragraph_doc(tmp_path, texts)
    assert block.raw_text == "area is 4 m 2 here next line"


def test_two_text_columns_inside_one_region_read_column_by_column(tmp_path: Path) -> None:
    # A single (over-large) region covering two columns must not interleave them.
    texts = [Text(72, 700, "left one"), Text(72, 686, "left two"),
             Text(330, 700, "right one"), Text(330, 686, "right two")]
    _, block = _paragraph_doc(tmp_path, texts)
    assert block.raw_text == "left one left two right one right two"


def test_layout_config_is_tunable() -> None:
    assert LayoutConfig(min_region_confidence=0.7).min_region_confidence == 0.7
