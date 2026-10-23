from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast

from app.evaluation._vendor.sea_helm_v1_3_0.instruction_checkers import (
    BulletListChecker,
    ConstrainedOptionsChecker,
    EndChecker,
    HighlightedSectionChecker,
    JSONChecker,
    NumberFrequencyChecker,
    NumberOfParagraphsChecker,
    NumberOfSentencesChecker,
    NumberOfWordsChecker,
    PlaceholderChecker,
    PostscriptChecker,
    QuotationMarkChecker,
    RepeatPromptChecker,
    ResponseLanguageChecker,
    SectionChecker,
    StartChecker,
    TitleChecker,
    TwoResponsesChecker,
    WordAbsenceChecker,
    WordExistenceChecker,
    WordFrequencyChecker,
)
from app.evaluation.cases import InstructionRule

SEA_IFEVAL_GRADER_VERSION: Final = "sea-ifeval-v1.1+sea-helm-v1.3.0@9be3986d"

LanguageDetector = Callable[[str], str]

ArgumentKind = Literal[
    "integer",
    "relation",
    "string",
    "string_tuple",
]

SeaIFEvalReason = Literal[
    "passed",
    "constraint_failed",
    "wrong_language",
    "constraint_and_language_failed",
]

CheckerFactory = Callable[..., object]


class CheckerProtocol(Protocol):
    def evaluate_response(self) -> bool: ...


class SeaIFEvalConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SeaIFEvalRuleGrade:
    instruction_id: str
    passed: bool
    constraint_passed: bool
    correct_language: bool
    expected_language: str
    detected_language: str
    reason: SeaIFEvalReason
    grader_version: str = SEA_IFEVAL_GRADER_VERSION


_CHECKER_FACTORIES: Final[dict[str, CheckerFactory]] = {
    "length_constraints:number_words": NumberOfWordsChecker,
    "length_constraints:number_sentences": NumberOfSentencesChecker,
    "length_constraints:number_paragraphs": NumberOfParagraphsChecker,
    "detectable_content:postscript": PostscriptChecker,
    "detectable_content:number_placeholders": PlaceholderChecker,
    "detectable_format:title": TitleChecker,
    "detectable_format:number_bullet_lists": BulletListChecker,
    "detectable_format:multiple_sections": SectionChecker,
    "detectable_format:number_highlighted_sections": (HighlightedSectionChecker),
    "detectable_format:json_format": JSONChecker,
    "detectable_format:constrained_response": (ConstrainedOptionsChecker),
    "startend:first_word": StartChecker,
    "startend:end_checker": EndChecker,
    "startend:quotation": QuotationMarkChecker,
    "keywords:existence": WordExistenceChecker,
    "keywords:forbidden_words": WordAbsenceChecker,
    "keywords:frequency": WordFrequencyChecker,
    "keywords:number_frequency": NumberFrequencyChecker,
    "combination:repeat_prompt": RepeatPromptChecker,
    "combination:two_responses": TwoResponsesChecker,
    "language:response_language": ResponseLanguageChecker,
}

_ARGUMENT_KINDS: Final[dict[str, dict[str, ArgumentKind]]] = {
    "length_constraints:number_words": {
        "relation": "relation",
        "num_words": "integer",
    },
    "length_constraints:number_sentences": {
        "relation": "relation",
        "num_sentences": "integer",
    },
    "length_constraints:number_paragraphs": {
        "num_paragraphs": "integer",
    },
    "detectable_content:postscript": {
        "postscript_marker": "string",
    },
    "detectable_content:number_placeholders": {
        "num_placeholders": "integer",
    },
    "detectable_format:title": {},
    "detectable_format:number_bullet_lists": {
        "num_bullets": "integer",
    },
    "detectable_format:multiple_sections": {
        "section_title": "string",
        "num_sections": "integer",
    },
    "detectable_format:number_highlighted_sections": {
        "num_highlights": "integer",
    },
    "detectable_format:json_format": {},
    "detectable_format:constrained_response": {},
    "startend:first_word": {
        "first_word": "string",
    },
    "startend:end_checker": {
        "end_phrase": "string",
    },
    "startend:quotation": {},
    "keywords:existence": {
        "keywords": "string_tuple",
    },
    "keywords:forbidden_words": {
        "forbidden_words": "string_tuple",
    },
    "keywords:frequency": {
        "keyword": "string",
        "relation": "relation",
        "frequency": "integer",
    },
    "keywords:number_frequency": {
        "number": "string",
        "relation": "relation",
        "frequency": "integer",
    },
    "combination:repeat_prompt": {
        "prompt_to_repeat": "string",
    },
    "combination:two_responses": {},
    "language:response_language": {
        "response_language": "string",
    },
}

SUPPORTED_INSTRUCTION_IDS: Final[frozenset[str]] = frozenset(_CHECKER_FACTORIES)

_COMPARISON_RELATIONS: Final = {
    "exactly",
    "at least",
    "less than",
}


def _validate_argument_value(
    *,
    name: str,
    value: object,
    kind: ArgumentKind,
) -> None:
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SeaIFEvalConfigurationError(f"argument {name!r} must be an integer")

        if value < 0:
            raise SeaIFEvalConfigurationError(f"argument {name!r} must be non-negative")
        return

    if kind in {"string", "relation"}:
        if not isinstance(value, str) or not value.strip():
            raise SeaIFEvalConfigurationError(f"argument {name!r} must be a non-blank string")

        if kind == "relation" and value not in _COMPARISON_RELATIONS:
            raise SeaIFEvalConfigurationError(
                f"argument {name!r} has unsupported relation {value!r}"
            )
        return

    if (
        not isinstance(value, tuple)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise SeaIFEvalConfigurationError(f"argument {name!r} must be a non-empty tuple of strings")


def _prepare_arguments(
    rule: InstructionRule,
) -> dict[str, object]:
    argument_names = tuple(argument.name for argument in rule.kwargs)
    duplicates = tuple(sorted(name for name, count in Counter(argument_names).items() if count > 1))

    if duplicates:
        raise SeaIFEvalConfigurationError(f"duplicate instruction arguments: {duplicates}")

    argument_kinds = _ARGUMENT_KINDS.get(rule.instruction_id)
    if argument_kinds is None:
        raise SeaIFEvalConfigurationError(
            f"unsupported SEA-IFEval instruction ID: {rule.instruction_id!r}"
        )

    actual_names = set(argument_names)
    expected_names = set(argument_kinds)
    missing = tuple(sorted(expected_names - actual_names))
    unexpected = tuple(sorted(actual_names - expected_names))

    if missing or unexpected:
        raise SeaIFEvalConfigurationError(
            "invalid instruction arguments for "
            f"{rule.instruction_id!r}: "
            f"missing={missing}, unexpected={unexpected}"
        )

    values: dict[str, object] = {}

    for argument in rule.kwargs:
        _validate_argument_value(
            name=argument.name,
            value=argument.value,
            kind=argument_kinds[argument.name],
        )
        values[argument.name] = argument.value

    if rule.instruction_id == "detectable_content:postscript" and values[
        "postscript_marker"
    ] not in {"P.S.", "P.P.S."}:
        raise SeaIFEvalConfigurationError("unsupported Vietnamese postscript marker")

    return values


def _language_matches(
    *,
    expected: str,
    detected: str,
) -> bool:
    if expected in {"id", "ms"}:
        return detected in {"id", "ms"}

    return detected == expected


def _reason_for_result(
    *,
    constraint_passed: bool,
    correct_language: bool,
) -> SeaIFEvalReason:
    if constraint_passed and correct_language:
        return "passed"

    if not constraint_passed and not correct_language:
        return "constraint_and_language_failed"

    if not constraint_passed:
        return "constraint_failed"

    return "wrong_language"


def grade_sea_ifeval_rule(
    *,
    response: str,
    source_language: str,
    rule: InstructionRule,
    language_detector: LanguageDetector,
) -> SeaIFEvalRuleGrade:
    if source_language != "vi":
        raise SeaIFEvalConfigurationError("this adapter currently supports only SEA-IFEval vi")

    checker_factory = _CHECKER_FACTORIES.get(rule.instruction_id)
    if checker_factory is None:
        raise SeaIFEvalConfigurationError(
            f"unsupported SEA-IFEval instruction ID: {rule.instruction_id!r}"
        )

    checker_arguments = _prepare_arguments(rule)
    detected_language: str | None = None

    def detect_once(text: str) -> str:
        nonlocal detected_language

        if detected_language is None:
            candidate = language_detector(text)

            if not isinstance(candidate, str) or not candidate.strip():
                raise SeaIFEvalConfigurationError("language detector returned an invalid language")

            detected_language = candidate.strip()

        return detected_language

    if rule.instruction_id == "language:response_language":
        checker_arguments["language_detector"] = detect_once

    checker = cast(
        CheckerProtocol,
        checker_factory(
            category=rule.instruction_id,
            language=source_language,
            response=response,
            **checker_arguments,
        ),
    )

    constraint_passed = checker.evaluate_response()
    detected = detect_once(response.replace("\n", " "))

    expected_language = source_language
    if rule.instruction_id == "language:response_language":
        expected_language = cast(
            str,
            checker_arguments["response_language"],
        )

    correct_language = _language_matches(
        expected=expected_language,
        detected=detected,
    )
    passed = constraint_passed and correct_language

    return SeaIFEvalRuleGrade(
        instruction_id=rule.instruction_id,
        passed=passed,
        constraint_passed=constraint_passed,
        correct_language=correct_language,
        expected_language=expected_language,
        detected_language=detected,
        reason=_reason_for_result(
            constraint_passed=constraint_passed,
            correct_language=correct_language,
        ),
    )
