import re
from importlib import import_module
from threading import Lock
from typing import Any

import tiktoken

from app.optimizers.preservation import validate_preservation
from app.optimizers.prompt_analyzer import analyze_prompt

PromptCompressor: Any = import_module("llmlingua").PromptCompressor


class LLMLinguaCompressor:
    def __init__(self) -> None:
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.compressor: Any | None = None
        self.max_input_tokens = 496
        self._load_lock = Lock()

    def _ensure_compressor(self) -> Any:
        if self.compressor is not None:
            return self.compressor
        with self._load_lock:
            if self.compressor is None:
                self.compressor = PromptCompressor(
                    model_name=("microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"),
                    device_map="cpu",
                    use_llmlingua2=True,
                )
                model_limit = getattr(self.compressor.tokenizer, "model_max_length", 512)
                self.max_input_tokens = max(1, int(model_limit) - 16)
        return self.compressor

    def _model_token_count(self, text: str) -> int:
        compressor = self._ensure_compressor()
        return len(compressor.tokenizer.encode(text, add_special_tokens=False))

    def _split_for_model(self, prompt: str) -> tuple[str, ...] | None:
        """Keep paragraph separators and avoid sending more than one model window."""
        parts = re.split(r"(\n{2,})", prompt)
        chunks: list[str] = []
        for part in parts:
            if not part:
                continue
            if part.isspace():
                chunks.append(part)
                continue
            if self._model_token_count(part) > self.max_input_tokens:
                return None
            chunks.append(part)
        return tuple(chunks)

    def compress(
        self,
        prompt: str,
        rate: float = 0.7,
    ) -> dict[str, Any]:
        original_tokens = len(self.encoding.encode(prompt))
        compressor = self._ensure_compressor()
        chunks = self._split_for_model(prompt)
        if chunks is None:
            return {
                "original": prompt,
                "compressed": prompt,
                "original_tokens": original_tokens,
                "compressed_tokens": original_tokens,
                "savings": 0,
                "ratio": 1.0,
                "status": "skipped",
                "preservation": "unknown",
                "reason": "paragraph_exceeds_llmlingua_limit",
            }

        compressed_parts: list[str] = []
        analysis = analyze_prompt(prompt, compression_threshold=0)
        # Ask LLMLingua to retain safety-critical literals where possible;
        # validate_preservation below remains the final fail-safe check.
        protected_tokens = list(dict.fromkeys(
            span.text for span in analysis.protected_spans if span.text.strip()
        ))
        force_tokens = list(dict.fromkeys(["\n", "?", *protected_tokens]))
        for chunk in chunks:
            if chunk.isspace():
                compressed_parts.append(chunk)
                continue
            result = compressor.compress_prompt(
                chunk,
                rate=rate,
                force_tokens=force_tokens,
            )
            compressed_parts.append(result["compressed_prompt"])

        compressed = "".join(compressed_parts)
        compressed_tokens = len(self.encoding.encode(compressed))
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
