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
