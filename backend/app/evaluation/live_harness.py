from decimal import Decimal
from math import ceil, fsum
from statistics import median
from typing import Literal, Self

from pydantic import Field, model_validator

from app.evaluation.aggregation import MetricAggregate
from app.evaluation.cases import (
    EvalCase,
    EvalModel,
    NonBlankString,
)
from app.evaluation.comparison import MeanMetricDelta, PairOutcome
from app.evaluation.live_runner import (
    ExecutionMode,
    LivePairConfig,
    LivePairResult,
    LivePredictionExecutor,
    run_live_pair,
)
from app.evaluation.sea_ifeval import LanguageDetector


class LiveHarnessError(ValueError):
    pass


class LiveSuiteConfig(EvalModel):
    run_id: NonBlankString
    repeat_index: int = Field(default=0, ge=0)
    seed: int = Field(default=0, ge=0)
    max_total_usd_per_arm: Decimal = Field(
        default=Decimal("0.02"),
        gt=0,
    )
    max_suite_usd: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
    )
    deadline_ms: int = Field(
        default=15_000,
        ge=100,
        le=120_000,
    )
    run_purpose: Literal["engineering_pilot"] = "engineering_pilot"


class OptionalIntegerAggregate(EvalModel):
    known_subtotal: int = Field(ge=0)
    unknown_case_count: int = Field(ge=0)
    complete_total: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_complete_total(self) -> Self:
        if self.unknown_case_count == 0:
            if self.complete_total != self.known_subtotal:
                raise ValueError(
                    "complete_total must equal known_subtotal when no values are unknown"
                )
        elif self.complete_total is not None:
            raise ValueError("complete_total must be null when values are unknown")

        return self


class LiveUsageAggregate(EvalModel):
    input_tokens: OptionalIntegerAggregate
    output_tokens: OptionalIntegerAggregate
    cached_input_tokens: OptionalIntegerAggregate
    reasoning_tokens: OptionalIntegerAggregate


class LiveCostAggregate(EvalModel):
    case_count: int = Field(gt=0)
    priced_case_count: int = Field(ge=0)
    unknown_case_count: int = Field(ge=0)
    not_billable_case_count: int = Field(ge=0)
    known_subtotal_usd: Decimal = Field(ge=0)
    complete_total_usd: Decimal | None = Field(default=None, ge=0)
    price_catalog_versions: tuple[NonBlankString, ...]

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        classified_count = (
            self.priced_case_count + self.unknown_case_count + self.not_billable_case_count
        )

        if classified_count != self.case_count:
            raise ValueError("cost classifications must equal case_count")

        if self.priced_case_count == self.case_count:
            if self.complete_total_usd != self.known_subtotal_usd:
                raise ValueError(
                    "complete_total_usd must equal known_subtotal_usd when all cases are priced"
                )
        elif self.complete_total_usd is not None:
            raise ValueError("complete_total_usd must be null when any case is unpriced")

        return self


class LiveLatencyAggregate(EvalModel):
    case_count: int = Field(gt=0)
    total_ms: float = Field(ge=0)
    mean_ms: float = Field(ge=0)
    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)


class LiveArmAggregate(EvalModel):
    mode: ExecutionMode
    case_count: int = Field(gt=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    metrics: tuple[MetricAggregate, ...] = Field(min_length=1)
    usage: LiveUsageAggregate
    cost: LiveCostAggregate
    latency: LiveLatencyAggregate
    call_count: int = Field(gt=0)
    model_ids: tuple[NonBlankString, ...] = Field(min_length=1)
    config_ids: tuple[NonBlankString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.passed_count + self.failed_count != self.case_count:
            raise ValueError("passed_count plus failed_count must equal case_count")

        if any(metric.sample_count != self.case_count for metric in self.metrics):
            raise ValueError("every metric sample_count must equal case_count")

        if self.cost.case_count != self.case_count:
            raise ValueError("cost case_count must equal arm case_count")

        if self.latency.case_count != self.case_count:
            raise ValueError("latency case_count must equal arm case_count")

        return self


class LivePairAggregate(EvalModel):
    pair_count: int = Field(gt=0)
    both_pass_count: int = Field(ge=0)
    regression_count: int = Field(ge=0)
    improvement_count: int = Field(ge=0)
    both_fail_count: int = Field(ge=0)
    regression_rate: float = Field(ge=0, le=1)
    improvement_rate: float = Field(ge=0, le=1)
    metric_deltas: tuple[MeanMetricDelta, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        outcome_count = (
            self.both_pass_count
            + self.regression_count
            + self.improvement_count
            + self.both_fail_count
        )

        if outcome_count != self.pair_count:
            raise ValueError("paired outcome counts must equal pair_count")

        if any(metric.sample_count != self.pair_count for metric in self.metric_deltas):
            raise ValueError("every metric sample_count must equal pair_count")

        return self


class LiveSuiteResult(EvalModel):
    schema_version: Literal["eval-live-suite-v1"] = "eval-live-suite-v1"
    run_id: NonBlankString
    repeat_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    suite_name: NonBlankString
    source_name: NonBlankString
    source_revision: NonBlankString
    pairs: tuple[LivePairResult, ...] = Field(min_length=1)
    baseline: LiveArmAggregate
    optimized: LiveArmAggregate
    comparison: LivePairAggregate
    run_purpose: Literal["engineering_pilot"] = "engineering_pilot"
    research_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_pair_count(self) -> Self:
        pair_count = len(self.pairs)

        if self.baseline.case_count != pair_count:
            raise ValueError("baseline case_count must equal pairs length")

        if self.optimized.case_count != pair_count:
            raise ValueError("optimized case_count must equal pairs length")

        if self.comparison.pair_count != pair_count:
            raise ValueError("comparison pair_count must equal pairs length")

        return self


def _validate_cases(
    cases: tuple[EvalCase, ...],
    config: LiveSuiteConfig,
) -> tuple[EvalCase, ...]:
    if not cases:
        raise LiveHarnessError("live suite requires at least one case")

    maximum_planned_spend = config.max_total_usd_per_arm * len(cases) * 2

    if maximum_planned_spend > config.max_suite_usd:
        raise LiveHarnessError(
            "per-arm caps exceed max_suite_usd: "
            f"planned={maximum_planned_spend}, "
            f"suite_cap={config.max_suite_usd}"
        )

    seen_case_ids: set[str] = set()
    seen_source_record_ids: set[str] = set()
    first = cases[0]
    expected_source = (
        first.task_family,
        first.source.suite_name,
        first.source.source_name,
        first.source.source_revision,
        first.source.split,
        first.source.language,
        first.source.qualification_status,
    )

    for case in cases:
        if case.source.split != "dev":
            raise LiveHarnessError("live suite requires DEV cases")

        if case.source.qualification_status != "qualified":
            raise LiveHarnessError("live suite requires qualified cases")

        if case.case_id in seen_case_ids:
            raise LiveHarnessError(f"duplicate case_id: {case.case_id!r}")

        if case.source.source_record_id in seen_source_record_ids:
            raise LiveHarnessError(f"duplicate source_record_id: {case.source.source_record_id!r}")

        observed_source = (
            case.task_family,
            case.source.suite_name,
            case.source.source_name,
            case.source.source_revision,
            case.source.split,
            case.source.language,
            case.source.qualification_status,
        )

        if observed_source != expected_source:
            raise LiveHarnessError(
                "live suite cases must share task family, source, revision, split, "
                "language, and qualification status"
            )

        seen_case_ids.add(case.case_id)
        seen_source_record_ids.add(case.source.source_record_id)

    return tuple(sorted(cases, key=lambda case: case.case_id))


def _optional_integer_aggregate(
    values: tuple[int | None, ...],
) -> OptionalIntegerAggregate:
    known_values = tuple(value for value in values if value is not None)
    unknown_case_count = len(values) - len(known_values)
    known_subtotal = sum(known_values)

    return OptionalIntegerAggregate(
        known_subtotal=known_subtotal,
        unknown_case_count=unknown_case_count,
        complete_total=(known_subtotal if unknown_case_count == 0 else None),
    )


def _aggregate_cost(
    pairs: tuple[LivePairResult, ...],
    mode: ExecutionMode,
) -> LiveCostAggregate:
    costs = tuple(
        (pair.baseline if mode == "baseline" else pair.optimized).execution.cost for pair in pairs
    )
    priced_costs = tuple(
        cost
        for cost in costs
        if cost.status in {"known", "estimated"} and cost.serving_usd is not None
    )
    not_billable_case_count = sum(cost.status == "not_billable" for cost in costs)
    unknown_case_count = len(costs) - len(priced_costs) - not_billable_case_count
    known_subtotal_usd = sum(
        (cost.serving_usd for cost in priced_costs if cost.serving_usd is not None),
        start=Decimal(0),
    )

    return LiveCostAggregate(
        case_count=len(costs),
        priced_case_count=len(priced_costs),
        unknown_case_count=unknown_case_count,
        not_billable_case_count=not_billable_case_count,
        known_subtotal_usd=known_subtotal_usd,
        complete_total_usd=(known_subtotal_usd if len(priced_costs) == len(costs) else None),
        price_catalog_versions=tuple(
            sorted(
                {
                    cost.price_catalog_version
                    for cost in priced_costs
                    if cost.price_catalog_version is not None
                },
            ),
        ),
    )


def _aggregate_arm(
    pairs: tuple[LivePairResult, ...],
    mode: ExecutionMode,
) -> LiveArmAggregate:
    arms = tuple(pair.baseline if mode == "baseline" else pair.optimized for pair in pairs)
    grades = tuple(arm.grade for arm in arms)
    executions = tuple(arm.execution for arm in arms)
    expected_metric_names = {metric.name for metric in grades[0].metrics}

    for grade in grades[1:]:
        if {metric.name for metric in grade.metrics} != expected_metric_names:
            raise LiveHarnessError("metric schema mismatch across live suite cases")

    metric_aggregates: list[MetricAggregate] = []

    for metric_name in sorted(expected_metric_names):
        values = tuple(
            next(metric.value for metric in grade.metrics if metric.name == metric_name)
            for grade in grades
        )
        value_sum = fsum(values)
        metric_aggregates.append(
            MetricAggregate(
                name=metric_name,
                value_sum=value_sum,
                sample_count=len(values),
                mean=value_sum / len(values),
            ),
        )

    durations = tuple(execution.duration_ms for execution in executions)
    ordered_durations = sorted(durations)
    case_count = len(executions)
    passed_count = sum(grade.passed for grade in grades)

    return LiveArmAggregate(
        mode=mode,
        case_count=case_count,
        passed_count=passed_count,
        failed_count=case_count - passed_count,
        pass_rate=passed_count / case_count,
        metrics=tuple(metric_aggregates),
        usage=LiveUsageAggregate(
            input_tokens=_optional_integer_aggregate(
                tuple(execution.usage.input_tokens for execution in executions),
            ),
            output_tokens=_optional_integer_aggregate(
                tuple(execution.usage.output_tokens for execution in executions),
            ),
            cached_input_tokens=_optional_integer_aggregate(
                tuple(execution.usage.cached_input_tokens for execution in executions),
            ),
            reasoning_tokens=_optional_integer_aggregate(
                tuple(execution.usage.reasoning_tokens for execution in executions),
            ),
        ),
        cost=_aggregate_cost(pairs, mode),
        latency=LiveLatencyAggregate(
            case_count=case_count,
            total_ms=fsum(durations),
            mean_ms=fsum(durations) / case_count,
            p50_ms=float(median(durations)),
            p95_ms=ordered_durations[ceil(0.95 * case_count) - 1],
        ),
        call_count=sum(len(execution.calls) for execution in executions),
        model_ids=tuple(sorted({execution.model_id for execution in executions})),
        config_ids=tuple(sorted({execution.config_id for execution in executions})),
    )


def _outcome(pair: LivePairResult) -> PairOutcome:
    baseline_passed = pair.baseline.grade.passed
    optimized_passed = pair.optimized.grade.passed

    if baseline_passed and optimized_passed:
        return "both_pass"
    if baseline_passed:
        return "regression"
    if optimized_passed:
        return "improvement"
    return "both_fail"


def _aggregate_pairs(
    pairs: tuple[LivePairResult, ...],
) -> LivePairAggregate:
    outcomes = tuple(_outcome(pair) for pair in pairs)
    expected_metric_names = {metric.name for metric in pairs[0].baseline.grade.metrics}

    metric_deltas: list[MeanMetricDelta] = []

    for pair in pairs:
        baseline_names = {metric.name for metric in pair.baseline.grade.metrics}
        optimized_names = {metric.name for metric in pair.optimized.grade.metrics}

        if baseline_names != expected_metric_names or optimized_names != expected_metric_names:
            raise LiveHarnessError("paired metric schema mismatch")

    for metric_name in sorted(expected_metric_names):
        deltas = tuple(
            next(
                metric.value
                for metric in pair.optimized.grade.metrics
                if metric.name == metric_name
            )
            - next(
                metric.value for metric in pair.baseline.grade.metrics if metric.name == metric_name
            )
            for pair in pairs
        )
        metric_deltas.append(
            MeanMetricDelta(
                name=metric_name,
                sample_count=len(deltas),
                mean_delta=fsum(deltas) / len(deltas),
            ),
        )

    pair_count = len(pairs)
    regression_count = outcomes.count("regression")
    improvement_count = outcomes.count("improvement")

    return LivePairAggregate(
        pair_count=pair_count,
        both_pass_count=outcomes.count("both_pass"),
        regression_count=regression_count,
        improvement_count=improvement_count,
        both_fail_count=outcomes.count("both_fail"),
        regression_rate=regression_count / pair_count,
        improvement_rate=improvement_count / pair_count,
        metric_deltas=tuple(metric_deltas),
    )


async def run_live_suite(
    *,
    cases: tuple[EvalCase, ...],
    config: LiveSuiteConfig,
    executor: LivePredictionExecutor,
    language_detector: LanguageDetector | None = None,
) -> LiveSuiteResult:
    ordered_cases = _validate_cases(cases, config)
    pairs: list[LivePairResult] = []
    pair_config = LivePairConfig(
        run_id=config.run_id,
        repeat_index=config.repeat_index,
        seed=config.seed,
        max_total_usd_per_arm=config.max_total_usd_per_arm,
        deadline_ms=config.deadline_ms,
    )

    for case in ordered_cases:
        pairs.append(
            await run_live_pair(
                case=case,
                config=pair_config,
                executor=executor,
                language_detector=language_detector,
            ),
        )

    paired_results = tuple(pairs)
    source = ordered_cases[0].source

    return LiveSuiteResult(
        run_id=config.run_id,
        repeat_index=config.repeat_index,
        seed=config.seed,
        suite_name=source.suite_name,
        source_name=source.source_name,
        source_revision=source.source_revision,
        pairs=paired_results,
        baseline=_aggregate_arm(paired_results, "baseline"),
        optimized=_aggregate_arm(paired_results, "optimized"),
        comparison=_aggregate_pairs(paired_results),
    )
