import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routing.family_threshold_preview import explore
from app.routing.task_groups import TaskGroupPolicy


def test_partial_preview_learns_classifier_and_threshold_but_cannot_serve(tmp_path):
    rows, originals = [], {}
    for family in ("exact_arithmetic", "structured_extraction", "vietnamese_qa"):
        for split, count in (("train", 50), ("calibration", 10), ("threshold", 10)):
            for i in range(count):
                key = f"{family}:{split}:{i}"
                text = f"{family} {family} question {i}"
                originals[key] = text
                rows.append(
                    dict(
                        task_id=key,
                        group_id=key,
                        domain=family,
                        split=split,
                        messages=[dict(role="user", content=text)],
                        observations=[
                            dict(
                                config_id=c,
                                qualified=c != "luna",
                                usd=".01" if c == "ref" else ".001",
                                latency_ms=1,
                                input_tokens=1,
                                output_tokens=1,
                            )
                            for c in ("small", "luna", "ref")
                        ],
                    )
                )
    engine = SimpleNamespace(
        hash="frozen",
        score=lambda c, *args: 0.8 if c == "small" else 0.7,
        artifact=SimpleNamespace(
            reference_config_id="ref",
            predictors=[SimpleNamespace(config_id=c, threshold=0.95) for c in ("small", "luna")],
            configurations=[
                SimpleNamespace(config_id=c, max_output_tokens=128)
                for c in ("small", "luna", "ref")
            ],
        ),
    )
    rates = {
        c: (
            Decimal(".1") if c == "ref" else Decimal(".01"),
            Decimal(".1") if c == "ref" else Decimal(".01"),
        )
        for c in ("small", "luna", "ref")
    }
    result = explore(rows, engine, originals, rates)
    assert result["classifier_fit_groups"] == 150
    assert not result["serving_activation"] and not result["independent_quality_test"]
    assert any(r["decision"] == "research_candidate_only" for r in result["reports"].values())
    for report in result["reports"].values():
        if report["decision"] == "research_candidate_only":
            assert report["thresholds"]["small"] == 0.8
            assert report["distribution"].get("luna", 0) == 0
    path = tmp_path / "preview.json"
    path.write_text(json.dumps(result, default=lambda x: int(x)))
    assert (
        TaskGroupPolicy(path, SimpleNamespace(hash="frozen")).status
        == "GROUP_POLICY_INVALID_SHADOW"
    )


def test_preview_never_reads_holdout():
    with pytest.raises(ValueError, match="HOLDOUT"):
        explore([{"split": "holdout"}], None, {}, {})
