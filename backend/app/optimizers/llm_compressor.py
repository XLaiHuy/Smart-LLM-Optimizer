"""Optional LLM compressor adapter; callers own provider calls and budgets."""

from collections.abc import Awaitable
from typing import Protocol

from .compressor import CompressionResult
from .preservation import validate_preservation
from .prompt_analyzer import analyze_prompt
from .tokenization import token_stats


class LLMRewrite(Protocol):
    def __call__(self, prompt: str) -> Awaitable[str]: ...


class LLMCompressor:
    def __init__(self, rewrite: LLMRewrite) -> None:
        self.rewrite = rewrite

    async def compress(self, prompt: str) -> CompressionResult:
        analysis = analyze_prompt(prompt, compression_threshold=0)
        candidate = await self.rewrite(prompt)
        verdict = validate_preservation(prompt, candidate, analysis.protected_spans)
        if verdict != "preserved":
            candidate, status, reason = prompt, "skipped", f"preservation_{verdict}"
        else:
            status = "applied" if candidate != prompt else "skipped"
            reason = "llm_rewrite" if candidate != prompt else "no_change"
        stats = token_stats(prompt, candidate)
        return CompressionResult(
            original=prompt, compressed=candidate, original_tokens=stats.before,
            compressed_tokens=stats.after, savings=stats.savings, ratio=stats.ratio,
            status=status, reason=reason,
        )
