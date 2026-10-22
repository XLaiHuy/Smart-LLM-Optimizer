"""Huy-owned execution contracts; dataset/grader ports can be implemented independently."""

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import Field, model_validator

from app.contracts.dtos import (
    DTO,
    CallRecord,
    CandidateExclusion,
    CostSnapshot,
    Message,
    ModelConfiguration,
    RegistrySnapshot,
    RouteDecision,
    RouteEstimate,
    RouteEvidence,
    TaskProfile,
    ToolDefinition,
)

Strategy = Literal[
    "fixed_reference",
    "fixed_candidate",
    "cheapest_feasible",
    "random_feasible",
    "rule_guarded",
    "ml_router",
    "ml_multi_model",
]


class LabModule(DTO):
    id: Literal["router", "prompt", "memory"]
    implemented: bool
    status: Literal["requires_qualified_data", "not_implemented", "ready"] = (
        "requires_qualified_data"
    )


class OptimizerLabInfo(DTO):
    modules: tuple[LabModule, ...]
    qualified_samples: int = 0
    requested_sizes: tuple[int, ...] = (50, 200, 600)
    dataset_status: Literal["not_qualified", "qualified"] = "not_qualified"
    comparison_available: bool = False


class MetricItem(DTO):
    baseline: float
    optimized: float
    delta_percent: float
    unit: str = ""


class AblationRunResponse(DTO):
    size: int
    evaluated_samples: int
    cost_usd: MetricItem
    latency_ms: MetricItem
    tokens: MetricItem
    pass_rate: MetricItem
    summary: str


class AblationRequest(DTO):
    size: Literal[50, 200, 600] = 50
    router: bool = True
    prompt: bool = False
    memory: bool = False


class FixtureCase(DTO):
    case_id: str
    messages: tuple[Message, ...]
    expected: str
    expected_error: str | None = None
    check: Literal["exact", "json_code"] = "exact"
    max_usd: Decimal = Decimal("0.05")
    deadline_ms: int = 15000
    tools: tuple[ToolDefinition, ...] = ()


class FixtureManifest(DTO):
    version: str
    purpose: Literal["functional_fixture"] = "functional_fixture"
    cases: tuple[FixtureCase, ...]


class ResearchRequest(DTO):
    client_request_id: str = Field(min_length=1, max_length=128)
    suite_id: Literal["huy-router-fixtures-v1", "huy-router-fixtures-v2"] = "huy-router-fixtures-v1"
    execution_source: Literal["simulation", "live"] = "simulation"
    config_ids: tuple[str, ...] = Field(
        default=("fixture-reference", "fixture-small"), min_length=1, max_length=8
    )
    policies: tuple[Strategy, ...] = Field(
        default=(
            "fixed_reference",
            "fixed_candidate",
            "cheapest_feasible",
            "random_feasible",
            "rule_guarded",
        ),
        min_length=1,
        max_length=7,
    )
    seed: int = Field(default=42, ge=0, le=2147483647)
    repeats: int = Field(default=1, ge=1, le=5)
    budget_usd: Decimal = Field(default=Decimal("1"), gt=0, le=20)

    @model_validator(mode="after")
    def unique_selections(self) -> "ResearchRequest":
        if len(set(self.config_ids)) != len(self.config_ids) or len(set(self.policies)) != len(
            self.policies
        ):
            raise ValueError("Duplicate selections")
        return self


class ResearchPreflight(DTO):
    trials: int
    max_calls: int
    simulation_upper_usd: Decimal | None = None
    live_upper_usd: Decimal | None = None
    live_enabled: bool = False
    manifest_hash: str


class ResearchConfigs(DTO):
    suite_id: str = "huy-router-fixtures-v1"
    cases: int
    models: tuple[ModelConfiguration, ...]
    policies: tuple[Strategy, ...]
    live_enabled: bool = False
    live_models: tuple[ModelConfiguration, ...] = ()
    live_reference_id: str | None = None
    ml_status: str = "ML_ARTIFACT_MISSING_FALLBACK"
    ml_artifact_hash: str | None = None


class SimulationMetrics(DTO):
    estimated_input_bound: int
    estimated_upper_usd: Decimal | None = None
    functional_pass: bool


class TrialResult(DTO):
    id: str
    case_id: str
    repeat: int
    policy: str
    snapshot_hash: str
    route: RouteDecision | None = None
    profile: TaskProfile
    error_code: str | None = None
    prediction: str | None = None
    calls: tuple[CallRecord, ...] = ()
    duration_ms: float
    simulation: SimulationMetrics | None = None
    functional_pass: bool = False
    operation_id: str | None = None
    rejections: tuple[CandidateExclusion, ...] = ()
    estimates: tuple[RouteEstimate, ...] = ()


class ResearchRunInfo(DTO):
    id: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled", "interrupted"]
    created_at: str
    completed: int
    total: int
    cancel_requested: bool
    execution_source: Literal["simulation", "live"] = "simulation"
    run_purpose: Literal["functional_fixture", "live_pilot"] = "functional_fixture"
    request: ResearchRequest
    manifest_hash: str
    catalog_hash: str
    code_sha: str
    checker_version: str = "fixture-checks-v1"
    error_code: str | None = None
    accounting: "RunAccounting | None" = None
    ml_artifact_hash: str | None = None


class UncommittedCall(DTO):
    operation_id: str
    call: CallRecord


class RunAccounting(DTO):
    calls: int
    calculated_usd: Decimal | None
    known_subtotal_usd: Decimal | None
    unknown_calls: int
    uncommitted_calls: tuple[UncommittedCall, ...] = ()


class PolicySummary(DTO):
    policy: str
    trials: int
    calls: int
    functional_passes: int
    errors: int
    fallbacks: int = 0
    fallback_rate: float | None = None
    p50_ms: float | None
    p95_ms: float | None
    simulation_upper_usd: Decimal | None
    calculated_usd: Decimal | None = None


class PredictorImportance(DTO):
    config_id: str
    importances: dict[str, float]


class ResearchSummary(DTO):
    routes: dict[str, int]
    policies: tuple[PolicySummary, ...]
    feature_importances: dict[str, float] = Field(default_factory=dict)
    predictor_importances: tuple[PredictorImportance, ...] = ()
    feature_importance_artifact_hash: str | None = None


class ReconcileRequest(DTO):
    actual_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(min_length=3, max_length=300)
    evidence_reference: str = Field(min_length=3, max_length=300)

    @model_validator(mode="after")
    def nonblank_evidence(self) -> "ReconcileRequest":
        if not self.reason.strip() or not self.evidence_reference.strip():
            raise ValueError("Reconciliation needs a reason and evidence reference")
        return self


class ExperimentSnapshot(DTO):
    request: ResearchRequest
    manifest: FixtureManifest
    registry: RegistrySnapshot
    costs: CostSnapshot
    evidence: tuple[RouteEvidence, ...]
    manifest_hash: str
    catalog_hash: str
    code_sha: str
    checker_version: str = "fixture-checks-v1"
    price_catalog_json: str | None = None
    ml_artifact_json: str | None = None
    ml_artifact_hash: str | None = None


class DatasetSource(Protocol):
    def load(self) -> FixtureManifest: ...


class PredictionGrader(Protocol):
    def grade(self, prediction: str, reference: str) -> bool: ...


class RoutingEvidenceSource(Protocol):
    def profiles(self) -> tuple[RouteEvidence, ...]: ...
