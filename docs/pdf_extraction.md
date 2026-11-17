# Phase 2 — native PDF extraction

Modules: `src/pathya_document_ai/pdf.py`, `quality.py` and the coordinate
helpers in `geometry.py`. There is no OCR, Docling, table, equation or figure
handling yet.

## Interfaces

| Function | Returns |
|---|---|
| `check_pdf_file(path, limits)` | File size, after checking the size and the `%PDF-` signature (first 1 KiB); the extension is ignored |
| `extract_native_pdf(path, limits=, thresholds=)` | `PdfExtraction` → one `PageExtraction` per page |
| `iter_rendered_pages(path, indices=, dpi=, grayscale=, limits=)` | Yields a `RenderedPage` for each page, one at a time |
| `render_page(path, index, ...)` | A single `RenderedPage` |
| `to_contract_document(extraction, source_uri=...)` | A Phase 1 `Document` |
| `geometry.normalized_to_pdf_user_space` / `pdf_user_space_to_normalized` | Maps a box between contract coordinates and PDF user space |

**Errors.** All errors derive from `PdfInputError`: `NotPdfError`,
`PdfTooLargeError`, `PdfEncryptedError`, `PdfMalformedError`, `PdfLimitError`
and `PdfTimeoutError`. If text extraction fails on one page, that page gets
`status = text_extraction_failed` and a warning, and the other pages are still
processed.

**`PageExtraction` fields:**
- `page_index` (zero-based)
- `page_label`, taken only from the PDF's `/PageLabels`, otherwise `None`
- `width` and `height` of the displayed page, in points
- `rotation` and `transform`
- `words`, each with its text exactly as extracted, a normalized `bbox`, the
  raw `display_box`, `fontname`, `glyph_height`, `upright` and `notes`
- `lines`, which are the text regions for this phase
- `stream_order` (the order text appears in the PDF's content stream) and
  `geometric_order`: two candidate reading orders
- `ocr` (the `OcrAssessment`: decision, reasons and metrics)
- `warnings`

**`RenderedPage`.** `image` is a PIL image of the page as displayed, with
`/Rotate` and the CropBox already applied. Pixel `(px, py)` corresponds to the
normalized point `(px / width_px, py / height_px)`.

## Coordinates

- Boxes are normalized `[x0, y0, x1, y1]` over the displayed page, with the
  origin at the top-left, following `geometry.py`.
- The visible region is CropBox ∩ MediaBox, rotated by `/Rotate`. This is
  computed from user space rather than taken from pdfplumber's `page.cropbox`,
  because that value is wrong for `/Rotate 180`.
- Tests check that every box maps back to the same PDF user-space position at
  0°, 90°, 180° and 270°, with and without a crop.
- A rendered black rectangle lands where the geometry says it should.
- Words partly outside the crop are clipped and noted as `clipped`. Words fully
  outside are kept with `bbox=None` and a warning. Zero-size boxes are widened
  to 1e-6 and noted as `degenerate`.

## OCR-needed decision (`quality.assess_ocr_need`)

| Decision | When |
|---|---|
| `ocr_required` | No text, and images cover at least 25% of the page; or at least 25% of characters cannot be mapped to Unicode |
| `ocr_recommended` | No text with a small image, or no text with 50 or more vector objects (possibly text drawn as outlines); or images cover at least 50% with fewer than 200 characters; or native extraction failed |
| `blank` | No text, no images, few vector objects |
| `native_text` | Otherwise. Short text adds `short_text_not_scan_evidence`; a full-page image under the text adds `full_page_image_under_text` |

The thresholds can be changed through `OcrThresholds`.

## Safety and limits

`PdfLimits` sets maximums for:
- file size
- page count
- characters per page
- total time (checked between pages)
- render DPI
- pixels per rendered page (checked before rendering)

Other safeguards:
- Files are streamed from disk and hashed in chunks.
- Each pdfplumber page is closed after use, and every PDFium page, bitmap and
  document is closed explicitly in `finally` blocks.
- PDFium runs without a form environment, so no JavaScript runs, and no URLs
  are fetched.

## Known limitations

- **Encrypted PDFs** that need a password are rejected; no password can be
  supplied in this phase.
- **Hindi text**: native text from Indic PDFs often decodes incorrectly because
  of legacy fonts and missing mappings. This shows up as `unmapped_glyphs` only
  when pdfminer reports `(cid:N)`, U+FFFD or private-use characters. Text that
  is wrong but valid Unicode, such as reordered Devanagari matras, is **not**
  detected. That is Phase 5 quality work.
- **Lines, not paragraphs**: text regions are lines. Paragraph and column
  structure comes from layout analysis in Phase 4.
- **Invisible OCR layers**: text drawn in invisible render mode (an existing
  OCR layer) is treated as native text, and only flagged when a full-page image
  lies underneath it.
- **Time limit**: the limit is checked between pages; a single slow page is not
  interrupted.
- **Contract conversion is provisional**: each line becomes a `paragraph` block
  with language `und` and the flags `language_uncertain` and
  `reading_order_uncertain`. See the contract issue in the Phase 2 report.
