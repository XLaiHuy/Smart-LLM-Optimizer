import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(os.environ.get("SMARTLLM_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: Literal["development", "test"] = "development"
    database_path: Path = ROOT / "data/smartllm.db"
    provider_mode: Literal["mock", "live"] = "mock"
    research_live_enabled: bool = False
    task_routing_bundle_path: Path = ROOT / "config/task_routing_profiles.json"
    auto_routing_strategy: Literal["rule_guarded", "ml_router", "ml_multi_model"] = "rule_guarded"
    ml_router_artifact_path: Path = ROOT / "config/router_model.json"
    ml_router_live_approved: bool = False
    ml_router_qualification_path: Path = ROOT / "config/router_live_qualified.review.json"
    provider_quota_enabled: bool = True
    provider_quota_account: str = "default-organization"
    groq_quota_rpm: int = Field(default=24, gt=0)
    groq_quota_rpd: int = Field(default=800, gt=0)
    groq_quota_tpm: int = Field(default=6400, gt=0)
    groq_quota_tpd: int = Field(default=160000, gt=0)
    openrouter_free_rpm: int = Field(default=16, gt=0)
    openrouter_free_rpd: int = Field(default=40, gt=0)
    # Conservative application pacing for paid profiles; observed provider
    # headers can impose tighter limits. These are not advertised account quotas.
    openrouter_paid_rpm: int = Field(default=16, gt=0)
    openai_quota_rpm: int = Field(default=24, gt=0)
    provider_max_failovers: int = Field(default=2, ge=0, le=2)
    # Development-only opt-in for testing research_candidate artifacts.
    ml_router_allow_research_candidate: bool = False
    ml_router_research_acceptance_path: Path = ROOT / "config/router_research_acceptance.json"
    router_training_manifest_path: Path = ROOT / "data/router-training/manifest.json"
    router_training_directory: Path = ROOT / "data/router-training"
    tools_live_approved: bool = False
    mock_config_id: str = "mock-baseline"
    auth_session_hours: int = Field(default=8, ge=1, le=168)
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )
    default_user_budget_usd: Decimal = Field(default=Decimal("5"), gt=0)
    project_budget_usd: Decimal = Field(default=Decimal("20"), gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_base_url: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: SecretStr = SecretStr("")
    huggingface_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    benchmark_impact_path: Path = ROOT / "config/benchmark-impact.json"
    benchmark_impact_approved: bool = False
    model_catalog_path: Path = ROOT / "config/models.json"
    upload_directory: Path = ROOT / "data/uploads"
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_documents: int = Field(default=5, ge=1, le=5)
    max_document_chars: int = Field(default=200000, ge=1, le=1000000)
    max_pdf_pages: int = Field(default=200, ge=1, le=1000)
    parser_timeout_seconds: int = Field(default=30, ge=1, le=120)
    document_operation_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0, le=20)
    adaptive_prompt_enabled: bool = False
    hybrid_context_enabled: bool = False
    memory_retrieval_enabled: bool = False
    context_token_budget: int = Field(default=8000, ge=1, le=200000)

    @field_validator(
        "database_path",
        "model_catalog_path",
        "upload_directory",
        "ml_router_artifact_path",
        "ml_router_qualification_path",
        "ml_router_research_acceptance_path",
        "benchmark_impact_path",
        "router_training_manifest_path",
        "router_training_directory",
    )
    @classmethod
    def resolve_db(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path.as_posix()}"

    @model_validator(mode="after")
    def prevent_split_live_storage(self) -> "Settings":
        if (
            os.name == "nt"
            and self.app_env != "test"
            and self.provider_mode == "live"
            and self.database_path == ROOT / "data/smartllm.db"
            and (ROOT / "data/docker-native-storage.json").exists()
        ):
            raise ValueError(
                "Live storage is owned by the Docker native volume. Run live CLI/jobs "
                "inside the backend container; the Windows database is a preserved snapshot."
            )
        return self

    @property
    def research_chat_enabled(self) -> bool:
        return self.app_env == "development" and self.ml_router_allow_research_candidate
