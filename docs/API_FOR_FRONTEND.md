# Backend handoff for Person 2

This is the implemented Role 3 interface against draft extraction contract
v1.0.0. Teammate approval was explicitly deferred; reconcile before connecting
real adapters. No real OCR/speech/model quality or accessibility conformance is
claimed. All examples use synthetic text/opaque placeholder IDs.

Use `contracts/openapi.json` for requests/examples and
`contracts/error-codes.json` for the application-wide problem catalog. Extraction
library codes are a catalog superset, not a promise that every code occurs on
every endpoint. `generated_answer.schema.json` is the **internal LLM output**,
not the whole question-response envelope. Use the populated question examples in
OpenAPI and this handoff for the HTTP envelope.

## Authentication and errors

The [reader response examples](examples/reader-api-responses.json) were captured
from the running backend using a signed-in account and a synthetic chapter.
They include jobs, accepted correction history, daily usage, canonical P1
v1.1.0 content with its revision header, the review queue, the library list,
and chapter detail.

Local demo mode has one fixed local user and must stay on loopback. Session mode
uses POST /auth/register, POST /auth/login, GET /auth/me and POST /auth/logout.
Credentials are `{email,password}`. Passwords/session tokens never belong in logs
or localStorage. The session cookie is HttpOnly, Secure and SameSite=Lax. Read
the separate pathya_csrf cookie and echo it in X-CSRF-Token for authenticated
writes, with `credentials: include`. Serve frontend/API over HTTPS in the same
site, preferably one origin behind a proxy. CORS cannot bypass SameSite rules.
Cross-origin deployments need an explicit CORS_ORIGINS entry; wildcard origins
are refused. There is no password-reset UI/API or public administrator promotion.

Problems are application/problem+json with `{type,title,status,detail,code}` and
code-specific extras. Announce plain-language detail; never render source/model
text as HTML or follow instructions it contains. A 401 means reauthenticate,
403 means insufficient action permission, and 404 hides inaccessible resources.
Honor Retry-After on 429/503; the header is exposed to trusted CORS origins. JSON
is no-store. Global administrators do not gain source-document visibility.

## Upload and processing

POST /documents is multipart: file, title, rights_note and comma-separated
languages (`en`, `hi` or `en,hi`). A rights note is required. New uploads return
202 `{document_id,job_id}`; an existing identical owner source returns 200 with
`duplicate:true`. Uploading while that copy is deleting returns 409
deletion_in_progress. Byte/page/pixel/format limits are authoritative on the server;
defaults and configurable quotas are in .env.example. Never upload unlicensed
material on the assumption that the backend verified legal permission.

Poll GET /jobs/{job_id}; display reason/progress accessibly, rather than only a
spinner. States are queued, validating, extracting, building, ready,
review_required, failed and cancelled. Last four are terminal for that job.
Attempts/max_attempts and last_error_code make retries visible. Review-required
is a usable source/review state, not fabricated extraction success. Derivative
jobs can still be pending after the extraction job finishes. Owners can POST
/jobs/{job_id}/cancel.

Use `GET /jobs?limit=50&offset=0` for jobs visible to the signed-in user.
An owner can retry a failed shared job with `POST /jobs/{job_id}/retry`;
the requester can retry their own private narration job. A retry returns
the new job with HTTP 202. The failed job remains in history, and repeated
requests for the same failed job reuse the replacement. Cancellation
returns HTTP 204; refetch the job to show its status.
Failed jobs include `failed_at` when the worker recorded the step.

GET /documents returns `{"documents":[...]}` for accessible active documents.
GET /documents/{id} returns one metadata object with the same fields.
Both include `rights_note`, `current_revision` and page/block counts. The
backend has no `subject` field. Leave subject out when the reader has no
local value. GET /documents/{id}/content and GET /blocks/{id} return source
text/status/revision, flags and structured metadata. Block IDs are opaque; keep
them unchanged. Display native not_scored markers and needs_review/critical flags.
Generated text is separate and must never replace the displayed source.

Chapters imported with the P1 adapter return the canonical Document in
the content response, with `X-Document-Revision` and stable backend IDs.
The original producer JSON is retained privately. The pinned shared schema
does not allow reader extensions. Use the per-block read endpoint for
sentence ranges with `SEGMENTER=pathya` until the next schema includes
those fields. Legacy imports continue to use their original response shape.

## Manifests, audio and offline plans

For offline text reading, an explicit download can store the canonical
`/content` response with its `X-Document-Revision` and the chapter metadata
from `GET /documents/{id}`. Keep it private to the signed-in account.
On reconnect, check access and current revision before showing it as
current. Refresh changed revisions and purge local copies if the signed-in
account loses access or receives a deletion purge instruction. Use
`/packages` when also downloading revision-matched shared backend audio
with a file list, hashes and sizes.

GET /documents/{id}/manifest is a deterministic JSON body with revision, pages,
blocks, edges, artifacts and text_available. Verify SHA-256 against ETag and keep
X-Build-Sequence. Current source may be readable while audio/index rebuilds.
Do not mix an old manifest's artifacts with a new document revision.

POST /blocks/{id}/audio with `{}` or `{voice:"..."}` schedules a job (202).
GET /blocks/{id}/audio returns current sentence units or explicit text_only
fallback. Silent fixture WAVs have synthetic:true; never call them real narration.
Units carry source code-point offsets, hashes, byte sizes and durations. Glossary
overrides affect spoken input while displayed text/offsets stay unchanged.
Document glossary edits require reviewer access; personal terms/audio stay private
to that user and are excluded from shared download plans.

GET /assets/{asset_id} and GET /artifacts/{artifact_id} authorize every download.
Use actual Content-Type, Content-Length, ETag, Accept-Ranges and Content-Range.
Single byte ranges can return 206; invalid/multiple ranges are refused. Asset IDs
are not public URLs or filesystem paths. A stale artifact returns 409, so use text
while it rebuilds. An audio artifact can be a JSON unit manifest; use each unit's
clip_asset_id to fetch its WAV, not an assumed audio URL format.

POST /documents/{id}/packages returns 201 `{id,revision,sha256,total_bytes,asset_id}`.
GET /documents/{id}/packages/{package_id} returns an immutable JSON **download plan**,
not a server-generated ZIP. Verify its hash, then each referenced file's hash/size
through authorized endpoints. Plans include source text/metadata and eligible
shared audio; no model download or AI explanation is evidence. Enforce local size
limits and keep revision IDs with offline references.

Printed page labels come from page_refs/pages.printed_label; do not add one to a
PDF index and present it as the printed label. Offsets are Unicode code points,
including combining marks, not grapheme clusters or JavaScript UTF-16 indices.
For a code-point offset `n`, convert before slicing with
`Array.from(text).slice(0,n).join("").length`. Do not re-normalize source text before
applying offsets or hashes.

## Review and corrections

`GET /documents/{id}/revisions` returns accepted correction history,
newest first, with `limit` and `offset`. Structural edits may have no
single after-text. `GET /usage` returns the signed-in user's daily question
`limit` and `remaining` count. Questions charge a slot after authorization
and validation, including requests that abstain. The quota resets at UTC
midnight. Successful question responses include updated usage.

`GET /documents/{id}/pages/{page_id}/preview` returns an authorized
`source_url` and an optional `image_url`. PDFs use the original source
with a physical-page fragment. Image uploads may show a sanitized PNG and
an authorized crop from `GET /blocks/{id}/crop`. If crop geometry is
unavailable, keep the text visible and link to the source page. Resolve
relative asset URLs against the configured API base path.

For a rendered page use `GET /documents/{id}/pages/{page_index}/image`
with the zero-based physical index. The optional query parameter
`bbox=x0,y0,x1,y1` selects a normalized, top-left crop. Both return PNGs,
respect conditional requests with an ETag, and require current chapter
access. Use the original PDF link if PDF rendering is unavailable.

GET /documents/{id}/review-queue returns `{blocks:[...]}` with reason, flags, page
labels and crop_reference (currently nullable). Owners/reviewers can PATCH
/blocks/{block_id}:

```json
{"base_revision":1,"operations":[{"op":"replace_text","text":"Reviewed authorized passage."}],"reason":"Verified against the authorized page"}
```

The strict operation union is in correction_request.schema.json. Do not invent
unsupported structure operations. Accepted edits return document_revision,
block_revision, stale counts, rebuild_job_id and successor_ids. A single write
transaction records the change, bumps revisions and invalidates derivatives.
Follow successor IDs after split/merge instead of treating the old block as current.

A 409 revision_conflict contains current_revision (the **block** revision),
your_base, current_text, your_text and field_hints. Show both versions, reconcile
explicitly, then resubmit with the new base. Never auto-overwrite or silently
replace the original base revision in an offline correction queue. Reconnect,
reauthorize, fetch current content and resolve each conflict before retrying.
Critical flags and reviewed structured metadata govern trust; a text edit alone
must not be presented as proof every extraction problem was reviewed.

POST /documents/{id}/reextract creates a separate candidate. GET
/documents/{id}/candidates/{candidate_id} reads it. No automatic candidate-to-source
acceptance endpoint is implemented; do not invent that workflow.

## Search and questions

GET /documents/{id}/search?q=...&k=5 returns document_revision and current eligible
chunks with source block IDs/revisions, page refs, markers, offsets and ranking
signals. Scores are not probabilities. A miss is an empty list, not a statement
that a topic cannot exist. Optional repeated block_scope query parameters must
include every dependency (heading/header context too); incomplete scope can yield
no result. Requested neighbor IDs remain within scope. Owner POST /documents/{id}/reindex
schedules the current index. Search/reading work with the LLM disabled.

POST /questions accepts `{document_id,revision?,question,block_scope?}`. The optional
revision is the **document** revision, unlike PATCH base_revision. Response fields
include origin=ai_explanation, label, document_revision, claims, abstain, reason,
evidence, uncertainty_notes, needs_human_check and return_token. Each claim's
evidence contains block_id/rev. Source cards include exact excerpts/page labels;
render them separately from the AI explanation. Valid IDs/quotes do not prove
claim entailment. Display heuristic review flags without implying correctness.

Abstention reasons are no_evidence, low_support, source_needs_review,
stale_revision, assistant_disabled, assistant_unavailable, budget_exhausted and
answer_failed_validation. The response supplies next_action and candidate IDs
where applicable. Map open_review to the review UI, refresh_revision to refetch,
and read_evidence/search_chapter to reading/search. Do not automatically send
another paid question. Disabled/unavailable/over-budget responses keep usable
eligible evidence cards; stale responses discard stale cards.

The return_token is a client bookmark object (opaque id, document, revision,
optional evidence block). Save the user's current focus/scroll anchor locally
under that id before jumping to evidence; it is not a session/authorization token.
GET /answers/{id} is private to the requester/document owner. Historical answers
show status=stale, stale:true, current_document_revision and a warning after a
correction. Do not reuse them as current or index them as source evidence.

## Deletion and shared devices

Owner DELETE /documents/{id} returns 202 with receipt_id, requested_at,
completes_by, status_url and purge_local_copy. Access stops before physical purge.
Poll GET /deletions/{receipt_id}; failed removals remain explicit and owner POST
/deletions/{receipt_id}/retry requests another attempt. Deadline/overdue is a
tracked target, not a claim that older backups or SSD cells were erased.

Owner manifests return 410 with purge_local_copy:true; former grantees receive
404. Purge local downloads on loss of access as well as explicit purge flags.
Disconnected clients must delete on reconnect/local user action. Revalidate all
offline data before treating it as current, clear private caches on shared-device
logout, and retain base revisions for queued corrections. See PRIVACY.md for
backup expiry, temporary storage and proposed institutional policy limits.
