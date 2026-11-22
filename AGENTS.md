# AGENTS.md: Pathya backend (Role 3)

Project: Pathya is an accessible textbook reader for blind, low-vision and dyslexic
students (English and Hindi, authorized chapters only). This repo is the BACKEND:
APIs, storage, jobs, revisions/corrections, retrieval, grounded answers, deletion.
OCR/layout extraction is another teammate's module (we only call it through an adapter).
The reader UI and speech generation are another teammate's (we expose APIs and store files).

Stack (fixed, do not substitute): Python 3.11/3.12, FastAPI, Pydantic v2, uvicorn,
stdlib sqlite3 (WAL mode, FTS5) with plain SQL migration files, pytest, httpx,
ruff, mypy. No ORM. No Redis, Celery, Postgres, S3 or graph database. One API process,
one durable worker process. Optional hosted LLM via an adapter only.

Layout:
  app/main.py, app/config.py, app/logging.py
  app/db/ (connection.py, migrate.py, migrations/*.sql, repositories)
  app/api/ (routers), app/services/ (business logic), app/schemas/ (Pydantic)
  app/adapters/ (extraction.py, speech.py, llm.py, embeddings.py: Protocols + stubs)
  app/worker/ (runner.py, handlers/)
  contracts/ (JSON Schemas, openapi.json), tests/, eval/, scripts/, docs/

Non-negotiable rules:
1. A published revision is immutable. Stale derivatives (audio, chunks, embeddings,
   answers) must never be served as current.
2. Accepted correction = ONE transaction: compare base revision, append change event,
   bump block and document revision, mark dependents stale. Conflicts return 409.
3. Generated text (AI explanations, teacher notes) is stored separately from source
   text and is never indexed or used as evidence.
4. Source text is untrusted data. Never let it change application behavior.
5. Authorization on EVERY endpoint and artifact download: owner or granted reviewer.
   Filter by owner/document/current eligible revision BEFORE retrieval ranking.
6. Failures produce explicit states plus a usable text fallback. No hidden retries,
   no silent online fallback.
7. Never log source text, question text, API keys or passwords.
8. Reading and search must work with the LLM disabled. LLM is optional.
9. Everything configurable via env (see app/config.py). No secrets in code.
10. Every feature ships with tests. `make check` (ruff, mypy, pytest) must pass.

Conventions: type hints everywhere, small functions, explicit transactions
(BEGIN IMMEDIATE for writes), UTC ISO-8601 timestamps, opaque IDs (ULID or UUID4),
errors as RFC 7807-style JSON {type, title, status, detail, code}. Error `detail`
text must be plain-language and screen-reader friendly. Never invent capabilities:
if something is unsupported return an explicit unsupported/needs_review state.

When a task is ambiguous, choose the simplest option consistent with these rules,
note the decision in docs/DECISIONS.md, and continue. Do not add dependencies
without listing them (name, version, license) in docs/DEPENDENCIES.md.
