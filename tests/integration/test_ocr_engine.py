"""REAL Tesseract integration tests (Phase 3).

These run the native Tesseract executable with eng+hin language data on
synthetic images. They are skipped, with the reason shown, when Tesseract or
the language data is unavailable. Language data is looked up in
PATHYA_TESSDATA_DIR, else the git-ignored ``local/tessdata`` folder.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unicodedata

from PIL import Image
import pytest

from pathya_document_ai.ocr import OcrConfig, OcrTimeoutError, TesseractEngine, ocr_image, ocr_pdf_pages
from pathya_document_ai.pdf import extract_native_pdf
from pathya_document_ai.tesseract import OcrError, TesseractConfig, TesseractLanguageError, detect_tesseract

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "ocr"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(ROOT / "tests" / "unit"))
from _pdf_factory import PageSpec, upright_text, write_pdf  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engines import unavailable  # noqa: E402

pytestmark = pytest.mark.integration


def _tessdata() -> Path | None:
    configured = os.environ.get("PATHYA_TESSDATA_DIR")
    if configured:
        return Path(configured)
    local = ROOT / "local" / "tessdata"
    return local if local.is_dir() else None


def _engine_or_skip() -> TesseractEngine:
    try:
        return TesseractEngine(TesseractConfig(tessdata_dir=_tessdata()))
    except OcrError as exc:
        unavailable(f"REAL TESSERACT UNAVAILABLE (eng+hin required): {exc}")


@pytest.fixture(scope="module")
def engine() -> TesseractEngine:
    return _engine_or_skip()


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def test_real_engine_version_and_languages(engine: TesseractEngine) -> None:
    assert engine.info.version.startswith("5.")
    assert {"eng", "hin"} <= set(engine.info.available_languages)
    assert "hin:" in engine.info.language_fingerprint(("hin", "eng"))


def test_default_tessdata_without_hindi_is_rejected(engine: TesseractEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATHYA_TESSDATA_DIR", raising=False)  # look at Tesseract's own default folder
    default = detect_tesseract(TesseractConfig(executable=engine.info.executable), require_languages=False)
    if "hin" in default.available_languages:
        pytest.skip("default tessdata already includes hin")
    with pytest.raises(TesseractLanguageError, match="hin"):
        detect_tesseract(TesseractConfig(executable=engine.info.executable))


def test_real_tessdata_path_with_spaces(engine: TesseractEngine, tmp_path: Path) -> None:
    import shutil

    if engine.info.tessdata_dir is None:
        pytest.skip("engine uses Tesseract's default tessdata; nothing to copy")
    spaced = tmp_path / "tess data with spaces"
    spaced.mkdir()
    for lang in ("eng", "hin"):
        shutil.copy2(engine.info.tessdata_dir / f"{lang}.traineddata", spaced)
    spaced_engine = TesseractEngine(TesseractConfig(executable=engine.info.executable, tessdata_dir=spaced))
    before = os.environ.get("TESSDATA_PREFIX")
    result = ocr_image(Image.open(FIXTURES / "hindi.png"), engine=spaced_engine)
    assert _nfc(result.lines[0].text) == _nfc(EXPECTED["hindi"][0])
    assert os.environ.get("TESSDATA_PREFIX") == before  # environment restored


def test_real_english_ocr_keeps_decimals_and_minus(engine: TesseractEngine) -> None:
    result = ocr_image(Image.open(FIXTURES / "english.png"), engine=engine)
    assert [line.text for line in result.lines] == EXPECTED["english"]
    assert all(line.language == "en" for line in result.lines)
    assert all(w.confidence is not None and 0 < w.confidence <= 1 for w in result.words)
    assert result.engine_version == engine.info.version


def test_real_hindi_ocr_keeps_matras_and_diacritics(engine: TesseractEngine) -> None:
    result = ocr_image(Image.open(FIXTURES / "hindi.png"), engine=engine)
    assert [_nfc(line.text) for line in result.lines] == [_nfc(t) for t in EXPECTED["hindi"]]
    assert all(line.language == "hi" for line in result.lines)
    text = "".join(line.text for line in result.lines)
    for mark in ["ि", "ी", "ू", "ं", "़", "्", "।"]:  # i/ii/uu matras, anusvara, nukta, virama, danda
        assert mark in unicodedata.normalize("NFD", text), mark


def test_real_mixed_script_line(engine: TesseractEngine) -> None:
    result = ocr_image(Image.open(FIXTURES / "mixed.png"), engine=engine)
    first = result.lines[0]
    assert _nfc(first.text) == _nfc(EXPECTED["mixed"][0]) and first.language == "mul"
    assert [result.words[i].language for i in first.word_indices] == ["hi", "hi", "en", "en", "en"]
    # Known limitation (see docs/ocr.md): a short Hindi word between English words
    # on line 2 is not reliably recognized; only the stable tokens are asserted.
    second = [result.words[i].text for i in result.lines[1].word_indices]
    assert second[0] == "Mirror" and second[-1] == "2024"


def test_real_word_boxes_match_known_positions(engine: TesseractEngine) -> None:
    result = ocr_image(Image.open(FIXTURES / "english.png"), engine=engine)
    first = result.words[0]
    assert first.raw_text == "The"
    x0, y0, x1, y1 = first.bbox  # type: ignore[misc]
    width, height = result.width_px, result.height_px
    assert 50 <= x0 * width <= 70 and x1 > x0 and y1 > y0  # text starts at the 60 px padding
    assert all(w.bbox is not None for w in result.words)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_real_ocr_geometry_matches_native_on_rotated_cropped_pages(
    engine: TesseractEngine, tmp_path: Path, rotation: int
) -> None:
    origins = {0: (100, 600), 90: (300, 200), 180: (500, 300), 270: (300, 600)}
    x, y = origins[rotation]
    spec = PageSpec(texts=[upright_text(rotation, x, y, "Geometry check passes", size=28)],
                    rotate=rotation, crop_box=(36, 36, 576, 756))
    path = write_pdf(tmp_path / "g.pdf", [spec])
    extraction = extract_native_pdf(path)
    native = {w.text: w.bbox for w in extraction.pages[0].words}
    run = ocr_pdf_pages(path, extraction, engine=engine, config=OcrConfig(languages=("eng",)), dpi=200,
                        force_pages=[0])
    ocr_words = {w.text: w.bbox for w in run.results[0].words}
    assert set(native) <= set(ocr_words)
    for text, box in native.items():
        assert _iou(box, ocr_words[text]) > 0.5, (text, box, ocr_words[text])


def test_real_timeout_and_temp_cleanup(engine: TesseractEngine) -> None:
    before = {p.name for p in Path(tempfile.gettempdir()).glob("tess_*")}
    with pytest.raises(OcrTimeoutError):
        ocr_image(Image.open(FIXTURES / "hindi.png"), engine=engine, config=OcrConfig(timeout_s=0.001))
    ocr_image(Image.open(FIXTURES / "english.png"), engine=engine)
    after = {p.name for p in Path(tempfile.gettempdir()).glob("tess_*")}
    assert after <= before  # pytesseract removed its temporary files


def _iou(a, b) -> float:  # type: ignore[no-untyped-def]
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
