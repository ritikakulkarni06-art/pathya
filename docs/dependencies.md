# Phase 0 dependency decisions

Metadata inspected on 17 November 2026; installed compatibility is verified
separately by the execution report. These choices are a tested baseline, not
a claim that older pins are indefinitely secure or the only valid combination.

| Dependency | Selected version | Reason |
|---|---|---|
| Python | 3.12.x (local 3.12.10) | Explicit project requirement; isolates the machine's default Python 3.14 |
| pdfplumber | 0.11.9 | Native text inspection; Python 3.12-compatible metadata |
| pypdfium2 | 5.13.0 | PDFium bindings; within Docling's >=4.30,<6 constraint |
| Pillow | 11.3.0 | Satisfies Docling 2.70/IBM models' >=10,<12 requirement |
| NumPy | 1.26.4 | Explicit Python 3.12 baseline shared by image and model dependencies |
| opencv-python-headless | 4.11.0.86 | Single selected cv2 distribution; no GUI requirement |
| pytesseract | 0.3.13 | Python wrapper only; native executable/languages separately checked |
| Docling | 2.70.0 | Fixed adapter baseline; no model execution in Phase 0 |
| Pydantic | 2.12.2 | v2 API as requested; satisfies selected Docling core constraints |
| jsonschema | 4.25.1 | Validates later exported JSON Schema fixtures |
| pytest | 8.4.2 | Fixed Python 3.12-compatible test runner |

## Resolving the OpenCV collision

Docling 2.70.0 requires RapidOCR and docling-ibm-models. Older RapidOCR versions
(checked 3.3.1 and 3.9.2) require `opencv-python`, while IBM models 3.9.1 requires
`opencv-python-headless`. Installing both would violate the project rule.

RapidOCR **3.10.0** metadata instead requires headless OpenCV; it is within
Docling's `>=3.3,<4` range. A compatibility constraint selects that version.
Do not bypass dependencies with `--no-deps` for third-party packages or accept
an inconsistent `pip check` to hide this conflict.

Additional constraints keep docling-core 2.50.1, docling-parse 4.7.0 and IBM
models 3.9.1 at Docling's inspected compatible baseline. Torch 2.7.1 and
torchvision 0.22.1 are an explicit matching pair (torchvision metadata requires
that torch version). Inference, accuracy and runtime-resource validation remain
later-phase work; no GPU is required for these foundation import checks.

## Reproducibility

`pyproject.toml` pins direct runtime/dev dependencies. `requirements/constraints.txt`
captures selected transitive compatibility decisions. A hash-bearing
`requirements/py312-windows.lock` records the complete resolver result for
CPython 3.12 on Windows x86-64. The lock also includes the selected build and
locking tools for repeatable editable installation and lock maintenance.

Regenerate in the project Python 3.12 environment only, reviewing the diff:

```powershell
& .\.venv\Scripts\python.exe -m piptools compile --resolver=backtracking --extra dev --extra lock --constraint requirements\constraints.txt --allow-unsafe --generate-hashes --output-file requirements\py312-windows.lock pyproject.toml
```

Never regenerate merely to silence a failure. Test the new resolution,
run `pip check` and confirm that only the selected OpenCV distribution is
installed. The root package's lightweight import must not import these engines.

The initial online compile encountered intermittent DNS/stream failures. Setup
recovered complete wheels from pip's cache, downloaded missing artifacts with
resume support, and verified each against its published PyPI SHA-256. The final
lock was resolved from that verified local wheelhouse, offline. Its active
requirements contain normal version pins and hashes, not machine-local URLs.
Only the selected Windows-compatible wheel hash is retained per distribution.
The temporary wheelhouse and download helpers live under ignored `.cache/`.

For this checkout, the verified cache supports offline installation:

```powershell
& .\.venv\Scripts\python.exe -m pip install --no-index --find-links .cache\wheels --require-hashes -r requirements\py312-windows.lock
```

The cache is not committed or required on a new machine: the main README's
online install resolves the same hashes from the configured package index.

## Primary metadata sources

- [Docling 2.70.0](https://pypi.org/pypi/docling/2.70.0/json)
- [RapidOCR 3.10.0](https://pypi.org/pypi/rapidocr/3.10.0/json)
- [IBM models 3.9.1](https://pypi.org/pypi/docling-ibm-models/3.9.1/json)
- [Docling core 2.50.1](https://pypi.org/pypi/docling-core/2.50.1/json)
- [Docling parse 4.7.0](https://pypi.org/pypi/docling-parse/4.7.0/json)
- [pdfplumber 0.11.9](https://pypi.org/pypi/pdfplumber/0.11.9/json)
- [PDFium bindings 5.13.0](https://pypi.org/pypi/pypdfium2/5.13.0/json)
- [Torchvision 0.22.1](https://pypi.org/pypi/torchvision/0.22.1/json)
- [Tesseract installation guidance](https://tesseract-ocr.github.io/tessdoc/Installation.html)

## Native engines and future checks

Native Tesseract and eng/hin data are external system prerequisites, not pip
dependencies or committed binaries. Report detection failures explicitly.
Docling weights are neither downloaded nor validated in Phase 0; Phase 4 must
record the selected model artifacts/versions and test offline execution.

