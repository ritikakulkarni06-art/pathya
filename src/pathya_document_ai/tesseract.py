"""Tesseract executable and language-data detection (Phase 3).

Tesseract is a separate native program; pytesseract only wraps it. This module
finds the executable, reads its version and installed languages, and refuses
to continue when required languages are missing. There is no silent fallback
to English-only OCR.

Resolution order for the executable: ``TesseractConfig.executable``, the
``PATHYA_TESSERACT_CMD`` environment variable, ``PATH``, then the standard
Windows install location. Language data: ``TesseractConfig.tessdata_dir``,
then ``PATHYA_TESSDATA_DIR``, then Tesseract's own default.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

DEFAULT_LANGUAGES: tuple[str, ...] = ("hin", "eng")
STANDARD_WINDOWS_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
_PROBE_TIMEOUT_S = 20


class OcrError(Exception):
    """Base class for OCR failures."""


class TesseractNotFoundError(OcrError):
    """No usable Tesseract executable was found."""


class TesseractLanguageError(OcrError):
    """Required Tesseract language data is not installed."""


@dataclass(frozen=True)
class TesseractConfig:
    executable: Path | None = None
    tessdata_dir: Path | None = None
    languages: tuple[str, ...] = DEFAULT_LANGUAGES  # order matters: first is primary
    oem: int = 1  # LSTM engine only
    psm: int = 3  # fully automatic page segmentation
    timeout_s: float = 120.0

    @property
    def lang_arg(self) -> str:
        return "+".join(self.languages)


@dataclass(frozen=True)
class TesseractInfo:
    executable: Path
    version: str  # e.g. "5.4.0.20240606"
    available_languages: tuple[str, ...]
    tessdata_dir: Path | None
    language_data_sha256: dict[str, str]  # traineddata hashes when the directory is known

    def language_fingerprint(self, languages: tuple[str, ...]) -> str:
        return ",".join(f"{lang}:{self.language_data_sha256.get(lang, 'unknown')[:12]}" for lang in languages)


def resolve_executable(config: TesseractConfig | None = None) -> Path:
    config = config or TesseractConfig()
    candidates: list[Path] = []
    if config.executable:
        candidates.append(Path(config.executable))
    elif os.environ.get("PATHYA_TESSERACT_CMD"):
        candidates.append(Path(os.environ["PATHYA_TESSERACT_CMD"]))
    else:
        found = shutil.which("tesseract")
        if found:
            candidates.append(Path(found))
        candidates.extend(STANDARD_WINDOWS_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    explicit = config.executable or os.environ.get("PATHYA_TESSERACT_CMD")
    if explicit:
        raise TesseractNotFoundError(f"Configured Tesseract executable not found: {explicit}")
    raise TesseractNotFoundError(
        "Tesseract executable not found on PATH or in the standard install location. Install "
        "Tesseract 5 and set TesseractConfig.executable or PATHYA_TESSERACT_CMD.")


def resolve_tessdata_dir(config: TesseractConfig) -> Path | None:
    value = config.tessdata_dir or os.environ.get("PATHYA_TESSDATA_DIR")
    if value is None:
        return None
    path = Path(value)
    if not path.is_dir():
        raise TesseractLanguageError(f"Configured tessdata directory does not exist: {path}")
    return path


def tessdata_arg(tessdata_dir: Path | None) -> list[str]:
    # Forward slashes survive pytesseract's shlex-based config splitting on Windows.
    return ["--tessdata-dir", tessdata_dir.resolve().as_posix()] if tessdata_dir else []


def _run(args: list[str]) -> str:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_S,
                                   check=False, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TesseractNotFoundError(f"Could not run {args[0]}: {exc}") from exc
    if completed.returncode != 0:
        raise TesseractNotFoundError(
            f"{Path(args[0]).name} {' '.join(args[1:])} failed ({completed.returncode}): "
            f"{completed.stderr.strip()[:300]}")
    return completed.stdout + completed.stderr


def detect_tesseract(config: TesseractConfig | None = None, *, require_languages: bool = True) -> TesseractInfo:
    """Locate Tesseract, read version and languages, and verify required languages."""
    config = config or TesseractConfig()
    executable = resolve_executable(config)
    tessdata_dir = resolve_tessdata_dir(config)
    version_output = _run([str(executable), "--version"])
    match = re.search(r"tesseract\s+v?(\d+\.\d+[\w.\-]*)", version_output, re.IGNORECASE)
    if not match:
        raise TesseractNotFoundError(f"Unrecognized Tesseract version output: {version_output[:200]!r}")
    langs_output = _run([str(executable), "--list-langs", *tessdata_arg(tessdata_dir)])
    available = tuple(sorted(
        line.strip() for line in langs_output.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")))
    hashes: dict[str, str] = {}
    if tessdata_dir is not None:
        for lang in available:
            data = tessdata_dir / f"{lang}.traineddata"
            if data.is_file():
                hashes[lang] = hashlib.sha256(data.read_bytes()).hexdigest()
    info = TesseractInfo(executable, match.group(1), available, tessdata_dir, hashes)
    if require_languages:
        check_languages(info, config.languages)
    return info


def check_languages(info: TesseractInfo, languages: tuple[str, ...]) -> None:
    if not languages:
        raise TesseractLanguageError("At least one OCR language must be configured")
    missing = [lang for lang in languages if lang not in info.available_languages]
    if missing:
        where = info.tessdata_dir or "Tesseract's default tessdata directory"
        raise TesseractLanguageError(
            f"Missing Tesseract language data {missing} in {where}; installed: "
            f"{list(info.available_languages)}. Install the missing *.traineddata files "
            f"(no automatic fallback to fewer languages).")
