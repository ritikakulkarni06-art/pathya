from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    pathya_env: Literal["dev", "test", "prod"] = "dev"
    pathya_data_dir: Path = Path("data")
    pathya_db_path: Path | None = None
    reader_dist: Path | None = None
    auth_mode: Literal["local", "session"] = "local"
    session_secret: SecretStr = SecretStr("")
    max_upload_mb: int = Field(default=25, ge=1, le=250)
    max_pages: int = Field(default=60, ge=1)
    max_pixels: int = Field(default=40_000_000, ge=1)
    preview_max_side: int = Field(default=1200, ge=100, le=1600)
    pdf_preview_enabled: bool = False
    preview_render_timeout: float = Field(default=20, gt=0, le=60)
    max_json_body_bytes: int = Field(default=262144, ge=1024, le=1048576)
    request_rate_window_seconds: int = Field(default=60, ge=1)
    upload_rate_limit: int = Field(default=30, ge=1)
    question_rate_limit: int = Field(default=60, ge=1)
    daily_question_limit: int = Field(default=20, ge=1)
    correction_rate_limit: int = Field(default=120, ge=1)
    max_concurrent_uploads: int = Field(default=2, ge=1, le=20)
    daily_page_quota: int = Field(default=120, ge=1)
    job_timeout_seconds: int = Field(default=300, ge=1)
    job_lease_seconds: int = Field(default=30, ge=2)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    retention_days_after_end: int = Field(default=30, ge=1)
    deletion_sla_days: int = Field(default=7, ge=1, le=7)
    retention_extension_max_days: int = Field(default=365, ge=1)
    backup_days: int = Field(default=30, ge=1, le=365)
    backup_dir: Path | None = None
    llm_enabled: bool = False
    llm_provider: Literal["none", "gemini"] = "none"
    llm_model_id: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    llm_max_input_tokens: int = Field(default=4096, ge=1)
    llm_max_output_tokens: int = Field(default=512, ge=1)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_retries: int = Field(default=2, ge=0, le=2)
    llm_prices_path: Path = Path("config/prices.json")
    llm_price_max_age_days: int = Field(default=30, ge=1)
    question_max_chars: int = Field(default=2000, ge=1, le=2000)
    answer_no_evidence_threshold: float = Field(default=0, ge=0, allow_inf_nan=False)
    answer_low_support_threshold: float = Field(default=0.1, ge=0, allow_inf_nan=False)
    api_budget_inr_hard_cap: float = Field(default=0, ge=0, allow_inf_nan=False)
    document_budget_inr_hard_cap: float = Field(default=0, ge=0, allow_inf_nan=False)
    embeddings_enabled: bool = False
    embedding_model_path: Path | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    storage_min_free_bytes: int = Field(default=100_000_000, ge=0)
    session_ttl_seconds: int = Field(default=86400, ge=60)
    login_rate_limit: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=60, ge=1)
    speech_provider: str = "disabled"
    speech_voice: str = "default"
    speech_engine_version: str = ""
    segmenter: str = ""
    segmenter_version: str = "demo-regex-v1"
    max_audio_clip_mb: int = Field(default=10, ge=1)
    package_max_mb: int = Field(default=50, ge=1)
    extraction_adapter: str = "fixture"
    p1_max_output_bytes: int = Field(default=10_000_000, ge=1024, le=50_000_000)
    extraction_command: list[str] = Field(default_factory=list)
    extraction_fixture_path: Path = Path("tests/fixtures/chapter_demo.json")

    @property
    def active_segmenter_version(self) -> str:
        if self.segmenter == "pathya":
            return "pathya-reader-v1"
        return self.segmenter_version

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        if self.pathya_db_path is None:
            self.pathya_db_path = self.pathya_data_dir / "pathya.sqlite3"
        if self.backup_dir is None:
            self.backup_dir = self.pathya_data_dir.parent / "backups"
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


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        # Pydantic's default error repr can include raw environment inputs.
        raise ValueError(
            "Configuration is invalid. Check environment variable types, allowed values and required secrets in app/config.py."
        ) from None
