"""Bounded deterministic guard for explicit numeric-only arithmetic requests.

Unknown wording is not parsed. Never infers a formula from generic word problems
or uses benchmark gold. This guard rejects known-wrong output, not paid retries.
"""

import re
from decimal import Decimal, DecimalException

from app.core.tools import calculate

NUMBER = r"[+-]?\d+(?:\.\d+)?"
REVERSE = re.compile(
    rf"Một giá trị giảm ({NUMBER})% còn ({NUMBER})\. "
    r"Giá trị ban đầu là bao nhiêu\? Chỉ trả lời số\.?",
    re.I,
)
FORWARD = re.compile(
    rf"Giảm ({NUMBER})% của ({NUMBER}), giá trị còn lại là bao nhiêu\? Chỉ trả lời số\.?", re.I
)
EXPRESSION = re.compile(
    r"Tính ([0-9+*/().−–\s-]+)\. Chỉ trả lời (?:kết quả|số)(?:, giữ dấu âm)?\.?", re.I
)


def numeric_answer_verdict(prompt: str, answer: str) -> bool | None:
    text = " ".join(prompt.split())
    expression = None
    reverse, forward, arithmetic = (
        REVERSE.fullmatch(text),
        FORWARD.fullmatch(text),
        EXPRESSION.fullmatch(text),
    )
    if reverse or forward:
        match = reverse or forward
        assert match is not None
        rate, value = match.groups()
        if not 0 <= Decimal(rate) < 100:
            return None
        expression = (
            f"({value}) / (1 - ({rate}) / 100)" if reverse else f"({value}) * (1 - ({rate}) / 100)"
        )
    elif arithmetic:
        expression = arithmetic.group(1).replace("−", "-").replace("–", "-")
    if expression is None:
        return None
    try:
        expected = Decimal(calculate(expression))
        # The supported envelope is exact integer-valued requests. Fractional
        # answers may require unspecified rounding; leave those unclassified.
        if expected != expected.to_integral_value():
            return None
        if not re.fullmatch(rf"{NUMBER}(?:[eE][+-]?\d+)?", answer.strip()):
            return False
        actual = Decimal(answer.strip())
        return actual.is_finite() and actual == expected
    except (DecimalException, ValueError, SyntaxError):
        return None
