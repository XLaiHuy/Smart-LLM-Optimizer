import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final, Literal

from pydantic import Field

from app.evaluation.cases import EvalModel, NonBlankString
from app.evaluation.runs import EvaluatedCaseRow, FixtureRun

EVAL_RESULT_ROW_SCHEMA_VERSION: Final = "eval-result-row-v1"


class ExportError(ValueError):
    pass


class EvaluatedCaseExportRecord(EvalModel):
    schema_version: Literal["eval-result-row-v1"] = "eval-result-row-v1"
    record_type: Literal["evaluated_case"] = "evaluated_case"
    result: EvaluatedCaseRow


class JsonlExportReceipt(EvalModel):
    schema_version: Literal["eval-export-receipt-v1"] = "eval-export-receipt-v1"
    output_path: Path
    run_id: NonBlankString
    config_id: NonBlankString
    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(gt=0)
    byte_count: int = Field(gt=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    overwrote_existing: bool


def _validate_run_rows(run: FixtureRun) -> None:
    seen_case_ids: set[str] = set()

    for row in run.rows:
        if row.case_id in seen_case_ids:
            raise ExportError(f"Duplicate case row: {row.case_id!r}")

        seen_case_ids.add(row.case_id)

        if (
            row.run_id != run.config.run_id
            or row.config_id != run.config.config_id
            or row.repeat_index != run.config.repeat_index
            or row.seed != run.config.seed
            or row.case_set_id != run.case_set_id
            or row.data_sha256 != run.data_sha256
        ):
            raise ExportError(f"Run metadata mismatch for case: {row.case_id!r}")

        if row.grade.case_id != row.case_id or row.grade.task_family != row.task_family:
            raise ExportError(f"Grade metadata mismatch for case: {row.case_id!r}")


def _serialize_run(run: FixtureRun) -> bytes:
    records = tuple(
        EvaluatedCaseExportRecord(result=row)
        for row in sorted(
            run.rows,
            key=lambda current_row: current_row.case_id,
        )
    )

    serialized_rows = tuple(
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for record in records
    )

    return ("\n".join(serialized_rows) + "\n").encode("utf-8")


def write_atomic_artifact(
    *,
    output_path: Path,
    content: bytes,
    overwrite: bool,
) -> bool:
    overwrote_existing = output_path.exists()

    if overwrote_existing and not overwrite:
        raise ExportError(f"Output already exists: {output_path}")

    temporary_path: Path | None = None

    try:
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)

        if output_path.exists() and not overwrite:
            raise ExportError(f"Output already exists: {output_path}")

        if temporary_path is None:
            raise ExportError("Could not create temporary export file")

        temporary_path.replace(output_path)
    except ExportError:
        raise
    except OSError as exc:
        raise ExportError(f"Could not export evaluation artifact: {output_path}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return overwrote_existing


def export_jsonl(
    *,
    run: FixtureRun,
    output_path: Path,
    overwrite: bool = False,
) -> JsonlExportReceipt:
    _validate_run_rows(run)

    content = _serialize_run(run)
    overwrote_existing = write_atomic_artifact(
        output_path=output_path,
        content=content,
        overwrite=overwrite,
    )

    return JsonlExportReceipt(
        output_path=output_path,
        run_id=run.config.run_id,
        config_id=run.config.config_id,
        case_set_id=run.case_set_id,
        data_sha256=run.data_sha256,
        row_count=len(run.rows),
        byte_count=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
        overwrote_existing=overwrote_existing,
    )
