# Pathya - AI Textbook Reader

Pathya is an accessible English and Hindi textbook reader project. This repository contains the team plan and the **Role 3 backend** for authorized chapters, revision-safe reading and search, and evidence-linked study answers.

## Current implementation

The backend supports authenticated uploads, durable processing jobs, atomic corrections, revision-safe content and offline manifests, chapter-scoped search, grounded answers with extractive fallbacks, and tracked deletion. The [backend playbook](docs/PLAYBOOK.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md) describe each phase.

The extraction contract is **draft v1.0.0**, and real extraction and speech integration await teammate agreement. The local demo uses synthetic content and audio with the LLM disabled. Human evaluation and accessibility review are pending. See the [evaluation results](docs/EVALUATION.md) and [contract approvals](docs/CONTRACT_APPROVALS.md).

## Quick start - Python 3.12

```bash
python -m venv .venv
# Activate the virtual environment for your shell.
python -m pip install -r requirements.lock
python -m scripts.check
python -m scripts.demo
```

On Windows, use `.venv\Scripts\python.exe` directly or activate `.venv\Scripts\Activate.ps1`. The demo runs migrations, seeds a synthetic chapter, starts one API and one worker on loopback, and prints the chapter and manifest URLs. Press Ctrl+C to stop both. To verify startup and exit automatically, run `python -m scripts.demo --smoke --port 0`.

With GNU Make, use `make check`, `make demo`, `make demo-check` and `make openapi`. For session settings, backup and recovery, see the [runbook](docs/RUNBOOK.md). For requests, responses and errors, see the [exported OpenAPI contract](contracts/openapi.json).

## Team and branches

| Branch | Owner | Scope |
| --- | --- | --- |
| `main` | Shared | Integrated project baseline |
| `person-1` | Person 1 | Document AI, OCR, structured content |
| `person-2` | Person 2 | Accessible reader, speech, offline experience |
| `person-3` | Person 3 - Ritika | Backend, revision consistency, grounded AI |

Backend code uses `app/`, shared schemas use `contracts/`, and tests use `tests/`. Existing `document-ai/`, `frontend/` and `shared/` folders remain available for teammates. [CONTRIBUTING.md](CONTRIBUTING.md) describes the PR workflow. Only person-3 contains the implementation until a reviewed integration PR is merged.

## Documents and handoffs

- [Original project report](docs/Pathya_AI_Textbook_Reader_Project_Report.pdf) and [three-person role plan](docs/Pathya_Project_Idea_and_Three_Person_Roles.pdf)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md), [decisions](docs/DECISIONS.md), [dependency/license inventory](docs/DEPENDENCIES.md)
- [Extraction contract](docs/CONTRACTS.md), [Person 1 handoff](docs/HANDOFF_FOR_EXTRACTION.md), [pending approvals](docs/CONTRACT_APPROVALS.md)
- [Person 2 frontend handoff](docs/API_FOR_FRONTEND.md), [API error catalog](contracts/error-codes.json)
- [Manual steps needed now and later](docs/MANUAL_SETUP.md)
- [Team roles](docs/TEAM_ROLES.md), [proposed architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md)

Use authorized or synthetic content. Never commit .env, private source files, databases, generated audio, user data or API credentials. The included ten-page JSON chapter is entirely synthetic development data, not an evaluation result. A software license has not yet been selected; reports and third-party material retain their respective rights.
