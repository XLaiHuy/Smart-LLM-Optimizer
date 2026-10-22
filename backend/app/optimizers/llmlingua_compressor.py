from importlib import import_module
from typing import Any

import tiktoken

from app.optimizers.preservation import validate_preservation
from app.optimizers.prompt_analyzer import analyze_prompt

PromptCompressor: Any = import_module("llmlingua").PromptCompressor


class LLMLinguaCompressor:
    def __init__(self) -> None:
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.compressor = PromptCompressor(
            model_name=("microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"),
            device_map="cpu",
            use_llmlingua2=True,
        )

    def compress(
        self,
        prompt: str,
        rate: float = 0.7,
    ) -> dict[str, Any]:
        original_tokens = len(self.encoding.encode(prompt))
        result = self.compressor.compress_prompt(
            prompt,
            rate=rate,
            force_tokens=["\n", "?"],
        )

        compressed = result["compressed_prompt"]
        compressed_tokens = len(self.encoding.encode(compressed))
        analysis = analyze_prompt(prompt, compression_threshold=0)
        preservation = validate_preservation(
            prompt,
            compressed,
            analysis.protected_spans,
            strategy="llmlingua2",
        )

        return {
            "original": prompt,
            "compressed": compressed,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "savings": original_tokens - compressed_tokens,
            "ratio": compressed_tokens / original_tokens if original_tokens else 1.0,
            "status": "applied" if compressed != prompt else "skipped",
            "preservation": preservation,
        }
