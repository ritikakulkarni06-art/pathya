"""Docling layout adapter (Phase 4). Only this module imports Docling.

Two modes, chosen per page:

* ``docling_pdf`` - Docling's StandardPdfPipeline on the original PDF page
  (layout model + TableFormer + Docling reading order). Used for unrotated
  pages that have a usable native text layer. Verified: geometry matches the
  Phase 2 coordinates on unrotated pages, with or without a CropBox.
* ``docling_image`` - Docling's layout model (docling-ibm-models
  ``LayoutPredictor``) on our own Phase 2 rendering of the displayed page.
  Used for rotated pages and pages without native text (scans). Reason: on
  this Docling version, rotated+cropped pages produced shifted boxes or no
  regions, and image-only pages produced no regions without Docling's OCR.
  This mode provides regions only: no table structure, no reading order, no
  caption links (each is then reported as uncertain/orphan, never guessed).

Model weights are loaded only from a local ``artifacts_path`` (no downloads),
remote services are disabled, and no picture description, formula/code
enrichment or Docling OCR is run.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import os
from pathlib import Path
import time
from typing import Any

from pathya_document_ai.geometry import Box
from pathya_document_ai.layout import (
    LayoutPage,
    LayoutRegion,
    LayoutStatus,
    RegionKind,
    TableCandidate,
    TableCellCandidate,
)

LAYOUT_MODEL_DIR = "docling-project--docling-layout-heron"
TABLE_MODEL_DIR = "docling-project--docling-models"


class LayoutError(Exception):
    """Base class for layout analysis failures."""


class DoclingUnavailableError(LayoutError):
    """Docling or its local model weights are not available."""


@dataclass(frozen=True)
class DoclingConfig:
    artifacts_path: Path | None = None  # else PATHYA_DOCLING_ARTIFACTS
    do_table_structure: bool = True
    document_timeout_s: float = 120.0  # per direct-mode page conversion
    image_dpi: float = 144.0  # rendering for image mode when no image is supplied
    image_min_score: float = 0.3  # raw predictions below are dropped (counted in warnings)
    num_threads: int = 4
    allow_direct_mode: bool = True


_LABELS = {
    "title": RegionKind.TITLE, "section_header": RegionKind.SECTION_HEADER, "text": RegionKind.TEXT,
    "paragraph": RegionKind.TEXT, "reference": RegionKind.TEXT, "list_item": RegionKind.LIST_ITEM,
    "table": RegionKind.TABLE, "document_index": RegionKind.TABLE, "caption": RegionKind.CAPTION,
    "picture": RegionKind.PICTURE, "chart": RegionKind.PICTURE, "formula": RegionKind.FORMULA,
    "page_header": RegionKind.PAGE_HEADER, "page_footer": RegionKind.PAGE_FOOTER,
    "footnote": RegionKind.FOOTNOTE, "code": RegionKind.CODE,
}


def map_label(label: str) -> RegionKind:
    """Docling label (either API spelling) -> RegionKind; unknown labels -> OTHER."""
    key = label.strip().lower().replace("-", "_").replace(" ", "_")
    return _LABELS.get(key, RegionKind.OTHER)


def docling_versions() -> dict[str, str]:
    out = {}
    for name in ("docling", "docling-core", "docling-ibm-models", "docling-parse"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = "missing"
    return out


def resolve_artifacts(config: DoclingConfig) -> Path:
    value = config.artifacts_path or os.environ.get("PATHYA_DOCLING_ARTIFACTS")
    if not value:
        raise DoclingUnavailableError(
            "No Docling model directory configured (DoclingConfig.artifacts_path or PATHYA_DOCLING_ARTIFACTS).")
    path = Path(value)
    missing = [d for d in (LAYOUT_MODEL_DIR, TABLE_MODEL_DIR) if not (path / d).is_dir()]
    if missing:
        raise DoclingUnavailableError(f"Docling model folders {missing} not found in {path}")
    return path


class DoclingLayoutEngine:
    def __init__(self, config: DoclingConfig | None = None) -> None:
        self.config = config or DoclingConfig()
        versions = docling_versions()
        if versions["docling"] == "missing" or versions["docling-ibm-models"] == "missing":
            raise DoclingUnavailableError(f"Docling packages missing: {versions}")
        self.artifacts = resolve_artifacts(self.config)
        self.versions = versions
        weights = self.artifacts / LAYOUT_MODEL_DIR / "model.safetensors"
        self.model_fingerprint = _sha256_prefix(weights) if weights.is_file() else "unknown"
        self._converter: Any = None
        self._predictor: Any = None

    # -- public ------------------------------------------------------------

    @property
    def version(self) -> str:
        return self.versions["docling"]

    def choose_mode(self, page: Any) -> str:
        from pathya_document_ai.quality import OcrDecision

        if self.config.allow_direct_mode and page.rotation.value == 0 \
                and page.ocr.decision is OcrDecision.NATIVE_TEXT:
            return "docling_pdf"
        return "docling_image"

    def analyze_page(self, pdf_path: Path | str, page: Any, image: Any = None) -> LayoutPage:
        """Analyze one Phase 2 page. Never raises for engine failures; returns FAILED instead."""
        started = time.monotonic()
        mode = self.choose_mode(page)
        warnings: list[str] = []
        try:
            if mode == "docling_pdf":
                try:
                    regions = self._direct(Path(pdf_path), page)
                except _FallBack as exc:
                    warnings.append(f"direct mode unusable ({exc}); used image mode")
                    mode = "docling_image"
            if mode == "docling_image":
                regions, dropped = self._image(Path(pdf_path), page, image)
                if dropped:
                    warnings.append(f"{dropped} raw layout predictions below score "
                                    f"{self.config.image_min_score} were ignored")
                warnings.append("image mode: no table structure, engine reading order or caption links")
        except Exception as exc:  # engine failure -> explicit FAILED page, text is still kept
            return LayoutPage(page.page_index, LayoutStatus.FAILED, mode, (), "docling", self.version,
                              LAYOUT_MODEL_DIR, self._params(mode), round(time.monotonic() - started, 3),
                              tuple(warnings + [f"Docling failed: {type(exc).__name__}: {exc}"]))
        return LayoutPage(page.page_index, LayoutStatus.OK, mode, tuple(regions), "docling", self.version,
                          LAYOUT_MODEL_DIR, self._params(mode), round(time.monotonic() - started, 3),
                          tuple(warnings))

    def analyze_document(self, pdf_path: Path | str, extraction: Any,
                         images: dict[int, Any] | None = None) -> dict[int, LayoutPage]:
        """Analyze pages one at a time, reusing any supplied rendered images."""
        images = images or {}
        return {p.page_index: self.analyze_page(pdf_path, p, images.get(p.page_index)) for p in extraction.pages}

    # -- direct mode -------------------------------------------------------

    def _params(self, mode: str) -> dict[str, Any]:
        return {"docling_ibm_models": self.versions["docling-ibm-models"],
                "layout_model_sha256": self.model_fingerprint, "layout_mode": mode,
                "table_structure": self.config.do_table_structure and mode == "docling_pdf"}

    def _get_converter(self) -> Any:
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            options = PdfPipelineOptions(
                artifacts_path=self.artifacts, do_ocr=False, do_table_structure=self.config.do_table_structure,
                enable_remote_services=False, generate_page_images=False, generate_picture_images=False,
                do_picture_classification=False, do_picture_description=False, do_formula_enrichment=False,
                do_code_enrichment=False, document_timeout=self.config.document_timeout_s)
            options.accelerator_options.num_threads = self.config.num_threads
            self._converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
        return self._converter

    def _direct(self, path: Path, page: Any) -> list[LayoutRegion]:
        from docling.datamodel.base_models import ConversionStatus
        from docling_core.types.doc import ContentLayer, DocItem, PictureItem, TableItem

        result = self._get_converter().convert(path, page_range=(page.page_index + 1, page.page_index + 1),
                                              raises_on_error=False)
        if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
            raise RuntimeError(f"conversion status {result.status}: {[str(e) for e in result.errors][:3]}")
        doc = result.document
        page_no = page.page_index + 1
        size = doc.pages.get(page_no).size if page_no in doc.pages else None
        if size is None:
            raise _FallBack("Docling returned no page")
        if abs(size.width - page.width) > 1 or abs(size.height - page.height) > 1:
            raise _FallBack(f"Docling page size {size.width}x{size.height} != displayed {page.width}x{page.height}")

        items = [item for item, _ in doc.iterate_items(included_content_layers=set(ContentLayer))
                 if isinstance(item, DocItem) and item.prov]
        index_of = {item.self_ref: n for n, item in enumerate(items)}
        caption_targets: dict[int, list[int]] = {}
        for n, item in enumerate(items):
            if isinstance(item, (PictureItem, TableItem)):
                for ref in item.captions:
                    if ref.cref in index_of:
                        caption_targets.setdefault(index_of[ref.cref], []).append(n)
        regions = []
        for n, item in enumerate(items):
            label = str(item.label.value)
            bbox = _to_normalized(item.prov[0].bbox, size.width, size.height)
            table = _table_candidate(item.data, size.width, size.height) if isinstance(item, TableItem) else None
            regions.append(LayoutRegion(index=n, kind=map_label(label), source_label=label, bbox=bbox,
                                        confidence=None, engine_order=n, table=table,
                                        caption_targets=tuple(caption_targets.get(n, ()))))
        return regions

    # -- image mode --------------------------------------------------------

    def _get_predictor(self) -> Any:
        if self._predictor is None:
            from docling_ibm_models.layoutmodel.layout_predictor import LayoutPredictor

            self._predictor = LayoutPredictor(str(self.artifacts / LAYOUT_MODEL_DIR), device="cpu",
                                              num_threads=self.config.num_threads)
        return self._predictor

    def _image(self, path: Path, page: Any, image: Any) -> tuple[list[LayoutRegion], int]:
        owned = image is None
        if owned:
            from pathya_document_ai.pdf import render_page

            image = render_page(path, page.page_index, dpi=self.config.image_dpi).image
        try:
            rgb = image.convert("RGB")
            width, height = rgb.size
            predictions = list(self._get_predictor().predict(rgb))
        finally:
            if owned:
                image.close()
        regions, dropped = [], 0
        for p in predictions:
            score = float(p["confidence"])
            if score < self.config.image_min_score:
                dropped += 1
                continue
            bbox = (p["l"] / width, p["t"] / height, p["r"] / width, p["b"] / height)
            label = str(p["label"])
            regions.append(LayoutRegion(index=len(regions), kind=map_label(label), source_label=label,
                                        bbox=bbox, confidence=score))
        return regions, dropped


class _FallBack(Exception):
    pass


def _to_normalized(bbox: Any, width: float, height: float) -> Box | None:
    """Docling BoundingBox (either origin) -> normalized top-left box; None if unusable."""
    try:
        top_left = bbox.to_top_left_origin(page_height=height)
        box = (top_left.l / width, top_left.t / height, top_left.r / width, top_left.b / height)
    except Exception:
        return None
    return box


def _table_candidate(data: Any, width: float, height: float) -> TableCandidate | None:
    if data is None or not getattr(data, "table_cells", None):
        return TableCandidate(None, None, ())
    cells = []
    for cell in data.table_cells:
        cells.append(TableCellCandidate(
            row=cell.start_row_offset_idx, col=cell.start_col_offset_idx,
            row_span=max(1, cell.end_row_offset_idx - cell.start_row_offset_idx),
            col_span=max(1, cell.end_col_offset_idx - cell.start_col_offset_idx),
            is_column_header=bool(cell.column_header), is_row_header=bool(cell.row_header),
            bbox=_to_normalized(cell.bbox, width, height) if cell.bbox is not None else None,
            engine_text=cell.text or ""))
    return TableCandidate(data.num_rows or None, data.num_cols or None, tuple(cells))


def _sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]
