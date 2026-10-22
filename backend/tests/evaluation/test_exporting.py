import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation.dispatcher import CaseGrade, MetricValue
from app.evaluation.exporting import (
    EVAL_RESULT_ROW_SCHEMA_VERSION,
    ExportError,
    export_jsonl,
)
from app.evaluation.runs import (
    EvaluatedCaseRow,
    FixtureRun,
    FixtureRunConfig,
)


def _row(
    case_id: str,
    *,
    passed: bool,
    prediction: str,
) -> EvaluatedCaseRow:
    return EvaluatedCaseRow(
        run_id="fixture-run-001",
        config_id="fixture-config-v1",
        repeat_index=0,
        seed=7,
        case_set_id="fixture-case-set-v1",
        data_sha256="a" * 64,
        case_id=case_id,
        task_family="multidisciplinary_mcq",
        suite_name="fixture-suite",
        source_name="local-fixture",
        source_revision="fixture-v1",
        source_record_id=case_id,
        group_id=f"group-{case_id}",
        split="smoke",
        language="vi",
        qualification_status="synthetic",
        tags=("fixture",),
        prediction=prediction,
        grade=CaseGrade(
            case_id=case_id,
            task_family="multidisciplinary_mcq",
            passed=passed,
            metrics=(
                MetricValue(
                    name="accuracy",
                    value=float(passed),
                ),
            ),
            normalized_prediction=("B" if passed else "A"),
            reason="fixture-grade",
            grader_version="fixture-grader-v1",
        ),
    )


def _run(
    rows: tuple[EvaluatedCaseRow, ...] | None = None,
) -> FixtureRun:
    if rows is None:
        rows = (
            _row(
                "case-002",
                passed=False,
                prediction="A",
            ),
            _row(
                "case-001",
                passed=True,
                prediction="Đáp án: B",
            ),
        )

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


def test_export_jsonl_writes_stable_unicode_case_rows(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "reports" / "results.jsonl"

    receipt = export_jsonl(
        run=_run(),
        output_path=output_path,
    )

    content = output_path.read_text(encoding="utf-8")
    records = tuple(json.loads(line) for line in content.splitlines())

    assert output_path.exists()
    assert content.endswith("\n")
    assert "Đáp án: B" in content
    assert "evaluator_target" not in content
    assert "answer_key" not in content

    assert tuple(record["result"]["case_id"] for record in records) == (
        "case-001",
        "case-002",
    )
    assert all(record["schema_version"] == EVAL_RESULT_ROW_SCHEMA_VERSION for record in records)
    assert all(record["record_type"] == "evaluated_case" for record in records)
    assert all(record["result"]["research_eligible"] is False for record in records)

    output_bytes = output_path.read_bytes()

    assert receipt.row_count == 2
    assert receipt.byte_count == len(output_bytes)
    assert receipt.content_sha256 == hashlib.sha256(output_bytes).hexdigest()
    assert receipt.overwrote_existing is False


def test_export_jsonl_is_byte_reproducible(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    first_receipt = export_jsonl(
        run=_run(),
        output_path=first_path,
    )
    second_receipt = export_jsonl(
        run=_run(),
        output_path=second_path,
    )

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first_receipt.content_sha256 == second_receipt.content_sha256


def test_export_jsonl_refuses_to_overwrite_by_default(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "results.jsonl"
    output_path.write_text(
        "existing artifact\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ExportError,
        match="Output already exists",
    ):
        export_jsonl(
            run=_run(),
            output_path=output_path,
        )

    assert output_path.read_text(encoding="utf-8") == "existing artifact\n"


def test_export_jsonl_overwrites_only_when_explicit(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "results.jsonl"
    output_path.write_text(
        "existing artifact\n",
        encoding="utf-8",
    )

    receipt = export_jsonl(
        run=_run(),
        output_path=output_path,
        overwrite=True,
    )

    assert receipt.overwrote_existing is True
    assert output_path.read_text(encoding="utf-8") != "existing artifact\n"


def test_export_jsonl_rejects_duplicate_case_rows(
    tmp_path: Path,
) -> None:
    row = _row(
        "case-001",
        passed=True,
        prediction="B",
    )
    run = _run(
        rows=(
            row,
            row,
        )
    )

    with pytest.raises(
        ExportError,
        match="Duplicate case row",
    ):
        export_jsonl(
            run=run,
            output_path=tmp_path / "results.jsonl",
        )


def test_export_jsonl_rejects_run_metadata_mismatch(
    tmp_path: Path,
) -> None:
    mismatched_row = _row(
        "case-001",
        passed=True,
        prediction="B",
    ).model_copy(
        update={"run_id": "different-run"},
    )
    run = _run(
        rows=(mismatched_row,),
    )

    with pytest.raises(
        ExportError,
        match="Run metadata mismatch",
    ):
        export_jsonl(
            run=run,
            output_path=tmp_path / "results.jsonl",
        )
