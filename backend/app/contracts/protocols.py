from decimal import Decimal
from typing import Protocol

from .dtos import (
    ChatResponse,
    ContextBudgets,
    ContextFeatures,
    ContextResult,
    CostSnapshot,
    DerivedMemory,
    ExecutionRequest,
    FeatureFlags,
    MemoryPlan,
    MemoryResult,
    Message,
    OptimizedPrompt,
    Overview,
    PolicySnapshot,
    Principal,
    ProviderOptions,
    ProviderResult,
    RegistrySnapshot,
    RemainingBudget,
    RouteDecision,
    SessionDetail,
    SessionInfo,
    SessionSnapshot,
    TaskProfile,
)
from .progress import ProgressStage, ProgressStatus


class TaskAnalyzer(Protocol):
    def analyze(
        self, req: ExecutionRequest, prepared: ContextResult | None = None
    ) -> TaskProfile: ...


class PromptOptimizer(Protocol):
    async def optimize(
        self, req: ExecutionRequest, context: ContextResult, flags: FeatureFlags
    ) -> OptimizedPrompt: ...


class ContextManager(Protocol):
    def prepare(
        self, snapshot: SessionSnapshot, budgets: ContextBudgets, features: ContextFeatures
    ) -> ContextResult: ...


class MemoryManager(Protocol):
    async def prepare(self, snapshot: SessionSnapshot, plan: MemoryPlan) -> MemoryResult: ...
    async def update(self, execution: ExecutionRequest, snapshot: SessionSnapshot) -> None: ...


class ModelRouter(Protocol):
    def select(
        self,
        profile: TaskProfile,
        prepared: ContextResult,
        registry: RegistrySnapshot,
        costs: CostSnapshot,
        policy: PolicySnapshot,
        remaining: RemainingBudget,
    ) -> RouteDecision: ...


class LLMProvider(Protocol):
    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult: ...


class SessionStore(Protocol):
    async def create(self, principal: Principal, title: str) -> SessionInfo: ...
    async def list_owned(
        self, principal: Principal, offset: int = 0, limit: int = 50
    ) -> tuple[SessionInfo, ...]: ...
    async def detail(self, principal: Principal, session_id: str) -> SessionDetail: ...
    async def snapshot(self, principal: Principal, session_id: str) -> SessionSnapshot: ...
    async def purge(self, principal: Principal, session_id: str) -> None: ...
    async def claim(self, req: ExecutionRequest, payload_hash: str) -> ChatResponse | None: ...
    async def mark_dispatched(self, request_id: str) -> None: ...
    async def commit(self, req: ExecutionRequest, response: ChatResponse) -> ChatResponse: ...
    async def fail(self, request_id: str, code: str) -> None: ...
    async def recover_interrupted(self) -> None: ...


class TraceStore(Protocol):
    async def get_owned(self, principal: Principal, request_id: str) -> ChatResponse: ...
    async def overview(self, principal: Principal) -> Overview: ...


class BudgetLedger(Protocol):
    async def mark_dispatched(self, reservation_id: str) -> None: ...
    async def reserve(
        self,
        principal: Principal,
        request_id: str,
        call_id: str,
        upper_usd: Decimal,
        request_limit: Decimal,
    ) -> str: ...
    async def settle(self, reservation_id: str, actual_usd: Decimal | None) -> None: ...
    async def release(self, reservation_id: str) -> None: ...
    async def reconcile(
        self,
        principal: Principal,
        reservation_id: str,
        actual_usd: Decimal,
        reason: str,
        evidence_reference: str,
    ) -> str: ...


class MemoryStore(Protocol):
    async def load(self, principal: Principal, session_id: str) -> "DerivedMemory": ...
    async def load_user_memories(
        self, execution_principal: str, exclude_session_id: str
    ) -> tuple[SessionSnapshot, ...]: ...
    async def save(self, principal: Principal, session_id: str, state: "DerivedMemory") -> None: ...


class RouterOutcomeSink(Protocol):
    async def observe(
        self,
        execution: ExecutionRequest,
        route: RouteDecision,
        *,
        success: bool,
        tool_error: bool = False,
    ) -> None: ...


class ProgressSink(Protocol):
    async def start(self, request_id: str, stage: ProgressStage) -> None: ...

    async def finish(self, request_id: str, status: ProgressStatus) -> None: ...
