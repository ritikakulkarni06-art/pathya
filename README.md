# Pathya — AI Textbook Reader

An accessible textbook reader proposed for students with visual impairment or dyslexia. Pathya will turn authorized English and Hindi textbook chapters into structured, page-linked content that students can read, listen to, correct, download, and ask questions about using textbook evidence.

**Status:** repository foundation only. Application features are planned and have not yet been implemented or validated.

## Project documents

- [Full project report](docs/Pathya_AI_Textbook_Reader_Project_Report.pdf)
- [Project idea and three-person roles](docs/Pathya_Project_Idea_and_Three_Person_Roles.pdf)
- [Team responsibilities](docs/TEAM_ROLES.md)
- [Proposed architecture](docs/ARCHITECTURE.md)
- [Development roadmap](docs/ROADMAP.md)

## Planned capabilities

- English/Hindi extraction with source-page links, reading order, and review flags.
- Accessible navigation, adjustable reading preferences, narration, and sentence focus.
- Corrections that update narration, search, and answer evidence consistently.
- Chapter-scoped, evidence-linked answers with clear abstention when support is missing.
- Explicit chapter downloads and offline reading/resume.

## Team and branches

| Branch | Owner | Scope |
| --- | --- | --- |
| `main` | Shared | Integrated project baseline |
| `person-1` | Person 1 | Document AI, OCR, structured content, extraction evaluation |
| `person-2` | Person 2 | Accessible reader, speech, offline experience |
| `person-3` | Person 3 — Ritika | Backend, revision consistency, grounded AI |

Use pull requests into `main` and request a teammate's review before merging. Git branch names use hyphens because spaces are unsupported.

## Repository layout

```text
backend/         Person 3: API, storage, jobs, revision handling, retrieval and AI
document-ai/     Person 1: extraction, layout, quality checks and content operations
frontend/        Person 2: reader, speech, accessibility and offline support
shared/          Shared contracts and integration examples
tests/           Future integration and system checks
docs/            Original reports and project guidance
.github/         Issue and pull request templates
```

## Getting started

```bash
git clone https://github.com/ritikakulkarni06-art/pathya.git
cd pathya
git switch person-3
```

Read the reports and agree on shared identifiers and revision contracts before implementation. See [CONTRIBUTING.md](CONTRIBUTING.md) for the team workflow. Module READMEs describe each work area; install/run commands will be added when runnable components exist.

The reports suggest React/TypeScript for the reader and Python/FastAPI, SQLite, private file storage, and a durable worker for backend development. These are proposed choices, not installed dependencies.

## Data and credentials

Commit only content the team has permission to share. Keep uploaded textbooks, private source files, personal data, credentials, databases, generated audio, and model artifacts outside version control. Store runtime configuration locally using `.env` and document variable names in `.env.example` when selected.

## License

A software license has not yet been selected. Publication of this repository does not grant an open-source license. Original reports and third-party content retain their respective rights.
