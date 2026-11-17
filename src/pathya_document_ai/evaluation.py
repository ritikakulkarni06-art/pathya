"""Extraction evaluation metrics (no external dependencies).

Compares a contract ``Document`` against hand-made ground truth per page.
Metrics are only as meaningful as the ground truth: results on synthetic
fixtures verify the harness, they do NOT measure textbook accuracy.

Ground-truth page format (JSON), all boxes normalized top-left like the contract::

    {"page_index": 0,
     "category": ["english", "multi_column"],
     "reading_order": ["first segment text", "second segment text", ...],
     "blocks": [{"type": "heading", "bbox": [x0, y0, x1, y1], "text": "..."}, ...],
     "tables": [{"bbox": [...], "rows": [["h1", "h2"], ["a", "b"]]}]}
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import unicodedata


# ------------------------------------------------------------------ text


def _norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def edit_distance(a: list[Any] | str, b: list[Any] | str) -> int:
    """Levenshtein distance over characters (str) or tokens (list)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        current = [i]
        for j, y in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float | None:
    """Character error rate on NFC, whitespace-normalized text; None for empty reference."""
    ref, hyp = _norm(reference), _norm(hypothesis)
    return edit_distance(ref, hyp) / len(ref) if ref else None


def wer(reference: str, hypothesis: str) -> float | None:
    ref, hyp = _norm(reference).split(), _norm(hypothesis).split()
    return edit_distance(ref, hyp) / len(ref) if ref else None


# ----------------------------------------------------------- reading order


def _best_match(segment: str, texts: list[str], used: set[int] = frozenset()) -> int | None:  # type: ignore[assignment]
    """Index of the unused predicted block that best contains ``segment`` (CER < 0.5), else None."""
    best, best_score = None, 0.5
    for i, text in enumerate(texts):
        if not text or i in used:
            continue
        score = edit_distance(_norm(segment), _norm(text)[: len(_norm(segment)) + 10]) / max(len(_norm(segment)), 1)
        if _norm(segment) in _norm(text):
            score = 0.0
        if score < best_score:
            best, best_score = i, score
    return best


def reading_order_accuracy(gold_segments: list[str], predicted_texts: list[str]) -> dict[str, Any]:
    """Fraction of gold segment pairs whose predicted order agrees (pairwise / Kendall-style).

    Segments that cannot be matched to any predicted block count as missing and
    are reported separately; they do not count as correctly ordered.
    """
    # One-to-one matching: repeated or near-identical paragraphs must map to distinct blocks.
    used: set[int] = set()
    positions: list[int | None] = []
    for segment in gold_segments:
        match = _best_match(segment, predicted_texts, used)
        if match is not None:
            used.add(match)
        positions.append(match)
    matched = [(i, p) for i, p in enumerate(positions) if p is not None]
    pairs = agree = 0
    for a in range(len(matched)):
        for b in range(a + 1, len(matched)):
            pairs += 1
            agree += matched[a][1] <= matched[b][1]
    return {"pairs": pairs, "pairwise_accuracy": agree / pairs if pairs else None,
            "unmatched_segments": len(gold_segments) - len(matched)}


# ----------------------------------------------------------------- layout


def _iou(a: list[float] | tuple[float, ...], b: list[float] | tuple[float, ...]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def detection_scores(gold: list[dict[str, Any]], predicted: list[dict[str, Any]], *,
                     iou_threshold: float = 0.5, match_type: bool = True) -> dict[str, Any]:
    """Greedy one-to-one matching at IoU >= threshold (and same type if ``match_type``)."""
    used: set[int] = set()
    true_positive = 0
    for g in gold:
        candidates = [(i, _iou(g["bbox"], p["bbox"])) for i, p in enumerate(predicted)
                      if i not in used and (not match_type or p["type"] == g["type"])]
        candidates = [c for c in candidates if c[1] >= iou_threshold]
        if candidates:
            used.add(max(candidates, key=lambda c: c[1])[0])
            true_positive += 1
    precision = true_positive / len(predicted) if predicted else None
    recall = true_positive / len(gold) if gold else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    return {"gold": len(gold), "predicted": len(predicted), "matched": true_positive,
            "precision": precision, "recall": recall, "f1": f1}


def table_cell_accuracy(gold_rows: list[list[str]], predicted_rows: list[list[str]] | None) -> dict[str, Any]:
    if predicted_rows is None:
        return {"structure": "missing", "shape_match": False, "cell_accuracy": 0.0}
    shape = (len(gold_rows), max((len(r) for r in gold_rows), default=0))
    pred_shape = (len(predicted_rows), max((len(r) for r in predicted_rows), default=0))
    total = sum(len(r) for r in gold_rows)
    correct = sum(1 for r, row in enumerate(gold_rows) for c, cell in enumerate(row)
                  if r < len(predicted_rows) and c < len(predicted_rows[r]) and _norm(predicted_rows[r][c]) == _norm(cell))
    return {"structure": "present", "shape_match": shape == pred_shape, "gold_shape": shape,
            "predicted_shape": pred_shape, "cell_accuracy": correct / total if total else None}


# --------------------------------------------------------------- per page


@dataclass
class PageScore:
    source: str
    page_index: int
    categories: list[str]
    status: str | None
    cer: float | None
    wer: float | None
    reading_order: dict[str, Any]
    layout: dict[str, Any]
    tables: list[dict[str, Any]] = field(default_factory=list)
    seconds: float | None = None


def _page_blocks(document: Any, page_index: int) -> tuple[Any, list[Any]]:
    page = next(p for p in document.pages if p.page_index == page_index)
    top = sorted((b for b in document.blocks if b.page_id == page.id and b.parent_id is None),
                 key=lambda b: b.reading_order)
    return page, top


def _predicted_table_rows(document: Any, table: Any) -> list[list[str]] | None:
    if table.table is None or not table.table.cell_ids:
        return None
    cells = [b for b in document.blocks if b.parent_id == table.id and b.table_cell is not None]
    rows: dict[int, dict[int, str]] = {}
    for cell in cells:
        rows.setdefault(cell.table_cell.row_index, {})[cell.table_cell.column_index] = cell.current_text or ""
    return [[row[c] for c in sorted(row)] for _, row in sorted(rows.items())]


def score_page(document: Any, gold: dict[str, Any], *, source: str = "", seconds: float | None = None) -> PageScore:
    page, blocks = _page_blocks(document, gold["page_index"])
    texts = [b.current_text or "" for b in blocks]
    gold_text = " ".join(gold.get("reading_order", []))
    predicted = [{"type": b.block_type.value, "bbox": list(b.bbox)} for b in blocks]
    tables = []
    for gt in gold.get("tables", []):
        candidates = [b for b in blocks if b.block_type.value == "table" and _iou(gt["bbox"], b.bbox) >= 0.5]
        rows = _predicted_table_rows(document, candidates[0]) if candidates else None
        tables.append(table_cell_accuracy(gt["rows"], rows))
    return PageScore(
        source=source, page_index=gold["page_index"], categories=list(gold.get("category", [])),
        status=page.status.value if page.status else None,
        cer=cer(gold_text, " ".join(texts)) if gold_text else None,
        wer=wer(gold_text, " ".join(texts)) if gold_text else None,
        reading_order=reading_order_accuracy(gold.get("reading_order", []), texts),
        layout=detection_scores(gold.get("blocks", []), predicted) if gold.get("blocks") else {},
        tables=tables, seconds=seconds)


def summarize(scores: list[PageScore]) -> dict[str, Any]:
    """Aggregate by category. Failure rate = pages whose status is failed/needs_ocr/partial."""
    def mean(values: list[float | None]) -> float | None:
        vals = [v for v in values if v is not None]
        return sum(vals) / len(vals) if vals else None

    categories = sorted({c for s in scores for c in s.categories}) or ["all"]
    out: dict[str, Any] = {}
    for category in ["all", *[c for c in categories if c != "all"]]:
        group = [s for s in scores if category == "all" or category in s.categories]
        if not group:
            continue
        out[category] = {
            "pages": len(group),
            "mean_cer": mean([s.cer for s in group]),
            "mean_wer": mean([s.wer for s in group]),
            "mean_reading_order_pairwise": mean([s.reading_order.get("pairwise_accuracy") for s in group]),
            "mean_layout_f1": mean([s.layout.get("f1") for s in group]),
            "mean_table_cell_accuracy": mean([t.get("cell_accuracy") for s in group for t in s.tables]),
            "failure_rate": sum(1 for s in group if s.status in ("failed", "needs_ocr", "partial")) / len(group),
            "mean_seconds_per_page": mean([s.seconds for s in group]),
        }
    return out


def to_json(scores: list[PageScore], *, dataset: str, synthetic: bool) -> dict[str, Any]:
    return {"dataset": dataset, "synthetic": synthetic,
            "warning": ("SYNTHETIC fixtures: verifies the evaluation harness only; NOT textbook accuracy."
                        if synthetic else "Authorized real samples; see dataset notes for coverage."),
            "summary": summarize(scores), "pages": [asdict(s) for s in scores]}
