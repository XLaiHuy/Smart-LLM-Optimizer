import pytest

from app.evaluation.comparison import (
    PairDiffError,
    diff_pairs,
)
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


def _run(
    *,
    run_id: str = "baseline-run",
    config_id: str = "baseline-config",
    cases: tuple[tuple[str, bool, float], ...] = (
        ("case-001", True, 1.0),
        ("case-002", False, 0.0),
    ),
    case_set_id: str = "fixture-case-set-v1",
    data_sha256: str = "a" * 64,
    repeat_index: int = 0,
    seed: int = 7,
    source_revision: str = "fixture-v1",
    metric_name: MetricName = "accuracy",
    grader_version: str = "fixture-grader-v1",
) -> FixtureRun:
    rows = tuple(
        EvaluatedCaseRow(
            run_id=run_id,
            config_id=config_id,
            repeat_index=repeat_index,
            seed=seed,
            case_set_id=case_set_id,
            data_sha256=data_sha256,
            case_id=case_id,
            task_family="multidisciplinary_mcq",
            suite_name="fixture-suite",
            source_name="local-fixture",
            source_revision=source_revision,
            source_record_id=case_id,
            group_id=f"group-{case_id}",
            split="smoke",
            language="vi",
            qualification_status="synthetic",
            tags=("fixture",),
            prediction=f"{config_id}:{case_id}",
            grade=CaseGrade(
                case_id=case_id,
                task_family="multidisciplinary_mcq",
                passed=passed,
                metrics=(
                    MetricValue(
                        name=metric_name,
                        value=metric_value,
                    ),
                ),
                normalized_prediction=None,
                reason="fixture-grade",
                grader_version=grader_version,
            ),
        )
        for case_id, passed, metric_value in cases
    )

    return FixtureRun(
        config=FixtureRunConfig(
            run_id=run_id,
            config_id=config_id,
            repeat_index=repeat_index,
            seed=seed,
        ),
        case_set_id=case_set_id,
        data_sha256=data_sha256,
        rows=rows,
    )


def test_diff_pairs_reports_all_outcomes_and_metric_deltas() -> None:
    baseline = _run(
        cases=(
            ("case-001", True, 1.0),
            ("case-002", False, 0.0),
            ("case-003", True, 1.0),
            ("case-004", False, 0.0),
        ),
    )
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        cases=(
            ("case-004", False, 0.0),
            ("case-003", True, 1.0),
            ("case-002", True, 1.0),
            ("case-001", False, 0.0),
        ),
    )

    report = diff_pairs(
        baseline=baseline,
        variant=variant,
    )

    assert tuple(pair.case_id for pair in report.pairs) == (
        "case-001",
        "case-002",
        "case-003",
        "case-004",
    )
    assert {pair.case_id: pair.outcome for pair in report.pairs} == {
        "case-001": "regression",
        "case-002": "improvement",
        "case-003": "both_pass",
        "case-004": "both_fail",
    }
    assert {pair.case_id: pair.metric_deltas[0].delta for pair in report.pairs} == {
        "case-001": -1.0,
        "case-002": 1.0,
        "case-003": 0.0,
        "case-004": 0.0,
    }

    group = report.groups[0]
    assert group.pair_count == 4
    assert group.independent_group_count == 4
    assert group.regression_count == 1
    assert group.improvement_count == 1
    assert group.both_pass_count == 1
    assert group.both_fail_count == 1
    assert group.regression_rate == 0.25
    assert group.improvement_rate == 0.25
    assert group.metric_deltas[0].mean_delta == 0.0

    serialized = report.model_dump_json()
    assert report.research_eligible is False
    assert "evaluator_target" not in serialized
    assert "overall_pass_rate" not in serialized


def test_diff_pairs_rejects_case_coverage_mismatch() -> None:
    baseline = _run()
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        cases=(("case-001", True, 1.0),),
    )

    with pytest.raises(
        PairDiffError,
        match="Case coverage mismatch",
    ):
        diff_pairs(
            baseline=baseline,
            variant=variant,
        )


@pytest.mark.parametrize(
    ("variant_overrides", "error_message"),
    [
        (
            {"case_set_id": "different-case-set"},
            "case_set_id",
        ),
        (
            {"data_sha256": "b" * 64},
            "data_sha256",
        ),
        (
            {"repeat_index": 1},
            "repeat_index",
        ),
        (
            {"seed": 8},
            "seed",
        ),
    ],
)
def test_diff_pairs_rejects_incompatible_run_metadata(
    variant_overrides: dict[str, object],
    error_message: str,
) -> None:
    baseline = _run()
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        **variant_overrides,
    )

    with pytest.raises(
        PairDiffError,
        match=error_message,
    ):
        diff_pairs(
            baseline=baseline,
            variant=variant,
        )


def test_diff_pairs_rejects_case_metadata_mismatch() -> None:
    baseline = _run()
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        source_revision="different-revision",
    )

    with pytest.raises(
        PairDiffError,
        match="Case metadata mismatch",
    ):
        diff_pairs(
            baseline=baseline,
            variant=variant,
        )


@pytest.mark.parametrize(
    ("variant_overrides", "error_message"),
    [
        (
            {"grader_version": "different-grader"},
            "grader_version mismatch",
        ),
        (
            {"metric_name": "exact_match"},
            "Metric schema mismatch",
        ),
    ],
)
def test_diff_pairs_rejects_incompatible_grading_protocol(
    variant_overrides: dict[str, object],
    error_message: str,
) -> None:
    baseline = _run()
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        **variant_overrides,
    )

    with pytest.raises(
        PairDiffError,
        match=error_message,
    ):
        diff_pairs(
            baseline=baseline,
            variant=variant,
        )


def test_diff_pairs_rejects_same_config() -> None:
    baseline = _run()
    variant = _run(
        run_id="variant-run",
        config_id="baseline-config",
    )

    with pytest.raises(
        PairDiffError,
        match="config_id must differ",
    ):
        diff_pairs(
            baseline=baseline,
            variant=variant,
        )


def test_diff_pairs_rejects_duplicate_case_rows() -> None:
    baseline = _run(
        cases=(("case-001", True, 1.0),),
    )
    duplicate_baseline = FixtureRun(
        config=baseline.config,
        case_set_id=baseline.case_set_id,
        data_sha256=baseline.data_sha256,
        rows=(
            baseline.rows[0],
            baseline.rows[0],
        ),
    )
    variant = _run(
        run_id="variant-run",
        config_id="variant-config",
        cases=(("case-001", True, 1.0),),
    )

    with pytest.raises(
        PairDiffError,
        match="Duplicate baseline case row",
    ):
        diff_pairs(
            baseline=duplicate_baseline,
            variant=variant,
        )
