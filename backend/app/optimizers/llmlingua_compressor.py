import logging
import re
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from threading import Lock
from typing import Any

import tiktoken

from app.optimizers.preservation import validate_preservation
from app.optimizers.prompt_analyzer import analyze_prompt


class LLMLinguaCompressor:
    def __init__(
        self, semantic_similarity: Callable[[str, str], float | None] | None = None
    ) -> None:
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.compressor: Any | None = None
        self.max_input_tokens = 496
        self._load_lock = Lock()
        self.semantic_similarity = semantic_similarity

    def warmup(self) -> bool:
        try:
            model = self._ensure_compressor()
            # Exercise inference kernels/tokenizer before accepting chat traffic.
            model.compress_prompt("General background information.", rate=0.7)
            return True
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Compressor warmup unavailable: %s", type(exc).__name__
            )
            return False

    def _ensure_compressor(self) -> Any:
        if self.compressor is not None:
            return self.compressor
        with self._load_lock:
            if self.compressor is None:
                from huggingface_hub import snapshot_download

                # Model preparation is an operator step, never a chat download.
                local_model = snapshot_download(
                    "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
                    revision="5f0c82792b7ea14c6484e015b6a072009496b7f2",
                    local_files_only=True,
                )
                if (
                    not any(Path(local_model).glob("*.safetensors"))
                    and not (Path(local_model) / "pytorch_model.bin").exists()
                ):
                    raise FileNotFoundError("LLMLingua weights must be prepared before serving")
                PromptCompressor = import_module("llmlingua").PromptCompressor
                self.compressor = PromptCompressor(
                    model_name=local_model,
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
        protected_tokens = list(
            dict.fromkeys(span.text for span in analysis.protected_spans if span.text.strip())
        )
        force_tokens = list(dict.fromkeys(["\n", "?", *protected_tokens]))
        # Repeated paragraphs reuse inference only; preserve every occurrence,
        # separator and order in the final prompt. Never deduplicate user facts.
        content_indexes = [i for i, chunk in enumerate(chunks) if not chunk.isspace()]
        if not content_indexes:
            return {
                "compressed": prompt,
                "status": "skipped",
                "preservation": "unknown",
                "reason": "empty_input",
            }
        last_content = content_indexes[-1]
        mutable = {
            chunk
            for i, chunk in enumerate(chunks)
            if not chunk.isspace()
            and i != last_content
            and not analyze_prompt(chunk, compression_threshold=0).protected_spans
            and not re.search(
                r"\?|\b(?:chỉ|hãy|phải|chọn|trước|sau|only|must|choose|before|after)\b",
                chunk,
                re.IGNORECASE,
            )
        }
        if sum(self._model_token_count(chunk) for chunk in mutable) > 512:
            return {
                "compressed": prompt,
                "status": "skipped",
                "preservation": "unknown",
                "reason": "compression_work_budget",
            }
        memo: dict[str, str] = {}
        minimum_similarity = 1.0
        for index, chunk in enumerate(chunks):
            if chunk.isspace():
                compressed_parts.append(chunk)
                continue
            if index == last_content or chunk not in mutable:
                compressed_parts.append(chunk)
                continue
            if chunk in memo:
                compressed_parts.append(memo[chunk])
                continue
            result = compressor.compress_prompt(
                chunk,
                rate=rate,
                force_tokens=force_tokens,
            )
            candidate = result["compressed_prompt"]
            # Unknown scope or unresolved meaning keeps this paragraph verbatim.
            score = self.semantic_similarity(chunk, candidate) if self.semantic_similarity else None
            if (
                validate_preservation(
                    chunk,
                    candidate,
                    analyze_prompt(chunk, compression_threshold=0).protected_spans,
                    semantic_similarity=score,
                )
                != "preserved"
            ):
                candidate = chunk
            elif score is not None:
                minimum_similarity = min(minimum_similarity, score)
            memo[chunk] = candidate
            compressed_parts.append(candidate)

        compressed = "".join(compressed_parts)
        compressed_tokens = len(self.encoding.encode(compressed))
        preservation = validate_preservation(
            prompt,
            compressed,
            analysis.protected_spans,
            strategy="llmlingua2",
            semantic_similarity=minimum_similarity,
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
            "minimum_paragraph_similarity": minimum_similarity,
            "unique_inferences": len(memo),
        }
