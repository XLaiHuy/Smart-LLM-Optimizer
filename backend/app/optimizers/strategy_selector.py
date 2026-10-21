from typing import Literal
from app.optimizers.prompt_analyzer import PromptAnalyzer
Strategy = Literal[
    "skip",
    "rule_based",
    "llmlingua2",
]

def select_strategy(
    analysis: PromptAnalyzer,
    model_available: bool = True,
    min_compress_tokens: int = 100,
    llm_threshold: int = 500,
) -> Strategy:
    if analysis.token_count < min_compress_tokens:
        return "skip"
    if analysis.has_code or analysis.has_json:
        return "rule_based"
    if not model_available:
        return "rule_based"
    if analysis.token_count >= llm_threshold:
        return "llmlingua2"
    return "rule_based"