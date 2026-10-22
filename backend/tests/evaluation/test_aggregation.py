import pytest

from app.evaluation.aggregation import (
    AggregationError,
    aggregate_metrics,
)
from app.evaluation.cases import TaskFamily
from app.evaluation.dispatcher import (
    CaseGrade,
    MetricName,
    MetricValue,
)
from app.evaluation.runs import (
    EvaluatedCaseRow,
    FixtureRun,
    FixtureRunConfig,
)


def _grade(
    case_id: str,
    task_family: TaskFamily,
    *,
    passed: bool,
    metrics: tuple[tuple[MetricName, float], ...],
) -> CaseGrade:
    return CaseGrade(
        case_id=case_id,
        task_family=task_family,
        passed=passed,
        metrics=tuple(MetricValue(name=name, value=value) for name, value in metrics),
        normalized_prediction=None,
        reason="fixture-grade",
        grader_version="fixture-grader-v1",
    )


def _row(
    case_id: str,
    task_family: TaskFamily,
    *,
    suite_name: str,
    group_id: str,
    passed: bool,
    metrics: tuple[tuple[MetricName, float], ...],
    run_id: str = "fixture-run-001",
) -> EvaluatedCaseRow:
    return EvaluatedCaseRow(
        run_id=run_id,
        config_id="fixture-config-v1",
        repeat_index=0,
        seed=7,
        case_set_id="fixture-case-set-v1",
        data_sha256="a" * 64,
        case_id=case_id,
        task_family=task_family,
        suite_name=suite_name,
        source_name="local-fixture",
        source_revision="fixture-v1",
        source_record_id=case_id,
        group_id=group_id,
        split="smoke",
        language="vi",
        qualification_status="synthetic",
        tags=("fixture",),
        prediction="fixture prediction",
        grade=_grade(
            case_id,
            task_family,
            passed=passed,
            metrics=metrics,
        ),
    )


def _run(
    rows: tuple[EvaluatedCaseRow, ...],
) -> FixtureRun:
    return FixtureRun(
        config=FixtureRunConfig(
            run_id="fixture-run-001",
            config_id="fixture-config-v1",
            repeat_index=0,
            seed=7,
        ),
        case_set_id="fixture-case-set-v1",
        data_sha256="a" * 64,
        rows=rows,
    )


def test_aggregate_metrics_keeps_task_metrics_separate() -> None:
    run = _run(
        (
            _row(
                "mcq-001",
                "multidisciplinary_mcq",
                suite_name="suite-mcq",
                group_id="mcq-source-group",
                passed=True,
                metrics=(("accuracy", 1.0),),
            ),
            _row(
                "mcq-002",
                "multidisciplinary_mcq",
                suite_name="suite-mcq",
                group_id="mcq-source-group",
                passed=False,
                metrics=(("accuracy", 0.0),),
            ),
            _row(
                "qa-001",
                "extractive_qa",
                suite_name="suite-qa",
                group_id="qa-group-001",
                passed=True,
                metrics=(
                    ("exact_match", 1.0),
                    ("token_f1", 1.0),
                ),
            ),
            _row(
                "qa-002",
                "extractive_qa",
                suite_name="suite-qa",
                group_id="qa-group-002",
                passed=False,
                metrics=(
                    ("exact_match", 0.0),
                    ("token_f1", 0.5),
                ),
            ),
        )
    )

    report = aggregate_metrics(run)
    groups = {group.task_family: group for group in report.groups}

    mcq = groups["multidisciplinary_mcq"]
    assert mcq.case_count == 2
    assert mcq.independent_group_count == 1
    assert mcq.passed_count == 1
    assert mcq.failed_count == 1
    assert mcq.pass_rate == 0.5
    assert {metric.name: metric.mean for metric in mcq.metrics} == {"accuracy": 0.5}

    qa = groups["extractive_qa"]
    assert qa.case_count == 2
    assert qa.independent_group_count == 2
    assert qa.pass_rate == 0.5
    assert {metric.name: metric.mean for metric in qa.metrics} == {
        "exact_match": 0.5,
        "token_f1": 0.75,
    }

    assert report.total_case_count == 4
    assert "overall_pass_rate" not in report.model_dump()


def test_aggregate_metrics_is_independent_of_row_order() -> None:
    rows = (
        _row(
            "mcq-001",
            "multidisciplinary_mcq",
            suite_name="suite-mcq",
            group_id="group-001",
            passed=True,
            metrics=(("accuracy", 1.0),),
        ),
        _row(
            "mcq-002",
            "multidisciplinary_mcq",
            suite_name="suite-mcq",
            group_id="group-002",
            passed=False,
            metrics=(("accuracy", 0.0),),
        ),
    )

    forward = aggregate_metrics(_run(rows))
    reversed_report = aggregate_metrics(_run(tuple(reversed(rows))))

    assert forward == reversed_report


def test_aggregate_metrics_rejects_inconsistent_metric_schema() -> None:
    run = _run(
        (
            _row(
                "mcq-001",
                "multidisciplinary_mcq",
                suite_name="suite-mcq",
                group_id="group-001",
                passed=True,
                metrics=(("accuracy", 1.0),),
            ),
            _row(
                "mcq-002",
                "multidisciplinary_mcq",
                suite_name="suite-mcq",
                group_id="group-002",
                passed=False,
                metrics=(("exact_match", 0.0),),
            ),
        )
    )

    with pytest.raises(
        AggregationError,
        match="Metric schema mismatch",
    ):
        aggregate_metrics(run)


def test_aggregate_metrics_rejects_duplicate_case_rows() -> None:
    row = _row(
        "mcq-001",
        "multidisciplinary_mcq",
        suite_name="suite-mcq",
        group_id="group-001",
        passed=True,
        metrics=(("accuracy", 1.0),),
    )

    with pytest.raises(
        AggregationError,
        match="Duplicate case row",
    ):
        aggregate_metrics(_run((row, row)))


def test_aggregate_metrics_rejects_row_metadata_mismatch() -> None:
    mismatched_row = _row(
        "mcq-001",
        "multidisciplinary_mcq",
        suite_name="suite-mcq",
        group_id="group-001",
        passed=True,
        metrics=(("accuracy", 1.0),),
        run_id="different-run",
    )

    with pytest.raises(
        AggregationError,
        match="Run metadata mismatch",
    ):
        aggregate_metrics(_run((mismatched_row,)))
