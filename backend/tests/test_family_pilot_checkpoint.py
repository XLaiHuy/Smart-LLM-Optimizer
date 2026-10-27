import json

import pytest

from app.routing.family_pilot import checkpoint_spend


def record():
    return {
        "candidate_sha256": "frozen",
        "usd": ".001",
        "calls": [
            {"dispatch_state": "completed", "cost": {"serving_usd": ".001", "status": "estimated"}}
        ],
    }


def test_resume_counts_all_known_files_once(tmp_path):
    for name in ("a", "b"):
        (tmp_path / (name + ".result.json")).write_text(json.dumps(record()))
    assert str(checkpoint_spend(tmp_path, "frozen")) == "0.002"


def test_unknown_later_dispatch_blocks_before_earlier_new_request(tmp_path):
    (tmp_path / "later.dispatch.json").write_text("{}")
    with pytest.raises(ValueError, match="Unresolved"):
        checkpoint_spend(tmp_path, "frozen")


@pytest.mark.parametrize(
    "defect", ["candidate", "unknown_cost", "unknown_dispatch", "nan", "negative", "mismatch"]
)
def test_corrupt_or_unresolved_checkpoint_blocks_paid_calls(tmp_path, defect):
    data = record()
    if defect == "candidate":
        data["candidate_sha256"] = "changed"
    elif defect == "unknown_cost":
        data["calls"][0]["cost"]["serving_usd"] = None
    elif defect == "unknown_dispatch":
        data["calls"][0]["dispatch_state"] = "unknown"
    elif defect == "nan":
        data["usd"] = "NaN"
    elif defect == "negative":
        data["usd"] = "-.001"
    elif defect == "mismatch":
        data["usd"] = ".002"
    (tmp_path / "a.result.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        checkpoint_spend(tmp_path, "frozen")
