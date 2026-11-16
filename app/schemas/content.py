import re
from datetime import datetime
from typing import Annotated, Any, Literal, Self
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.errors import Problem

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Language = Literal["en", "hi"]
BlockType = Literal[
    "heading", "paragraph", "list_item", "table", "table_cell", "equation", "figure", "caption"
]
BlockStatus = Literal["ok", "needs_review", "corrected", "reviewed", "unsupported", "not_scored"]
Relation = Literal["contains", "precedes", "caption_of", "refers_to", "header_for", "supersedes"]


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Confidence(ContentModel):
    engine: str = Field(min_length=1, max_length=128)
    score: float | None = Field(ge=0, le=1)
    flags: list[Annotated[str, Field(max_length=128)]] = Field(max_length=100)


class Provenance(ContentModel):
    parser: str = Field(min_length=1, max_length=128)
    model: str | None = Field(max_length=128)
    version: str = Field(min_length=1, max_length=128)
    reviewer: Identifier | None
    changed_at: datetime

    @field_validator("changed_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("changed_at must include a UTC offset")
        return value


class BlockMetadata(ContentModel):
    alt_text_short: str | None = Field(default=None, max_length=1000)
    alt_text_extended: str | None = Field(default=None, max_length=10000)
    mathml: str | None = Field(default=None, max_length=20000)
    spoken_fallback: str | None = Field(default=None, max_length=5000)
    header_cell_ids: list[Identifier] = Field(default_factory=list, max_length=200)
    caption_block_ids: list[Identifier] = Field(default_factory=list, max_length=100)

    @field_validator("mathml")
    @classmethod
    def safe_mathml(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "<!" in value or "<?" in value:
            raise ValueError("MathML declarations and entities are unsupported")
        try:
            root = ElementTree.fromstring(value)
        except ElementTree.ParseError:
            raise ValueError("MathML must be well formed") from None
        allowed = {
            "math",
            "mrow",
            "mi",
            "mn",
            "mo",
            "mfrac",
            "msup",
            "msub",
            "msubsup",
            "msqrt",
            "mroot",
            "mtext",
        }
        if root.tag not in {"math", "{http://www.w3.org/1998/Math/MathML}math"}:
            raise ValueError("MathML must have a math root")
        for node in root.iter():
            tag = node.tag.removeprefix("{http://www.w3.org/1998/Math/MathML}")
            if tag not in allowed or node.attrib:
                raise ValueError("Only the supported attribute-free MathML subset is accepted")
        return value


class Page(ContentModel):
    id: Identifier
    pdf_index_0: int = Field(ge=0)
    printed_label: str = Field(min_length=1, max_length=64)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: Literal[0, 90, 180, 270] = 0
    source_asset_id: Identifier | None = None
    transform: tuple[float, float, float, float, float, float]


class Block(ContentModel):
    id: Identifier
    page_id: Identifier
    type: BlockType
    parent_id: Identifier | None
    order_key: float
    bbox: tuple[float, float, float, float]
    text_raw: str = Field(max_length=100000)
    text_current: str = Field(max_length=100000)
    lang: Language
    revision: int = Field(default=1, ge=1)
    status: BlockStatus
    confidence: Confidence
    provenance: Provenance
    critical_flag: bool = False
    successor_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    metadata: BlockMetadata = Field(default_factory=BlockMetadata)

    @field_validator("bbox")
    @classmethod
    def valid_bbox(
        cls, value: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = value
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise PydanticCustomError(
                "invalid_bbox", "Use normalized ordered coordinates within [0,1]."
            )
        return value

    @model_validator(mode="after")
    def review_metadata(self) -> Self:
        if self.status == "ok" and self.confidence.score is None:
            raise ValueError("Unscored native text must use not_scored, not an invented OCR score")
        if self.status == "not_scored" and self.confidence.score is not None:
            raise ValueError("not_scored content must have a null score")
        if self.status == "reviewed" and not self.provenance.reviewer:
            raise ValueError("Reviewed content needs a reviewer identifier")
        if (
            self.status == "reviewed"
            and self.type == "equation"
            and not (self.metadata.mathml and self.metadata.spoken_fallback)
        ):
            raise ValueError("Reviewed equations need MathML and a spoken fallback")
        if self.status == "reviewed" and self.type == "figure" and not self.metadata.alt_text_short:
            raise ValueError("Reviewed figures need a short description")
        return self


class Edge(ContentModel):
    from_id: Identifier
    relation: Relation
    to_id: Identifier


class Document(ContentModel):
    id: Identifier
    owner_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    languages: list[Language] = Field(min_length=1, max_length=2)
    current_revision: int = Field(ge=0)
    state: Literal[
        "uploading",
        "queued",
        "processing",
        "review_required",
        "building",
        "ready",
        "failed",
        "deleting",
        "deleted",
    ]
    rights_note: str = Field(min_length=1, max_length=2000)
    retention_until: datetime


class Correction(ContentModel):
    id: Identifier
    document_id: Identifier
    block_id: Identifier
    base_revision: int = Field(ge=1)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    author_id: Identifier
    accepted_revision: int | None = None
    state: Literal["accepted", "conflict", "rejected"]


class Artifact(ContentModel):
    id: Identifier
    document_id: Identifier
    kind: Literal["audio_block", "chunk_index", "embedding", "package"]
    block_id: Identifier | None
    dependency_revisions: dict[Identifier, Annotated[int, Field(ge=1)]]
    content_hash: str | None
    language: Language | None
    voice: str | None
    engine_version: str | None
    status: Literal["pending", "building", "ready", "stale", "failed"]
    asset_id: Identifier | None


class ExtractionResult(ContentModel):
    schema_version: Literal["1.0.0"]
    pages: list[Page] = Field(min_length=1, max_length=1000)
    blocks: list[Block] = Field(max_length=100000)
    edges: list[Edge] = Field(max_length=200000)
    quality_flags: list[Annotated[str, Field(max_length=128)]] = Field(max_length=1000)
    parser_versions: dict[
        Annotated[str, Field(max_length=128)], Annotated[str, Field(max_length=128)]
    ]

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        page_ids = {page.id for page in self.pages}
        block_ids = {block.id for block in self.blocks}
        if (
            len(page_ids) != len(self.pages)
            or len(block_ids) != len(self.blocks)
            or page_ids & block_ids
        ):
            raise PydanticCustomError("duplicate_id", "Page and block identifiers must be unique.")
        if len({page.pdf_index_0 for page in self.pages}) != len(self.pages):
            raise PydanticCustomError("duplicate_page", "PDF indexes must be unique.")
        by_id = {block.id: block for block in self.blocks}
        order_keys = set()
        for block in self.blocks:
            if block.revision != 1:
                raise PydanticCustomError(
                    "invalid_initial_revision", "Initial extraction blocks must have revision 1."
                )
            if block.page_id not in page_ids:
                raise PydanticCustomError("dangling_page", "A block references an unknown page.")
            if block.parent_id is not None and block.parent_id not in block_ids:
                raise PydanticCustomError(
                    "dangling_parent", "A block references an unknown parent."
                )
            order = (block.page_id, block.parent_id, block.order_key)
            if order in order_keys:
                raise PydanticCustomError(
                    "invalid_order", "Reading order keys must be unique within a page and parent."
                )
            order_keys.add(order)
            seen = {block.id}
            parent = block.parent_id
            while parent:
                if parent in seen:
                    raise PydanticCustomError(
                        "parent_cycle", "Block parents must not contain cycles."
                    )
                seen.add(parent)
                parent_block = by_id.get(parent)
                if parent_block is None:
                    raise PydanticCustomError(
                        "dangling_parent", "A block references an unknown parent."
                    )
                if parent_block.page_id != block.page_id:
                    raise PydanticCustomError(
                        "invalid_parent", "A parent must be on the same page."
                    )
                parent = parent_block.parent_id
            for header_id in block.metadata.header_cell_ids:
                header = by_id.get(header_id)
                if (
                    header is None
                    or header.type != "table_cell"
                    or header.parent_id != block.parent_id
                    or block.parent_id is None
                ):
                    raise PydanticCustomError(
                        "invalid_header", "Table headers must reference cells in the same table."
                    )
            if any(
                item not in block_ids
                for item in [*block.successor_ids, *block.metadata.caption_block_ids]
            ):
                raise PydanticCustomError("dangling_edge", "Metadata references an unknown block.")
        for edge in self.edges:
            if edge.from_id not in block_ids or edge.to_id not in block_ids:
                raise PydanticCustomError("dangling_edge", "An edge references an unknown block.")
        signatures = {(edge.from_id, edge.relation, edge.to_id) for edge in self.edges}
        if len(signatures) != len(self.edges):
            raise PydanticCustomError("duplicate_edge", "Edges must be unique.")
        return self


def parse_extraction(value: Any) -> ExtractionResult:
    try:
        # Revalidate model inputs too: callers cannot bypass validation using model_construct.
        return ExtractionResult.model_validate(
            value.model_dump(mode="json", warnings=False)
            if isinstance(value, ExtractionResult)
            else value
        )
    except ValidationError as error:
        first = error.errors(include_input=False)[0]
        code = first["type"]
        if not re.fullmatch(r"[a-z_]+", code):
            code = "invalid_extraction"
        raise Problem(
            422,
            code,
            "Extraction content is invalid. Check the schema and referenced page/block identifiers.",
        ) from None
