import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

MCQ_GRADER_VERSION = "mcq-option-v1"
QA_GRADER_VERSION = "vi-extractive-qa-nfc-token-v1"

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


QAGradeReason = Literal[
    "exact_match",
    "partial_match",
    "incorrect",
    "correct_no_answer",
    "unexpected_answer",
]


@dataclass(frozen=True, slots=True)
class QAGrade:
    passed: bool
    exact_match: float
    token_f1: float
    normalized_prediction: str
    matched_gold: str | None
    reason: QAGradeReason
    grader_version: str = QA_GRADER_VERSION


def normalize_qa_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).casefold()

    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )

    return " ".join(without_punctuation.split())


def _token_f1(
    prediction_tokens: tuple[str, ...],
    gold_tokens: tuple[str, ...],
) -> float:
    if not prediction_tokens and not gold_tokens:
        return 1.0

    if not prediction_tokens or not gold_tokens:
        return 0.0

    prediction_counts = Counter(prediction_tokens)
    gold_counts = Counter(gold_tokens)
    overlap = sum((prediction_counts & gold_counts).values())

    if overlap == 0:
        return 0.0

    precision = overlap / len(prediction_tokens)
    recall = overlap / len(gold_tokens)

    return 2 * precision * recall / (precision + recall)


def grade_extractive_qa(
    *,
    prediction: str,
    gold_answers: tuple[str, ...],
    is_impossible: bool,
) -> QAGrade:
    normalized_prediction = normalize_qa_text(prediction)

    if is_impossible:
        if gold_answers:
            raise ValueError("unanswerable case must not contain gold answers")

        if not prediction.strip():
            return QAGrade(
                passed=True,
                exact_match=1.0,
                token_f1=1.0,
                normalized_prediction=normalized_prediction,
                matched_gold=None,
                reason="correct_no_answer",
            )

        return QAGrade(
            passed=False,
            exact_match=0.0,
            token_f1=0.0,
            normalized_prediction=normalized_prediction,
            matched_gold=None,
            reason="unexpected_answer",
        )

    if not gold_answers:
        raise ValueError("answerable case must contain at least one gold answer")

    normalized_golds = tuple(normalize_qa_text(gold) for gold in gold_answers)

    if any(not gold for gold in normalized_golds):
        raise ValueError("gold answers must contain normalized text")

    prediction_tokens = tuple(normalized_prediction.split())

    scores = tuple(
        (
            float(normalized_prediction == normalized_gold),
            _token_f1(
                prediction_tokens,
                tuple(normalized_gold.split()),
            ),
            original_gold,
        )
        for original_gold, normalized_gold in zip(
            gold_answers,
            normalized_golds,
            strict=True,
        )
    )

    exact_match = max(score[0] for score in scores)
    best_f1_score = max(scores, key=lambda score: (score[1], score[0]))
    token_f1 = best_f1_score[1]
    matched_gold = best_f1_score[2]

    if exact_match == 1.0:
        reason: QAGradeReason = "exact_match"
    elif token_f1 > 0.0:
        reason = "partial_match"
    else:
        reason = "incorrect"

    return QAGrade(
        passed=exact_match == 1.0,
        exact_match=exact_match,
        token_f1=token_f1,
        normalized_prediction=normalized_prediction,
        matched_gold=matched_gold,
        reason=reason,
    )
