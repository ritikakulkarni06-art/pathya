# Phase 3 — image preprocessing and English/Hindi OCR

Modules: `tesseract.py` (detection), `preprocess.py`, `ocr.py`. There is no
Docling, layout, table, equation or figure handling yet.

## Setup (verified 17 Nov 2026)

- **Tesseract 5.4.0.20240606** (UB-Mannheim build, installed with
  `winget install UB-Mannheim.TesseractOCR`) at
  `C:\Program Files\Tesseract-OCR\tesseract.exe`. Its default tessdata
  folder contains only `eng` and `osd`.
- **Bilingual data:** official `tessdata_fast` models in the git-ignored
  `local/tessdata/`, downloaded from
  `github.com/tesseract-ocr/tessdata_fast` (main branch):

  | File | SHA-256 |
  |---|---|
  | `eng.traineddata` | `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` |
  | `hin.traineddata` | `4c73ffc59d497c186b19d1e90f5d721d678ea6b2e277b719bee4e2af12271825` |
  | `osd.traineddata` | `9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff` |

- **Configuration:**
  - `TesseractConfig(executable=..., tessdata_dir=...)`, or the environment
    variables `PATHYA_TESSERACT_CMD` and `PATHYA_TESSDATA_DIR`.
  - The tessdata path must not contain whitespace, because pytesseract keeps
    quote characters on Windows.
  - The default languages are `("hin", "eng")`. If any are missing,
    `TesseractLanguageError` is raised. There is **no** automatic fallback to
    English only; English-only OCR happens only when the caller configures
    `languages=("eng",)`.

## Preprocessing (`preprocess.preprocess`)

Each step produces a new image; the input image is never modified.
`ProcessedImage.forward` is the 3×3 affine map from original pixels to
processed pixels, and `to_original()` maps OCR boxes back.

| Step | Default | Notes |
|---|---|---|
| Flatten alpha onto white | when needed | |
| Grayscale | on | |
| Upscale toward 300 DPI | when the source DPI is lower | Capped at 2×; Lanczos resampling |
| Deskew | on, only when justified | Projection-profile search within ±5°. Applied only if the angle is at least 0.3° and the profile score improves by at least 10%. The canvas is expanded so no corner is cut off. |
| Contrast | `autocontrast` (linear, no clipping) | `clahe` is optional |
| Denoise | **off** | `nl_means` is optional. `median` erases 1-px marks (shown by a test). |
| Threshold | **off** | `adaptive` (block 31, C 10) or `otsu` are optional |

Tests show that the default pipeline, adaptive thresholding and
CLAHE + NL-means all keep faint decimal points, minus signs, small dots and
1-px strokes. They also show the default and adaptive pipelines lose no
connected components (matras, dots, danda) from the Hindi fixture.

## OCR interface (`ocr.py`)

| Function | Purpose |
|---|---|
| `TesseractEngine(config)` | Detects Tesseract and checks languages; runs `pytesseract.image_to_data` with a timeout |
| `ocr_image(image, engine=, config=, page_index=, dpi=, transform=)` | Returns an `OcrPageResult` |
| `select_ocr_pages(extraction, force_pages=, include_recommended=False)` | Pages the caller forces, plus pages Phase 2 marked `ocr_required` |
| `ocr_pdf_pages(path, extraction, engine=, ...)` | Renders and OCRs pages one at a time; returns `OcrRun` (results and skipped pages with reasons) |
| `to_contract_blocks(result, page_id)` | Converts to Phase 1 blocks |
| `merge_ocr_into_document(document, results, extraction=)` | Adds OCR lines to a Phase 2 (line-level) `Document` using the shared native/OCR policy below. Every decision is reported in `notes`. |

**`OcrPageResult`.** It records:
- the page index, original image size, DPI and Phase 2 transform
- `status` (`ok` or `blank_image`)
- `words` and `lines`
- the languages, engine and version
- a `language_data` fingerprint (traineddata SHA-256 prefixes)
- psm/oem and the preprocessing steps
- `diagnostics` and `warnings`

**`OcrWord`.** Each word has:
- `raw_text` (Tesseract output, unchanged) and `text` (NFC form only)
- normalized `bbox` and original-pixel `image_box`
- `confidence` (Tesseract conf / 100; null for -1 or invalid values),
  `raw_confidence`, `script`, `language`, `line_key` and `notes`

Lines follow Tesseract's (block, paragraph, line) grouping. A line's
confidence is the mean of its non-null word confidences.

**Language rules.** Language comes from the Unicode script of each word,
limited to the configured languages:
- Devanagari → `hi`; Latin → `en`
- both in one word → `mul` (flagged `mixed_script`)
- digits or symbols only, or another script → `und`
- a line containing both `hi` and `en` → `mul`

No text is translated.

**Contract conversion.** Each line becomes a provisional `paragraph` block:
- `raw_text = current_text =` Tesseract's raw line text (revision 1)
- confidence `engine_reported` (the mean), or `not_available`
- flags `reading_order_uncertain` and `low_confidence` +
  `possible_ocr_error` below 0.60, plus `mixed_script` or
  `language_uncertain` where they apply
- provenance `ocr`/`tesseract`/version, with the language-data fingerprint as
  `model_version`

## Native/OCR merge policy (shared by `merge_ocr_into_document` and layout)

This policy was fixed after the pre-Phase-5 audit. Before the fix, good OCR was
discarded on pages whose native text was garbled, and partly overlapping OCR
was added as unflagged duplicate text.

**When native text is unreliable.** Native text counts as unreliable for:
- a whole page, when Phase 2 decided `ocr_required` for it (pass
  `extraction=` to the merge function)
- a single line or block containing undecodable glyphs, which is flagged
  `possible_ocr_error`

**Coverage.** An OCR word is *covered* when its centre lies inside a native
line or block.

**What happens to each OCR line:**

| Situation | Result |
|---|---|
| No covered words | Added as new content, unflagged |
| Covers only unreliable native text | OCR **replaces** that native block at the same reading position, flagged `duplicate_content`. The native text stays in `PdfExtraction`. |
| At least 50% of its words cover reliable native text | Not added. The native block gets `duplicate_content`. |
| Partly covers reliable native text | Added and flagged `duplicate_content` for review. It is never added silently. |

**Layout path.** `build_layout_document` applies the same rule word by word.
It drops unreliable native words covered by an OCR line, and OCR words covered
by a reliable native line. A test checks that both paths produce the same text.

**Version.** A document that receives `duplicate_content` is upgraded to schema
1.1.0, and the upgrade is reported in `notes`.

## Safety

- One page image is kept in memory at a time, and rendered images are closed.
- Image width, height and pixel limits apply to the input and to every
  processed derivative.
- Each Tesseract call has its own timeout (pytesseract kills the process), and
  a total time limit is checked between pages.
- pytesseract's temporary files are removed (checked by a test).
- Uniform images skip Tesseract.
- No document content is executed and nothing is fetched.

## Known limitations

- **Short Hindi words between English words** may be misread. In the mixed
  fixture, "दर्पण" in "Mirror दर्पण 2024" came out as `@UUI` (line
  confidence about 0.68). Low-confidence flags catch many cases like this, but
  not all.
- **Model accuracy**: `tessdata_fast` models trade accuracy for speed. The
  `tessdata_best` `hin` model may do better on real scans; this has not been
  measured.
- **Test coverage**: the fixtures are clean renders at about 44 px glyph
  height. Real scans with blur, show-through, warping, low DPI or old
  typefaces have **not** been evaluated; that is Phase 7 work.
- **Script vs language**: Latin script is tagged `en` because only eng and hin
  are configured. Romanized Hindi would be tagged `en`.
- **Vertical text**: vertical or sideways text inside an upright page is not
  handled, and orientation detection (`osd`) is not used.
- **Normalized text in the contract**: the NFC form is kept in the OCR
  result, but a revision-1 contract block can only store raw text (see the
  Phase 3 report).
- **Fixtures**: they are rendered by `scripts/make_ocr_fixtures.py` with
  headless Edge or Chrome and the Windows "Nirmala UI" font, because Pillow
  here lacks libraqm and cannot shape Devanagari.
