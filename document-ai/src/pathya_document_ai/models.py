"""Versioned Pathya P1 content contract (Pydantic v2).

These models are the shared structure P1 produces and P2/P3 consume. They hold
data and validation only: no extraction, OCR, persistence or transactions.
Field meanings and rules are documented in ``docs/p1_contract.md``.
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from pathya_document_ai.geometry import CoordinateTransform, NormalizedBBox, Rotation

SCHEMA_VERSION = "1.1.0"
"""Semantic version produced by this code. See docs/p1_contract.md#versioning."""

SUPPORTED_SCHEMA_VERSIONS = ("1.0.0", "1.1.0")
"""Versions accepted on input. 1.0.0 documents are validated against 1.0.0 rules."""

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ScalarParam = str | int | float | bool | None


def new_id() -> UUID:
    """Return a random (UUID4) identifier. IDs never derive from content."""
    return uuid4()


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=False)


# --------------------------------------------------------------------------- enums


class Language(StrEnum):
    """BCP 47 language tags supported by the contract."""

    ENGLISH = "en"
    HINDI = "hi"
    MULTIPLE = "mul"  # block mixes languages, e.g. Hindi text with English terms
    UNDETERMINED = "und"  # language not known (e.g. figure, numeric table cell)


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_CELL = "table_cell"
    EQUATION = "equation"
    FIGURE = "figure"
    CAPTION = "caption"


TEXT_BLOCK_TYPES = frozenset(
    {BlockType.HEADING, BlockType.PARAGRAPH, BlockType.LIST_ITEM, BlockType.TABLE_CELL, BlockType.CAPTION}
)


class EdgeType(StrEnum):
    CONTAINS = "contains"
    PRECEDES = "precedes"
    CAPTION_OF = "caption_of"
    REFERS_TO = "refers_to"
    HEADER_FOR = "header_for"
    SUPERSEDES = "supersedes"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConfidenceOrigin(StrEnum):
    ENGINE_REPORTED = "engine_reported"  # score emitted by OCR/layout engine
    MODEL_ESTIMATED = "model_estimated"  # score from a separate calibration model
    HEURISTIC = "heuristic"  # rule-based score; must state its reason
    NOT_AVAILABLE = "not_available"  # no meaningful score (e.g. native PDF text)


class QualityFlag(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    POSSIBLE_OCR_ERROR = "possible_ocr_error"
    MIXED_SCRIPT = "mixed_script"
    LANGUAGE_UNCERTAIN = "language_uncertain"
    READING_ORDER_UNCERTAIN = "reading_order_uncertain"
    GEOMETRY_UNCERTAIN = "geometry_uncertain"
    TABLE_STRUCTURE_UNCERTAIN = "table_structure_uncertain"
    MATH_NEEDS_REVIEW = "math_needs_review"
    UNSUPPORTED_CONTENT = "unsupported_content"
    EMPTY_TEXT = "empty_text"
    # Added in 1.1.0 (layout analysis):
    BLOCK_TYPE_UNCERTAIN = "block_type_uncertain"
    MISSING_GEOMETRY = "missing_geometry"  # some source parts lacked valid geometry
    OVERLAPPING_REGIONS = "overlapping_regions"
    ORPHAN_CAPTION = "orphan_caption"
    DUPLICATE_CONTENT = "duplicate_content"  # native and OCR text covered the same area


QUALITY_FLAGS_ADDED_IN_1_1 = frozenset({
    QualityFlag.BLOCK_TYPE_UNCERTAIN, QualityFlag.MISSING_GEOMETRY, QualityFlag.OVERLAPPING_REGIONS,
    QualityFlag.ORPHAN_CAPTION, QualityFlag.DUPLICATE_CONTENT,
})


class ExtractionMethod(StrEnum):
    NATIVE_PDF_TEXT = "native_pdf_text"
    OCR = "ocr"
    LAYOUT_MODEL = "layout_model"
    HUMAN = "human"
    DERIVED = "derived"  # computed from other P1 outputs (e.g. inferred edges)


class MediaType(StrEnum):
    PDF = "application/pdf"
    PNG = "image/png"
    JPEG = "image/jpeg"
    TIFF = "image/tiff"


class AnnotationOrigin(StrEnum):
    SOURCE = "source"  # printed in the textbook
    HUMAN = "human"  # written by a reviewer
    MODEL_GENERATED = "model_generated"  # machine-written; must be reviewed before trusted


class CorrectionOperation(StrEnum):
    REPLACE_TEXT = "replace_text"
    SET_LANGUAGE = "set_language"
    SET_REVIEW_STATUS = "set_review_status"


# --------------------------------------------------------------- shared value types


class Confidence(_Model):
    """Optional quality score. ``score`` is null when no meaningful value exists."""

    score: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    origin: ConfidenceOrigin
    reason: str | None = Field(default=None, description="Why the score is absent or how it was derived.")

    @model_validator(mode="after")
    def _consistent(self) -> "Confidence":
        if self.origin is ConfidenceOrigin.NOT_AVAILABLE and self.score is not None:
            raise ValueError("confidence origin 'not_available' requires score to be null")
        if self.origin is not ConfidenceOrigin.NOT_AVAILABLE and self.score is None:
            raise ValueError(f"confidence origin '{self.origin}' requires a score")
        if self.score is None and not self.reason:
            raise ValueError("a null confidence score requires a reason")
        if self.origin is ConfidenceOrigin.HEURISTIC and not self.reason:
            raise ValueError("heuristic confidence requires a reason")
        return self

    @classmethod
    def unavailable(cls, reason: str) -> "Confidence":
        return cls(score=None, origin=ConfidenceOrigin.NOT_AVAILABLE, reason=reason)


class Provenance(_Model):
    """Which method/engine/version produced a value, with its parameters."""

    method: ExtractionMethod
    engine: str | None = Field(default=None, description="e.g. 'tesseract', 'pdfplumber', 'docling'.")
    engine_version: str | None = None
    model: str | None = Field(default=None, description="Model or traineddata name, if any.")
    model_version: str | None = None
    parameters: dict[str, ScalarParam] = Field(default_factory=dict)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _engine_required(self) -> "Provenance":
        machine = {ExtractionMethod.NATIVE_PDF_TEXT, ExtractionMethod.OCR, ExtractionMethod.LAYOUT_MODEL}
        if self.method in machine and not (self.engine and self.engine_version):
            raise ValueError(f"provenance method '{self.method}' requires engine and engine_version")
        if self.model_version and not self.model:
            raise ValueError("model_version requires model")
        return self


class SourceAsset(_Model):
    """Original uploaded file, referenced by ID and hash rather than embedded."""

    id: UUID = Field(default_factory=new_id)
    uri: NonEmptyStr = Field(description="Opaque storage reference assigned by P3.")
    media_type: MediaType
    sha256: Sha256Hex


# ------------------------------------------------------------- type-specific metadata


class TableMeta(_Model):
    """Attached to blocks of type ``table``.

    Since 1.1.0 a table whose structure could not be reconstructed is an
    *uncertain table candidate*: ``cell_ids`` is empty and both counts are
    null (never guessed). Such a block must carry ``table_structure_uncertain``.
    """

    row_count: int | None = Field(default=None, ge=1)
    column_count: int | None = Field(default=None, ge=1)
    cell_ids: list[UUID] = Field(default_factory=list, description="IDs of this table's table_cell blocks.")

    @model_validator(mode="after")
    def _structure(self) -> "TableMeta":
        if len(set(self.cell_ids)) != len(self.cell_ids):
            raise ValueError("table cell_ids must be unique")
        if self.cell_ids and (self.row_count is None or self.column_count is None):
            raise ValueError("a table with cells requires row_count and column_count")
        if not self.cell_ids and (self.row_count is not None or self.column_count is not None):
            raise ValueError("an uncertain table (no cells) must leave row_count and column_count null")
        return self

    @property
    def is_uncertain_candidate(self) -> bool:
        return not self.cell_ids


class TableCellMeta(_Model):
    """Attached to blocks of type ``table_cell``. Indices are zero-based."""

    table_id: UUID
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False
    header_cell_ids: list[UUID] = Field(default_factory=list, description="Header cells that label this cell.")


class EquationMeta(_Model):
    """Conservative equation record. The source crop (block page + bbox) is canonical.

    MathML is only present after human approval; it is never machine-invented
    content presented as fact. ``spoken_fallback`` describes, not solves.
    """

    source_crop_uri: str | None = Field(default=None, description="Optional stored crop image reference.")
    source_text: str | None = Field(default=None, description="Text exactly as extracted, if any.")
    mathml: str | None = None
    mathml_review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    spoken_fallback: str | None = None
    spoken_fallback_origin: AnnotationOrigin | None = None
    spoken_fallback_review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @model_validator(mode="after")
    def _conservative(self) -> "EquationMeta":
        if self.mathml is not None:
            if self.mathml_review_status is not ReviewStatus.APPROVED:
                raise ValueError("mathml may only be stored once mathml_review_status is 'approved'")
            if not self.mathml.lstrip().startswith("<math"):
                raise ValueError("mathml must be a <math> element")
        if (self.spoken_fallback is None) != (self.spoken_fallback_origin is None):
            raise ValueError("spoken_fallback and spoken_fallback_origin must be set together")
        return self


class TextAnnotation(_Model):
    text: NonEmptyStr
    language: Language
    origin: AnnotationOrigin
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED


class FigureMeta(_Model):
    """Figure accessibility text. Caption, alt text and long description stay separate."""

    source_caption: str | None = Field(default=None, description="Caption text as printed, if any.")
    caption_block_id: UUID | None = Field(default=None, description="The caption block, if extracted.")
    alt_text: TextAnnotation | None = Field(default=None, description="Short (one-sentence) description.")
    extended_description: TextAnnotation | None = None

    @model_validator(mode="after")
    def _alt_text_short(self) -> "FigureMeta":
        if self.alt_text and len(self.alt_text.text) > 250:
            raise ValueError("alt_text must be at most 250 characters; use extended_description")
        return self


# --------------------------------------------------------------------- core models


class PageStatus(StrEnum):
    """Added in 1.1.0: how completely a page was processed."""

    OK = "ok"  # content extracted (native and/or OCR)
    BLANK = "blank"  # nothing to extract (no text, images or drawings that could hold text)
    NEEDS_OCR = "needs_ocr"  # content is likely in images but OCR was not run: blocks may be missing
    PARTIAL = "partial"  # a stage failed (e.g. layout); text kept, structure may be wrong
    FAILED = "failed"  # extraction failed; the page's content is missing


class ProcessingStage(StrEnum):
    EXTRACTION = "extraction"
    OCR = "ocr"
    LAYOUT = "layout"
    MERGE = "merge"


class PageWarning(_Model):
    """Added in 1.1.0: a machine-readable processing warning carried in the contract."""

    stage: ProcessingStage
    code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    message: NonEmptyStr


class Page(_Model):
    id: UUID = Field(default_factory=new_id)
    document_id: UUID
    page_index: int = Field(ge=0, description="Zero-based physical index in the source file.")
    page_label: str | None = Field(default=None, description="Printed/logical label, e.g. 'iv' or '12'.")
    width: float = Field(gt=0, allow_inf_nan=False, description="Displayed width in source units.")
    height: float = Field(gt=0, allow_inf_nan=False, description="Displayed height in source units.")
    units: Literal["pt", "px"]
    rotation: Rotation = Rotation.R0
    source_asset_id: UUID
    transform: CoordinateTransform
    status: PageStatus | None = Field(
        default=None, description="1.1.0+: processing outcome. Null/absent only in 1.0.0 documents.")
    warnings: list[PageWarning] = Field(default_factory=list, description="1.1.0+: processing warnings.")


_META_FIELD_FOR_TYPE = {
    BlockType.TABLE: "table",
    BlockType.TABLE_CELL: "table_cell",
    BlockType.EQUATION: "equation",
    BlockType.FIGURE: "figure",
}


class Block(_Model):
    id: UUID = Field(default_factory=new_id)
    page_id: UUID
    parent_id: UUID | None = None
    block_type: BlockType
    reading_order: int = Field(ge=0, description="Order among siblings (same page and parent).")
    bbox: NormalizedBBox
    raw_text: str | None = Field(default=None, description="Text as extracted; never edited.")
    current_text: str | None = Field(default=None, description="Text after content corrections.")
    language: Language
    revision: int = Field(default=1, ge=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    confidence: Confidence
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    provenance: Provenance
    table: TableMeta | None = None
    table_cell: TableCellMeta | None = None
    equation: EquationMeta | None = None
    figure: FigureMeta | None = None

    @model_validator(mode="after")
    def _block_rules(self) -> "Block":
        if self.parent_id == self.id:
            raise ValueError("block cannot be its own parent")
        if len(set(self.quality_flags)) != len(self.quality_flags):
            raise ValueError("quality_flags must be unique")
        if self.block_type in TEXT_BLOCK_TYPES and (self.raw_text is None or self.current_text is None):
            raise ValueError(f"block_type '{self.block_type}' requires raw_text and current_text")
        if (self.raw_text is None) != (self.current_text is None):
            raise ValueError("raw_text and current_text must both be set or both be null")
        if self.revision == 1 and self.current_text != self.raw_text:
            raise ValueError("revision 1 is unedited: current_text must equal raw_text")
        for btype, name in _META_FIELD_FOR_TYPE.items():
            present = getattr(self, name) is not None
            if btype is self.block_type and not present:
                raise ValueError(f"block_type '{btype}' requires '{name}' metadata")
            if btype is not self.block_type and present:
                raise ValueError(f"'{name}' metadata is only allowed on '{btype}' blocks")
        return self


class Edge(_Model):
    id: UUID = Field(default_factory=new_id)
    edge_type: EdgeType
    source_id: UUID
    target_id: UUID
    provenance: Provenance

    @model_validator(mode="after")
    def _no_self_loop(self) -> "Edge":
        if self.source_id == self.target_id:
            raise ValueError("edge source_id and target_id must differ")
        return self


class Correction(_Model):
    """A content-only correction request for one block, against a base revision.

    P1 validates and applies content; P3 owns persistence and transactions.
    """

    id: UUID = Field(default_factory=new_id)
    document_id: UUID
    block_id: UUID
    base_revision: int = Field(ge=1, description="Block revision the correction was made against.")
    operation: CorrectionOperation
    new_text: str | None = None
    new_language: Language | None = None
    new_review_status: ReviewStatus | None = None
    reason: str | None = None
    author_ref: str | None = Field(default=None, description="Opaque reviewer reference from P3.")
    created_at: AwareDatetime

    @model_validator(mode="after")
    def _operation_payload(self) -> "Correction":
        payload = {
            CorrectionOperation.REPLACE_TEXT: "new_text",
            CorrectionOperation.SET_LANGUAGE: "new_language",
            CorrectionOperation.SET_REVIEW_STATUS: "new_review_status",
        }
        required = payload[self.operation]
        for name in payload.values():
            value = getattr(self, name)
            if name == required and value is None:
                raise ValueError(f"operation '{self.operation}' requires '{name}'")
            if name != required and value is not None:
                raise ValueError(f"operation '{self.operation}' does not accept '{name}'")
        return self


class Document(_Model):
    """Root of the contract. Cross-references are validated here."""

    schema_version: Literal["1.0.0", "1.1.0"] = SCHEMA_VERSION
    id: UUID = Field(default_factory=new_id)
    title: str | None = None
    languages: list[Language] = Field(min_length=1)
    source_asset: SourceAsset
    pages: list[Page] = Field(min_length=1)
    blocks: list[Block] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    corrections: list[Correction] = Field(default_factory=list, description="Applied correction history.")
    created_at: AwareDatetime

    @model_validator(mode="before")
    @classmethod
    def _serialized_ids_required(cls, data: Any) -> Any:
        """Serialized input must carry every ``id``; generating one would hide producer bugs.

        Python code constructing models directly still gets fresh UUIDs from the
        default factories; this check applies to mapping (JSON) input.
        """
        if isinstance(data, dict):
            missing = _missing_ids(data)
            if missing:
                raise ValueError(f"serialized document is missing required id fields: {missing[:5]}")
        return data

    @model_validator(mode="after")
    def _cross_references(self) -> "Document":
        _unique("page id", [p.id for p in self.pages])
        _unique("page_index", [p.page_index for p in self.pages])
        _unique("block id", [b.id for b in self.blocks])
        _unique("edge id", [e.id for e in self.edges])
        _unique("correction id", [c.id for c in self.corrections])

        page_ids = {p.id for p in self.pages}
        for page in self.pages:
            if page.document_id != self.id:
                raise ValueError(f"page {page.id} document_id does not match document {self.id}")
            if page.source_asset_id != self.source_asset.id:
                raise ValueError(f"page {page.id} source_asset_id is not the document's source asset")

        blocks = {b.id: b for b in self.blocks}
        for block in self.blocks:
            if block.page_id not in page_ids:
                raise ValueError(f"block {block.id} references unknown page {block.page_id}")
            if block.parent_id is not None and block.parent_id not in blocks:
                raise ValueError(f"block {block.id} references unknown parent {block.parent_id}")
            if block.parent_id is not None and blocks[block.parent_id].page_id != block.page_id:
                raise ValueError(f"block {block.id} is on a different page from its parent {block.parent_id}")
        _check_acyclic(blocks)
        _unique("reading_order within (page_id, parent_id)",
                [(b.page_id, b.parent_id, b.reading_order) for b in self.blocks])

        _check_tables(blocks)
        if self.schema_version == "1.0.0":
            _check_v1_0_compatible(self.blocks)
            for page in self.pages:
                if page.status is not None or page.warnings:
                    raise ValueError(f"page {page.id} uses 1.1.0 status/warnings in a 1.0.0 document")
        else:
            for page in self.pages:
                if page.status is None:
                    raise ValueError(f"page {page.id} requires a status in a {self.schema_version} document")
        blocks_per_page = {p.id: 0 for p in self.pages}
        for block in self.blocks:
            blocks_per_page[block.page_id] += 1
        for page in self.pages:
            if page.status is PageStatus.BLANK and blocks_per_page[page.id]:
                raise ValueError(f"page {page.id} is marked blank but has blocks")
        for block in self.blocks:
            if block.table is not None and block.table.is_uncertain_candidate \
                    and QualityFlag.TABLE_STRUCTURE_UNCERTAIN not in block.quality_flags:
                raise ValueError(f"table {block.id} has no cells and must carry table_structure_uncertain")
            if block.figure and block.figure.caption_block_id is not None:
                cap = blocks.get(block.figure.caption_block_id)
                if cap is None or cap.block_type is not BlockType.CAPTION:
                    raise ValueError(f"figure {block.id} caption_block_id must reference a caption block")

        for edge in self.edges:
            _check_edge(edge, blocks)

        doc_ids = {self.id}
        for corr in self.corrections:
            if corr.document_id not in doc_ids:
                raise ValueError(f"correction {corr.id} belongs to a different document")
            target = blocks.get(corr.block_id)
            if target is None:
                raise ValueError(f"correction {corr.id} references unknown block {corr.block_id}")
            if corr.base_revision >= target.revision:
                raise ValueError(
                    f"correction {corr.id} base_revision {corr.base_revision} must be below the "
                    f"block's current revision {target.revision}"
                )
        return self


# ------------------------------------------------------------------ helper checks


def _unique(label: str, values: list[object]) -> None:
    dupes = [v for v, n in Counter(values).items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate {label}: {dupes[0]}")


def _check_v1_0_compatible(blocks: list[Block]) -> None:
    """A document labelled 1.0.0 may not use anything introduced in 1.1.0."""
    for block in blocks:
        added = QUALITY_FLAGS_ADDED_IN_1_1.intersection(block.quality_flags)
        if added:
            raise ValueError(f"block {block.id} uses 1.1.0 quality flags {sorted(added)} in a 1.0.0 document")
        if block.table is not None and block.table.is_uncertain_candidate:
            raise ValueError(f"block {block.id} is an uncertain table candidate, which requires 1.1.0")


def _missing_ids(data: dict) -> list[str]:  # type: ignore[type-arg]
    missing = []
    if "id" not in data:
        missing.append("document.id")
    asset = data.get("source_asset")
    if isinstance(asset, dict) and "id" not in asset:
        missing.append("source_asset.id")
    for key in ("pages", "blocks", "edges", "corrections"):
        for n, item in enumerate(data.get(key) or []):
            if isinstance(item, dict) and "id" not in item:
                missing.append(f"{key}[{n}].id")
    return missing


def required_version(document: "Document") -> str:
    """Lowest contract version able to represent ``document`` exactly."""
    uses_1_1 = any(QUALITY_FLAGS_ADDED_IN_1_1.intersection(b.quality_flags) for b in document.blocks)         or any(b.table is not None and b.table.is_uncertain_candidate for b in document.blocks)         or any(p.status is not None or p.warnings for p in document.pages)
    return "1.1.0" if uses_1_1 else "1.0.0"


class IncompatibleVersionError(ValueError):
    """The document uses features the requested contract version cannot represent."""


def export_document_data(document: "Document", target_version: str = SCHEMA_VERSION) -> dict:  # type: ignore[type-arg]
    """Serialize ``document`` as JSON-compatible data for ``target_version``.

    * ``1.1.0``: the full document.
    * ``1.0.0``: only if the content needs nothing from 1.1.0 other than page
      status, which is then **omitted** (it cannot be expressed in 1.0.0), and
      only when every page is ``ok`` with no warnings. Otherwise
      ``IncompatibleVersionError`` is raised: content, flags and failure
      information are never silently dropped.
    """
    if target_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported target version {target_version!r}")
    data = document.model_dump(mode="json")
    data["schema_version"] = target_version
    if target_version == "1.1.0":
        if any(p.status is None for p in document.pages):
            raise IncompatibleVersionError("every page needs a status to be exported as 1.1.0; "
                                           "upgrade with upgrade_document_data() and set page status")
        return data
    blockers = [
        *(f"block {b.id} flags {sorted(QUALITY_FLAGS_ADDED_IN_1_1.intersection(b.quality_flags))}"
          for b in document.blocks if QUALITY_FLAGS_ADDED_IN_1_1.intersection(b.quality_flags)),
        *(f"block {b.id} is an uncertain table" for b in document.blocks
          if b.table is not None and b.table.is_uncertain_candidate),
        *(f"page {p.page_index} status {p.status.value}" for p in document.pages
          if p.status not in (None, PageStatus.OK)),
        *(f"page {p.page_index} has {len(p.warnings)} warnings" for p in document.pages if p.warnings),
    ]
    if blockers:
        raise IncompatibleVersionError(f"document cannot be represented in 1.0.0: {blockers[:5]}")
    for page in data["pages"]:
        page.pop("status", None)
        page.pop("warnings", None)
    return data


def upgrade_document_data(data: dict) -> dict:  # type: ignore[type-arg]
    """Migrate serialized contract data to the current version (1.0.0 -> 1.1.0 is a relabel).

    1.1.0 only adds optional values, so every valid 1.0.0 document is a valid
    1.1.0 document. Unknown versions are rejected rather than guessed.
    """
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported schema_version {version!r}; supported: {SUPPORTED_SCHEMA_VERSIONS}")
    upgraded = dict(data)
    if version == "1.0.0":
        # 1.0.0 had no processing status; "ok" with no warnings is what a 1.0.0
        # producer asserted by emitting the page. Nothing else changes.
        upgraded["pages"] = [{**p, "status": p.get("status") or "ok", "warnings": p.get("warnings", [])}
                             for p in data.get("pages", [])]
    upgraded["schema_version"] = SCHEMA_VERSION
    return upgraded


def _check_acyclic(blocks: dict[UUID, Block]) -> None:
    for start in blocks.values():
        seen: set[UUID] = set()
        node: Block | None = start
        while node is not None and node.parent_id is not None:
            if node.id in seen:
                raise ValueError(f"parent cycle detected at block {node.id}")
            seen.add(node.id)
            node = blocks.get(node.parent_id)


def _check_tables(blocks: dict[UUID, Block]) -> None:
    for table in (b for b in blocks.values() if b.table is not None):
        for cell_id in table.table.cell_ids:  # type: ignore[union-attr]
            cell = blocks.get(cell_id)
            if cell is None or cell.table_cell is None:
                raise ValueError(f"table {table.id} lists {cell_id}, which is not a table_cell block")
            if cell.table_cell.table_id != table.id:
                raise ValueError(f"cell {cell_id} is listed by table {table.id} but names another table")
    for cell in (b for b in blocks.values() if b.table_cell is not None):
        meta = cell.table_cell
        assert meta is not None
        table = blocks.get(meta.table_id)
        if table is None or table.table is None:
            raise ValueError(f"cell {cell.id} references unknown table {meta.table_id}")
        if cell.id not in table.table.cell_ids:
            raise ValueError(f"cell {cell.id} is missing from table {table.id} cell_ids")
        if cell.page_id != table.page_id:
            raise ValueError(f"cell {cell.id} must be on the same page as table {table.id}")
        if meta.row_index + meta.row_span > table.table.row_count:
            raise ValueError(f"cell {cell.id} row span exceeds table row_count")
        if meta.column_index + meta.column_span > table.table.column_count:
            raise ValueError(f"cell {cell.id} column span exceeds table column_count")
        for header_id in meta.header_cell_ids:
            header = blocks.get(header_id)
            if header is None or header.table_cell is None or not header.table_cell.is_header:
                raise ValueError(f"cell {cell.id} header {header_id} is not a header cell")
            if header.table_cell.table_id != meta.table_id:
                raise ValueError(f"cell {cell.id} header {header_id} belongs to another table")


def _check_edge(edge: Edge, blocks: dict[UUID, Block]) -> None:
    source, target = blocks.get(edge.source_id), blocks.get(edge.target_id)
    if source is None or target is None:
        raise ValueError(f"edge {edge.id} references an unknown block")
    if edge.edge_type is EdgeType.CAPTION_OF:
        if source.block_type is not BlockType.CAPTION:
            raise ValueError(f"caption_of edge {edge.id} source must be a caption block")
        if target.block_type not in {BlockType.FIGURE, BlockType.TABLE, BlockType.EQUATION}:
            raise ValueError(f"caption_of edge {edge.id} target must be a figure, table or equation")
    if edge.edge_type is EdgeType.HEADER_FOR:
        if not (source.table_cell and source.table_cell.is_header):
            raise ValueError(f"header_for edge {edge.id} source must be a header table_cell")
        if target.table_cell is None:
            raise ValueError(f"header_for edge {edge.id} target must be a table_cell")
    if edge.edge_type is EdgeType.CONTAINS and target.parent_id not in (None, source.id):
        raise ValueError(f"contains edge {edge.id} conflicts with the target's parent_id")
