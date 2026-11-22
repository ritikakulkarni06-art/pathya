import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise ValueError("Enter an email address.")
    return normalized


class GrantRequest(StrictModel):
    """Share with an account by its ID or by its email address (exactly one of them)."""

    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    role: Literal["reader", "reviewer"]

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        return None if value is None else _email(value)

    @model_validator(mode="after")
    def one_target(self) -> "GrantRequest":
        if (self.user_id is None) == (self.email is None):
            raise ValueError("Give either user_id or email.")
        return self


class GrantView(StrictModel):
    user_id: str
    email: str
    role: Literal["reader", "reviewer"]
    created_at: str


class GrantList(StrictModel):
    grants: list[GrantView]


class PasswordResetRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return _email(value)


class PasswordResetConfirm(StrictModel):
    token: str = Field(min_length=20, max_length=200, repr=False)
    password: str = Field(min_length=12, max_length=128, repr=False)
