import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128, repr=False)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter an email address.")
        return normalized


class UserView(StrictModel):
    id: str
    email: str
    role: Literal["user", "admin"]


class GrantRequest(StrictModel):
    user_id: str = Field(min_length=1, max_length=128)
    role: Literal["reader", "reviewer"]
