from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModuleName = Literal["router", "rewrite", "context", "memory"]
ModuleStatus = Literal["disabled", "not_implemented", "skipped", "applied", "failed"]
CostStatus = Literal["known", "estimated", "unknown", "not_billable"]


class DTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolDefinition(DTO):
    name: str
    description: str
    parameters_json: str


class ProviderItem(DTO):
    type: str
    payload_json: str


class ToolCall(DTO):
    call_id: str
    name: str
    arguments: str


class ToolEvent(DTO):
    call_id: str
    name: str
    status: Literal["succeeded", "failed", "interrupted", "running"]
    error_code: str | None = None
    arguments_json: str | None = None
    output_json: str | None = None
    duration_ms: float | None = None


class RoutingStage(DTO):
    config_id: str
    score: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)
    status: str
    base_threshold: float | None = Field(default=None, ge=0, le=1)
    drift_shift: float = Field(default=0, ge=0, le=1)


class FeatureFlags(DTO):
    router: bool = False
    rewrite: bool = False
    context: bool = False
    memory: bool = False


class Constraints(DTO):
    max_total_usd: Decimal | None = Field(default=None, gt=0)
    deadline_ms: int = Field(default=60000, ge=100, le=120000)


class ChatRequest(DTO):
    session_id: str = Field(min_length=1, max_length=64)
    client_request_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=50000)
    mode: Literal["baseline", "optimized"]
    policy_id: str | None = None
    flags: FeatureFlags | None = None
    constraints: Constraints = Field(default_factory=Constraints)
    document_ids: tuple[str, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_mode(self) -> "ChatRequest":
        if not self.message.strip():
            raise ValueError("Message must not be blank")
        if self.mode == "baseline":
            if (
                self.policy_id not in (None, "baseline")
                and not (self.policy_id and self.policy_id.startswith("fixed_candidate:"))
            ) or (
                self.flags and any(self.flags.model_dump().values())
            ):
                raise ValueError("Baseline conflicts with policy/flags")
        elif (
            self.policy_id is not None
            and not (
                self.policy_id in ("foundation-mock-v3", "quality-guarded-v3")
                or self.policy_id.startswith("fixed_candidate:")
            )
        ):
            raise ValueError("Only foundation-mock-v3 is available in G0")
        return self


class EffectiveConfiguration(DTO):
    policy_id: str
    policy_version: str = "g0.1"
    flags: FeatureFlags
    candidate_id: str | None = None


class Principal(DTO):
    id: str
    username: str
    role: Literal["user", "admin"] = "user"
    quota_usd: Decimal


class LoginRequest(DTO):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SessionCreate(DTO):
    title: str = Field(default="Cuộc hội thoại mới", min_length=1, max_length=120)


class SessionInfo(DTO):
    id: str
    title: str
    revision: int
    created_at: str
    updated_at: str
    active: bool = False


class Message(DTO):
    role: Literal["system", "developer", "user", "assistant"]
    content: str
    id: str | None = None
    request_id: str | None = None


class Summary(DTO):
    revision: int
    content: str
    covered_message_ids: tuple[str, ...]


class Fact(DTO):
    key: str
    value: str
    source_message_ids: tuple[str, ...]


class SessionSnapshot(DTO):
    owner_user_id: str
    session_id: str
    revision: int
    raw_turns: tuple[Message, ...] = ()
    server_instructions: tuple[Message, ...] = ()
    summaries: tuple[Summary, ...] = ()
    facts: tuple[Fact, ...] = ()


class SessionDetail(SessionInfo):
    messages: tuple[Message, ...]
    active_client_request_id: str | None = None


class DerivedMemory(DTO):
    snapshot_revision: int
    summaries: tuple[Summary, ...] = ()
    facts: tuple[Fact, ...] = ()


class ExecutionRequest(DTO):
    request_id: str
    principal: Principal
    request: ChatRequest
    namespace: Literal["chat", "eval"] = "chat"
    execution_source: Literal["mock", "live"] = "mock"


class OptimizationState(DTO):
    module: ModuleName
    status: ModuleStatus
    reason: str
    before_tokens: int | None = None
    after_tokens: int | None = None


class TokenEstimate(DTO):
    value: int | None = None
    status: Literal["measured", "estimated", "unknown"] = "unknown"
    source: str = "unavailable_g0"
    model_id: str
    tokenizer_version: str | None = None


class ContextBudgets(DTO):
    estimates: tuple[TokenEstimate, ...] = ()


class ContextFeatures(DTO):
    current_turn: Message
    flags: FeatureFlags
    approved_current_content: str | None = None
    evidence: tuple[Message, ...] = ()
    memory: tuple[Message, ...] = ()


class ContextResult(DTO):
    messages: tuple[Message, ...]
    provenance: tuple[str, ...]
    state: OptimizationState
    tools: tuple[ToolDefinition, ...] = ()
    continuation_items: tuple[ProviderItem, ...] = ()
    token_estimates: tuple[TokenEstimate, ...] = ()
    summary_needed: bool = False


class MemoryPlan(DTO):
    enabled: bool = False
    query: str = ""
    token_budget: int = Field(default=0, ge=0)
    top_k: int | None = Field(default=None, ge=1)


class MemoryResult(DTO):
    snapshot: SessionSnapshot
    state: OptimizationState
    memory_messages: tuple[Message, ...] = ()


class OptimizedPrompt(DTO):
    original: str
    proposed: str
    validation: Literal["preserved", "violation", "unknown"] = "unknown"
    state: OptimizationState


class TaskProfile(DTO):
    domain: str = "unknown"
    difficulty: str = "unknown"
    reason: str = "not_implemented_g0"
    language: str = "unknown"
    requires_structured: bool = False
    rules_matched: tuple[str, ...] = ()
    input_utf8_bytes: int = 0
    length_tier: Literal["short", "long"] = "short"
    total_input_bytes: int = 0
    has_rag_context: bool = False
    code_ratio: float = Field(default=0, ge=0, le=1)
    json_schema_required: bool = False
    tool_count: int = 0
    tool_recovery_required: bool = False


class ModelConfiguration(DTO):
    config_id: str
    model_id: str
    execution_source: Literal["mock", "live"] = "mock"
    context_window: int | None = None
    available: bool = True
    availability_reason: str = "configured_mock"
    endpoint: str = "responses"
    max_output_tokens: int = 1024
    structured_output: bool = False
    supported_parameters: tuple[str, ...] = ()
    function_calling: bool = False
    reasoning_effort: str | None = None


class RegistrySnapshot(DTO):
    configurations: tuple[ModelConfiguration, ...]
    mock_config_id: str


class CostSnapshot(DTO):
    version: str = "g0-no-live-prices"
    rates: tuple["RouteRate", ...] = ()


class RouteRate(DTO):
    config_id: str
    input_per_million: Decimal = Field(ge=0, allow_inf_nan=False)
    output_per_million: Decimal = Field(ge=0, allow_inf_nan=False)


class PolicySnapshot(EffectiveConfiguration):
    strategy: Literal[
        "fixed_reference",
        "fixed_candidate",
        "cheapest_feasible",
        "random_feasible",
        "rule_guarded",
        "ml_router",
        "ml_multi_model",
    ] = "rule_guarded"
    candidate_id: str | None = None
    seed: int = 0
    sandbox: bool = False
    evidence: tuple["RouteEvidence", ...] = ()
    evidence_version: str | None = None
    ml_artifact_hash: str | None = None


class RouteEvidence(DTO):
    config_id: str
    domain: str
    qualifies: bool | None = None
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provenance: Literal["fixture", "qualified_dev"] = "fixture"


class RemainingBudget(DTO):
    usd: Decimal | None = None
    deadline_ms: float | None = None


class RouteDecision(DTO):
    model_id: str
    config_id: str
    effort: str = "none"
    policy_id: str
    reason: str = "foundation_fixed_mock"
    fallback_used: bool = False
    rules_matched: tuple[str, ...] = ()
    exclusions: tuple["CandidateExclusion", ...] = ()
    estimates: tuple["RouteEstimate", ...] = ()
    policy_hash: str | None = None
    evidence_version: str | None = None
    use_original_context: bool = False
    ml_score: float | None = Field(default=None, ge=0, le=1)
    calibrated_threshold: float | None = Field(default=None, ge=0, le=1)
    reason_code: str | None = None
    ml_artifact_hash: str | None = None
    ml_model_version: str | None = None
    stages: tuple[RoutingStage, ...] = ()


class CandidateExclusion(DTO):
    config_id: str
    reason: str


class RouteEstimate(DTO):
    config_id: str
    input_bound: int
    upper_usd: Decimal | None
    provenance: str = "utf8_byte_bound_v1"


class Usage(DTO):
    scope: Literal["all_calls", "call"] = "all_calls"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_source: Literal["provider", "mock", "estimated", "unknown"] = "mock"


class CostEstimate(DTO):
    scope: Literal["all_calls", "call"] = "all_calls"
    status: CostStatus = "not_billable"
    serving_usd: Decimal | None = None
    price_catalog_version: str | None = None
    known_subtotal_usd: Decimal | None = None


class Timing(DTO):
    e2e_ms: float
    provider_ms: float
    ttft_ms: float | None = None
    measurement_scope: Literal["server_through_history_flush"] = "server_through_history_flush"


class ProviderOptions(DTO):
    request_id: str
    call_id: str
    config_id: str
    model_id: str
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    tools: tuple[ToolDefinition, ...] = ()
    continuation_items: tuple[ProviderItem, ...] = ()


class ProviderResult(DTO):
    text: str
    execution_source: Literal["mock", "live"] = "mock"
    provider_response_id: str | None = None
    native_usage_json: str | None = None
    usage: Usage = Field(default_factory=lambda: Usage(scope="call"))
    cost: CostEstimate = Field(default_factory=lambda: CostEstimate(scope="call"))
    duration_ms: float
    status: Literal["completed", "tool_calls", "incomplete"] = "completed"
    tool_calls: tuple[ToolCall, ...] = ()
    output_items: tuple[ProviderItem, ...] = ()


class CallRecord(DTO):
    provider_response_id: str | None = None
    native_usage_json: str | None = None
    call_id: str
    stage: Literal["provider", "query_embedding", "indexing", "document_map", "document_reduce"] = (
        "provider"
    )
    model_id: str
    usage: Usage = Field(default_factory=lambda: Usage(scope="call"))
    cost: CostEstimate = Field(default_factory=lambda: CostEstimate(scope="call"))
    duration_ms: float | None = None
    reconciled_usd: Decimal | None = None
    reconciliation_id: str | None = None


class MeteringContext(DTO):
    operation_id: str
    principal: Principal
    session_id: str | None = None
    category: Literal["serving", "evaluation", "indexing"] = "serving"
    max_total_usd: Decimal = Field(gt=0)

    @classmethod
    def from_execution(
        cls, execution: ExecutionRequest, default_limit: Decimal
    ) -> "MeteringContext":
        return cls(
            operation_id=execution.request_id,
            principal=execution.principal,
            session_id=execution.request.session_id,
            category="evaluation" if execution.namespace == "eval" else "serving",
            max_total_usd=execution.request.constraints.max_total_usd or default_limit,
        )


class Citation(DTO):
    chunk_id: str
    document_id: str
    filename: str
    location: str
    excerpt: str


class ChatResponse(DTO):
    request_id: str
    session_id: str
    session_revision: int
    execution_source: Literal["mock", "live"] = "mock"
    response: Message
    route: RouteDecision
    requested_flags: FeatureFlags | None = None
    effective_configuration: EffectiveConfiguration
    usage: Usage
    cost: CostEstimate
    timing: Timing
    calls: tuple[CallRecord, ...]
    optimizations: tuple[OptimizationState, ...]
    quality_score: float | None = None
    cost_saving_ratio: float | None = None
    citations: tuple["Citation", ...] = ()
    tool_events: tuple[ToolEvent, ...] = ()


class PublicModel(DTO):
    name: str
    status: Literal["planned", "configured", "simulated"]


class PlatformInfo(DTO):
    name: str = "Smart LLM Optimizer"
    execution_mode: Literal["mock", "live"]
    models: tuple[PublicModel, ...]
    tools_available: bool


class RecentRequest(DTO):
    execution_source: Literal["mock", "live"] = "mock"
    request_id: str
    session_id: str
    status: str
    created_at: str
    e2e_ms: float | None


class Overview(DTO):
    scope: Literal["current_user_all_time"] = "current_user_all_time"
    execution_source: Literal["mock", "live"] = "mock"
    total_requests: int
    succeeded: int
    failed: int
    active: int
    median_latency_ms: float | None
    latency_sample_count: int
    cost: CostEstimate = Field(default_factory=CostEstimate)
    quality_score: float | None = None
    recent_requests: tuple[RecentRequest, ...]


class ErrorDetail(DTO):
    code: str
    message: str
    request_id: str | None = None
    retryable: bool = False


class ErrorEnvelope(DTO):
    error: ErrorDetail


class SmokeCase(DTO):
    case_id: str
    message: str


class EvalManifest(DTO):
    suite_version: str
    run_purpose: Literal["smoke", "live_research"]
    execution_source: Literal["mock", "live"]
    cases: tuple[SmokeCase, ...] = Field(min_length=1)


class DocumentInfo(DTO):
    id: str
    session_id: str
    filename: str
    status: str
    characters: int
    chunks: int
    created_at: str
    error_code: str | None = None


class DocumentDetail(DocumentInfo):
    text: str


class JobRequest(DTO):
    client_request_id: str = Field(min_length=1, max_length=128)
    task: Literal["index", "summarize", "compare"]
    document_ids: tuple[str, ...] = Field(min_length=1, max_length=5)
    instruction: str = Field(default="", max_length=5000)
    max_total_usd: Decimal = Field(default=Decimal("0.50"), gt=0, le=20)


class DocumentJob(DTO):
    id: str
    session_id: str
    task: str
    status: str
    completed_steps: int = 0
    total_steps: int = 0
    coverage: float = 0
    error_code: str | None = None
    response: ChatResponse | None = None


class MetricBucket(DTO):
    key: str
    calls: int
    input_tokens: int | None
    output_tokens: int | None
    usd: Decimal | None
    known_subtotal_usd: Decimal | None
    unknown_calls: int
    p50_ms: float | None
    p95_ms: float | None
    timing_samples: int = 0
    reconciled_calls: int = 0


class Analytics(DTO):
    scope: str
    execution_source: Literal["mock", "live"]
    timezone: str = "Asia/Ho_Chi_Minh"
    start: str
    end: str
    totals: MetricBucket
    daily: tuple[MetricBucket, ...]
    granularity: Literal["hour", "day", "month"] = "day"
    timeseries: tuple[MetricBucket, ...] = ()
    models: tuple[MetricBucket, ...]
    categories: tuple[MetricBucket, ...]
    sessions: tuple[MetricBucket, ...]
    quota_usd: Decimal
    settled_usd: Decimal
    reserved_usd: Decimal
    available_usd: Decimal
    project_available_usd: Decimal
    requests: int
    succeeded: int
    failed: int
    retention_note: str = "Content deletion retains minimal usage and accounting metadata."


class AdminUser(DTO):
    id: str
    username: str
    role: str
    quota_usd: Decimal
    settled_usd: Decimal
    reserved_usd: Decimal


class QuotaUpdate(DTO):
    quota_usd: Decimal = Field(gt=0, le=10000)
    reason: str = Field(min_length=3, max_length=300)
