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
