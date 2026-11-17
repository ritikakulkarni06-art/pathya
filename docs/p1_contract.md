# P1 content contract — version 1.1.0

> **Status: 1.1.0 is PROPOSED, not approved. P2/P3 approval is pending.**
>
> 1.1.0 is **backward-compatible** (every valid 1.0.0 document is still
> valid) but **not forward-compatible**: a consumer that only implements
> 1.0.0 will reject 1.1.0 documents. See
> [Compatibility policy](#compatibility-policy-110) and the change request
> in `docs/contract_change_request_v1.1.0.md`.
>
> P3 has separately drafted its own extraction contract on the `person-3`
> branch. The two drafts are not compatible; see the change request.

This is the shared data structure P1 (document AI) produces and P2 (frontend,
speech) and P3 (backend, storage, question answering) consume.

| Artifact | Location |
|---|---|
| Pydantic models (source of truth) | `src/pathya_document_ai/models.py`, `geometry.py` |
| JSON Schema 1.1.0 (current, Draft 2020-12, generated) | `contract/schemas/pathya_content.v1.1.0.schema.json` (also `contract/pathya_content.schema.json`) |
| JSON Schema 1.0.0 (frozen, reconstructed) | `contract/schemas/pathya_content.v1.0.0.schema.json` |
| Conformance vectors (valid and invalid, with expected verdicts) | `contract/conformance/` |
| Bilingual sample document (1.0.0) | `contract/samples/sample_document_en_hi.json` |
| Regenerate or check | `scripts/export_schema.py [--check]`, `scripts/make_conformance.py [--check]` |

**Status:** proposed by P1 in Phase 1. It is not yet the agreed integration contract.
P2 and P3 must review the open decisions at the end of this document first.
No extraction code produces it yet. The sample is hand-written to show the
format; it is not real extraction output.

## Two validation layers

1. **JSON Schema** checks shapes, required fields (including every `id` in
   1.1.0), enums, numeric ranges, UUID format, bbox length, table-count
   nullability and the 1.0.0 restrictions. Any language can use it.
2. **The Pydantic `Document` validator** also checks rules JSON Schema cannot
   express: cross-references, bbox ordering (`x0 < x1`), table spans,
   confidence consistency, revision rules and conservative equation rules.
   Treat this layer as authoritative. P3 should validate with it from Python,
   or reproduce these rules in its own code. The rules are listed under
   `x-pathya-invariants` in the schema. The `invalid_python_only_*`
   conformance vectors are documents that pass JSON Schema but must be
   rejected.

All objects reject unknown fields (`extra = forbid`). Timestamps must include a
timezone (ISO 8601, e.g. `2026-11-17T09:30:00Z`).

## Identity

- Every `id` is a random UUID (version 4), created once when the object is
  first made. IDs never depend on text, position or page, so correcting text
  never changes an ID.
- IDs are unique within a document across pages, blocks, edges and corrections.
- Re-extraction identity (matching old and new blocks after a source is
  processed again) is **not** solved in v1. See the open decisions.

## Document

| Field | Meaning |
|---|---|
| `schema_version` | Always `"1.0.0"` for this version |
| `id`, `title`, `created_at` | Identity, optional title, creation time |
| `languages` | Languages present (at least one), from the `Language` values |
| `source_asset` | `{id, uri, media_type, sha256}`. `uri` is an opaque reference assigned by P3. `media_type` ∈ `application/pdf`, `image/png`, `image/jpeg`, `image/tiff` |
| `pages`, `blocks`, `edges`, `corrections` | Lists described below |

## Page and coordinates

| Field | Meaning |
|---|---|
| `page_index` | **Zero-based physical position** in the source file. Unique. |
| `page_label` | **Printed page label** (e.g. `"iv"`, `"48"`), or null. Never used for ordering. |
| `width`, `height`, `units` | Displayed page size; `units` is `pt` (PDF) or `px` (image) |
| `rotation` | Source rotation in degrees clockwise: 0, 90, 180 or 270 |
| `source_asset_id` | Must equal `document.source_asset.id` |
| `transform` | How normalized coordinates map back to the source (below) |
| `status` (1.1.0) | `ok`, `blank`, `needs_ocr`, `partial` or `failed`. Required in 1.1.0; absent in 1.0.0. |
| `warnings` (1.1.0) | List of `{stage, code, message}`. `stage` is `extraction`, `ocr`, `layout` or `merge`; `code` matches `^[a-z][a-z0-9_]{0,63}$`. |

**What each page status means:**

| `status` | Meaning | What consumers should do |
|---|---|---|
| `ok` | Content was extracted, natively and/or by OCR | Show normally |
| `blank` | Nothing to extract. A blank page cannot have blocks. | Show as an empty page |
| `needs_ocr` | Content is probably inside images, but OCR was not run | Do not treat the page as complete; queue OCR or review |
| `partial` | A stage failed (for example layout). Text was kept, but its structure may be wrong. | Show, flagged for review |
| `failed` | Extraction failed; the page's content is missing | Show the error; do not treat the page as blank |

**Bounding-box convention.** `bbox = [x0, y0, x1, y1]`, normalized to `0..1`
over the *displayed* page. "Displayed" means after rotation and within the
crop box. The origin is the **top-left** corner, y increases **downward**,
and `x0 < x1`, `y0 < y1` (no zero-size boxes).

**Transform.** `{normalized_origin: "top_left", source_space, crop_box,
rotation_applied, render_dpi}`.
- `source_space` is `pdf_user_space` (points, bottom-left origin) or
  `image_pixels` (top-left origin).
- `crop_box` is the visible region in source units.
- `render_dpi` is set when a raster was used (e.g. for OCR).

To map a box back to the source:
1. Multiply by the displayed width and height.
2. Undo `rotation_applied`.
3. Add the crop offset.
4. For PDF sources, flip y.

## Block

| Field | Meaning / rule |
|---|---|
| `page_id` | Must reference a page in the document |
| `parent_id` | Optional containing block (e.g. table → cells). Must exist; not itself; no cycles |
| `block_type` | `heading`, `paragraph`, `list_item`, `table`, `table_cell`, `equation`, `figure`, `caption` |
| `reading_order` | Integer ≥ 0, unique among siblings with the same `(page_id, parent_id)` |
| `bbox` | See the convention above |
| `raw_text` | Text exactly as extracted. **Never edited.** |
| `current_text` | Text after content corrections; equals `raw_text` while `revision == 1` |
| `language` | `en`, `hi`, `mul` (mixed, e.g. Hindi with English terms) or `und` (unknown / not applicable) |
| `revision` | Integer ≥ 1. Revision 1 means not yet edited |
| `review_status` | `unreviewed`, `needs_review`, `approved`, `rejected` |
| `confidence` | See Confidence below |
| `quality_flags` | Unique list of: `low_confidence`, `possible_ocr_error`, `mixed_script`, `language_uncertain`, `reading_order_uncertain`, `geometry_uncertain`, `table_structure_uncertain`, `math_needs_review`, `unsupported_content`, `empty_text`. Added in 1.1.0: `block_type_uncertain`, `missing_geometry`, `overlapping_regions`, `orphan_caption`, `duplicate_content` |
| `provenance` | See Provenance below |
| `table`, `table_cell`, `equation`, `figure` | Extra details for that block type only. Each is required on the matching block type and forbidden on every other type |

**Text rules:**
- `heading`, `paragraph`, `list_item`, `table_cell` and `caption` must have
  text. An empty string is allowed when paired with the `empty_text` flag.
- `table`, `figure` and `equation` may have null text.
- `raw_text` and `current_text` are either both null or both set.

### Confidence

`{score, origin, reason}`. `score` is a number from 0 to 1, or **null**.

| `origin` | Rule |
|---|---|
| `engine_reported` | The engine gave a score; `score` is required |
| `model_estimated` | A separate calibration model produced it; `score` is required |
| `heuristic` | A rule produced it; `score` and `reason` are required |
| `not_available` | `score` **must be null** and `reason` is required |

Native PDF text has no meaningful confidence. It is always `not_available`
with a null score, **never 1.0**. Consumers must not treat null as high
confidence.

### Provenance

`{method, engine, engine_version, model, model_version, parameters, created_at}`.
- `method` ∈ `native_pdf_text`, `ocr`, `layout_model`, `human`, `derived`.
- Machine methods (`native_pdf_text`, `ocr`, `layout_model`) require `engine`
  and `engine_version`.
- `parameters` is a flat map of simple values (e.g. `{"lang": "hin+eng", "psm": 6}`).

### Tables

- **Table block** `table`: `{row_count ≥ 1, column_count ≥ 1, cell_ids[]}`.
  Since 1.1.0 it may instead be an *uncertain table candidate*:
  `{row_count: null, column_count: null, cell_ids: []}`. Such a block must
  carry `table_structure_uncertain`, and its `raw_text` holds the region's
  text. Counts are never guessed.
- **Cell block** `table_cell`: `{table_id, row_index, column_index` (zero-based)`,
  row_span ≥ 1, column_span ≥ 1, is_header, header_cell_ids[]}`.

The document validator checks that:
- each cell lists an existing table, and that table lists the cell;
- cells are on the same page as their table;
- spans stay within the table's rows and columns;
- `header_cell_ids` point to header cells in the same table.

Cells normally set `parent_id` to the table. `header_for` edges may repeat the
header links for graph consumers.

### Equations (conservative)

`equation`: `{source_crop_uri, source_text, mathml, mathml_review_status,
spoken_fallback, spoken_fallback_origin, spoken_fallback_review_status}`.
- The canonical source is the block's page plus `bbox`. `source_crop_uri`
  optionally points to a stored crop image. `source_text` is text exactly as
  extracted.
- `mathml` may be stored **only** when `mathml_review_status = approved`, and
  must be a `<math>` element. Unreviewed machine-made MathML is not part of v1.
- `spoken_fallback` describes the printed expression in words. It must not
  solve or rewrite it. It requires `spoken_fallback_origin` (`source`, `human`,
  `model_generated`).
- When there is no approved MathML, P2 should show the source crop and read
  the fallback only if it is approved. If there is no fallback, P2 should
  announce an equation that needs review.

### Figures

`figure`: `{source_caption, caption_block_id, alt_text, extended_description}`.
- `source_caption` is caption text as printed.
- `caption_block_id`, when set, must reference a `caption` block.
- `alt_text` (≤ 250 characters) and `extended_description` are each
  `{text, language, origin, review_status}`, with `origin` ∈ `source`, `human`,
  `model_generated`.
- P2 must label model-generated text that has not been approved.

## Edge

`{id, edge_type, source_id, target_id, provenance}`. The source and target
must be different blocks, and both must exist in the document.

| `edge_type` | Direction and rule |
|---|---|
| `contains` | parent → child. Must agree with the child's `parent_id` |
| `precedes` | earlier → later in reading order, including across pages |
| `caption_of` | caption block → figure, table or equation |
| `refers_to` | referring block → referenced block (e.g. "see Fig. 10.1") |
| `header_for` | header `table_cell` → `table_cell` |
| `supersedes` | new block → old block it replaces (reserved for re-extraction) |

## Correction

A **content-only** correction request for one block. It never changes
geometry, identity or block type.

Fields: `{id, document_id, block_id, base_revision, operation, new_text,
new_language, new_review_status, reason, author_ref, created_at}`.

`operation` decides which payload field is set. Exactly that one field is
present; the other two are null.

| `operation` | Payload field |
|---|---|
| `replace_text` | `new_text` |
| `set_language` | `new_language` |
| `set_review_status` | `new_review_status` |

`base_revision` is the block revision the editor saw. A document's
`corrections` list is the history of applied corrections. Each entry's
`base_revision` must be lower than the target block's current revision.

`author_ref` is an opaque reviewer reference supplied by P3. P1 stores no
user identity.

Applying corrections (conflict checks, the revision increment) is Phase 5
work. Storing them, transactions and invalidating derived data (audio,
embeddings) belong to P3.

## Versioning

- `schema_version` uses semantic versioning. The Python validator accepts
  `"1.0.0"` and `"1.1.0"`.
- **Patch**: documentation or validation-message changes only; the data
  format is unchanged.
- **Minor**: additive for readers that support the new version (new optional
  field, new enum value). A minor version is backward-compatible, not
  forward-compatible: readers that only know the older version reject it.
  Producers must not send it until consumers confirm support.
- **Major**: removals, renames, meaning changes or new required fields.
- Each change updates `SCHEMA_VERSION`, regenerates the schema
  (`scripts/export_schema.py`), updates the sample and this document, and
  records the impact on P2 and P3 in the changelog below. A test fails if the
  committed schema is stale.

## Handoff to P2 / P3

- **P3** will call a Python function (Phase 6) that returns a `Document`, or
  its JSON from `model_dump_json()`. P3 stores it, owns transactions, and
  sends `Correction` requests to P1 for content validation.
- **P2** receives the JSON as stored by P3:
  - It renders blocks by `(page, parent, reading_order)` or by following
    `precedes` edges.
  - It reads `current_text`, using `language` to pick the voice.
  - It shows uncertainty using `confidence` and `quality_flags`.
- Neither consumer depends on parser objects from pdfplumber, Docling or
  Tesseract.

## Open decisions needing P2/P3 agreement

1. **Re-extraction identity**: how new blocks are matched to old ones, and
   whether `supersedes` edges or carried-over IDs are used.
2. **Reading order across pages and columns**: whether `precedes` edges are
   always produced, or consumers sort by page and `reading_order`.
3. **Unreviewed machine MathML**: whether a `mathml_candidate` field should be
   added in a later minor version.
4. **Applying corrections**: whether P1 returns a whole updated block or a
   diff, and whether a `set_review_status` change bumps `revision`.
5. **Storage URIs**: the format of `source_asset.uri` and `source_crop_uri`
   (owned by P3).
6. **Language tags**: whether more languages or script subtags (e.g.
   `hi-Latn`) are needed.
7. **Quality-flag thresholds**: the confidence threshold for `low_confidence`
   (Phase 5) and how P2 presents it.

## 1.1.0 changes (proposed in Phase 4, revised before Phase 5)

**Why these are needed.** Layout analysis must report:
- uncertain block types
- missing geometry
- overlapping regions
- captions with no linked figure or table
- native and OCR text that duplicate each other

1.0.0 had no way to express these. The Phase 4 rules also forbid inventing
table cells when the structure can't be reconstructed, yet 1.0.0 required at
least one cell in every table.

**Changes:**
1. Five new `quality_flags` values: `block_type_uncertain`,
   `missing_geometry`, `overlapping_regions`, `orphan_caption`,
   `duplicate_content`.
2. Uncertain table candidates (see Tables above).
3. `schema_version` accepts `"1.0.0"` or `"1.1.0"`; P1 emits `"1.1.0"`.
4. Page `status` and `warnings`, added in the pre-Phase-5 revision. Failed and
   needs-OCR pages are now visible in the JSON, not only in Python report
   objects.
5. Stricter validation in 1.1.0:
   - every `id` is required in serialized documents (before, a missing id was
     silently replaced with a new random UUID)
   - a child block must be on its parent's page

**Compatibility rules (enforced and tested in
`tests/unit/test_contract_versions.py`):**
- A document labelled `"1.0.0"` is validated with 1.0.0 rules. Using a 1.1.0
  flag or an uncertain table inside it is rejected.
- `models.upgrade_document_data()` migrates 1.0.0 → 1.1.0 without losing
  anything. It relabels the version and sets each page's status to `ok` with
  no warnings, which is exactly what a 1.0.0 producer asserted by emitting the
  page. Unknown versions are rejected.
- The committed sample stays at 1.0.0 as the backward-compatibility fixture.

**Impact on consumers:**
- **P2:** it must accept the new flags (show them as "needs review") and handle
  a `table` block with no cells by reading its `raw_text`.
- **P3:** it must store and allow the new enum values, and accept null table
  counts.

Documents P1 produced earlier (1.0.0) are unaffected and still validate.

## Compatibility policy (1.1.0)

| Reader | Writer emits 1.0.0 | Writer emits 1.1.0 |
|---|---|---|
| 1.0.0-only reader (1.0.0 schema) | Accepted | **Rejected** (version, status, new flags, null table counts) |
| 1.1.0 reader (1.1.0 schema or Python) | Accepted, with 1.0.0 rules applied | Accepted |

**Rules:**
- **Default output.** P1 emits 1.1.0 by default, because page status is
  always present.
- **Exporting 1.0.0.** `models.export_document_data(document, "1.0.0")`
  produces a 1.0.0 document only when nothing would be lost: no 1.1.0 flags,
  no uncertain tables, every page `ok`, and no warnings. Page status is then
  omitted. Otherwise it raises `IncompatibleVersionError`. **Nothing is
  silently downgraded or dropped.**
- **Lowest version.** `models.required_version(document)` reports the lowest
  version that can represent a document exactly.
- **Cut-over.** Until P2 and P3 confirm 1.1.0 support, integration must either
  use the 1.0.0 export (which fails loudly on pages it cannot represent), or
  wait for that confirmation.

## Changelog

| Version | Change | Consumer impact |
|---|---|---|
| 1.0.0 | Initial proposed contract | P2 and P3 to review |
| 1.1.0 | Five new quality flags, uncertain table candidates, page status and warnings, required ids, parent on the same page | Backward-compatible only; 1.0.0-only readers reject 1.1.0. **Approval pending** (see the change request). |
