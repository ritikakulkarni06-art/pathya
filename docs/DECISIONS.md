# Backend decisions

- Follow the supplied playbook inside the existing Pathya repository on `person-3`; do not create a second repository. Backend packages use the requested root `app/` layout.
- Python 3.12, UUID4 identifiers, SQLite and plain SQL; no ORM or external queue.
- P1 readiness checks storage and DB reachability. Migration verification is added in P2.
- Windows without GNU Make uses `python -m scripts.check`, the same commands as `make check`.
- API docs endpoints are disabled until an authenticated documentation route is supplied; OpenAPI is exported offline.
- Worker execution deliberately refuses until P7, rather than claiming jobs were processed.
- No LLM, cloud call or embedding model is enabled or downloaded during P1?P5.
- Existing main/person branches and teammates' work areas are preserved.

- Supplied Uvicorn commands disable access logs to avoid raw question URLs; structured logs use route templates.

## P2

- FTS uses a normal, content-storing virtual table maintained by triggers: only current, eligible chunks are present. This avoids contentless-table deletion incompatibilities and permits stale rows to remain in `chunks` history. The additional private text copy is purged with the source rows.
- Migrations execute complete SQL statements inside one BEGIN IMMEDIATE transaction; executescript is avoided because it implicitly commits. Applied checksums and missing files are verified at startup and readiness.
- Published content/history and manifests reject mutation. P13 must add an explicit controlled purge mechanism that reconciles append-only history with physical deletion; ordinary request code cannot delete history.
- Aggregate repositories added for currently reachable reads; later aggregate writes will be added in the stage that implements them, using bound SQL parameters.

## P3

- Content-addressed files are published atomically using create-only hard links from same-filesystem temporary files. Existing sources are never overwritten. Local storage must support hard links; the NTFS development environment does.
- `secure_delete_document` means path-confined physical file removal, not guaranteed forensic erasure on SSDs or removal from external backups. P13 coordinates row purging and backup policy.
- Private storage directories must be writable only by the service account. Resolve-based checks defend traversal/symlinks; they do not protect against a malicious local administrator racing filesystem changes.
- File-store reads use owner/grant checks now, shared with the P4 API authorization dependency. Artifact HTTP routes and Range support remain scheduled for P8/P9.

## P4

- Local mode seeds one fixed demo user; routes still use ordinary owner/grant checks. Local mode refuses production startup and the supplied server binds loopback.
- Session authentication uses Argon2id password hashes and random 256-bit session tokens stored as SHA-256 digests. Secure cookies require HTTPS; integration tests use HTTPS URLs. Frontend deployments must configure TLS, not disable cookie security.
- A session-bound HMAC CSRF token must match the cookie and request header on authenticated writes. Public login/registration reject untrusted browser origins and have IP, email and pair limits.
- Login limits are bounded, in-memory and single-process; no distributed deployment claim is made. Public registration currently reveals that an account is unavailable (409); this is a conscious project usability tradeoff.
- Admin is an operations role only; it does not grant document visibility. Existing reader/reviewer permissions yield 403 for insufficient actions; invisible documents yield 404.
- Permission dependencies cover every current protected route. Future block/job/artifact/question routes must resolve their resource back to a document and use the same checks.

## P5

- Extraction v1.0.0 is a draft, pending written approval. Later stages will not be built against it until Person 1 confirms it.
- Adapter IDs are document-local stable identifiers. A transactionally persisted mapping assigns UUID4 backend IDs, preserving retry idempotency and cross-document separation.
- Migration 002 adds structured math/description/table metadata and import receipts/maps; no applied migration file was edited. Metadata is never silently dropped.
- Parent/reading-order uniqueness is per page and parent; page-local containers avoid ambiguous cross-page coordinates. This interpretation needs teammate approval.
- Initial import only publishes revision 1 and cannot overwrite existing content. It records review_required or building; actual derivative workers are a later stage.
- Subprocess mode fails closed on Windows or when unprivileged Linux namespaces are unavailable. The Linux child runs in a network namespace with rlimits and whole-group timeout termination; this requires a deployment-host smoke test. Trusted Python adapters are explicitly not sandboxed.
- JSON Schema structural validation and cross-reference validation are separate: both are tested. MathML accepts a small inert attribute-free subset only; arbitrary markup and external entities are rejected.
- Correction operation schemas are only descriptive drafts at P5; the strict discriminated operation union and HTTP correction workflow arrive at P8.

- `make install` installs the exact locked environment for source-checkout execution; it does not require an unpinned editable-build bootstrap. `make check` also enforces >=85% coverage of app/db.

- User override, 16 November 2026: teammate approval is deferred. Continue P6 onwards against the draft using fixtures; never represent this as actual teammate acceptance. Reconcile before connecting real adapters.

## P6

- Upload bodies are capped at ASGI receive time, including chunked bodies; multipart overhead has a separate 64 KiB allowance. Actual file bytes are also bounded during staging and source storage.
- Magic bytes must match a recognized filename extension when supplied. PDF inspection never fetches links. Parser diagnostics are suppressed because they may include private data; errors have fixed, accessible descriptions.
- Rights notes are required. The immutable original keeps its metadata; only a verified working PNG has metadata stripped. Sources are not silently rewritten.
- With no institutional project-end date supplied yet, retention is conservatively upload time plus RETENTION_DAYS_AFTER_END. Final policy/project-end configuration is deferred to P13 and institutional review.
- Failed uploads before job creation remove their temporary/source files and rows, or leave an explicit failed state if physical cleanup itself fails.

## P7

- Attempts count executions started (increment on atomic claim), not an extra increment on reaping. Lease expiry visibly records lease_expired, queues another attempt, and fails permanently at the configured maximum.
- The deployment worker is one parent process with at most one job child at a time. The parent heartbeats the SQLite lease and kills the child tree on timeout/cancellation. In-process execution is an integration-test helper, not the hard-timeout deployment path.
- Extraction is page-by-page and imported once in one transaction. IDs/mappings and import receipts make retries idempotent. Review-required extraction is a successful terminal review state, not failed processing.
- P7 build_audio/build_index handlers deliberately complete with an explicit unavailable-handler/text-fallback message and produce no pretend artifacts. P9/P10 replace them. Other unimplemented handlers fail visibly; delete is not exposed until P13.

- Tests clone a pristine migrated SQLite template via the SQLite backup API into separate per-test databases. Migration behavior is still tested on fresh databases; this reduces repeated schema setup without sharing mutable state. Crash tests explicitly expire the abandoned lease after killing the worker, rather than relying on a two-second wall-clock window under load.

## P8

- Corrections use an op-discriminated union, a single BEGIN IMMEDIATE transaction and append-only history. Conflicts commit a conflict record and return 409 without last-writer-wins behavior.
- Split/merge support adjacent leaf text blocks. Merge's optional with_base_revision protects the second passage; when omitted it defaults to the first passage's base. Complex structure is rejected explicitly.
- Current structural edges are materialized; immutable historical manifests preserve prior relationships. Split caption references follow successors. Table-header assignment is limited to complete rows with one header row.
- Candidate re-extraction is separate from published revisions and never automatically replaces accepted text. Acceptance needs a reconciled review workflow rather than an unsafe implicit publish.
- P8 supplies a minimal prose index and text-only speech fallback. Full chunking, multilingual ranking and speech adapters remain P9/P10.
- UTC timestamp helpers now live outside authentication, avoiding unnecessary FastAPI/Argon2 initialization in worker children. Current content/manifest reads take a consistent snapshot and recheck access.


### P9 speech boundary

Keep source offsets in Unicode code points, apply whole-word aliases without
changing displayed text, and keep personal audio private. Silent WAV clips are
explicitly synthetic. Unsupported voices return text_only; no online fallback
is attempted. Cache keys include source revision, engine, segmenter and relevant
glossary hashes. Immutable package manifests describe downloads rather than
producing a server-side ZIP. Paid providers fail closed pending verified pricing
and budget reservation support in P11.


### P10 evidence retrieval

Chunks aim at 150-350 approximate tokens, allowing shorter topic/page boundaries
and indivisible table associations. The estimate is words*1.3 plus Devanagari
code-points/2; it is not a model tokenizer. Long prose retains source offsets.
Reviewed figure descriptions and equation spoken fallbacks are source metadata;
generated explanations are excluded. Header, caption and heading revisions are
chunk dependencies. not_scored native text remains eligible and visibly marked.

FTS5 unicode61 may split Hindi combining marks poorly. An NFC character trigram
table provides an additional Hindi lexical signal. Scores use only the authorized
current candidate pool; global FTS BM25 statistics are deliberately avoided.
Optional vector ranking uses reciprocal-rank fusion (k=60). Hash vectors test
plumbing only. Native Hindi review and real recall measurement remain pending.

E5 uses local_files_only=True, trust_remote_code=False, CPU, exact query:/passage:
prefixes and float32 384-dimensional BLOBs. Inputs beyond 512 model tokens are
refused explicitly. No downloads occur at runtime. See the
[model card](https://huggingface.co/intfloat/multilingual-e5-small) and
[local loader API](https://sbert.net/docs/package_reference/sentence_transformer/model.html).

### P11 optional generation and budgeting

Use stateless Gemini generateContent through httpx, with no default model and no
real calls in tests. Strict excerpt-only payloads exclude application metadata.
The input bound counts UTF-8 bytes plus framing rather than inventing a model
tokenizer; oversize requests are refused without dropping evidence.

Global and per-document lifetime caps both default to zero. Each attempt makes a
durable worst-case reservation in usage_events before network I/O. Unknown costs
keep their reservation, including process crashes. Explicit 429/5xx responses
alone allow at most two retries; each retry is independently reserved and visible.
Timeouts are not retried. Placeholder/free/expired tariffs block paid calls.
No dependency is added. See docs/LLM_AND_BUDGET.md for accounting limits and the
manual price/model/provider checks.

### P12 grounded questions

Return exact eligible evidence cards when generation is disabled, unavailable,
over budget or fails validation. Navigation bookmarks are client state, not bearer
credentials. Saved explanations are private to their requester and document owner.
Use lexical overlap for abstention thresholds; RRF scores are not confidence.
Otherwise-identical sentences with differing numbers/negation are a conservative
conflict signal. All such checks are heuristics, not entailment proof.
Recheck document access/current revision in the answer write transaction after
generation, and discard stale claims/cards. Reviewed media evidence uses reviewed
source metadata. No generated text is indexed. See docs/GROUNDING.md.

### P13 deletion and backups

Immediate access revocation precedes physical removal. Owners retain a private
receipt while ordinary document routes deny access; owner manifests return a 410
purge flag and former grantees receive 404. History deletion requires a guard
inserted only for a deleting document inside the purge transaction. Guards do not
relax history updates and are removed before commit. Failed filesystem removal
keeps the receipt visibly failed and the document inaccessible until an explicit
retry or the worker's visible attempt policy succeeds.

Staging-file prefixes use a fixed SHA-256 of the document ID to prevent prefix
collisions. Keep only scrubbed document tombstones and content-free audit/cost
metadata. SQLite secure_delete and FTS rebuild support logical purge; no forensic
erasure claim is made. Consistent backups hold a write/publication lock, exclude
request temporaries, prune only marked confined snapshot children, and restore
only into a new nonoverlapping destination with sessions cleared. Old backups
require deletion reconciliation before access is restored. Policy numbers remain
proposals pending institutional review. No new dependency is added.

### P14 hardening and operations

Use bounded single-process request windows per action, user and IP. Reserve daily
page quota and allocated-upload slots in the same SQLite transaction as document
creation; duplicate uploads do not consume pages and deletion does not refund
quota. This allocation limit is not a connection-level DoS defense. Runtime config
loaders suppress Pydantic raw-input error reprs to prevent secret disclosure.
Grant/audio scheduling writes recheck authorization in their write transaction.
Admin metrics contain identifiers/counts only; stage timing is observed attempts,
not an assertion that killed processes recorded a final duration. No extra service
or dependency is added. Synthetic seed/reset scripts use only fixed local adapters.
