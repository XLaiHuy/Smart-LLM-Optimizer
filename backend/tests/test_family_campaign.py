import hashlib
from decimal import Decimal

import pytest

from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingManifest,
    TrainingSource,
)
from app.routing.ml.family_campaign import stop_requested, validate_source
from app.routing.ml.pipeline import cache_key


def test_user_stop_boundary_is_exact_and_persistent(tmp_path):
    import json

    assert not stop_requested(tmp_path, 450)
    (tmp_path / "collection-control.json").write_text(json.dumps({"stop_after_completed": 450}))
    assert not stop_requested(tmp_path, 449)
    assert stop_requested(tmp_path, 450)
    assert stop_requested(tmp_path, 451)
    (tmp_path / "collection-control.json").write_text(json.dumps({"stop_after_completed": True}))
    with pytest.raises(ValueError):
        stop_requested(tmp_path, 450)




def corpus():
    rows = []
    for family in ("exact_arithmetic", "structured_extraction", "vietnamese_qa"):
        for split, count in (
            ("train", 100),
            ("calibration", 50),
            ("threshold", 50),
            ("holdout", 100),
        ):
            for i in range(count):
                key = f"{family}:{split}:{i}"
                rows.append(
                    RawTrainingSample(
                        task_id=key,
                        group_id=key,
                        domain=family,
                        split=split,
                        messages=(Message(role="user", content=key),),
                        gold="1",
                        grading=GradingSpec(kind="numeric"),
                    )
                )
    return TrainingCorpus(samples=tuple(rows))


def test_exact_source_splits_and_no_synthetic_labels():
    data = corpus()
    validate_source(data)
    with pytest.raises(ValueError):
        validate_source(data.model_copy(update={"samples": data.samples[:-1]}))
    bad = data.samples[0].model_copy(
        update={"grading": GradingSpec(kind="numeric", synthetic=True)}
    )
    with pytest.raises(ValueError):
        validate_source(data.model_copy(update={"samples": (bad, *data.samples[1:])}))


def test_family_cache_is_bound_to_grading_corpus():
    configs = tuple(
        ModelConfiguration(
            config_id=str(i), model_id=str(i), context_window=10000, max_output_tokens=128
        )
        for i in range(3)
    )
    manifest = TrainingManifest(
        version="task-family-v1-20261027",
        reviewed_by="fixture",
        pricing_source="fixture",
        source=TrainingSource(
            local_path="fixture", sha256="a" * 64, license="fixture", provenance="fixture"
        ),
        configurations=configs,
        reference_config_id="0",
        costs=CostSnapshot(
            version="fixture",
            rates=tuple(
                RouteRate(
                    config_id=str(i),
                    input_per_million=Decimal(".1"),
                    output_per_million=Decimal(".2"),
                )
                for i in range(3)
            ),
        ),
        pilot=True,
    )
    messages = (Message(role="user", content="actual input"),)
    original = cache_key(manifest, "0", messages)
    changed = manifest.model_copy(
        update={
            "source": manifest.source.model_copy(
                update={"sha256": hashlib.sha256(b"new grader/gold").hexdigest()}
            )
        }
    )
    assert cache_key(changed, "0", messages) != original
    assert cache_key(manifest, "1", messages) != original
    assert (
        cache_key(manifest, "0", (Message(role="user", content="different context"),)) != original
    )


def test_calibration_refuses_holdout_before_loading_engine():
    from app.routing.family_calibration import fit_dev

    with pytest.raises(ValueError, match="HOLDOUT"):
        fit_dev([{"split": "holdout"}], None, {})


def test_platt_is_numerically_stable_and_uses_log_odds():
    from app.routing.family_calibration import probability

    assert probability(0.8, [1.0, 0.0]) == pytest.approx(0.8)
    assert 0 < probability(0, [2.0, -100.0]) < 1
    assert 0 < probability(1, [2.0, 100.0]) <= 1


def test_single_turn_profile_never_applies_to_history_or_unknown_context():
    from pathlib import Path
    from types import SimpleNamespace

    from app.routing.task_groups import TaskGroupPolicy

    policy = TaskGroupPolicy(Path("__absent_family_bundle__"), SimpleNamespace())
    policy.bundle = {"profiles": {"exact_arithmetic": {"scope": "single_turn_no_memory_no_tools"}}}
    task = {"family": "exact_arithmetic", "source": "local_tfidf_classifier_v1"}
    assert policy.profile(task) is None
    assert policy.profile({**task, "single_turn_empty_memory": False}) is None
    assert policy.profile({**task, "single_turn_empty_memory": True}) is not None


def test_fit_only_development_and_freezes_classifier_without_activation():
    from types import SimpleNamespace

    from app.routing.family_calibration import fit_dev

    source = corpus()
    rows = []
    originals = {}
    for sample in source.samples:
        if sample.split == "holdout":
            continue
        index = int(sample.task_id.rsplit(":", 1)[-1])
        # These artificial outcomes exercise the fitting software only.
        text = sample.domain + " category question " + str(index)
        originals[sample.task_id] = text
        observations = [
            dict(
                config_id=c,
                qualified=(c == "reference" or sample.split != "calibration" or index % 5 != 0),
                usd=".01" if c == "reference" else ".001",
                latency_ms=1,
                input_tokens=10,
                output_tokens=1,
            )
            for c in ("reference", "small", "luna")
        ]
        rows.append(
            dict(
                task_id=sample.task_id,
                group_id=sample.group_id,
                domain=sample.domain,
                split=sample.split,
                messages=[dict(role="user", content=text)],
                observations=observations,
            )
        )
    configs = [
        SimpleNamespace(config_id=c, max_output_tokens=128) for c in ("reference", "small", "luna")
    ]
    artifact = SimpleNamespace(
        reference_config_id="reference",
        predictors=[SimpleNamespace(config_id=c, threshold=0.95) for c in ("small", "luna")],
        configurations=configs,
        configuration_hashes={c.config_id: c.config_id for c in configs},
        costs_hash="fixture",
    )
    engine = SimpleNamespace(
        artifact=artifact,
        hash="fixture",
        score=lambda *args: 0.8,
        family_rates={
            c: (
                Decimal(".1" if c == "reference" else ".01"),
                Decimal(".1" if c == "reference" else ".01"),
            )
            for c in ("reference", "small", "luna")
        },
    )
    result = fit_dev(rows, engine, originals)
    assert result["holdout_read"] is False
    assert result["serving_activation"] is False
    assert set(result["bundle_candidate"]["classifier"]["classes"]) == {
        "exact_arithmetic",
        "structured_extraction",
        "vietnamese_qa",
    }
    assert all("holdout" not in name for name in result["dev_report"])
