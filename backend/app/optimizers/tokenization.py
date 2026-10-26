"""Tokenizer utilities for optimizer decisions, never provider billing."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenStats:
    before: int
    after: int
    savings: int
    ratio: float
    source: str


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> tuple[int, str]:
    """Return a local estimate with explicit provenance."""
    try:
        import tiktoken

        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text)), f"tiktoken:{encoding_name}"
    except (ImportError, LookupError, OSError):
        pieces = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        return len(pieces), "regex_estimate_v1"


def token_stats(original: str, compressed: str) -> TokenStats:
    before, source = count_tokens(original)
    after, after_source = count_tokens(compressed)
    return TokenStats(
        before=before,
        after=after,
        savings=max(before - after, 0),
        ratio=after / (before or 1),
        source=source if source == after_source else f"{source};{after_source}",
    )
