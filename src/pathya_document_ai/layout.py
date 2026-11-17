"""Layout assembly and reading order (Phase 4), independent of any layout engine.

Inputs per page:
* ``LayoutPage``: regions from a layout adapter (e.g. ``layout_docling``),
  already in normalized displayed-page coordinates (``geometry.py`` convention);
* Phase 2 ``PageExtraction`` (native words) and optional Phase 3 ``OcrPageResult``.

Text always comes from Phase 2/3 words assigned to regions by geometry, so raw
text, languages and OCR provenance are preserved; layout engines contribute
region types, boxes, table structure, caption links and an order candidate.
Nothing is discarded silently: unassigned text becomes uncertain paragraphs,
rejected regions and merged duplicate predictions are reported.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import time
from typing import Any
import unicodedata

from pathya_document_ai.geometry import Box, normalize_display_box

# ------------------------------------------------------------- adapter output


class RegionKind(StrEnum):
    TITLE = "title"
    SECTION_HEADER = "section_header"
    TEXT = "text"
    LIST_ITEM = "list_item"
    TABLE = "table"
    CAPTION = "caption"
    PICTURE = "picture"
    FORMULA = "formula"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    FOOTNOTE = "footnote"
    CODE = "code"
    OTHER = "other"  # any engine label without a supported mapping


UNSUPPORTED_KINDS = frozenset({RegionKind.CODE, RegionKind.OTHER})


@dataclass(frozen=True)
class TableCellCandidate:
    row: int
    col: int
    row_span: int
    col_span: int
    is_column_header: bool
    is_row_header: bool
    bbox: Box | None
    engine_text: str = ""  # only used when the cell has no geometry


@dataclass(frozen=True)
class TableCandidate:
    rows: int | None
    cols: int | None
    cells: tuple[TableCellCandidate, ...]


@dataclass(frozen=True)
class LayoutRegion:
    index: int
    kind: RegionKind
    source_label: str  # engine's own label, kept verbatim
    bbox: Box | None  # normalized displayed-page box, or None if the engine geometry was invalid
    confidence: float | None
    engine_order: int | None = None  # engine reading-order position, if provided
    table: TableCandidate | None = None
    caption_targets: tuple[int, ...] = ()  # regions this caption describes, per the engine
    notes: tuple[str, ...] = ()


class LayoutStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


@dataclass(frozen=True)
class LayoutPage:
    page_index: int
    status: LayoutStatus
    mode: str  # e.g. "docling_pdf", "docling_image", "none"
    regions: tuple[LayoutRegion, ...]
    engine: str
    engine_version: str
    model: str | None
    parameters: dict[str, Any]
    elapsed_s: float
    warnings: tuple[str, ...] = ()


# ------------------------------------------------------------------ config


@dataclass(frozen=True)
class LayoutConfig:
    languages: tuple[str, ...] = ("hin", "eng")
    min_region_confidence: float = 0.5  # below: kept, flagged block_type_uncertain
    duplicate_iou: float = 0.7  # same-type predictions above this are merged
    conflict_iou: float = 0.5  # different-type predictions above this conflict
    overlap_fraction: float = 0.3  # of the smaller region -> overlapping_regions
    full_width: float = 0.6  # regions wider than this span columns
    min_gutter: float = 0.015


# ---------------------------------------------------------------- page result


@dataclass
class _Token:
    key: str
    text: str
    bbox: Box
    order: int
    source: str  # "native" | "ocr"
    language: str
    confidence: float | None
    line: tuple[str, int]


@dataclass
class _Region:
    """Mutable working copy of a region during assembly."""

    region: LayoutRegion | None  # None for fallback (unclassified) text
    kind: RegionKind
    bbox: Box
    confidence: float | None
    flags: set[str] = field(default_factory=set)
    tokens: list[_Token] = field(default_factory=list)
    alternatives: list[tuple[str, float | None]] = field(default_factory=list)
    duplicate_tokens: int = 0
    key: int = 0


@dataclass(frozen=True)
class OrderReport:
    selected: str
    reason: str
    candidates: dict[str, tuple[int, ...]]  # candidate name -> block positions (selected order indices)
    discordant_pairs: dict[str, int]
    ambiguous: bool
    columns: int


@dataclass(frozen=True)
class PageLayoutReport:
    page_index: int
    mode: str
    status: LayoutStatus
    order: OrderReport
    merged_predictions: tuple[str, ...]
    rejected_regions: tuple[str, ...]
    unassigned_token_count: int
    duplicate_token_count: int
    elapsed_s: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class LayoutDocumentResult:
    document: Any  # models.Document
    reports: tuple[PageLayoutReport, ...]


# ------------------------------------------------------------- geometry utils


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def iou(a: Box, b: Box) -> float:
    i = _inter(a, b)
    union = _area(a) + _area(b) - i
    return i / union if union > 0 else 0.0


def overlap_of_smaller(a: Box, b: Box) -> float:
    smaller = min(_area(a), _area(b))
    return _inter(a, b) / smaller if smaller > 0 else 0.0


def _center_in(token: Box, region: Box, pad: float = 0.002) -> bool:
    cx, cy = (token[0] + token[2]) / 2, (token[1] + token[3]) / 2
    return region[0] - pad <= cx <= region[2] + pad and region[1] - pad <= cy <= region[3] + pad


def _union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def clean_bbox(box: Box | None) -> tuple[Box | None, set[str]]:
    """Validate/clip an engine box; returns (box, flags). Invalid boxes return None."""
    if box is None:
        return None, {"missing_geometry"}
    try:
        if any(v != v for v in box):  # NaN
            return None, {"missing_geometry"}
        if box[0] >= box[2] or box[1] >= box[3]:  # reversed or zero-size: invalid, never re-sorted
            return None, {"missing_geometry"}
        bbox, notes = normalize_display_box(box, (0.0, 0.0, 1.0, 1.0))
    except (ValueError, TypeError, ZeroDivisionError):
        return None, {"missing_geometry"}
    if bbox is None:
        return None, {"missing_geometry"}
    return bbox, ({"geometry_uncertain"} if notes else set())


# --------------------------------------------------------------- tokens


def _language(text: str, languages: tuple[str, ...]) -> str:
    from pathya_document_ai.ocr import classify_script, language_for

    return language_for(classify_script(text), languages)


def _collect_tokens(page: Any, ocr: Any, config: LayoutConfig) -> tuple[list[_Token], list[Box], list[str]]:
    """Native + OCR tokens with duplicates removed. Returns (tokens, dropped_boxes, warnings)."""
    from pathya_document_ai.quality import OcrDecision

    warnings: list[str] = []
    native: list[_Token] = []
    line_of_word = {w: line.index for line in page.lines for w in line.word_indices}
    for word in page.words:
        if word.bbox is None:
            continue  # outside the crop; already reported by Phase 2
        native.append(_Token(f"n{word.index}", word.text, word.bbox, word.index, "native",
                             _language(word.text, config.languages), None, ("n", line_of_word.get(word.index, -1))))
    ocr_tokens: list[_Token] = []
    if ocr is not None:
        line_of = {i: line.index for line in ocr.lines for i in line.word_indices}
        missing = 0
        for word in ocr.words:
            if word.bbox is None:
                missing += 1
                continue
            ocr_tokens.append(_Token(f"o{word.index}", word.raw_text, word.bbox, word.index, "ocr",
                                     word.language, word.confidence, ("o", line_of.get(word.index, -1))))
        if missing:
            warnings.append(f"{missing} OCR words without geometry were not placed in layout")
    if not native or not ocr_tokens:
        return native + ocr_tokens, [], warnings

    # Shared native/OCR policy (same as ocr.merge_ocr_into_document, docs/ocr.md):
    # a native line is unreliable when Phase 2 said ocr_required for the page or the
    # line contains undecodable glyphs. Unreliable native words covered by an OCR
    # line are dropped; OCR words covered by a reliable native line are dropped.
    from pathya_document_ai.quality import is_unmapped_char

    page_unreliable = page.ocr.decision is OcrDecision.OCR_REQUIRED
    unreliable_lines = {line.index for line in page.lines
                        if page_unreliable or any(is_unmapped_char(ch) for ch in line.text)}
    reliable_native_boxes = [line.bbox for line in page.lines
                             if line.bbox is not None and line.index not in unreliable_lines]
    ocr_line_boxes = [line.bbox for line in ocr.lines if line.bbox is not None]
    kept: list[_Token] = []
    dropped: list[Box] = []
    dropped_native = dropped_ocr = 0
    for token in native:
        if token.line[1] in unreliable_lines and any(_center_in(token.bbox, b) for b in ocr_line_boxes):
            dropped_native += 1
            dropped.append(token.bbox)
            continue
        kept.append(token)
    for token in ocr_tokens:
        if any(_center_in(token.bbox, b) for b in reliable_native_boxes):
            dropped_ocr += 1
            dropped.append(token.bbox)
            continue
        kept.append(token)
    if dropped_native:
        warnings.append(f"{dropped_native} unreliable native words were replaced by OCR text")
    if dropped_ocr:
        warnings.append(f"{dropped_ocr} OCR words duplicated reliable native text and were not used")
    return kept, dropped, warnings


# ------------------------------------------------------------- regions


def _postprocess(regions: tuple[LayoutRegion, ...], config: LayoutConfig) -> tuple[list[_Region], list[str], list[str]]:
    working: list[_Region] = []
    rejected: list[str] = []
    for region in regions:
        bbox, flags = clean_bbox(region.bbox)
        if bbox is None:
            rejected.append(f"region {region.index} ({region.source_label}) has invalid geometry {region.bbox}")
            continue
        working.append(_Region(region, region.kind, bbox, region.confidence, flags))
    working.sort(key=lambda r: -(r.confidence if r.confidence is not None else 1.0))
    kept: list[_Region] = []
    merged: list[str] = []
    for cand in working:
        absorbed = False
        for k in kept:
            if _block_type(cand.kind) == _block_type(k.kind) and (
                    iou(cand.bbox, k.bbox) > config.duplicate_iou or overlap_of_smaller(cand.bbox, k.bbox) > 0.9
                    and _area(cand.bbox) <= _area(k.bbox)):
                merged.append(f"{cand.region.source_label}@{cand.confidence} merged into "  # type: ignore[union-attr]
                              f"{k.region.source_label}@{k.confidence}")  # type: ignore[union-attr]
                absorbed = True
                break
            if _block_type(cand.kind) != _block_type(k.kind) and iou(cand.bbox, k.bbox) > config.conflict_iou:
                k.alternatives.append((cand.region.source_label, cand.confidence))  # type: ignore[union-attr]
                if (cand.confidence or 0) >= 0.5 * (k.confidence or 1.0):
                    k.flags.add("block_type_uncertain")
                merged.append(f"{cand.region.source_label}@{cand.confidence} conflicts with "  # type: ignore[union-attr]
                              f"{k.region.source_label}@{k.confidence}; kept the latter")  # type: ignore[union-attr]
                absorbed = True
                break
        if not absorbed:
            kept.append(cand)
    for r in kept:
        if r.confidence is not None and r.confidence < config.min_region_confidence:
            r.flags.add("block_type_uncertain")
        if r.kind in UNSUPPORTED_KINDS:
            r.flags.update({"unsupported_content", "block_type_uncertain"})
    return kept, merged, rejected


_TEXTUAL = frozenset({RegionKind.TEXT, RegionKind.TITLE, RegionKind.SECTION_HEADER, RegionKind.LIST_ITEM,
                      RegionKind.CAPTION, RegionKind.FOOTNOTE, RegionKind.PAGE_HEADER, RegionKind.PAGE_FOOTER})


def _drop_empty_containers(regions: list[_Region], merged: list[str]) -> list[_Region]:
    """Remove text-like regions that received no words but overlap regions that did.

    Raw layout predictions often include both a block box and its line boxes;
    after word assignment the empty one is a duplicate. Recorded in ``merged``.
    """
    holders = [r for r in regions if r.tokens]
    out = []
    for r in regions:
        if not r.tokens and r.kind in _TEXTUAL and any(
                overlap_of_smaller(r.bbox, h.bbox) > 0.5 for h in holders):
            label = r.region.source_label if r.region else "region"
            merged.append(f"empty {label}@{r.confidence} overlapped regions holding text; removed")
            continue
        out.append(r)
    return out


def _flag_overlaps(regions: list[_Region], config: LayoutConfig) -> None:
    for i, a in enumerate(regions):
        for b in regions[i + 1:]:
            if overlap_of_smaller(a.bbox, b.bbox) > config.overlap_fraction:
                a.flags.add("overlapping_regions")
                b.flags.add("overlapping_regions")


def _assign_tokens(regions: list[_Region], tokens: list[_Token]) -> list[_Token]:
    unassigned = []
    for token in tokens:
        holders = [r for r in regions if _center_in(token.bbox, r.bbox)]
        if not holders:
            unassigned.append(token)
            continue
        min(holders, key=lambda r: _area(r.bbox)).tokens.append(token)
    return unassigned


def _fallback_regions(tokens: list[_Token]) -> list[_Region]:
    groups: dict[tuple[str, int], list[_Token]] = defaultdict(list)
    for token in tokens:
        groups[token.line].append(token)
    out = []
    for group in groups.values():
        out.append(_Region(None, RegionKind.TEXT, _union([t.bbox for t in group]), None,
                           {"block_type_uncertain"}, list(group)))
    return out


def _visual_lines(tokens: list[_Token]) -> list[list[_Token]]:
    """Cluster tokens into visual lines (top to bottom), each sorted left to right.

    A token joins the line whose vertical span overlaps it by at least half of
    the smaller height, so superscripts and mixed font sizes stay on their line.
    Content-stream order is deliberately NOT used: PDFs often draw text out of
    visual order, and this text is what speech reads aloud.
    """
    lines: list[list[_Token]] = []
    spans: list[list[float]] = []  # [top, bottom] per line
    for token in sorted(tokens, key=lambda t: ((t.bbox[1] + t.bbox[3]) / 2, t.bbox[0])):
        top, bottom = token.bbox[1], token.bbox[3]
        best, best_overlap = None, 0.0
        for i, (lt, lb) in enumerate(spans):
            overlap = min(bottom, lb) - max(top, lt)
            if overlap >= 0.5 * min(bottom - top, lb - lt) and overlap > best_overlap:
                best, best_overlap = i, overlap
        if best is None:
            lines.append([token])
            spans.append([top, bottom])
        else:
            lines[best].append(token)
            spans[best] = [min(spans[best][0], top), max(spans[best][1], bottom)]
    order = sorted(range(len(lines)), key=lambda i: spans[i][0])
    return [sorted(lines[i], key=lambda t: t.bbox[0]) for i in order]


def _ordered_tokens(tokens: list[_Token], *, allow_columns: bool = True) -> list[_Token]:
    """Visual reading order of the words inside one region.

    If the region itself contains side-by-side text columns (an over-large
    region), each column is read completely before the next. Tables pass
    ``allow_columns=False`` so a structureless table still reads row by row.
    """
    if allow_columns and len(tokens) > 1:
        gutters = _find_gutters([t.bbox for t in tokens], min_gutter=0.03)
        if gutters:
            def column(t: _Token) -> int:
                return sum(1 for g in gutters if (t.bbox[0] + t.bbox[2]) / 2 > g)

            by_column: dict[int, list[_Token]] = defaultdict(list)
            for t in tokens:
                by_column[column(t)].append(t)
            return [t for c in sorted(by_column) for line in _visual_lines(by_column[c]) for t in line]
    return [t for line in _visual_lines(tokens) for t in line]


def _text(tokens: list[_Token], *, allow_columns: bool = True) -> str:
    return " ".join(t.text for t in _ordered_tokens(tokens, allow_columns=allow_columns))


def _block_language(tokens: list[_Token]) -> str:
    tags = {t.language for t in tokens} - {"und"}
    if not tags:
        return "und"
    return tags.pop() if len(tags) == 1 else "mul"


# -------------------------------------------------------------- reading order


def _column_order(regions: list[_Region], config: LayoutConfig) -> tuple[list[int], int, bool]:
    """Column-aware order: full-width regions split the page into bands; within a
    band, columns are read left to right and each column top to bottom.

    Returns (positions, column_count, ambiguous).
    """
    idx = list(range(len(regions)))
    narrow = [i for i in idx if regions[i].bbox[2] - regions[i].bbox[0] <= config.full_width]
    gutters = _find_gutters([regions[i].bbox for i in narrow], config.min_gutter)
    ambiguous = False

    def spans(i: int) -> bool:
        x0, _, x1, _ = regions[i].bbox
        return (x1 - x0) > config.full_width or any(x0 < g < x1 for g in gutters)

    separators = sorted((i for i in idx if spans(i)), key=lambda i: regions[i].bbox[1])
    for i in idx:
        x0, _, x1, _ = regions[i].bbox
        if gutters and not (x1 - x0) > config.full_width and any(x0 < g < x1 for g in gutters):
            ambiguous = True  # a narrow block straddles a detected gutter
    rest = [i for i in idx if i not in separators]
    order: list[int] = []
    cursor = -1.0
    for sep in separators + [None]:
        limit = regions[sep].bbox[1] if sep is not None else 2.0
        band = [i for i in rest if cursor <= (regions[i].bbox[1] + regions[i].bbox[3]) / 2 < limit]
        rest = [i for i in rest if i not in band]

        def column(i: int) -> int:
            cx = (regions[i].bbox[0] + regions[i].bbox[2]) / 2
            return sum(1 for g in gutters if cx > g)

        order += sorted(band, key=lambda i: (column(i), regions[i].bbox[1], regions[i].bbox[0]))
        if sep is not None:
            order.append(sep)
            cursor = (regions[sep].bbox[1] + regions[sep].bbox[3]) / 2
    order += sorted(rest, key=lambda i: (regions[i].bbox[1], regions[i].bbox[0]))
    return order, len(gutters) + 1, ambiguous


def _find_gutters(boxes: list[Box], min_gutter: float, bins: int = 400) -> list[float]:
    """Vertical gutters: x-ranges whose height-weighted coverage is near zero.

    Weighting by box height means one short box crossing a gutter (a stray
    label or a mis-sized prediction) cannot hide a tall column gap.
    """
    if len(boxes) < 2:
        return []
    weight = [0.0] * bins
    for x0, y0, x1, y1 in boxes:
        for b in range(max(0, int(x0 * bins)), min(bins, int(x1 * bins) + 1)):
            weight[b] += y1 - y0
    tallest = max(weight)
    covered = [w > 0.25 * tallest for w in weight]
    lo = min(b[0] for b in boxes)
    hi = max(b[2] for b in boxes)
    gutters = []
    start = None
    for b in range(int(lo * bins), int(hi * bins) + 1):
        if b < bins and not covered[b]:
            start = b if start is None else start
        elif start is not None:
            if (b - start) / bins >= min_gutter:
                g = (start + b) / 2 / bins
                left = [x for x in boxes if x[2] <= g]
                right = [x for x in boxes if x[0] >= g]
                if any(_v_overlap(l, r) for l in left for r in right):  # truly side by side
                    gutters.append(g)
            start = None
    return gutters


def _v_overlap(a: Box, b: Box) -> bool:
    return min(a[3], b[3]) - max(a[1], b[1]) > 0


def _complete(partial: list[int], reference: list[int]) -> list[int]:
    """Insert positions missing from ``partial`` after their predecessor in ``reference``."""
    out = list(partial)
    for pos, item in enumerate(reference):
        if item in out:
            continue
        prev = next((reference[j] for j in range(pos - 1, -1, -1) if reference[j] in out), None)
        out.insert(out.index(prev) + 1 if prev is not None else 0, item)
    return out


def _discordant(a: list[int], b: list[int]) -> set[tuple[int, int]]:
    common = [x for x in a if x in set(b)]
    rank = {x: i for i, x in enumerate(b)}
    pairs = set()
    for i, x in enumerate(common):
        for y in common[i + 1:]:
            if rank[x] > rank[y]:
                pairs.add((x, y))
    return pairs


def _reading_order(regions: list[_Region], config: LayoutConfig) -> tuple[list[int], OrderReport]:
    geometric, columns, straddle = _column_order(regions, config)
    candidates: dict[str, list[int]] = {"geometric_columns": geometric}
    engine = [i for i in sorted(range(len(regions)), key=lambda i: (
        regions[i].region.engine_order if regions[i].region and regions[i].region.engine_order is not None else 1e9))
        if regions[i].region is not None and regions[i].region.engine_order is not None]
    if engine:
        candidates["layout_engine"] = engine
    native = [i for i in range(len(regions)) if any(t.source == "native" for t in regions[i].tokens)]
    if native:
        candidates["native_stream"] = sorted(native, key=lambda i: min(t.order for t in regions[i].tokens
                                                                      if t.source == "native"))
    ocr = [i for i in range(len(regions)) if any(t.source == "ocr" for t in regions[i].tokens)]
    if ocr:
        candidates["ocr"] = sorted(ocr, key=lambda i: min(t.order for t in regions[i].tokens if t.source == "ocr"))

    if engine and len(engine) >= max(1, len(regions) // 2):
        selected_name = "layout_engine"
        selected = _complete(engine, geometric)
        reason = "layout engine reading order (learned model), missing regions inserted by column geometry"
    else:
        selected_name = "geometric_columns"
        selected = geometric
        reason = f"column-aware geometric order ({columns} column(s)); no complete engine order"

    discordant: dict[str, int] = {}
    involved: set[int] = set()
    for name, cand in candidates.items():
        if name == selected_name:
            continue
        pairs = _discordant(cand, selected)
        discordant[name] = len(pairs)
        if name in ("layout_engine", "geometric_columns"):
            involved.update(x for pair in pairs for x in pair)
    ambiguous = bool(involved) or straddle
    for i in involved:
        regions[i].flags.add("reading_order_uncertain")
    if straddle:
        for r in regions:
            r.flags.add("reading_order_uncertain")
    rank = {pos: n for n, pos in enumerate(selected)}
    report = OrderReport(
        selected=selected_name, reason=reason,
        candidates={name: tuple(rank[i] for i in cand) for name, cand in candidates.items()},
        discordant_pairs=discordant, ambiguous=ambiguous, columns=columns)
    return selected, report


# --------------------------------------------------------------- build blocks


_BLOCK_FOR_KIND = {
    RegionKind.TITLE: "heading", RegionKind.SECTION_HEADER: "heading", RegionKind.TEXT: "paragraph",
    RegionKind.LIST_ITEM: "list_item", RegionKind.TABLE: "table", RegionKind.CAPTION: "caption",
    RegionKind.PICTURE: "figure", RegionKind.FORMULA: "equation", RegionKind.PAGE_HEADER: "paragraph",
    RegionKind.PAGE_FOOTER: "paragraph", RegionKind.FOOTNOTE: "paragraph", RegionKind.CODE: "paragraph",
    RegionKind.OTHER: "paragraph",
}


def _block_type(kind: RegionKind) -> str:
    return _BLOCK_FOR_KIND[kind]


def build_layout_document(
    extraction: Any,
    layouts: dict[int, LayoutPage],
    ocr_results: dict[int, Any] | None = None,
    *,
    source_uri: str,
    title: str | None = None,
    config: LayoutConfig | None = None,
) -> LayoutDocumentResult:
    """Combine Phase 2 pages, Phase 3 OCR results and layout pages into a contract Document."""
    from pathya_document_ai import models as m
    from pathya_document_ai.pdf import to_contract_document

    config = config or LayoutConfig()
    ocr_results = ocr_results or {}
    base = to_contract_document(extraction, source_uri=source_uri, title=title)
    page_ids = {p.page_index: p.id for p in base.pages}
    blocks: list[Any] = []
    edges: list[Any] = []
    reports: list[PageLayoutReport] = []
    for page in extraction.pages:
        started = time.monotonic()
        layout = layouts.get(page.page_index) or LayoutPage(
            page.page_index, LayoutStatus.FAILED, "none", (), "none", "0", None, {}, 0.0,
            ("no layout result for this page",))
        page_blocks, page_edges, report = _build_page(
            page, layout, ocr_results.get(page.page_index), page_ids[page.page_index], extraction, config, m)
        blocks += page_blocks
        edges += page_edges
        reports.append(PageLayoutReport(**{**report.__dict__, "elapsed_s": round(
            report.elapsed_s + time.monotonic() - started, 3)}))
    languages = sorted({b.language for b in blocks} - {m.Language.UNDETERMINED}) or [m.Language.UNDETERMINED]
    data = base.model_dump()
    data.update(blocks=[b.model_dump() for b in blocks], edges=[e.model_dump() for e in edges],
                languages=languages)
    return LayoutDocumentResult(m.Document.model_validate(data), tuple(reports))


def _build_page(page: Any, layout: LayoutPage, ocr: Any, page_id: Any, extraction: Any,
                config: LayoutConfig, m: Any) -> tuple[list[Any], list[Any], PageLayoutReport]:
    tokens, dropped_boxes, warnings = _collect_tokens(page, ocr, config)
    duplicates = len(dropped_boxes)
    warnings = list(layout.warnings) + warnings
    regions, merged, rejected = _postprocess(layout.regions, config)
    unassigned = _assign_tokens(regions, tokens)
    regions = _drop_empty_containers(regions, merged)
    _flag_overlaps(regions, config)
    for r in regions:  # a region that lost a duplicate word carries the evidence
        if any(_center_in(b, r.bbox) for b in dropped_boxes):
            r.flags.add("duplicate_content")
    fallback = _fallback_regions(unassigned)
    if unassigned:
        warnings.append(f"{len(unassigned)} words were outside every layout region; kept as uncertain paragraphs")
    regions += fallback
    for n, r in enumerate(regions):
        r.key = n
    if layout.status is LayoutStatus.FAILED:
        for r in regions:
            r.flags.add("reading_order_uncertain")

    order, order_report = _reading_order(regions, config)
    now = datetime.now(timezone.utc)
    provenance = _provenance(layout, extraction, ocr, m, now)

    blocks: list[Any] = []
    edges: list[Any] = []
    id_of: dict[int, Any] = {}
    for position, ridx in enumerate(order):
        region = regions[ridx]
        block, children, child_edges = _region_to_blocks(region, position, page_id, provenance, layout, m)
        id_of[ridx] = block.id
        blocks.append(block)
        blocks += children
        edges += child_edges

    # Caption links, only where the engine supplied them.
    linked_captions: set[int] = set()
    by_engine_index = {r.region.index: n for n, r in enumerate(regions) if r.region is not None}
    for n, r in enumerate(regions):
        if r.kind is not RegionKind.CAPTION or r.region is None:
            continue
        for target_index in r.region.caption_targets:
            t = by_engine_index.get(target_index)
            if t is None or regions[t].kind not in (RegionKind.PICTURE, RegionKind.TABLE, RegionKind.FORMULA):
                continue
            edges.append(m.Edge(edge_type=m.EdgeType.CAPTION_OF, source_id=id_of[n], target_id=id_of[t],
                                provenance=provenance))
            linked_captions.add(n)
            if regions[t].kind is RegionKind.PICTURE:
                _set_figure_caption(blocks, id_of[t], id_of[n], _text(r.tokens) or None)
    for n, r in enumerate(regions):
        if r.kind is RegionKind.CAPTION and n not in linked_captions:
            _add_flag(blocks, id_of[n], m.QualityFlag.ORPHAN_CAPTION)

    top = [b for b in blocks if b.parent_id is None]
    for a, b in zip(top, top[1:]):
        edges.append(m.Edge(edge_type=m.EdgeType.PRECEDES, source_id=a.id, target_id=b.id, provenance=provenance))

    report = PageLayoutReport(
        page_index=page.page_index, mode=layout.mode, status=layout.status, order=order_report,
        merged_predictions=tuple(merged), rejected_regions=tuple(rejected),
        unassigned_token_count=len(unassigned), duplicate_token_count=duplicates,
        elapsed_s=layout.elapsed_s, warnings=tuple(warnings + rejected))
    return blocks, edges, report



def _provenance(layout: LayoutPage, extraction: Any, ocr: Any, m: Any, now: datetime) -> Any:
    params: dict[str, Any] = {"layout_mode": layout.mode, "text_engine": f"{extraction.engine} {extraction.engine_version}"}
    params.update({k: v for k, v in layout.parameters.items() if isinstance(v, (str, int, float, bool)) or v is None})
    if ocr is not None:
        params.update(ocr_engine=f"tesseract {ocr.engine_version}", ocr_lang="+".join(ocr.languages),
                      ocr_language_data=ocr.language_data)
    if layout.status is LayoutStatus.FAILED or layout.engine == "none":
        return m.Provenance(method=m.ExtractionMethod.DERIVED, parameters=params, created_at=now)
    return m.Provenance(method=m.ExtractionMethod.LAYOUT_MODEL, engine=layout.engine,
                        engine_version=layout.engine_version, model=layout.model, parameters=params,
                        created_at=now)


def _confidence(tokens: list[_Token], m: Any) -> Any:
    scores = [t.confidence for t in tokens if t.source == "ocr" and t.confidence is not None]
    if scores:
        return m.Confidence(score=round(sum(scores) / len(scores), 4), origin=m.ConfidenceOrigin.ENGINE_REPORTED,
                            reason=f"Mean Tesseract word confidence / 100 over {len(scores)} OCR words.")
    if tokens:
        return m.Confidence.unavailable("Native PDF text has no engine confidence; layout score is in provenance.")
    return m.Confidence.unavailable("Region contains no text; layout score is in provenance.")


def _flags(region: _Region, tokens: list[_Token], text: str | None, m: Any, extra: set[str] = frozenset()) -> list[Any]:  # type: ignore[assignment]
    flags = set(region.flags) | set(extra)
    languages = {t.language for t in tokens}
    if {"hi", "en"} <= languages or "mul" in languages:
        flags.add("mixed_script")
    if text and _block_language(tokens) == "und" and any(unicodedata.category(c).startswith("L") for c in text):
        flags.add("language_uncertain")
    if any(t.source == "ocr" and t.confidence is not None and t.confidence < 0.6 for t in tokens):
        flags.update({"low_confidence", "possible_ocr_error"})
    return [m.QualityFlag(f) for f in sorted(flags)]


def _region_to_blocks(region: _Region, position: int, page_id: Any, provenance: Any, layout: LayoutPage,
                      m: Any) -> tuple[Any, list[Any], list[Any]]:
    block_type = m.BlockType(_block_type(region.kind))
    tokens = region.tokens
    text = _text(tokens, allow_columns=region.kind is not RegionKind.TABLE) if tokens else None
    language = m.Language(_block_language(tokens))
    prov = provenance.model_copy(update={"parameters": {
        **provenance.parameters,
        "layout_label": region.region.source_label if region.region else "unclassified_text",
        "layout_confidence": None if region.confidence is None else round(region.confidence, 4),
        "layout_alternatives": ";".join(f"{lbl}@{c}" for lbl, c in region.alternatives) or None,
        "text_source": "+".join(sorted({t.source for t in tokens})) or "none",
    }})
    common = dict(page_id=page_id, reading_order=position, bbox=region.bbox, language=language,
                  confidence=_confidence(tokens, m), provenance=prov)
    children: list[Any] = []
    edges: list[Any] = []

    if block_type is m.BlockType.TABLE:
        table_block, children, edges = _table_blocks(region, common, text, prov, m)
        return table_block, children, edges
    if block_type is m.BlockType.EQUATION:
        block = m.Block(block_type=block_type, raw_text=text, current_text=text,
                        quality_flags=_flags(region, tokens, None, m, {"math_needs_review"}),
                        equation=m.EquationMeta(source_text=text), **common)
        return block, [], []
    if block_type is m.BlockType.FIGURE:
        block = m.Block(block_type=block_type, raw_text=text, current_text=text,
                        quality_flags=_flags(region, tokens, None, m), figure=m.FigureMeta(), **common)
        return block, [], []
    raw = text if text is not None else ""
    extra = {"empty_text"} if not raw else set()
    block = m.Block(block_type=block_type, raw_text=raw, current_text=raw,
                    quality_flags=_flags(region, tokens, raw, m, extra), **common)
    return block, [], []


def _table_blocks(region: _Region, common: dict[str, Any], text: str | None, prov: Any,
                  m: Any) -> tuple[Any, list[Any], list[Any]]:
    candidate = region.region.table if region.region else None
    problems = _table_problems(candidate)
    if candidate is None or not candidate.cells or problems:
        flags = _flags(region, region.tokens, None, m, {"table_structure_uncertain"})
        block = m.Block(block_type=m.BlockType.TABLE, raw_text=text, current_text=text, quality_flags=flags,
                        table=m.TableMeta(), **common)
        return block, [], []

    table_id = m.new_id()
    cell_tokens: dict[int, list[_Token]] = defaultdict(list)
    stray: list[_Token] = []
    for token in region.tokens:
        holders = [i for i, c in enumerate(candidate.cells) if c.bbox is not None and _center_in(token.bbox, c.bbox)]
        if holders:
            cell_tokens[min(holders, key=lambda i: _area(candidate.cells[i].bbox))].append(token)  # type: ignore[arg-type]
        else:
            stray.append(token)
    cell_ids = [m.new_id() for _ in candidate.cells]
    header_cols: dict[int, list[int]] = defaultdict(list)
    header_rows: dict[int, list[int]] = defaultdict(list)
    for i, c in enumerate(candidate.cells):
        if c.is_column_header:
            for col in range(c.col, c.col + c.col_span):
                header_cols[col].append(i)
        if c.is_row_header:
            for row in range(c.row, c.row + c.row_span):
                header_rows[row].append(i)
    children, edges = [], []
    for i, c in enumerate(candidate.cells):
        toks = cell_tokens.get(i, [])
        cell_flags: set[str] = set()
        bbox, geo = clean_bbox(c.bbox)
        if bbox is None:
            bbox = region.bbox
            cell_flags.add("missing_geometry")
            cell_text = c.engine_text
        else:
            cell_flags |= geo
            cell_text = _text(toks, allow_columns=False) if toks else ""
        if not cell_text:
            cell_flags.add("empty_text")
        headers: list[int] = []
        if not c.is_column_header:
            headers += [h for col in range(c.col, c.col + c.col_span) for h in header_cols.get(col, [])]
        if not c.is_row_header:
            headers += [h for row in range(c.row, c.row + c.row_span) for h in header_rows.get(row, [])]
        headers = list(dict.fromkeys(h for h in headers if h != i))
        dummy = _Region(None, RegionKind.TEXT, bbox, None, set(), toks)
        children.append(m.Block(
            id=cell_ids[i], page_id=common["page_id"], parent_id=table_id, block_type=m.BlockType.TABLE_CELL,
            reading_order=i, bbox=bbox, raw_text=cell_text, current_text=cell_text,
            language=m.Language(_block_language(toks)), confidence=_confidence(toks, m),
            quality_flags=_flags(dummy, toks, cell_text, m, cell_flags), provenance=prov,
            table_cell=m.TableCellMeta(table_id=table_id, row_index=c.row, column_index=c.col, row_span=c.row_span,
                                       column_span=c.col_span, is_header=c.is_column_header or c.is_row_header,
                                       header_cell_ids=[cell_ids[h] for h in headers])))
        edges.append(m.Edge(edge_type=m.EdgeType.CONTAINS, source_id=table_id, target_id=cell_ids[i], provenance=prov))
        for h in headers:
            edges.append(m.Edge(edge_type=m.EdgeType.HEADER_FOR, source_id=cell_ids[h], target_id=cell_ids[i],
                                provenance=prov))
    extra = {"table_structure_uncertain"} if stray else set()
    stray_text = _text(stray, allow_columns=False) if stray else None
    table = m.Block(id=table_id, block_type=m.BlockType.TABLE, raw_text=stray_text, current_text=stray_text,
                    quality_flags=_flags(region, stray, None, m, extra),
                    table=m.TableMeta(row_count=candidate.rows, column_count=candidate.cols, cell_ids=cell_ids),
                    **common)
    return table, children, edges


def _table_problems(t: TableCandidate | None) -> list[str]:
    if t is None or not t.cells:
        return ["no cells"]
    if not t.rows or not t.cols:
        return ["missing dimensions"]
    occupied: set[tuple[int, int]] = set()
    problems = []
    for c in t.cells:
        if c.row < 0 or c.col < 0 or c.row_span < 1 or c.col_span < 1 \
                or c.row + c.row_span > t.rows or c.col + c.col_span > t.cols:
            problems.append(f"cell ({c.row},{c.col}) outside grid")
            continue
        for r in range(c.row, c.row + c.row_span):
            for col in range(c.col, c.col + c.col_span):
                if (r, col) in occupied:
                    problems.append(f"cell overlap at ({r},{col})")
                occupied.add((r, col))
    return problems


def _set_figure_caption(blocks: list[Any], figure_id: Any, caption_id: Any, caption_text: str | None) -> None:
    for i, b in enumerate(blocks):
        if b.id == figure_id and b.figure is not None:
            blocks[i] = b.model_copy(update={"figure": b.figure.model_copy(update={
                "caption_block_id": caption_id, "source_caption": caption_text})})


def _add_flag(blocks: list[Any], block_id: Any, flag: Any) -> None:
    for i, b in enumerate(blocks):
        if b.id == block_id and flag not in b.quality_flags:
            blocks[i] = b.model_copy(update={"quality_flags": [*b.quality_flags, flag]})
