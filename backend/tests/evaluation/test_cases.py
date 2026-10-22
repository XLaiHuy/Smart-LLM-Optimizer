import pytest
from pydantic import ValidationError

from app.evaluation.cases import (
    AnswerSpan,
    EvalCase,
    ExtractiveQATarget,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    MemoryServingInput,
    MemoryTarget,
    SourceMetadata,
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


def test_mcq_case_separates_serving_input_from_hidden_target() -> None:
    case = EvalCase(
        case_id="vmlu-mcq-001",
        task_family="multidisciplinary_mcq",
        source=_candidate_source(),
        serving_input=MCQServingInput(
            question="Thủ đô của Việt Nam là gì?",
            options=(
                MCQOption(key="A", text="Huế"),
                MCQOption(key="B", text="Hà Nội"),
                MCQOption(key="C", text="Đà Nẵng"),
                MCQOption(key="D", text="Cần Thơ"),
            ),
        ),
        evaluator_target=MCQTarget(answer_key="B"),
        tags=("geography",),
    )

    serving_payload = case.serving_input.model_dump(mode="json")

    assert "answer_key" not in serving_payload
    assert isinstance(case.evaluator_target, MCQTarget)
    assert case.evaluator_target.answer_key == "B"


def test_mcq_keys_are_normalized_before_case_validation() -> None:
    case = EvalCase(
        case_id="mcq-normalized-001",
        task_family="multidisciplinary_mcq",
        source=_candidate_source(),
        serving_input=MCQServingInput(
            question="Chọn đáp án đúng.",
            options=(
                MCQOption(key=" a ", text="Một"),
                MCQOption(key="b", text="Hai"),
            ),
        ),
        evaluator_target=MCQTarget(answer_key=" b "),
    )

    assert tuple(option.key for option in case.serving_input.options) == ("A", "B")
    assert isinstance(case.evaluator_target, MCQTarget)
    assert case.evaluator_target.answer_key == "B"


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        ("A", "a"),
        ("A", "AA"),
        ("A", "1"),
    ],
)
def test_mcq_serving_input_rejects_invalid_or_duplicate_keys(
    first_key: str,
    second_key: str,
) -> None:
    with pytest.raises(ValidationError):
        MCQServingInput(
            question="Chọn đáp án đúng.",
            options=(
                MCQOption(key=first_key, text="Một"),
                MCQOption(key=second_key, text="Hai"),
            ),
        )


def test_eval_case_rejects_mismatched_task_types() -> None:
    with pytest.raises(ValidationError, match="task_family"):
        EvalCase(
            case_id="mismatched-001",
            task_family="extractive_qa",
            source=_candidate_source(),
            serving_input=MCQServingInput(
                question="Chọn đáp án đúng.",
                options=(
                    MCQOption(key="A", text="Một"),
                    MCQOption(key="B", text="Hai"),
                ),
            ),
            evaluator_target=MCQTarget(answer_key="A"),
        )


def test_extract_qa_preserves_golds_and_plausible_answers() -> None:
    answerable = ExtractiveQATarget(
        answers=(
            AnswerSpan(text="Đại học Mở", answer_start=0),
            AnswerSpan(text="Trường Đại học Mở", answer_start=0),
        ),
        is_impossible=False,
    )

    unanswerable = ExtractiveQATarget(
        answers=(),
        plausible_answers=(AnswerSpan(text="một đáp án gây nhiễu", answer_start=10),),
        is_impossible=True,
    )

    assert len(answerable.answers) == 2
    assert unanswerable.answers == ()
    assert len(unanswerable.plausible_answers) == 1


@pytest.mark.parametrize(
    ("is_impossible", "answers"),
    [
        (False, ()),
        (
            True,
            (
                AnswerSpan(
                    text="không được phép là gold",
                    answer_start=0,
                ),
            ),
        ),
    ],
)
def test_extract_qa_rejects_invalid_answerability_shape(
    is_impossible: bool,
    answers: tuple[AnswerSpan, ...],
) -> None:
    with pytest.raises(ValidationError):
        ExtractiveQATarget(
            answers=answers,
            is_impossible=is_impossible,
        )


def test_memory_case_rejects_evidence_outside_visible_checkpoint() -> None:
    with pytest.raises(ValidationError, match="evidence turn IDs"):
        EvalCase(
            case_id="memory-001",
            task_family="conversation_memory",
            source=_candidate_source(),
            serving_input=MemoryServingInput(
                turns=(
                    {
                        "turn_id": "turn-1",
                        "turn_index": 1,
                        "role": "user",
                        "content": "Tên tôi là Khoa.",
                    },
                ),
                checkpoint=1,
                question="Người dùng tên gì?",
            ),
            evaluator_target=MemoryTarget(
                gold_answers=("Khoa",),
                evidence_turn_ids=("turn-2",),
                probe_type="recall",
                protocol_version="vi-dialog-memory-probes-v1",
                annotator="annotator-a",
                reviewer="reviewer-b",
                review_status="reviewed",
            ),
        )


def test_instruction_case_retains_rule_metadata() -> None:
    case = EvalCase.model_validate(
        {
            "case_id": "ifeval-001",
            "task_family": "instruction",
            "source": _candidate_source().model_dump(mode="json"),
            "serving_input": {
                "kind": "instruction",
                "prompt": "Trả lời đúng ba câu.",
            },
            "evaluator_target": {
                "kind": "instruction",
                "rules": [
                    {
                        "instruction_id": "number_of_sentences",
                        "kwargs": [
                            {
                                "name": "num_sentences",
                                "value": 3,
                            }
                        ],
                    }
                ],
                "evaluator_version": "sea-ifeval-candidate-v1",
            },
        }
    )

    assert isinstance(case.evaluator_target, InstructionTarget)
    rule = case.evaluator_target.rules[0]
    assert rule.instruction_id == "number_of_sentences"
    assert rule.kwargs[0].value == 3
