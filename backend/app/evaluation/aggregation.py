from math import fsum
from typing import Literal, Self

from pydantic import Field, model_validator

from app.evaluation.cases import (
    DatasetSplit,
    EvalModel,
    NonBlankString,
    TaskFamily,
)
from app.evaluation.dispatcher import MetricName
from app.evaluation.runs import EvaluatedCaseRow, FixtureRun


class AggregationError(ValueError):
    pass


class MetricAggregate(EvalModel):
    name: MetricName
    value_sum: float = Field(ge=0.0)
    sample_count: int = Field(gt=0)
    mean: float = Field(ge=0.0, le=1.0)


class GroupAggregate(EvalModel):
    suite_name: NonBlankString
    split: DatasetSplit
    task_family: TaskFamily
    case_count: int = Field(gt=0)
    independent_group_count: int = Field(gt=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    metrics: tuple[MetricAggregate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.passed_count + self.failed_count != self.case_count:
            raise ValueError("passed_count plus failed_count must equal case_count")

        if self.independent_group_count > self.case_count:
            raise ValueError("independent_group_count must not exceed case_count")

        if any(metric.sample_count != self.case_count for metric in self.metrics):
            raise ValueError("every metric sample_count must equal case_count")

        return self


class FixtureAggregateReport(EvalModel):
    run_id: NonBlankString
    config_id: NonBlankString
    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    repeat_index: int = Field(ge=0)
    seed: int
    run_purpose: Literal["smoke"] = "smoke"
    execution_source: Literal["fixture"] = "fixture"
    namespace: Literal["eval"] = "eval"
    research_eligible: Literal[False] = False
    total_case_count: int = Field(gt=0)
    groups: tuple[GroupAggregate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_total_case_count(self) -> Self:
        grouped_case_count = sum(group.case_count for group in self.groups)

        if grouped_case_count != self.total_case_count:
            raise ValueError("group case counts must equal total_case_count")

        return self


GroupKey = tuple[str, DatasetSplit, TaskFamily]


def _validate_run_rows(run: FixtureRun) -> None:
    seen_case_ids: set[str] = set()

    for row in run.rows:
        if row.case_id in seen_case_ids:
            raise AggregationError(f"Duplicate case row: {row.case_id!r}")

        seen_case_ids.add(row.case_id)

        if (
            row.run_id != run.config.run_id
            or row.config_id != run.config.config_id
            or row.repeat_index != run.config.repeat_index
            or row.seed != run.config.seed
            or row.case_set_id != run.case_set_id
            or row.data_sha256 != run.data_sha256
        ):
            raise AggregationError(f"Run metadata mismatch for case: {row.case_id!r}")


def aggregate_metrics(
    run: FixtureRun,
) -> FixtureAggregateReport:
    _validate_run_rows(run)

    grouped_rows: dict[GroupKey, list[EvaluatedCaseRow]] = {}

    for row in run.rows:
        key: GroupKey = (
            row.suite_name,
            row.split,
            row.task_family,
        )
        grouped_rows.setdefault(key, []).append(row)

    group_aggregates: list[GroupAggregate] = []

    for suite_name, split, task_family in sorted(grouped_rows):
        rows = grouped_rows[(suite_name, split, task_family)]
        expected_metric_names = {metric.name for metric in rows[0].grade.metrics}

        for row in rows[1:]:
            observed_metric_names = {metric.name for metric in row.grade.metrics}

            if observed_metric_names != expected_metric_names:
                raise AggregationError(
                    f"Metric schema mismatch in group {(suite_name, split, task_family)!r}"
                )

        metric_aggregates: list[MetricAggregate] = []

        for metric_name in sorted(expected_metric_names):
            values = [
                next(metric.value for metric in row.grade.metrics if metric.name == metric_name)
                for row in rows
            ]
            value_sum = fsum(values)

            metric_aggregates.append(
                MetricAggregate(
                    name=metric_name,
                    value_sum=value_sum,
                    sample_count=len(values),
                    mean=value_sum / len(values),
                )
            )

        passed_count = sum(row.grade.passed for row in rows)
        case_count = len(rows)

        group_aggregates.append(
            GroupAggregate(
                suite_name=suite_name,
                split=split,
                task_family=task_family,
                case_count=case_count,
                independent_group_count=len({(row.source_name, row.group_id) for row in rows}),
                passed_count=passed_count,
                failed_count=case_count - passed_count,
                pass_rate=passed_count / case_count,
                metrics=tuple(metric_aggregates),
            )
        )

    return FixtureAggregateReport(
        run_id=run.config.run_id,
        config_id=run.config.config_id,
        case_set_id=run.case_set_id,
        data_sha256=run.data_sha256,
        repeat_index=run.config.repeat_index,
        seed=run.config.seed,
        total_case_count=len(run.rows),
        groups=tuple(group_aggregates),
    )
