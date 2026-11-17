from typing import Literal

from pydantic import Field

from app.schemas.auth import StrictModel
from app.schemas.content import Language


class GlossaryRequest(StrictModel):
    term: str = Field(min_length=1, max_length=128)
    language: Language
    scope: Literal["document", "user"] = "document"
    spoken_alias: str = Field(min_length=1, max_length=256)
    phoneme: str | None = Field(default=None, max_length=256)


class AudioRequest(StrictModel):
    voice: str | None = Field(default=None, min_length=1, max_length=64)
