from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.cases import (
    DatasetSplit,
    EvalCase,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    QualificationStatus,
    SourceMetadata,
)
from app.evaluation.loader import LoadedCaseSet
from app.evaluation.manifests import (
    CaseSetManifest,
    ResolvedCaseSet,
)
from app.evaluation.runs import (
    FixturePrediction,
    FixtureRunConfig,
    RunConfigError,
    run_config,
)


def _source(
    case_id: str,
    *,
    split: DatasetSplit = "smoke",
    qualification_status: QualificationStatus = "synthetic",
) -> SourceMetadata:
    return SourceMetadata(
        suite_name="g1-fixture-suite",
        source_name="local-fixture",
        source_revision="fixture-v1",
        source_record_id=case_id,
        group_id=f"group-{case_id}",
        split=split,
        language="vi",
        qualification_status=qualification_status,
        license_id=("fixture-license" if qualification_status == "qualified" else None),
    )


def _mcq_case(
    case_id: str,
    *,
    answer_key: str = "B",
    split: DatasetSplit = "smoke",
    qualification_status: QualificationStatus = "synthetic",
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="multidisciplinary_mcq",
        source=_source(
            case_id,
            split=split,
            qualification_status=qualification_status,
        ),
        serving_input=MCQServingInput(
            question="Thủ đô Việt Nam là gì?",
            options=(
                MCQOption(key="A", text="Huế"),
                MCQOption(key="B", text="Hà Nội"),
            ),
        ),
        evaluator_target=MCQTarget(
            answer_key=answer_key,
        ),
        tags=("fixture",),
    )


def _unanswerable_qa_case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="extractive_qa",
        source=_source(case_id),
        serving_input=ExtractiveQAServingInput(
            context="Đoạn văn không nêu tên thành phố.",
            question="Thành phố nào được nhắc đến?",
        ),
        evaluator_target=ExtractiveQATarget(
            answers=(),
            plausible_answers=(),
            is_impossible=True,
        ),
        tags=("fixture", "unanswerable"),
    )


def _instruction_case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="instruction",
        source=_source(case_id),
        serving_input=InstructionServingInput(
            prompt="Trả lời bằng đúng ba câu.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id="number_of_sentences",
                ),
            ),
            evaluator_version="fixture-instruction-v1",
        ),
    )


def _resolved(
    cases: tuple[EvalCase, ...],
) -> ResolvedCaseSet:
    data_sha256 = "a" * 64

    manifest = CaseSetManifest(
        case_set_id="g1-synthetic-fixtures-v1",
        cases_file="cases.jsonl",
        data_sha256=data_sha256,
        case_count=len(cases),
        suite_names=tuple(sorted({case.source.suite_name for case in cases})),
        task_families=tuple(sorted({case.task_family for case in cases})),
        splits=tuple(sorted({case.source.split for case in cases})),
        qualification_statuses=tuple(sorted({case.source.qualification_status for case in cases})),
    )

    return ResolvedCaseSet(
        manifest=manifest,
        cases_path=Path("cases.jsonl"),
        loaded=LoadedCaseSet(
            cases=cases,
            data_sha256=data_sha256,
        ),
    )


def _config() -> FixtureRunConfig:
    return FixtureRunConfig(
        run_id="fixture-run-001",
        config_id="frozen-predictions-v1",
        repeat_index=0,
        seed=7,
    )


def test_run_config_grades_in_case_set_order_and_is_reproducible() -> None:
    resolved = _resolved(
        (
            _mcq_case("mcq-001", answer_key="B"),
            _mcq_case("mcq-002", answer_key="A"),
        )
    )
    predictions = (
        FixturePrediction(
            case_id="mcq-002",
            prediction="B",
        ),
        FixturePrediction(
            case_id="mcq-001",
            prediction="B",
        ),
    )

    first = run_config(
        resolved=resolved,
        config=_config(),
        predictions=predictions,
    )
    second = run_config(
        resolved=resolved,
        config=_config(),
        predictions=predictions,
    )

    assert tuple(row.case_id for row in first.rows) == (
        "mcq-001",
        "mcq-002",
    )
    assert tuple(row.grade.passed for row in first.rows) == (
        True,
        False,
    )
    assert first.model_dump_json() == second.model_dump_json()
    assert first.research_eligible is False

    serialized = first.model_dump_json()
    assert "evaluator_target" not in serialized
    assert "answer_key" not in serialized


def test_run_config_rejects_duplicate_predictions() -> None:
    resolved = _resolved((_mcq_case("mcq-001"),))

    with pytest.raises(
        RunConfigError,
        match="Duplicate prediction",
    ):
        run_config(
            resolved=resolved,
            config=_config(),
            predictions=(
                FixturePrediction(
                    case_id="mcq-001",
                    prediction="B",
                ),
                FixturePrediction(
                    case_id="mcq-001",
                    prediction="A",
                ),
            ),
        )


@pytest.mark.parametrize(
    ("predictions", "error_message"),
    [
        (
            (
                FixturePrediction(
                    case_id="mcq-001",
                    prediction="B",
                ),
            ),
            "missing",
        ),
        (
            (
                FixturePrediction(
                    case_id="mcq-001",
                    prediction="B",
                ),
                FixturePrediction(
                    case_id="mcq-002",
                    prediction="A",
                ),
                FixturePrediction(
                    case_id="unknown-case",
                    prediction="B",
                ),
            ),
            "unexpected",
        ),
    ],
)
def test_run_config_requires_exact_prediction_coverage(
    predictions: tuple[FixturePrediction, ...],
    error_message: str,
) -> None:
    resolved = _resolved(
        (
            _mcq_case("mcq-001"),
            _mcq_case("mcq-002"),
        )
    )

    with pytest.raises(
        RunConfigError,
        match=error_message,
    ):
        run_config(
            resolved=resolved,
            config=_config(),
            predictions=predictions,
        )


@pytest.mark.parametrize(
    ("split", "qualification_status"),
    [
        ("dev", "synthetic"),
        ("smoke", "candidate"),
    ],
)
def test_fixture_run_rejects_non_synthetic_smoke_cases(
    split: DatasetSplit,
    qualification_status: QualificationStatus,
) -> None:
    resolved = _resolved(
        (
            _mcq_case(
                "mcq-001",
                split=split,
                qualification_status=qualification_status,
            ),
        )
    )

    with pytest.raises(
        RunConfigError,
        match="requires synthetic smoke cases",
    ):
        run_config(
            resolved=resolved,
            config=_config(),
            predictions=(
                FixturePrediction(
                    case_id="mcq-001",
                    prediction="B",
                ),
            ),
        )


def test_run_config_reports_unsupported_grader_with_case_id() -> None:
    resolved = _resolved((_instruction_case("instruction-001"),))

    with pytest.raises(
        RunConfigError,
        match="instruction-001",
    ):
        run_config(
            resolved=resolved,
            config=_config(),
            predictions=(
                FixturePrediction(
                    case_id="instruction-001",
                    prediction="Một. Hai. Ba.",
                ),
            ),
        )


def test_run_config_allows_empty_no_answer_prediction() -> None:
    resolved = _resolved((_unanswerable_qa_case("qa-001"),))

    result = run_config(
        resolved=resolved,
        config=_config(),
        predictions=(
            FixturePrediction(
                case_id="qa-001",
                prediction="",
            ),
        ),
    )

    assert result.rows[0].grade.passed is True
    assert result.rows[0].grade.reason == "correct_no_answer"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("run_purpose", "live_research"),
        ("execution_source", "live"),
    ],
)
def test_fixture_config_cannot_be_relabeled_as_live(
    field_name: str,
    value: str,
) -> None:
    payload: dict[str, object] = {
        "run_id": "fixture-run-001",
        "config_id": "frozen-predictions-v1",
        field_name: value,
    }

    with pytest.raises(ValidationError):
        FixtureRunConfig.model_validate(payload)
