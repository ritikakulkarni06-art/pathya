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
    monkeypatch.setattr(environment, "inspect_tesseract", lambda *_: {"status": "unavailable"})
    assert environment.inspect_environment()["ok"] is True
    strict = environment.inspect_environment(require_tesseract=True)
    assert strict["ok"] is False
    assert any("Native OCR prerequisite" in message for message in strict["errors"])


def test_custom_tessdata_dir_with_spaces_is_passed_as_one_argument(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    spaced = tmp_path / "tess data"
    spaced.mkdir()
    seen: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        output = "tesseract 5.4.0\n" if command[-1] == "--version" else "List:\neng\nhin\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(environment.subprocess, "run", fake_run)
    report = environment.inspect_tesseract("test-tesseract", str(spaced))
    assert report["status"] == "ready"
    assert seen[1][-2:] == ["--tessdata-dir", str(spaced.resolve())]  # one argument, not split on the space


def test_missing_tessdata_dir_is_reported() -> None:
    report = environment.inspect_tesseract("test-tesseract", "C:/definitely/not/here")
    assert report["status"] == "unavailable" and "tessdata" in report["reason"]


def test_docling_models_are_checked_against_the_manifest(tmp_path: Path) -> None:
    assert environment.inspect_docling_models(None)["status"] == "unavailable"
    report = environment.inspect_docling_models(str(tmp_path))
    assert report["status"] == "invalid" and report["problems"]
    assert all(len(rev) == 40 for rev in report["pinned"].values())  # full commit hashes are pinned


def test_require_docling_turns_missing_models_into_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(environment, "inspect_tesseract", lambda *_: {"status": "unavailable"})
    report = environment.inspect_environment(require_docling=True, docling_artifacts=None)
    assert report["ok"] is False and any("Docling model" in e for e in report["errors"])

