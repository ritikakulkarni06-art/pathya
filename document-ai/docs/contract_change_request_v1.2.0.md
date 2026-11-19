# Contract change request: P1 content contract 1.1.0 → 1.2.0

**Status: PROPOSED. Not approved by P1, P2 or P3.** This document asks for
review. Record actual written decisions only in the
[Approval record](#approval-record).

- **Branch:** `person-1` (Person 1's branch), code in `document-ai/`. Commit
  `39331e4`, the 1.1.0 integration baseline P3 pins, is imported as a subtree
  with its history, so it is an ancestor of `person-1`. Nothing is merged into
  `main`. An earlier draft on `feature/p1-contract-v1.2.0` is superseded by
  this branch and was left untouched.
- **Schema:** `contract/schemas/pathya_content.v1.2.0.schema.json`.
- **Conformance vectors:** `contract/conformance/v1.2.0/` holds 17 files: 16
  conformance documents plus `index.json`, with verdicts for the 1.0.0, 1.1.0
  and 1.2.0 schemas and for Python. The frozen 1.0.0/1.1.0 set in
  `contract/conformance/` holds 13 files: 12 documents plus `index.json`.

## Decisions already recorded in writing

These are from P3's `docs/CONTRACT_APPROVALS.md` (`person-3` at `2621fc9`),
relayed from Atul (P2) and Tharun (P1). 1.2.0 implements them:

| Decision | 1.2.0 |
|---|---|
| The canonical Document is the direct content response body | `extract_document(...).to_json()` returns the Document itself; there is no envelope |
| Next version adds a document revision | `Document.integration.document_revision` (P3) |
| Each block needs a stable backend identifier and its own revision | `Block.integration.backend_block_id` (P3); `Block.revision` already exists |
| Sentence ranges: start-inclusive, end-exclusive code points into the exact `current_text`, before pronunciation substitutions | `Block.integration.sentences` |
| Ranges cover all text without gaps; trailing whitespace belongs to the preceding range | Enforced by the Python validator; segmenter `pathya-sentences/2` |
| Only headings, paragraphs and list items need ranges | Ranges on any other block type are rejected |
| Optional `voice_language` (`en`/`hi`), keeping the source `language` | `Block.integration.voice_language` |
| Prepared audio entries `{key, url, bytes}` within a revision-scoped package | `Block.integration.audio[]` with `key`, `url`, `bytes`, plus `text_revision` and `text_sha256` |
| P1 emits `critical_symbol_uncertain`; P3 derives `critical_flag` | Flag plus `critical.critical_flag` and `critical.is_trusted_evidence` |
| Conformance checks: direct response, fresh offsets after a text correction, critically uncertain content excluded from trusted evidence | Covered by tests in `tests/unit/test_contract_v1_2.py` and `test_pipeline.py` |

## Answers to P3's reconciliation questions (`person-3`, c53dadc)

| P3 question | 1.2.0 answer |
|---|---|
| How does the adapter identify the producer family? | Required `contract_family: "pathya.p1.content"` plus `schema_version`. 1.0.0/1.1.0 documents carry no family field and are recognized by their version and P1 shape. |
| Which critical-symbol flags does P1 emit, and what must P3 withhold? | One flag: `critical_symbol_uncertain`. P3 derives `critical_flag` while it is present and the block is not `approved`. Withhold from trusted retrieval: those blocks; pages not `ok`; blocks that are `needs_review` or `rejected`; and `unsupported_content` or `block_type_uncertain` blocks until approved. Reference: `critical.is_trusted_evidence`. |
| How are PDF points, image pixels, rotation, crop and DPI carried? | Unchanged structured `transform`. `source_space` is `pdf_user_space` (points, CropBox ∩ MediaBox, clockwise `/Rotate`) or `image_pixels` (stored pixels, EXIF rotation, DPI from the file or null). Inverse mappings: `geometry.normalized_to_pdf_user_space` and `normalized_to_image_pixels`, tested at all four rotations. DPI is never invented. |
| Original `mul`/`und` tag and voice language | `Block.language` keeps `en`/`hi`/`mul`/`und`. The narration voice goes in `Block.integration.voice_language` (`en`/`hi`), owned by P2/P3. |

## What changes

| Change | Owner | Consumer impact |
|---|---|---|
| `contract_family` (required) | P1 | P3 checks it at the boundary |
| `heading_level` (1–6, headings only, nullable) | P1 | P2 can build heading navigation; null means unknown |
| `role` (body, page_header, page_footer, footnote; required) | P1 | P2 may skip headers and footers in narration; P3 may exclude them from answers |
| Pipeline review status (`needs_review` iff a review-trigger flag) | P1 | P3's review queue can rely on it |
| `critical_symbol_uncertain` flag | P1 | See above; must stay visible in P2 |
| `Document.integration` (document_revision, backend_document_id) | P3 | Producers leave it null |
| `Block.integration.sentences` (code-point ranges, revision and hash bound) | P3 (P1 helper) | P2 converts to UTF-16 for JavaScript |
| `Block.integration.voice_language` | P2/P3 | Narration voice, separate from `language` |
| `Block.integration.audio[]` (revision-bound references) | P3 | Stale audio makes the document invalid |
| Corrections `set_block_type` and `set_reading_order` | Proposed | P3 commits; P1 validates and applies (`apply_correction`) |

## Compatibility

- **1.0.0 and 1.1.0 are frozen.** The schemas, the 12 conformance documents and their `index.json`, the sample and
  the unversioned `contract/pathya_content.schema.json` (a 1.1.0 alias) are
  byte-identical to `39331e4`; tests pin their SHA-256.
- **Backward-compatible.** All existing payloads validate unchanged under the
  1.2.0 schema and Python, including the three valid 1.0.0/1.1.0 samples, and
  they upgrade losslessly.
- **Not forward-compatible.** The 1.1.0 schema rejects 1.2.0 documents.
- **For P3 while it integrates 1.1.0:** `extract_document(...).to_json("1.1.0",
  drop=("heading_level", "role"))` or `--target-version 1.1.0 --drop
  heading_level,role`. It fails loudly (exit 5) if the document contains
  critical flags, integration fields or new correction operations.

## Reconciliation with the latest written decisions (20 Nov 2026)

Checked against `person-3` at `2621fc9` (`docs/CONTRACT_APPROVALS.md`,
`docs/DECISIONS.md`, `app/services/sentences.py`, `app/config.py`) and
`person-2` at `6142588` (`frontend/src/lib/speech.ts`, `frontend/src/types.ts`).
There were no newer commits on either branch.

### Settled in writing and implemented as written

| Decision (source) | 1.2.0 |
|---|---|
| Canonical Document as the direct content body (P2, P3) | `ExtractionResult.to_json()` returns the Document itself |
| Document revision (P2) | `Document.integration.document_revision` (P3-owned) |
| Stable backend block identifier plus per-block revision (P2) | `Block.integration.backend_block_id` (P3-owned); `Block.revision` |
| Sentence ranges are start-inclusive, end-exclusive code points into the exact `current_text`, before pronunciation substitutions (P2; P1 follow-up) | `SentenceRange`, validated against the text hash |
| Ranges cover all text without gaps; trailing whitespace belongs to the preceding range (P2) | Enforced by Python; conformance vector `invalid_python_only_v1_2_0_sentence_gap` |
| Only headings, paragraphs and list items carry ranges (P2) | Enforced; vector `invalid_python_only_v1_2_0_sentences_on_caption` |
| Text corrections must regenerate ranges (P1 follow-up) | `apply_correction` removes them; `attach_sentences` regenerates them for the new revision |
| Optional `voice_language` `en`/`hi`, keeping the source `language` (P2) | `Block.integration.voice_language` |
| Prepared audio entries `{key, url, bytes}` (P2) | `AudioReference.key`, `.url`, `.bytes` |
| P1 emits `critical_symbol_uncertain`; P3 derives `critical_flag` (P1, P3) | Flag; `critical.critical_flag` |
| Exclude `needs_ocr`, `partial` and `failed` pages from trusted evidence (P1, P3) | `critical.is_trusted_evidence` |
| Treat uncertain reading order, math, table structure and missing geometry as review conditions (P1) | Pipeline review-trigger flags include `reading_order_uncertain`, `math_needs_review`, `table_structure_uncertain` and `missing_geometry`. **`reading_order_uncertain` was added in this reconciliation.** Consequence: documents built without layout (every line order-uncertain) come out entirely `needs_review`. |
| Producer UUIDs scoped to an extraction; P3 owns IDs, access, revisions, commits and invalidation (P1, P3) | Field ownership table; producers leave `integration` null (`producer_violations`) |
| Conformance checks: direct response, fresh offsets after a text correction, critical content excluded from trusted evidence (P2) | `tests/unit/test_pipeline.py`, `test_contract_v1_2.py` |

### Not settled: needs a written decision

1. **Which segmenter is canonical, and its identifier.**
   - **P1** ships `pathya-sentences/2` (`sentences.SEGMENTER`).
   - **P3** ships its own implementation (`SEGMENTER=pathya`, cache version
     `pathya-reader-v1`, `app/services/sentences.py`).
   - **Same:** both produce gap-free code-point ranges.
   - **Different:** they are separate code, and their abbreviation lists
     differ. Since this reconciliation, both keep a leading list marker
     ("1.", "iv.") with its item.
   - **What the contract fixes today:** `segmenter` is a free, non-empty
     string recording whichever segmenter produced the ranges; the coverage
     and binding rules apply to both.
   - **Decide:** one shared implementation, or keep both with their own
     identifiers?
2. **Where audio lives.**
   - **P1 1.2.0:** audio is per block (`Block.integration.audio[]`), bound to
     that block's `text_revision` and `text_sha256`.
   - **P2's reader package:** one list, `ChapterPackage.audio`, plus a
     package-level `audio_voice`.
   - **Written record:** says only "optional prepared audio entries
     `{key, url, bytes}`" within "a revision-scoped package".
   - **Decide:** per block (P1 now), per document, or both?
3. **Audio `key` format.**
   - **P2's reader computes** the first 16 hex characters of
     `SHA-1("<lang>|<sentence text>")` (`frontend/src/lib/speech.ts`). That is
     an implementation choice, not a recorded contract decision.
   - **P1's contract treats** `key` as an opaque, non-empty string, unique
     within a block.
   - **Decide:** should the contract fix this derivation, and what is
     `<lang>` for `mul`/`und` blocks?
4. **`audio_voice`** (P2's package-level voice name for prepared clips) has no
   contract field.
5. **Heading levels.** Ranking by glyph size across the document (P1 now), a
   Docling hierarchy, or null when unknown?
6. **Correction scope.**
   - Should `set_block_type` and `set_reading_order` be kept?
   - May a reorder cross pages? (Not allowed now.)
   - Should a review-status-only correction invalidate audio? (It does now,
     because the revision changes.)
   - Must every correction bump P3's `document_revision`? (P3's call.)
7. **Trust policy beyond critical symbols.** P1 also withholds
   `unsupported_content` and `block_type_uncertain` blocks until they are
   approved. The written record covers only critical-symbol uncertainty and
   page status.
8. **HTTP envelope and backend ID mapping** for the reader package (P2/P3
   scope, outside this producer contract).

## Approval record

| Reviewer | Role | Date | Version | Decision | Notes |
|---|---|---|---|---|---|
| — | P1 | — | 1.2.0 | **pending** | — |
| — | P2 | — | 1.2.0 | **pending** | — |
| — | P3 | — | 1.2.0 | **pending** | P3 is integrating 1.1.0 at `39331e4` |
