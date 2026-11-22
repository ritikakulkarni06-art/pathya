# Contract approvals

Extraction contract v1.0.0: **pending**.
Speech and sentence-unit contract: **pending**.
Block identifiers, page labels and coordinate rules: **pending teammate review**.

Record only actual written feedback here (reviewer, date, version and approval/changes). No teammate has been contacted or represented as having approved this contract by the implementation agent.

## User-authorized deferral ? 16 November 2026

The user asked to defer teammate review because Person 1 is not working today. Proceed with P6 onwards against draft v1.0.0 and the synthetic adapter. This is permission to continue implementation, not Person 1's approval. Review and reconcile the contract before connecting the real extraction/speech modules.

## Tharun's integration feedback

Tharun's two written replies were relayed by the project owner on 19 November 2026.
Tharun selected the Person 1 `Document` v1.1.0 payload as the producer boundary
and identified `contract/pathya_content.schema.json` at commit
`39331e4291d2af6b68654dead2e9e8b9595de32f`. The pinned alias and versioned schema
have identical Git blob IDs. Backend access control, revision commits, invalidation
and persistent ID mapping remain under Person 3.

- Producer UUID4s identify entities within an extraction. They carry no identity
  guarantee across independent reruns. Re-extraction outputs remain candidates.
- Preserve the zero-based physical page index, nullable printed label, displayed
  normalized boxes, transform back to source coordinates, page outcomes and warnings.
- Preserve all producer quality flags. Treat uncertain reading order, math, table
  structure and missing geometry as review conditions. Exclude pages marked
  `needs_ocr`, `partial` or `failed` from trusted evidence while unresolved.
- Tharun supports the proposed `critical_symbol_uncertain` flag for ambiguous signs,
  decimal points, exponents and units that can change meaning. It is pending a
  finalized producer schema and conformance vectors. Once versioned, preserve the
  producer flag and derive the backend `critical_flag` from it.
- Tharun confirmed the image and PDF-page OCR functions. The pinned branch
  documents the full extraction pipeline as unfinished.

The final shared approval remains pending. Open points include heading level,
header/footer/footnote roles, pipeline review status, correction scope for block
type and reading order, the content API response and speech segmentation.

## Atul's integration feedback

Atul's written reply was relayed by the project owner. The reader snapshot
is `54493ac9966a7f6655c82f3fd9be45e3ba9edc0d`. Sign-in through
`/auth/*` with cookies and the CSRF header was tested against Atul's mock.
Atul plans to push it for a real backend check.

- Atul wants one content response for the reader and offline cache, with a
  P1 v1.1.0 Document, backend revision and optional prepared audio.
- Keep source language `en`, `hi`, `mul` or `und`. Atul proposes a separate
  optional `voice_language` of `en` or `hi` and will retain both fields.
- Preserve table and cell data, including indexes, spans and header flags.
  The reader derives associations and warns on uncertain tables. Merged
  cells in the row-header column are still unsupported.
- The current reader splits sentences in TypeScript and uses browser device
  voices. Atul has no Python segmenter or synthesis adapter. The reader can
  play optional prepared clips and keeps text readable on `clip_failed`.
- Atul prefers backend-published sentence ranges as the single source for
  highlighting and narration. The reader does not consume those ranges yet.
  Atul confirmed code-point offsets and can convert them to UTF-16 indices.
  The reader currently matches prepared clips by a short SHA-1 text key.

Atul's feedback establishes reader requirements. The exact versioned HTTP
envelope, stable backend ID mapping, revision rules for prepared clips and
end-to-end sign-in and reading checks remain open.

## Tharun's follow-up on the content response

Tharun supports returning the canonical P1 Document as the content response
body and backend-managed sentence ranges against `current_text`. Text
corrections must regenerate those ranges. He also confirmed that P1 will
add the proposed `critical_symbol_uncertain` producer flag, from which P3
will derive `critical_flag`.

P3 can support both decisions. The pinned v1.1.0 schema already carries
block revisions but rejects extra properties and has no fields for document
revision, sentence ranges, voice language or prepared audio. The proposed
next schema should explicitly define the metadata Atul needs for a single
live/offline response. Atul still needs to confirm the exact direct response
shape. Shared approval, the next schema pin and integration tests remain
pending.

## Tharun's confirmation of the current adapter target

Tharun confirmed that P3 should continue against P1 Document v1.1.0 at
`39331e4291d2af6b68654dead2e9e8b9595de32f` while P1 prepares its next
contract update. The three shared synthetic samples pass the pinned
producer schema and fail the current backend's direct adapter validation.
Use them to verify translation and field preservation.

Keep supported producer versions explicit at the adapter boundary so the
next agreed schema and its conformance cases can be added together.
Tharun will supply the verified full Document-producing entry point and
updated schema, version and fixtures. Joint conformance and live
integration verification are pending.

## Atul's confirmation of the next direct response

Atul confirmed that all three synthetic payloads open in the reader's
converter. He accepted the canonical Document as the direct content body
with next-version fields for document revision, per-block sentence ranges,
optional `voice_language`, and optional prepared audio entries
`{key, url, bytes}`. Each block needs a stable backend identifier and its
own revision. Keep the source `language` unchanged.

Atul confirmed start-inclusive, end-exclusive Unicode code-point offsets
into exact `current_text` before pronunciation substitutions. When present,
ranges cover all text without gaps and trailing whitespace belongs to the
preceding range. Only headings, paragraphs and list items need ranges.
The reader can use its existing splitter when ranges are absent and uses
built descriptions for tables, equations and figures. Preserve Atul's
clip lookup key within a revision-scoped package.

Atul agreed to the three conformance checks: direct Document response,
fresh offsets after a text correction, and exclusion of critically
uncertain content from trusted evidence. The final schema version and
commit, tests and live integration remain pending.

Atul pushed reader sign-in at `6142588116247f9bcc4d85c2aaca6ea3b07afd81`.
The four auth paths, request fields and cookie/header names match the P16
backend. An ASGI smoke test passed CORS preflight, registration, login,
authenticated session lookup, rejection of logout without CSRF, logout
with CSRF, and session revocation. The reader's browser flow still needs
verification. Serve the frontend and API through the same HTTPS origin
so the reader can access the API's host-scoped CSRF cookie.

## 21 November v1.2.0 handoff, recorded 22 November 2026

- **P1, Tharun.** Reported 514 strict tests passing, all 45 segmentation
  fixtures matching the P1 reference, and the frozen v1.0.0/v1.1.0 artifacts
  byte-identical. The v1.2.0 candidate, reference implementation, fixtures
  and P3 verification guide were reported as local.
- **P2, Atul.** Approves v1.2.0 provided `pathya-sentences/3` is the single
  pinned segmenter. Reader commit `a9fbda324498247c79449f00ea7e9b7049352bb2`
  implements heading ranks (null reads as level 2), skips page headers and
  footers, retains footnotes, and consumes bulk ranges by block ID after
  checking the chapter revision and per-block text hash. Atul reported clip
  identity as block ID, text SHA-256, sentence index and voice language.
  For `mul` and `und`, the reader retains the source tag and uses
  `integration.voice_language` when supplied, with a script-based fallback.
- **P2's policy position.** Display `unsupported_content` with a review
  marker and keep it out of trusted evidence until approved. The reader
  matches bulk results by block ID and can accept any response order.

Shared approval and pinning remain pending. Open items include P3 verification
against the 45 fixtures, end-to-end audio and reader compatibility, and joint
confirmation of the evidence trust rule and the bulk ordering guarantee.

The published P1 candidate at `9f0d4ccf6ab3b740a98401ee44e6e09daa24eea5`
contains `pathya-sentences/1`. P3 needs the later `/3` reference and fixture
bundle from Tharun's update. At P2 commit
`95b662e6263a702817f96402f86c39966bcd1f26`, prepared playback still computes
a short SHA-1 key from language and sentence text. The live chapter loader
reads content and sentence ranges. Verify P3 package ingestion and the
four-field clip key before recording audio interoperability as complete.
