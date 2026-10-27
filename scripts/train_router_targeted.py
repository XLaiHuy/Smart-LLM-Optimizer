"""Offline data-only ablation; never reads old or fresh HOLDOUT outcomes."""

import argparse
import hashlib
import json
import socket
from collections import Counter
from pathlib import Path

from analyze_router_errors import load, surface_issues, write
from app.contracts.representations import EncoderSpec
from app.contracts.training import TrainingManifest
from app.routing.ml.multi import MultiArtifact
from app.routing.ml.multi_training import MultiDataset, MultiSample, train_multi
from app.routing.ml.pilot import dataset, frozen_hash
from train_router_round2 import selection_report


def combined_dev(previous, current, manifest, variants=None):
    old = MultiDataset.model_validate(load(previous / "dev.json"))
    incoming = load(current / "observations.json")
    old_manifest = TrainingManifest.model_validate(load(previous / "manifest.json"))
    if (
        old_manifest.configurations != manifest.configurations
        or old_manifest.costs != manifest.costs
    ):
        raise ValueError("Measured generation/price profiles must match exactly")
    if len(incoming) != manifest.max_samples:
        raise ValueError("Collect the entire frozen campaign before fitting")
    fresh = tuple(
        MultiSample.model_validate(s) for s in incoming if s["split"] != "holdout"
    )
    excluded = [
        s for s in old.samples + fresh if surface_issues(s.messages[-1].content)
    ]
    excluded_groups = {s.group_id for s in excluded}
    retained = tuple(s for s in old.samples if s.group_id not in excluded_groups)
    fresh = tuple(s for s in fresh if s.group_id not in excluded_groups)
    extra = ()
    if variants:
        variant_manifest = TrainingManifest.model_validate(
            load(variants / "manifest.json")
        )
        if (
            variant_manifest.configurations != manifest.configurations
            or variant_manifest.costs != manifest.costs
        ):
            raise ValueError("Variant generation/price profiles differ")
        source_path = Path(variant_manifest.source.local_path)
        if (
            hashlib.sha256(source_path.read_bytes()).hexdigest()
            != variant_manifest.source.sha256
        ):
            raise ValueError("Variant source changed")
        raw_variants = load(source_path)["samples"]
        expected = {
            s["task_id"]: s
            for s in raw_variants
            if s.get("grading", {}).get("synthetic")
        }
        extra = tuple(
            MultiSample.model_validate(s) for s in load(variants / "observations.json")
        )
        if (
            not expected
            or {s.task_id for s in extra} != set(expected)
            or len(extra) != len(expected)
        ):
            raise ValueError("Collect all frozen TRAIN variants before fitting")
        train_groups = {s.group_id for s in retained if s.split == "train"}
        for row in extra:
            source = expected[row.task_id]
            if (
                row.split != "train"
                or row.group_id not in train_groups
                or row.group_id != source["group_id"]
                or [m.model_dump(mode="json") for m in row.messages]
                != source["messages"]
                or any(o.label_source != "synthetic_verified" for o in row.observations)
            ):
                raise ValueError("Variant label or parent provenance mismatch")
    # MultiDataset validates identity/content conflicts across DEV splits.
    merged = dataset(manifest, list(retained + fresh + extra))
    return merged, [
        {
            "task_id": s.task_id,
            "group_id": s.group_id,
            "flags": surface_issues(s.messages[-1].content),
        }
        for s in excluded
    ]


def run(args):
    if args.output.exists():
        raise ValueError("Frozen training outputs must not be overwritten")
    manifest = TrainingManifest.model_validate(load(args.current / "manifest.json"))
    dev, excluded = combined_dev(args.previous, args.current, manifest, args.variants)
    dev = dev.model_copy(
        update={
            "version": "router-targeted-data-v2-20261027",
            "provenance": json.dumps(
                {
                    "protocol": "targeted-data-only-v2; historical HOLDOUT used only for diagnostics",
                    "collection_manifest": manifest.model_dump(mode="json"),
                    "previous_dev_sha256": hashlib.sha256(
                        (args.previous / "dev.json").read_bytes()
                    ).hexdigest(),
                    "previous_manifest_sha256": hashlib.sha256(
                        (args.previous / "manifest.json").read_bytes()
                    ).hexdigest(),
                    "variant_manifest_sha256": hashlib.sha256(
                        (args.variants / "manifest.json").read_bytes()
                    ).hexdigest()
                    if args.variants
                    else None,
                    "input_exclusions": excluded,
                    "train_variants": "Measured provider outputs; retain real parent groups; no variants in calibration/threshold/test",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        }
    )
    original = MultiArtifact.model_validate(load(args.previous / "artifact.json"))
    if original.attention is None:
        raise ValueError("Original Attention specification required")
    spec = EncoderSpec.model_validate(original.attention.encoder.model_dump())
    args.output.mkdir(parents=True)
    write(args.output / "dev-input-exclusions.json", excluded)
    (args.output / "dev.json").write_text(
        dev.model_dump_json(indent=2), encoding="utf-8"
    )
    write(
        args.output / "recipe.json",
        {
            "attention_epochs": 5,
            "n_estimators": 100,
            "domain_loss_weight": 0,
            "encoder": spec.model_dump(),
            "changes": "input defect quarantine and targeted data only",
            "train_variant_observations": str(args.variants) if args.variants else None,
            "split_counts": dict(Counter(s.split for s in dev.samples)),
            "fresh_holdout_opened": False,
            "old_holdout_used_in_fit": False,
            "serving_artifact_sha256_before": hashlib.sha256(
                args.serving.read_bytes()
            ).hexdigest(),
        },
    )

    def deny(*a, **kw):
        raise RuntimeError("Offline training forbids network")

    socket.socket.connect = deny
    socket.getaddrinfo = deny
    import torch

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    reports = {}
    hashes = {"dev": frozen_hash(dev.model_dump_json())}
    for name, attention in (("baseline", False), ("attention", True)):
        artifact = train_multi(
            dev,
            hybrid=True,
            encoder_spec=spec if attention else None,
            attention_epochs=5,
            n_estimators=100,
            domain_loss_weight=0,
        )
        raw = artifact.model_dump_json(indent=2)
        (args.output / (name + ".json")).write_text(raw, encoding="utf-8")
        hashes[name] = frozen_hash(raw)
        reports[name] = selection_report(dev, artifact)
        print(
            json.dumps(
                {
                    "stage": "offline_train_complete",
                    "model": name,
                    "dev_threshold_report": reports[name],
                }
            ),
            flush=True,
        )
    reports["previous_attention_on_same_dev_threshold"] = selection_report(
        dev, original
    )
    # Both artifacts are frozen before inspecting any fresh HOLDOUT scores.
    write(args.output / "frozen.json", hashes)
    write(args.output / "dev-comparison.json", reports)
    if (
        hashlib.sha256(args.serving.read_bytes()).hexdigest()
        != load(args.output / "recipe.json")["serving_artifact_sha256_before"]
    ):
        raise ValueError("Serving artifact unexpectedly changed")
    print(
        json.dumps(
            {
                "stage": "candidate_frozen",
                "samples": len(dev.samples),
                "excluded_input_rows": len(excluded),
                "serving_unchanged": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variants", type=Path)
    parser.add_argument(
        "--serving",
        type=Path,
        default=Path("config/router_attention_operator_accepted.json"),
    )
    run(parser.parse_args())
