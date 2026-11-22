# Pathya contract reconciliation review - 18 November 2026

Status: **review proposal, not an agreed contract or teammate approval**.
The backend runtime and shared schemas have not been changed by this review.

## Evidence and scope

- P1: `fix/p1-pre-phase5-audit`, commit `39331e4291d2af6b68654dead2e9e8b9595de32f`.
- Published P3: `person-3`, commit `a2ebba5ec12397cc84ae0b2d33ea28510a8554ba`.
- Current local P3: `c1fd149ba54ab9c5193fa26364d521cfb84396c6`, with existing uncommitted work preserved.
- P2 reader: `person-2`, commit `346921aeb301e0b5629a8ed1f2a996cc1e1fc3a6`.
- P1 GitHub Actions run `44144339208`: Windows unit, Ubuntu unit and real Tesseract/Docling
  jobs all completed successfully. This establishes P1 CI success, not cross-branch compatibility
  or measured textbook accuracy.
- A Python 3.12 probe ran all 12 pinned P1 conformance vectors through both JSON Schemas and
  P1's semantic validator: **12/12 matched the expected outcomes**.
- The current local P3 schema rejected **all 3 valid P1 examples**, including P1 1.0.0, P1 1.1.0
  with page statuses/flags, and the uncertain-table example. P3's own legacy fixture still validates.
- Detailed observed verdicts, error locations and producer-file hashes are in
  `CONTRACT_COMPATIBILITY_20261118.json`. No OCR engine was rerun and no textbook data was used.

## Actual conflicts

| Area | P1 content contract | Current P3 extraction draft | Required resolution |
|---|---|---|---|
| Root/version | Document, source asset, languages, corrections; versions 1.0.0/1.1.0 | ExtractionResult with pages/blocks/edges/quality_flags/parser_versions; only 1.0.0 | Same version string currently names different formats. Identify the contract family as well as version; do not merely allow the 1.1.0 literal. |
| Field names | block_type, raw_text, current_text, reading_order, language, page_index, page_label | type, text_raw, text_current, order_key, lang, pdf_index_0, printed_label | Explicit boundary mapping, not field dropping. |
| Languages | en, hi, mul, und | en, hi | Preserve source tags. Voice selection is a separate P2 decision, not a rewrite of stored language. |
| Text | Nullable for figures, equations and tables | Strings required | Preserve null versus an empty string in schemas, persistence and APIs. |
| Tables | Counts, cells, row/column positions, spans, headers; uncertain null counts | Only a header-cell list | Persist the complete structure. Do not invent counts/cells or flatten away spans. |
| Page outcome | ok/blank/needs_ocr/partial/failed plus warnings | No page status/warnings | Persist and expose outcomes; incomplete/failed pages cannot enter trusted retrieval as complete pages. |
| Geometry | Structured transform to PDF points or image pixels, with crop/rotation/DPI | Six-number affine asserted to target original pixels | Preserve declared source space. Do not invent render DPI or reinterpret PDF points as pixels. |
| Page labels | Nullable printed label, separate physical index | Required nonempty printed label | Preserve unknown printed labels; any physical-page fallback must be labelled as such. |
| Confidence/review | Independent confidence origin/reason and review_status | Block status, confidence engine/flags, critical_flag | Keep scoring separate from human review. Unknown confidence must stay null. |
| STEM metadata | Independent origins/review states for MathML, fallback and figure descriptions | Flattened metadata with block-wide review status | Preserve the separate states/origins; unreviewed generated descriptions must not become trusted source evidence. |
| Identity/assets | UUIDs plus producer document/source-asset records | External local IDs mapped to backend UUIDs; asset access checked | Bind output to the uploaded source/hash. Producer IDs never grant ownership/access; map them explicitly. |
| Corrections | Content-only operations and applied history in Document | Backend transactions, revisions and dependency invalidation | Backend is the sole commit authority. Separate transport validity from permission to import historical revisions. |

## Recommended agreement

Use **P1's versioned content Document as the canonical producer payload**, because it represents
information the current backend draft cannot express. Keep backend storage/revision/API models
explicitly internal, rather than declaring two different payloads to be the same shared v1.0.0.
This is a recommendation for P1/P2/P3 agreement, not a unilateral schema switch.

1. Pin the agreed producer schema, semantic invariants and conformance vectors to a specific
   commit/hash. Support P1 1.0.0 only through its explicit, lossless version policy; reject unknown
   versions. JSON Schema alone is insufficient for cross-references and ordered boxes.
2. Add a lossless backend boundary and migrations: source language, nullable text/labels, typed
   table/STEM metadata, page outcome/warnings and structured transforms must survive import,
   storage, revision history, API responses and re-extraction. Preserve original producer
   provenance alongside the backend's authoritative revisions and opaque identifiers.
3. Bind the payload to the backend-owned document/source asset and source checksum. Never fetch
   arbitrary producer URIs or treat a producer document/user identifier as authorization.
4. Keep `critical_flag` and critical-symbol uncertainty semantics explicitly represented. Agree
   whether these become producer fields/flags in a revised draft or a reviewed backend policy.
   Do not map every uncertainty into a harmless display-only flag.
5. Exclude needs_ocr/partial/failed pages and uncertain/unsupported content from trusted evidence
   until an explicit authorized review transition. A fluent string or high OCR score is not an
   approval. Generated annotations remain separate from source and out of trusted evidence.
6. P1 may validate a proposed content correction; P3 alone authorizes and commits it in one
   transaction, checks the base revision, appends history, and invalidates dependent artifacts.
   Review/language/structure changes affecting output also need revision/dependency handling.
   Initial machine import must not silently trust supplied correction history or revision >1.
7. Re-extraction returns candidates for reconciliation. It cannot replace a corrected chapter
   through initial import or silently assign old identity based on text/position.

## P2 review findings

`frontend/src/lib/p1.ts` accepts version labels 1.0.0/1.1.0 and has a fallback for uncertain
tables. That is useful partial support, not full 1.1.0 conformance.

- Its P1 page type and conversion retain only id/index/label: page statuses and warnings are
  not propagated. P2 must distinguish failed/partial/needs-OCR pages from blank/complete pages.
- Mixed/unknown language tags are guessed by script to choose a voice. Keep the original tag
  as data and obtain P2's explicit narration policy rather than claiming an exact language label.
- Null printed labels become a physical page number. The UI must distinguish physical index
  from a known printed label.
- Table spans are converted to a simple grid and flagged; confirm the required accessible
  presentation rather than implying full merged-header semantics.
- The reader's chapter/package contract and P3's HTTP/manifest contract are a separate handoff.
  Agree those response mappings in addition to the extraction payload; passing producer-vector
  checks does not prove the reader and backend endpoints interoperate.

No P2 changes were made and P2 approval has not been represented as granted.

## P3 support statement

**Current code: not directly compatible.** P3 can implement the lossless migration above using
the existing FastAPI/Pydantic/SQLite stack, but cannot truthfully confirm completed support
before schema, persistence, import, retrieval and API tests pass against the agreed payload.
The unchanged legacy backend fixture passing is not evidence of support for P1 output.

## Acceptance gates before real integration

- P1 and P3 select the canonical family/version and resolve critical flags and source geometry.
- P2 confirms page failure display, warnings, null labels, uncertain tables and language policy.
- P3 implements migrations and round-trip tests proving no information loss, correct identity/
  asset binding, transaction-owned corrections and exclusion of unsafe pages from retrieval.
- Run all P1 positive/negative semantic conformance vectors in consumer CI, including the cases
  that intentionally pass JSON Schema but fail Python invariants.
- Add a cross-branch handoff test: actual producer fixture -> backend import/read API -> reader
  conversion, including null/mul/und, failed page, uncertain table, reviewed/generated STEM
  annotations, corrections, re-extraction and stale derivative rejection.
- Record actual written teammate replies with versions/commits. Keep approvals pending until
  those replies and corresponding integration evidence exist. Do not merge solely on green P1 CI.

This review does not begin P1 Phase 5, amend approved schemas, merge branches, approve peers,
publish changes or send a message to teammates. Existing local P3 source edits are preserved.

## Follow-up — 19 November 2026

The P1 audit branch still points to the reviewed commit, 39331e4. The pinned probe was
rerun against local P3 P16, 786fe47, after verifying all 18 producer file hashes.
All 12 vectors matched the expected P1 results,
and P3 directly accepted zero of the three valid samples. The legacy P3 fixture and
the P16 contract export freshness check passed. The machine-readable report records
this rerun under `p16_follow_up` and retains the original P3 snapshot. GitHub's
`person-3` branch still points to the published P10 snapshot, a2ebba5.

P2 commit [54493ac](https://github.com/ritikakulkarni06-art/pathya/commit/54493ac9966a7f6655c82f3fd9be45e3ba9edc0d)
supersedes the earlier reader snapshot. The reader now carries page status and
warnings, shows warnings in the page view, announces incomplete-page notices in
the narration flow, and marks physical-page fallbacks when printed labels are
missing. Stacked and spanning headers are converted to combined column labels.
The converter passed its nine built-in checks and accepted all three pinned P1
positive fixtures in Node. The three fixture checks exercise direct reader
conversion. The P3 import, read API and reader handoff remain pending.

P2 documents a script-based voice choice for mixed and unknown language. The
reader package still retains only the selected English or Hindi voice language,
so the handoff needs a field for the original language tag. The table grid still
uses derived labels in place of source spans and explicit header associations.
The converter prioritizes critical flags for review. P1 and P3 still need to
agree on a canonical producer representation for critical uncertainty and on
the coordinate contract. Written agreement and the shared end-to-end test
remain pending.

### Decisions for teammate review

| Reviewers | Decision to record |
|---|---|
| P1 and P3 | Confirm the producer contract family, supported versions and pinned commit. Specify how the adapter identifies the family. |
| P1 and P3 | Confirm which critical-symbol uncertainty flags P1 emits and which conditions require P3 to withhold a block or page from trusted retrieval. |
| P1 and P3 | Confirm how the adapter carries PDF points, image pixels, rotation, crop and DPI through to the reader. Include a fixture for each source coordinate space. |
| P2 and P3 | Confirm reader payload fields for the original `mul`/`und` tag, the selected voice language, and table spans and header associations. |

Once these decisions are recorded, use the same pinned producer fixtures for the
P3 import and read API checks and the P2 reader conversion. Include a negative
case that verifies incomplete pages and unresolved critical uncertainty stay
out of search and question evidence.

### Tharun's replies

Tharun selected the v1.1.0 `Document` at `39331e4` for the producer
boundary. At that commit, `contract/pathya_content.schema.json` and
`contract/schemas/pathya_content.v1.1.0.schema.json` have the same Git blob
ID, `2d84b927cdb49898e85bb4020351073601c32944`. The pinned OCR module
exports `ocr_image()` and `ocr_pdf_pages()`. The branch README describes
the complete extraction pipeline as unfinished. See `CONTRACT_APPROVALS.md`
for the confirmed identity and geometry rules and the remaining approval items.

For the reader-facing response, P3 proposes a versioned, lossless backend
representation with backend IDs and revisions authoritative for navigation,
corrections and downloads. Preserve producer provenance alongside nullable
labels and text, source languages, full table structure, page outcomes,
warnings, transforms and review/origin metadata. Any incompatible response
change should be explicitly versioned. Atul should review the response mapping.

For speech, P3 proposes that Atul's segmenter run within the backend speech
job and return Unicode code-point ranges into the exact current block text
before pronunciation substitutions. The reader consumes those published ranges
for highlighting, with conversion where browser indexing uses UTF-16.
Atul's confirmation is pending.

The current backend already exposes chapter content and manifests, block reads
and corrections, review queues, re-extraction candidates, audio, artifacts and
offline package routes. Compare those routes and response fields against the
reader's actual call sites before adding a route.

### Atul's reply and proposed API mapping

Atul prefers one response for live reading and offline caching. Keep the
P1 v1.1.0 Document in a `document` member and put the backend document ID,
revision, ID mapping, sentence ranges and optional audio beside it in a
versioned response. Atul can pass only `document` into his converter.
The mapping gives the UI stable backend block IDs and revisions for edits.
Serialize current corrected content and reconcile references in the same
revision snapshot. Compare the offline behavior against the existing
deletion and revision checks before switching the reader to this response.

Use `voice_language` as optional reader metadata. Preserve source language
and the complete producer table and cell data. Atul derives the headers and
will keep a visible limitation for merged row headers until they are supported.

Atul has no Python adapter. P3 proposes porting the tested reader sentence
rules to a backend segmenter and publishing start-inclusive, end-exclusive
Unicode code-point offsets into the exact current block text. Publish
sentence boundaries even when prepared clips are unavailable. Atul can use
device speech when selected and keep text readable if a clip fails.

If prepared clips are added, use the reader's text hash as a lookup key
inside an authorized revision-scoped package. Bind inclusion to the current
document and block revisions and voice/segmenter configuration. The reader
should also check the revision when reopening an offline copy after reconnecting.
Backend generation of real clips still requires a synthesis provider.

### Direct content response follow-up

Tharun confirmed a direct canonical Document response and backend-managed
sentence offsets. This supersedes the earlier P3 wrapper proposal for
`GET /documents/{id}/content`, subject to confirming the response fields
with Atul. Use stable backend IDs with consistent references in the
published view and retain original producer IDs in provenance or backend
storage. Verify that current corrected content and supported correction
history pass the shared semantic validator, including the effect of
backend split and merge operations on references.

Pinned v1.1.0 rejects undeclared fields. To keep a direct Document and give
Atul one response for online and offline, propose explicit optional reader
metadata in the next version. Confirm where document revision, per-block
sentence ranges, voice language and optional audio belong. Validate the
output against the newly pinned schema and test that a text correction
publishes fresh offsets and invalidates the old ranges and audio.

### Reader acceptance and route review

Atul accepted the direct response and proposed metadata fields. For the
next schema, propose using the existing block `id` and `revision` fields
for backend identity and revision in the published view. Keep producer IDs
in the import record. Sentence ranges apply to headings, paragraphs and
list items and cover all of `current_text` with no gaps. Keep whitespace
after a sentence in the preceding range. Use the reader's TypeScript
splitter and Atul's Hindi, decimal, abbreviation, numbered-list and quoted
speech cases as the reference when implementing the Python segmenter.
The reader may split locally if ranges are absent.

| Reader feature | P16 API coverage and open work |
|---|---|
| Job list and retry | Per-job status and owner cancellation exist. The job list is admin-only. Reader-scoped listing and general failed-job retry are absent. The frontend currently expects a job from cancellation, which returns HTTP 204. |
| Document correction history | Backend records correction history and exposes block edits. The reader's `GET /documents/{id}/revisions` is absent. Its `move` operation differs from the backend's anchor-based `reorder`. Align this with the agreed correction policy. |
| Daily question usage and limit | The question API enforces a request rate window. The reader's daily quota and `GET /usage` are absent. Agree the quota and reset behavior before wiring the screen. |
| Source preview | Authorized asset downloads exist. The review queue returns a null crop reference. Page image and crop delivery are absent. |
| Chapter content | Atul's pushed HTTP client calls `/manifest`. Switch it to the canonical `/content` response after the updated contract is implemented and verified. |

The backend now supports the pinned whole-document import through a
configured producer, canonical readback, and the reader routes in the
frontend handoff. Backend HTTP responses for all three pinned synthetic
fixtures opened in Atul's converter at `6142588` after import as fresh
chapters. A local same-origin HTTPS smoke test with the built reader at
`6142588` passed registration and login in Chrome. Its browser session
also passed authenticated lookup, missing-CSRF rejection and logout.
Shared schema extensions, the live extractor and Atul's browser
test against a deployed HTTPS preview remain pending.
