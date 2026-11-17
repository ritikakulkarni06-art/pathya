"""Geometry contracts: normalized bounding boxes and page coordinate transforms.

Convention (see docs/p1_contract.md): every block ``bbox`` is
``[x0, y0, x1, y1]`` normalized to ``0..1`` relative to the *displayed* page,
i.e. after the page rotation is applied and within the crop box, with origin at
the top-left corner and y increasing downward. ``x0 < x1`` and ``y0 < y1``.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

UnitFloat = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


def _check_box_order(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    if not x0 < x1:
        raise ValueError(f"bbox requires x0 < x1 (got x0={x0}, x1={x1})")
    if not y0 < y1:
        raise ValueError(f"bbox requires y0 < y1 (got y0={y0}, y1={y1})")
    return box


NormalizedBBox = Annotated[
    tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat],
    AfterValidator(_check_box_order),
    Field(description="[x0, y0, x1, y1] normalized 0..1, top-left origin, y downward, displayed page."),
]
"""A non-degenerate normalized box in displayed-page coordinates."""


class SourceCoordinateSpace(StrEnum):
    PDF_USER_SPACE = "pdf_user_space"  # PDF points, bottom-left origin
    IMAGE_PIXELS = "image_pixels"  # raster pixels, top-left origin


class Rotation(IntEnum):
    """Clockwise display rotation in degrees, as declared by the source."""

    R0 = 0
    R90 = 90
    R180 = 180
    R270 = 270


class CoordinateTransform(BaseModel):
    """How normalized boxes map back onto the original source coordinates.

    To recover a source point: un-normalize against the displayed width/height,
    undo ``rotation`` and add the crop-box offset. For PDF sources the y axis
    must also be flipped because PDF user space has a bottom-left origin.
    """

    model_config = ConfigDict(extra="forbid")

    normalized_origin: Literal["top_left"] = "top_left"
    source_space: SourceCoordinateSpace
    crop_box: tuple[NonNegativeFloat, NonNegativeFloat, NonNegativeFloat, NonNegativeFloat] = Field(
        description="[x0, y0, x1, y1] of the visible region in source units (PDF CropBox or pixel crop)."
    )
    rotation_applied: Rotation = Field(description="Rotation already applied before normalization.")
    render_dpi: float | None = Field(default=None, gt=0, description="DPI of the raster used, if any.")

    @model_validator(mode="after")
    def _crop_is_non_degenerate(self) -> "CoordinateTransform":
        _check_box_order(self.crop_box)
        return self


# ----------------------------------------------------------------- box conversion

Box = tuple[float, float, float, float]
MIN_NORMALIZED_EXTENT = 1e-6
"""Width/height given to zero-size boxes so they satisfy x0 < x1, y0 < y1."""


def validate_normalized_bbox(box: Box) -> Box:
    """Raise ValueError unless ``box`` satisfies the contract's NormalizedBBox rules."""
    for value in box:
        if not (0.0 <= value <= 1.0) or value != value:
            raise ValueError(f"bbox value {value!r} is outside 0..1")
    return _check_box_order(box)


def normalize_display_box(box: Box, visible: Box) -> tuple[Box | None, frozenset[str]]:
    """Normalize a top-left-origin box against the visible (cropped) display region.

    Both inputs use the same top-left display space, e.g. pdfplumber's
    ``(x0, top, x1, bottom)`` and ``page.cropbox``. Returns ``(bbox, notes)``:
    ``bbox`` is None when the box lies entirely outside the visible region.
    ``notes`` may contain ``"clipped"`` (partly outside, clamped to the edge) and
    ``"degenerate"`` (zero size, widened to MIN_NORMALIZED_EXTENT).
    """
    vx0, vtop, vx1, vbottom = visible
    width, height = vx1 - vx0, vbottom - vtop
    if width <= 0 or height <= 0:
        raise ValueError(f"visible region {visible} is degenerate")
    x0, top, x1, bottom = (min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3]))
    if x1 < vx0 or x0 > vx1 or bottom < vtop or top > vbottom:
        return None, frozenset()
    raw = ((x0 - vx0) / width, (top - vtop) / height, (x1 - vx0) / width, (bottom - vtop) / height)
    clamped = tuple(min(1.0, max(0.0, v)) for v in raw)
    notes: set[str] = set()
    if clamped != raw:
        notes.add("clipped")
    nx0, ny0, nx1, ny1 = clamped
    nx0, nx1, widened_x = _widen(nx0, nx1)
    ny0, ny1, widened_y = _widen(ny0, ny1)
    if widened_x or widened_y:
        notes.add("degenerate")
    return validate_normalized_bbox((nx0, ny0, nx1, ny1)), frozenset(notes)


def _widen(lo: float, hi: float) -> tuple[float, float, bool]:
    if hi - lo >= MIN_NORMALIZED_EXTENT:
        return lo, hi, False
    if lo + MIN_NORMALIZED_EXTENT <= 1.0:
        return lo, lo + MIN_NORMALIZED_EXTENT, True
    return 1.0 - MIN_NORMALIZED_EXTENT, 1.0, True


def normalized_to_pdf_user_space(bbox: Box, transform: CoordinateTransform) -> Box:
    """Map a normalized displayed-page box back to PDF user space (points).

    Returns ``(x0, y0, x1, y1)`` with PDF's bottom-left origin. ``rotation_applied``
    is the page's clockwise /Rotate; ``crop_box`` is the CropBox in user space.
    """
    if transform.source_space is not SourceCoordinateSpace.PDF_USER_SPACE:
        raise ValueError("transform does not describe PDF user space")
    cx0, cy0, cx1, cy1 = transform.crop_box
    w, h = cx1 - cx0, cy1 - cy0
    u0, v0, u1, v1 = bbox
    rotation = transform.rotation_applied
    if rotation is Rotation.R0:
        xs, ys = (cx0 + u0 * w, cx0 + u1 * w), (cy1 - v0 * h, cy1 - v1 * h)
    elif rotation is Rotation.R90:
        xs, ys = (cx0 + v0 * w, cx0 + v1 * w), (cy0 + u0 * h, cy0 + u1 * h)
    elif rotation is Rotation.R180:
        xs, ys = (cx1 - u0 * w, cx1 - u1 * w), (cy0 + v0 * h, cy0 + v1 * h)
    else:  # R270
        xs, ys = (cx1 - v0 * w, cx1 - v1 * w), (cy1 - u0 * h, cy1 - u1 * h)
    return (min(xs), min(ys), max(xs), max(ys))


def pdf_user_space_to_normalized(box: Box, transform: CoordinateTransform) -> Box:
    """Inverse of :func:`normalized_to_pdf_user_space` (no clipping or validation)."""
    if transform.source_space is not SourceCoordinateSpace.PDF_USER_SPACE:
        raise ValueError("transform does not describe PDF user space")
    cx0, cy0, cx1, cy1 = transform.crop_box
    w, h = cx1 - cx0, cy1 - cy0
    x0, y0, x1, y1 = box
    rotation = transform.rotation_applied
    if rotation is Rotation.R0:
        us, vs = ((x0 - cx0) / w, (x1 - cx0) / w), ((cy1 - y0) / h, (cy1 - y1) / h)
    elif rotation is Rotation.R90:
        us, vs = ((y0 - cy0) / h, (y1 - cy0) / h), ((x0 - cx0) / w, (x1 - cx0) / w)
    elif rotation is Rotation.R180:
        us, vs = ((cx1 - x0) / w, (cx1 - x1) / w), ((y0 - cy0) / h, (y1 - cy0) / h)
    else:  # R270
        us, vs = ((cy1 - y0) / h, (cy1 - y1) / h), ((cx1 - x0) / w, (cx1 - x1) / w)
    return (min(us), min(vs), max(us), max(vs))
