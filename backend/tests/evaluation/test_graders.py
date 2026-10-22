import pytest

from app.evaluation.graders import (
    MCQ_GRADER_VERSION,
    QA_GRADER_VERSION,
    grade_extractive_qa,
    grade_mcq,
    normalize_qa_text,
)


@pytest.mark.parametrize(
    ("prediction", "normalized_prediction", "passed", "reason"),
    [
        ("B", "B", True, "correct"),
        ("b", "B", True, "correct"),
        ("Đáp án: B", "B", True, "correct"),
        (" ĐÁP ÁN: b. ", "B", True, "correct"),
        ("A", "A", False, "incorrect"),
        ("", None, False, "invalid_format"),
        ("B hoặc C", None, False, "invalid_format"),
    ],
)
def test_grade_mcq_common_outputs(
    prediction: str,
    normalized_prediction: str | None,
    passed: bool,
    reason: str,
) -> None:
    result = grade_mcq(
        prediction=prediction,
        answer_key="B",
        valid_keys=("A", "B", "C", "D"),
    )

    assert result.normalized_prediction == normalized_prediction
    assert result.passed is passed
    assert result.reason == reason
    assert result.grader_version == MCQ_GRADER_VERSION


def test_grade_mcq_rejects_option_outside_configured_keys() -> None:
    result = grade_mcq(
        prediction="D",
        answer_key="B",
        valid_keys=("A", "B", "C"),
    )

    assert result.normalized_prediction == "D"
    assert result.passed is False
    assert result.reason == "invalid_option"


def test_grade_mcq_rejects_invalid_answer_key() -> None:
    with pytest.raises(ValueError, match="answer_key"):
        grade_mcq(
            prediction="B",
            answer_key="E",
            valid_keys=("A", "B", "C", "D"),
        )


@pytest.mark.parametrize(
    ("valid_keys", "error_message"),
    [
        ((), "valid_keys must not be empty"),
        (("A", "a"), "valid_keys must not contain duplicates"),
        (("A", "AB"), "valid_keys must contain single ASCII letters"),
    ],
)
def test_grade_mcq_rejects_invalid_valid_keys(
    valid_keys: tuple[str, ...],
    error_message: str,
) -> None:
    with pytest.raises(ValueError, match=error_message):
        grade_mcq(
            prediction="A",
            answer_key="A",
            valid_keys=valid_keys,
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  HÀ   NỘI  ", "hà nội"),
        ("Hà-Nội.", "hà nội"),
        ("không ít hơn 10", "không ít hơn 10"),
    ],
)
def test_normalize_qa_text_preserves_vietnamese_semantics(
    text: str,
    expected: str,
) -> None:
    assert normalize_qa_text(text) == expected
    assert normalize_qa_text("hoa") != normalize_qa_text("hòa")


def test_grade_extractive_qa_uses_best_matching_gold() -> None:
    result = grade_extractive_qa(
        prediction="Hà Nội",
        gold_answers=("Thành phố Hà Nội", "Hà Nội"),
        is_impossible=False,
    )

    assert result.passed is True
    assert result.exact_match == 1.0
    assert result.token_f1 == 1.0
    assert result.matched_gold == "Hà Nội"
    assert result.reason == "exact_match"
    assert result.grader_version == QA_GRADER_VERSION


def test_grade_extractive_qa_reports_partial_token_f1() -> None:
    result = grade_extractive_qa(
        prediction="Đại học Mở",
        gold_answers=("Trường Đại học Mở",),
        is_impossible=False,
    )

    assert result.passed is False
    assert result.exact_match == 0.0
    assert result.token_f1 == pytest.approx(6 / 7)
    assert result.matched_gold == "Trường Đại học Mở"
    assert result.reason == "partial_match"


@pytest.mark.parametrize(
    ("prediction", "passed", "reason"),
    [
        ("", True, "correct_no_answer"),
        ("   ", True, "correct_no_answer"),
        ("Không có đáp án", False, "unexpected_answer"),
        ("...", False, "unexpected_answer"),
    ],
)
def test_grade_extractive_qa_handles_unanswerable_cases(
    prediction: str,
    passed: bool,
    reason: str,
) -> None:
    result = grade_extractive_qa(
        prediction=prediction,
        gold_answers=(),
        is_impossible=True,
    )

    assert result.passed is passed
    assert result.reason == reason


@pytest.mark.parametrize(
    ("gold_answers", "is_impossible"),
    [
        ((), False),
        (("Hà Nội",), True),
        (("...",), False),
    ],
)
def test_grade_extractive_qa_rejects_invalid_targets(
    gold_answers: tuple[str, ...],
    is_impossible: bool,
) -> None:
    with pytest.raises(ValueError):
        grade_extractive_qa(
            prediction="Hà Nội",
            gold_answers=gold_answers,
            is_impossible=is_impossible,
        )
