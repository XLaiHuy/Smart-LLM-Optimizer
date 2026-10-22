"""Prompt optimization orchestration without provider/database side effects."""

import asyncio
from collections.abc import Mapping
from typing import Protocol

from app.contracts.dtos import (
    ContextResult,
    ExecutionRequest,
    FeatureFlags,
    OptimizationState,
    OptimizedPrompt,
)
from app.core.policy import noop_state
from app.optimizers.compressor import compress_rule_based
from app.optimizers.prompt_analyzer import analyze_prompt
from app.optimizers.strategy_selector import select_strategy


class PromptCompressorPort(Protocol):
    def compress(self, prompt: str) -> Mapping[str, object]: ...


class NoOpPromptOptimizer:
    async def optimize(
        self, req: ExecutionRequest, context: ContextResult, flags: FeatureFlags
    ) -> OptimizedPrompt:
        return OptimizedPrompt(
            original=req.request.message,
            proposed=req.request.message,
            state=noop_state("rewrite", flags.rewrite),
        )


class AdaptivePromptOptimizer:
    """Select skip/rule/LLMLingua and always return a safe typed result."""

    def __init__(
        self,
        llm_compressor: PromptCompressorPort | None = None,
        min_compress_tokens: int = 100,
        llm_threshold: int = 500,
    ) -> None:
        if min_compress_tokens < 0:
            raise ValueError("min_compress_tokens must be non-negative")
        if llm_threshold < min_compress_tokens:
            raise ValueError("llm_threshold must be >= min_compress_tokens")
        self.llm_compressor = llm_compressor
        self.min_compress_tokens = min_compress_tokens
        self.llm_threshold = llm_threshold

    async def optimize(
        self, req: ExecutionRequest, context: ContextResult, flags: FeatureFlags
    ) -> OptimizedPrompt:
        del context
        original = req.request.message
        if not flags.rewrite:
            return self._result(original, "disabled", "feature_disabled")

        analysis = analyze_prompt(original, compression_threshold=0)
        strategy = select_strategy(
            analysis,
            model_available=self.llm_compressor is not None,
            min_compress_tokens=self.min_compress_tokens,
            llm_threshold=self.llm_threshold,
        )

        if strategy == "skip":
            return self._result(original, "skipped", "under_threshold")

        if strategy == "rule_based":
            result = compress_rule_based(original, self.min_compress_tokens)
            applied = result.status == "applied"
            return self._result(
                original,
                "applied" if applied else "skipped",
                result.reason,
                proposed=result.compressed if applied else original,
                before_tokens=result.original_tokens,
                after_tokens=result.compressed_tokens,
            )

        if self.llm_compressor is None:
            return self._result(original, "skipped", "llm_compressor_unavailable", "unknown")

        raw_result = await asyncio.to_thread(self.llm_compressor.compress, original)
        proposed = raw_result.get("compressed")
        status = raw_result.get("status")
        preservation = raw_result.get("preservation", "unknown")
        if not isinstance(proposed, str) or status != "applied" or preservation != "preserved":
            validation = (
                preservation if preservation in {"preserved", "violation", "unknown"} else "unknown"
            )
            return self._result(original, "skipped", f"llmlingua_{validation}", validation)

        before = raw_result.get("original_tokens")
        after = raw_result.get("compressed_tokens")
        return self._result(
            original,
            "applied",
            "llmlingua2",
            proposed=proposed,
            before_tokens=before if isinstance(before, int) else None,
            after_tokens=after if isinstance(after, int) else None,
        )

    @staticmethod
    def _result(
        original: str,
        status: str,
        reason: str,
        validation: str = "preserved",
        *,
        proposed: str | None = None,
        before_tokens: int | None = None,
        after_tokens: int | None = None,
    ) -> OptimizedPrompt:
        return OptimizedPrompt(
            original=original,
            proposed=proposed if proposed is not None else original,
            validation=validation,  # type: ignore[arg-type]
            state=OptimizationState(
                module="rewrite",
                status=status,  # type: ignore[arg-type]
                reason=reason,
                before_tokens=before_tokens,
                after_tokens=after_tokens,
            ),
        )
