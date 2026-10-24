import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from app.evaluation.cases import (
    EvalModel,
    NonBlankString,
)
from app.evaluation.exporting import (
    ExportError,
    write_atomic_artifact,
)
from app.evaluation.live_harness import (
    LiveArmAggregate,
    LivePairAggregate,
    LiveSuiteResult,
)
from app.evaluation.live_runner import (
    LivePairResult,
)


class LivePairExportRecord(EvalModel):
    schema_version: Literal["eval-live-pair-result-v1"] = "eval-live-pair-result-v1"
    record_type: Literal["live_pair"] = "live_pair"
    result: LivePairResult


class LivePairJsonlReceipt(EvalModel):
    schema_version: Literal["eval-live-jsonl-receipt-v1"] = "eval-live-jsonl-receipt-v1"
    output_path: Path
    run_id: NonBlankString
    suite_name: NonBlankString
    row_count: int = Field(gt=0)
    byte_count: int = Field(gt=0)
    content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    overwrote_existing: bool


class LiveSuiteReport(EvalModel):
    schema_version: Literal["eval-live-suite-report-v1"] = "eval-live-suite-report-v1"
    run_id: NonBlankString
    repeat_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    suite_name: NonBlankString
    source_name: NonBlankString
    source_revision: NonBlankString
    baseline: LiveArmAggregate
    optimized: LiveArmAggregate
    comparison: LivePairAggregate
    run_purpose: Literal["engineering_pilot"] = "engineering_pilot"
    research_eligible: Literal[False] = False


class LiveSuiteExportReceipt(EvalModel):
    schema_version: Literal["eval-live-suite-export-receipt-v1"] = (
        "eval-live-suite-export-receipt-v1"
    )
    output_dir: Path
    pair_results: LivePairJsonlReceipt
    report_path: Path
    report_byte_count: int = Field(gt=0)
    report_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )
    report_overwrote_existing: bool


def _validate_result(
    result: LiveSuiteResult,
) -> None:
    seen_case_ids: set[str] = set()

    expected_source = (
        result.suite_name,
        result.source_name,
        result.source_revision,
    )

    for pair in result.pairs:
        if pair.case_id in seen_case_ids:
            raise ExportError(f"Duplicate live pair case_id: {pair.case_id!r}")

        if (
            pair.run_id != result.run_id
            or pair.repeat_index != result.repeat_index
            or pair.seed != result.seed
        ):
            raise ExportError(f"Live pair run metadata mismatch for case: {pair.case_id!r}")

        observed_source = (
            pair.source.suite_name,
            pair.source.source_name,
            pair.source.source_revision,
        )

        if observed_source != expected_source:
            raise ExportError(f"Live pair source metadata mismatch for case: {pair.case_id!r}")

        seen_case_ids.add(pair.case_id)


def _serialize_pairs(
    result: LiveSuiteResult,
) -> bytes:
    records = tuple(
        LivePairExportRecord(result=pair)
        for pair in sorted(
            result.pairs,
            key=lambda current: current.case_id,
        )
    )

    rows = tuple(
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for record in records
    )

    return ("\n".join(rows) + "\n").encode("utf-8")


def _serialize_report(
    result: LiveSuiteResult,
) -> bytes:
    report = LiveSuiteReport(
        run_id=result.run_id,
        repeat_index=result.repeat_index,
        seed=result.seed,
        suite_name=result.suite_name,
        source_name=result.source_name,
        source_revision=result.source_revision,
        baseline=result.baseline,
        optimized=result.optimized,
        comparison=result.comparison,
    )

    return (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def export_live_suite(
    *,
    result: LiveSuiteResult,
    output_dir: Path,
    overwrite: bool = False,
) -> LiveSuiteExportReceipt:
    _validate_result(result)

    pair_results_path = output_dir / "paired-results.jsonl"
    report_path = output_dir / "live-suite-report.json"
    output_paths = (
        pair_results_path,
        report_path,
    )

    if not overwrite:
        existing_paths = tuple(path for path in output_paths if path.exists())

        if existing_paths:
            raise ExportError(f"Output already exists: {existing_paths[0]}")

    pair_content = _serialize_pairs(result)
    report_content = _serialize_report(result)

    pair_overwrote_existing = write_atomic_artifact(
        output_path=pair_results_path,
        content=pair_content,
        overwrite=overwrite,
    )
    report_overwrote_existing = write_atomic_artifact(
        output_path=report_path,
        content=report_content,
        overwrite=overwrite,
    )

    pair_receipt = LivePairJsonlReceipt(
        output_path=pair_results_path,
        run_id=result.run_id,
        suite_name=result.suite_name,
        row_count=len(result.pairs),
        byte_count=len(pair_content),
        content_sha256=hashlib.sha256(
            pair_content,
        ).hexdigest(),
        overwrote_existing=(pair_overwrote_existing),
    )

    return LiveSuiteExportReceipt(
        output_dir=output_dir,
        pair_results=pair_receipt,
        report_path=report_path,
        report_byte_count=len(report_content),
        report_sha256=hashlib.sha256(
            report_content,
        ).hexdigest(),
        report_overwrote_existing=(report_overwrote_existing),
    )
