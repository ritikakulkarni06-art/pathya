# Backend verification

Run `python -m scripts.check` (or `make check`) for lint, format, strict application types, pytest and the database coverage gate. Tests use isolated SQLite databases, synthetic English/Hindi content and fake adapters; live provider keys are not needed.

Coverage includes authorization, immutable migrations/history, bounded uploads/storage, worker lease races/crash recovery, revision conflicts/rollback, stale derivatives and verified manifests. Later stages extend the suite with speech, retrieval, grounded answers and deletion. See docs/IMPLEMENTATION_STATUS.md for recorded checkpoint results.
