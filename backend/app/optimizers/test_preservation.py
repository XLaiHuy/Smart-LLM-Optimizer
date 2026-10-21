from app.optimizers.prompt_analyzer import analyze_prompt
from app.optimizers.preservation import validate_preservation

def check(original, compressed, strategy="llmlingua2"):
    analysis = analyze_prompt(original)
    return validate_preservation(
        original,
        compressed,
        analysis.protected_spans,
        strategy=strategy,
    )


def test_identical_prompt():
    assert check("Explain AI.", "Explain AI.") == "preserved"


def test_negation_removed():
    assert check(
        "Do not remove 95%.",
        "Remove 95%.",
    ) == "violation"


def test_number_removed():
    assert check(
        "The cost is 150 USD.",
        "The cost is 150.",
    ) == "violation"


def test_url_removed():
    assert check(
        "Visit https://example.com",
        "Visit the website",
    ) == "violation"


def test_empty_compressed():
    assert check("Explain AI.", "") == "violation"


def test_rule_based_preserved():
    assert check(
        "Explain AI.   \n\n\nExplain ML.",
        "Explain AI.\n\nExplain ML.",
        strategy="rule_based",
    ) == "preserved"


def test_llmlingua_unknown():
    assert check(
        "Explain artificial intelligence in detail.",
        "Explain artificial intelligence.",
    ) == "unknown"