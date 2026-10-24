from hashlib import sha256
from typing import Literal, Protocol

from app.config import Settings
from app.contracts.dtos import (
    ChatRequest,
    ChatResponse,
    Constraints,
    FeatureFlags,
    Principal,
    SessionInfo,
)
from app.evaluation.live_runner import (
    LiveExecutionRequest,
    LiveExecutionResult,
)
from app.evaluation.rendering import render_serving_input


class OrchestratorExecutorError(RuntimeError):
    pass


class EvaluationOrchestrator(Protocol):
    async def execute(
        self,
        principal: Principal,
        request: ChatRequest,
        *,
        namespace: Literal["chat", "eval"] = "chat",
    ) -> ChatResponse: ...


class EvaluationSessionStore(Protocol):
    async def create(
        self,
        principal: Principal,
        title: str,
    ) -> SessionInfo: ...

    async def purge(
        self,
        principal: Principal,
        session_id: str,
    ) -> None: ...


class OrchestratorLiveExecutor:
    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: EvaluationOrchestrator,
        sessions: EvaluationSessionStore,
        principal: Principal,
        optimized_flags: FeatureFlags | None = None,
    ) -> None:
        self._settings = settings
        self._orchestrator = orchestrator
        self._sessions = sessions
        self._principal = principal
        self._optimized_flags = (
            optimized_flags
            if optimized_flags is not None
            else FeatureFlags(
                router=True,
                rewrite=True,
                context=True,
                memory=True,
            )
        )

    def _require_live_gate(self) -> None:
        if self._settings.provider_mode != "live" or not self._settings.research_live_enabled:
            raise OrchestratorExecutorError(
                "live evaluation requires PROVIDER_MODE=live and RESEARCH_LIVE_ENABLED=true"
            )

    @staticmethod
    def _client_request_id(
        operation_key: str,
    ) -> str:
        digest = sha256(
            operation_key.encode("utf-8"),
        ).hexdigest()

        return f"eval:{digest}"

    async def execute(
        self,
        request: LiveExecutionRequest,
    ) -> LiveExecutionResult:
        self._require_live_gate()

        rendered = render_serving_input(
            request.serving_input,
        )

        if rendered.history:
            raise OrchestratorExecutorError(
                "memory evaluation requires an owner-reviewed session history seeding port"
            )

        title = (f"eval:{request.run_id}:{request.case_id}:{request.mode}")[:120]

        session = await self._sessions.create(
            self._principal,
            title,
        )

        try:
            flags = self._optimized_flags if request.mode == "optimized" else None

            response = await self._orchestrator.execute(
                self._principal,
                ChatRequest(
                    session_id=session.id,
                    client_request_id=(
                        self._client_request_id(
                            request.operation_key,
                        )
                    ),
                    message=(rendered.current_user_message),
                    mode=request.mode,
                    flags=flags,
                    constraints=Constraints(
                        max_total_usd=(request.max_total_usd),
                        deadline_ms=request.deadline_ms,
                    ),
                ),
                namespace="eval",
            )

            if response.execution_source != "live":
                raise OrchestratorExecutorError("orchestrator returned a non-live execution source")

            return LiveExecutionResult(
                operation_key=request.operation_key,
                mode=request.mode,
                prediction=response.response.content,
                model_id=response.route.model_id,
                config_id=response.route.config_id,
                usage=response.usage,
                cost=response.cost,
                duration_ms=response.timing.e2e_ms,
                calls=response.calls,
            )
        finally:
            await self._sessions.purge(
                self._principal,
                session.id,
            )
