from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document_id: str = Field(min_length=1, max_length=128)
    revision: int | None = Field(default=None, ge=1)
    question: str = Field(min_length=1, max_length=2000)
    block_scope: list[str] | None = Field(default=None, max_length=200)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    block_id: str = Field(min_length=1, max_length=128)
    rev: int = Field(ge=1)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=4000)
    evidence: list[Citation] = Field(min_length=1, max_length=30)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    origin: Literal["ai_explanation"]
    document_revision: int = Field(ge=1)
    claims: list[Claim] = Field(max_length=8)
    abstain: bool
    uncertainty_notes: list[str] = Field(max_length=12)
    model_id: str = Field(min_length=1, max_length=128)
