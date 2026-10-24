from decimal import Decimal
from hashlib import sha256
from typing import Literal, Protocol, TypeAlias

from pydantic import Field

from app.contracts.dtos import (
    CallRecord,
    CostEstimate,
    Usage,
)
from app.evaluation.cases import (
    EvalCase,
    EvalModel,
    InstructionServingInput,
    NonBlankString,
    ServingInput,
    SourceMetadata,
)
from app.evaluation.dispatcher import CaseGrade, grade_case
from app.evaluation.sea_ifeval import LanguageDetector

ExecutionMode = Literal["baseline", "optimized"]
ExecutionOrder: TypeAlias = tuple[
    ExecutionMode,
    ExecutionMode,
]


class LiveRunnerError(ValueError):
    pass


class LivePairConfig(EvalModel):
    run_id: NonBlankString
    repeat_index: int = Field(default=0, ge=0)
    seed: int = Field(default=0, ge=0)
    max_total_usd_per_arm: Decimal = Field(
        default=Decimal("0.02"),
        gt=0,
    )
    deadline_ms: int = Field(
        default=15_000,
        ge=100,
        le=120_000,
    )
    run_purpose: Literal["engineering_pilot"] = "engineering_pilot"


class LiveExecutionRequest(EvalModel):
    operation_key: NonBlankString
    run_id: NonBlankString
    case_id: NonBlankString
    repeat_index: int = Field(ge=0)
    mode: ExecutionMode
    serving_input: ServingInput
    max_total_usd: Decimal = Field(gt=0)
    deadline_ms: int = Field(
        ge=100,
        le=120_000,
    )


class LiveExecutionResult(EvalModel):
    operation_key: NonBlankString
    mode: ExecutionMode
    prediction: str
    execution_source: Literal["live"] = "live"
    model_id: NonBlankString
    config_id: NonBlankString
    usage: Usage
    cost: CostEstimate
    duration_ms: float = Field(ge=0)
    calls: tuple[CallRecord, ...] = Field(
        min_length=1,
    )


class LivePredictionExecutor(Protocol):
    async def execute(
        self,
        request: LiveExecutionRequest,
    ) -> LiveExecutionResult: ...


class LiveArmResult(EvalModel):
    execution: LiveExecutionResult
    grade: CaseGrade


class LivePairResult(EvalModel):
    schema_version: Literal["eval-live-pair-v1"] = "eval-live-pair-v1"
    run_id: NonBlankString
    case_id: NonBlankString
    source: SourceMetadata
    repeat_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    execution_order: ExecutionOrder
    baseline: LiveArmResult
    optimized: LiveArmResult
    run_purpose: Literal["engineering_pilot"] = "engineering_pilot"
    research_eligible: Literal[False] = False


def _execution_order(
    *,
    seed: int,
    case_id: str,
) -> ExecutionOrder:
    digest = sha256(
        f"{seed}\0{case_id}".encode(),
    ).digest()

    if digest[0] % 2 == 0:
        return ("baseline", "optimized")

    return ("optimized", "baseline")


def _operation_key(
    *,
    config: LivePairConfig,
    case: EvalCase,
    mode: ExecutionMode,
) -> str:
    return f"{config.run_id}:{case.case_id}:{config.repeat_index}:{mode}"


def _validate_case(case: EvalCase) -> None:
    if case.source.split != "dev":
        raise LiveRunnerError("engineering live pilot requires a DEV case")

    if case.source.qualification_status != "qualified":
        raise LiveRunnerError("live execution requires a qualified source")

    if not isinstance(
        case.serving_input,
        InstructionServingInput,
    ):
        raise LiveRunnerError("initial live pilot supports instruction cases only")


def _validate_execution(
    *,
    request: LiveExecutionRequest,
    execution: LiveExecutionResult,
) -> None:
    if execution.operation_key != request.operation_key:
        raise LiveRunnerError("executor returned a mismatched operation key")

    if execution.mode != request.mode:
        raise LiveRunnerError("executor returned a mismatched execution mode")

    if not execution.prediction.strip():
        raise LiveRunnerError("executor returned a blank prediction")


async def run_live_pair(
    *,
    case: EvalCase,
    config: LivePairConfig,
    executor: LivePredictionExecutor,
    language_detector: LanguageDetector,
) -> LivePairResult:
    _validate_case(case)

    order = _execution_order(
        seed=config.seed,
        case_id=case.case_id,
    )

    results: dict[
        ExecutionMode,
        LiveArmResult,
    ] = {}

    for mode in order:
        request = LiveExecutionRequest(
            operation_key=_operation_key(
                config=config,
                case=case,
                mode=mode,
            ),
            run_id=config.run_id,
            case_id=case.case_id,
            repeat_index=config.repeat_index,
            mode=mode,
            serving_input=case.serving_input,
            max_total_usd=(config.max_total_usd_per_arm),
            deadline_ms=config.deadline_ms,
        )

        execution = await executor.execute(request)

        _validate_execution(
            request=request,
            execution=execution,
        )

        grade = grade_case(
            case=case,
            prediction=execution.prediction,
            language_detector=language_detector,
        )

        results[mode] = LiveArmResult(
            execution=execution,
            grade=grade,
        )

    return LivePairResult(
        run_id=config.run_id,
        case_id=case.case_id,
        source=case.source,
        repeat_index=config.repeat_index,
        seed=config.seed,
        execution_order=order,
        baseline=results["baseline"],
        optimized=results["optimized"],
    )
