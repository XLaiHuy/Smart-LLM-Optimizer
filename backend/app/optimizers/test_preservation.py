from typing import Literal

from app.optimizers.preservation import validate_preservation
from app.optimizers.prompt_analyzer import analyze_prompt


def check(
    original: str,
    compressed: str,
    strategy: Literal["rule_based", "llmlingua2"] = "llmlingua2",
) -> str:
    analysis = analyze_prompt(original)
    return validate_preservation(
        original,
        compressed,
        analysis.protected_spans,
        strategy=strategy,
    )


def test_identical_prompt() -> None:
    assert check("Explain AI.", "Explain AI.") == "preserved"


def test_negation_removed() -> None:
    assert (
        check(
            "Do not remove 95%.",
            "Remove 95%.",
        )
        == "violation"
    )


def test_number_removed() -> None:
    assert (
        check(
            "The cost is 150 USD.",
            "The cost is 150.",
        )
        == "violation"
    )


def test_url_removed() -> None:
    assert (
        check(
            "Visit https://example.com",
            "Visit the website",
        )
        == "violation"
    )


def test_empty_compressed() -> None:
    assert check("Explain AI.", "") == "violation"


def test_rule_based_preserved() -> None:
    assert (
        check(
            "Explain AI.   \n\n\nExplain ML.",
            "Explain AI.\n\nExplain ML.",
            strategy="rule_based",
        )
        == "preserved"
    )


def test_entity_survival_without_semantic_evidence_is_unknown() -> None:
    assert (
        check(
            "Explain artificial intelligence in detail.",
            "Explain artificial intelligence.",
        )
        == "unknown"
    )


def test_identifier_spacing_is_not_equivalent() -> None:
    assert check("Mã BLUE-851.", "Mã BLUE - 851.") == "violation"


def test_semantic_rejection_even_when_entities_survive() -> None:
    original = "Explain artificial intelligence in detail."
    spans = analyze_prompt(original).protected_spans
    for score in (None, float("nan"), 0.8):
        assert (
            validate_preservation(
                original, "Explain intelligence.", spans, semantic_similarity=score
            )
            == "unknown"
        )
