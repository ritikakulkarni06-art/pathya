# Pathya - P1 Document AI

This repository contains Pathya's research artifacts and the new Person 1
Python package. **Phases 0-4 are complete: the environment, the proposed shared
content contract v1.1.0 (`docs/p1_contract.md`, `contract/`), native PDF
text extraction/rendering (`docs/pdf_extraction.md`) and English/Hindi OCR
(`docs/ocr.md`), and Docling layout analysis and reading order
(`docs/layout.md`). The full pipeline is not implemented yet.**

P1 owns PDF/image inspection, rendering, preprocessing, English/Hindi OCR,
layout/order extraction, structured content, uncertainty flags, content-only
corrections and extraction evaluation. P2 owns the frontend and speech; P3
owns HTTP services, persistence, revision transactions and retrieval/answers.
No P2 or P3 implementation is included.

## Python and installation

Use **CPython 3.12.x, Windows x86-64** for the initial verified environment.
The machine's default `python` is 3.14; do not use it for this package.

From the repository root in PowerShell (the first path is the verified local
interpreter; use your own Python 3.12 executable on another machine):

```powershell
& 'C:\Users\gunda\AppData\Local\Programs\Python\Python312\python.exe' -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements\py312-windows.lock
& .\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe scripts\check_environment.py
```

The lockfile is generated and validated during Phase 0. It records this
platform's dependency resolution, not universal Linux/macOS compatibility.
Other platforms need their own resolution and tests. No global packages are
changed. Installing Docling/PyTorch can require substantial disk/download space;
installation does not establish model quality or download inference weights.

## Native Tesseract prerequisite

`pytesseract` is a wrapper; the native Tesseract executable and `eng` / `hin`
language files are separate prerequisites. They are not bundled in this repo.
The environment checker reports their actual availability, and strict OCR
readiness can be checked with:

```powershell
& .\.venv\Scripts\python.exe scripts\check_environment.py --require-tesseract
```

If Tesseract is installed outside PATH, pass `--tesseract-cmd` with its full
executable path. Missing languages must be installed from an authorized
distribution before Phase 3 live OCR verification. No guessed confidence or
mocked OCR is considered a successful native-engine check.

## Repository layout

```text
src/pathya_document_ai/  # Application package, initially import-safe shell
tests/unit/             # Deterministic foundation/contract tests
tests/integration/      # Real dependency and native-binding checks
scripts/                # Development environment verification
requirements/           # Compatibility constraints and Windows/Python lock
contract/               # Generated JSON Schema and bilingual sample document
docs/                   # Phase tracker, dependency decisions, P1 contract
output/pdf/             # Existing research reports, preserved
```

Existing root-level `build_*`, `revise_roles_pdf.py` and `verify_report.py`
are documentation tools, not the P1 pipeline. They execute work on import;
the new package does not import them. Their fonts/report dependencies are
outside this package's environment and remain untouched.

## Tests and phase boundaries

```powershell
& .\.venv\Scripts\python.exe -m pytest tests\unit
& .\.venv\Scripts\python.exe -m pytest tests\integration -m integration
```

Foundation tests check packaging, import isolation, pinned dependencies, one
OpenCV distribution, actual PDFium/image bindings and Docling imports. They do
not claim OCR accuracy, extraction correctness or model inference coverage.
No remote calls, model downloads or copyrighted fixtures belong in tests.

See [development plan](docs/development_plan.md),
[dependency decisions](docs/dependencies.md) and
[P1 contract status](docs/p1_contract.md).

