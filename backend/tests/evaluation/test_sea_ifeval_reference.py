from app.evaluation._vendor.sea_helm_v1_3_0.instruction_checkers import (
    NumberOfSentencesChecker,
    NumberOfWordsChecker,
    ResponseLanguageChecker,
)


def test_vietnamese_word_count_uses_unicode_word_units() -> None:
    checker = NumberOfWordsChecker(
        category="length_constraints:number_words",
        language="vi",
        response="một-hai ba",
        relation="exactly",
        num_words=3,
    )

    assert checker.evaluate_response() is True  # type: ignore[no-untyped-call]


def test_sentence_count_uses_triple_asterisk_separator() -> None:
    checker = NumberOfSentencesChecker(
        category=("length_constraints:number_sentences"),
        language="vi",
        response="Câu thứ nhất.***Câu thứ hai!",
        relation="exactly",
        num_sentences=2,
    )

    assert checker.evaluate_response() is True  # type: ignore[no-untyped-call]


def test_response_language_uses_injected_detector() -> None:
    observed_texts: list[str] = []

    def detect_language(text: str) -> str:
        observed_texts.append(text)
        return "vi"

    checker = ResponseLanguageChecker(
        category="language:response_language",
        language="vi",
        response="Xin\nchào Việt Nam.",
        response_language="vi",
        language_detector=detect_language,
    )

    assert checker.evaluate_response() is True  # type: ignore[no-untyped-call]
    assert observed_texts == [
        "Xin chào Việt Nam.",
    ]


def test_indonesian_accepts_malay_detection() -> None:
    def detect_language(_: str) -> str:
        return "ms"

    checker = ResponseLanguageChecker(
        category="language:response_language",
        language="vi",
        response="Selamat pagi.",
        response_language="id",
        language_detector=detect_language,
    )

    assert checker.evaluate_response() is True  # type: ignore[no-untyped-call]
