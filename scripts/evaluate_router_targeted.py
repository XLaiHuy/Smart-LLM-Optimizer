"""Evaluate once on the fresh sealed source groups after artifacts are frozen.

No provider calls, model fitting, threshold changes or serving promotion.
"""

import argparse
import hashlib
import json
import socket
from collections import Counter
from pathlib import Path

from analyze_router_errors import load, write
from app.contracts.training import TrainingCorpus, TrainingManifest
from app.routing.ml.multi_training import MultiSample
from app.routing.ml.pilot import dataset, paired_comparison, timed_evaluate
from app.routing.ml.qualification import regression_upper_95


def sealed_test(campaign, collection, trained):
    frozen = load(trained / "frozen.json")
    for name in ("baseline", "attention"):
        # Training freezes UTF-8 JSON text; normalize platform CRLF identically.
        if (
            hashlib.sha256(
                (trained / (name + ".json")).read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            != frozen[name]
        ):
            raise ValueError("Frozen artifact changed; do not inspect HOLDOUT")
    source = campaign / "sealed-fresh-holdout.json"
    if (
        hashlib.sha256(source.read_bytes()).hexdigest()
        != load(campaign / "plan.json")["holdout_sha256"]
    ):
        raise ValueError("Sealed test source changed")
    gold = TrainingCorpus.model_validate_json(source.read_text(encoding="utf-8"))
    manifest = TrainingManifest.model_validate(load(collection / "manifest.json"))
    measured = load(collection / "observations.json")
    if len(measured) != manifest.max_samples:
        raise ValueError("Full frozen collection required")
    observed = {s["task_id"]: s for s in measured}
    dev_groups = {s["group_id"] for s in load(trained / "dev.json")["samples"]}
    rows = []
    for original in gold.samples:
        raw = observed.get("source-0:" + original.task_id)
        if not raw:
            raise ValueError("Missing fresh test observation")
        row = MultiSample.model_validate(raw)
        if (
            row.messages != original.messages
            or row.group_id != original.group_id
            or row.domain != original.domain
            or row.split != "holdout"
            or row.group_id in dev_groups
        ):
            raise ValueError("Test input/group mismatch or training leakage")
        rows.append(row)
    return dataset(manifest, rows)


def run(args):
    if args.report.exists():
        raise ValueError("Do not overwrite an already observed test report")
    holdout = sealed_test(args.campaign, args.collection, args.trained)

    def deny(*a, **kw):
        raise RuntimeError("Offline evaluation forbids network")

    socket.socket.connect = deny
    socket.getaddrinfo = deny
    reports = {}
    for name, path in (
        ("new_ml", args.trained / "baseline.json"),
        ("new_attention", args.trained / "attention.json"),
        ("previous_attention", args.previous / "artifact.json"),
    ):
        reports[name] = timed_evaluate(holdout, path.read_text(encoding="utf-8"))
    summary = {}
    for name, report in reports.items():
        domains = {}
        for row in report["outcomes"]:
            values = domains.setdefault(
                row["domain"],
                Counter(n=0, correct=0, reference_correct=0, regressions=0),
            )
            values["n"] += 1
            values["correct"] += int(row["qualified"])
            values["reference_correct"] += int(row["reference_qualified"])
            values["regressions"] += int(
                row["reference_qualified"] and not row["qualified"]
            )
        summary[name] = {
            domain: {
                **counts,
                "regression_upper_95": regression_upper_95(
                    counts["regressions"], counts["n"]
                ),
            }
            for domain, counts in domains.items()
        }
    result = {
        "conclusion": "DESCRIPTIVE_FRESH_TEST_ONLY",
        "live_approved": False,
        "source_counts": dict(Counter(r.domain for r in holdout.samples)),
        "domains": summary,
        "reports": reports,
        "attention_vs_new_ml": paired_comparison(
            reports["new_ml"], reports["new_attention"]
        ),
        "attention_vs_previous_attention": paired_comparison(
            reports["previous_attention"], reports["new_attention"]
        ),
        "no_retuning_after_test": True,
        "limitations": [
            "Only 10 fresh Vietnamese MCQ groups available; cannot certify the previous 3% regression guard",
            "No E2E serving pilot or production approval",
            "Unresolved billing reserve remains; never infer zero cost",
            "TRAIN option variants are not independent test cases",
        ],
    }
    write(args.report, result)
    print(
        json.dumps(
            {"report": str(args.report), "domains": summary, "live_approved": False}
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--trained", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    run(parser.parse_args())
