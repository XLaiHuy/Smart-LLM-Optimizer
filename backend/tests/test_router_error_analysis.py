"""Error attribution does not blame routing for every source/model failure."""

import importlib.util
import sys

import pytest

from app.config import ROOT
from app.contracts.dtos import Message
from app.contracts.training import GradingSpec, RawTrainingSample

sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "router_error_analysis", ROOT / "scripts/analyze_router_errors.py"
)
assert spec and spec.loader
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
import prepare_targeted_math_variants as variants  # noqa: E402


def test_attribution_distinguishes_wrong_route_reference_failure_and_missed_rescue():
    results = [
        {"task_id": "regress", "qualified": False, "reference_qualified": True},
        {"task_id": "all", "qualified": False, "reference_qualified": False},
        {"task_id": "missed", "qualified": False, "reference_qualified": False},
        {"task_id": "gain", "qualified": True, "reference_qualified": False},
        {"task_id": "tie", "qualified": True, "reference_qualified": True},
    ]
    observations = {
        row["task_id"]: {"observations": [{"qualified": row["task_id"] != "all"}]}
        for row in results
    }
    assert analysis.error_breakdown(results, observations) == {
        "routing_regression": 1,
        "all_measured_profiles_fail": 1,
        "missed_successful_alternative": 1,
        "route_improves_reference": 1,
        "both_pass": 1,
    }


def test_quarantine_flags_visible_damage_without_calling_it_answer_validation():
    assert analysis.surface_issues("Tom\ufffds cat") == ["unicode_replacement_character"]
    assert analysis.surface_issues("Tìm số Bài tập trắc nghiệm toán có đáp án | Toán lớp 6")
    assert analysis.surface_issues("Cho hình vẽ dưới. Tính diện tích.")
    assert analysis.surface_issues("-12 + 3 = ?") == []
    assert analysis.surface_issues("Hiện nay tỉnh nào...") == [
        "time_dependent_question_without_reference_date"
    ]
    assert analysis.surface_issues("Quốc gia giàu nhất thế giới năm 2022?") == [
        "wealth_ranking_metric_unspecified"
    ]
    assert analysis.surface_issues("GDP bình quân đầu người năm 2022 của nước nào cao nhất?") == []


@pytest.mark.parametrize("gold", list("ABCD"))
@pytest.mark.parametrize("shift", [1, 2, 3])
def test_rotation_preserves_correct_option_value_and_training_group(gold, shift):
    parent = RawTrainingSample(
        task_id="real-parent",
        group_id="public-source-group",
        domain="vietnamese_mcq",
        split="train",
        messages=(
            Message(
                role="user",
                content="Tính toán?\nA. -7\nB. 13\nC. 0\nD. 2\nChỉ trả lời một chữ cái trong các lựa chọn.",
            ),
        ),
        gold=gold,
        grading=GradingSpec(kind="mcq", choices=tuple("ABCD")),
    )
    rotated = variants.rotate(parent, shift)
    assert (
        variants.options(parent)[1]["ABCD".index(gold)]
        == variants.options(rotated)[1]["ABCD".index(rotated.gold)]
    )
    assert rotated.group_id == parent.group_id == rotated.grading.parent_group_id
    assert rotated.split == "train" and rotated.grading.synthetic
    assert rotated.grading.label_source == "synthetic_verified"


@pytest.mark.parametrize("split", ["calibration", "threshold", "holdout"])
def test_rotation_cannot_turn_nontraining_source_into_training(split):
    parent = RawTrainingSample(
        task_id="source",
        group_id="group",
        domain="vietnamese_mcq",
        split=split,
        messages=(Message(role="user", content="Question"),),
        gold="A",
        grading=GradingSpec(kind="mcq", choices=tuple("ABCD")),
    )
    with pytest.raises(ValueError, match="TRAIN"):
        variants.rotate(parent, 1)


def test_original_identity_strips_only_exact_protocol_suffix():
    assert (
        analysis.source_text("What is 2+3?\nGive only the final numeric answer.") == "What is 2+3?"
    )
    assert analysis.source_text("Chọn A?\nChỉ trả lời một chữ cái trong các lựa chọn.") == "Chọn A?"
    assert (
        analysis.source_text("Give only the final numeric answer.\nActual question")
        == "Give only the final numeric answer.\nActual question"
    )
