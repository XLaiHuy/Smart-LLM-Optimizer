import math
import re
from collections import Counter
from typing import Literal

from app.optimizers.compressor import normalize_whitespace
from app.optimizers.prompt_analyzer import ProtectedSpan, analyze_prompt

PreservationStatus = Literal[
    "preserved",
    "violation",
    "unknown",
]
CompressionStrategy = Literal[
    "rule_based",
    "llmlingua2",
]


def validate_preservation(
    original: str,
    compressed: str,
    protected_spans: tuple[ProtectedSpan, ...],
    strategy: CompressionStrategy = "llmlingua2",
    *,
    semantic_similarity: float | None = None,
) -> PreservationStatus:
    if not compressed.strip():
        return "violation"
    if original == compressed:
        return "preserved"
    required = Counter(span.text for span in protected_spans)
    for text, count in required.items():
        if compressed.count(text) < count:
            return "violation"
    if strategy == "rule_based":
        if normalize_whitespace(original) == compressed:
            return "preserved"
        return "unknown"
    # Entity survival alone cannot establish semantic preservation. The real
    # compressor additionally checks each mutable paragraph with a local encoder
    # and keeps task/protected paragraphs verbatim. Missing evidence fails closed.
    if strategy == "llmlingua2":
        # Keeping the word "not/không" alone does not preserve its bound.
        pattern = r"\b(?:không\s+(?:ít|nhiều|nhỏ|lớn|thấp|cao)\s+hơn|(?:at\s+least|at\s+most|no\s+(?:less|more)\s+than))\b"
        if Counter(re.findall(pattern, original, re.IGNORECASE)) != Counter(
            re.findall(pattern, compressed, re.IGNORECASE)
        ):
            return "unknown"
        if semantic_similarity is None or not math.isfinite(semantic_similarity):
            return "unknown"
        return "preserved" if 0.85 <= semantic_similarity <= 1.000001 else "unknown"
    return "unknown"


def check_preservation(original: str, compressed: str) -> PreservationStatus:
    """Backward-compatible facade for callers that do not precompute spans."""
    analysis = analyze_prompt(original, compression_threshold=0)
    return validate_preservation(
        original,
        compressed,
        analysis.protected_spans,
    )
