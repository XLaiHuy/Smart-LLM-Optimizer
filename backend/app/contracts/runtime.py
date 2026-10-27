from typing import Literal

from app.contracts.dtos import DTO


class RuntimeModel(DTO):
    model_id: str
    config_id: str | None = None
    label: str
    provider: Literal["openrouter", "openai"]
    available: bool


class RuntimeSettings(DTO):
    execution_source: str
    models: tuple[RuntimeModel, ...]
    group_policy_status: str
    reporting_epoch: str | None = None
    internal_lab_ui: bool = False
