"""Phase 3 preprocessing tests (no OCR engine involved)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from pathya_document_ai.preprocess import (
    ImageLimits,
    OcrImageError,
    PreprocessConfig,
    estimate_skew,
    preprocess,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ocr"


def _text_like(size: tuple[int, int] = (1200, 800), angle: float = 0.0) -> Image.Image:
    """Dark horizontal bars imitating text lines, optionally rotated."""
    img = Image.new("L", size, 255)
    draw = ImageDraw.Draw(img)
    for row in range(8):
        y = 120 + row * 70
        draw.rectangle([150, y, 1050, y + 18], fill=20)
    return img.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255) if angle else img


def _faint_marks() -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """Strong text plus faint small marks: decimal point, minus sign, matra-like dot."""
    img = Image.new("L", (600, 300), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 560, 60], fill=10)  # a strong text line
    marks = {
        "decimal_point": (100, 150, 102, 152),  # 3x3 px, faint
        "minus_sign": (200, 150, 215, 151),  # 16x2 px, faint
        "anusvara_dot": (300, 140, 302, 142),  # small dot above a stroke
        "thin_stroke": (400, 120, 400, 180),  # 1 px wide vertical stroke (danda-like)
    }
    for box in marks.values():
        draw.rectangle(box, fill=150)  # light grey ink
    return img, marks


def _ink_present(image: Image.Image, box: tuple[int, int, int, int], forward: np.ndarray, threshold: int) -> bool:
    x0, y0, x1, y1 = box
    corners = forward @ np.array([[x0, x1], [y0, y1], [1, 1]], dtype=float)
    px0, px1 = int(np.floor(corners[0].min())) - 1, int(np.ceil(corners[0].max())) + 2
    py0, py1 = int(np.floor(corners[1].min())) - 1, int(np.ceil(corners[1].max())) + 2
    region = np.asarray(image.convert("L"))[max(py0, 0):py1, max(px0, 0):px1]
    return bool(region.size) and int(region.min()) < threshold


def test_original_image_is_not_modified() -> None:
    img = _text_like(angle=2.0).convert("RGB")
    before = img.tobytes()
    result = preprocess(img, source_dpi=150)
    assert img.tobytes() == before and img.mode == "RGB"
    assert result.image is not img and result.image.mode == "L"


def test_default_pipeline_is_conservative() -> None:
    names = [op.name for op in preprocess(_text_like()).operations]
    assert names == ["deskew_skipped", "autocontrast"]  # already L; no threshold/denoise by default
    assert PreprocessConfig().threshold == "none" and PreprocessConfig().denoise == "none"


def test_each_operation_is_configurable() -> None:
    cfg = PreprocessConfig(grayscale=False, deskew=False, contrast="none")
    result = preprocess(_text_like().convert("RGB"), cfg)
    assert result.operations == () and result.image.mode == "RGB"
    cfg = PreprocessConfig(contrast="clahe", denoise="nl_means", threshold="adaptive")
    names = [op.name for op in preprocess(_text_like(), cfg).operations]
    assert names == ["deskew_skipped", "clahe", "denoise_nl_means", "adaptive_threshold"]


def test_alpha_is_flattened_onto_white() -> None:
    rgba = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
    result = preprocess(rgba, PreprocessConfig(deskew=False, contrast="none"))
    assert result.operations[0].name == "flatten_alpha"
    assert np.asarray(result.image).min() == 255


@pytest.mark.parametrize("angle", [-3.0, 2.0, 4.0])
def test_deskew_detects_and_corrects_rotation(angle: float) -> None:
    estimated, gain = estimate_skew(np.asarray(_text_like(angle=angle)))
    assert estimated == pytest.approx(-angle, abs=0.3) and gain > 0.1
    result = preprocess(_text_like(angle=angle))
    op = next(op for op in result.operations if op.name == "deskew")
    assert op.params["angle_deg"] == pytest.approx(-angle, abs=0.3)
    residual, _ = estimate_skew(np.asarray(result.image))
    assert abs(residual) <= 0.3


def test_deskew_not_applied_without_justification() -> None:
    blank = Image.new("L", (400, 400), 255)
    assert estimate_skew(np.asarray(blank)) == (0.0, 0.0)
    ops = preprocess(_text_like(angle=0.1)).operations
    assert ops[0].name == "deskew_skipped"


@pytest.mark.parametrize("angle", [0.0, 3.0])
@pytest.mark.parametrize("dpi", [None, 100])
def test_transform_maps_processed_pixels_back(angle: float, dpi: float | None) -> None:
    img = _text_like(angle=angle)
    marker = (900, 700, 911, 711)
    ImageDraw.Draw(img).rectangle(marker, fill=0)
    result = preprocess(img, source_dpi=dpi)
    x0, y0, x1, y1 = marker
    pts = result.forward @ np.array([[x0, x1 + 1], [y0, y1 + 1], [1, 1]], dtype=float)
    processed_box = (pts[0].min(), pts[1].min(), pts[0].max(), pts[1].max())
    back = result.to_original(processed_box)
    assert back == pytest.approx((x0, y0, x1 + 1, y1 + 1), abs=1.0)
    assert _ink_present(result.image, marker, result.forward, 100)


def test_upscale_is_bounded_and_recorded() -> None:
    result = preprocess(_text_like((400, 300)), source_dpi=72)
    op = next(op for op in result.operations if op.name == "upscale")
    assert op.params["factor"] == 2.0  # capped at max_upscale, not 300/72
    assert result.image.size == (800, 600)
    assert not any(op.name == "upscale" for op in preprocess(_text_like((400, 300)), source_dpi=300).operations)


@pytest.mark.parametrize("config", [
    PreprocessConfig(),
    PreprocessConfig(threshold="adaptive"),
    PreprocessConfig(contrast="clahe", denoise="nl_means"),
])
def test_faint_math_marks_survive(config: PreprocessConfig) -> None:
    img, marks = _faint_marks()
    result = preprocess(img, config)
    for name, box in marks.items():
        assert _ink_present(result.image, box, result.forward, 200), f"{name} erased by {result.describe()}"


def test_median_denoise_erases_tiny_marks_which_is_why_it_is_off_by_default() -> None:
    img, marks = _faint_marks()
    result = preprocess(img, PreprocessConfig(denoise="median", contrast="none", deskew=False))
    one_px = (400, 120, 400, 180)
    assert not _ink_present(result.image, one_px, result.forward, 200)
    assert _ink_present(result.image, marks["minus_sign"], result.forward, 200)  # 2 px tall survives


@pytest.mark.parametrize("config", [PreprocessConfig(), PreprocessConfig(threshold="adaptive")])
def test_hindi_vowel_marks_survive_preprocessing(config: PreprocessConfig) -> None:
    import cv2

    img = Image.open(FIXTURES / "hindi.png")
    result = preprocess(img, config)
    before = np.asarray(img.convert("L")) < 128
    after = np.asarray(result.image) < 128
    n_before = cv2.connectedComponents(before.astype(np.uint8))[0]
    n_after = cv2.connectedComponents(after.astype(np.uint8))[0]
    assert n_after >= n_before  # no matra, dot or danda component lost
    assert after.sum() >= 0.9 * before.sum()


def test_empty_and_oversized_images_rejected() -> None:
    with pytest.raises(OcrImageError, match="zero"):
        preprocess(Image.new("L", (0, 10)))
    with pytest.raises(OcrImageError, match="exceeds"):
        preprocess(Image.new("L", (300, 300)), limits=ImageLimits(max_pixels=10_000))
    with pytest.raises(OcrImageError, match="upscaling"):
        preprocess(Image.new("L", (90, 90), 255), source_dpi=100, limits=ImageLimits(max_pixels=10_000))
