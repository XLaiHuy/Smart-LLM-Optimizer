"""Replay the frozen second-round router on source-family-independent live labels.

Offline only. Missing cases block full evaluation; partial results never authorize
serving. Reuse is restricted to exact messages, generation and price settings.
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.contracts.training import TrainingCorpus, TrainingManifest
from app.routing.ml.multi_training import MultiSample
from app.routing.ml.pilot import dataset, paired_comparison, timed_evaluate
from app.routing.ml.pipeline import atomic_text
from app.routing.ml.qualification import regression_upper_95


def available_holdout(campaign: Path):
    manifest = TrainingManifest.model_validate_json(
        (campaign / "family-deduplicated/manifest.json").read_text(encoding="utf-8")
    )
    corpus = TrainingCorpus.model_validate_json(
        (campaign / "family-deduplicated/corpus.json").read_text(encoding="utf-8")
    )
    plan = json.loads(
        (campaign / "independent-family-plan.json").read_text(encoding="utf-8")
    )
    expected_groups = set(plan["mcq_holdout_families"]) | set(
        plan["fresh_math_holdout_groups"]
    )
    source_tests = [r for r in corpus.samples if r.split == "holdout"]
    if (
        len(source_tests) != 200
        or {r.group_id for r in source_tests} != expected_groups
    ):
        raise ValueError("Frozen independent test plan changed")
    observed: dict[str, dict[str, Any]] = {}
    for path in sorted((campaign / "runs").glob("*/observations.json")):
        prior_manifest = TrainingManifest.model_validate_json(
            (path.parent / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            prior_manifest.configurations != manifest.configurations
            or prior_manifest.costs != manifest.costs
        ):
            raise ValueError("Response generation or price configuration changed")
        for row in json.loads(path.read_text(encoding="utf-8")):
            observed.setdefault(row["task_id"], row)
    rows: list[MultiSample] = []
    missing: list[dict[str, str]] = []
    for source in source_tests:
        raw = observed.get("source-0:" + source.task_id)
        if raw is None:
            missing.append({"task_id": source.task_id, "domain": source.domain})
            continue
        row = MultiSample.model_validate(raw)
        if row.messages != source.messages or row.domain != source.domain:
            raise ValueError(
                "Exact source input or domain did not match measured response"
            )
        rows.append(
            row.model_copy(update={"group_id": source.group_id, "split": "holdout"})
        )
    return dataset(manifest, rows) if rows else None, missing


def run(args):
    if args.report.exists():
        raise ValueError(
            "Use a new report path; earlier test evidence remains immutable"
        )
    holdout, missing = available_holdout(args.campaign)
    if missing and not args.partial:
        raise ValueError(
            f"Independent test is incomplete: {len(missing)} of 200 families missing; resume the existing collection job"
        )
    if holdout is None:
        raise ValueError("No measured independent cases available")
    trained = args.campaign / "trained"
    if not (trained / "frozen.json").exists():
        raise ValueError("Freeze both artifacts before reading test scores")
    ml = timed_evaluate(
        holdout, (trained / "baseline.json").read_text(encoding="utf-8")
    )
    attention = timed_evaluate(
        holdout, (trained / "artifact.json").read_text(encoding="utf-8")
    )
    domains: dict[str, Counter[str]] = {}
    for row in attention["outcomes"]:
        group = domains.setdefault(
            row["domain"],
            Counter(n=0, reference_pass=0, attention_pass=0, regressions=0),
        )
        group["n"] += 1
        group["reference_pass"] += int(row["reference_qualified"])
        group["attention_pass"] += int(row["qualified"])
        group["regressions"] += int(row["reference_qualified"] and not row["qualified"])
    summary = {
        domain: {
            **counts,
            "regression_upper_95": regression_upper_95(
                counts["regressions"], counts["n"]
            ),
        }
        for domain, counts in domains.items()
    }
    result = {
        "conclusion": "INSUFFICIENT_EVIDENCE"
        if missing
        else "OBSERVED_REPLAY_REQUIRES_FORMAL_QUALIFICATION",
        "live_approved": False,
        "partial": bool(missing),
        "expected_test_families": 200,
        "available_test_families": len(holdout.samples),
        "missing_test_families": len(missing),
        "missing": missing,
        "domains": summary,
        "ml_without_attention": ml,
        "attention": attention,
        "paired_comparison": paired_comparison(ml, attention),
        "no_retuning_after_this_test": True,
    }
    atomic_text(args.report, json.dumps(result, ensure_ascii=False, indent=2))
    atomic_text(
        args.report.with_suffix(".holdout.json"), holdout.model_dump_json(indent=2)
    )
    print(
        json.dumps(
            {
                "report": str(args.report),
                "partial": bool(missing),
                "domains": summary,
                "live_approved": False,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Descriptive partial report only; cannot authorize serving",
    )
    run(parser.parse_args())
