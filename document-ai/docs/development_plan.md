# P1 development plan and phase tracker

Status as of 17 November 2026. Work is limited to the current user-authorized
phase. Never advance with an unresolved critical failure. Await instruction
before starting another phase.

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository foundation, isolated Python 3.12 environment, pinned dependencies, smoke tests and documentation | COMPLETE |
| 1 | Pydantic content models, identity/geometry contracts and JSON Schema | COMPLETE - contract v1.0.0 proposed, awaiting P2/P3 review |
| 2 | Native PDF inspection/extraction and source geometry | COMPLETE - see `docs/pdf_extraction.md` |
| 3 | Image preprocessing and explicit English/Hindi OCR | COMPLETE - see `docs/ocr.md` |
| 4 | Docling adapter, supported hierarchy and reading order | COMPLETE - see `docs/layout.md`; pre-Phase-5 audit fixes on `fix/p1-pre-phase5-audit`; contract 1.1.0 PROPOSED, P2/P3 approval PENDING |
| 5 | Quality flags and deterministic content-only corrections | NOT STARTED - blocked on contract approval (P1 vs P3 draft) and real-sample evaluation |
| 6 | Pipeline orchestration and local CLI | NOT STARTED |
| 7 | Evaluation and P2/P3 integration verification | NOT STARTED |

## Phase 0 affected files

New files only: `pyproject.toml`, `.gitignore`, `README.md`, package `__init__.py`,
requirements/constraints and lock, environment-check script, foundation tests,
and documentation in `docs/`. Existing report files/generators are preserved.

## Phase 0 approach and acceptance

1. Recheck workspace and existing instructions; keep audit read-only.
2. Select compatible versions using package metadata, not an unbounded upgrade.
3. Create a local environment using the installed CPython 3.12.10 interpreter.
4. Resolve and lock dependencies for Windows x86-64; allow one OpenCV distribution.
5. Install package and run dependency consistency, unit and integration checks.
6. Verify imports do not initialize engines, fetch weights or change files.
7. Report native Tesseract/language availability separately from Python libraries.
8. Record actual commands/results and unresolved prerequisites, then stop.

No extraction models, fake pipeline entry point, HTTP backend or frontend will
be added in this phase. No textbook source files or model weights are needed.

## Next-phase files, not yet created

`quality.py` extensions,
`corrections.py`, `pipeline.py`, `cli.py`. (`evaluation.py` metrics and `scripts/evaluate.py` were added before Phase 5; real-sample evaluation is pending.)
Create them only in the relevant phase with tests and documentation. Approve
the shared schema before using it as the P2/P3 integration contract; document
every later schema change and its consumer impact.

