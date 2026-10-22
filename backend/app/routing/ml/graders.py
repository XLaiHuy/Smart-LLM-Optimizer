"""Versioned routing-label graders. Evaluation targets never enter serving inputs."""

import ast
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Literal

from app.contracts.training import GradingSpec

GRADER_VERSION = "router-gold-graders-v1"
LabelSource = Literal["dataset_gold", "human_verified", "teacher_judged", "synthetic_verified"]


@dataclass(frozen=True)
class Grade:
    qualified: bool
    metrics: dict[str, float]
    label_source: LabelSource
    grader_version: str = GRADER_VERSION


def normalize(text: str) -> str:
    # Explicit Vietnamese protocol: retain diacritics and do not remove English
    # articles (the letter 'a' can itself be a Vietnamese gold entity).
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(
        "".join(" " if unicodedata.category(c).startswith("P") else c for c in text).split()
    )


def numeric(text: str) -> Decimal:
    text = text.strip()
    if len(text) > 128:
        raise ValueError("Numeric answer too long")
    if re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        text = text.replace(",", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]?\d+/\d+", text):
        raise ValueError("Invalid numeric answer")
    try:
        if "/" in text:
            fraction = Fraction(text)
            return Decimal(fraction.numerator) / Decimal(fraction.denominator)
        value = Decimal(text)
        if not value.is_finite() or abs(value.adjusted()) > 1000:
            raise ValueError("Non-finite answer")
        return value
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise ValueError("Invalid numeric answer") from exc


def arithmetic(expression: str) -> Decimal:
    """Verify synthetic arithmetic without executing teacher-provided Python."""
    if len(expression) > 128:
        raise ValueError("Expression too long")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 40:
        raise ValueError("Expression too complex")

    def visit(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 10000:
            return Decimal(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            else:
                if right == 0 or left % right:
                    raise ValueError("Synthetic division must have an exact integer result")
                result = left / right
            if abs(result) > 10**8:
                raise ValueError("Synthetic result out of bounds")
            return result
        raise ValueError("Unsupported expression")

    return visit(tree.body)


def validate_gold(spec: GradingSpec, gold: str) -> None:
    if spec.version != "router-grader-v1":
        raise ValueError("Unsupported grading specification version")
    if spec.kind == "numeric":
        numeric(gold)
    elif spec.kind == "mcq":
        if gold not in spec.choices or any(not re.fullmatch("[A-Z]", c) for c in spec.choices):
            raise ValueError("Invalid MCQ gold/options")
    elif spec.kind == "extractive_qa":
        data = json.loads(gold)
        if not isinstance(data.get("is_impossible"), bool) or not isinstance(
            data.get("answers"), list
        ):
            raise ValueError("Invalid extractive gold")
        if not data["is_impossible"] and not data["answers"]:
            raise ValueError("Missing answerable gold")
        if data["is_impossible"] and data["answers"]:
            raise ValueError("No-answer gold cannot contain an answer")
        if not all(isinstance(a, str) and a.strip() for a in data["answers"]):
            raise ValueError("Invalid gold answers")
    elif spec.kind == "code":
        if not spec.tests or not spec.docker_image:
            raise ValueError("Code tests and pinned sandbox image required")
        for test in (spec.test_setup, *spec.tests):
            ast.parse(test)
    elif spec.label_source == "synthetic_verified" and not spec.human_reviewed:
        raise ValueError("Open synthetic tasks require independent human verification")


def grade(spec: GradingSpec, output: str, gold: str) -> Grade:
    validate_gold(spec, gold)
    metrics: dict[str, float]
    if spec.kind == "mcq":
        last = output.strip().splitlines()[-1] if output.strip() else ""
        match = re.fullmatch(
            r"(?:(?:Đáp án|Answer|Final answer|Kết luận)\s*:\s*)?([A-Z])[.)]?", last, re.IGNORECASE
        )
        passed = bool(match and match[1].upper() in spec.choices and match[1].upper() == gold)
        metrics = {"accuracy": float(passed)}
    elif spec.kind == "numeric":
        last = output.strip().splitlines()[-1] if output.strip() else ""
        last = re.sub(
            r"^(?:Đáp án|Answer|Final answer|####)\s*:?\s*", "", last, flags=re.IGNORECASE
        )
        expected = numeric(gold)
        try:
            actual = numeric(last)
            passed = abs(actual - expected) <= max(
                Decimal(str(spec.absolute_tolerance)),
                abs(expected) * Decimal(str(spec.relative_tolerance)),
            )
        except ValueError:
            passed = False
        metrics = {"numeric_accuracy": float(passed)}
    elif spec.kind == "extractive_qa":
        data = json.loads(gold)
        try:
            response = json.loads(output)
            answer = response["answer"]
            if set(response) != {"answer"} or (answer is not None and not isinstance(answer, str)):
                raise ValueError("Invalid answer envelope")
        except (ValueError, KeyError, TypeError, IndexError):
            return Grade(False, {"em": 0, "f1": 0, "format_valid": 0}, spec.label_source)
        if data["is_impossible"]:
            passed = answer is None or answer == ""
            metrics = {"em": float(passed), "f1": float(passed), "no_answer": 1}
        else:
            prediction = normalize(answer or "")
            em, f1 = 0.0, 0.0
            for target in data["answers"]:
                target = normalize(target)
                em = max(em, float(prediction == target))
                p, t = prediction.split(), target.split()
                common = sum((Counter(p) & Counter(t)).values())
                score = 2 * common / (len(p) + len(t)) if p and t else 0.0
                f1 = max(f1, score)
            # Conservative qualification uses EM. F1 is reported, never substring pass.
            passed, metrics = em == 1, {"em": em, "f1": f1, "no_answer": 0}
    elif spec.kind == "code":
        from app.routing.ml.sandbox import code_grade

        return code_grade(spec, output)
    else:
        raise ValueError("Open tasks require the blind judge path")
    return Grade(passed, metrics, spec.label_source)
