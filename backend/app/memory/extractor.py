"""Conservative, deterministic extraction of explicit user facts."""

from __future__ import annotations

import re

from app.contracts.dtos import Fact

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("name", re.compile(r"\b(?:my name is|tên tôi là)\s+([^.!?\n]{1,80})", re.I)),
    (
        "preference",
        re.compile(r"\b(?:i prefer|i like|tôi thích|tôi ưu tiên)\s+([^.!?\n]{1,120})", re.I),
    ),
    (
        "deadline",
        re.compile(r"\b(?:deadline|hạn chót|hạn cuối)\s+(?:is|là)?\s*([^.!?\n]{1,80})", re.I),
    ),
)


def extract_explicit_facts(content: str, source_message_id: str) -> tuple[Fact, ...]:
    """Extract only explicit, high-confidence statements.

    Ambiguous conversational text is intentionally ignored; a wrong memory is
    more harmful than a missing one.
    """

    facts: list[Fact] = []
    for key, pattern in _PATTERNS:
        match = pattern.search(content)
        if match is None:
            continue
        value = " ".join(match.group(1).strip().split())
        if value:
            facts.append(Fact(key=key, value=value, source_message_ids=(source_message_id,)))
    return tuple(facts)
