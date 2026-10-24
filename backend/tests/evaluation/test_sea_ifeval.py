from typing import TypeAlias

import pytest

from app.evaluation.cases import (
    InstructionArgument,
    InstructionRule,
    InstructionValue,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
    SUPPORTED_INSTRUCTION_IDS,
    SeaIFEvalConfigurationError,
    grade_sea_ifeval_rule,
)

ArgumentPairs: TypeAlias = tuple[
    tuple[str, InstructionValue],
    ...,
]
PassingCase: TypeAlias = tuple[
    str,
    ArgumentPairs,
    str,
    str,
]


def _rule(
    instruction_id: str,
    arguments: ArgumentPairs = (),
) -> InstructionRule:
    return InstructionRule(
        instruction_id=instruction_id,
        kwargs=tuple(
            InstructionArgument(
                name=name,
                value=value,
            )
            for name, value in arguments
        ),
    )


def _detect_vietnamese(_: str) -> str:
    return "vi"


_PASSING_CASES: tuple[PassingCase, ...] = (
    (
        "length_constraints:number_words",
        (
            ("relation", "exactly"),
            ("num_words", 3),
        ),
        "một hai ba",
        "vi",
    ),
    (
        "length_constraints:number_sentences",
        (
            ("relation", "exactly"),
            ("num_sentences", 2),
        ),
        "Câu thứ nhất.***Câu thứ hai.",
        "vi",
    ),
    (
        "length_constraints:number_paragraphs",
        (("num_paragraphs", 2),),
        "Đoạn một***Đoạn hai",
        "vi",
    ),
    (
        "detectable_content:postscript",
        (("postscript_marker", "P.S."),),
        "Nội dung chính.\nP.S. Ghi chú.",
        "vi",
    ),
    (
        "detectable_content:number_placeholders",
        (("num_placeholders", 2),),
        "[một] [hai]",
        "vi",
    ),
    (
        "detectable_format:title",
        (),
        "<<Tiêu đề>>",
        "vi",
    ),
    (
        "detectable_format:number_bullet_lists",
        (("num_bullets", 2),),
        "- Mục một\n- Mục hai",
        "vi",
    ),
    (
        "detectable_format:multiple_sections",
        (
            ("section_title", "PHẦN"),
            ("num_sections", 2),
        ),
        "PHẦN 1\nNội dung\nPHẦN 2\nNội dung",
        "vi",
    ),
    (
        "detectable_format:number_highlighted_sections",
        (("num_highlights", 2),),
        "*một* và *hai*",
        "vi",
    ),
    (
        "detectable_format:json_format",
        (),
        '{"ok": true}',
        "vi",
    ),
    (
        "detectable_format:constrained_response",
        (),
        "Câu trả lời của tôi là có.",
        "vi",
    ),
    (
        "startend:first_word",
        (("first_word", "Xin"),),
        "Xin chào Việt Nam.",
        "vi",
    ),
    (
        "startend:end_checker",
        (("end_phrase", "chào."),),
        "Tôi xin gửi lời chào.",
        "vi",
    ),
    (
        "startend:quotation",
        (),
        '"Xin chào"',
        "vi",
    ),
    (
        "keywords:existence",
        (("keywords", ("ổn định", "hợp tác")),),
        "Chúng ta cần ổn định và hợp tác.",
        "vi",
    ),
    (
        "keywords:forbidden_words",
        (("forbidden_words", ("cấm",)),),
        "Đây là nội dung an toàn.",
        "vi",
    ),
    (
        "keywords:frequency",
        (
            ("keyword", "voi"),
            ("relation", "exactly"),
            ("frequency", 2),
        ),
        "voi và voi",
        "vi",
    ),
    (
        "keywords:number_frequency",
        (
            ("number", "3"),
            ("relation", "exactly"),
            ("frequency", 2),
        ),
        "3 và 3",
        "vi",
    ),
    (
        "combination:repeat_prompt",
        (("prompt_to_repeat", "Xin chào"),),
        "Xin chào. Tôi có thể hỗ trợ bạn.",
        "vi",
    ),
    (
        "combination:two_responses",
        (),
        "Câu trả lời một******Câu trả lời hai",
        "vi",
    ),
    (
        "language:response_language",
        (("response_language", "id"),),
        "Selamat pagi.",
        "ms",
    ),
)


def test_supported_rules_match_pinned_sea_helm_categories() -> None:
    tested_instruction_ids = {instruction_id for instruction_id, _, _, _ in _PASSING_CASES}

    assert tested_instruction_ids == SUPPORTED_INSTRUCTION_IDS
    assert len(_PASSING_CASES) == len(SUPPORTED_INSTRUCTION_IDS)


@pytest.mark.parametrize(
    (
        "instruction_id",
        "arguments",
        "response",
        "detected_language",
    ),
    _PASSING_CASES,
)
def test_dispatches_all_supported_rules(
    instruction_id: str,
    arguments: ArgumentPairs,
    response: str,
    detected_language: str,
) -> None:
    def detect_language(_: str) -> str:
        return detected_language

    result = grade_sea_ifeval_rule(
        response=response,
        source_language="vi",
        rule=_rule(
            instruction_id,
            arguments,
        ),
        language_detector=detect_language,
    )

    assert result.passed is True
    assert result.constraint_passed is True
    assert result.correct_language is True
    assert result.reason == "passed"
    assert result.grader_version == SEA_IFEVAL_GRADER_VERSION


@pytest.mark.parametrize(
    (
        "response",
        "detected_language",
        "constraint_passed",
        "correct_language",
        "reason",
    ),
    (
        (
            "<<Tiêu đề>>",
            "en",
            True,
            False,
            "wrong_language",
        ),
        (
            "Không có định dạng tiêu đề.",
            "vi",
            False,
            True,
            "constraint_failed",
        ),
        (
            "Không có định dạng tiêu đề.",
            "en",
            False,
            False,
            "constraint_and_language_failed",
        ),
    ),
)
def test_primary_result_requires_constraint_and_language(
    response: str,
    detected_language: str,
    constraint_passed: bool,
    correct_language: bool,
    reason: str,
) -> None:
    def detect_language(_: str) -> str:
        return detected_language

    result = grade_sea_ifeval_rule(
        response=response,
        source_language="vi",
        rule=_rule(
            "detectable_format:title",
        ),
        language_detector=detect_language,
    )

    assert result.passed is False
    assert result.constraint_passed is constraint_passed
    assert result.correct_language is correct_language
    assert result.reason == reason


def test_language_detector_is_called_once_with_newlines_removed() -> None:
    observed_texts: list[str] = []

    def detect_language(text: str) -> str:
        observed_texts.append(text)
        return "vi"

    result = grade_sea_ifeval_rule(
        response="<<Tiêu đề>>\nNội dung",
        source_language="vi",
        rule=_rule(
            "detectable_format:title",
        ),
        language_detector=detect_language,
    )

    assert result.passed is True
    assert observed_texts == [
        "<<Tiêu đề>> Nội dung",
    ]


@pytest.mark.parametrize(
    ("rule", "error_message"),
    (
        (
            _rule("unknown:rule"),
            "unsupported SEA-IFEval instruction ID",
        ),
        (
            _rule(
                "length_constraints:number_words",
                (("num_words", 3),),
            ),
            "missing=",
        ),
        (
            _rule(
                "detectable_format:title",
                (("unexpected", "value"),),
            ),
            "unexpected=",
        ),
        (
            _rule(
                "length_constraints:number_words",
                (
                    ("relation", "exactly"),
                    ("relation", "at least"),
                    ("num_words", 3),
                ),
            ),
            "duplicate instruction arguments",
        ),
        (
            _rule(
                "length_constraints:number_words",
                (
                    ("relation", "exactly"),
                    ("num_words", "3"),
                ),
            ),
            "must be an integer",
        ),
        (
            _rule(
                "length_constraints:number_words",
                (
                    ("relation", "approximately"),
                    ("num_words", 3),
                ),
            ),
            "unsupported relation",
        ),
        (
            _rule(
                "detectable_content:postscript",
                (("postscript_marker", "GHI CHÚ:"),),
            ),
            "unsupported Vietnamese postscript marker",
        ),
    ),
)
def test_rejects_invalid_rule_configuration(
    rule: InstructionRule,
    error_message: str,
) -> None:
    with pytest.raises(
        SeaIFEvalConfigurationError,
        match=error_message,
    ):
        grade_sea_ifeval_rule(
            response="Nội dung.",
            source_language="vi",
            rule=rule,
            language_detector=_detect_vietnamese,
        )


def test_rejects_unaudited_source_language() -> None:
    with pytest.raises(
        SeaIFEvalConfigurationError,
        match="only SEA-IFEval vi",
    ):
        grade_sea_ifeval_rule(
            response="A response.",
            source_language="en",
            rule=_rule(
                "detectable_format:title",
            ),
            language_detector=lambda _: "en",
        )


def test_rejects_invalid_language_detector_result() -> None:
    with pytest.raises(
        SeaIFEvalConfigurationError,
        match="language detector returned",
    ):
        grade_sea_ifeval_rule(
            response="<<Tiêu đề>>",
            source_language="vi",
            rule=_rule(
                "detectable_format:title",
            ),
            language_detector=lambda _: "   ",
        )
