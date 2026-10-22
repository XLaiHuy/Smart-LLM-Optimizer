import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation.cases import (
    EvalCase,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    SourceMetadata,
)
from app.evaluation.exporting import ExportError
from app.evaluation.harness import (
    FixturePairConfig,
    FixturePredictionLoadError,
    export_fixture_harness,
    load_fixture_predictions,
    run_fixture_pair,
)
from app.evaluation.manifests import CaseSetManifest
from app.evaluation.runs import FixturePrediction


def _mcq_case(
    case_id: str,
    *,
    answer_key: str,
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="multidisciplinary_mcq",
        source=SourceMetadata(
            suite_name="g1-harness-fixture",
            source_name="local-synthetic",
            source_revision="fixture-v1",
            source_record_id=case_id,
            group_id=f"group-{case_id}",
            split="smoke",
            language="vi",
            qualification_status="synthetic",
        ),
        serving_input=MCQServingInput(
            question=f"Câu hỏi {case_id}",
            options=(
                MCQOption(
                    key="A",
                    text="Lựa chọn A",
                ),
                MCQOption(
                    key="B",
                    text="Lựa chọn B",
                ),
            ),
        ),
        evaluator_target=MCQTarget(
            answer_key=answer_key,
        ),
        tags=("fixture",),
    )


def _write_case_manifest(
    directory: Path,
) -> Path:
    cases = (
        _mcq_case(
            "case-001",
            answer_key="B",
        ),
        _mcq_case(
            "case-002",
            answer_key="A",
        ),
    )

    cases_path = directory / "cases.jsonl"
    cases_content = "".join(f"{case.model_dump_json()}\n" for case in cases).encode("utf-8")
    cases_path.write_bytes(cases_content)

    manifest = CaseSetManifest(
        case_set_id="g1-harness-fixture-v1",
        cases_file=cases_path.name,
        data_sha256=hashlib.sha256(cases_content).hexdigest(),
        case_count=len(cases),
        suite_names=("g1-harness-fixture",),
        task_families=("multidisciplinary_mcq",),
        splits=("smoke",),
        qualification_statuses=("synthetic",),
    )

    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    return manifest_path


def _write_predictions(
    path: Path,
    predictions: tuple[
        FixturePrediction,
        ...,
    ],
) -> None:
    path.write_text(
        "".join(f"{prediction.model_dump_json()}\n" for prediction in predictions),
        encoding="utf-8",
    )


def test_fixture_harness_runs_paired_pipeline(
    tmp_path: Path,
) -> None:
    manifest_path = _write_case_manifest(tmp_path)
    baseline_path = tmp_path / "baseline.jsonl"
    variant_path = tmp_path / "variant.jsonl"

    _write_predictions(
        baseline_path,
        (
            FixturePrediction(
                case_id="case-001",
                prediction="B",
            ),
            FixturePrediction(
                case_id="case-002",
                prediction="B",
            ),
        ),
    )

    _write_predictions(
        variant_path,
        (
            FixturePrediction(
                case_id="case-001",
                prediction="A",
            ),
            FixturePrediction(
                case_id="case-002",
                prediction="A",
            ),
        ),
    )

    result = run_fixture_pair(
        case_manifest_path=manifest_path,
        baseline_predictions_path=baseline_path,
        variant_predictions_path=variant_path,
        config=FixturePairConfig(
            baseline_run_id="baseline-run",
            baseline_config_id="baseline-config",
            variant_run_id="variant-run",
            variant_config_id="variant-config",
            seed=7,
        ),
    )

    assert result.baseline_aggregate.groups[0].pass_rate == 0.5
    assert result.variant_aggregate.groups[0].pass_rate == 0.5

    outcomes = {pair.case_id: pair.outcome for pair in result.comparison.pairs}

    assert outcomes == {
        "case-001": "regression",
        "case-002": "improvement",
    }
    assert result.research_eligible is False

    serialized = result.model_dump_json()

    assert "evaluator_target" not in serialized
    assert "answer_key" not in serialized

    output_dir = tmp_path / "reports"

    receipt = export_fixture_harness(
        result=result,
        output_dir=output_dir,
    )

    assert receipt.baseline_results.row_count == 2
    assert receipt.variant_results.row_count == 2
    assert receipt.report_path.exists()

    report_payload = json.loads(
        receipt.report_path.read_text(
            encoding="utf-8",
        )
    )

    assert report_payload["research_eligible"] is False
    assert report_payload["comparison"]["total_pair_count"] == 2

    report_text = receipt.report_path.read_text(
        encoding="utf-8",
    )

    assert "evaluator_target" not in report_text
    assert "answer_key" not in report_text

    with pytest.raises(
        ExportError,
        match="Output already exists",
    ):
        export_fixture_harness(
            result=result,
            output_dir=output_dir,
        )

    overwrite_receipt = export_fixture_harness(
        result=result,
        output_dir=output_dir,
        overwrite=True,
    )

    assert overwrite_receipt.baseline_results.overwrote_existing is True
    assert overwrite_receipt.variant_results.overwrote_existing is True
    assert overwrite_receipt.report_overwrote_existing is True


def test_prediction_loader_rejects_duplicates(
    tmp_path: Path,
) -> None:
    path = tmp_path / "predictions.jsonl"
    prediction = FixturePrediction(
        case_id="case-001",
        prediction="B",
    )

    path.write_text(
        (f"{prediction.model_dump_json()}\n{prediction.model_dump_json()}\n"),
        encoding="utf-8",
    )

    with pytest.raises(
        FixturePredictionLoadError,
        match="Duplicate case_id",
    ):
        load_fixture_predictions(path)


def test_fixture_pair_cli_exports_bundle(
    tmp_path: Path,
) -> None:
    from typer.testing import CliRunner

    from app.cli import cli

    manifest_path = _write_case_manifest(tmp_path)
    baseline_path = tmp_path / "baseline.jsonl"
    variant_path = tmp_path / "variant.jsonl"
    output_dir = tmp_path / "cli-report"

    _write_predictions(
        baseline_path,
        (
            FixturePrediction(
                case_id="case-001",
                prediction="B",
            ),
            FixturePrediction(
                case_id="case-002",
                prediction="B",
            ),
        ),
    )
    _write_predictions(
        variant_path,
        (
            FixturePrediction(
                case_id="case-001",
                prediction="A",
            ),
            FixturePrediction(
                case_id="case-002",
                prediction="A",
            ),
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "fixture-pair",
            "--case-manifest",
            str(manifest_path),
            "--baseline-predictions",
            str(baseline_path),
            "--variant-predictions",
            str(variant_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "FIXTURE ONLY: 2 paired cases" in (result.output)
    assert (output_dir / "baseline.results.jsonl").exists()
    assert (output_dir / "variant.results.jsonl").exists()
    assert (output_dir / "paired-report.json").exists()
