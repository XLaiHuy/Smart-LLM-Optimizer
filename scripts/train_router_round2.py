"""Offline expanded training. Choose a predeclared recipe on DEV, never HOLDOUT.

The old published HOLDOUT is retired to development data; only freshly collected
round-two groups may supply the next test. No serving activation or provider calls.
"""

import argparse
import hashlib
import json
import socket
from collections import Counter
from pathlib import Path
from time import perf_counter
from typing import Any

from app.contracts.representations import EncoderSpec
from app.contracts.training import TrainingManifest
from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import (
    MultiDataset,
    MultiSample,
    replay_rows,
    report_replay,
    train_multi,
)
from app.routing.ml.pilot import dataset, frozen_hash
from app.routing.ml.pipeline import atomic_text


def retired_dev_split(group: str) -> str:
    bucket = (
        int(hashlib.sha256(("round2-dev:" + group).encode()).hexdigest()[:8], 16) % 100
    )
    return "train" if bucket < 60 else "calibration" if bucket < 80 else "threshold"


def expanded_dev(
    previous: Path,
    pilot: Path,
    current: Path,
    manifest: TrainingManifest,
    allow_partial: bool = False,
) -> MultiDataset:
    family_plan_path = current.parents[1] / "independent-family-plan.json"
    if family_plan_path.exists():
        plan = json.loads(family_plan_path.read_text(encoding="utf-8"))
        family = plan["family_map"]
        test_families = set(plan["mcq_holdout_families"])
        current_raw = json.loads(
            (current / "observations.json").read_text(encoding="utf-8")
        )
        if (
            sum(r["split"] != "holdout" for r in current_raw) != 62
            and not allow_partial
        ):
            raise ValueError("Wait for all 62 fresh measured DEV cases")
        rows = []
        prior_ids = set()
        signatures: dict[str, str] = {}
        partial_source = current.parent / plan["superseded_job_id"]
        directories = (
            (previous, pilot, partial_source, current)
            if allow_partial
            else (previous, pilot, current)
        )
        for directory in directories:
            old_manifest = TrainingManifest.model_validate_json(
                (directory / "manifest.json").read_text(encoding="utf-8")
            )
            if (
                old_manifest.configurations != manifest.configurations
                or old_manifest.costs != manifest.costs
            ):
                raise ValueError("Measured generation and price settings differ")
            for raw in json.loads(
                (directory / "observations.json").read_text(encoding="utf-8")
            ):
                key = raw["group_id"]
                group = family.get(key, key)
                if group in test_families or (
                    directory in (current, partial_source)
                    and raw["domain"] == "math_reasoning"
                    and raw["split"] == "holdout"
                ):
                    continue
                signature = json.dumps(
                    {key: raw[key] for key in ("messages", "observations")},
                    sort_keys=True,
                )
                if raw["task_id"] in prior_ids:
                    # Exact repeated cache entries are not extra training units.
                    if signatures[raw["task_id"]] != signature:
                        raise ValueError(
                            "Conflicting response or grading for the same cached task"
                        )
                    continue
                prior_ids.add(raw["task_id"])
                signatures[raw["task_id"]] = signature
                row = MultiSample.model_validate(raw)
                rows.append(
                    row.model_copy(
                        update={"group_id": group, "split": retired_dev_split(group)}
                    )
                )
        if len(rows) != 510 and not allow_partial:
            raise ValueError(f"Expected 510 measured DEV rows; found {len(rows)}")
        return dataset(manifest, rows)
    rows = []
    for directory in (previous, pilot):
        old_manifest = TrainingManifest.model_validate_json(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            old_manifest.configurations != manifest.configurations
            or old_manifest.costs != manifest.costs
        ):
            raise ValueError(
                "Old observations do not match the exact generation/price snapshot"
            )
        for raw in json.loads(
            (directory / "observations.json").read_text(encoding="utf-8")
        ):
            row = MultiSample.model_validate(raw)
            rows.append(
                row.model_copy(update={"split": retired_dev_split(row.group_id)})
            )
    # Filter before deserializing measured outcomes; fresh HOLDOUT is never fitted.
    fresh = [
        MultiSample.model_validate(raw)
        for raw in json.loads(
            (current / "observations.json").read_text(encoding="utf-8")
        )
        if raw["split"] != "holdout"
    ]
    if len(fresh) != 100:
        raise ValueError(f"Wait for all 100 fresh DEV rows; currently {len(fresh)}")
    rows.extend(fresh)
    if len(rows) != 548 or len({r.group_id for r in rows}) != 548:
        raise ValueError("Expected 548 distinct measured DEV groups")
    return dataset(manifest, rows)


def selection_report(dev: MultiDataset, artifact) -> dict:
    threshold = tuple(r for r in dev.samples if r.split == "threshold")
    engine = MultiRouterService(artifact.model_dump_json())
    replay = replay_rows(dev, engine, threshold)
    thresholds = {p.config_id: p.threshold for p in artifact.predictors}
    report: dict[str, Any] = dict(
        report_replay(replay, dev.reference_config_id, thresholds)
    )
    regressions: dict[str, int] = {}
    for row, scores, ordered in replay:
        selected = next(
            (
                key
                for key in ordered
                if not row.tool_recovery_required and scores[key] >= thresholds[key]
            ),
            dev.reference_config_id,
        )
        obs = {o.config_id: o for o in row.observations}
        regressions[row.domain] = regressions.get(row.domain, 0) + int(
            obs[dev.reference_config_id].qualified and not obs[selected].qualified
        )
    report["gross_regressions_by_domain"] = regressions
    timings = []
    for row in threshold:
        if engine.semantic:
            engine.semantic.cache.clear()
        started = perf_counter()
        replay_rows(dev, engine, (row,))
        timings.append((perf_counter() - started) * 1000)
    from statistics import median

    report["routing_p50_ms"] = median(timings)
    return report


def run(args):
    if (args.output / "frozen.json").exists():
        raise ValueError("Recipes already frozen; never retune on HOLDOUT")
    manifest = TrainingManifest.model_validate_json(
        (args.current / "manifest.json").read_text(encoding="utf-8")
    )
    dev = expanded_dev(
        args.previous, args.pilot, args.current, manifest, args.allow_partial_dev
    )
    spec = EncoderSpec.model_validate_json(
        (
            Path(__file__).resolve().parents[1] / "config/encoder.minilm-int8.json"
        ).read_text(encoding="utf-8")
    )
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_text(args.output / "dev.json", dev.model_dump_json(indent=2))

    def deny(*a, **kw):
        raise RuntimeError("Offline training forbids network")

    socket.socket.connect = deny
    socket.getaddrinfo = deny
    import torch

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    print(
        json.dumps(
            {
                "stage": "expanded_dev_frozen",
                "rows": len(dev.samples),
                "splits": dict(Counter(r.split for r in dev.samples)),
                "dev_hash": frozen_hash(dev.model_dump_json()),
                "independent_groups": len({r.group_id for r in dev.samples}),
                "partial_collection": args.allow_partial_dev,
            }
        ),
        flush=True,
    )
    # Freeze this small recipe set before reading any fresh HOLDOUT result.
    recipes = [
        ("attention64-e5", 64, 5),
        ("attention64-e15", 64, 15),
        ("attention128-e15", 128, 15),
    ]
    atomic_text(
        args.output / "recipes.json",
        json.dumps(
            {
                "recipes": recipes,
                "selection": "DEV gross regressions, then observed quality, measured cost and routing overhead; no HOLDOUT access",
            },
            indent=2,
        ),
    )
    started = perf_counter()
    baseline = train_multi(dev, hybrid=True, n_estimators=100)
    atomic_text(args.output / "baseline.json", baseline.model_dump_json(indent=2))
    baseline_report = selection_report(dev, baseline)
    reports = {"ml_without_attention": baseline_report}
    candidates = []
    for name, tokens, epochs in recipes:
        recipe_spec = spec.model_copy(update={"max_tokens": tokens})
        artifact = train_multi(
            dev,
            hybrid=True,
            encoder_spec=recipe_spec,
            attention_epochs=epochs,
            n_estimators=100,
        )
        atomic_text(args.output / (name + ".json"), artifact.model_dump_json(indent=2))
        report = selection_report(dev, artifact)
        reports[name] = report
        candidates.append(
            (
                sum(report["gross_regressions_by_domain"].values()),
                -report["observed_pass_rate"],
                report["serving_usd"],
                report["routing_p50_ms"],
                name,
                artifact,
            )
        )
        atomic_text(
            args.output / "dev-recipe-comparison.json", json.dumps(reports, indent=2)
        )
        print(json.dumps({"recipe": name, "dev_report": report}), flush=True)
    chosen = min(candidates, key=lambda x: x[:5])
    raw = chosen[-1].model_dump_json(indent=2)
    atomic_text(args.output / "artifact.json", raw)
    frozen = {
        "dev": frozen_hash(dev.model_dump_json()),
        "baseline": frozen_hash(baseline.model_dump_json(indent=2)),
        "attention": frozen_hash(raw),
        "selected_recipe": chosen[-2],
        "seconds": perf_counter() - started,
    }
    atomic_text(args.output / "frozen.json", json.dumps(frozen, indent=2))
    print(json.dumps({"stage": "final_recipes_frozen", **frozen}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-partial-dev",
        action="store_true",
        help="Train measured DEV collected so far; never qualifies incomplete HOLDOUT",
    )
    for name in ("previous", "pilot", "current", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    run(parser.parse_args())
