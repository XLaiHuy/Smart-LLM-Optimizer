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
    provider_mode: Literal["mock"] = "mock"
    mock_config_id: str = "mock-baseline"
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    project_budget_usd: Decimal = Field(default=Decimal("20"), gt=0)
    default_user_budget_usd: Decimal = Field(default=Decimal("5"), gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""

    @field_validator("database_path")
    @classmethod
    def resolve_db(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"
