# Implementation status

Work follows P1-P16 in docs/PLAYBOOK.md. Only passing stages are committed. Nothing here establishes production readiness or measured project accuracy.

Next manual gate: approve the extraction/speech/identifier contracts with teammates. The user authorized deferring teammate approval on 16 November 2026; continue against the draft contract and reconcile before real adapter integration.

- P1 complete: lint, strict types, 8 tests and live localhost health check passed.
- P2 implemented: transactional migrations, immutable history, FTS triggers and aggregate reads; 18 tests passed; app/db coverage 96% (target >=85%).

- P3 complete: 33 tests passed, including bounded streaming, path escape rejection, deduplication, permissions, idempotent physical deletion and rollback after file publication failure.

- P4 complete: 64 tests passed, including the role matrix, full route audit, real Argon2id login/logout, secure cookies, CSRF, expiry/revocation and safe unexpected errors.

- P5 complete: 84 tests passed; strict types/lint/format passed; database coverage 96%; JSON Schemas and OpenAPI deterministic/current. User deferred teammate approval; continue P6 with draft v1.0.0. Linux namespace execution still needs host smoke-testing.

- P6 complete: 98 tests passed; strict types/lint/format passed; DB coverage 95%. Upload, listing and metadata APIs include rights notes, magic/type checks, PDF/password/page/pixel limits, source deduplication, private storage, metadata-free working images and request-body limits.

- P7 complete: 104-test full regression passed with 96% database coverage; a subsequent cancellation-race guard passed its targeted test plus lint/type checks. Durable claims, leases, heartbeat, visible retries, cancellation, process timeout and real crash/restart are implemented. P8 full checks will include the new guard.

- P8 complete: 120 tests passed with 97% app/db coverage, lint, formatting, strict types and deterministic contracts. Atomic corrections/conflicts, split/merge history, dependency invalidation, text-fallback rebuilds, immutable verified manifests, content/review routes and separate re-extraction candidates are implemented.

- P9 implemented: 128-test completed run recorded no failures in the pytest cache; database coverage 97%. Speech provider/segmenter boundaries, scoped aliases and personal audio, immutable sentence manifests, range downloads, cache invalidation and bounded offline package plans. The terminal completion output was lost at a context handoff; the cached test list/failure state and saved coverage were rechecked. No paid or real voice calls were made.

- P10 complete: 151 tests passed; lint, formatting and strict types passed; database coverage 97%. Current eligible evidence is chunked with structured context and source offsets, indexed with FTS5/Hindi trigrams, and ranked within document/access/revision filters. Optional local E5 and deterministic fake-vector paths are separate. Neighbor IDs respect block scope; the API revision and results use one snapshot. Tests required execution outside the restricted Windows sandbox because pytest temp-directory permissions prevented setup there. Actual E5 and native Hindi review remain manual.

- P11 complete: 172 tests passed with lint, formatting, strict types and 97% database coverage. Disabled/scripted/Gemini adapters, strict excerpt payloads, bounded explicit transient retries, durable per-attempt reservations, Decimal micro-INR costs, independent lifetime global/document caps and admin usage totals are implemented. Real providers remain disabled; no live call was made. Prices/model/terms and live smoke testing are manual. P10 was published to person-3 after explicit user approval; P11 remains local.

- P12 complete: 200 tests passed; lint, formatting, strict types and 97% database coverage passed. Questions return validated claim citations or explicit abstentions with source cards. Strict schema, current supplied citations, exact quotations, heuristic number/unit/negation checks, conservative conflicting-evidence signals, prompt-injection fixtures, private historical answers and concurrent-correction rechecks are implemented. No real model quality or entailment claim is made. See GROUNDING.md.

- P13 complete: 215 tests passed; lint, formatting, strict types and 97% database coverage passed. Owner deletion immediately revokes reads and tracks resumable file/history/index/answer purge through private receipts; immutable deletion needs a transaction-scoped guard. Owner manifests return 410/purge instructions. Daily retention and backup pruning, bounded retention extension, consistent backup/restore and upload/deletion race protection are implemented. Restored sessions are cleared. Policy approval, backup deletion reconciliation and a fresh-machine restore drill remain manual; no forensic erasure guarantee is made.

- P14 complete: 232 tests passed; lint, formatting, strict types and 97% database coverage passed. Per-user/IP action windows, transactional page quota/upload-allocation caps, configurable JSON byte limits, safe startup errors, admin jobs/storage/usage/observed timing metrics, and post-authorization write rechecks are implemented. Offline synthetic demo seed/reset and single-API/single-worker launch scripts are included. No live adapters were called. SECURITY.md explicitly retains manual assessment, vulnerability audit, host/TLS checks and limitations.
