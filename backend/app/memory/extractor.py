"""Conservative, deterministic extraction of explicit user facts."""

from __future__ import annotations

import re

from app.contracts.dtos import Fact

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "name",
        re.compile(
            r"\b(?:my name is|tên tôi là|tôi tên(?: là)?|toi ten(?: la)?)\s+([^.!?\n]{1,80})",
            re.I,
        ),
    ),
    (
        "preference",
        re.compile(
            r"\b(?:i prefer|i like|tôi thích|tôi ưu tiên|toi thich|toi uu tien)\s+([^.!?\n]{1,120})",
            re.I,
        ),
    ),
    (
        "deadline",
        re.compile(
            r"\b(?:deadline|hạn chót|hạn cuối|han chot|han cuoi)"
            r"(?:\s+(?:nộp(?:\s+báo cáo)?|báo cáo|nop(?:\s+bao cao)?|bao cao))?"
            # A recall question is not a fact: require a declarative link.
            r"\s*(?:(?:is|là|la)\s+|:\s*)([^.!?\n]{1,80})",
            re.I,
        ),
    ),
    (
        "major",
        re.compile(
            r"\b(?:tôi học ngành|ngành học của tôi là|ngành của tôi là|"
            r"toi hoc nganh|nganh hoc cua toi la|nganh cua toi la)\s+([^.!?\n]{1,120})",
            re.I,
        ),
    ),
    (
        "school",
        re.compile(
            r"\b(?:tôi học tại|tôi là sinh viên (?:của|tại)|trường của tôi là|"
            r"toi hoc tai|toi la sinh vien (?:cua|tai)|truong cua toi la)\s+"
            r"((?:[^.!?\n]|\.(?=\S)){1,120})",
            re.I,
        ),
    ),
    (
        "research_topic",
        re.compile(
            r"\b(?:đề tài nghiên cứu của tôi là|đề tài của tôi là|tôi đang nghiên cứu(?: về)?|"
            r"de tai nghien cuu cua toi la|de tai cua toi la|toi dang nghien cuu(?: ve)?)"
            r"\s+([^.!?\n]{1,160})",
            re.I,
        ),
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
        # Do not persist interrogative values such as 'Tên tôi là gì?'.
        if content[match.end() :].lstrip().startswith("?"):
            continue
        value = " ".join(match.group(1).strip().split())
        # A correction can repeat its label: 'hạn chót: hạn chót là 25/11'.
        nested = pattern.search(value)
        if nested is not None:
            value = " ".join(nested.group(1).strip().split())
        if value:
            facts.append(Fact(key=key, value=value, source_message_ids=(source_message_id,)))
    return tuple(facts)


# The original patterns above include legacy mojibake spellings kept for old
# fixtures. These normal-Unicode patterns handle current Vietnamese UI input.
_NORMALIZED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("name", re.compile(r"\b(?:tên tôi là|tôi tên(?: là)?)\s+([^.!?\n]{1,80})", re.I)),
    (
        "preference",
        re.compile(r"\b(?:tôi thích|tôi ưu tiên)\s+([^.!?\n]{1,120})", re.I),
    ),
    (
        "deadline",
        re.compile(
            r"\b(?:hạn chót|hạn cuối)(?:\s+(?:nộp(?: báo cáo)?|báo cáo))?"
            r"\s*(?:(?:là)\s+|:\s*)([^.!?\n]{1,80})",
            re.I,
        ),
    ),
    (
        "major",
        re.compile(
            r"\b(?:tôi học ngành|ngành học của tôi là|ngành của tôi là)\s+([^.!?\n]{1,120})",
            re.I,
        ),
    ),
    (
        "school",
        re.compile(
            r"\b(?:tôi học tại|tôi là sinh viên (?:của|tại)|trường của tôi là)\s+"
            r"((?:[^.!?\n]|\.(?=\S)){1,120})",
            re.I,
        ),
    ),
    (
        "research_topic",
        re.compile(
            r"\b(?:đề tài nghiên cứu của tôi là|đề tài của tôi là|tôi đang nghiên cứu(?: về)?)"
            r"\s+([^.!?\n]{1,160})",
            re.I,
        ),
    ),
)

_LEGACY_EXTRACT_EXPLICIT_FACTS = extract_explicit_facts


def extract_explicit_facts(content: str, source_message_id: str) -> tuple[Fact, ...]:
    """Extract explicit facts from both legacy and normal Unicode Vietnamese."""

    facts = list(_LEGACY_EXTRACT_EXPLICIT_FACTS(content, source_message_id))
    existing = {fact.key for fact in facts}
    for key, pattern in _NORMALIZED_PATTERNS:
        match = pattern.search(content)
        if match is None or key in existing:
            continue
        if content[match.end() :].lstrip().startswith("?"):
            continue
        value = " ".join(match.group(1).strip().split())
        if value:
            facts.append(Fact(key=key, value=value, source_message_ids=(source_message_id,)))
            existing.add(key)
    return tuple(facts)
