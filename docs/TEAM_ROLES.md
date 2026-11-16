# Three-person responsibilities

Based on the original [role plan](Pathya_Project_Idea_and_Three_Person_Roles.pdf). Responsibilities describe intended work.

## Person 1 — Document AI and content engineering

Branch: `person-1`. Primary folder: `document-ai/`.

Prepare PDFs/images; extract English/Hindi text and layout; preserve stable block IDs, page geometry, language and provenance; flag uncertain content; implement content repair operations; evaluate OCR, reading order and limited reviewed STEM content.

Deliver structured, page-linked textbook blocks to Person 3 and source geometry to Person 2.

## Person 2 — Accessible reader, speech and offline experience

Branch: `person-2`. Primary folder: `frontend/`.

Build navigation, bookmarks, reading preferences, correction forms and evidence interactions. Own speech generation, sentence segmentation, highlighting, pronunciation overrides, chapter downloads and offline resume. Lead keyboard, screen-reader and usability checks.

Consume Person 3's versioned APIs and Person 1's structured content. Person 3 schedules speech jobs and stores the resulting assets.

## Person 3 — Backend, revision consistency and grounded AI

Branch: `person-3`. Primary folder: `backend/`. Assigned to Ritika.

- Implement upload, processing-status, content, correction, question and deletion APIs with authorization.
- Manage database records, private files, durable jobs, retries and failures.
- Commit edits against their base revisions and reject or reconcile conflicts.
- Invalidate and rebuild dependent audio, search chunks, embeddings and answers after corrections.
- Retrieve only from the selected authorized chapter and return evidence-linked responses.
- Validate citation identifiers and revisions; abstain or qualify when evidence is insufficient or unreliable.
- Handle deployment, limits, costs, retention/deletion and backend integrity evaluation.

Integrate Person 1's extraction adapter and Person 2's speech adapter. Own shared schema coordination and immutable chapter manifests.

## Shared handoffs

Agree on identifiers and contracts before implementation. Person 1 produces structured content; Person 3 stores and versions it; Person 2 presents it. All three participate in integration, evaluation, documentation and demonstration.
