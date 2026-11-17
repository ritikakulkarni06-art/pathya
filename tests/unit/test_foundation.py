"""Tests for the Phase 0 package boundaries, not future extraction behavior."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_package_import_is_lightweight_and_has_no_filesystem_side_effects(tmp_path: Path) -> None:
    code = """
import json, pathlib, sys
import pathya_document_ai
engines = ['docling', 'torch', 'cv2', 'pdfplumber', 'pypdfium2', 'pytesseract']
print(json.dumps({'files': list(map(str, pathlib.Path('.').iterdir())),
                  'engines': [name for name in engines if name in sys.modules],
                  'package': pathya_document_ai.__file__}))
"""
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=20, check=True)
    report = json.loads(result.stdout)
    assert report["files"] == []
    assert report["engines"] == []
    assert Path(report["package"]).resolve().is_relative_to(ROOT / "src")


def test_packaging_limits_discovery_to_application_and_pytest_to_tests() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["requires-python"] == ">=3.12,<3.13"
    assert config["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert "scripts" not in config["project"]  # No premature extraction CLI.


@pytest.mark.parametrize("lockfile", ["py312-windows.lock", "py312-linux.lock"])
def test_lock_contains_all_direct_runtime_and_dev_pins(lockfile: str) -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = (ROOT / "requirements" / lockfile).read_text(encoding="utf-8")
    locked = {
        line.strip().removesuffix("\\").strip().lower().replace("_", "-")
        for line in lock.splitlines()
        if line and not line[0].isspace() and "==" in line and not line.startswith("#")
    }
    required = config["project"]["dependencies"] + config["project"]["optional-dependencies"]["dev"]
    assert all(pin.lower().replace("_", "-") in locked for pin in required)
    assert "--hash=sha256:" in lock

