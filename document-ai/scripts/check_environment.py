"""Read-only environment report; no model imports, inference or downloads.

Checks Python and pinned packages, the native Tesseract executable and its
eng/hin language data (default or custom tessdata directory, paths with
spaces supported), and the local Docling model folders against the pinned
manifest requirements/models.lock.json (sizes; full SHA-256 with --verify-hashes).
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENCV_DISTRIBUTIONS = (
    "opencv-python", "opencv-python-headless",
    "opencv-contrib-python", "opencv-contrib-python-headless",
)


def inspect_tesseract(command: str | None = None, tessdata_dir: str | None = None) -> dict[str, Any]:
    """Report the actual executable and languages, with a bounded subprocess."""
    tessdata_args: list[str] = []
    if tessdata_dir:
        if not Path(tessdata_dir).is_dir():
            return {"status": "unavailable", "reason": f"tessdata directory not found: {tessdata_dir}",
                    "languages": [], "required_languages": ["eng", "hin"], "tessdata_dir": tessdata_dir}
        # Passed as one list item, so directories containing spaces work.
        tessdata_args = ["--tessdata-dir", str(Path(tessdata_dir).resolve())]
    resolved = command or os.environ.get("PATHYA_TESSERACT_CMD") or shutil.which("tesseract")
    if not resolved:
        standard = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        resolved = str(standard) if standard.is_file() else None
    if not resolved:
        return {"status": "unavailable", "reason": "Native Tesseract not found.",
                "languages": [], "required_languages": ["eng", "hin"]}
    try:
        version = subprocess.run(
            [resolved, "--version"], capture_output=True, text=True,
            timeout=10, check=True,
        )
        language_result = subprocess.run(
            [resolved, "--list-langs", *tessdata_args], capture_output=True, text=True,
            timeout=10, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "unavailable", "reason": str(exc), "command": resolved,
                "languages": [], "required_languages": ["eng", "hin"]}
    lines = language_result.stdout.splitlines()
    languages = sorted(line.strip() for line in lines if line.strip() in {"eng", "hin"})
    version_lines = (version.stdout or version.stderr).splitlines()
    return {"status": "ready" if set(languages) == {"eng", "hin"} else "missing_languages",
            "command": resolved, "version": version_lines[0] if version_lines else None,
            "languages": languages, "required_languages": ["eng", "hin"], "tessdata_dir": tessdata_dir}


def inspect_docling_models(artifacts: str | None, *, verify_hashes: bool = False) -> dict[str, Any]:
    """Compare local Docling model folders with requirements/models.lock.json."""
    if not artifacts:
        return {"status": "unavailable", "reason": "No model directory (PATHYA_DOCLING_ARTIFACTS or "
                "--docling-artifacts). Run scripts/fetch_models.py --download.", "problems": []}
    manifest = json.loads((ROOT / "requirements" / "models.lock.json").read_text(encoding="utf-8"))
    base = Path(artifacts)
    problems = []
    for repo in manifest["docling"]:
        for entry in repo["files"]:
            path = base / repo["local_dir"] / entry["path"]
            if not path.is_file():
                problems.append(f"missing {path}")
            elif path.stat().st_size != entry["size"]:
                problems.append(f"size mismatch {path}")
    if verify_hashes and not problems:
        spec = importlib.util.spec_from_file_location("fetch_models", ROOT / "scripts" / "fetch_models.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        problems = module.verify(base, None)
    pinned = {r["repo_id"]: r["revision"] for r in manifest["docling"]}
    return {"status": "ready" if not problems else "invalid", "directory": str(base), "pinned": pinned,
            "hashes_verified": verify_hashes and not problems, "problems": problems}


def inspect_environment(
    *, require_tesseract: bool = False, tesseract_cmd: str | None = None,
    tessdata_dir: str | None = None, docling_artifacts: str | None = None,
    require_docling: bool = False, verify_hashes: bool = False,
) -> dict[str, Any]:
    """Compare installed direct pins and report external-engine readiness."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = config["project"]["dependencies"] + config["project"]["optional-dependencies"]["dev"]
    errors: list[str] = []
    if sys.version_info[:2] != (3, 12):
        errors.append("Use CPython 3.12.x for this project.")
    packages: dict[str, Any] = {}
    for requirement in requirements:
        name, separator, expected = requirement.partition("==")
        if not separator:
            errors.append(f"Unpinned direct requirement: {requirement}")
            continue
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        packages[name] = {"expected": expected, "installed": installed}
        if installed != expected:
            errors.append(f"{name}: expected {expected}, found {installed!r}.")
    opencv = []
    for name in OPENCV_DISTRIBUTIONS:
        try:
            metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        opencv.append(name)
    if opencv != ["opencv-python-headless"]:
        errors.append(f"Expected only opencv-python-headless; found {opencv!r}.")
    tesseract = inspect_tesseract(tesseract_cmd, tessdata_dir)
    if require_tesseract and tesseract["status"] != "ready":
        errors.append("Native OCR prerequisite incomplete: Tesseract with eng and hin required.")
    docling = inspect_docling_models(docling_artifacts, verify_hashes=verify_hashes)
    if require_docling and docling["status"] != "ready":
        errors.append("Docling model prerequisite incomplete: "
                      + (docling.get("reason") or "; ".join(docling["problems"][:3])))
    return {"python": sys.version.split()[0], "executable": sys.executable,
            "packages": packages, "opencv_distributions": opencv,
            "tesseract": tesseract, "docling_models": docling, "model_inference_verified": False,
            "errors": errors, "ok": not errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tesseract", action="store_true")
    parser.add_argument("--tesseract-cmd", help="Explicit native executable path.")
    parser.add_argument("--tessdata-dir", default=os.environ.get("PATHYA_TESSDATA_DIR"),
                        help="Custom tessdata directory (default: PATHYA_TESSDATA_DIR).")
    parser.add_argument("--docling-artifacts", default=os.environ.get("PATHYA_DOCLING_ARTIFACTS"),
                        help="Docling model directory (default: PATHYA_DOCLING_ARTIFACTS).")
    parser.add_argument("--require-docling", action="store_true")
    parser.add_argument("--verify-hashes", action="store_true", help="Full SHA-256 check of model files.")
    arguments = parser.parse_args()
    report = inspect_environment(
        require_tesseract=arguments.require_tesseract, tesseract_cmd=arguments.tesseract_cmd,
        tessdata_dir=arguments.tessdata_dir, docling_artifacts=arguments.docling_artifacts,
        require_docling=arguments.require_docling, verify_hashes=arguments.verify_hashes)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

