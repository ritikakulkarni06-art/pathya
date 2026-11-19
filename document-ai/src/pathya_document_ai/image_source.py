"""Image sources (PNG, JPEG, TIFF) for the extraction entry point.

An image page has no native text layer: each page is marked ``ocr_required``
and its geometry is in **image pixels** (``source_space = image_pixels``,
``units = "px"``). EXIF orientation is applied so normalized boxes refer to the
upright displayed image; the applied rotation is recorded in
``transform.rotation_applied``. Mirrored EXIF orientations are rejected rather
than guessed. Multi-frame TIFFs become one page per frame.

The file type is decided by signature, never by extension, and pixel limits are
checked from the header before any pixel data is decoded.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from pathya_document_ai.geometry import CoordinateTransform, Rotation, SourceCoordinateSpace
from pathya_document_ai.pdf import (
    NotPdfError,
    PageExtraction,
    PageStatus,
    PdfExtraction,
    PdfInputError,
    PdfLimitError,
    PdfLimits,
)
from pathya_document_ai.preprocess import ImageLimits
from pathya_document_ai.quality import NativeTextMetrics, OcrAssessment, OcrDecision, OcrReason, OcrThresholds

IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}
# EXIF orientation -> clockwise rotation needed to display the stored pixels upright.
_EXIF_ROTATION = {1: 0, 3: 180, 6: 90, 8: 270}


class ImageSourceError(PdfInputError):
    """The image cannot be used as an extraction source."""


def detect_media_type(path: Path | str) -> str:
    """Return the source media type from the file signature (PDF or a supported image)."""
    with Path(path).open("rb") as handle:
        head = handle.read(1024)
    if not head:
        raise NotPdfError(f"{Path(path).name} is empty")
    if b"%PDF-" in head:
        return "application/pdf"
    for signature, media_type in IMAGE_SIGNATURES.items():
        if head.startswith(signature):
            return media_type
    raise ImageSourceError(f"{Path(path).name}: unsupported file type (PDF, PNG, JPEG or TIFF only)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _orientation(image: Any) -> int:
    try:
        return int(image.getexif().get(0x0112, 1))
    except Exception:  # unreadable EXIF: treat as unrotated, never guess
        return 1


def load_image_page(path: Path | str, index: int, limits: ImageLimits | None = None) -> Any:
    """Decode frame ``index`` as an upright RGB image (caller closes it)."""
    from PIL import Image, ImageOps

    limits = limits or ImageLimits()
    with Image.open(path) as source:
        source.seek(index)
        width, height = source.size
        if width * height > limits.max_pixels or max(width, height) > max(limits.max_width, limits.max_height):
            raise PdfLimitError(f"image frame {index} is {width}x{height}; exceeds image limits")
        frame = source.copy()
    upright = ImageOps.exif_transpose(frame)
    if upright is not frame:
        frame.close()
    rgb = upright.convert("RGB")
    if rgb is not upright:
        upright.close()
    return rgb


def extract_image(path: Path | str, *, limits: PdfLimits | None = None,
                  image_limits: ImageLimits | None = None) -> PdfExtraction:
    """Describe an image file as extraction pages (no native text; OCR required)."""
    from PIL import Image, __version__ as pillow_version

    limits = limits or PdfLimits()
    image_limits = image_limits or ImageLimits()
    path = Path(path)
    media_type = detect_media_type(path)
    if media_type == "application/pdf":
        raise ImageSourceError(f"{path.name} is a PDF; use extract_native_pdf")
    size = path.stat().st_size
    if size > limits.max_file_bytes:
        raise PdfLimitError(f"{path.name} is {size} bytes; limit is {limits.max_file_bytes}")
    pages = []
    try:
        with Image.open(path) as image:
            frames = getattr(image, "n_frames", 1)
            if frames > limits.max_pages:
                raise PdfLimitError(f"{path.name} has {frames} frames; limit is {limits.max_pages}")
            for index in range(frames):
                image.seek(index)
                stored_w, stored_h = image.size
                if stored_w * stored_h > image_limits.max_pixels:
                    raise PdfLimitError(f"frame {index} is {stored_w}x{stored_h}; exceeds image limits")
                orientation = _orientation(image)
                if orientation not in _EXIF_ROTATION:
                    raise ImageSourceError(f"frame {index}: mirrored EXIF orientation {orientation} is not supported")
                rotation = _EXIF_ROTATION[orientation]
                width, height = (stored_h, stored_w) if rotation in (90, 270) else (stored_w, stored_h)
                dpi = image.info.get("dpi")
                render_dpi = float(dpi[0]) if dpi and dpi[0] and dpi[0] > 1 else None
                transform = CoordinateTransform(
                    source_space=SourceCoordinateSpace.IMAGE_PIXELS, crop_box=(0.0, 0.0, float(stored_w), float(stored_h)),
                    rotation_applied=Rotation(rotation), render_dpi=render_dpi)
                metrics = NativeTextMetrics(0, 0, 0, 1, 1.0, 0, 0.0)
                pages.append(PageExtraction(
                    page_index=index, page_label=None, width=float(width), height=float(height),
                    rotation=Rotation(rotation), transform=transform, status=PageStatus.OK, text="", words=(),
                    lines=(), stream_order=(), geometric_order=(),
                    ocr=OcrAssessment(OcrDecision.OCR_REQUIRED, (OcrReason.NO_NATIVE_TEXT, OcrReason.IMAGE_ONLY_PAGE),
                                      metrics, OcrThresholds())))
    except (PdfInputError, ImageSourceError):
        raise
    except Exception as exc:  # truncated or corrupt image data
        raise ImageSourceError(f"{path.name} could not be read as an image: {exc}") from exc
    return PdfExtraction(
        source_path=str(path), sha256=_sha256(path), file_bytes=size, page_count=len(pages), pages=tuple(pages),
        engine="pillow", engine_version=pillow_version, parameters={"source": "image"},
        created_at=datetime.now(timezone.utc), media_type=media_type, units="px")
