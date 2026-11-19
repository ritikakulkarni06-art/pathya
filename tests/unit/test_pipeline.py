"""Public entry point (pipeline.extract_document / CLI) with MOCKED OCR and layout engines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
import pytest

from _fake_ocr import FakeEngine, W
from _layout_fixtures import write_textbook
from _pdf_factory import Image as PdfImage, PageSpec, Text, write_pdf
from pathya_document_ai import __main__ as cli
from pathya_document_ai.geometry import normalized_to_image_pixels
from pathya_document_ai.image_source import ImageSourceError, detect_media_type, extract_image, load_image_page
from pathya_document_ai.layout import LayoutPage, LayoutRegion, LayoutStatus, RegionKind
from pathya_document_ai.models import CONTRACT_FAMILY, SCHEMA_VERSION, BlockRole, Document, QualityFlag, ReviewStatus
from pathya_document_ai.pdf import PdfLimitError
from pathya_document_ai.pipeline import (
    EngineUnavailableError,
    ExtractionOptions,
    ProducerContractError,
    extract_document,
    extract_to_json,
    producer_violations,
    validate_document_json,
)

NO_ENGINES = {"ocr_engine": None, "layout_engine": None}


class FakeLayout:
    """Region per Phase 2 line group; first line on a page is a heading, a 'Page 7' line a footer."""

    version = "mock-1"

    def choose_mode(self, page: Any) -> str:
        return "docling_pdf" if page.lines else "docling_image"

    def analyze_page(self, source: Any, page: Any, image: Any = None) -> LayoutPage:
        regions = []
        for i, line in enumerate(sorted((l for l in page.lines if l.bbox), key=lambda l: l.bbox[1])):
            x0, y0, x1, y1 = line.bbox
            kind = RegionKind.SECTION_HEADER if i == 0 else RegionKind.TEXT
            label = "section_header" if i == 0 else "text"
            if line.text.startswith("Page "):
                kind, label = RegionKind.PAGE_FOOTER, "page_footer"
            regions.append(LayoutRegion(i, kind, label, (x0 - 0.005, y0 - 0.005, x1 + 0.005, y1 + 0.005), 0.95,
                                        engine_order=i))
        return LayoutPage(page.page_index, LayoutStatus.OK, self.choose_mode(page), tuple(regions), "mock-layout",
                          self.version, "mock", {}, 0.0)


# ------------------------------------------------------------- direct response


def test_returns_the_document_directly_and_json_root_is_the_document(tmp_path: Path) -> None:
    pdf = write_textbook(tmp_path / "tb.pdf")
    result = extract_document(pdf, ExtractionOptions(source_uri="asset://p3/42"), **NO_ENGINES)
    assert isinstance(result.document, Document)
    data = json.loads(result.to_json())
    assert data["schema_version"] == SCHEMA_VERSION and data["contract_family"] == CONTRACT_FAMILY
    assert set(data) == set(Document.model_fields)  # no envelope around the Document
    assert data["source_asset"]["uri"] == "asset://p3/42" and data["integration"] is None
    assert validate_document_json(result.to_json()) == result.document
    assert producer_violations(result.document) == []
    assert result.engines == {"source": result.engines["source"], "ocr": "not run", "layout": "not run"}
    assert all(any(w.code == "layout_not_run" for w in p.warnings) for p in result.document.pages)


def test_extract_to_json_and_explicit_1_1_export(tmp_path: Path) -> None:
    import jsonschema

    from pathya_document_ai.schema import build_json_schema

    pdf = write_textbook(tmp_path / "tb.pdf")
    text = extract_to_json(pdf, target_version="1.1.0", **NO_ENGINES)
    data = json.loads(text)
    assert data["schema_version"] == "1.1.0" and "contract_family" not in data
    jsonschema.Draft202012Validator(build_json_schema("1.1.0")).validate(data)  # the frozen 1.1.0 schema


def test_layout_path_sets_heading_levels_roles_and_review_status(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "h.pdf", [
        PageSpec(texts=[Text(72, 740, "Big Chapter Title", 22), Text(72, 700, "Body text on the page.", 11),
                        Text(72, 40, "Page 7", 9)]),
        PageSpec(texts=[Text(72, 740, "Smaller Section", 14), Text(72, 700, "More body text here.", 11)]),
    ])
    doc = extract_document(pdf, ocr_engine=None, layout_engine=FakeLayout()).document
    headings = {b.raw_text: b.heading_level for b in doc.blocks if b.block_type.value == "heading"}
    assert headings == {"Big Chapter Title": 1, "Smaller Section": 2}
    footer = next(b for b in doc.blocks if b.raw_text == "Page 7")
    assert footer.role is BlockRole.PAGE_FOOTER and footer.block_type.value == "paragraph"
    assert all(b.role is BlockRole.BODY for b in doc.blocks if b.raw_text != "Page 7")
    assert producer_violations(doc) == []


def test_ocr_path_flags_uncertain_critical_symbols(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "scan.pdf", [PageSpec(images=[PdfImage(0, 0, 612, 792)])])
    words = [W("Speed", 100, 100, 80, 30, 96), W("4.5", 190, 100, 40, 30, 71), W("m/s", 240, 100, 50, 30, 95),
             W("Plain", 100, 200, 80, 30, 97, line=(2, 1, 1)), W("words", 190, 200, 80, 30, 96, line=(2, 1, 1))]
    result = extract_document(pdf, ExtractionOptions(ocr_dpi=72), ocr_engine=FakeEngine(words), layout_engine=None)
    doc = result.document
    assert doc.pages[0].status.value == "ok" and result.engines["ocr"] == "tesseract 5.4.0-fake"
    by_text = {b.raw_text: b for b in doc.blocks}
    critical = by_text["Speed 4.5 m/s"]
    assert QualityFlag.CRITICAL_SYMBOL_UNCERTAIN in critical.quality_flags
    assert critical.review_status is ReviewStatus.NEEDS_REVIEW
    assert QualityFlag.CRITICAL_SYMBOL_UNCERTAIN not in by_text["Plain words"].quality_flags
    assert by_text["Plain words"].review_status is ReviewStatus.UNREVIEWED


def test_scanned_page_without_ocr_stays_needs_ocr(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "scan.pdf", [PageSpec(images=[PdfImage(0, 0, 612, 792)])])
    doc = extract_document(pdf, ExtractionOptions(ocr="never"), **NO_ENGINES).document
    assert doc.pages[0].status.value == "needs_ocr" and doc.blocks == []


def test_required_engines_raise_when_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = write_textbook(tmp_path / "tb.pdf")
    monkeypatch.setenv("PATHYA_TESSERACT_CMD", str(tmp_path / "missing.exe"))
    monkeypatch.delenv("PATHYA_DOCLING_ARTIFACTS", raising=False)
    with pytest.raises(EngineUnavailableError, match="OCR required"):
        extract_document(pdf, ExtractionOptions(ocr="always"), layout_engine=None)
    with pytest.raises(EngineUnavailableError, match="layout required"):
        extract_document(pdf, ExtractionOptions(layout="required"), ocr_engine=None)
    result = extract_document(pdf, ExtractionOptions(), )  # auto: both missing, reported not hidden
    assert result.engines["ocr"] == result.engines["layout"] == "not run"
    assert any("OCR unavailable" in n for n in result.notes) and any("Layout unavailable" in n for n in result.notes)


def test_producer_rules_reject_backend_fields_and_wrong_review_status(tmp_path: Path) -> None:
    doc = extract_document(write_textbook(tmp_path / "tb.pdf"), **NO_ENGINES).document
    data = doc.model_dump()
    data["integration"] = {"document_revision": 2, "backend_document_id": "x"}
    data["blocks"][0]["review_status"] = "approved"
    problems = producer_violations(Document.model_validate(data))
    assert any("backend-owned" in p for p in problems) and any("pipeline rule" in p for p in problems)
    with pytest.raises(ProducerContractError, match="JSON Schema"):
        bad = json.loads(doc.model_dump_json())
        bad["blocks"][0]["role"] = "sidebar"
        validate_document_json(bad)


# ------------------------------------------------------------------ images


def _page_image(path: Path, fmt: str, size: tuple[int, int] = (600, 400), **save: Any) -> Path:
    img = Image.new("RGB", size, "white")
    ImageDraw.Draw(img).rectangle([50, 60, 200, 90], fill="black")
    img.save(path, format=fmt, **save)
    return path


@pytest.mark.parametrize(("fmt", "suffix", "media"), [("PNG", ".png", "image/png"), ("JPEG", ".jpg", "image/jpeg"),
                                                       ("TIFF", ".tif", "image/tiff")])
def test_image_formats_by_signature(tmp_path: Path, fmt: str, suffix: str, media: str) -> None:
    path = _page_image(tmp_path / f"page{suffix}", fmt, dpi=(200, 200))
    assert detect_media_type(path) == media
    ex = extract_image(path)
    page = ex.pages[0]
    assert (ex.media_type, ex.units, page.width, page.height) == (media, "px", 600.0, 400.0)
    assert page.transform.source_space.value == "image_pixels" and page.transform.render_dpi == pytest.approx(200, abs=1)
    assert page.ocr.decision.value == "ocr_required"


def test_extension_is_ignored_and_unsupported_files_rejected(tmp_path: Path) -> None:
    disguised = _page_image(tmp_path / "really_png.pdf", "PNG")
    assert detect_media_type(disguised) == "image/png"
    text = tmp_path / "notes.png"
    text.write_text("hello", encoding="utf-8")
    with pytest.raises(ImageSourceError, match="unsupported"):
        detect_media_type(text)
    corrupt = tmp_path / "broken.png"
    corrupt.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 20)
    with pytest.raises(ImageSourceError, match="could not be read"):
        extract_image(corrupt)


def test_multi_frame_tiff_becomes_pages(tmp_path: Path) -> None:
    frames = [Image.new("L", (300, 200), 255), Image.new("L", (200, 300), 255)]
    path = tmp_path / "two.tif"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    ex = extract_image(path)
    assert [(p.page_index, p.width, p.height) for p in ex.pages] == [(0, 300.0, 200.0), (1, 200.0, 300.0)]


def test_image_pixel_limit_checked_before_decoding(tmp_path: Path) -> None:
    from pathya_document_ai.preprocess import ImageLimits

    path = _page_image(tmp_path / "big.png", "PNG", size=(800, 800))
    with pytest.raises(PdfLimitError, match="exceeds image limits"):
        extract_image(path, image_limits=ImageLimits(max_pixels=100_000))


@pytest.mark.parametrize(("orientation", "rotation"), [(1, 0), (3, 180), (6, 90), (8, 270)])
def test_exif_orientation_and_image_pixel_mapping(tmp_path: Path, orientation: int, rotation: int) -> None:
    stored = Image.new("L", (600, 400), 255)
    ImageDraw.Draw(stored).rectangle([50, 60, 199, 89], fill=0)  # known box in STORED pixels
    exif = stored.getexif()
    exif[0x0112] = orientation
    path = tmp_path / f"o{orientation}.jpg"
    stored.save(path, format="JPEG", exif=exif, quality=95)
    page = extract_image(path).pages[0]
    assert page.transform.rotation_applied.value == rotation
    upright = load_image_page(path, 0)
    assert (page.width, page.height) == tuple(map(float, upright.size))
    dark = np.argwhere(np.asarray(upright.convert("L")) < 128)
    (y0, x0), (y1, x1) = dark.min(axis=0), dark.max(axis=0) + 1
    normalized = (x0 / upright.width, y0 / upright.height, x1 / upright.width, y1 / upright.height)
    assert normalized_to_image_pixels(normalized, page.transform) == pytest.approx((50, 60, 200, 90), abs=3)


def test_mirrored_exif_orientation_rejected(tmp_path: Path) -> None:
    stored = Image.new("L", (100, 100), 255)
    exif = stored.getexif()
    exif[0x0112] = 2
    path = tmp_path / "mirror.jpg"
    stored.save(path, format="JPEG", exif=exif)
    with pytest.raises(ImageSourceError, match="mirrored"):
        extract_image(path)


def test_image_entry_point_with_mocked_ocr(tmp_path: Path) -> None:
    path = _page_image(tmp_path / "page.png", "PNG")
    words = [W("प्रकाश", 50, 60, 150, 30, 93), W("light", 210, 60, 80, 30, 95)]
    doc = extract_document(path, ExtractionOptions(source_uri="asset://img"), ocr_engine=FakeEngine(words),
                           layout_engine=None).document
    assert doc.source_asset.media_type.value == "image/png" and doc.pages[0].units == "px"
    assert doc.pages[0].status.value == "ok" and doc.blocks[0].raw_text == "प्रकाश light"
    assert doc.blocks[0].language.value == "mul"


# --------------------------------------------------------------------- CLI


def test_cli_extract_validate_and_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    pdf = write_textbook(tmp_path / "tb.pdf")
    out = tmp_path / "doc.json"
    assert cli.main(["extract", str(pdf), "-o", str(out), "--ocr", "never", "--layout", "never",
                     "--source-uri", "asset://cli"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["source_asset"]["uri"] == "asset://cli"
    assert cli.main(["validate", str(out)]) == 0

    bad = json.loads(out.read_text(encoding="utf-8"))
    bad["blocks"][0]["bbox"] = [0.5, 0.1, 0.2, 0.2]  # passes JSON Schema, fails Python invariant
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    assert cli.main(["validate", str(tmp_path / "bad.json")]) == 3

    junk = tmp_path / "junk.txt"
    junk.write_text("not a document source", encoding="utf-8")
    assert cli.main(["extract", str(junk), "--ocr", "never", "--layout", "never"]) == 2
    # layout_not_run warnings cannot be represented in 1.0.0: loud failure, not a silent drop
    assert cli.main(["extract", str(pdf), "--ocr", "never", "--layout", "never", "--target-version", "1.0.0"]) == 5
    monkeypatch.setenv("PATHYA_TESSERACT_CMD", str(tmp_path / "missing.exe"))
    assert cli.main(["extract", str(pdf), "--ocr", "always", "--layout", "never"]) == 4


def test_package_exports_are_lazy() -> None:
    import pathya_document_ai

    assert pathya_document_ai.extract_document is extract_document
    with pytest.raises(AttributeError):
        pathya_document_ai.no_such_name  # noqa: B018
