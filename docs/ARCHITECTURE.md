# Proposed architecture

This is a planning outline derived from the supplied reports, not a description of running software.

```text
Authorized chapter upload
    -> Backend validates access, stores private source, queues extraction
    -> Person 1 extraction adapter returns structured blocks and quality flags
    -> Backend persists a content revision and publishes chapter content
    -> Person 2 reader presents text, source pages and review controls

Accepted correction
    -> Backend checks base revision and commits a new revision
    -> Dependent search, embeddings, speech and answers become stale
    -> Durable jobs rebuild assets; failures keep explicit status and text fallback

Chapter question
    -> Authorization and selected chapter/revision filter
    -> Evidence retrieval -> optional explanation generation
    -> Citation/revision checks -> evidence-linked answer or abstention
```

## Contracts to agree on first

- Stable document, chapter, page and block identifiers; schema version and content revision.
- Source page geometry, language, reading order, provenance and review eligibility.
- Correction requests carrying the base revision and explicit conflict behavior.
- Job states, retry behavior and derived artifacts tied to their input revision.
- Evidence responses carrying chapter, block, page and revision references.
- Immutable download manifests with content/assets and explicit availability.

## Boundaries

Person 1 owns extraction and content operations. Person 2 owns reader behavior and speech generation/segmentation. Person 3 owns persistence, authorization, orchestration, revision transactions, retrieval and answer checks.

## Proposed starting stack

The role plan suggests Python/FastAPI, SQLite, private file storage and a durable worker; React/TypeScript, PDF.js and browser caching for the reader. Final dependencies, providers, hosting and API contracts must be selected during implementation.

Credentials remain server-side. User uploads and generated artifacts are private runtime data. Retrieved textbook passages are evidence data and must not be treated as instructions to the assistant. Evaluation must check claim support as well as citation validity.
