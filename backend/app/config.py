from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: Literal["development", "test"] = "development"
    database_path: Path = ROOT / "data/smartllm.db"
    provider_mode: Literal["mock", "live"] = "mock"
    research_live_enabled: bool = False
    mock_config_id: str = "mock-baseline"
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    project_budget_usd: Decimal = Field(default=Decimal("20"), gt=0)
    default_user_budget_usd: Decimal = Field(default=Decimal("5"), gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    model_catalog_path: Path = ROOT / "config/models.json"
    upload_directory: Path = ROOT / "data/uploads"
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_documents: int = Field(default=5, ge=1, le=5)
    max_document_chars: int = Field(default=200000, ge=1, le=1000000)
    max_pdf_pages: int = Field(default=200, ge=1, le=1000)
    parser_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_operation_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0, le=20)

    @field_validator("database_path", "model_catalog_path", "upload_directory")
    @classmethod
    def resolve_db(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"
