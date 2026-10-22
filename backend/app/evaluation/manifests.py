from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from app.evaluation.cases import (
    DatasetSplit,
    EvalModel,
    NonBlankString,
    QualificationStatus,
    TaskFamily,
)
from app.evaluation.loader import CaseLoadError, LoadedCaseSet, load_cases


class ManifestLoadError(ValueError):
    pass


def _require_unique_declaration(
    field_name: str,
    values: tuple[str, ...],
) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


class CaseSetManifest(EvalModel):
    schema_version: Literal["eval-case-set-v1"] = "eval-case-set-v1"
    case_set_id: NonBlankString
    cases_file: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(gt=0)
    suite_names: tuple[NonBlankString, ...] = Field(min_length=1)
    task_families: tuple[TaskFamily, ...] = Field(min_length=1)
    splits: tuple[DatasetSplit, ...] = Field(min_length=1)
    qualification_statuses: tuple[QualificationStatus, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_declarations(self) -> Self:
        _require_unique_declaration("suite_names", self.suite_names)
        _require_unique_declaration("task_families", self.task_families)
        _require_unique_declaration("splits", self.splits)
        _require_unique_declaration(
            "qualification_statuses",
            self.qualification_statuses,
        )
        return self


class ResolvedCaseSet(EvalModel):
    manifest: CaseSetManifest
    cases_path: Path
    loaded: LoadedCaseSet


def _require_exact_values(
    *,
    field_name: str,
    declared: set[str],
    observed: set[str],
) -> None:
    if declared != observed:
        raise ManifestLoadError(
            f"{field_name} mismatch: declared={sorted(declared)!r}, observed={sorted(observed)!r}"
        )


def _validate_loaded_cases(
    manifest: CaseSetManifest,
    loaded: LoadedCaseSet,
) -> None:
    if len(loaded.cases) != manifest.case_count:
        raise ManifestLoadError(
            f"case_count mismatch: declared={manifest.case_count}, observed={len(loaded.cases)}"
        )

    _require_exact_values(
        field_name="suite_names",
        declared=set(manifest.suite_names),
        observed={case.source.suite_name for case in loaded.cases},
    )
    _require_exact_values(
        field_name="task_families",
        declared={str(value) for value in manifest.task_families},
        observed={case.task_family for case in loaded.cases},
    )
    _require_exact_values(
        field_name="splits",
        declared={str(value) for value in manifest.splits},
        observed={case.source.split for case in loaded.cases},
    )
    _require_exact_values(
        field_name="qualification_statuses",
        declared={str(value) for value in manifest.qualification_statuses},
        observed={case.source.qualification_status for case in loaded.cases},
    )

    group_splits: dict[tuple[str, str, str], DatasetSplit] = {}

    for case in loaded.cases:
        group_key = (
            case.source.suite_name,
            case.source.source_name,
            case.source.group_id,
        )
        previous_split = group_splits.get(group_key)

        if previous_split is not None and previous_split != case.source.split:
            raise ManifestLoadError(f"group_id crosses dataset splits: {group_key!r}")

        group_splits[group_key] = case.source.split


def load_case_set_manifest(path: Path) -> ResolvedCaseSet:
    try:
        manifest_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestLoadError(f"Could not read eval case-set manifest: {path}") from exc

    try:
        manifest = CaseSetManifest.model_validate_json(manifest_text)
    except ValidationError as exc:
        raise ManifestLoadError(f"Invalid eval case-set manifest: {exc}") from exc

    relative_cases_path = Path(manifest.cases_file)

    if relative_cases_path.is_absolute():
        raise ManifestLoadError("cases_file must be relative to the manifest")

    cases_path = (path.parent / relative_cases_path).resolve()

    try:
        loaded = load_cases(
            cases_path,
            expected_sha256=manifest.data_sha256,
        )
    except CaseLoadError as exc:
        raise ManifestLoadError(f"Could not load manifest case set: {exc}") from exc

    _validate_loaded_cases(manifest, loaded)

    return ResolvedCaseSet(
        manifest=manifest,
        cases_path=cases_path,
        loaded=loaded,
    )
