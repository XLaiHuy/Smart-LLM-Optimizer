from math import fsum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.evaluation.cases import (
    DatasetSplit,
    EvalModel,
    NonBlankString,
    QualificationStatus,
    TaskFamily,
)
from app.evaluation.dispatcher import CaseGrade, MetricName
from app.evaluation.runs import EvaluatedCaseRow, FixtureRun


class PairDiffError(ValueError):
    pass


PairOutcome = Literal[
    "both_pass",
    "regression",
    "improvement",
    "both_fail",
]


class PairedMetricDelta(EvalModel):
    name: MetricName
    baseline_value: float = Field(ge=0.0, le=1.0)
    variant_value: float = Field(ge=0.0, le=1.0)
    delta: float = Field(ge=-1.0, le=1.0)


class PairedCaseDiff(EvalModel):
    baseline_run_id: NonBlankString
    baseline_config_id: NonBlankString
    variant_run_id: NonBlankString
    variant_config_id: NonBlankString
    repeat_index: int = Field(ge=0)
    seed: int
    research_eligible: Literal[False] = False

    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: NonBlankString
    task_family: TaskFamily
    suite_name: NonBlankString
    source_name: NonBlankString
    source_revision: NonBlankString
    source_record_id: NonBlankString
    group_id: NonBlankString
    split: DatasetSplit
    language: NonBlankString
    qualification_status: QualificationStatus
    tags: tuple[NonBlankString, ...]

    baseline_prediction: str
    variant_prediction: str
    baseline_grade: CaseGrade
    variant_grade: CaseGrade
    outcome: PairOutcome
    metric_deltas: tuple[PairedMetricDelta, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_metric_deltas(self) -> Self:
        metric_names = tuple(metric.name for metric in self.metric_deltas)

        if len(set(metric_names)) != len(metric_names):
            raise ValueError("metric delta names must be unique")

        return self


class MeanMetricDelta(EvalModel):
    name: MetricName
    sample_count: int = Field(gt=0)
    mean_delta: float = Field(ge=-1.0, le=1.0)


class PairGroupSummary(EvalModel):
    suite_name: NonBlankString
    split: DatasetSplit
    task_family: TaskFamily
    pair_count: int = Field(gt=0)
    independent_group_count: int = Field(gt=0)
    both_pass_count: int = Field(ge=0)
    regression_count: int = Field(ge=0)
    improvement_count: int = Field(ge=0)
    both_fail_count: int = Field(ge=0)
    regression_rate: float = Field(ge=0.0, le=1.0)
    improvement_rate: float = Field(ge=0.0, le=1.0)
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
            raise ValueError("outcome counts must equal pair_count")

        if self.independent_group_count > self.pair_count:
            raise ValueError("independent_group_count must not exceed pair_count")

        if any(metric.sample_count != self.pair_count for metric in self.metric_deltas):
            raise ValueError("every metric sample_count must equal pair_count")

        return self


class FixturePairReport(EvalModel):
    baseline_run_id: NonBlankString
    baseline_config_id: NonBlankString
    variant_run_id: NonBlankString
    variant_config_id: NonBlankString
    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repeat_index: int = Field(ge=0)
    seed: int
    run_purpose: Literal["smoke"] = "smoke"
    execution_source: Literal["fixture"] = "fixture"
    namespace: Literal["eval"] = "eval"
    research_eligible: Literal[False] = False
    total_pair_count: int = Field(gt=0)
    pairs: tuple[PairedCaseDiff, ...] = Field(min_length=1)
    groups: tuple[PairGroupSummary, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_pair_counts(self) -> Self:
        if len(self.pairs) != self.total_pair_count:
            raise ValueError("pairs length must equal total_pair_count")

        if sum(group.pair_count for group in self.groups) != self.total_pair_count:
            raise ValueError("group pair counts must equal total_pair_count")

        return self


GroupKey = tuple[str, DatasetSplit, TaskFamily]


def _index_rows(
    run: FixtureRun,
    *,
    label: str,
) -> dict[str, EvaluatedCaseRow]:
    indexed: dict[str, EvaluatedCaseRow] = {}

    for row in run.rows:
        if row.case_id in indexed:
            raise PairDiffError(f"Duplicate {label} case row: {row.case_id!r}")

        if (
            row.run_id != run.config.run_id
            or row.config_id != run.config.config_id
            or row.repeat_index != run.config.repeat_index
            or row.seed != run.config.seed
            or row.case_set_id != run.case_set_id
            or row.data_sha256 != run.data_sha256
        ):
            raise PairDiffError(f"{label} run metadata mismatch for case: {row.case_id!r}")

        if row.grade.case_id != row.case_id or row.grade.task_family != row.task_family:
            raise PairDiffError(f"{label} grade metadata mismatch for case: {row.case_id!r}")

        indexed[row.case_id] = row

    return indexed


def _require_compatible_runs(
    baseline: FixtureRun,
    variant: FixtureRun,
    baseline_rows: dict[str, EvaluatedCaseRow],
    variant_rows: dict[str, EvaluatedCaseRow],
) -> None:
    if baseline.config.run_id == variant.config.run_id:
        raise PairDiffError("baseline and variant run_id must differ")

    if baseline.config.config_id == variant.config.config_id:
        raise PairDiffError("baseline and variant config_id must differ")

    shared_fields = (
        ("case_set_id", baseline.case_set_id, variant.case_set_id),
        ("data_sha256", baseline.data_sha256, variant.data_sha256),
        (
            "repeat_index",
            baseline.config.repeat_index,
            variant.config.repeat_index,
        ),
        ("seed", baseline.config.seed, variant.config.seed),
    )

    for field_name, baseline_value, variant_value in shared_fields:
        if baseline_value != variant_value:
            raise PairDiffError(f"Paired runs must share {field_name}")

    baseline_ids = set(baseline_rows)
    variant_ids = set(variant_rows)

    if baseline_ids != variant_ids:
        raise PairDiffError(
            "Case coverage mismatch: "
            f"baseline_only={sorted(baseline_ids - variant_ids)!r}, "
            f"variant_only={sorted(variant_ids - baseline_ids)!r}"
        )


def _require_same_case_metadata(
    baseline: EvaluatedCaseRow,
    variant: EvaluatedCaseRow,
) -> tuple[dict[MetricName, float], dict[MetricName, float]]:
    baseline_metadata = (
        baseline.task_family,
        baseline.suite_name,
        baseline.source_name,
        baseline.source_revision,
        baseline.source_record_id,
        baseline.group_id,
        baseline.split,
        baseline.language,
        baseline.qualification_status,
        baseline.tags,
    )
    variant_metadata = (
        variant.task_family,
        variant.suite_name,
        variant.source_name,
        variant.source_revision,
        variant.source_record_id,
        variant.group_id,
        variant.split,
        variant.language,
        variant.qualification_status,
        variant.tags,
    )

    if baseline_metadata != variant_metadata:
        raise PairDiffError(f"Case metadata mismatch for case: {baseline.case_id!r}")

    if baseline.grade.grader_version != variant.grade.grader_version:
        raise PairDiffError(f"grader_version mismatch for case: {baseline.case_id!r}")

    baseline_metrics = {metric.name: metric.value for metric in baseline.grade.metrics}
    variant_metrics = {metric.name: metric.value for metric in variant.grade.metrics}

    if set(baseline_metrics) != set(variant_metrics):
        raise PairDiffError(f"Metric schema mismatch for case: {baseline.case_id!r}")

    return baseline_metrics, variant_metrics


def _pair_outcome(
    baseline_passed: bool,
    variant_passed: bool,
) -> PairOutcome:
    if baseline_passed and variant_passed:
        return "both_pass"

    if baseline_passed and not variant_passed:
        return "regression"

    if not baseline_passed and variant_passed:
        return "improvement"

    return "both_fail"


def diff_pairs(
    *,
    baseline: FixtureRun,
    variant: FixtureRun,
) -> FixturePairReport:
    baseline_rows = _index_rows(
        baseline,
        label="baseline",
    )
    variant_rows = _index_rows(
        variant,
        label="variant",
    )

    _require_compatible_runs(
        baseline,
        variant,
        baseline_rows,
        variant_rows,
    )

    pairs: list[PairedCaseDiff] = []

    for case_id in sorted(baseline_rows):
        baseline_row = baseline_rows[case_id]
        variant_row = variant_rows[case_id]

        baseline_metrics, variant_metrics = _require_same_case_metadata(
            baseline_row,
            variant_row,
        )

        metric_deltas = tuple(
            PairedMetricDelta(
                name=metric_name,
                baseline_value=baseline_metrics[metric_name],
                variant_value=variant_metrics[metric_name],
                delta=(variant_metrics[metric_name] - baseline_metrics[metric_name]),
            )
            for metric_name in sorted(baseline_metrics)
        )

        pairs.append(
            PairedCaseDiff(
                baseline_run_id=baseline.config.run_id,
                baseline_config_id=baseline.config.config_id,
                variant_run_id=variant.config.run_id,
                variant_config_id=variant.config.config_id,
                repeat_index=baseline.config.repeat_index,
                seed=baseline.config.seed,
                case_set_id=baseline.case_set_id,
                data_sha256=baseline.data_sha256,
                case_id=case_id,
                task_family=baseline_row.task_family,
                suite_name=baseline_row.suite_name,
                source_name=baseline_row.source_name,
                source_revision=baseline_row.source_revision,
                source_record_id=baseline_row.source_record_id,
                group_id=baseline_row.group_id,
                split=baseline_row.split,
                language=baseline_row.language,
                qualification_status=baseline_row.qualification_status,
                tags=baseline_row.tags,
                baseline_prediction=baseline_row.prediction,
                variant_prediction=variant_row.prediction,
                baseline_grade=baseline_row.grade,
                variant_grade=variant_row.grade,
                outcome=_pair_outcome(
                    baseline_row.grade.passed,
                    variant_row.grade.passed,
                ),
                metric_deltas=metric_deltas,
            )
        )

    grouped_pairs: dict[GroupKey, list[PairedCaseDiff]] = {}

    for pair in pairs:
        key: GroupKey = (
            pair.suite_name,
            pair.split,
            pair.task_family,
        )
        grouped_pairs.setdefault(key, []).append(pair)

    groups: list[PairGroupSummary] = []

    for suite_name, split, task_family in sorted(grouped_pairs):
        group_pairs = grouped_pairs[(suite_name, split, task_family)]
        expected_metric_names = {metric.name for metric in group_pairs[0].metric_deltas}

        for pair in group_pairs[1:]:
            observed_metric_names = {metric.name for metric in pair.metric_deltas}

            if observed_metric_names != expected_metric_names:
                raise PairDiffError(
                    f"Metric delta schema mismatch in group {(suite_name, split, task_family)!r}"
                )

        mean_metric_deltas: list[MeanMetricDelta] = []

        for metric_name in sorted(expected_metric_names):
            values = [
                next(metric.delta for metric in pair.metric_deltas if metric.name == metric_name)
                for pair in group_pairs
            ]

            mean_metric_deltas.append(
                MeanMetricDelta(
                    name=metric_name,
                    sample_count=len(values),
                    mean_delta=fsum(values) / len(values),
                )
            )

        pair_count = len(group_pairs)
        both_pass_count = sum(pair.outcome == "both_pass" for pair in group_pairs)
        regression_count = sum(pair.outcome == "regression" for pair in group_pairs)
        improvement_count = sum(pair.outcome == "improvement" for pair in group_pairs)
        both_fail_count = sum(pair.outcome == "both_fail" for pair in group_pairs)

        groups.append(
            PairGroupSummary(
                suite_name=suite_name,
                split=split,
                task_family=task_family,
                pair_count=pair_count,
                independent_group_count=len(
                    {(pair.source_name, pair.group_id) for pair in group_pairs}
                ),
                both_pass_count=both_pass_count,
                regression_count=regression_count,
                improvement_count=improvement_count,
                both_fail_count=both_fail_count,
                regression_rate=regression_count / pair_count,
                improvement_rate=improvement_count / pair_count,
                metric_deltas=tuple(mean_metric_deltas),
            )
        )

    return FixturePairReport(
        baseline_run_id=baseline.config.run_id,
        baseline_config_id=baseline.config.config_id,
        variant_run_id=variant.config.run_id,
        variant_config_id=variant.config.config_id,
        case_set_id=baseline.case_set_id,
        data_sha256=baseline.data_sha256,
        repeat_index=baseline.config.repeat_index,
        seed=baseline.config.seed,
        total_pair_count=len(pairs),
        pairs=tuple(pairs),
        groups=tuple(groups),
    )
