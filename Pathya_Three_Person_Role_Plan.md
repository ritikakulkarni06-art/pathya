# Pathya: three-person implementation plan

Planning assumption: three students, 14 weeks, 12 hours per person per week. Each person has a proposed 168-hour allocation; the team has 504 hours. These are planning estimates, not measured effort. Rebalance weekly against actual work and blockers.

## Person 1: Document AI and content engineering

**Owns the transformation from a textbook page into reliable structured content.**

- Inspect native PDF text and preprocess page photographs.
- Integrate Tesseract English/Hindi and the selected Docling pipeline.
- Extract headings, paragraphs, reading order, page coordinates and language labels.
- Map parser output into the shared block schema; preserve original text and provenance.
- Implement quality flags and extraction checks, keeping engine scores separate from review status.
- Prepare simple table structures, reviewed MathML and reviewed figure descriptions.
- Implement the content-side effects of accepted corrections: corrected text, order, language and structure.
- Maintain the evaluation corpus, rights ledger and reference annotations.
- Measure OCR CER/WER, reading-order accuracy, component errors and review effort.

**Deliverable:** a versioned extraction adapter that returns structured blocks, source geometry, quality flags and clear unsupported-content states.

**Does not own:** correction forms, authorization, database transactions or cache invalidation. Person 2 owns the forms; Person 3 owns persistence and revision consistency.

| Work package | Hours |
|---|---:|
| Corpus, permissions ledger and reference annotations | 24 |
| Ingestion, preprocessing and parser comparison | 36 |
| Structured content, language and reading order | 28 |
| Quality flags and content correction logic | 24 |
| Bounded tables, equations and figures | 16 |
| Extraction evaluation, integration and documentation | 40 |
| **Total** | **168** |

## Person 2: Accessible reader, speech and offline experience

**Owns the complete student-facing reading experience.**

- Build the responsive reader using semantic HTML and accessible controls.
- Implement heading/page/paragraph navigation, bookmarks and reading-position recovery.
- Add independent font, size, spacing, color, focus, voice and speed controls.
- Implement the correction/review interface, including keyboard alternatives to visual actions.
- Build the speech adapter and sentence-to-audio manifest; integrate it into Person 3's worker interface.
- Implement sentence highlighting and the document/user pronunciation glossary.
- Render accessible tables, reviewed MathML and linked figure descriptions supplied by Person 1.
- Build source/evidence navigation and a reliable return-to-answer interaction.
- Implement explicit chapter downloads, browser caching and offline reading/search/bookmarks.
- Lead keyboard, NVDA, TalkBack, zoom/reflow and formative usability testing.

**Deliverable:** a student can independently find, read, inspect, report, download and resume a prepared chapter.

**Does not own:** inventing missing source structure, accepting revisions on the server or deciding whether answer evidence is trustworthy. It displays states supplied by the content/API contracts.

| Work package | Hours |
|---|---:|
| Reader shell, navigation and preferences | 36 |
| Speech, pronunciation and sentence synchronization | 28 |
| Review forms and evidence/source navigation | 24 |
| Offline packages, browser cache and resume | 28 |
| Accessibility and usability testing | 32 |
| Integration, repairs and documentation | 20 |
| **Total** | **168** |

## Person 3: Backend, revision consistency and grounded AI

**Owns the application services and the integrity of every derived artifact.**

- Build FastAPI endpoints, validation, access checks and private artifact delivery.
- Implement SQLite persistence, private file storage and durable background jobs.
- Coordinate shared schema contracts with Persons 1 and 2.
- Store correction history, enforce base-revision checks and handle conflicting edits.
- Invalidate and rebuild affected audio, search chunks, embeddings and answers after corrections.
- Publish consistent versioned manifests; prevent stale derivatives from appearing current.
- Build chapter-scoped retrieval and evidence cards, then optional grounded generation.
- Validate citation IDs/revisions and implement abstention for missing or unreliable evidence.
- Implement usage limits, cost accounting, deployment configuration, deletion and retention jobs.
- Lead API, authorization, stale-artifact, retrieval and answer-grounding tests.

**Deliverable:** a reliable API and worker pipeline in which reading, corrections and answers resolve to the correct authorized revision.

**Does not own:** writing every AI component. Person 1 owns extraction; Person 2 owns speech generation and interaction. Person 3 integrates those adapters through jobs.

| Work package | Hours |
|---|---:|
| API contracts, access control and validation | 28 |
| Database, file storage and durable jobs | 28 |
| Revision history, invalidation and synchronization | 32 |
| Retrieval, evidence cards and optional generation | 36 |
| Deployment, usage limits, privacy and deletion | 20 |
| Integration, evaluation and documentation | 24 |
| **Total** | **168** |

## Feature ownership and handoffs

Each feature has one accountable owner. Supporting work is specified so that corrections, audio and offline packages do not fall between roles.

| Feature | Accountable owner | Required support |
|---|---|---|
| OCR, layout and quality flags | Person 1 | Person 3 schedules jobs; Person 2 displays progress and review states. |
| Shared block schema | Person 3 | Person 1 defines extraction fields; Person 2 defines navigation/display requirements. All approve before implementation. |
| Correction workflow | Person 3 | Person 1 applies content operations; Person 2 builds accessible forms. |
| Reader and source navigation | Person 2 | Person 1 supplies source geometry; Person 3 serves authorized versioned content. |
| Speech and synchronization | Person 2 | Person 1 supplies segmented source text; Person 3 schedules generation and stores artifacts. |
| Offline reading | Person 2 | Person 3 publishes immutable manifests/assets; Person 1 supplies supported content structures. |
| Grounded answers and abstention | Person 3 | Person 1 supplies evidence eligibility; Person 2 presents citations and return navigation. |
| Extraction/STEM evaluation | Person 1 | Another person independently reviews reference annotations. |
| Accessibility and usability evaluation | Person 2 | All participate in sessions and fix barriers in their own components. |
| Security, consistency and Q&A evaluation | Person 3 | Person 1 reviews source support; Person 2 checks the interaction. |

The core handoff is: **Person 1 produces structured content; Person 3 stores and versions it; Person 2 makes it usable.** A correction travels from Person 2's form through Person 3's revision transaction to Person 1's content operation, then back through rebuilt artifacts to the reader.

## Shared 14-week schedule

| Weeks | Person 1 | Person 2 | Person 3 | Integration gate |
|---|---|---|---|---|
| 1-2 | Corpus and OCR/layout feasibility experiment | Accessible mock reader, user tasks and device/voice checks | Schema, mock API, jobs/storage skeleton | Agree on scope and contracts; expose feasibility failures early. |
| 3-4 | Extraction adapter and block/page mapping | Reader navigation against mock and real data | Upload/status/manifest API and durable jobs | One chapter imports and opens end to end. |
| 5-6 | Quality flags and correction operations | Review forms, speech adapter and highlighting | Revision transactions, conflicts and invalidation | One correction updates text and speech without stale output. |
| 7-8 | Simple tables and reviewed STEM assets | Offline download, restart and resume | Manifest publishing and secure asset delivery | Prepared chapter works after network loss and app restart. |
| 9-10 | Evidence quality and source eligibility checks | Citation opening/return and abstention UI | Retrieval, evidence cards and optional generation | Supported answer opens exact evidence; unsupported answer abstains. |
| 11-12 | Held-out extraction/STEM evaluation | Accessibility and formative user evaluation | Grounding, consistency, cost and failure testing | Freeze features and record actual results. |
| 13-14 | Fix content failures; explain extraction results | Fix interaction barriers; lead student workflow demo | Fix integration failures; package deployment | Reproducible demo, final report and release. |

## Coordination and release rules

- Review one working end-to-end chapter every week; do not wait until the end to integrate.
- Keep shared types and mock fixtures in the repository. Parser-specific fields must not leak directly into the UI.
- Require cross-review: Person 1 reviews Person 3's evidence behavior; Person 2 reviews Person 1's content usability; Person 3 reviews Person 2's version/cache handling.
- Every member writes their own method, results and limitations, with measured evidence. Person 2 coordinates report readability; Person 1 checks citations/permissions; Person 3 checks architecture/configuration consistency.
- Accessibility, correctness and privacy remain shared responsibilities. A lead coordinates a check; each person repairs failures in their component.
- If time becomes tight, cut automatic diagrams, automatic equation OCR, word timing and extra languages first. Cut generative prose next while keeping evidence retrieval. Preserve the reader, correction consistency, source links and offline restart.

## Individual demonstration ownership

1. **Person 1:** show the original page, extracted structure, uncertainty and before/after extraction metrics.
2. **Person 2:** complete keyboard/screen-reader navigation, sentence playback and offline restart.
3. **Person 3:** show correction propagation, revision-safe answers, source citations and abstention.

The team succeeds only when the complete workflow works. Equal planned hours are a starting point, not a promise of identical difficulty; move bounded tasks between members after weekly effort reviews.
