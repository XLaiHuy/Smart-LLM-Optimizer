import asyncio
import hashlib
import json
from time import perf_counter
from typing import Literal
from uuid import uuid4

from app.contracts.dtos import (
    CallRecord,
    ChatRequest,
    ChatResponse,
    ContextBudgets,
    ContextFeatures,
    CostEstimate,
    CostSnapshot,
    ExecutionRequest,
    MemoryPlan,
    Message,
    PolicySnapshot,
    Principal,
    ProviderOptions,
    RegistrySnapshot,
    RemainingBudget,
    Timing,
    Usage,
)
from app.contracts.errors import AppError
from app.contracts.protocols import (
    ContextManager,
    LLMProvider,
    MemoryManager,
    ModelRouter,
    PromptOptimizer,
    SessionStore,
    TaskAnalyzer,
)
from app.core.policy import noop_state, resolve_configuration


class Orchestrator:
    def __init__(
        self,
        sessions: SessionStore,
        provider: LLMProvider,
        analyzer: TaskAnalyzer,
        memory: MemoryManager,
        context: ContextManager,
        prompt: PromptOptimizer,
        router: ModelRouter,
        registry: RegistrySnapshot,
    ):
        self.sessions = sessions
        self.provider = provider
        self.analyzer = analyzer
        self.memory = memory
        self.context = context
        self.prompt = prompt
        self.router = router
        self.registry = registry

    async def execute(
        self,
        principal: Principal,
        request: ChatRequest,
        *,
        namespace: Literal["chat", "eval"] = "chat",
    ) -> ChatResponse:
        started = perf_counter()
        execution = ExecutionRequest(
            request_id=str(uuid4()), principal=principal, request=request, namespace=namespace
        )
        payload_hash = hashlib.sha256(
            json.dumps(request.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        saved = await self.sessions.claim(execution, payload_hash)
        if saved is not None:
            return saved
        try:
            async with asyncio.timeout(request.constraints.deadline_ms / 1000):
                snapshot = await self.sessions.snapshot(principal, request.session_id)
                config = resolve_configuration(request)
                profile = self.analyzer.analyze(execution)
                memory = await self.memory.prepare(
                    snapshot, MemoryPlan(enabled=config.flags.memory)
                )
                prepared = self.context.prepare(
                    memory.snapshot,
                    ContextBudgets(),
                    ContextFeatures(
                        current_turn=Message(role="user", content=request.message),
                        flags=config.flags,
                    ),
                )
                rewrite = await self.prompt.optimize(execution, prepared, config.flags)
                if rewrite.proposed != request.message:
                    raise AppError(
                        "OUTPUT_INVALID", 502, "G0 no-op altered input", execution.request_id
                    )
                route = self.router.select(
                    profile,
                    prepared,
                    self.registry,
                    CostSnapshot(),
                    PolicySnapshot(**config.model_dump()),
                    RemainingBudget(),
                )
                call_id = str(uuid4())
                await self.sessions.mark_dispatched(execution.request_id)
                result = await self.provider.generate(
                    prepared.messages,
                    ProviderOptions(
                        request_id=execution.request_id,
                        call_id=call_id,
                        config_id=route.config_id,
                        model_id=route.model_id,
                    ),
                )
                if not result.text:
                    raise AppError(
                        "OUTPUT_INVALID",
                        502,
                        "Provider returned an empty response",
                        execution.request_id,
                    )
                response = ChatResponse(
                    request_id=execution.request_id,
                    session_id=request.session_id,
                    session_revision=snapshot.revision + 1,
                    response=Message(role="assistant", content=result.text),
                    route=route,
                    requested_flags=request.flags,
                    effective_configuration=config,
                    usage=Usage(),
                    cost=CostEstimate(),
                    timing=Timing(
                        e2e_ms=(perf_counter() - started) * 1000, provider_ms=result.duration_ms
                    ),
                    calls=(
                        CallRecord(
                            call_id=call_id,
                            model_id=route.model_id,
                            usage=result.usage,
                            cost=result.cost,
                            duration_ms=result.duration_ms,
                        ),
                    ),
                    optimizations=(
                        noop_state("router", config.flags.router),
                        rewrite.state,
                        prepared.state,
                        memory.state,
                    ),
                )
                return await self.sessions.commit(execution, response)
        except asyncio.CancelledError:
            await asyncio.shield(self.sessions.fail(execution.request_id, "REQUEST_CANCELLED"))
            raise
        except TimeoutError as exc:
            await self.sessions.fail(execution.request_id, "PROVIDER_TIMEOUT")
            raise AppError(
                "PROVIDER_TIMEOUT", 504, "Request deadline exceeded", execution.request_id
            ) from exc
        except AppError as exc:
            await self.sessions.fail(execution.request_id, exc.code)
            raise
        except Exception as exc:
            await self.sessions.fail(execution.request_id, "DEPENDENCY_UNAVAILABLE")
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Dependency unavailable", execution.request_id
            ) from exc
