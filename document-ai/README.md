# Document AI

Owner: Person 1. Branch: `person-1`.

Work area for PDF/image preparation, English/Hindi OCR, layout, structured blocks, source geometry, review flags, content operations and extraction evaluation. Add adapter setup, legally usable fixtures and validation instructions with implementation.

Coordinate output contracts with Person 3 and source-navigation needs with Person 2.

## Pathya P1 Document AI package

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

## Extract a document

```python
from pathya_document_ai import ExtractionOptions, extract_document

result = extract_document("chapter.pdf", ExtractionOptions(source_uri="asset://p3/123"))
print(result.to_json(indent=2))     # validated contract Document (1.2.0, proposed)
```

```
python -m pathya_document_ai extract chapter.pdf -o chapter.json   # PDF, PNG, JPEG or TIFF
python -m pathya_document_ai validate chapter.json
```

See `docs/p1_contract.md` (contract, entry point, exit codes). 1.1.0 output for
current integrations: `--target-version 1.1.0 --drop heading_level,role`.

## Python and installation

Use **CPython 3.12.x**. Both lockfiles are hash-locked (`--require-hashes`).

| Platform | Lockfile | Notes |
|---|---|---|
| Windows x86-64 | `requirements/py312-windows.lock` | Verified on the development machine (fresh install). CI installs from it. |
| Linux x86-64 | `requirements/py312-linux.lock` | Generated with `pip-compile` on Ubuntu 24.04 (WSL) with the CPU-only PyTorch index. CI installs from it. |
| macOS | none | Not resolved or tested |

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements\py312-windows.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
```

Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/py312-linux.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/python -m pip check
```

## Native engines and pinned models (optional for unit tests)

These are only needed for real OCR and layout and their integration tests.
They are not stored in git.

1. **Tesseract 5.** Windows: `winget install UB-Mannheim.TesseractOCR`.
   Debian/Ubuntu: `apt install tesseract-ocr`. The executable is found on
   `PATH`, at the standard Windows location, or via `PATHYA_TESSERACT_CMD`.
2. **Pinned model files** (eng/hin/osd tessdata and Docling layout and
   TableFormer weights):
   ```
   python scripts/fetch_models.py --download   # pinned commits, SHA-256 verified, safetensors only
   python scripts/fetch_models.py --verify
   ```
   The files go to `local/` (git-ignored). Override with
   `PATHYA_TESSDATA_DIR` and `PATHYA_DOCLING_ARTIFACTS`. Paths with spaces
   are supported. Exact revisions and hashes are in
   `requirements/models.lock.json`.
3. **Check the setup:**
   ```
   python scripts/check_environment.py --require-tesseract --require-docling --verify-hashes
   ```

## Tests

| Command | What runs |
|---|---|
| `pytest tests/unit` | Everything that needs no native engine: mocked OCR and layout, contract, conformance vectors, geometry |
| `pytest` | Unit tests plus real-engine integration tests. Real-engine tests **skip** when Tesseract or the models are missing. |
| `PATHYA_REQUIRE_REAL_ENGINES=1 pytest tests/integration` | Missing engines **fail** instead of skipping (used in CI) |

**CI** (`.github/workflows/p1-document-ai.yml`) has three jobs:
- unit tests on Windows and Linux, installed from the lockfiles
- a check that the schemas and conformance vectors are current
- a real-engine job on Windows that installs Tesseract, fetches the pinned
  models (cached) and requires the integration tests to run

**Evaluation:** `scripts/evaluate.py`; see `docs/evaluation.md`. Real-textbook
evaluation is pending.

## Security notes

- **Untrusted PDFs:** handled with file-size, page, character, pixel, DPI and
  time limits. PDFium runs without forms or JavaScript, and nothing is
  fetched from links inside documents.
- **Model weights:** loaded as **safetensors** only. Docling's TableFormer
  inference uses `safetensors.load_model`. Its `torch.load` path exists only
  for training checkpoints (`*.check`), and `fetch_models.py` refuses
  pickle-format files.
- **Downloads:** happen only when `fetch_models.py --download` is run
  explicitly, from pinned commits, and each file is verified before use. At
  runtime Docling reads the local folder only; remote services are disabled.
- **Remaining risks:**
  - The pinned upstream repositories are trusted.
  - Docling's C++ PDF parser (docling-parse) and PDFium parse untrusted input
    in-process. There is no OS-level sandbox; P3's subprocess sandbox would
    provide one.

## Repository layout

```text
src/pathya_document_ai/  # Application package, initially import-safe shell
tests/unit/             # Deterministic foundation/contract tests
tests/integration/      # Real dependency and native-binding checks
scripts/                # Development environment verification
requirements/           # Compatibility constraints and Windows/Python lock
contract/               # Generated JSON Schema and bilingual sample document
docs/                   # Phase tracker, dependency decisions, P1 contract
```

The research reports live in the repository's `docs/` folder. Their generator
scripts are not part of this package; they remain in the history of commit
`39331e4`.

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

