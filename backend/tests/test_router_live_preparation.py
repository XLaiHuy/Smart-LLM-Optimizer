"""Offline protocol tests; no model dispatch, download or research activation."""

import importlib.util
from collections import Counter

import pytest

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.training import GradingSpec, RawTrainingSample
from app.routing.ml.graders import grade

spec = importlib.util.spec_from_file_location(
    "prepare_qualification", ROOT / "scripts/prepare_router_qualification.py"
)
assert spec and spec.loader
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


@pytest.mark.parametrize(
    ("prompt", "target", "expected"),
    [
        ("Choose one\nA. one\nB. two\nC. three", "B. two", "B"),
        ("Chọn\na) một\nb) hai\nc) ba", "Đáp án đúng: b", "B"),
        (
            "Parts\na) part one\nb) part two\nc) part three",
            "a) answer one\nb) answer two\nc) answer three",
            None,
        ),
        ("Choose\nA. one\nB. two\nC. three", "Đáp án\n\na) explanation", None),
        ("Choose\nA. one\nB. two\nC. three", "A. one, B. two", None),
        ("Choose\nA. one\nA. two\nC. three", "A", None),
        ("Choose\nA. one\nB. two\nC. three", "D", None),
    ],
)
def test_mcq_adaptation_requires_unambiguous_original_gold(prompt, target, expected):
    assert preparation.mcq_gold(prompt, target) == expected
    if expected:
        grading = GradingSpec(kind="mcq", choices=preparation.mcq_options(prompt))
        assert grade(grading, expected, expected).qualified
        assert not grade(grading, "not an answer", expected).qualified


def test_stratified_freeze_is_order_independent_and_excludes_previous_pilot():
    rows = [
        RawTrainingSample(
            task_id=str(i),
            group_id=str(i),
            domain="test",
            split="train",
            messages=(Message(role="user", content=f"Original functional unit {i}"),),
            gold="1",
            grading=GradingSpec(kind="numeric"),
        )
        for i in range(210)
    ]
    first = preparation.freeze_groups(rows, {"0", "1"})
    second = preparation.freeze_groups(list(reversed(rows)), {"0", "1"})
    assert first == second
    assert Counter(r.split for r in first) == {
        "train": 60,
        "calibration": 20,
        "threshold": 20,
        "holdout": 100,
    }
    assert len({r.group_id for r in first}) == 200
    assert not {"0", "1"} & {r.group_id for r in first}
    with pytest.raises(ValueError, match="200 original groups"):
        preparation.freeze_groups(rows[:199], set())
