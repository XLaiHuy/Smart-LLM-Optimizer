from dataclasses import dataclass
import re
import tiktoken
from app.optimizers.prompt_analyzer import ProtectedSpan
from app.optimizers.prompt_analyzer import analyze_prompt
from collections import Counter
_ENCODING = tiktoken.get_encoding("cl100k_base")

def normalize_whitespace(prompt: str) -> str:
    parts = re.split(r"(```.*?```)", prompt, flags=re.DOTALL)
    result: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 0:
            part = re.sub(r"[ \t]+$", "", part, flags=re.MULTILINE)
            part = re.sub(r"\n{3,}", "\n\n", part)
        result.append(part)
    return "".join(result)

def preserves_protected_spans(
    compressed: str,
    protected_spans: tuple[ProtectedSpan, ...],
) -> bool:
    required = Counter(span.text for span in protected_spans)
    return all(
        compressed.count(text) >= count
        for text, count in required.items()
    )
@dataclass(frozen=True)
class CompressionResult:
    original: str
    compressed: str
    original_tokens: int
    compressed_tokens: int
    savings: int
    ratio: float
    status: str
    reason: str

def compress_rule_based(
        prompt: str,
        compression_threshold: int = 100,
) -> CompressionResult:
    analysis = analyze_prompt(prompt, compression_threshold)
    original_tokens = len(_ENCODING.encode(prompt))
    if not analysis.should_compress:
        return CompressionResult(
            original=prompt,
            compressed=prompt,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            savings=0,
            ratio=1.0,
            status="skipped",
            reason="Prompt is already below the compression threshold.",
        )
    candidate = normalize_whitespace(prompt)
    if not preserves_protected_spans(
        candidate,
        analysis.protected_spans,
    ):
        return CompressionResult(
            original=prompt,
            compressed=prompt,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            savings=0,
            ratio=1.0,
            status="skipped",
            reason="protected_span_lost.",
        )
    compressed_tokens = len(_ENCODING.encode(candidate))
    savings = original_tokens - compressed_tokens
    if savings <= 0:
        return CompressionResult(
            original=prompt,
            compressed=prompt,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            savings=savings,
            ratio=1.0,
            status="skipped",
            reason="no_token_savings",
        )
    return CompressionResult(
        original=prompt,
        compressed=candidate,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        savings=savings,
        ratio=compressed_tokens / original_tokens,
        status="applied",
        reason="whitespace_normalization",
    )