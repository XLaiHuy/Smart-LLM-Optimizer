import pytest

from app.evaluation.cases import (
    AnswerSpan,
    ConversationTurn,
    EvalCase,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    InstructionArgument,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    MemoryServingInput,
    MemoryTarget,
    SourceMetadata,
)
from app.evaluation.dispatcher import UnsupportedGraderError, grade_case
from app.evaluation.graders import (
    MEMORY_GRADER_VERSION,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
)


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


def _instruction_case(
    rules: tuple[InstructionRule, ...],
    *,
    evaluator_version: str = (SEA_IFEVAL_GRADER_VERSION),
) -> EvalCase:
    return EvalCase(
        case_id="instruction-001",
        task_family="instruction",
        source=_candidate_source(),
        serving_input=InstructionServingInput(
            prompt="Tuân thủ các yêu cầu định dạng.",
        ),
        evaluator_target=InstructionTarget(
            rules=rules,
            evaluator_version=evaluator_version,
        ),
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


@pytest.mark.parametrize(
    (
        "prediction",
        "passed",
        "expected_exact_match",
        "expected_token_f1",
        "expected_reason",
    ),
    [
        (
            "Khoa",
            True,
            1.0,
            1.0,
            "exact_match",
        ),
        (
            "Tên là Khoa",
            False,
            0.0,
            0.5,
            "partial_match",
        ),
    ],
)
def test_grade_case_dispatches_memory_probe(
    prediction: str,
    passed: bool,
    expected_exact_match: float,
    expected_token_f1: float,
    expected_reason: str,
) -> None:
    case = EvalCase(
        case_id="memory-001",
        task_family="conversation_memory",
        source=_candidate_source(),
        serving_input=MemoryServingInput(
            turns=(
                ConversationTurn(
                    turn_id="turn-001",
                    turn_index=1,
                    role="user",
                    content="Tên tôi là Khoa.",
                ),
            ),
            checkpoint=1,
            question="Người dùng tên gì?",
        ),
        evaluator_target=MemoryTarget(
            gold_answers=("Khoa",),
            evidence_turn_ids=("turn-001",),
            probe_type="recall",
            protocol_version=("vi-dialog-memory-probes-v1"),
            review_status="draft",
        ),
    )

    result = grade_case(
        case=case,
        prediction=prediction,
    )

    metrics = {metric.name: metric.value for metric in result.metrics}

    assert result.passed is passed
    assert result.reason == expected_reason
    assert result.grader_version == (MEMORY_GRADER_VERSION)
    assert metrics == {
        "exact_match": expected_exact_match,
        "token_f1": expected_token_f1,
    }


# def test_grade_case_rejects_task_without_implemented_grader() -> None:
#     case = EvalCase(
#         case_id="instruction-001",
#         task_family="instruction",
#         source=_candidate_source(),
#         serving_input=InstructionServingInput(
#             prompt="Trả lời bằng đúng ba câu.",
#         ),
#         evaluator_target=InstructionTarget(
#             rules=(
#                 InstructionRule(
#                     instruction_id="number_of_sentences",
#                 ),
#             ),
#             evaluator_version="sea-ifeval-candidate-v1",
#         ),
#     )

#     with pytest.raises(
#         UnsupportedGraderError,
#         match="instruction",
#     ):
#         grade_case(
#             case=case,
#             prediction="Một. Hai. Ba.",
#         )


def test_grade_case_dispatches_sea_ifeval_instruction() -> None:
    case = _instruction_case(
        (
            InstructionRule(
                instruction_id=("length_constraints:number_sentences"),
                kwargs=(
                    InstructionArgument(
                        name="relation",
                        value="exactly",
                    ),
                    InstructionArgument(
                        name="num_sentences",
                        value=2,
                    ),
                ),
            ),
        )
    )

    result = grade_case(
        case=case,
        prediction="Câu thứ nhất.***Câu thứ hai.",
        language_detector=lambda _: "vi",
    )

    metrics = {metric.name: metric.value for metric in result.metrics}

    assert result.passed is True
    assert result.reason == "all_rules_passed"
    assert result.grader_version == (SEA_IFEVAL_GRADER_VERSION)
    assert metrics == {
        "overall_acc": 1.0,
        "correct_language_rate": 1.0,
        "overall_lang_normalized_acc": 1.0,
        "case_all_pass_rate": 1.0,
    }


def test_grade_case_reports_partial_instruction_failure() -> None:
    case = _instruction_case(
        (
            InstructionRule(
                instruction_id="detectable_format:title",
            ),
            InstructionRule(
                instruction_id="startend:first_word",
                kwargs=(
                    InstructionArgument(
                        name="first_word",
                        value="Xin",
                    ),
                ),
            ),
        )
    )

    result = grade_case(
        case=case,
        prediction="<<Tiêu đề>>",
        language_detector=lambda _: "vi",
    )

    metrics = {metric.name: metric.value for metric in result.metrics}

    assert result.passed is False
    assert result.reason == ("failed_rules:startend:first_word=constraint_failed")
    assert metrics == {
        "overall_acc": 0.5,
        "correct_language_rate": 1.0,
        "overall_lang_normalized_acc": 0.5,
        "case_all_pass_rate": 0.0,
    }


def test_grade_case_requires_instruction_language_detector() -> None:
    case = _instruction_case(
        (
            InstructionRule(
                instruction_id="detectable_format:title",
            ),
        )
    )

    with pytest.raises(
        UnsupportedGraderError,
        match="requires a language detector",
    ):
        grade_case(
            case=case,
            prediction="<<Tiêu đề>>",
        )


def test_grade_case_rejects_instruction_evaluator_version() -> None:
    case = _instruction_case(
        (
            InstructionRule(
                instruction_id="detectable_format:title",
            ),
        ),
        evaluator_version="unknown-evaluator-v1",
    )

    with pytest.raises(
        UnsupportedGraderError,
        match="evaluator version",
    ):
        grade_case(
            case=case,
            prediction="<<Tiêu đề>>",
            language_detector=lambda _: "vi",
        )
