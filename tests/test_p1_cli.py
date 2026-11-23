import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.adapters import p1_cli
from app.errors import Problem


def test_command_uses_p1_venv_and_local_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("P1_HOME", str(tmp_path))
    monkeypatch.delenv("P1_PYTHON", raising=False)
    argv = p1_cli.command(tmp_path / "ch.pdf", ["hi", "en"])
    assert ".venv" in argv[0]
    assert argv[1:4] == ["-m", "pathya_document_ai", "extract"]
    assert argv[argv.index("--languages") + 1] == "hin,eng"
    assert argv[argv.index("--tessdata-dir") + 1] == str(tmp_path / "local" / "tessdata")
    assert argv[argv.index("--docling-artifacts") + 1] == str(tmp_path / "local" / "docling-models")


def test_missing_python_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("P1_PYTHON", str(tmp_path / "missing"))
    with pytest.raises(Problem) as error:
        p1_cli.extract(tmp_path / "ch.pdf", ["en"])
    assert error.value.code == "p1_extractor_unavailable"


@pytest.mark.parametrize(
    ("returncode", "code"),
    [(0, None), (2, "unreadable_source"), (4, "p1_engine_unavailable"), (1, "extraction_failed")],
)
def test_exit_codes(monkeypatch: pytest.MonkeyPatch, returncode: int, code: str | None) -> None:
    monkeypatch.setenv("P1_PYTHON", sys.executable)
    seen: dict[str, Any] = {}

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        seen.update(kw)
        return subprocess.CompletedProcess(argv, returncode, b'{"ok":1}', b"")

    monkeypatch.setattr(p1_cli.subprocess, "run", run)
    if code is None:
        assert p1_cli.extract(Path("ch.pdf"), ["en"]) == b'{"ok":1}'
        assert seen["env"]["HF_HUB_OFFLINE"] == "1"
    else:
        with pytest.raises(Problem) as error:
            p1_cli.extract(Path("ch.pdf"), ["en"])
        assert error.value.code == code


def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P1_PYTHON", sys.executable)

    def run(argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(p1_cli.subprocess, "run", run)
    with pytest.raises(Problem) as error:
        p1_cli.extract(Path("ch.pdf"), ["en"])
    assert error.value.code == "extraction_timeout"
