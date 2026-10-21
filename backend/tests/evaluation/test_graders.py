import pytest

from app.evaluation.graders import MCQ_GRADER_VERSION, grade_mcq


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
