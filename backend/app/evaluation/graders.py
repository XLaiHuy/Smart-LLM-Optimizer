import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Literal, NoReturn, cast

EXACT_GRADER_VERSION = "exact-match-v1"
MCQ_GRADER_VERSION = "mcq-option-v1"
MEMORY_GRADER_VERSION = "vi-dialog-memory-probe-nfc-token-v1"
NUMERIC_GRADER_VERSION = "numeric-decimal-v1"
QA_GRADER_VERSION = "vi-extractive-qa-nfc-token-v1"
SCHEMA_GRADER_VERSION = "json-object-schema-v1"

ExactMatchMode = Literal[
    "strict",
    "nfc_trim",
]

ExactGradeReason = Literal[
    "exact_match",
    "incorrect",
]


@dataclass(frozen=True, slots=True)
class ExactGrade:
    passed: bool
    normalized_prediction: str
    matched_reference: str | None
    mode: ExactMatchMode
    reason: ExactGradeReason
    grader_version: str = EXACT_GRADER_VERSION


def normalize_exact_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def _prepare_exact_value(
    value: str,
    mode: ExactMatchMode,
) -> str:
    if mode == "strict":
        return value

    if mode == "nfc_trim":
        return normalize_exact_text(value)

    raise ValueError(f"unsupported exact match mode: {mode!r}")


def grade_exact(
    *,
    prediction: str,
    references: tuple[str, ...],
    mode: ExactMatchMode = "strict",
) -> ExactGrade:
    if not references:
        raise ValueError("references must not be empty")

    if any(not reference.strip() for reference in references):
        raise ValueError("references must not contain blank values")

    normalized_references = tuple(_prepare_exact_value(reference, mode) for reference in references)

    if len(set(normalized_references)) != len(normalized_references):
        raise ValueError("references must not contain duplicates after normalization")

    normalized_prediction = _prepare_exact_value(
        prediction,
        mode,
    )

    for original_reference, normalized_reference in zip(
        references,
        normalized_references,
        strict=True,
    ):
        if normalized_prediction == normalized_reference:
            return ExactGrade(
                passed=True,
                normalized_prediction=normalized_prediction,
                matched_reference=original_reference,
                mode=mode,
                reason="exact_match",
            )

    return ExactGrade(
        passed=False,
        normalized_prediction=normalized_prediction,
        matched_reference=None,
        mode=mode,
        reason="incorrect",
    )


NumericGradeReason = Literal[
    "within_tolerance",
    "outside_tolerance",
    "invalid_format",
]


@dataclass(frozen=True, slots=True)
class NumericGrade:
    passed: bool
    parsed_prediction: Decimal | None
    expected: Decimal
    absolute_error: Decimal | None
    allowed_error: Decimal
    reason: NumericGradeReason
    grader_version: str = NUMERIC_GRADER_VERSION


_NUMERIC_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _require_finite_decimal(
    value: Decimal,
    *,
    field_name: str,
) -> None:
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")


def _require_valid_tolerance(
    value: Decimal,
    *,
    field_name: str,
) -> None:
    _require_finite_decimal(
        value,
        field_name=field_name,
    )

    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def grade_numeric(
    *,
    prediction: str,
    expected: Decimal,
    absolute_tolerance: Decimal = Decimal("0"),
    relative_tolerance: Decimal = Decimal("0"),
) -> NumericGrade:
    _require_finite_decimal(
        expected,
        field_name="expected",
    )
    _require_valid_tolerance(
        absolute_tolerance,
        field_name="absolute_tolerance",
    )
    _require_valid_tolerance(
        relative_tolerance,
        field_name="relative_tolerance",
    )

    try:
        relative_error_limit = relative_tolerance * abs(expected)
    except DecimalException as exc:
        raise ValueError("combined tolerance must be finite") from exc

    allowed_error = max(
        absolute_tolerance,
        relative_error_limit,
    )

    if not allowed_error.is_finite():
        raise ValueError("combined tolerance must be finite")

    normalized_prediction = prediction.strip()

    if _NUMERIC_PATTERN.fullmatch(normalized_prediction) is None:
        return NumericGrade(
            passed=False,
            parsed_prediction=None,
            expected=expected,
            absolute_error=None,
            allowed_error=allowed_error,
            reason="invalid_format",
        )

    try:
        parsed_prediction = Decimal(normalized_prediction)
        absolute_error = abs(parsed_prediction - expected)
    except DecimalException:
        return NumericGrade(
            passed=False,
            parsed_prediction=None,
            expected=expected,
            absolute_error=None,
            allowed_error=allowed_error,
            reason="invalid_format",
        )

    if not parsed_prediction.is_finite() or not absolute_error.is_finite():
        return NumericGrade(
            passed=False,
            parsed_prediction=None,
            expected=expected,
            absolute_error=None,
            allowed_error=allowed_error,
            reason="invalid_format",
        )

    passed = absolute_error <= allowed_error
    reason: NumericGradeReason = "within_tolerance" if passed else "outside_tolerance"

    return NumericGrade(
        passed=passed,
        parsed_prediction=parsed_prediction,
        expected=expected,
        absolute_error=absolute_error,
        allowed_error=allowed_error,
        reason=reason,
    )


JsonValueType = Literal[
    "string",
    "integer",
    "number",
    "boolean",
    "null",
    "object",
    "array",
]

SchemaGradeReason = Literal[
    "valid_schema",
    "invalid_json",
    "not_object",
    "missing_required_fields",
    "unexpected_fields",
    "wrong_field_type",
]


@dataclass(frozen=True, slots=True)
class JsonFieldSpec:
    name: str
    value_type: JsonValueType
    required: bool = True


@dataclass(frozen=True, slots=True)
class SchemaGrade:
    passed: bool
    reason: SchemaGradeReason
    missing_fields: tuple[str, ...]
    unexpected_fields: tuple[str, ...]
    wrong_type_fields: tuple[str, ...]
    grader_version: str = SCHEMA_GRADER_VERSION


_SUPPORTED_JSON_VALUE_TYPES = frozenset(
    {
        "string",
        "integer",
        "number",
        "boolean",
        "null",
        "object",
        "array",
    }
)


class _DuplicateJsonKeyError(ValueError):
    pass


def _reject_non_standard_json_constant(
    value: str,
) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _build_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON key: {key!r}")

        result[key] = value

    return result


def _matches_json_type(
    value: object,
    expected_type: JsonValueType,
) -> bool:
    if expected_type == "string":
        return isinstance(value, str)

    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)

    if expected_type == "number":
        if isinstance(value, int) and not isinstance(value, bool):
            return True

        return isinstance(value, Decimal) and value.is_finite()

    if expected_type == "boolean":
        return isinstance(value, bool)

    if expected_type == "null":
        return value is None

    if expected_type == "object":
        return isinstance(value, dict)

    if expected_type == "array":
        return isinstance(value, list)

    raise ValueError(f"unsupported JSON value type: {expected_type!r}")


def _validate_schema_fields(
    fields: tuple[JsonFieldSpec, ...],
) -> None:
    if not fields:
        raise ValueError("schema fields must not be empty")

    field_names = tuple(field.name for field in fields)

    if any(not name.strip() for name in field_names):
        raise ValueError("schema field names must not be blank")

    if len(set(field_names)) != len(field_names):
        raise ValueError("schema field names must not contain duplicates")

    for field in fields:
        if field.value_type not in _SUPPORTED_JSON_VALUE_TYPES:
            raise ValueError(f"unsupported JSON value type: {field.value_type!r}")


def grade_schema(
    *,
    prediction: str,
    fields: tuple[JsonFieldSpec, ...],
    allow_extra_keys: bool = False,
) -> SchemaGrade:
    _validate_schema_fields(fields)

    try:
        parsed: object = json.loads(
            prediction,
            parse_float=Decimal,
            parse_constant=(_reject_non_standard_json_constant),
            object_pairs_hook=_build_json_object,
        )
    except (
        json.JSONDecodeError,
        DecimalException,
        ValueError,
    ):
        return SchemaGrade(
            passed=False,
            reason="invalid_json",
            missing_fields=(),
            unexpected_fields=(),
            wrong_type_fields=(),
        )

    if not isinstance(parsed, dict):
        return SchemaGrade(
            passed=False,
            reason="not_object",
            missing_fields=(),
            unexpected_fields=(),
            wrong_type_fields=(),
        )

    parsed_object = cast(
        dict[str, object],
        parsed,
    )
    expected_fields = {field.name: field for field in fields}
    observed_names = set(parsed_object)

    missing_fields = tuple(
        sorted(
            field.name for field in fields if (field.required and field.name not in observed_names)
        )
    )

    unexpected_fields = (
        () if allow_extra_keys else tuple(sorted(observed_names - set(expected_fields)))
    )

    wrong_type_fields = tuple(
        sorted(
            field.name
            for field in fields
            if (
                field.name in parsed_object
                and not _matches_json_type(
                    parsed_object[field.name],
                    field.value_type,
                )
            )
        )
    )

    if missing_fields:
        reason: SchemaGradeReason = "missing_required_fields"
    elif unexpected_fields:
        reason = "unexpected_fields"
    elif wrong_type_fields:
        reason = "wrong_field_type"
    else:
        reason = "valid_schema"

    return SchemaGrade(
        passed=reason == "valid_schema",
        reason=reason,
        missing_fields=missing_fields,
        unexpected_fields=unexpected_fields,
        wrong_type_fields=wrong_type_fields,
    )


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
