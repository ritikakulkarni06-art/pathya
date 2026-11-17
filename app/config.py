from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    pathya_env: Literal["dev", "test", "prod"] = "dev"
    pathya_data_dir: Path = Path("data")
    pathya_db_path: Path | None = None
    auth_mode: Literal["local", "session"] = "local"
    session_secret: SecretStr = SecretStr("")
    max_upload_mb: int = Field(default=25, ge=1, le=250)
    max_pages: int = Field(default=60, ge=1)
    max_pixels: int = Field(default=40_000_000, ge=1)
    job_timeout_seconds: int = Field(default=300, ge=1)
    job_lease_seconds: int = Field(default=30, ge=2)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    retention_days_after_end: int = Field(default=30, ge=1)
    deletion_sla_days: int = Field(default=7, ge=1, le=7)
    llm_enabled: bool = False
    llm_provider: Literal["none", "gemini"] = "none"
    llm_model_id: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    llm_max_input_tokens: int = Field(default=4096, ge=1)
    llm_max_output_tokens: int = Field(default=512, ge=1)
    api_budget_inr_hard_cap: float = Field(default=0, ge=0)
    embeddings_enabled: bool = False
    embedding_model_path: Path | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    storage_min_free_bytes: int = Field(default=100_000_000, ge=0)
    session_ttl_seconds: int = Field(default=86400, ge=60)
    login_rate_limit: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=60, ge=1)
    extraction_adapter: str = "fixture"
    extraction_command: list[str] = Field(default_factory=list)
    extraction_fixture_path: Path = Path("tests/fixtures/chapter_demo.json")

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        if self.pathya_db_path is None:
            self.pathya_db_path = self.pathya_data_dir / "pathya.sqlite3"
        if self.auth_mode == "session" and len(self.session_secret.get_secret_value()) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters in session mode.")
        if self.pathya_env == "prod" and self.auth_mode == "local":
            raise ValueError("Local authentication cannot be used in production.")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit trusted origins.")
        if self.llm_enabled and (
            self.llm_provider != "gemini"
            or not self.llm_model_id
            or not self.gemini_api_key.get_secret_value()
        ):
            raise ValueError("Enable the LLM only after configuring provider, model and key.")
        if self.embeddings_enabled and (
            self.embedding_model_path is None or not self.embedding_model_path.is_dir()
        ):
            raise ValueError("EMBEDDING_MODEL_PATH must be an existing local model directory.")
        return self
