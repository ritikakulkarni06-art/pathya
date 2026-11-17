# Pathya - AI Textbook Reader

Pathya is a proposed accessible English/Hindi textbook reader. This repository contains the team plan and the **Role 3 backend foundation**. Students will eventually read, listen, correct content and inspect evidence-linked explanations.

## Current implementation

P1-P8 of the [backend playbook](docs/PLAYBOOK.md): FastAPI configuration/health/errors, content-safe logs, transactional SQLite migrations and immutable history, private file storage, local/session authentication, CSRF and document roles, versioned extraction schemas, adapters and atomic initial import; durable worker leases, cancellation/recovery; atomic corrections and conflicts; immutable manifests, review queues and separate re-extraction candidates.

The extraction contract is **draft v1.0.0**; the user authorized deferring teammate approval while implementation continues with fixtures. Speech adapters, the full retrieval index, grounded answers, packages and deletion workflows remain in P9-P16. LLM calls remain disabled. This is not a production-ready service or a measured accessibility/accuracy result.

## Quick start ? Python 3.12

```bash
python -m venv .venv
# Activate the virtual environment for your shell.
python -m pip install -r requirements.lock
python -m scripts.check
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

On this Windows checkout use `.venv\Scripts\python.exe` directly, or activate `.venv\Scripts\Activate.ps1`. `GET http://127.0.0.1:8000/healthz` and `/readyz` report service health. `GET /auth/me` shows the fixed local demo user. Public interactive API docs are disabled; inspect [the exported OpenAPI contract](contracts/openapi.json).

Local mode needs no secrets and binds only loopback. To customize, copy `.env.example` to `.env` and edit local values. Session mode requires a random secret of at least 32 characters and HTTPS because cookies are always Secure. Do not use local mode in production. Disable raw access logs as shown; they can contain query text.

On systems with GNU Make, `make check`, `make dev`, `make contracts` and `make openapi` are available. Windows equivalents are `python -m scripts.check` and `python -m scripts.export_contracts`. Run the durable worker in a second terminal with `python -m app.worker`.

## Team and branches

| Branch | Owner | Scope |
| --- | --- | --- |
| `main` | Shared | Integrated project baseline |
| `person-1` | Person 1 | Document AI, OCR, structured content |
| `person-2` | Person 2 | Accessible reader, speech, offline experience |
| `person-3` | Person 3 ? Ritika | Backend, revision consistency, grounded AI |

Backend code uses `app/`, shared schemas use `contracts/`, and tests use `tests/`. Existing `document-ai/`, `frontend/` and `shared/` folders remain available for teammates. [CONTRIBUTING.md](CONTRIBUTING.md) describes the PR workflow. Only person-3 contains the implementation until a reviewed integration PR is merged.

## Documents and handoffs

- [Original project report](docs/Pathya_AI_Textbook_Reader_Project_Report.pdf) and [three-person role plan](docs/Pathya_Project_Idea_and_Three_Person_Roles.pdf)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md), [decisions](docs/DECISIONS.md), [dependency/license inventory](docs/DEPENDENCIES.md)
- [Extraction contract](docs/CONTRACTS.md), [Person 1 handoff](docs/HANDOFF_FOR_EXTRACTION.md), [pending approvals](docs/CONTRACT_APPROVALS.md)
- [Manual steps needed now and later](docs/MANUAL_SETUP.md)
- [Team roles](docs/TEAM_ROLES.md), [proposed architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md)

Use authorized or synthetic content. Never commit .env, private source files, databases, generated audio, user data or API credentials. The included ten-page JSON chapter is entirely synthetic development data, not an evaluation result. A software license has not yet been selected; reports and third-party material retain their respective rights.
