import json
from pathlib import Path

from app.evaluation.harness import (
    FixturePairConfig,
    export_fixture_harness,
    run_fixture_pair,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "benchmark" / "fixtures" / "four_suite_smoke"


def test_four_suite_smoke_exports_paired_report(
    tmp_path: Path,
) -> None:
    result = run_fixture_pair(
        case_manifest_path=(FIXTURE_DIR / "manifest.json"),
        baseline_predictions_path=(FIXTURE_DIR / "baseline.predictions.jsonl"),
        variant_predictions_path=(FIXTURE_DIR / "optimized.predictions.jsonl"),
        config=FixturePairConfig(
            baseline_run_id=("four-suite-baseline-run"),
            baseline_config_id=("four-suite-baseline"),
            variant_run_id=("four-suite-optimized-run"),
            variant_config_id=("four-suite-optimized"),
            seed=7,
        ),
        language_detector=lambda _: "vi",
    )

    baseline_groups = {
        (
            group.suite_name,
            group.task_family,
        )
        for group in result.baseline_aggregate.groups
    }
    optimized_groups = {
        (
            group.suite_name,
            group.task_family,
        )
        for group in result.variant_aggregate.groups
    }

    expected_groups = {
        (
            "sea-ifeval-synthetic",
            "instruction",
        ),
        (
            "uit-viquad-synthetic",
            "extractive_qa",
        ),
        (
            "vi-dialog-memory-synthetic",
            "conversation_memory",
        ),
        (
            "vmlu-synthetic",
            "multidisciplinary_mcq",
        ),
    }

    assert baseline_groups == expected_groups
    assert optimized_groups == expected_groups

    baseline_passed = sum(group.passed_count for group in result.baseline_aggregate.groups)
    optimized_passed = sum(group.passed_count for group in result.variant_aggregate.groups)

    assert baseline_passed == 1
    assert optimized_passed == 4

    outcomes = {pair.case_id: pair.outcome for pair in result.comparison.pairs}

    assert outcomes == {
        "sea-ifeval-smoke-001": "improvement",
        "uit-viquad-smoke-001": "improvement",
        "vi-dialog-smoke-001": "improvement",
        "vmlu-smoke-001": "both_pass",
    }

    assert result.research_eligible is False

    receipt = export_fixture_harness(
        result=result,
        output_dir=tmp_path / "report",
    )

    assert receipt.baseline_results.row_count == 4
    assert receipt.variant_results.row_count == 4
    assert receipt.report_sha256 == (
        "8688c3e32272b676408428ab4d6c5ea329146665de04256efe9ec258fee2ff9d"
    )

    report_text = receipt.report_path.read_text(
        encoding="utf-8",
    )
    report = json.loads(report_text)

    assert report["research_eligible"] is False
    assert report["comparison"]["total_pair_count"] == 4

    assert '"evaluator_target"' not in report_text
    assert '"answer_key"' not in report_text
    assert '"gold_answers"' not in report_text
    assert '"evidence_turn_ids"' not in report_text
