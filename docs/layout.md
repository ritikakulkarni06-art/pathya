# Phase 4 — layout detection and reading order

Modules:
- `layout.py`: the engine-independent part (assembly, reading order, tables,
  captions, quality flags and contract output)
- `layout_docling.py`: the only module that imports Docling

## Setup (verified 17 Nov 2026)

- **Versions:** Docling 2.70.0, docling-core 2.50.1, docling-ibm-models 3.9.1,
  docling-parse 4.7.0, torch 2.7.1 (CPU).
- **Weights:** downloaded once with `docling.utils.model_downloader.download_models`
  (layout and TableFormer only) into the git-ignored `local/docling-models/`
  (about 506 MB): `docling-project--docling-layout-heron` and
  `docling-project--docling-models`.
- **Configuration:** `DoclingConfig(artifacts_path=...)` or
  `PATHYA_DOCLING_ARTIFACTS`. Weights are only read locally; there are no
  downloads at run time.
- **Docling features turned off:** remote services, Docling's own OCR, picture
  classification and description, and formula and code enrichment.

## Two adapter modes, chosen per page

| Mode | When | Engine | Provides |
|---|---|---|---|
| `docling_pdf` | Rotation 0 **and** Phase 2 decision `native_text` | Docling `StandardPdfPipeline`, one page at a time (`page_range`) | Regions, TableFormer cells and headers, Docling reading order, caption links |
| `docling_image` | Rotated pages, scans, or after a direct-mode fallback | `LayoutPredictor` (layout-heron) on our Phase 2 rendering of the displayed page | Regions and scores only |

**Why there are two modes.** These problems were found while probing this
Docling version:
- On rotated **and** cropped pages, boxes were shifted by about the crop
  margin. On 180° and 270° pages, no regions came back at all.
- On image-only pages with Docling's OCR off, no regions came back, because
  regions without text cells are dropped.
- Docling's own `TesseractCliOcrOptions` crashed parsing Tesseract's output
  (`KeyError: 'text'`).
- A "proxy PDF" (our image plus an invisible text layer) lost paragraphs.

On unrotated pages, cropped or not, direct mode matched the Phase 2 geometry
to within about 0.003. The direct mode also checks that Docling's page size
equals the displayed size and otherwise falls back to image mode, with a
warning.

## Geometry conversion

- **Direct mode:** `BoundingBox.to_top_left_origin(page_height)`, divided by
  Docling's page size. Docling's page size equals our displayed (cropped) page
  size, which is checked.
- **Image mode:** predictor pixel boxes divided by the rendered image size. The
  render already has `/Rotate` and the CropBox applied, so this is exact for
  any rotation or crop.
- **Validation:** every box goes through `geometry.normalize_display_box`.
  - Partly outside the page: clipped and flagged `geometry_uncertain`.
  - Reversed, zero-size, NaN or fully outside: rejected, listed in
    `PageLayoutReport.rejected_regions`. The region's words still appear as
    uncertain paragraphs.

## Text, languages and duplicates

Words inside a block are read in **visual** order: clustered into lines, lines
top to bottom, words left to right. They are not read in PDF content-stream
order, which often differs from what is on the page. An over-large region that
contains two text columns is read column by column. Tables always read row by
row.

- Block text always comes from Phase 2 native words or Phase 3 OCR words whose
  centres fall in a region. Docling's own text is never used, except as the
  text of a table cell that has no geometry (flagged `missing_geometry`).
  This keeps raw text, list markers, `hi`/`en`/`mul` tags and OCR confidence
  and provenance. OCR engine and version and language data are stored in
  `provenance.parameters`.
- Native and OCR words covering the same text are used once, following the
  shared policy in `docs/ocr.md`:
  - Unreliable native words covered by an OCR line are replaced by the OCR.
    Native text is unreliable on `ocr_required` pages and on lines with
    undecodable glyphs.
  - OCR words covered by a reliable native line are dropped.
  - Each block that lost a duplicate is flagged `duplicate_content`, and the
    count appears in the report.
- Words outside every region become paragraphs flagged
  `block_type_uncertain`, one per source line, placed by geometry. Nothing is
  dropped.

## Region post-processing

- **Duplicates:** a same-type prediction with IoU above 0.7, or one contained
  in another, is merged.
- **Conflicts:** a different-type prediction with IoU above 0.5 is merged, the
  alternative label is recorded, and `block_type_uncertain` is added if its
  score is at least half of the kept one.
- **Low scores:** a score below 0.5 adds `block_type_uncertain`. Raw image-mode
  predictions below 0.3 are dropped, and their count is reported.
- **Unsupported labels:** labels with no mapping (code, form, key-value,
  checkbox) become `paragraph` with `unsupported_content` and
  `block_type_uncertain`.
- **Empty containers:** an empty text-like region overlapping regions that hold
  text is removed and recorded.
- **Overlaps:** remaining overlaps above 30% of the smaller region add
  `overlapping_regions`.

## Reading order

Candidates are computed for each page, and every one is kept in
`PageLayoutReport.order.candidates`:

| Candidate | Source |
|---|---|
| `layout_engine` | Docling's order (direct mode only) |
| `geometric_columns` | Our column-aware order (below) |
| `native_stream` | First native word's position in the PDF content stream |
| `ocr` | First OCR word's Tesseract order |

**`geometric_columns` algorithm:**
1. Find gutters in the x-coverage of regions narrower than 60% of the page.
   Coverage is weighted by height, so one small stray box cannot hide a
   gutter.
2. A gutter counts only if regions on both sides overlap vertically.
3. Regions that are full-width or cross a gutter split the page into
   horizontal bands.
4. Inside each band, read columns left to right, and each column top to
   bottom.

**Selection.** Use `layout_engine` when it covers at least half the regions;
regions it missed are inserted at their geometric position. Otherwise use
`geometric_columns`. The reason is recorded.

**Ambiguity.** Blocks in pairs that are out of order between the engine order
and the geometric order get `reading_order_uncertain`, and the page is marked
`ambiguous`. A narrow block straddling a gutter also marks the page
ambiguous. Disagreement with `native_stream` or `ocr` is only counted, because
content-stream order often differs harmlessly from visual order.

**Output.** `reading_order` is per page; page order stays as `page_index`.
`precedes` edges link consecutive top-level blocks within a page only.

## Tables, equations and figures

- **Tables (direct mode):**
  - Cells come from TableFormer, with row and column, spans and header flags.
  - `header_cell_ids` link each cell to the column headers above it and the
    row headers beside it, plus `header_for` and `contains` edges.
  - Cell text comes from words in each cell box.
  - If the grid is inconsistent (overlap, out of range) or has no cells, the
    block becomes an **uncertain table candidate** (no cells, all its text in
    `raw_text`, `table_structure_uncertain`).
  - Words not inside any cell also add `table_structure_uncertain`.
- **Tables (image mode):** always an uncertain table candidate, because
  TableFormer is not run.
- **Equations:**
  - `EquationMeta.source_text` is the extracted text, the crop is the block
    box, and the flag is `math_needs_review`.
  - No MathML or spoken text is generated; formula enrichment is off.
- **Figures:** `FigureMeta` has no alt text or description (nothing is
  generated).
- **Caption links:** `caption_block_id`, `source_caption` and `caption_of`
  edges are set **only** from Docling's own caption links (direct mode).
  Captions without a link, including every caption in image mode, get
  `orphan_caption`.

## Performance

- Pages are processed one at a time. Docling and the predictor are loaded once
  per engine.
  - First model load: about 40 s.
  - After that: about 3 s per page in direct mode and about 3 s per page in
    image mode at 144 DPI.
- Rendered images can be passed to `analyze_document(images=...)` for reuse.
  Images the adapter renders itself are closed afterwards.
- Direct mode uses Docling's `document_timeout`. Image-mode prediction has no
  timeout of its own, since it is a single model call per page.
- Docling failures (parse errors, a missing file) return a `FAILED` page.
  Assembly then keeps all text as uncertain paragraphs with `derived`
  provenance.

## Known limitations

- **Validation scope:** this has only been checked on clean synthetic pages
  (Helvetica, simple layouts) and rendered Hindi and mixed fixtures. Accuracy
  on real textbook scans is **not** measured (Phase 7).
- **Image mode is reduced:** no table structure, engine reading order or
  caption links.
- **Rotated pages always use image mode**, even with a good native text layer.
- **Single-model order:** the reading order on complex layouts (sidebars,
  wrap-around figures, nested boxes) depends on Docling's model and the
  column heuristic; disagreements are flagged, but not resolved.
- **Lines across columns:** Phase 2 lines now split at gaps wider than 1.2×
  the glyph height. Very loosely justified text could split a line in two,
  which affects only the line grouping, never the words.
- **Docling warning:** Docling emits a `DeprecationWarning` about
  `generate_table_images` from inside its own pipeline.
