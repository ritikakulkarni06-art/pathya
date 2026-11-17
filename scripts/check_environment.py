"""Read-only Phase 0 environment report; no model imports or downloads."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
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


def inspect_tesseract(command: str | None = None) -> dict[str, Any]:
    """Report the actual executable and languages, with a bounded subprocess."""
    resolved = command or shutil.which("tesseract")
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
            [resolved, "--list-langs"], capture_output=True, text=True,
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
            "languages": languages, "required_languages": ["eng", "hin"]}


def inspect_environment(
    *, require_tesseract: bool = False, tesseract_cmd: str | None = None,
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
    tesseract = inspect_tesseract(tesseract_cmd)
    if require_tesseract and tesseract["status"] != "ready":
        errors.append("Native OCR prerequisite incomplete: Tesseract with eng and hin required.")
    return {"python": sys.version.split()[0], "executable": sys.executable,
            "packages": packages, "opencv_distributions": opencv,
            "tesseract": tesseract, "model_inference_verified": False,
            "errors": errors, "ok": not errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-tesseract", action="store_true")
    parser.add_argument("--tesseract-cmd", help="Explicit native executable path.")
    arguments = parser.parse_args()
    report = inspect_environment(require_tesseract=arguments.require_tesseract,
                                 tesseract_cmd=arguments.tesseract_cmd)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

