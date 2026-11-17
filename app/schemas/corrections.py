from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.auth import StrictModel
from app.schemas.content import BlockType, Identifier, Language


class ReplaceText(StrictModel):
    op: Literal["replace_text"]
    text: str = Field(min_length=1, max_length=100000)


class SetLanguage(StrictModel):
    op: Literal["set_language"]
    lang: Language


class SetType(StrictModel):
    op: Literal["set_type"]
    type: BlockType


class Reorder(StrictModel):
    op: Literal["reorder"]
    parent_id: Identifier | None
    before_block_id: Identifier | None = None
    after_block_id: Identifier | None = None

    @model_validator(mode="after")
    def one_anchor(self) -> Self:
        if (self.before_block_id is None) == (self.after_block_id is None):
            raise ValueError("Choose exactly one before or after anchor")
        return self


class Split(StrictModel):
    op: Literal["split"]
    at_offsets: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=50)


class Merge(StrictModel):
    op: Literal["merge"]
    with_block_id: Identifier
    with_base_revision: int | None = Field(default=None, ge=1)


class MarkReviewed(StrictModel):
    op: Literal["mark_reviewed"]


class SetAltText(StrictModel):
    op: Literal["set_alt_text"]
    short: str = Field(min_length=1, max_length=1000)
    extended: str | None = Field(default=None, max_length=10000)


class SetMathML(StrictModel):
    op: Literal["set_mathml"]
    mathml: str = Field(min_length=1, max_length=20000)
    spoken_fallback: str = Field(min_length=1, max_length=5000)


class SetTableHeaders(StrictModel):
    op: Literal["set_table_headers"]
    header_cell_ids: list[Identifier] = Field(min_length=1, max_length=100)


Operation = Annotated[
    ReplaceText
    | SetLanguage
    | SetType
    | Reorder
    | Split
    | Merge
    | MarkReviewed
    | SetAltText
    | SetMathML
    | SetTableHeaders,
    Field(discriminator="op"),
]


class CorrectionRequest(StrictModel):
    base_revision: int = Field(ge=1)
    operations: list[Operation] = Field(min_length=1, max_length=30)
    reason: str = Field(min_length=1, max_length=2000)
