# Extraction evaluation

**Status: real-textbook evaluation is PENDING.** No authorized English, Hindi
or mixed textbook pages are available yet, so this project has **no** measured
textbook accuracy. Everything below the harness section is a protocol, not a
result.

## Harness

- **Metrics:** `src/pathya_document_ai/evaluation.py`, dependency-free.
- **Runner:** `scripts/evaluate.py`.
  - It runs native extraction, plus Tesseract OCR and Docling layout when they
    are available locally. Which engines actually ran is recorded in the report.
  - It writes `report.json` and `report.md`.
  - A crash counts as a failed page, not a skipped one.

| Metric | Definition |
|---|---|
| CER / WER | Levenshtein distance on NFC, whitespace-normalized page text (top-level blocks in reading order) against the gold text |
| Reading order | Pairwise agreement between gold segment order and predicted block order, using one-to-one fuzzy matching. Unmatched segments are reported separately. |
| Layout | Precision, recall and F1 of top-level blocks at IoU ≥ 0.5 with the same block type |
| Tables | Grid shape match and exact cell-text accuracy. A table with no recovered structure scores 0. |
| Failure rate | Share of pages whose status is `failed`, `needs_ocr` or `partial`, or which crashed |
| Time | Seconds per page, including first-call model loading (cold start) |

The metric tests (`tests/unit/test_evaluation.py`) check that each metric
actually detects its error: swaps, missing segments, wrong block types,
shifted boxes, wrong cells, and a dropped Hindi virama.

**Synthetic smoke run.** `python scripts/evaluate.py --synthetic --out <dir>`
evaluates the generated 5-page English textbook. It scored CER 0, reading
order 1.0 and table cells 1.0, and layout F1 was not measured. Those numbers
**only show that the harness works**; clean generated pages say nothing about
real textbooks.

## Protocol for real samples

**Data rules:**
- Use only pages you are authorized to use; record who approved it and the
  licence in the manifest's `authorization` field.
- Keep the PDFs and gold files in `evaluation/private/`, which is git-ignored.
- Never upload them to external services.
- Commit only aggregate results, after checking they reveal no textbook content.

**Coverage target (minimum per category before Phase 5 thresholds are set):**

| Category | Pages | What it exercises |
|---|---|---|
| English, native text | 20 | Baseline text and order |
| Hindi, native text | 20 | Devanagari encoding problems (unmapped or reordered glyphs) |
| Mixed English/Hindi | 15 | `mul` tagging, script switching |
| Scanned (English and Hindi) | 20 | OCR quality, `needs_ocr` handling |
| Multi-column | 10 | Column detection, reading order |
| Tables | 10 | TableFormer structure, uncertain-table fallback |
| Equations | 10 | Region detection, `math_needs_review` |
| Figures and captions | 10 | Caption linking, orphan captions |
| Rotated, low-quality (low DPI, skewed, show-through) | 10 | Deskew, rotation, OCR degradation |

**Gold annotation.** One JSON list per PDF; see the module docstring of
`evaluation.py`:
- `reading_order`: all text segments in the order a human reads them
- `blocks`: type and normalized bbox per block (needed for layout F1)
- `tables`: bbox and cell text per row

Annotate from the page image, not from the system's output.

**Run:**
```
python scripts/evaluate.py --manifest evaluation/private/<set>/manifest.json --out evaluation/results/<set>
```

Report every category separately. Do not quote an `all` average without the
per-category rows.
