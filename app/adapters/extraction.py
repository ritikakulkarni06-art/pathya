import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.config import Settings
from app.errors import Problem
from app.schemas.content import ExtractionResult, parse_extraction

ProgressCallback = Callable[[int, int], None]


class ExtractionError(Problem):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(422, code, detail)


@runtime_checkable
class ExtractionAdapter(Protocol):
    def extract(
        self,
        source_path: Path,
        languages: list[str],
        page_range: list[int] | None,
        progress_cb: ProgressCallback,
    ) -> ExtractionResult: ...


class FixtureExtractionAdapter:
    """Canned synthetic content for development only; this class performs no OCR."""

    def __init__(self, fixture_path: Path = Path("tests/fixtures/chapter_demo.json")) -> None:
        self.fixture_path = fixture_path

    def extract(
        self,
        source_path: Path,
        languages: list[str],
        page_range: list[int] | None,
        progress_cb: ProgressCallback,
    ) -> ExtractionResult:
        _validate_request(languages, page_range)
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        validated = parse_extraction(raw)
        if page_range is not None:
            selected = set(page_range)
            if selected - {page.pdf_index_0 for page in validated.pages}:
                raise ExtractionError(
                    "invalid_page_range", "Select pages that exist in the chapter."
                )
            raw["pages"] = [page for page in raw["pages"] if page["pdf_index_0"] in selected]
            page_ids = {page["id"] for page in raw["pages"]}
            raw["blocks"] = [block for block in raw["blocks"] if block["page_id"] in page_ids]
            block_ids = {block["id"] for block in raw["blocks"]}
            raw["edges"] = [
                edge
                for edge in raw["edges"]
                if edge["from_id"] in block_ids and edge["to_id"] in block_ids
            ]
            validated = parse_extraction(raw)
        for index, _ in enumerate(validated.pages, 1):
            progress_cb(index, len(validated.pages))
        return validated


def _validate_request(languages: list[str], page_range: list[int] | None) -> None:
    if not languages or set(languages) - {"en", "hi"}:
        raise ExtractionError("unsupported_language", "Select English, Hindi or both.")
    if page_range is not None and (
        not page_range
        or any(page < 0 for page in page_range)
        or len(set(page_range)) != len(page_range)
    ):
        raise ExtractionError("invalid_page_range", "Select unique, non-negative PDF page indexes.")


class SubprocessExtractionAdapter:
    def __init__(
        self, command: list[str], timeout: int = 300, output_limit: int = 10_000_000
    ) -> None:
        if not command:
            raise ExtractionError(
                "extraction_command_required", "Configure the extraction command before running it."
            )
        self.command = command
        self.timeout = timeout
        self.output_limit = output_limit

    def _isolated_command(self) -> list[str]:
        if sys.platform != "linux" or shutil.which("unshare") is None:
            raise ExtractionError(
                "extraction_sandbox_unavailable",
                "Subprocess extraction requires a Linux network namespace sandbox. Use the fixture for development or configure the trusted Python adapter.",
            )
        if os.geteuid() == 0:
            raise ExtractionError(
                "extraction_sandbox_unavailable",
                "Run extraction as an unprivileged service account.",
            )
        return [
            "unshare",
            "--user",
            "--map-root-user",
            "--net",
            "--",
            sys.executable,
            "-m",
            "app.adapters.sandbox",
            str(self.timeout),
            str(self.output_limit),
            "--",
            *self.command,
        ]

    def extract(
        self,
        source_path: Path,
        languages: list[str],
        page_range: list[int] | None,
        progress_cb: ProgressCallback,
    ) -> ExtractionResult:
        _validate_request(languages, page_range)
        command = self._isolated_command()
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PYTHONPATH"}
        }
        environment["PYTHONIOENCODING"] = "utf-8"
        request = json.dumps(
            {
                "source_path": str(source_path.resolve()),
                "languages": languages,
                "page_range": page_range,
            }
        ).encode()
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=output,
                stderr=subprocess.DEVNULL,
                env=environment,
                start_new_session=os.name == "posix",
            )
            try:
                process.communicate(request, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    process.kill()
                process.wait()
                raise ExtractionError(
                    "extraction_timeout", "Extraction took too long. Try fewer pages."
                ) from None
            if process.returncode:
                raise ExtractionError(
                    "extraction_failed",
                    "Extraction failed or its sandbox is unavailable. Check the adapter setup.",
                )
            output.seek(0)
            encoded = output.read(self.output_limit + 1)
        if len(encoded) > self.output_limit:
            raise ExtractionError(
                "extraction_output_too_large", "Extraction returned too much data. Try fewer pages."
            )
        try:
            result = parse_extraction(json.loads(encoded))
        except Problem as error:
            raise ExtractionError(error.code, error.detail) from None
        except (ValueError, UnicodeError):
            raise ExtractionError(
                "invalid_extraction_output", "The extraction command did not return valid JSON."
            ) from None
        for index, _ in enumerate(result.pages, 1):
            progress_cb(index, len(result.pages))
        return result


def get_extraction_adapter(settings: Settings) -> ExtractionAdapter:
    name = settings.extraction_adapter
    if name == "fixture":
        if settings.pathya_env == "prod":
            raise ExtractionError(
                "fixture_is_demo_only", "Synthetic fixture extraction cannot run in production."
            )
        return FixtureExtractionAdapter(settings.extraction_fixture_path)
    if name == "subprocess":
        return SubprocessExtractionAdapter(
            settings.extraction_command, settings.job_timeout_seconds
        )
    if name.startswith("python:"):
        parts = name.removeprefix("python:").split(":")
        if len(parts) == 2:
            module_name, attribute = parts
            adapter = getattr(importlib.import_module(module_name), attribute)()
            if isinstance(adapter, ExtractionAdapter):
                return adapter
    raise ExtractionError("invalid_adapter", "Select a supported extraction adapter.")
