import pytest

from app.evaluation.cases import (
    AnswerSpan,
    EvalCase,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    SourceMetadata,
)
from app.evaluation.dispatcher import UnsupportedGraderError, grade_case


def _candidate_source() -> SourceMetadata:
    return SourceMetadata(
        suite_name="fixture-suite",
        source_name="local-fixture",
        source_revision="fixture-v1",
        source_record_id="record-001",
        group_id="group-001",
        split="dev",
        language="vi",
        qualification_status="candidate",
    )


def test_grade_case_dispatches_mcq() -> None:
    case = EvalCase(
        case_id="mcq-001",
        task_family="multidisciplinary_mcq",
        source=_candidate_source(),
        serving_input=MCQServingInput(
            question="Thủ đô Việt Nam là gì?",
            options=(
                MCQOption(key="A", text="Huế"),
                MCQOption(key="B", text="Hà Nội"),
            ),
        ),
        evaluator_target=MCQTarget(answer_key="B"),
    )

    result = grade_case(
        case=case,
        prediction="Đáp án: b.",
    )

    metrics = {metric.name: metric.value for metric in result.metrics}

    assert result.case_id == "mcq-001"
    assert result.passed is True
    assert result.normalized_prediction == "B"
    assert metrics == {"accuracy": 1.0}


def test_grade_case_dispatches_extract_qa_without_using_plausible_answers() -> None:
    case = EvalCase(
        case_id="qa-001",
        task_family="extractive_qa",
        source=_candidate_source(),
        serving_input=ExtractiveQAServingInput(
            context="Đoạn văn không cung cấp tên thành phố.",
            question="Thành phố nào được nhắc đến?",
        ),
        evaluator_target=ExtractiveQATarget(
            answers=(),
            plausible_answers=(
                AnswerSpan(
                    text="Hà Nội",
                    answer_start=0,
                ),
            ),
            is_impossible=True,
        ),
    )

    result = grade_case(
        case=case,
        prediction="Hà Nội",
    )

    metrics = {metric.name: metric.value for metric in result.metrics}

    assert result.passed is False
    assert result.reason == "unexpected_answer"
    assert metrics == {
        "exact_match": 0.0,
        "token_f1": 0.0,
    }


def test_grade_case_rejects_task_without_implemented_grader() -> None:
    case = EvalCase(
        case_id="instruction-001",
        task_family="instruction",
        source=_candidate_source(),
        serving_input=InstructionServingInput(
            prompt="Trả lời bằng đúng ba câu.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id="number_of_sentences",
                ),
            ),
            evaluator_version="sea-ifeval-candidate-v1",
        ),
    )

    with pytest.raises(
        UnsupportedGraderError,
        match="instruction",
    ):
        grade_case(
            case=case,
            prediction="Một. Hai. Ba.",
        )
