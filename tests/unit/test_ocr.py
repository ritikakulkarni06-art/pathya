"""Phase 3 OCR unit tests with a MOCKED Tesseract engine.

These verify detection logic, parsing, confidence handling, language tagging,
geometry mapping and integration plumbing. They say nothing about real OCR
accuracy; see tests/integration/test_ocr_engine.py for the real engine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jsonschema
from PIL import Image, ImageDraw
import pytest

from _fake_ocr import FAKE_INFO, FakeEngine, W
from _pdf_factory import Image as PdfImage, PageSpec, Text, write_pdf
from pathya_document_ai import tesseract as tess
from pathya_document_ai.geometry import CoordinateTransform, normalized_to_pdf_user_space
from pathya_document_ai.models import ConfidenceOrigin, Document, Language, QualityFlag
from pathya_document_ai.ocr import (
    OcrConfig,
    OcrEngineError,
    OcrPageStatus,
    OcrTimeoutError,
    Script,
    TesseractEngine,
    classify_script,
    language_for,
    merge_ocr_into_document,
    ocr_image,
    ocr_pdf_pages,
    select_ocr_pages,
    to_contract_blocks,
)
from pathya_document_ai.pdf import extract_native_pdf, to_contract_document
from pathya_document_ai.preprocess import ImageLimits, OcrImageError, PreprocessConfig
from pathya_document_ai.schema import build_json_schema
from pathya_document_ai.tesseract import (
    TesseractConfig,
    TesseractLanguageError,
    TesseractNotFoundError,
    detect_tesseract,
)

NO_PREP = OcrConfig(preprocess=PreprocessConfig(deskew=False, contrast="none"))


def _page(size: tuple[int, int] = (1000, 500)) -> Image.Image:
    img = Image.new("RGB", size, "white")
    ImageDraw.Draw(img).rectangle([100, 100, 400, 140], fill="black")
    return img


# ------------------------------------------------------------- detection


@pytest.fixture()
def fake_exe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    exe = tmp_path / "tesseract.exe"
    exe.write_bytes(b"")
    monkeypatch.delenv("PATHYA_TESSERACT_CMD", raising=False)
    monkeypatch.delenv("PATHYA_TESSDATA_DIR", raising=False)
    return exe


def _fake_run(langs: list[str], version: str = "tesseract v5.4.0.20240606\n leptonica-1.84.1"):  # type: ignore[no-untyped-def]
    def run(args: list[str]) -> str:
        if "--version" in args:
            return version
        return 'List of available languages in "x" (2):\n' + "\n".join(langs) + "\n"
    return run


def test_detects_explicit_executable_version_and_languages(fake_exe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tess, "_run", _fake_run(["eng", "hin", "osd"]))
    info = detect_tesseract(TesseractConfig(executable=fake_exe))
    assert info.executable == fake_exe and info.version == "5.4.0.20240606"
    assert info.available_languages == ("eng", "hin", "osd")


def test_executable_from_environment_variable(fake_exe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATHYA_TESSERACT_CMD", str(fake_exe))
    assert tess.resolve_executable(TesseractConfig()) == fake_exe


def test_missing_hindi_is_an_error_not_a_fallback(fake_exe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tess, "_run", _fake_run(["eng", "osd"]))
    with pytest.raises(TesseractLanguageError, match=r"\['hin'\]"):
        detect_tesseract(TesseractConfig(executable=fake_exe))
    # Explicit English-only configuration is allowed; it is a caller decision.
    info = detect_tesseract(TesseractConfig(executable=fake_exe, languages=("eng",)))
    assert "hin" not in info.available_languages


def test_missing_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PATHYA_TESSERACT_CMD", raising=False)
    with pytest.raises(TesseractNotFoundError, match="Configured"):
        detect_tesseract(TesseractConfig(executable=tmp_path / "nope.exe"))
    monkeypatch.setattr(tess.shutil, "which", lambda name: None)
    monkeypatch.setattr(tess, "STANDARD_WINDOWS_PATHS", (tmp_path / "absent.exe",))
    with pytest.raises(TesseractNotFoundError, match="not found on PATH"):
        detect_tesseract(TesseractConfig())


def test_unusable_executable_output(fake_exe: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tess, "_run", _fake_run(["eng"], version="not tesseract"))
    with pytest.raises(TesseractNotFoundError, match="version"):
        detect_tesseract(TesseractConfig(executable=fake_exe, languages=("eng",)))


def test_missing_tessdata_directory(fake_exe: Path, tmp_path: Path) -> None:
    with pytest.raises(TesseractLanguageError, match="tessdata"):
        detect_tesseract(TesseractConfig(executable=fake_exe, tessdata_dir=tmp_path / "missing"))


def test_ocr_refuses_languages_engine_lacks() -> None:
    engine = FakeEngine(info=FAKE_INFO.__class__(**{**FAKE_INFO.__dict__, "available_languages": ("eng",)}))
    with pytest.raises(TesseractLanguageError):
        ocr_image(_page(), engine=engine)
    assert engine.calls == []


# ---------------------------------------------------------- parsing & text


def test_english_words_lines_and_confidence() -> None:
    engine = FakeEngine([W("Speed", 100, 100, 120, 40, 96.5), W("4.5", 230, 100, 60, 40, 88),
                         W("m/s", 300, 100, 80, 40, -1), W("Next", 100, 200, 90, 40, 70, line=(1, 1, 2))])
    result = ocr_image(_page(), engine=engine, config=NO_PREP, page_index=3)
    assert result.status is OcrPageStatus.OK and result.page_index == 3
    assert [w.raw_text for w in result.words] == ["Speed", "4.5", "m/s", "Next"]
    assert [w.confidence for w in result.words] == [0.965, 0.88, None, 0.70]
    assert result.words[2].raw_confidence == "-1"
    assert [line.text for line in result.lines] == ["Speed 4.5 m/s", "Next"]
    assert result.lines[0].confidence == pytest.approx((0.965 + 0.88) / 2)
    assert result.diagnostics.null_confidence_count == 1 and result.diagnostics.word_count == 4
    assert result.engine_version == "5.4.0-fake" and result.languages == ("hin", "eng")
    assert engine.calls[0]["languages"] == ("hin", "eng")


@pytest.mark.parametrize("conf", ["abc", 150, -5, "nan"])
def test_invalid_confidence_becomes_null_with_warning(conf: Any) -> None:
    result = ocr_image(_page(), engine=FakeEngine([W("x", 100, 100, 20, 20, conf)]), config=NO_PREP)
    assert result.words[0].confidence is None
    assert any("confidence set to null" in w for w in result.warnings)


def test_hindi_and_mixed_language_tags() -> None:
    words = [W("प्रकाश", 100, 100, 100, 40), W("कोण", 210, 100, 60, 40), W("(angle)", 280, 100, 100, 40),
             W("2024", 390, 100, 60, 40), W("Mirrorदर्पण", 100, 200, 200, 40, line=(1, 1, 2))]
    result = ocr_image(_page(), engine=FakeEngine(words), config=NO_PREP)
    assert [w.language for w in result.words] == ["hi", "hi", "en", "und", "mul"]
    assert [line.language for line in result.lines] == ["mul", "mul"]
    blocks = to_contract_blocks(result, page_id=Document.model_fields["id"].default_factory())  # type: ignore[misc]
    assert all(QualityFlag.MIXED_SCRIPT in b.quality_flags for b in blocks)


@pytest.mark.parametrize(("text", "script"), [
    ("विद्यार्थी", Script.DEVANAGARI), ("ि", Script.DEVANAGARI), ("ँ", Script.DEVANAGARI),
    ("Hello", Script.LATIN), ("café", Script.LATIN), ("x²", Script.LATIN),
    ("4.5", Script.NONE), ("−", Script.NONE), ("।", Script.NONE),
    ("Mirrorदर्पण", Script.MIXED), ("Ωμέγα", Script.OTHER),
])
def test_script_classification(text: str, script: Script) -> None:
    assert classify_script(text) is script


def test_language_requires_configured_language() -> None:
    assert language_for(Script.DEVANAGARI, ("eng",)) == "und"
    assert language_for(Script.LATIN, ("hin",)) == "und"
    assert language_for(Script.OTHER, ("hin", "eng")) == "und"


def test_unusual_characters_preserved_and_nfc_kept_separately() -> None:
    decomposed = "पढ़"  # ढ + nukta as separate code points
    words = [W("≈∑", 100, 100, 40, 40), W("á", 150, 100, 40, 40), W(decomposed, 200, 100, 60, 40)]
    result = ocr_image(_page(), engine=FakeEngine(words), config=NO_PREP)
    assert result.words[0].raw_text == "≈∑" and result.words[0].language == "und"
    assert result.words[1].raw_text == "á" and result.words[1].text == "á"
    assert result.words[2].raw_text == decomposed


# -------------------------------------------------------------- geometry


def test_boxes_normalized_to_original_image() -> None:
    result = ocr_image(_page((1000, 500)), engine=FakeEngine([W("x", 100, 100, 300, 40)]), config=NO_PREP)
    assert result.words[0].bbox == pytest.approx((0.1, 0.2, 0.4, 0.28))


def test_boxes_mapped_back_through_upscaling() -> None:
    # Processed image is 2x (150 -> 300 DPI); the engine reports processed pixels.
    engine = FakeEngine([W("x", 200, 200, 600, 80)])
    result = ocr_image(_page((1000, 500)), engine=engine, config=OcrConfig(preprocess=PreprocessConfig(deskew=False)),
                       dpi=150)
    assert engine.calls[0]["size"] == (2000, 1000) and engine.calls[0]["dpi"] == 300
    assert result.words[0].image_box == pytest.approx((100, 100, 400, 140))
    assert result.words[0].bbox == pytest.approx((0.1, 0.2, 0.4, 0.28))


def test_boxes_mapped_back_through_deskew() -> None:
    img = Image.new("L", (1200, 800), 255)
    draw = ImageDraw.Draw(img)
    for row in range(8):
        draw.rectangle([150, 120 + row * 70, 1050, 138 + row * 70], fill=20)
    img = img.rotate(3, resample=Image.Resampling.BICUBIC, fillcolor=255)
    captured: dict[str, Any] = {}

    def words(processed: Image.Image) -> list[W]:
        captured["size"] = processed.size
        return [W("edge", 0, 0, processed.width, processed.height)]  # whole processed canvas

    result = ocr_image(img, engine=FakeEngine(words), config=OcrConfig())
    assert "deskew" in result.preprocessing[0]
    assert captured["size"] != img.size  # rotated with an expanded canvas
    assert result.words[0].bbox == (0.0, 0.0, 1.0, 1.0)  # clipped back to the page
    assert "clipped" in result.words[0].notes


def test_out_of_page_and_invalid_geometry_are_reported() -> None:
    words = [W("far", 5000, 5000, 50, 20), W("neg", 10, 10, -5, 20), W("ok", 10, 10, 20, 20)]
    result = ocr_image(_page(), engine=FakeEngine(words), config=NO_PREP)
    far, neg, ok = result.words
    assert far.bbox is None and "outside_image" in far.notes
    assert neg.bbox is None and "invalid_geometry" in neg.notes
    assert ok.bbox is not None
    assert any("outside the image" in w for w in result.warnings)
    assert any("negative size" in w for w in result.warnings)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotation_and_crop_mapping_to_pdf_space(tmp_path: Path, rotation: int) -> None:
    # A rendered, rotated + cropped page; the engine reports a box over a known region.
    path = write_pdf(tmp_path / "r.pdf", [PageSpec(rotate=rotation, crop_box=(50, 300, 562, 750),
                                                   raw_content=b"0 g 100 500 80 40 re f")])
    extraction = extract_native_pdf(path)
    from pathya_document_ai.geometry import pdf_user_space_to_normalized

    transform = extraction.pages[0].transform
    target = pdf_user_space_to_normalized((100, 500, 180, 540), transform)

    def words(processed: Image.Image) -> list[W]:
        w, h = processed.size
        return [W("rect", target[0] * w, target[1] * h, (target[2] - target[0]) * w, (target[3] - target[1]) * h)]

    run = ocr_pdf_pages(path, extraction, engine=FakeEngine(words), config=NO_PREP, dpi=144, force_pages=[0])
    word = run.results[0].words[0]
    back = normalized_to_pdf_user_space(word.bbox, run.results[0].transform)  # type: ignore[arg-type]
    assert back == pytest.approx((100, 500, 180, 540), abs=1.0)  # within ~2 px at 144 DPI


# ------------------------------------------------------ empty, limits, errors


def test_blank_image_skips_engine() -> None:
    engine = FakeEngine([W("ghost", 0, 0, 10, 10)])
    result = ocr_image(Image.new("L", (800, 600), 255), engine=engine)
    assert result.status is OcrPageStatus.BLANK_IMAGE and result.words == () and engine.calls == []


def test_zero_size_and_large_images_rejected() -> None:
    with pytest.raises(OcrImageError):
        ocr_image(Image.new("L", (0, 0)), engine=FakeEngine())
    with pytest.raises(OcrImageError, match="exceeds"):
        ocr_image(_page((3000, 3000)), engine=FakeEngine(), config=OcrConfig(limits=ImageLimits(max_pixels=1_000_000)))


def test_engine_timeout_propagates() -> None:
    engine = FakeEngine(error=OcrTimeoutError("Tesseract exceeded 0.01s"))
    with pytest.raises(OcrTimeoutError):
        ocr_image(_page(), engine=engine, config=NO_PREP)


def test_engine_output_must_be_well_formed() -> None:
    class Broken(FakeEngine):
        def image_to_data(self, image: Any, **kwargs: Any) -> dict[str, list[Any]]:
            return {"text": ["a"], "level": [5]}

    with pytest.raises(OcrEngineError, match="lacks columns"):
        ocr_image(_page(), engine=Broken(), config=NO_PREP)


def test_pytesseract_failures_are_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    import pytesseract

    engine = object.__new__(TesseractEngine)
    engine.config = TesseractConfig()
    engine.info = FAKE_INFO

    def timeout(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_data", timeout)
    with pytest.raises(OcrTimeoutError):
        engine.image_to_data(_page(), languages=("eng",), psm=3, oem=1, dpi=None, timeout_s=0.1)

    def failed(*args: Any, **kwargs: Any) -> None:
        raise pytesseract.TesseractError(1, "Failed loading language 'hin'")

    monkeypatch.setattr(pytesseract, "image_to_data", failed)
    with pytest.raises(OcrEngineError, match="hin"):
        engine.image_to_data(_page(), languages=("eng",), psm=3, oem=1, dpi=None, timeout_s=1)


# ------------------------------------------------- Phase 1/2 integration


def _mixed_pdf(tmp_path: Path) -> Path:
    return write_pdf(tmp_path / "mixed.pdf", [
        PageSpec(texts=[Text(72, 700, "Native text line")]),
        PageSpec(images=[PdfImage(0, 0, 612, 792)]),
        PageSpec(texts=[Text(72, 760, "Fig")], images=[PdfImage(36, 36, 540, 700)]),
    ])


def test_page_selection_follows_phase2_decision(tmp_path: Path) -> None:
    extraction = extract_native_pdf(_mixed_pdf(tmp_path))
    selected, skipped = select_ocr_pages(extraction)
    assert selected == [1] and set(skipped) == {0, 2}
    assert select_ocr_pages(extraction, include_recommended=True)[0] == [1, 2]
    assert select_ocr_pages(extraction, force_pages=[0])[0] == [0, 1]
    with pytest.raises(IndexError):
        select_ocr_pages(extraction, force_pages=[9])


def test_ocr_run_releases_images_and_file(tmp_path: Path) -> None:
    path = _mixed_pdf(tmp_path)
    extraction = extract_native_pdf(path)
    seen: list[Image.Image] = []

    def words(processed: Image.Image) -> list[W]:
        seen.append(processed)
        return [W("scanned", 100, 100, 200, 40)]

    run = ocr_pdf_pages(path, extraction, engine=FakeEngine(words), config=NO_PREP, dpi=72,
                        include_recommended=True)
    assert [r.page_index for r in run.results] == [1, 2] and set(run.skipped) == {0}
    os.remove(path)  # Windows refuses if PDFium still holds the file


def test_ocr_merges_into_phase1_document(tmp_path: Path) -> None:
    path = _mixed_pdf(tmp_path)
    extraction = extract_native_pdf(path)
    native_line = extraction.pages[0].lines[0].bbox

    def words(processed: Image.Image) -> list[W]:
        w, h = processed.size
        x0, y0, x1, y1 = native_line  # type: ignore[misc]
        return [W("Native", x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h, 91),  # duplicates native text
                W("स्कैन", 100, 400, 100, 30, 80, line=(2, 1, 1)),
                W("faint", 100, 500, 100, 30, 40, line=(3, 1, 1))]

    run = ocr_pdf_pages(path, extraction, engine=FakeEngine(words), config=NO_PREP, dpi=72, force_pages=[0, 1])
    base = to_contract_document(extraction, source_uri="asset://t/mixed.pdf")
    document, notes = merge_ocr_into_document(base, run.results)

    page0 = [b for b in document.blocks if b.page_id == document.pages[0].id]
    assert [b.raw_text for b in page0] == ["Native text line", "स्कैन", "faint"]
    assert any("overlaps native text" in n for n in notes)
    ocr_blocks = [b for b in document.blocks if b.provenance.method.value == "ocr"]
    assert {b.language for b in ocr_blocks} == {Language.HINDI, Language.ENGLISH}
    for block in ocr_blocks:
        assert block.confidence.origin is ConfidenceOrigin.ENGINE_REPORTED and block.confidence.score is not None
        assert block.raw_text == block.current_text and block.revision == 1
        assert block.provenance.engine == "tesseract" and block.provenance.model_version
    faint = next(b for b in ocr_blocks if b.raw_text == "faint")
    assert QualityFlag.LOW_CONFIDENCE in faint.quality_flags
    assert Language.HINDI in document.languages

    payload = json.loads(document.model_dump_json())
    jsonschema.Draft202012Validator(build_json_schema(), format_checker=jsonschema.FormatChecker()).validate(payload)
    assert Document.model_validate(payload) == document


def test_null_confidence_line_converts_to_not_available() -> None:
    result = ocr_image(_page(), engine=FakeEngine([W("x", 100, 100, 50, 30, -1)]), config=NO_PREP)
    block = to_contract_blocks(result, page_id=Document.model_fields["id"].default_factory())[0]  # type: ignore[misc]
    assert block.confidence.score is None and block.confidence.origin is ConfidenceOrigin.NOT_AVAILABLE


def test_transform_is_carried_from_rendered_page() -> None:
    t = CoordinateTransform(source_space="pdf_user_space", crop_box=(0, 0, 612, 792), rotation_applied=90)
    result = ocr_image(_page(), engine=FakeEngine([W("x", 1, 1, 5, 5)]), config=NO_PREP, transform=t)
    assert result.transform is t
