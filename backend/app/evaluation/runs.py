from typing import Literal

from pydantic import Field

from app.evaluation.cases import (
    DatasetSplit,
    EvalModel,
    NonBlankString,
    QualificationStatus,
    TaskFamily,
)
from app.evaluation.dispatcher import CaseGrade, grade_case
from app.evaluation.manifests import ResolvedCaseSet


class RunConfigError(ValueError):
    pass


class FixtureRunConfig(EvalModel):
    run_id: NonBlankString
    config_id: NonBlankString
    repeat_index: int = Field(default=0, ge=0)
    seed: int = 0
    run_purpose: Literal["smoke"] = "smoke"
    execution_source: Literal["fixture"] = "fixture"
    namespace: Literal["eval"] = "eval"


class FixturePrediction(EvalModel):
    case_id: NonBlankString
    prediction: str


class EvaluatedCaseRow(EvalModel):
    run_id: NonBlankString
    config_id: NonBlankString
    repeat_index: int = Field(ge=0)
    seed: int
    run_purpose: Literal["smoke"] = "smoke"
    execution_source: Literal["fixture"] = "fixture"
    namespace: Literal["eval"] = "eval"
    research_eligible: Literal[False] = False

    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: NonBlankString
    task_family: TaskFamily
    suite_name: NonBlankString
    source_name: NonBlankString
    source_revision: NonBlankString
    source_record_id: NonBlankString
    group_id: NonBlankString
    split: DatasetSplit
    language: NonBlankString
    qualification_status: QualificationStatus
    tags: tuple[NonBlankString, ...]

    prediction: str
    grade: CaseGrade


class FixtureRun(EvalModel):
    config: FixtureRunConfig
    case_set_id: NonBlankString
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: tuple[EvaluatedCaseRow, ...] = Field(min_length=1)
    research_eligible: Literal[False] = False


def _index_predictions(
    predictions: tuple[FixturePrediction, ...],
) -> dict[str, FixturePrediction]:
    indexed: dict[str, FixturePrediction] = {}

    for prediction in predictions:
        if prediction.case_id in indexed:
            raise RunConfigError(f"Duplicate prediction for case_id: {prediction.case_id!r}")

        indexed[prediction.case_id] = prediction

    return indexed


def _require_exact_prediction_coverage(
    resolved: ResolvedCaseSet,
    indexed_predictions: dict[str, FixturePrediction],
) -> None:
    expected_ids = {case.case_id for case in resolved.loaded.cases}
    observed_ids = set(indexed_predictions)

    missing_ids = sorted(expected_ids - observed_ids)
    unexpected_ids = sorted(observed_ids - expected_ids)

    if missing_ids or unexpected_ids:
        raise RunConfigError(
            f"Prediction coverage mismatch: missing={missing_ids!r}, unexpected={unexpected_ids!r}"
        )


def _require_synthetic_smoke_cases(
    resolved: ResolvedCaseSet,
) -> None:
    invalid_case_ids = [
        case.case_id
        for case in resolved.loaded.cases
        if case.source.split != "smoke" or case.source.qualification_status != "synthetic"
    ]

    if invalid_case_ids:
        raise RunConfigError(
            "Fixture runner requires synthetic smoke cases; "
            f"invalid_case_ids={sorted(invalid_case_ids)!r}"
        )


def run_config(
    *,
    resolved: ResolvedCaseSet,
    config: FixtureRunConfig,
    predictions: tuple[FixturePrediction, ...],
) -> FixtureRun:
    _require_synthetic_smoke_cases(resolved)

    indexed_predictions = _index_predictions(predictions)
    _require_exact_prediction_coverage(
        resolved,
        indexed_predictions,
    )

    rows: list[EvaluatedCaseRow] = []

    for case in resolved.loaded.cases:
        prediction = indexed_predictions[case.case_id]

        try:
            grade = grade_case(
                case=case,
                prediction=prediction.prediction,
            )
        except ValueError as exc:
            raise RunConfigError(f"Could not grade case {case.case_id!r}: {exc}") from exc

        rows.append(
            EvaluatedCaseRow(
                run_id=config.run_id,
                config_id=config.config_id,
                repeat_index=config.repeat_index,
                seed=config.seed,
                case_set_id=resolved.manifest.case_set_id,
                data_sha256=resolved.loaded.data_sha256,
                case_id=case.case_id,
                task_family=case.task_family,
                suite_name=case.source.suite_name,
                source_name=case.source.source_name,
                source_revision=case.source.source_revision,
                source_record_id=case.source.source_record_id,
                group_id=case.source.group_id,
                split=case.source.split,
                language=case.source.language,
                qualification_status=case.source.qualification_status,
                tags=case.tags,
                prediction=prediction.prediction,
                grade=grade,
            )
        )

    return FixtureRun(
        config=config,
        case_set_id=resolved.manifest.case_set_id,
        data_sha256=resolved.loaded.data_sha256,
        rows=tuple(rows),
    )
