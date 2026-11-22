"""Public end-to-end entry point: PDF or image in, validated canonical Document out.

    from pathya_document_ai import extract_document, extract_to_json

    result = extract_document("chapter.pdf", ExtractionOptions(source_uri="asset://p3/123"))
    result.document          # models.Document (contract 1.2.0), already validated
    json_text = result.to_json()   # the Document itself as JSON (no envelope)

Steps for each page, one page at a time:

1. Source: PDF native text and geometry (``pdf.extract_native_pdf``) or an image
   (``image_source.extract_image``); the type is detected from the file signature.
2. OCR (``ocr.ocr_image``) on pages Phase 2 marks ``ocr_required`` or
   ``ocr_recommended`` (``ocr="auto"``), every page (``"always"``) or none.
3. Layout (``layout_docling.DoclingLayoutEngine``) when available, then
   ``layout.build_layout_document``. Without layout the line-level document is
   used and every page records a ``layout_not_run`` warning.
4. Validation: the serialized payload must pass the JSON Schema for its version,
   the Python validator, and the producer-output rules (no backend fields, no
   corrections, revision 1, pipeline review status, roles set).

Engines are detected locally (never downloaded); missing engines are reported
in ``result.engines`` and page warnings, or raise if required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any, Literal

from pathya_document_ai.pdf import PdfLimits


class ProducerContractError(ValueError):
    """The produced document violates the contract or the producer-output rules."""


class EngineUnavailableError(RuntimeError):
    """A required OCR or layout engine is not available."""


@dataclass(frozen=True)
class ExtractionOptions:
    source_uri: str | None = None  # opaque P3 reference; defaults to "local:<file name>"
    title: str | None = None
    languages: tuple[str, ...] = ("hin", "eng")
    ocr: Literal["auto", "always", "never"] = "auto"
    layout: Literal["auto", "required", "never"] = "auto"
    ocr_dpi: float = 300.0
    tessdata_dir: Path | None = None  # else PATHYA_TESSDATA_DIR / Tesseract default
    tesseract_cmd: Path | None = None  # else PATHYA_TESSERACT_CMD / PATH
    docling_artifacts: Path | None = None  # else PATHYA_DOCLING_ARTIFACTS
    pdf_limits: PdfLimits = field(default_factory=PdfLimits)


@dataclass
class ExtractionResult:
    document: Any  # models.Document
    engines: dict[str, str]
    layout_reports: tuple[Any, ...]
    notes: list[str]
    elapsed_s: float

    def to_data(self, target_version: str | None = None, *, drop: tuple[str, ...] = ()) -> dict[str, Any]:
        from pathya_document_ai import models as m

        data = m.export_document_data(self.document, target_version or m.SCHEMA_VERSION, drop=drop)
        validate_document_json(data)
        return data

    def to_json(self, target_version: str | None = None, *, drop: tuple[str, ...] = (), indent: int | None = None) -> str:
        return json.dumps(self.to_data(target_version, drop=drop), ensure_ascii=False, indent=indent)


# ------------------------------------------------------------------ engines


def _ocr_engine(options: ExtractionOptions, notes: list[str]) -> Any:
    if options.ocr == "never":
        return None
    from pathya_document_ai.ocr import TesseractEngine
    from pathya_document_ai.tesseract import OcrError, TesseractConfig

    tessdata = options.tessdata_dir or (Path(os.environ["PATHYA_TESSDATA_DIR"])
                                        if os.environ.get("PATHYA_TESSDATA_DIR") else None)
    try:
        return TesseractEngine(TesseractConfig(executable=options.tesseract_cmd, tessdata_dir=tessdata,
                                               languages=options.languages))
    except OcrError as exc:
        if options.ocr == "always":
            raise EngineUnavailableError(f"OCR required but unavailable: {exc}") from exc
        notes.append(f"OCR unavailable: {exc}")
        return None


def _layout_engine(options: ExtractionOptions, notes: list[str]) -> Any:
    if options.layout == "never":
        return None
    from pathya_document_ai.layout_docling import DoclingConfig, DoclingLayoutEngine, LayoutError

    try:
        return DoclingLayoutEngine(DoclingConfig(artifacts_path=options.docling_artifacts))
    except LayoutError as exc:
        if options.layout == "required":
            raise EngineUnavailableError(f"layout required but unavailable: {exc}") from exc
        notes.append(f"Layout unavailable: {exc}")
        return None


# ------------------------------------------------------------------- run


def extract_document(source: Path | str, options: ExtractionOptions | None = None, *,
                     ocr_engine: Any = "auto", layout_engine: Any = "auto") -> ExtractionResult:
    """Extract ``source`` (PDF, PNG, JPEG or TIFF) into a validated contract Document.

    ``ocr_engine``/``layout_engine``: ``"auto"`` builds them from ``options``;
    pass an engine object (or None to disable) to inject one, e.g. in tests.
    """
    from pathya_document_ai import models as m
    from pathya_document_ai.image_source import detect_media_type, extract_image, load_image_page
    from pathya_document_ai.layout import build_layout_document
    from pathya_document_ai.ocr import OcrConfig, merge_ocr_into_document, ocr_image
    from pathya_document_ai.pdf import check_pdf_file, extract_native_pdf, render_page, to_contract_document
    from pathya_document_ai.quality import OcrDecision

    options = options or ExtractionOptions()
    source = Path(source)
    started = time.monotonic()
    notes: list[str] = []
    media_type = detect_media_type(source)
    is_pdf = media_type == "application/pdf"
    if is_pdf:
        check_pdf_file(source, options.pdf_limits)
        extraction = extract_native_pdf(source, limits=options.pdf_limits)
    else:
        extraction = extract_image(source, limits=options.pdf_limits)

    ocr = _ocr_engine(options, notes) if ocr_engine == "auto" else ocr_engine
    layout = _layout_engine(options, notes) if layout_engine == "auto" else layout_engine
    ocr_config = OcrConfig(languages=options.languages)

    wants_ocr = {OcrDecision.OCR_REQUIRED, OcrDecision.OCR_RECOMMENDED}
    ocr_results: dict[int, Any] = {}
    layouts: dict[int, Any] = {}
    for page in extraction.pages:
        run_ocr = ocr is not None and options.ocr != "never" and (
            options.ocr == "always" or page.ocr.decision in wants_ocr)
        image_mode = layout is not None and layout.choose_mode(page) == "docling_image"
        image = None
        try:
            if run_ocr or image_mode:
                image = (render_page(source, page.page_index, dpi=options.ocr_dpi, limits=options.pdf_limits).image
                         if is_pdf else load_image_page(source, page.page_index))
            if run_ocr:
                dpi = options.ocr_dpi if is_pdf else page.transform.render_dpi
                ocr_results[page.page_index] = ocr_image(image, engine=ocr, config=ocr_config,
                                                         page_index=page.page_index, dpi=dpi, transform=page.transform)
            if layout is not None:
                layouts[page.page_index] = layout.analyze_page(source, page, image)
        finally:
            if image is not None:
                image.close()

    source_uri = options.source_uri or f"local:{source.name}"
    if layout is not None:
        built = build_layout_document(extraction, layouts, ocr_results, source_uri=source_uri, title=options.title)
        document, reports = built.document, built.reports
    else:
        document = to_contract_document(extraction, source_uri=source_uri, title=options.title)
        if ocr_results:
            document, merge_notes = merge_ocr_into_document(document, ocr_results.values(), extraction=extraction)
            notes += merge_notes
        document = _mark_layout_not_run(document, m)
        reports = ()

    engines = {"source": f"{extraction.engine} {extraction.engine_version}",
               "ocr": f"tesseract {ocr.info.version}" if ocr is not None else "not run",
               "layout": f"docling {layout.version}" if layout is not None else "not run"}
    validate_document_json(m.export_document_data(document))
    violations = producer_violations(document)
    if violations:
        raise ProducerContractError(f"producer output rules violated: {violations[:5]}")
    return ExtractionResult(document, engines, tuple(reports), notes, round(time.monotonic() - started, 3))


def _mark_layout_not_run(document: Any, m: Any) -> Any:
    data = document.model_dump()
    for page in data["pages"]:
        page["warnings"].append({"stage": "layout", "code": "layout_not_run",
                                 "message": "Layout analysis was not run: blocks are text lines typed as "
                                            "paragraphs; headings, lists, tables and figures are not identified."})
    return m.Document.model_validate(data)


def extract_to_json(source: Path | str, options: ExtractionOptions | None = None, *,
                    target_version: str | None = None, drop: tuple[str, ...] = (), indent: int | None = None,
                    **engines: Any) -> str:
    """``extract_document`` and serialize the validated Document (the JSON root is the Document)."""
    return extract_document(source, options, **engines).to_json(target_version, drop=drop, indent=indent)


# -------------------------------------------------------------- validation


def validate_document_json(payload: str | bytes | dict[str, Any]) -> Any:
    """Validate a serialized Document with its version's JSON Schema and the Python rules.

    Returns the ``Document``; raises ``ProducerContractError`` (schema) or
    ``pydantic.ValidationError`` (semantic rules).
    """
    import jsonschema

    from pathya_document_ai import models as m
    from pathya_document_ai.schema import build_json_schema

    data = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    data = json.loads(json.dumps(data, default=str))  # plain JSON types, as a consumer would see them
    version = data.get("schema_version")
    if version not in m.SUPPORTED_SCHEMA_VERSIONS:
        raise ProducerContractError(f"unsupported schema_version {version!r}")
    validator = jsonschema.Draft202012Validator(build_json_schema(version), format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        raise ProducerContractError(f"{len(errors)} JSON Schema error(s); first at "
                                    f"/{'/'.join(map(str, first.absolute_path))}: {first.message[:200]}")
    return m.Document.model_validate(data)


def producer_violations(document: Any) -> list[str]:
    """Rules for documents emitted by P1 (stricter than what consumers may store)."""
    from pathya_document_ai import models as m

    problems = []
    if document.schema_version != m.SCHEMA_VERSION:
        problems.append(f"schema_version {document.schema_version} (producer emits {m.SCHEMA_VERSION})")
    if document.corrections:
        problems.append("a producer document has no correction history")
    for b in document.blocks:
        if b.revision != 1 or b.current_text != b.raw_text:
            problems.append(f"block {b.id}: producer output is revision 1 and unedited")
        if b.role is None:
            problems.append(f"block {b.id}: missing role")
        expected = m.pipeline_review_status(b.quality_flags)
        if b.review_status is not expected:
            problems.append(f"block {b.id}: review_status {b.review_status.value}, pipeline rule gives {expected.value}")
    return problems
