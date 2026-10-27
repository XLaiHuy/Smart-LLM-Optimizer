import pytest

from app.routing.family_postcollection import diagnose


def row():
    return {
        "task_id": "t",
        "group_id": "g",
        "domain": "exact_arithmetic",
        "split": "train",
        "observations": [
            {"config_id": c, "qualified": c != "20b"} for c in ("20b", "120b", "luna")
        ],
    }


def test_partial_dev_diagnostics_never_claims_training_or_qualification():
    result = diagnose([row()], {"20b", "120b", "luna"})
    assert result["missing_dev"]["exact_arithmetic"]["train"] == 99
    assert result["model_diagnostics"]["exact_arithmetic/20b"]["failed_task_ids"] == ["t"]
    assert not any(
        result[k]
        for k in (
            "calibration_ready",
            "trained",
            "live_qualified",
            "holdout_read",
            "serving_changed",
        )
    )


@pytest.mark.parametrize("defect", ["holdout", "duplicate", "missing_model"])
def test_postcollection_rejects_holdout_or_incomplete_pairing(defect):
    rows = [row()]
    if defect == "holdout":
        rows[0]["split"] = "holdout"
    elif defect == "duplicate":
        rows *= 2
    else:
        rows[0]["observations"].pop()
    with pytest.raises(ValueError):
        diagnose(rows, {"20b", "120b", "luna"})
