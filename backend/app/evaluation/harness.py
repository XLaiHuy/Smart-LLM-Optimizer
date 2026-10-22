import hashlib
import json
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from app.evaluation.aggregation import (
    FixtureAggregateReport,
    aggregate_metrics,
)
from app.evaluation.cases import EvalModel, NonBlankString
from app.evaluation.comparison import (
    FixturePairReport,
    diff_pairs,
)
from app.evaluation.exporting import (
    ExportError,
    JsonlExportReceipt,
    export_jsonl,
    write_atomic_artifact,
)
from app.evaluation.manifests import load_case_set_manifest
from app.evaluation.runs import (
    FixturePrediction,
    FixtureRun,
    FixtureRunConfig,
    run_config,
)


class FixturePredictionLoadError(ValueError):
    pass


class LoadedFixturePredictions(EvalModel):
    predictions: tuple[FixturePrediction, ...] = Field(
        min_length=1,
    )
    data_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )


class FixturePairConfig(EvalModel):
    schema_version: Literal["fixture-pair-config-v1"] = "fixture-pair-config-v1"
    baseline_run_id: NonBlankString
    baseline_config_id: NonBlankString
    variant_run_id: NonBlankString
    variant_config_id: NonBlankString
    repeat_index: int = Field(default=0, ge=0)
    seed: int = 0

    @model_validator(mode="after")
    def require_distinct_runs(self) -> Self:
        if self.baseline_run_id == self.variant_run_id:
            raise ValueError("baseline and variant run IDs must differ")

        if self.baseline_config_id == self.variant_config_id:
            raise ValueError("baseline and variant config IDs must differ")

        return self


class FixtureHarnessResult(EvalModel):
    schema_version: Literal["fixture-harness-result-v1"] = "fixture-harness-result-v1"
    case_set_id: NonBlankString
    data_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    baseline_predictions_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    variant_predictions_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    baseline_run: FixtureRun
    variant_run: FixtureRun
    baseline_aggregate: FixtureAggregateReport
    variant_aggregate: FixtureAggregateReport
    comparison: FixturePairReport
    research_eligible: Literal[False] = False


class FixtureHarnessReport(EvalModel):
    schema_version: Literal["fixture-harness-report-v1"] = "fixture-harness-report-v1"
    case_set_id: NonBlankString
    data_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    baseline_predictions_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    variant_predictions_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    baseline_aggregate: FixtureAggregateReport
    variant_aggregate: FixtureAggregateReport
    comparison: FixturePairReport
    research_eligible: Literal[False] = False


class FixtureHarnessExportReceipt(EvalModel):
    schema_version: Literal["fixture-harness-export-receipt-v1"] = (
        "fixture-harness-export-receipt-v1"
    )
    output_dir: Path
    baseline_results: JsonlExportReceipt
    variant_results: JsonlExportReceipt
    report_path: Path
    report_byte_count: int = Field(gt=0)
    report_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    report_overwrote_existing: bool


def load_fixture_predictions(
    path: Path,
) -> LoadedFixturePredictions:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise FixturePredictionLoadError(f"Could not read fixture predictions: {path}") from exc

    data_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixturePredictionLoadError("Fixture predictions must be valid UTF-8") from exc

    predictions: list[FixturePrediction] = []
    case_lines: dict[str, int] = {}

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            prediction = FixturePrediction.model_validate_json(line)
        except ValidationError as exc:
            raise FixturePredictionLoadError(
                f"Invalid fixture prediction at line {line_number}"
            ) from exc

        previous_line = case_lines.get(prediction.case_id)

        if previous_line is not None:
            raise FixturePredictionLoadError(
                f"Duplicate case_id {prediction.case_id!r} "
                f"at line {line_number}; "
                f"first declared at line {previous_line}"
            )

        case_lines[prediction.case_id] = line_number
        predictions.append(prediction)

    if not predictions:
        raise FixturePredictionLoadError("Fixture predictions must contain at least one prediction")

    return LoadedFixturePredictions(
        predictions=tuple(predictions),
        data_sha256=data_sha256,
    )


def run_fixture_pair(
    *,
    case_manifest_path: Path,
    baseline_predictions_path: Path,
    variant_predictions_path: Path,
    config: FixturePairConfig,
) -> FixtureHarnessResult:
    resolved = load_case_set_manifest(case_manifest_path)

    baseline_predictions = load_fixture_predictions(baseline_predictions_path)
    variant_predictions = load_fixture_predictions(variant_predictions_path)

    baseline_run = run_config(
        resolved=resolved,
        config=FixtureRunConfig(
            run_id=config.baseline_run_id,
            config_id=config.baseline_config_id,
            repeat_index=config.repeat_index,
            seed=config.seed,
        ),
        predictions=baseline_predictions.predictions,
    )

    variant_run = run_config(
        resolved=resolved,
        config=FixtureRunConfig(
            run_id=config.variant_run_id,
            config_id=config.variant_config_id,
            repeat_index=config.repeat_index,
            seed=config.seed,
        ),
        predictions=variant_predictions.predictions,
    )

    baseline_aggregate = aggregate_metrics(baseline_run)
    variant_aggregate = aggregate_metrics(variant_run)

    comparison = diff_pairs(
        baseline=baseline_run,
        variant=variant_run,
    )

    return FixtureHarnessResult(
        case_set_id=resolved.manifest.case_set_id,
        data_sha256=resolved.loaded.data_sha256,
        baseline_predictions_sha256=(baseline_predictions.data_sha256),
        variant_predictions_sha256=(variant_predictions.data_sha256),
        baseline_run=baseline_run,
        variant_run=variant_run,
        baseline_aggregate=baseline_aggregate,
        variant_aggregate=variant_aggregate,
        comparison=comparison,
    )


def export_fixture_harness(
    *,
    result: FixtureHarnessResult,
    output_dir: Path,
    overwrite: bool = False,
) -> FixtureHarnessExportReceipt:
    baseline_path = output_dir / "baseline.results.jsonl"
    variant_path = output_dir / "variant.results.jsonl"
    report_path = output_dir / "paired-report.json"

    output_paths = (
        baseline_path,
        variant_path,
        report_path,
    )

    if not overwrite:
        existing_paths = tuple(path for path in output_paths if path.exists())

        if existing_paths:
            raise ExportError(f"Output already exists: {existing_paths[0]}")

    report = FixtureHarnessReport(
        case_set_id=result.case_set_id,
        data_sha256=result.data_sha256,
        baseline_predictions_sha256=(result.baseline_predictions_sha256),
        variant_predictions_sha256=(result.variant_predictions_sha256),
        baseline_aggregate=(result.baseline_aggregate),
        variant_aggregate=(result.variant_aggregate),
        comparison=result.comparison,
    )

    report_content = (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    baseline_receipt = export_jsonl(
        run=result.baseline_run,
        output_path=baseline_path,
        overwrite=overwrite,
    )
    variant_receipt = export_jsonl(
        run=result.variant_run,
        output_path=variant_path,
        overwrite=overwrite,
    )

    report_overwrote_existing = write_atomic_artifact(
        output_path=report_path,
        content=report_content,
        overwrite=overwrite,
    )

    return FixtureHarnessExportReceipt(
        output_dir=output_dir,
        baseline_results=baseline_receipt,
        variant_results=variant_receipt,
        report_path=report_path,
        report_byte_count=len(report_content),
        report_sha256=hashlib.sha256(report_content).hexdigest(),
        report_overwrote_existing=(report_overwrote_existing),
    )
