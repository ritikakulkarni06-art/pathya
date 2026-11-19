"""A mocked Tesseract engine for unit tests. It proves parsing/mapping logic only,
never OCR accuracy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pathya_document_ai.tesseract import TesseractInfo

FAKE_INFO = TesseractInfo(
    executable=Path("fake-tesseract"), version="5.4.0-fake", available_languages=("eng", "hin", "osd"),
    tessdata_dir=None, language_data_sha256={"eng": "e" * 64, "hin": "h" * 64})


@dataclass
class W:
    """One mocked word in *processed-image* pixel coordinates."""

    text: str
    left: float
    top: float
    width: float
    height: float
    conf: Any = 95
    line: tuple[int, int, int] = (1, 1, 1)


def tesseract_dict(words: list[W]) -> dict[str, list[Any]]:
    """Build image_to_data(DICT) columns, including non-word rows that must be ignored."""
    cols: dict[str, list[Any]] = {k: [] for k in (
        "level", "page_num", "block_num", "par_num", "line_num", "word_num",
        "left", "top", "width", "height", "conf", "text")}

    def add(level: int, block: int, par: int, line: int, word: int, w: W | None) -> None:
        values = dict(level=level, page_num=1, block_num=block, par_num=par, line_num=line, word_num=word,
                      left=int(w.left) if w else 0, top=int(w.top) if w else 0,
                      width=int(w.width) if w else 0, height=int(w.height) if w else 0,
                      conf=w.conf if w else -1, text=w.text if w else "")
        for key, value in values.items():
            cols[key].append(value)

    add(1, 0, 0, 0, 0, None)  # page row
    for n, w in enumerate(words, start=1):
        add(4, *w.line, 0, None)  # line row (ignored)
        add(5, *w.line, n, w)
    add(5, 1, 1, 1, 99, W(" ", 0, 0, 1, 1, conf=-1))  # whitespace word (ignored)
    return cols


@dataclass
class FakeEngine:
    words: list[W] | Callable[[Any], list[W]] = field(default_factory=list)
    info: TesseractInfo = FAKE_INFO
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def image_to_data(self, image: Any, *, languages: tuple[str, ...], psm: int, oem: int,
                      dpi: int | None, timeout_s: float) -> dict[str, list[Any]]:
        self.calls.append(dict(size=image.size, mode=image.mode, languages=languages, psm=psm,
                               oem=oem, dpi=dpi, timeout_s=timeout_s))
        if self.error is not None:
            raise self.error
        words = self.words(image) if callable(self.words) else self.words
        return tesseract_dict(words)
