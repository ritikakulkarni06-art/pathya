# Contract change request: P1 content contract 1.0.0 → 1.1.0

**Status: PENDING. Not approved by P2 or P3.** This document asks for review.
It does not record any approval. Record actual written decisions in the
[Approval record](#approval-record) only.

## 0. Decide this first: there are two draft contracts

- **P1's contract** (this repository, `docs/p1_contract.md`, versions 1.0.0
  and 1.1.0).
- **P3's extraction contract** (draft "v1.0.0", `person-3` branch:
  `contracts/extraction_output.schema.json` and `docs/CONTRACTS.md`). It was
  written independently, and P3 is waiting for Person 1's written approval.

The two are **not wire-compatible**. Differences found by reading both schemas
(P3 branch at `69355cd`):

| Topic | P1 (1.1.0) | P3 draft (1.0.0) | Effect |
|---|---|---|---|
| Field names | `raw_text`, `current_text`, `block_type`, `reading_order`, `language`, `page_index`, `page_label` | `text_raw`, `text_current`, `type`, `order_key` (number), `lang`, `pdf_index_0`, `printed_label` | Mechanical rename |
| IDs | UUID (document-wide) | Local string `^[A-Za-z0-9_-]{1,128}$`; the backend maps them to UUIDs | P1 UUIDs fit P3's pattern |
| Languages | `en`, `hi`, `mul`, `und` | `en`, `hi` only | **Lossy:** mixed-language and unknown blocks cannot be expressed |
| Block text | Null allowed for figure, table and equation | `text_raw`/`text_current` required strings | Null would need to become `""`, losing the difference between "no text" and "empty" |
| Tables | `TableMeta` (row and column counts, cell ids) and `TableCellMeta` (row, column, spans, header flag) | Only `metadata.header_cell_ids` | **Lossy:** the table grid cannot be represented |
| Uncertain tables | Null counts plus `table_structure_uncertain` | Not represented | Needs a P3 flag |
| Equations and figures | Separate review status and origin for MathML, spoken fallback, alt text and long description | Single `metadata` strings; review follows block `status` | Partly lossy |
| Confidence | `{score, origin, reason}`, origin `not_available` gives a null score | `{engine, score, flags}`; block `status` `not_scored` | Mappable |
| Quality signals | `quality_flags` enum (15 values) | `confidence.flags` free strings, plus `critical_flag` | Vocabulary must be agreed |
| Page processing | `status` and `warnings` (1.1.0) | None | P3 cannot tell a failed page from a blank one |
| Transform | Crop box (PDF points) and rotation; normalized → PDF user space | 6-number affine, normalized → original **pixels** | Different target space |
| Document-level fields | `source_asset` (sha256, uri), `languages`, `corrections` | Not in the payload (backend-owned) | Fine; P3 owns these |

**Decision needed from P1 and P3:** which contract governs.
- **Option A:** P3 adopts P1's contract.
- **Option B:** P1 adds an adapter that emits P3's format. Tables, `mul`/`und`
  and page status would first need to be added to P3's schema, or the adapter
  is lossy.
- **Option C:** a merged contract.

P1 has not chosen. The audit fixes below apply to P1's contract either way.

## 1. What changes in P1's contract (1.0.0 → 1.1.0)

| # | Change | Kind |
|---|---|---|
| 1 | New `quality_flags`: `block_type_uncertain`, `missing_geometry`, `overlapping_regions`, `orphan_caption`, `duplicate_content` | New enum values |
| 2 | Uncertain table candidate: `TableMeta {row_count: null, column_count: null, cell_ids: []}` with the `table_structure_uncertain` flag | Nullable fields |
| 3 | `Page.status`: `ok`, `blank`, `needs_ocr`, `partial` or `failed`. Required in 1.1.0. | New required field (1.1.0) |
| 4 | `Page.warnings`: list of `{stage, code, message}` | New field |
| 5 | Every `id` required in serialized JSON (1.1.0 schema and Python) | Stricter validation |
| 6 | A child block must be on its parent's page | Stricter validation |
| 7 | `schema_version` is `"1.0.0"` or `"1.1.0"`; 1.0.0 documents are validated with 1.0.0 rules | Versioning |

## 2. Compatibility

- **Backward-compatible:** yes. Every valid 1.0.0 document validates under
  1.1.0, which the conformance vectors check.
- **Forward-compatible: no.** A 1.0.0-only consumer rejects 1.1.0 documents.
  Earlier documentation called 1.1.0 "purely additive"; that was inaccurate
  and has been corrected.
- **No silent downgrade:** `export_document_data(doc, "1.0.0")` either
  represents the document exactly (page status omitted, every page `ok`) or
  raises `IncompatibleVersionError`.
- **Artifacts:**
  - `contract/schemas/pathya_content.v1.0.0.schema.json`: frozen; rebuilt
    from the 1.0.0 rules because the original file was never committed
  - `contract/schemas/pathya_content.v1.1.0.schema.json`
  - `contract/conformance/` (12 vectors with expected verdicts)

## 3. Required consumer changes, if P1's contract is adopted

**P2 (frontend and speech):**
- Accept the five new flags and show them as "needs review".
- For a `table` block with no cells, show or read `raw_text` and mark the
  table structure as uncertain.
- Show page status. `needs_ocr`, `partial` and `failed` pages must not appear
  complete, and `failed` must not appear blank.
- Read text in `reading_order` within each page. Words inside each block are
  already in visual order (fixed before Phase 5).

**P3 (backend):**
- Store the new enum values, accept null table counts, and store page `status`
  and `warnings`.
- Validate input with the 1.1.0 schema **and** either the Python validator or
  equivalent rules (`x-pathya-invariants`). Run `contract/conformance/` in CI.
- Do not invent ids on import; missing ids are now an error.
- Exclude `needs_ocr`, `partial` and `failed` pages from trusted answer
  evidence until they are reviewed.

## 4. Questions for reviewers

1. Which contract governs (section 0)?
2. Is the page status vocabulary (`ok`, `blank`, `needs_ocr`, `partial`,
   `failed`) sufficient?
3. Should P3's `critical_flag` (for example `critical_minus_sign_uncertain`)
   become a P1 `quality_flags` value?
4. Is the 1.0.0 export with loud failure acceptable for a transition period,
   or will both sides move to 1.1.0 together?

## Approval record

| Reviewer | Role | Date | Version | Decision | Notes |
|---|---|---|---|---|---|
| — | P2 | — | 1.1.0 | **pending** | — |
| — | P3 | — | 1.1.0 | **pending** | P3's own draft also awaits P1's review |
