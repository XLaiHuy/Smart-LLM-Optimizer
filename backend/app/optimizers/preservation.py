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
    # LLMLingua is the semantic compressor selected by the adaptive path.
    # Its output is accepted only after the hard constraints above pass.  The
    # previous implementation returned ``unknown`` for every non-identical
    # LLMLingua result, which made the adaptive path permanently fall back to
    # the original prompt even when all protected spans were preserved.
    if strategy == "llmlingua2":
        return "preserved"
    return "unknown"


def check_preservation(original: str, compressed: str) -> PreservationStatus:
    """Backward-compatible facade for callers that do not precompute spans."""
    analysis = analyze_prompt(original, compression_threshold=0)
    return validate_preservation(
        original,
        compressed,
        analysis.protected_spans,
    )
