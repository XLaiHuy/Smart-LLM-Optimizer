from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest

from app.config import Settings
from app.contracts.dtos import (
    CallRecord,
    ChatRequest,
    ChatResponse,
    CostEstimate,
    EffectiveConfiguration,
    FeatureFlags,
    Message,
    Principal,
    RouteDecision,
    SessionInfo,
    Timing,
    Usage,
)
from app.evaluation.cases import (
    ConversationTurn,
    EvalCase,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MemoryServingInput,
    SourceMetadata,
)
from app.evaluation.live_exporting import export_live_suite
from app.evaluation.live_harness import LiveSuiteConfig, run_live_suite
from app.evaluation.live_runner import ExecutionMode, LiveExecutionRequest
from app.evaluation.orchestrator_executor import (
    OrchestratorExecutorError,
    OrchestratorLiveExecutor,
)
from app.evaluation.sea_ifeval import SEA_IFEVAL_GRADER_VERSION


def _principal() -> Principal:
    return Principal(
        id="evaluation-user",
        username="evaluation-user",
        role="admin",
        quota_usd=Decimal(5),
    )


def _session() -> SessionInfo:
    return SessionInfo(
        id="evaluation-session",
        title="evaluation",
        revision=0,
        created_at="2026-10-24T00:00:00Z",
        updated_at="2026-10-24T00:00:00Z",
    )


def _response(
    *,
    execution_source: Literal["mock", "live"] = "live",
) -> ChatResponse:
    call_usage = Usage(
        scope="call",
        input_tokens=10,
        output_tokens=3,
        cached_input_tokens=0,
        reasoning_tokens=0,
        usage_source="provider",
    )
    call_cost = CostEstimate(
        scope="call",
        status="estimated",
        serving_usd=Decimal("0.001"),
        price_catalog_version="catalog-v1",
    )

    return ChatResponse(
        request_id="request-001",
        session_id="evaluation-session",
        session_revision=1,
        execution_source=execution_source,
        response=Message(
            role="assistant",
            content="Kết quả thử nghiệm.",
        ),
        route=RouteDecision(
            model_id="live-model",
            config_id="live-config",
            policy_id="test-policy",
        ),
        effective_configuration=EffectiveConfiguration(
            policy_id="test-policy",
            flags=FeatureFlags(),
        ),
        usage=call_usage.model_copy(
            update={"scope": "all_calls"},
        ),
        cost=call_cost.model_copy(
            update={"scope": "all_calls"},
        ),
        timing=Timing(
            e2e_ms=12.5,
            provider_ms=10.0,
        ),
        calls=(
            CallRecord(
                call_id="call-001",
                model_id="live-model",
                usage=call_usage,
                cost=call_cost,
                duration_ms=10.0,
            ),
        ),
        optimizations=(),
    )


def _request(
    *,
    mode: ExecutionMode = "optimized",
    serving_input: InstructionServingInput | MemoryServingInput | None = None,
) -> LiveExecutionRequest:
    return LiveExecutionRequest(
        operation_key=f"run-001:case-001:0:{mode}",
        run_id="run-001",
        case_id="case-001",
        repeat_index=0,
        mode=mode,
        serving_input=serving_input
        or InstructionServingInput(
            prompt="Chỉ trả lời đúng một câu.",
        ),
        max_total_usd=Decimal("0.02"),
        deadline_ms=15_000,
    )


class FakeSessions:
    def __init__(self) -> None:
        self.created: list[tuple[Principal, str]] = []
        self.purged: list[tuple[Principal, str]] = []

    async def create(
        self,
        principal: Principal,
        title: str,
    ) -> SessionInfo:
        self.created.append((principal, title))
        return _session()

    async def purge(
        self,
        principal: Principal,
        session_id: str,
    ) -> None:
        self.purged.append((principal, session_id))


class FakeOrchestrator:
    def __init__(
        self,
        *,
        response: ChatResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or _response()
        self.error = error
        self.requests: list[
            tuple[
                Principal,
                ChatRequest,
                str,
            ]
        ] = []

    async def execute(
        self,
        principal: Principal,
        request: ChatRequest,
        *,
        namespace: str = "chat",
    ) -> ChatResponse:
        self.requests.append(
            (
                principal,
                request,
                namespace,
            ),
        )
        if self.error is not None:
            raise self.error
        return self.response


def _executor(
    *,
    settings: Settings | None = None,
    orchestrator: FakeOrchestrator | None = None,
    sessions: FakeSessions | None = None,
) -> tuple[
    OrchestratorLiveExecutor,
    FakeOrchestrator,
    FakeSessions,
]:
    selected_orchestrator = orchestrator or FakeOrchestrator()
    selected_sessions = sessions or FakeSessions()
    return (
        OrchestratorLiveExecutor(
            settings=settings
            or Settings(
                provider_mode="live",
                research_live_enabled=True,
            ),
            orchestrator=selected_orchestrator,
            sessions=selected_sessions,
            principal=_principal(),
        ),
        selected_orchestrator,
        selected_sessions,
    )


async def test_executor_dispatches_optimized_eval_and_purges_session() -> None:
    executor, orchestrator, sessions = _executor()
    source_request = _request()

    result = await executor.execute(source_request)

    assert len(orchestrator.requests) == 1
    principal, chat_request, namespace = orchestrator.requests[0]
    assert principal == _principal()
    assert namespace == "eval"
    assert chat_request.session_id == "evaluation-session"
    assert chat_request.client_request_id.startswith("eval:")
    assert len(chat_request.client_request_id) == 69
    assert chat_request.message == "Chỉ trả lời đúng một câu."
    assert chat_request.mode == "optimized"
    assert chat_request.flags == FeatureFlags(
        router=True,
        rewrite=True,
        context=True,
        memory=True,
    )
    assert chat_request.constraints.max_total_usd == Decimal("0.02")
    assert chat_request.constraints.deadline_ms == 15_000
    assert result.operation_key == source_request.operation_key
    assert result.prediction == "Kết quả thử nghiệm."
    assert result.config_id == "live-config"
    assert result.model_id == "live-model"
    assert sessions.purged == [
        (
            _principal(),
            "evaluation-session",
        ),
    ]


async def test_executor_dispatches_baseline_without_optimizer_flags() -> None:
    executor, orchestrator, _ = _executor()

    await executor.execute(
        _request(
            mode="baseline",
        ),
    )

    _, chat_request, _ = orchestrator.requests[0]
    assert chat_request.mode == "baseline"
    assert chat_request.flags is None


@pytest.mark.parametrize(
    ("provider_mode", "research_live_enabled"),
    [
        ("mock", True),
        ("live", False),
    ],
)
async def test_executor_requires_both_live_gates(
    provider_mode: Literal["mock", "live"],
    research_live_enabled: bool,
) -> None:
    executor, orchestrator, sessions = _executor(
        settings=Settings(
            provider_mode=provider_mode,
            research_live_enabled=research_live_enabled,
        ),
    )

    with pytest.raises(
        OrchestratorExecutorError,
        match="PROVIDER_MODE=live",
    ):
        await executor.execute(_request())

    assert orchestrator.requests == []
    assert sessions.created == []


async def test_executor_rejects_memory_history_before_session_creation() -> None:
    executor, orchestrator, sessions = _executor()
    memory_input = MemoryServingInput(
        turns=(
            ConversationTurn(
                turn_id="turn-001",
                turn_index=0,
                role="user",
                content="Tên tôi là Khoa.",
            ),
        ),
        checkpoint=0,
        question="Người dùng tên gì?",
    )

    with pytest.raises(
        OrchestratorExecutorError,
        match="history seeding port",
    ):
        await executor.execute(
            _request(
                serving_input=memory_input,
            ),
        )

    assert orchestrator.requests == []
    assert sessions.created == []


async def test_executor_rejects_non_live_result_and_purges_session() -> None:
    executor, _, sessions = _executor(
        orchestrator=FakeOrchestrator(
            response=_response(
                execution_source="mock",
            ),
        ),
    )

    with pytest.raises(
        OrchestratorExecutorError,
        match="non-live",
    ):
        await executor.execute(_request())

    assert sessions.purged == [
        (
            _principal(),
            "evaluation-session",
        ),
    ]


async def test_executor_purges_session_when_orchestrator_fails() -> None:
    executor, _, sessions = _executor(
        orchestrator=FakeOrchestrator(
            error=RuntimeError("provider failed"),
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="provider failed",
    ):
        await executor.execute(_request())

    assert sessions.purged == [
        (
            _principal(),
            "evaluation-session",
        ),
    ]


async def test_executor_composes_live_suite_and_export(
    tmp_path: Path,
) -> None:
    executor, orchestrator, sessions = _executor()

    case = EvalCase(
        case_id="live-integration-001",
        task_family="instruction",
        source=SourceMetadata(
            suite_name="functional-live-fixture",
            source_name="local-live-fixture",
            source_revision="fixture-revision",
            source_record_id="source-001",
            group_id="source-001",
            split="dev",
            language="vi",
            qualification_status="qualified",
            license_id="MIT",
        ),
        serving_input=InstructionServingInput(
            prompt="Viết câu trả lời có tiêu đề.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id="detectable_format:title",
                ),
            ),
            evaluator_version=SEA_IFEVAL_GRADER_VERSION,
        ),
        tags=("functional-fixture",),
    )

    result = await run_live_suite(
        cases=(case,),
        config=LiveSuiteConfig(
            run_id="live-integration-run",
            max_total_usd_per_arm=Decimal("0.01"),
            max_suite_usd=Decimal("0.02"),
        ),
        executor=executor,
        language_detector=lambda _: "vi",
    )

    receipt = export_live_suite(
        result=result,
        output_dir=tmp_path / "live-report",
    )

    assert len(orchestrator.requests) == 2
    assert all(namespace == "eval" for _, _, namespace in orchestrator.requests)
    assert len(sessions.created) == 2
    assert len(sessions.purged) == 2

    assert result.baseline.case_count == 1
    assert result.optimized.case_count == 1
    assert result.comparison.pair_count == 1
    assert result.research_eligible is False

    assert receipt.pair_results.row_count == 1
    assert receipt.report_path.exists()
    assert "evaluator_target" not in (
        receipt.pair_results.output_path.read_text(
            encoding="utf-8",
        )
    )
