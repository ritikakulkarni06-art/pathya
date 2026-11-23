"""Run the Person 1 extractor (document-ai) from its own virtual environment.

Set ``EXTRACTION_ADAPTER=p1:app.adapters.p1_cli:extract``. The extractor keeps its heavy
dependencies (Docling, PyTorch, Tesseract bindings) in ``document-ai/.venv``, so the
backend calls it as a trusted local program and reads the contract JSON it prints.

Environment (all optional):
- ``P1_HOME``: the document-ai folder (default ``document-ai``)
- ``P1_PYTHON``: its Python (default ``<P1_HOME>/.venv`` Python)
- ``P1_TIMEOUT_SECONDS``: default 900
- ``PATHYA_TESSERACT_CMD``: Tesseract, when it is not on PATH or in the standard place
"""

import os
import subprocess
import sys
from pathlib import Path

from app.errors import Problem

LANGUAGES = {"en": "eng", "hi": "hin"}


def _python(home: Path) -> Path:
    configured = os.environ.get("P1_PYTHON")
    if configured:
        return Path(configured)
    venv = home / ".venv"
    return venv / "Scripts" / "python.exe" if sys.platform == "win32" else venv / "bin" / "python"


def command(path: Path, languages: list[str]) -> list[str]:
    home = Path(os.environ.get("P1_HOME", "document-ai")).resolve()
    local = home / "local"
    return [
        str(_python(home)),
        "-m",
        "pathya_document_ai",
        "extract",
        str(path.resolve()),
        "--languages",
        ",".join(LANGUAGES[language] for language in languages if language in LANGUAGES),
        "--tessdata-dir",
        str(local / "tessdata"),
        "--docling-artifacts",
        str(local / "docling-models"),
        "--indent",
        "0",
    ]


def extract(path: Path, languages: list[str]) -> bytes:
    argv = command(path, languages)
    if not Path(argv[0]).is_file():
        raise Problem(503, "p1_extractor_unavailable", "Configure the verified Person 1 extractor.")
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            env=environment,
            timeout=int(os.environ.get("P1_TIMEOUT_SECONDS", "900")),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise Problem(
            422, "extraction_timeout", "Extraction took too long. Try fewer pages."
        ) from None
    if done.returncode == 4:
        raise Problem(
            503,
            "p1_engine_unavailable",
            "Text recognition is not installed on the server. Ask the administrator to install Tesseract.",
        )
    if done.returncode == 2:
        raise Problem(
            422, "unreadable_source", "This file could not be read. Upload a PDF or image."
        )
    if done.returncode:
        raise Problem(
            422, "extraction_failed", "Extraction failed. Try again or upload another copy."
        )
    return done.stdout
