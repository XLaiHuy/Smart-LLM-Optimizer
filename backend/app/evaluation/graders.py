import re
from dataclasses import dataclass
from typing import Literal

MCQ_GRADER_VERSION = "mcq-option-v1"

MCQGradeReason = Literal[
    "correct",
    "incorrect",
    "invalid_format",
    "invalid_option",
]


@dataclass(frozen=True, slots=True)
class MCQGrade:
    passed: bool
    normalized_prediction: str | None
    reason: MCQGradeReason
    grader_version: str = MCQ_GRADER_VERSION


_MCQ_PATTERN = re.compile(
    r"(?:đáp\s+án\s*:\s*)?([A-Za-z])\.?",
    re.IGNORECASE,
)


def _normalize_valid_keys(valid_keys: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(key.strip().upper() for key in valid_keys)

    if not normalized:
        raise ValueError("valid_keys must not be empty")

    if any(len(key) != 1 or not key.isascii() or not key.isalpha() for key in normalized):
        raise ValueError("valid_keys must contain single ASCII letters")

    if len(set(normalized)) != len(normalized):
        raise ValueError("valid_keys must not contain duplicates")

    return normalized


def grade_mcq(
    *,
    prediction: str,
    answer_key: str,
    valid_keys: tuple[str, ...],
) -> MCQGrade:
    normalized_keys = _normalize_valid_keys(valid_keys)
    normalized_answer_key = answer_key.strip().upper()

    if normalized_answer_key not in normalized_keys:
        raise ValueError("answer_key must be one of valid_keys")

    match = _MCQ_PATTERN.fullmatch(prediction.strip())
    if match is None:
        return MCQGrade(
            passed=False,
            normalized_prediction=None,
            reason="invalid_format",
        )

    normalized_prediction = match.group(1).upper()

    if normalized_prediction not in normalized_keys:
        return MCQGrade(
            passed=False,
            normalized_prediction=normalized_prediction,
            reason="invalid_option",
        )

    if normalized_prediction == normalized_answer_key:
        return MCQGrade(
            passed=True,
            normalized_prediction=normalized_prediction,
            reason="correct",
        )

    return MCQGrade(
        passed=False,
        normalized_prediction=normalized_prediction,
        reason="incorrect",
    )
