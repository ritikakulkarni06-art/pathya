# Contract change request: P1 content contract 1.1.0 → 1.2.0

**Status: PROPOSED, not pinned or frozen. Final approval by P1, P2 and P3 is
pending.** Atul has given conditional P2 approval, subject to
`pathya-sentences/3` being the single pinned segmenter. Ritika reports P3
conformance of **45/45 fixtures** and **327 backend tests passed**. These
P3 results were reported to P1, not independently rerun by P1. The
individual decisions below were approved in writing (see
[Decision approvals](#decision-approvals-21-nov-2026)); the
[Approval record](#approval-record) for the contract as a whole is still open.

- **Branch:** `person-1` (Person 1's branch), code in `document-ai/`. Commit
  `39331e4`, the 1.1.0 integration baseline P3 pins, is imported as a subtree
  with its history. Nothing is merged into `main`.
- **Schema:** `contract/schemas/pathya_content.v1.2.0.schema.json`.
- **Conformance documents:** `contract/conformance/v1.2.0/` holds 12 files:
  11 documents plus `index.json`, with verdicts for the 1.0.0, 1.1.0 and
  1.2.0 schemas and for Python. The frozen 1.0.0/1.1.0 set in
  `contract/conformance/` holds 13 files: 12 documents plus `index.json`.
- **Segmentation fixtures:** `contract/segmentation/` holds the
  `pathya-sentences/3` fixtures (45 cases) and an example bulk response.
- **P3 verification:** [docs/p3_verification_guide.md](p3_verification_guide.md).

## Summary: 1.2.0 is a producer-only contract

The P1 Document is the canonical producer payload. It carries only what P1
extracts. Everything that depends on backend state is served by P3's API:

| Not in the Document | Served by P3 |
|---|---|
| Document revision | `X-Document-Revision` header on `/content` and `/sentence-ranges` |
| Backend IDs | P3 replaces every P1 UUID with its own ID in the served Document, so `block.id` *is* the stable backend ID |
| Sentence ranges | `GET /documents/{id}/sentence-ranges` (bulk, one request per document) and `GET /blocks/{id}` |
| Audio, voice, pronunciation | `GET /blocks/{id}/audio`, packages, glossary |

Compared with the earlier 1.2.0 draft (`fd36152`), this removes
`Document.integration`, `Block.integration` (backend block ID, sentence
ranges, `voice_language`, audio) and the structural correction operations
`set_block_type` and `set_reading_order`.

## Decision approvals (21 Nov 2026)

Written approvals from Atul (P2) and Ritika (P3), relayed by Tharun (P1) on
21 Nov 2026. Where the teammates' branches already show the decision, the
evidence is cited. Latest team updates (22 Nov 2026, relayed by P1) are
recorded below; final contract approval remains pending. Ritika reports
that both the trust rule and the bulk-response matching rule are recorded.

| # | Decision | Approved by | Evidence or teammate report | 1.2.0 implementation |
|---|---|---|---|---|
| 1 | The P1 Document is the canonical producer payload and the direct `/content` body; backend fields stay out of it | P2, P3 | P3 `app/services/p1_content.py` serves the Document with P3 IDs; `docs/API_FOR_FRONTEND.md` | `integration` removed; vector `invalid_v1_2_0_backend_integration_fields` |
| 2 | Document revision travels in `X-Document-Revision` | P2, P3 | P3 `app/api/content.py`; P2 reads the header | No body field |
| 3 | Bulk sentence ranges: one request per document, with the revision and, for every current block, block ID, `text_sha256` (UTF-8 bytes of `current_text`), segmenter and code-point ranges with full coverage. Match by `block_id`; no ordering guarantee; reading order may be included for debugging | P2, P3 | P3 `14d9aee`: bulk route; Ritika reports the matching rule is recorded | Reference builder and checker: `sentences.document_sentence_ranges`, `check_sentence_ranges_response` |
| 4 | `pathya-sentences/3` is the single intended pinned segmenter, with list markers, Roman numerals, lettered items, Devanagari numerals, `pp. Ch. Vol. figs. cf.` and `« »` | P2, P3 | P3 `docs/DECISIONS.md` (`14d9aee`): adopt `/3` once reference rules and fixtures are available; P2 approval is conditional on `/3` being the single pin | `sentences.py`; 45 fixtures with offsets and hashes; Ritika reports 45/45 P3 conformance (not independently rerun by P1); final joint approval and pinning pending |
| 5 | Audio is reused while text, language, voice, pronunciation settings and segmenter are unchanged; a review-only edit bumps revisions but does not by itself invalidate audio; chapter metadata refreshes and access is revalidated on reconnect | P2, P3 | Ritika reports review-only cache preservation is complete locally; her latest reported backend result is 327 tests passed (not independently rerun by P1); clips and offline packages are preserved, while text corrections still invalidate affected clips and packages | Documented; the Document has no audio fields; prepared-audio interoperability remains pending |
| 6 | Trust: `unsupported_content` stays visible with a review marker and is excluded until reviewer approval; after approval it is eligible subject to other trust conditions. `block_type_uncertain` stays out until the type is verified | P2, P3 | Confirmed rule relayed by P1; Ritika reports it is recorded | `critical.is_trusted_evidence`; approval preserves flags and markers |
| 7 | Three P1 correction operations: `replace_text`, `set_language`, `mark_reviewed` | P2, P3 | P3 `app/services/revisions.py` allows exactly these for P1 chapters | History records `mark_reviewed` as `set_review_status: approved` (as P3 already does); structural operations removed |
| 8 | Heading level: P1 supplies one when reliably determinable, otherwise leaves it null; P2 treats null as level 2 | P2, P3 | Atul reports heading support complete (`a9fbda3`): level 1 remains level 1; level 2, deeper levels and null are read as level 2 | A level is set only when the document has at least two distinct heading sizes |
| 9 | v1.0.0 and v1.1.0 artifacts stay byte-identical | P1, P3 | P3 pins `39331e4` | SHA-256 pinned in `tests/unit/test_contract_v1_2.py` |

Earlier written decisions that still hold: `critical_symbol_uncertain` from
P1 with `critical_flag` derived by P3; pages that are `needs_ocr`, `partial` or
`failed` excluded from trusted evidence; uncertain reading order, math, table
structure and missing geometry as review conditions; code-point offsets into
the exact `current_text`, start-inclusive, end-exclusive, covering all text,
trailing whitespace with the preceding sentence, only headings, paragraphs and
list items split.

## What changes from 1.1.0

| Change | Owner | Consumer impact |
|---|---|---|
| `contract_family: "pathya.p1.content"` (required) | P1 | P3 checks it at the boundary |
| `heading_level` (1–6, headings only, nullable) | P1 | Null means unspecified; P2 shows it as level 2 |
| `role` (`body`, `page_header`, `page_footer`, `footnote`; required) | P1 | P2 may skip headers and footers in narration; P3 may exclude them from answers |
| Pipeline review status (`needs_review` iff a review-trigger flag) | P1 | P3's review queue can rely on it |
| `critical_symbol_uncertain` flag | P1 | P3 derives `critical_flag`; must stay visible in P2 |

Unchanged from 1.1.0: correction history operations (`replace_text`,
`set_language`, `set_review_status`), every other field and rule.

## Field ownership (final proposal)

| Area | Owner |
|---|---|
| Document, pages, blocks, edges, raw and extracted text, block type, language, geometry, provenance, confidence, quality flags, first-pass review status, `heading_level`, `role`, contract version and family, schema, conformance documents, segmentation fixtures | **P1** |
| Trust rules (`is_trusted_evidence`, `critical_flag`) | **P1** defines, **P3** applies |
| Backend IDs, access, document and block revisions after import, committing corrections, human review status, correction history, sentence segmentation (running `pathya-sentences/3` and serving ranges), audio generation, storage, keys and validity, voices, glossary, packages | **P3** |
| Rendering, the `X-Document-Revision` header, code-point → UTF-16 conversion, local clip cache, voice choice, offline copies and reconnect revalidation, null heading level shown as level 2, warnings for flagged blocks | **P2** |

## Compatibility

- **1.0.0 and 1.1.0 are frozen.** The schemas, the 12 conformance documents
  and their `index.json`, the sample and the unversioned
  `contract/pathya_content.schema.json` (a 1.1.0 alias) are byte-identical to
  `39331e4`; tests pin their SHA-256.
- **Backward-compatible.** Existing payloads validate unchanged under the 1.2.0
  schema and Python, and upgrade losslessly.
- **Not forward-compatible.** The 1.1.0 schema rejects 1.2.0 documents.
- **Core CLI for 1.1.0 compatibility checks:** use `python -m
  pathya_document_ai extract` with `--target-version 1.1.0 --drop
  heading_level,role`. Loss of a critical-symbol flag fails loudly (exit 5).
- **Optional worker adapter is excluded:** `src/pathya_document_ai/p3_adapter.py`
  and `tests/unit/test_p3_adapter.py` are excluded from the proposed 26-file
  core publication. Neither the adapter source nor its 12 tests is available
  in that publication. Do not configure or import the adapter from the core
  package. Separately review and publish the adapter and its tests, verify
  the worker interface and version/loss behavior, and run those tests plus
  worker integration checks before enabling it. See the guide's optional
  adapter integration section.

## Verification record and publication scope

The completed P1 pre-publication review recorded these results for the
selected core scope; the suites were not rerun for this documentation-only
update. P3 results are separate teammate reports, not independent P1 runs.

| Check | Recorded result | Scope / attribution |
|---|---|---|
| Selected P1 unit tests | 479 passed | Excludes `test_p3_adapter.py` and its 12 tests; do not use the earlier 491-test working-copy total for core publication |
| Strict P1 integration | 29 passed | Real engines required; two Docling deprecation warnings, no skips |
| P1 segmentation fixtures | 45/45 passed | `pathya-sentences/3` reference checks |
| Conformance freshness | 25 files current | 13 frozen baseline files + 12 candidate files, including indexes |
| Schema freshness | 4 files current | Check mode only; no regeneration |
| Frozen/reference files | All 19 match `39331e4` | 17 published inputs + two runtime schema copies |
| P3 conformance | Ritika reports 45/45 fixtures passed | Reported to P1; not independently rerun by P1 |
| P3 backend tests | Ritika reports 327 passed | Reported to P1; not part of the P1 unit total and not independently rerun by P1 |

## Remaining items

P3 conformance is now reported as 45/45 passed; it is no longer an
unreported fixture gate. `/3` remains the single intended pinned segmenter.
The following checks and approvals are still **pending**:

1. **Joint English/Hindi prepared-audio playback interoperability.** Verify
   `block_id` + `text_sha256` + `sentence_index` + `voice_language` in the
   relevant P2/P3 playback path, including replacement of the previously
   reported short SHA-1 lookup key. No completion has been reported.
2. **`mul`/`und` voice-selection verification** in that playback path.
3. **Reconnect after review-only changes**, including metadata refresh,
   access revalidation and preserved audio/offline packages. Local P3 cache
   preservation and the reported 327 tests do not establish this joint check.
4. **Final joint P1/P2/P3 approval** before 1.2.0 is finally pinned or frozen.
   Atul's conditional approval and Ritika's conformance/backend reports do
   not close the audio, voice or reconnect gates or constitute final joint
   approval.

The optional worker adapter also requires separate review, publication and
verification before use; its exclusion does not block the 26-file core.
The historical handoff ZIP remains an unchanged snapshot and predates this
approval/status update; do not overwrite it or describe its old docs as the
updated publication record.

## Approval record

The latest confirmations below were relayed to P1. The original approval
and verification dates were not supplied; no dates are inferred.

| Reviewer | Role | Date | Version | Decision | Notes |
|---|---|---|---|---|---|
| — | P1 | — | 1.2.0 | **Final approval pending** | Final joint P1/P2/P3 approval remains open |
| Atul | P2 | Not supplied | 1.2.0 | **Conditional approval reported** | Conditional on `pathya-sentences/3` being the single pinned segmenter; final joint approval and playback/voice/reconnect verification remain pending |
| Ritika | P3 | Not supplied | 1.2.0 | **Verification reported; final approval pending** | Reports 45/45 P3 conformance fixtures and 327 backend tests passed; P1 has not independently rerun P3; final joint approval remains pending |

The earlier individual decisions were approved in writing on 21 Nov 2026
(relayed); that decision record is distinct from final contract approval.
