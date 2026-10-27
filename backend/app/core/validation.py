"""Serving validators use only explicit user contracts, never evaluator gold."""

import json
import re
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]

from app.contracts.dtos import AnswerValidation, ChatRequest, Message, SessionSnapshot
from app.core.numeric_validation import numeric_answer_verdict


def validate_schema(schema: dict[str, Any]) -> None:
    if len(json.dumps(schema)) > 8192:
        raise ValueError("Response schema exceeds 8 KiB")

    def visit(node: Any, depth: int = 0) -> None:
        if depth > 16:
            raise ValueError("Response schema is too deep")
        if isinstance(node, dict):
            if any(key in node for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise ValueError("Schema references are not accepted")
            for value in node.values():
                visit(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                visit(value, depth + 1)

    visit(schema)

    # Regex evaluation is not bounded by JSON Schema; decline user patterns.
    def patterns(node: Any) -> None:
        if isinstance(node, dict):
            if "pattern" in node or "patternProperties" in node:
                raise ValueError("Regex schema constraints are not accepted")
            for v in node.values():
                patterns(v)
        elif isinstance(node, list):
            for v in node:
                patterns(v)

    patterns(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError("Invalid response JSON schema") from exc


def known_memory_facts(
    snapshot: SessionSnapshot, memory_messages: tuple[Message, ...]
) -> dict[str, str]:
    """Only owned, provenance-backed facts provided by the memory port.

    Ambiguous cross-session values are excluded instead of resolving by a guessed
    order. Current-session corrections take precedence over other sessions.
    """
    values: dict[str, set[str]] = {}
    for message in memory_messages:
        if not (message.id or "").startswith("memory:fact:"):
            continue
        body = message.content.removeprefix("[Retrieved memory]\n")
        key, sep, value = body.partition(": ")
        if sep:
            values.setdefault(key, set()).add(value)
    result = {key: next(iter(items)) for key, items in values.items() if len(items) == 1}
    result.update({fact.key: fact.value for fact in snapshot.facts if fact.source_message_ids})
    return result


def validate_answer(
    request: ChatRequest, text: str, known_facts: dict[str, str] | None = None
) -> AnswerValidation:
    verdict = numeric_answer_verdict(request.message, text)
    if verdict is not None:
        return AnswerValidation(
            status="pass" if verdict else "fail", reason="exact_integer_arithmetic"
        )
    if request.response_schema is not None:
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return AnswerValidation(status="fail", reason="json_parse_failed")
        valid = Draft202012Validator(request.response_schema).is_valid(data)
        if not valid:
            return AnswerValidation(status="fail", reason="json_schema")
        if (
            isinstance(data, dict)
            and known_facts
            and re.search(r"nhớ|nhắc lại|remember|recall", request.message, re.I)
        ):
            checked = 0
            for key, expected in known_facts.items():
                if key not in data:
                    continue
                if key == "deadline":
                    match = re.fullmatch(
                        r"(\d{1,2}/\d{1,2}/\d{4})(?:,?\s*thay cho\s*\d{1,2}/\d{1,2}/\d{4})?",
                        expected,
                        re.I,
                    )
                    if match:
                        expected = match.group(1)
                checked += 1

                def normalized(value: Any) -> str:
                    return " ".join(str(value).casefold().split())

                if normalized(data[key]) != normalized(expected):
                    return AnswerValidation(status="fail", reason="memory_entity_binding")
            if checked:
                return AnswerValidation(status="pass", reason="json_schema_and_memory_bindings")
        return AnswerValidation(status="pass", reason="json_schema_only_not_factuality")
    if re.search(
        r"(?:^|\n)(?:Chỉ trả(?: lời| về)? JSON|Return only JSON)[.!]?\s*$", request.message, re.I
    ):
        try:
            json.loads(text)
        except (ValueError, RecursionError):
            return AnswerValidation(status="fail", reason="json_parse_failed")
        return AnswerValidation(status="unknown", reason="json_syntax_only_no_content_contract")
    if re.search(
        r"(?:chỉ (?:trả lời|trả lại|trả về) (?:mã|ngày|số tiền)|reply only with the code)",
        request.message,
        re.I,
    ):
        # Only an unambiguous explicit identifier binding. Dates/amounts without
        # entity/unit/source contracts remain unknown, not a bag-of-numbers pass.
        values = re.findall(
            r"(?:mã(?: xác nhận| cuối cùng)? (?:là|is)|confirmation code is)\s+([A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)",
            request.message,
            re.I,
        )
        unique = set(values)
        if len(unique) == 1:
            return AnswerValidation(
                status="pass" if text.strip() == next(iter(unique)) else "fail",
                reason="explicit_identifier_binding",
            )
    return AnswerValidation(status="unknown", reason="no_reviewed_deterministic_contract")
