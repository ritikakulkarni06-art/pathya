"""Deterministic readiness-report tests with no native engine invocation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pathya_environment_check", ROOT / "scripts" / "check_environment.py")
assert SPEC is not None and SPEC.loader is not None
environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(environment)


def test_missing_tesseract_is_reported_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment.shutil, "which", lambda _: None)
    monkeypatch.setattr(environment.Path, "is_file", lambda _: False)
    report = environment.inspect_tesseract()
    assert report["status"] == "unavailable"
    assert report["languages"] == []


@pytest.mark.parametrize(
    ("languages", "status"),
    [(["eng"], "missing_languages"), (["hin"], "missing_languages"), (["eng", "hin"], "ready")],
)
def test_tesseract_language_readiness_checks_both_languages(
    monkeypatch: pytest.MonkeyPatch, languages: list[str], status: str,
) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 10
        output = "tesseract 5.5.0\n" if command[-1] == "--version" else "List of available languages:\n" + "\n".join(languages)
        return subprocess.CompletedProcess(command, 0, output, "")
    monkeypatch.setattr(environment.subprocess, "run", fake_run)
    report = environment.inspect_tesseract("test-tesseract")
    assert report["status"] == status
    assert report["languages"] == sorted(languages)


def test_tesseract_timeout_is_an_explicit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(command: list[str], **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(command, 10)
    monkeypatch.setattr(environment.subprocess, "run", timeout)
    assert environment.inspect_tesseract("test-tesseract")["status"] == "unavailable"


def test_native_readiness_is_separate_from_python_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment, "inspect_tesseract", lambda _: {"status": "unavailable"})
    assert environment.inspect_environment()["ok"] is True
    strict = environment.inspect_environment(require_tesseract=True)
    assert strict["ok"] is False
    assert any("Native OCR prerequisite" in message for message in strict["errors"])

