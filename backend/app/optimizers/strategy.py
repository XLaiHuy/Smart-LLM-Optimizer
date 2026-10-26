"""Adaptive strategy selection and safe fallback."""

from dataclasses import dataclass
from enum import StrEnum

from .compressor import CompressionResult, compress_rule_based
from .prompt_analyzer import PromptAnalysis, analyze_prompt


class CompressionStrategy(StrEnum):
    NONE = "none"
    RULE_BASED = "rule_based"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    strategy: CompressionStrategy
    reason: str
    analysis: PromptAnalysis


class AdaptiveStrategySelector:
    def __init__(self, rule_threshold: int = 80, llm_threshold: int = 400) -> None:
        self.rule_threshold = rule_threshold
        self.llm_threshold = llm_threshold

    def select(self, prompt: str, llm_available: bool = False) -> StrategyDecision:
        analysis = analyze_prompt(prompt, self.rule_threshold)
        if not analysis.should_compress:
            return StrategyDecision(CompressionStrategy.NONE, "under_threshold", analysis)
        if llm_available and analysis.token_count >= self.llm_threshold:
            return StrategyDecision(CompressionStrategy.LLM, "long_prompt_llm_candidate", analysis)
        return StrategyDecision(CompressionStrategy.RULE_BASED, "deterministic_first", analysis)

    def compress(self, prompt: str, llm_compressor: object | None = None) -> CompressionResult:
        decision = self.select(prompt, llm_available=llm_compressor is not None)
        if decision.strategy != CompressionStrategy.LLM or llm_compressor is None:
            return compress_rule_based(prompt, self.rule_threshold)
        try:
            result = llm_compressor.compress(prompt)  # type: ignore[attr-defined]
            if result.preservation == "preserved" and result.compressed:
                return result
        except (AttributeError, TypeError, ValueError):
            pass
        return compress_rule_based(prompt, self.rule_threshold)
