"""Prompt optimization orchestration without provider/database side effects."""

import asyncio
from collections.abc import Mapping
from typing import Protocol

from app.contracts.dtos import (
    ContextResult,
    ExecutionRequest,
    FeatureFlags,
    Message,
    OptimizationState,
    OptimizedPrompt,
)
from app.core.policy import noop_state
from app.optimizers.compressor import compress_rule_based
from app.optimizers.prompt_analyzer import analyze_prompt
from app.optimizers.strategy_selector import select_strategy


class PromptCompressorPort(Protocol):
    """Interface for an LLM-based prompt compressor."""

    def compress(self, prompt: str) -> Mapping[str, object]: ...


class NoOpPromptOptimizer:
    """Return the original prompt when optimization is disabled or for testing."""

    async def optimize(
        self,
        req: ExecutionRequest,
        context: ContextResult,
        flags: FeatureFlags,
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
        min_compress_tokens: int = 300,
        llm_threshold: int = 1000,
        compression_timeout_seconds: float = 2.0,
        min_rule_savings_tokens: int = 16,
        min_rule_savings_ratio: float = 0.05,
    ) -> None:
        if min_compress_tokens < 0:
            raise ValueError("min_compress_tokens must be non-negative")

        if llm_threshold < min_compress_tokens:
            raise ValueError("llm_threshold must be >= min_compress_tokens")

        if compression_timeout_seconds <= 0:
            raise ValueError("compression_timeout_seconds must be positive")

        if min_rule_savings_tokens < 0:
            raise ValueError("min_rule_savings_tokens must be non-negative")

        if not 0 <= min_rule_savings_ratio <= 1:
            raise ValueError("min_rule_savings_ratio must be between 0 and 1")

        self.llm_compressor = llm_compressor
        self.min_compress_tokens = min_compress_tokens
        self.llm_threshold = llm_threshold
        self.compression_timeout_seconds = compression_timeout_seconds
        self.min_rule_savings_tokens = min_rule_savings_tokens
        self.min_rule_savings_ratio = min_rule_savings_ratio
        self._compression_slot = asyncio.Semaphore(1)

    async def optimize(
        self,
        req: ExecutionRequest,
        context: ContextResult,
        flags: FeatureFlags,
    ) -> OptimizedPrompt:
        original = req.request.message

        if not flags.rewrite:
            return self._result(original, "disabled", "feature_disabled")

        # Compress prepared context messages instead of only the current user
        # prompt. System/developer messages remain untouched.
        messages = getattr(context, "messages", ()) or (
            Message(role="user", content=original),
        )

        rewritten: list[Message] = []
        total_before = 0
        total_after = 0
        applied_any = False
        reasons: list[str] = []
        validation = "preserved"

        for message in messages:
            if message.role in {"system", "developer"}:
                rewritten.append(message)
                continue

            result = await self._optimize_text(message.content, flags)

            rewritten.append(
                message.model_copy(update={"content": result.proposed})
            )

            if result.state.before_tokens is not None:
                total_before += result.state.before_tokens

            if result.state.after_tokens is not None:
                total_after += result.state.after_tokens

            if result.state.status == "applied":
                applied_any = True

            if result.state.reason:
                reasons.append(result.state.reason)

            if result.validation != "preserved":
                validation = result.validation

        current = next(
            (
                message.content
                for message in reversed(rewritten)
                if message.role == "user"
            ),
            original,
        )

        if applied_any:
            state_status = "applied"
            state_reason = "context_messages_compressed"
        else:
            state_status = "skipped"
            state_reason = next(
                (
                    reason
                    for reason in reasons
                    if reason != "under_threshold"
                ),
                "under_threshold",
            )

        return self._result(
            original,
            state_status,
            state_reason,
            validation,
            proposed=current,
            before_tokens=total_before or None,
            after_tokens=total_after or None,
            messages=tuple(rewritten),
        )

    async def _optimize_text(
        self,
        original: str,
        flags: FeatureFlags,
    ) -> OptimizedPrompt:
        """Optimize one message using the existing bounded strategy."""

        analysis = analyze_prompt(
            original,
            compression_threshold=0,
        )

        strategy = select_strategy(
            analysis,
            model_available=self.llm_compressor is not None,
            min_compress_tokens=self.min_compress_tokens,
            llm_threshold=self.llm_threshold,
        )

        if strategy == "skip":
            return self._result(original, "skipped", "under_threshold")

        if strategy == "rule_based":
            result = compress_rule_based(
                original,
                self.min_compress_tokens,
            )

            savings_ratio = (
                result.savings / result.original_tokens
                if result.original_tokens > 0
                else 0.0
            )

            meaningful_savings = (
                result.savings >= self.min_rule_savings_tokens
                and savings_ratio >= self.min_rule_savings_ratio
            )

            applied = result.status == "applied" and meaningful_savings

            return self._result(
                original,
                "applied" if applied else "skipped",
                result.reason if applied else "insufficient_token_savings",
                proposed=result.compressed if applied else original,
                before_tokens=result.original_tokens,
                after_tokens=result.compressed_tokens,
            )

        if self.llm_compressor is None:
            return self._result(
                original,
                "skipped",
                "llm_compressor_unavailable",
                "unknown",
            )

        if self._compression_slot.locked():
            return self._result(
                original,
                "skipped",
                "llmlingua_busy",
                "unknown",
            )

        await self._compression_slot.acquire()

        # Cancelling to_thread does not stop CPU/model loading.
        # Keep the slot until the background worker actually finishes.
        worker = asyncio.create_task(
            asyncio.to_thread(self.llm_compressor.compress, original)
        )

        def completed(task: asyncio.Task[Mapping[str, object]]) -> None:
            self._compression_slot.release()

            if not task.cancelled():
                task.exception()

        worker.add_done_callback(completed)

        try:
            raw_result = await asyncio.wait_for(
                asyncio.shield(worker),
                timeout=self.compression_timeout_seconds,
            )
        except TimeoutError:
            return self._result(
                original,
                "skipped",
                "llmlingua_timeout",
                "unknown",
            )
        except Exception:
            return self._result(
                original,
                "skipped",
                "llmlingua_error",
                "unknown",
            )

        proposed = raw_result.get("compressed")
        status = raw_result.get("status")
        preservation = raw_result.get("preservation", "unknown")

        if (
            not isinstance(proposed, str)
            or status != "applied"
            or preservation != "preserved"
        ):
            validation = (
                preservation
                if preservation in {"preserved", "violation", "unknown"}
                else "unknown"
            )

            reason = raw_result.get("reason")
            if not isinstance(reason, str):
                reason = f"llmlingua_{validation}"

            return self._result(
                original,
                "skipped",
                reason,
                validation,
            )

        before = raw_result.get("original_tokens")
        after = raw_result.get("compressed_tokens")

        if (
            not isinstance(before, int)
            or not isinstance(after, int)
            or after >= before
        ):
            return self._result(
                original,
                "skipped",
                "llmlingua_no_token_savings",
                "preserved",
                before_tokens=before if isinstance(before, int) else None,
                after_tokens=after if isinstance(after, int) else None,
            )

        return self._result(
            original,
            "applied",
            "llmlingua2",
            proposed=proposed,
            before_tokens=before,
            after_tokens=after,
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
        messages: tuple[Message, ...] | None = None,
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
            messages=messages,
        )