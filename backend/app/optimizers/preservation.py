from collections import Counter
from typing import Literal

from app.optimizers.compressor import normalize_whitespace
from app.optimizers.prompt_analyzer import ProtectedSpan

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
    return "unknown"
