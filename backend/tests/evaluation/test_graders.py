from decimal import Decimal

import pytest

from app.evaluation.graders import (
    EXACT_GRADER_VERSION,
    MCQ_GRADER_VERSION,
    NUMERIC_GRADER_VERSION,
    QA_GRADER_VERSION,
    SCHEMA_GRADER_VERSION,
    ExactMatchMode,
    JsonFieldSpec,
    grade_exact,
    grade_extractive_qa,
    grade_mcq,
    grade_numeric,
    grade_schema,
    normalize_exact_text,
    normalize_qa_text,
)


@pytest.mark.parametrize(
    (
        "prediction",
        "reference",
        "mode",
        "passed",
    ),
    [
        (
            "Hà Nội",
            "Hà Nội",
            "strict",
            True,
        ),
        (
            " Hà Nội ",
            "Hà Nội",
            "strict",
            False,
        ),
        (
            "  Ho\u0300a  ",
            "Hòa",
            "nfc_trim",
            True,
        ),
        (
            "hòa",
            "Hòa",
            "nfc_trim",
            False,
        ),
        (
            "B.",
            "B",
            "nfc_trim",
            False,
        ),
        (
            "Đáp án: B",
            "B",
            "nfc_trim",
            False,
        ),
        (
            "không",
            "có",
            "nfc_trim",
            False,
        ),
    ],
)
def test_grade_exact_strict_and_normalized_modes(
    prediction: str,
    reference: str,
    mode: ExactMatchMode,
    passed: bool,
) -> None:
    result = grade_exact(
        prediction=prediction,
        references=(reference,),
        mode=mode,
    )

    expected_prediction = prediction if mode == "strict" else normalize_exact_text(prediction)

    assert result.passed is passed
    assert result.normalized_prediction == expected_prediction
    assert result.matched_reference == (reference if passed else None)
    assert result.mode == mode
    assert result.reason == ("exact_match" if passed else "incorrect")
    assert result.grader_version == EXACT_GRADER_VERSION


@pytest.mark.parametrize(
    ("references", "mode", "error_message"),
    [
        (
            (),
            "strict",
            "references must not be empty",
        ),
        (
            ("   ",),
            "strict",
            "references must not contain blank values",
        ),
        (
            (
                "Hòa",
                "Ho\u0300a",
            ),
            "nfc_trim",
            "duplicates after normalization",
        ),
    ],
)
def test_grade_exact_rejects_invalid_references(
    references: tuple[str, ...],
    mode: ExactMatchMode,
    error_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        grade_exact(
            prediction="Hòa",
            references=references,
            mode=mode,
        )


def test_grade_exact_rejects_unknown_mode() -> None:
    with pytest.raises(
        ValueError,
        match="unsupported exact match mode",
    ):
        grade_exact(
            prediction="Hà Nội",
            references=("Hà Nội",),
            mode="casefold",  # type: ignore[arg-type]
        )


def test_grade_exact_matches_one_of_multiple_references() -> None:
    result = grade_exact(
        prediction="Thành phố Hồ Chí Minh",
        references=(
            "Sài Gòn",
            "Thành phố Hồ Chí Minh",
        ),
        mode="strict",
    )

    assert result.passed is True
    assert result.matched_reference == "Thành phố Hồ Chí Minh"
    assert result.reason == "exact_match"


@pytest.mark.parametrize(
    (
        "prediction",
        "expected",
        "absolute_tolerance",
        "relative_tolerance",
        "passed",
        "reason",
    ),
    [
        (
            "10",
            "10",
            "0",
            "0",
            True,
            "within_tolerance",
        ),
        (
            "10.05",
            "10",
            "0.05",
            "0",
            True,
            "within_tolerance",
        ),
        (
            "10.051",
            "10",
            "0.05",
            "0",
            False,
            "outside_tolerance",
        ),
        (
            "101",
            "100",
            "0",
            "0.01",
            True,
            "within_tolerance",
        ),
        (
            "101.01",
            "100",
            "0",
            "0.01",
            False,
            "outside_tolerance",
        ),
        (
            "-2.5",
            "-2.5",
            "0",
            "0",
            True,
            "within_tolerance",
        ),
        (
            "1e3",
            "1000",
            "0",
            "0",
            True,
            "within_tolerance",
        ),
    ],
)
def test_grade_numeric_exact_and_tolerance_boundaries(
    prediction: str,
    expected: str,
    absolute_tolerance: str,
    relative_tolerance: str,
    passed: bool,
    reason: str,
) -> None:
    result = grade_numeric(
        prediction=prediction,
        expected=Decimal(expected),
        absolute_tolerance=Decimal(absolute_tolerance),
        relative_tolerance=Decimal(relative_tolerance),
    )

    assert result.passed is passed
    assert result.parsed_prediction == Decimal(prediction)
    assert result.expected == Decimal(expected)
    assert result.absolute_error is not None
    assert result.reason == reason
    assert result.grader_version == NUMERIC_GRADER_VERSION


@pytest.mark.parametrize(
    "prediction",
    [
        "",
        "10 kg",
        "Giá trị: 10",
        "1,5",
        "NaN",
        "Infinity",
    ],
)
def test_grade_numeric_rejects_non_numeric_output(
    prediction: str,
) -> None:
    result = grade_numeric(
        prediction=prediction,
        expected=Decimal("10"),
    )

    assert result.passed is False
    assert result.parsed_prediction is None
    assert result.absolute_error is None
    assert result.reason == "invalid_format"
    assert result.grader_version == NUMERIC_GRADER_VERSION


@pytest.mark.parametrize(
    (
        "expected",
        "absolute_tolerance",
        "relative_tolerance",
        "error_message",
    ),
    [
        (
            "NaN",
            "0",
            "0",
            "expected must be finite",
        ),
        (
            "Infinity",
            "0",
            "0",
            "expected must be finite",
        ),
        (
            "1",
            "-0.1",
            "0",
            "absolute_tolerance must be non-negative",
        ),
        (
            "1",
            "0",
            "-0.1",
            "relative_tolerance must be non-negative",
        ),
        (
            "1",
            "NaN",
            "0",
            "absolute_tolerance must be finite",
        ),
    ],
)
def test_grade_numeric_rejects_invalid_configuration(
    expected: str,
    absolute_tolerance: str,
    relative_tolerance: str,
    error_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        grade_numeric(
            prediction="1",
            expected=Decimal(expected),
            absolute_tolerance=Decimal(absolute_tolerance),
            relative_tolerance=Decimal(relative_tolerance),
        )


def test_grade_schema_validates_supported_json_types() -> None:
    result = grade_schema(
        prediction=(
            '{"name":"Khoa","age":21,"score":9.5,"active":true,"note":null,"tags":[],"meta":{}}'
        ),
        fields=(
            JsonFieldSpec(
                name="name",
                value_type="string",
            ),
            JsonFieldSpec(
                name="age",
                value_type="integer",
            ),
            JsonFieldSpec(
                name="score",
                value_type="number",
            ),
            JsonFieldSpec(
                name="active",
                value_type="boolean",
            ),
            JsonFieldSpec(
                name="note",
                value_type="null",
            ),
            JsonFieldSpec(
                name="tags",
                value_type="array",
            ),
            JsonFieldSpec(
                name="meta",
                value_type="object",
            ),
        ),
    )

    assert result.passed is True
    assert result.reason == "valid_schema"
    assert result.missing_fields == ()
    assert result.unexpected_fields == ()
    assert result.wrong_type_fields == ()
    assert result.grader_version == SCHEMA_GRADER_VERSION


def test_grade_schema_allows_missing_optional_field() -> None:
    result = grade_schema(
        prediction='{"answer":"B"}',
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
            JsonFieldSpec(
                name="explanation",
                value_type="string",
                required=False,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason == "valid_schema"


def test_grade_schema_allows_extra_keys_when_configured() -> None:
    result = grade_schema(
        prediction='{"answer":"B","explanation":"Vì B đúng"}',
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
        ),
        allow_extra_keys=True,
    )

    assert result.passed is True
    assert result.reason == "valid_schema"
    assert result.unexpected_fields == ()


def test_grade_schema_rejects_wrong_type_for_present_optional_field() -> None:
    result = grade_schema(
        prediction='{"answer":"B","explanation":123}',
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
            JsonFieldSpec(
                name="explanation",
                value_type="string",
                required=False,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason == "wrong_field_type"
    assert result.wrong_type_fields == ("explanation",)


@pytest.mark.parametrize(
    "prediction",
    [
        "",
        "{",
        '{"answer":NaN}',
        '{"answer":"A","answer":"B"}',
    ],
)
def test_grade_schema_rejects_invalid_json(
    prediction: str,
) -> None:
    result = grade_schema(
        prediction=prediction,
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
        ),
    )

    assert result.passed is False
    assert result.reason == "invalid_json"


@pytest.mark.parametrize(
    "prediction",
    [
        "[]",
        '"A"',
        "10",
        "null",
    ],
)
def test_grade_schema_requires_top_level_object(
    prediction: str,
) -> None:
    result = grade_schema(
        prediction=prediction,
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
        ),
    )

    assert result.passed is False
    assert result.reason == "not_object"


@pytest.mark.parametrize(
    (
        "prediction",
        "reason",
        "missing_fields",
        "unexpected_fields",
        "wrong_type_fields",
    ),
    [
        (
            "{}",
            "missing_required_fields",
            ("answer",),
            (),
            (),
        ),
        (
            '{"answer":"A","extra":1}',
            "unexpected_fields",
            (),
            ("extra",),
            (),
        ),
        (
            '{"answer":1}',
            "wrong_field_type",
            (),
            (),
            ("answer",),
        ),
    ],
)
def test_grade_schema_reports_structural_failures(
    prediction: str,
    reason: str,
    missing_fields: tuple[str, ...],
    unexpected_fields: tuple[str, ...],
    wrong_type_fields: tuple[str, ...],
) -> None:
    result = grade_schema(
        prediction=prediction,
        fields=(
            JsonFieldSpec(
                name="answer",
                value_type="string",
            ),
        ),
    )

    assert result.passed is False
    assert result.reason == reason
    assert result.missing_fields == missing_fields
    assert result.unexpected_fields == unexpected_fields
    assert result.wrong_type_fields == wrong_type_fields


@pytest.mark.parametrize(
    (
        "prediction",
        "value_type",
        "passed",
    ),
    [
        (
            '{"value":3}',
            "number",
            True,
        ),
        (
            '{"value":3.5}',
            "integer",
            False,
        ),
        (
            '{"value":true}',
            "integer",
            False,
        ),
    ],
)
def test_grade_schema_distinguishes_numeric_types(
    prediction: str,
    value_type: str,
    passed: bool,
) -> None:
    result = grade_schema(
        prediction=prediction,
        fields=(
            JsonFieldSpec(
                name="value",
                value_type=value_type,  # type: ignore[arg-type]
            ),
        ),
    )

    assert result.passed is passed
    assert result.reason == ("valid_schema" if passed else "wrong_field_type")


@pytest.mark.parametrize(
    ("fields", "error_message"),
    [
        (
            (),
            "schema fields must not be empty",
        ),
        (
            (
                JsonFieldSpec(
                    name="   ",
                    value_type="string",
                ),
            ),
            "schema field names must not be blank",
        ),
        (
            (
                JsonFieldSpec(
                    name="answer",
                    value_type="string",
                ),
                JsonFieldSpec(
                    name="answer",
                    value_type="string",
                ),
            ),
            "schema field names must not contain duplicates",
        ),
        (
            (
                JsonFieldSpec(
                    name="date",
                    value_type="date",  # type: ignore[arg-type]
                ),
            ),
            "unsupported JSON value type",
        ),
    ],
)
def test_grade_schema_rejects_invalid_configuration(
    fields: tuple[JsonFieldSpec, ...],
    error_message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        grade_schema(
            prediction='{"answer":"A"}',
            fields=fields,
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
