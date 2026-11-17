"""Conservative, configurable image preprocessing for OCR (Phase 3).

The input image is never modified: every step produces a new derivative, and
the cumulative affine transform from original pixels to processed pixels is
recorded so OCR boxes can be mapped back exactly.

Defaults are deliberately gentle: grayscale, upscaling only when the source
DPI is low, deskew only when it is clearly justified, and a linear contrast
stretch. Denoising and thresholding are **off by default** because median
filters and aggressive binarization erase decimal points, faint minus signs,
punctuation and Devanagari vowel marks (matras, anusvara, nukta).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from pathya_document_ai.tesseract import OcrError


class OcrImageError(OcrError):
    """The image is empty, too large or otherwise unusable."""


@dataclass(frozen=True)
class ImageLimits:
    max_width: int = 20_000
    max_height: int = 20_000
    max_pixels: int = 80_000_000  # applies to the input and to every derivative


@dataclass(frozen=True)
class PreprocessConfig:
    grayscale: bool = True
    target_dpi: float = 300.0  # upscale toward this when source DPI is known and lower
    max_upscale: float = 2.0
    deskew: bool = True
    deskew_max_angle: float = 5.0
    deskew_min_angle: float = 0.3  # smaller corrections are not worth resampling
    deskew_min_gain: float = 0.10  # projection score must improve by 10% over 0°
    contrast: Literal["none", "autocontrast", "clahe"] = "autocontrast"
    denoise: Literal["none", "nl_means", "median"] = "none"
    denoise_strength: float = 5.0  # nl_means h
    threshold: Literal["none", "adaptive", "otsu"] = "none"
    adaptive_block_size: int = 31
    adaptive_c: float = 10.0  # larger values whiten faint strokes; keep modest


@dataclass(frozen=True)
class Operation:
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        inner = ",".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.name}({inner})" if inner else self.name


@dataclass
class ProcessedImage:
    """A derivative image plus the affine map from original to processed pixels."""

    image: Any  # PIL.Image.Image, mode "L" or "RGB"
    source_size: tuple[int, int]
    operations: tuple[Operation, ...]
    forward: np.ndarray  # 3x3: original pixel -> processed pixel

    def to_original(self, box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """Map a processed-pixel box to the bounding box of its corners in original pixels."""
        x0, y0, x1, y1 = box
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], dtype=float).T
        mapped = np.linalg.inv(self.forward) @ corners
        xs, ys = mapped[0], mapped[1]
        return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())

    def describe(self) -> str:
        return ";".join(op.describe() for op in self.operations) or "none"


def check_image(image: Any, limits: ImageLimits) -> None:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise OcrImageError("image has zero width or height")
    if width > limits.max_width or height > limits.max_height or width * height > limits.max_pixels:
        raise OcrImageError(
            f"image {width}x{height} exceeds limits ({limits.max_width}x{limits.max_height}, "
            f"{limits.max_pixels} pixels)")


def preprocess(
    image: Any,
    config: PreprocessConfig | None = None,
    *,
    source_dpi: float | None = None,
    limits: ImageLimits | None = None,
) -> ProcessedImage:
    """Return a processed derivative of ``image``. ``image`` itself is not modified."""
    import cv2
    from PIL import Image as PILImage, ImageOps

    config = config or PreprocessConfig()
    limits = limits or ImageLimits()
    check_image(image, limits)
    ops: list[Operation] = []
    forward = np.eye(3)
    work = image.copy()

    if work.mode in ("RGBA", "LA", "P"):
        rgba = work.convert("RGBA")
        background = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
        work = PILImage.alpha_composite(background, rgba).convert("RGB")
        ops.append(Operation("flatten_alpha"))
    if config.grayscale and work.mode != "L":
        work = work.convert("L")
        ops.append(Operation("grayscale"))
    elif not config.grayscale and work.mode not in ("RGB", "L"):
        work = work.convert("RGB")

    if source_dpi and source_dpi < config.target_dpi:
        scale = min(config.target_dpi / source_dpi, config.max_upscale)
        new_size = (round(work.width * scale), round(work.height * scale))
        if new_size[0] * new_size[1] > limits.max_pixels or max(new_size) > max(limits.max_width, limits.max_height):
            raise OcrImageError(f"upscaling to {new_size} would exceed image limits")
        sx, sy = new_size[0] / work.width, new_size[1] / work.height
        work = work.resize(new_size, PILImage.Resampling.LANCZOS)
        forward = np.diag([sx, sy, 1.0]) @ forward
        ops.append(Operation("upscale", {"factor": round(scale, 4), "source_dpi": source_dpi}))

    if config.deskew:
        angle, gain = estimate_skew(np.asarray(work.convert("L")), config.deskew_max_angle)
        if abs(angle) >= config.deskew_min_angle and gain >= config.deskew_min_gain:
            arr = np.asarray(work)
            matrix, size = _rotation_matrix(work.width, work.height, angle)
            fill = 255 if work.mode == "L" else (255, 255, 255)
            rotated = cv2.warpAffine(arr, matrix, size, flags=cv2.INTER_CUBIC,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=fill)
            work = PILImage.fromarray(rotated)
            forward = np.vstack([matrix, [0, 0, 1]]) @ forward
            ops.append(Operation("deskew", {"angle_deg": round(angle, 2), "gain": round(gain, 3)}))
        else:
            ops.append(Operation("deskew_skipped", {"angle_deg": round(angle, 2), "gain": round(gain, 3)}))

    if config.contrast == "autocontrast":
        work = ImageOps.autocontrast(work, cutoff=0)  # linear stretch; no clipping of faint ink
        ops.append(Operation("autocontrast"))
    elif config.contrast == "clahe":
        gray = np.asarray(work.convert("L"))
        work = PILImage.fromarray(cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray))
        ops.append(Operation("clahe", {"clip_limit": 2.0}))

    if config.denoise == "nl_means":
        gray = np.asarray(work.convert("L"))
        work = PILImage.fromarray(cv2.fastNlMeansDenoising(gray, None, h=config.denoise_strength))
        ops.append(Operation("denoise_nl_means", {"h": config.denoise_strength}))
    elif config.denoise == "median":
        work = PILImage.fromarray(cv2.medianBlur(np.asarray(work.convert("L")), 3))
        ops.append(Operation("denoise_median", {"ksize": 3}))

    if config.threshold == "adaptive":
        gray = np.asarray(work.convert("L"))
        block = config.adaptive_block_size | 1
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,
                                       block, config.adaptive_c)
        work = PILImage.fromarray(binary)
        ops.append(Operation("adaptive_threshold", {"block": block, "c": config.adaptive_c}))
    elif config.threshold == "otsu":
        gray = np.asarray(work.convert("L"))
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        work = PILImage.fromarray(binary)
        ops.append(Operation("otsu_threshold"))

    check_image(work, limits)
    return ProcessedImage(work, image.size, tuple(ops), forward)


def _rotation_matrix(width: int, height: int, angle: float) -> tuple[np.ndarray, tuple[int, int]]:
    """Rotation about the centre by ``angle`` degrees (counter-clockwise), canvas expanded."""
    import cv2

    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(np.ceil(height * sin + width * cos)), int(np.ceil(height * cos + width * sin))
    matrix[0, 2] += new_w / 2.0 - width / 2.0
    matrix[1, 2] += new_h / 2.0 - height / 2.0
    return matrix, (new_w, new_h)


def estimate_skew(gray: np.ndarray, max_angle: float = 5.0) -> tuple[float, float]:
    """Return ``(correction_angle_deg, gain)`` using a horizontal projection-profile search.

    ``gain`` is the relative improvement of the best angle's profile score over
    0°; callers apply the correction only when it is large enough. Pages with
    too little ink return ``(0.0, 0.0)``.
    """
    import cv2

    scale = min(1.0, 1200.0 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if np.count_nonzero(ink) < 0.001 * ink.size or np.count_nonzero(ink) > 0.6 * ink.size:
        return 0.0, 0.0
    h, w = ink.shape

    def score(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
        rotated = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        rows = rotated.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(rows) ** 2))

    base = score(0.0)
    coarse = np.arange(-max_angle, max_angle + 1e-9, 0.5)
    best = max(coarse, key=score)
    fine = np.arange(best - 0.5, best + 0.5 + 1e-9, 0.1)
    best = float(max(fine, key=score))
    best_score = score(best)
    gain = (best_score - base) / base if base > 0 else 0.0
    return round(best, 2), max(0.0, gain)
