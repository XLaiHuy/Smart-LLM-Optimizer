from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModuleName = Literal["router", "rewrite", "context", "memory"]
ModuleStatus = Literal["disabled", "not_implemented", "skipped", "applied", "failed"]
CostStatus = Literal["known", "estimated", "unknown", "not_billable"]


class DTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FeatureFlags(DTO):
    router: bool = False
    rewrite: bool = False
    context: bool = False
    memory: bool = False


class Constraints(DTO):
    max_total_usd: Decimal | None = Field(default=None, gt=0)
    deadline_ms: int = Field(default=15000, ge=100, le=120000)


class ChatRequest(DTO):
    session_id: str = Field(min_length=1, max_length=64)
    client_request_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=50000)
    mode: Literal["baseline", "optimized"]
    policy_id: str | None = None
    flags: FeatureFlags | None = None
    constraints: Constraints = Field(default_factory=Constraints)

    @model_validator(mode="after")
    def validate_mode(self) -> "ChatRequest":
        if not self.message.strip():
            raise ValueError("Message must not be blank")
        if self.mode == "baseline":
            if self.policy_id not in (None, "baseline") or (
                self.flags and any(self.flags.model_dump().values())
            ):
                raise ValueError("Baseline conflicts with policy/flags")
        elif self.policy_id not in (None, "foundation-mock-v3"):
            raise ValueError("Only foundation-mock-v3 is available in G0")
        return self


class EffectiveConfiguration(DTO):
    policy_id: str
    policy_version: str = "g0.1"
    flags: FeatureFlags


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


class DerivedMemory(DTO):
    snapshot_revision: int
    summaries: tuple[Summary, ...] = ()
    facts: tuple[Fact, ...] = ()


class ExecutionRequest(DTO):
    request_id: str
    principal: Principal
    request: ChatRequest
    namespace: Literal["chat", "eval"] = "chat"


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


class ContextResult(DTO):
    messages: tuple[Message, ...]
    provenance: tuple[str, ...]
    state: OptimizationState
    token_estimates: tuple[TokenEstimate, ...] = ()
    summary_needed: bool = False


class MemoryPlan(DTO):
    enabled: bool = False


class MemoryResult(DTO):
    snapshot: SessionSnapshot
    state: OptimizationState


class OptimizedPrompt(DTO):
    original: str
    proposed: str
    validation: Literal["preserved", "violation", "unknown"] = "unknown"
    state: OptimizationState


class TaskProfile(DTO):
    domain: str = "unknown"
    difficulty: str = "unknown"
    reason: str = "not_implemented_g0"


class ModelConfiguration(DTO):
    config_id: str
    model_id: str
    execution_source: Literal["mock"] = "mock"


class RegistrySnapshot(DTO):
    configurations: tuple[ModelConfiguration, ...]
    mock_config_id: str


class CostSnapshot(DTO):
    version: str = "g0-no-live-prices"


class PolicySnapshot(EffectiveConfiguration):
    pass


class RemainingBudget(DTO):
    usd: Decimal | None = None


class RouteDecision(DTO):
    model_id: str
    config_id: str
    effort: str = "none"
    policy_id: str
    reason: str = "foundation_fixed_mock"
    fallback_used: bool = False


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


class ProviderResult(DTO):
    text: str
    execution_source: Literal["mock"] = "mock"
    usage: Usage = Field(default_factory=lambda: Usage(scope="call"))
    cost: CostEstimate = Field(default_factory=lambda: CostEstimate(scope="call"))
    duration_ms: float


class CallRecord(DTO):
    call_id: str
    stage: Literal["provider"] = "provider"
    model_id: str
    usage: Usage
    cost: CostEstimate
    duration_ms: float


class ChatResponse(DTO):
    request_id: str
    session_id: str
    session_revision: int
    execution_source: Literal["mock"] = "mock"
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


class RecentRequest(DTO):
    request_id: str
    session_id: str
    status: str
    created_at: str
    e2e_ms: float | None


class Overview(DTO):
    scope: Literal["current_user_all_time"] = "current_user_all_time"
    execution_source: Literal["mock"] = "mock"
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
