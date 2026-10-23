from decimal import Decimal

import pytest

from app.contracts.dtos import (
    CallRecord,
    CostEstimate,
    Usage,
)
from app.evaluation.cases import (
    EvalCase,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    SourceMetadata,
)
from app.evaluation.live_runner import (
    LiveExecutionRequest,
    LiveExecutionResult,
    LivePairConfig,
    LiveRunnerError,
    run_live_pair,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
)


def _dev_case() -> EvalCase:
    return EvalCase(
        case_id="sea-ifeval-dev-001",
        task_family="instruction",
        source=SourceMetadata(
            suite_name="sea-ifeval-vi",
            source_name="sea-ifeval-vi-v1-1",
            source_revision="fixture-revision",
            source_record_id="001",
            group_id="001",
            split="dev",
            language="vi",
            qualification_status="candidate",
            license_id="CC-BY-4.0",
        ),
        serving_input=InstructionServingInput(
            prompt="Viết câu trả lời có tiêu đề.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id=("detectable_format:title"),
                ),
            ),
            evaluator_version=(SEA_IFEVAL_GRADER_VERSION),
        ),
        tags=("sea-ifeval",),
    )


class FakeLiveExecutor:
    def __init__(self) -> None:
        self.requests: list[LiveExecutionRequest] = []

    async def execute(
        self,
        request: LiveExecutionRequest,
    ) -> LiveExecutionResult:
        self.requests.append(request)

        prediction = "Không có tiêu đề." if request.mode == "baseline" else "<<Tiêu đề>>"

        call_cost = CostEstimate(
            scope="call",
            status="estimated",
            serving_usd=Decimal("0.001"),
            price_catalog_version="test-catalog-v1",
        )

        call_usage = Usage(
            scope="call",
            input_tokens=10,
            output_tokens=5,
            cached_input_tokens=0,
            reasoning_tokens=0,
            usage_source="provider",
        )

        return LiveExecutionResult(
            operation_key=request.operation_key,
            mode=request.mode,
            prediction=prediction,
            model_id="fake-live-model",
            config_id=f"{request.mode}-config",
            usage=call_usage.model_copy(
                update={"scope": "all_calls"},
            ),
            cost=call_cost.model_copy(
                update={"scope": "all_calls"},
            ),
            duration_ms=10.0,
            calls=(
                CallRecord(
                    call_id=(f"call-{request.mode}"),
                    model_id="fake-live-model",
                    usage=call_usage,
                    cost=call_cost,
                    duration_ms=10.0,
                ),
            ),
        )


async def test_live_runner_executes_and_grades_pair() -> None:
    case = _dev_case()
    executor = FakeLiveExecutor()

    result = await run_live_pair(
        case=case,
        config=LivePairConfig(
            run_id="engineering-pilot-001",
            seed=7,
        ),
        executor=executor,
        language_detector=lambda _: "vi",
    )

    assert {request.mode for request in executor.requests} == {
        "baseline",
        "optimized",
    }

    assert all(request.serving_input == case.serving_input for request in executor.requests)

    assert all("evaluator_target" not in request.model_dump_json() for request in executor.requests)

    assert result.baseline.grade.passed is False
    assert result.optimized.grade.passed is True
    assert result.research_eligible is False


async def test_live_runner_rejects_holdout() -> None:
    dev_case = _dev_case()
    holdout_case = dev_case.model_copy(
        update={
            "source": dev_case.source.model_copy(
                update={"split": "holdout"},
            ),
        },
    )
    executor = FakeLiveExecutor()

    with pytest.raises(
        LiveRunnerError,
        match="DEV",
    ):
        await run_live_pair(
            case=holdout_case,
            config=LivePairConfig(
                run_id="engineering-pilot-001",
            ),
            executor=executor,
            language_detector=lambda _: "vi",
        )

    assert executor.requests == []
