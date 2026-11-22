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
- **P2's policy confirmation.** Atul confirmed that `unsupported_content`
  stays visible with a review marker and stays out of trusted evidence until
  reviewer approval. Bulk responses are matched by `block_id` with no order
  guarantee.

Tharun confirmed both rules in his follow-up. Keep `unsupported_content`
visible with a review marker and exclude it from trusted evidence until a
reviewer approves it. Match bulk sentence ranges by `block_id`. Reading order
is available for debugging and carries no contract guarantee.

Tharun shared the reconciled candidate bundle from his `person-1` working tree
at base commit `fd361526fe077b3c9cf3cc8a0436b0766bf50037`. P3's previous
segmenter matched 31 of 45 fixtures. The `pathya-sentences/3` port matched all
45 in the P3 reader range and built-in speech code, including expected
code-point and UTF-16 offsets and text and sentence hashes. Shared approval
and pinning remain pending.

Atul reported the prepared-audio implementation and passing local
`npm run test:p1` checks at P2 commit
`568d572caf7c0316be9ca1113e7fe7c2e7d52579`. The reader loads audio from a
chapter manifest matching the content revision and keys clips by block ID,
text SHA-256, sentence index and voice language. It skips synthetic clips.
Manifest-based downloads are suitable for the live interoperability check.

P3 sends the resolved `en` or `hi` in audio `language` and retains the
original `mul` or `und` in content. Atul reported and pushed the matching P2
fallback in `3936525566fa49847eb1f41f0bf6bf69de983b9b`. The reader now picks
Hindi only when the Devanagari count exceeds the English count, with English
on a tie or when both are zero. The commit includes a test for these cases.

Atul supplied a reader build with `VITE_API_URL=/api` and shared a Piper
adapter and test chapter in `9460bdc54b441f4db36b4bf381f3bb1bb64b26f2`.
The supplied build passed a local same-origin ASGI check for static files,
API routing, session cookies and CSRF. P3 parsed the chapter as v1.1.0 and
resolved its `mul` list item to Hindi and its `und` paragraph to English.

P3 generated real Piper WAVs for both passages in an isolated local preview.
The API served the WAVs with matching hashes and `/3` offsets. A review-only
correction temporarily returned `manifest_pending`, kept the original audio
assets available and reused them in the newly published manifest.

Atul reported that the live reader played and downloaded the prepared English
clip for the `und` paragraph and the Hindi clip for the `mul` list item.
Both clip checksums matched. The first pending-manifest reconnect updated the
saved chapter from revision 1 to 2, but the reader discarded the saved clips.
Atul reported a fix in `d033981da81efc79e3fbe7e06e81b39e009911d6`. The
reader tests passed, and the preview served a build from that commit.
P3 published revision 2 with the same prepared audio asset IDs and hashes.
Atul reported that reconnect while revision 3 was pending refreshed the
review state, retained both saved clips and requested no clip downloads in
the captured repeat run. P3 published the revision 3 manifest and verified
that both clip IDs and hashes match revision 2.

## Live prepared-audio interoperability, 23 November 2026

Atul confirmed all three joint checks passed on the live HTTPS preview with
P2 commit `d033981da81efc79e3fbe7e06e81b39e009911d6` and P3's
`pathya-sentences/3` implementation at `82841efb63f587c7ba35b58b49b14ae91a621796`.
The reader found both prepared clips
with the four-field key and selected English for `und` and Hindi for `mul`.
Reconnect refreshed review state and retained both clips while the manifest
was pending. After publication, the saved chapter stayed at revision 3,
cleared `audio_pending` and kept both files. The reader requested the chapter
manifest and per-passage audio metadata, with no WAV requests in the
published-manifest check. Atul confirmed P2 is ready for final v1.2.0 approval
and pinning. The final shared approval and pin are still pending.
