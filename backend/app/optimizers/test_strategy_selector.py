import pytest
from app.optimizers.prompt_analyzer import analyze_prompt
from app.optimizers.strategy_selector import select_strategy


def select(prompt, model_available=True):
    analysis = analyze_prompt(prompt)

    return select_strategy(
        analysis,
        model_available=model_available,
        min_compress_tokens=10,
        llm_threshold=30,
    )
def test_skip_short_prompt():
    assert select("Hello") == "skip"


def test_rule_based_medium_prompt():
    prompt = "Explain machine learning. " * 5
    assert select(prompt) == "rule_based"


def test_llmlingua_long_prompt():
    prompt = "Explain machine learning in detail. " * 30
    assert select(prompt) == "llmlingua2"


def test_model_unavailable():
    prompt = "Explain machine learning in detail. " * 30
    assert select(prompt, model_available=False) == "rule_based"


def test_code_uses_rule_based():
    prompt = (
        "Explain the following code:\n"
        "```python\nprint('hello')\n```\n"
        + "Explain its behavior. " * 20
    )
    assert select(prompt) == "rule_based"


def test_invalid_threshold():
    analysis = analyze_prompt("Hello world")

    with pytest.raises(ValueError):
        select_strategy(
            analysis,
            min_compress_tokens=100,
            llm_threshold=50,
        )