"""Admin training API and server-owned distillation manifest. No client paths or keys."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from app.contracts.dtos import DTO, CostSnapshot, Message, ModelConfiguration


class TrainingRequest(DTO):
    client_request_id: str = Field(min_length=1, max_length=100)
    # ``huggingface_gemini`` is retained only so existing saved jobs can be read.
    # New live training uses the configured provider catalog.
    mode: Literal["cache", "live", "huggingface_gemini"] = "cache"
    budget_usd: Decimal = Field(default=Decimal("1"), gt=0, le=20, allow_inf_nan=False)
    hybrid: bool = True
    auto_import: bool = True
    flash_attention: bool = False
    phase: Literal["full", "collect", "train"] = "full"
    collection_batches: int = Field(default=1, ge=1, le=20)


class TrainingResume(DTO):
    phase: Literal["full", "collect", "train"] = "full"


class TrainingReviewItem(DTO):
    task_id: str
    config_id: str
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    qualified: bool
    reason: str = Field(min_length=8, max_length=2000)


class TrainingReviews(DTO):
    items: tuple[TrainingReviewItem, ...] = Field(min_length=1, max_length=100)


class TrainingReviewAnswer(DTO):
    config_id: str
    text: str
    response_sha256: str
    qualified: bool


class TrainingReviewCase(DTO):
    task_id: str
    split: Literal["train", "calibration", "threshold", "holdout"]
    task: tuple[Message, ...]
    gold: str
    answers: tuple[TrainingReviewAnswer, ...]
    reviewed: bool = False


class TrainingInfo(DTO):
    configured: bool
    cache_available: bool
    live_available: bool
    attention_available: bool = False
    reason: str | None = None
    active_artifact_hash: str | None = None
    pilot: bool = False


class TrainingJob(DTO):
    id: str
    request: TrainingRequest
    status: Literal["running", "succeeded", "failed", "interrupted"] = "running"
    stage: Literal["collect", "distill", "train", "evaluate", "import", "complete"] = "collect"
    completed: int = 0
    total: int = 0
    cache_hits: int = 0
    api_calls: int = 0
    unknown_cost_calls: int = 0
    spent_usd: Decimal = Decimal(0)
    artifact_hash: str | None = None
    imported: bool = False
    holdout_report: dict[str, float] = Field(default_factory=dict)
    error_code: str | None = None
    ready_for_training: bool = False
    batches_completed: int = 0
    active_phase: Literal["full", "collect", "train"] = "full"
    pilot_report: dict[str, Any] = Field(default_factory=dict)


class GradingSpec(DTO):
    kind: Literal["mcq", "numeric", "code", "extractive_qa", "open"]
    version: str = "router-grader-v1"
    label_source: Literal[
        "dataset_gold", "human_verified", "teacher_judged", "synthetic_verified"
    ] = "dataset_gold"
    choices: tuple[str, ...] = ()
    absolute_tolerance: float = Field(default=0, ge=0, allow_inf_nan=False)
    relative_tolerance: float = Field(default=0, ge=0, allow_inf_nan=False)
    tests: tuple[str, ...] = ()
    test_setup: str = ""
    docker_image: str | None = None
    human_reviewed: bool = False
    synthetic: bool = False
    parent_group_id: str | None = None


class RawTrainingSample(DTO):
    task_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    split: Literal["train", "calibration", "threshold", "holdout"]
    messages: tuple[Message, ...] = Field(min_length=1)
    # Evaluator-only data; never appended to serving messages.
    gold: str = Field(min_length=1)
    has_rag_context: bool = False
    critical: bool = False
    grading: GradingSpec | None = None


class TrainingCorpus(DTO):
    samples: tuple[RawTrainingSample, ...] = Field(min_length=16, max_length=2000)


class TrainingSource(DTO):
    local_path: str
    hf_repo: str | None = None
    hf_revision: str | None = None
    hf_file: str | None = None
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    adapter: Literal["canonical", "vmlu", "viquad2", "gsm8k", "mbpp", "aya"] = "canonical"
    license: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    license_url: str | None = None
    license_reviewed: bool = False
    allow_training: bool = False


class TrainingManifest(DTO):
    version: str = Field(min_length=1)
    reviewed_by: str = Field(min_length=1)
    pricing_source: str = Field(min_length=1)
    access_verified: bool = False
    software_test: bool = False
    source: TrainingSource
    configurations: tuple[ModelConfiguration, ModelConfiguration, ModelConfiguration]
    reference_config_id: str
    costs: CostSnapshot
    max_samples: int = Field(default=80, ge=16, le=2000)
    min_interval_seconds: float = Field(default=4.2, ge=0, le=3600, allow_inf_nan=False)
    encoder_spec_path: str | None = None
    attention_epochs: int = Field(default=10, ge=1, le=200)
    pilot: bool = False
    sources: tuple[TrainingSource, ...] = ()
    synthesize: bool = False
    split_protocol: Literal["source_hash", "frozen_canonical"] = "source_hash"
    domain_loss_weight: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    docker_image: str | None = None

    @model_validator(mode="before")
    @classmethod
    def pilot_defaults(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("pilot") and "attention_epochs" not in value:
            return {**value, "attention_epochs": 15}
        return value

    @model_validator(mode="after")
    def coherent(self) -> "TrainingManifest":
        ids = {c.config_id for c in self.configurations}
        if (
            len(ids) != 3
            or self.reference_config_id not in ids
            or ids != {r.config_id for r in self.costs.rates}
            or len(self.costs.rates) != 3
        ):
            raise ValueError("Three distinct models and complete reviewed prices required")
        if any(
            c.max_output_tokens <= 0
            or not c.context_window
            or c.context_window <= c.max_output_tokens
            for c in self.configurations
        ):
            raise ValueError("Positive generation limits and context windows required")
        return self


class CachedGeneration(DTO):
    text: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(gt=0, allow_inf_nan=False)
    usd: Decimal = Field(ge=0, allow_inf_nan=False)


class JudgeResult(DTO):
    scores: tuple[float, float, float]

    @model_validator(mode="after")
    def bounded(self) -> "JudgeResult":
        if any(not 0 <= score <= 100 for score in self.scores):
            raise ValueError("Judge scores must be finite and in [0,100]")
        return self
