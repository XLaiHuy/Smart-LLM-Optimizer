"""One frozen candidate, fresh HOLDOUT replay. Never tunes, promotes or calls APIs."""

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from app.contracts.dtos import (
    ChatRequest,
    RemainingBudget,
    RouteDecision,
    RouteEstimate,
)
from app.contracts.training import TrainingManifest
from app.routing.features import extract_context_features
from app.routing.ml.multi_training import MultiDataset, MultiSample, replay_rows
from app.routing.ml.pipeline import atomic_text, cache_key
from app.routing.ml.qualification import regression_upper_95
from app.routing.ml.service import MLRouterService
from app.routing.task_groups import TaskGroupPolicy, content_hash


def run(args):
    directory = args.directory
    folder = directory / "calibration"
    frozen = json.loads((folder / "frozen.json").read_text())
    raw = (folder / "candidate.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != frozen["candidate_file_sha256"]:
        raise ValueError("Candidate changed after freezing")
    if (folder / "holdout-report.json").exists():
        raise ValueError(
            "HOLDOUT already evaluated; no retuning or repeated evaluation"
        )
    bundle = json.loads(raw)
    job = json.loads((directory / "job.json").read_text())["job_id"]
    run = directory / "runs" / job
    rows = json.loads((run / "holdout-observations.json").read_text())
    if len(rows) != 300:
        raise ValueError("Complete 300-group HOLDOUT required")
    manifest = json.loads((directory / "manifest.json").read_text())
    frozen_manifest = TrainingManifest.model_validate(manifest)
    data = MultiDataset(
        format_version="router-dataset-v2",
        version=manifest["version"],
        purpose="research_candidate",
        provenance=json.dumps(manifest),
        grader_version="router-gold-graders-v1",
        configurations=manifest["configurations"],
        reference_config_id=manifest["reference_config_id"],
        costs=manifest["costs"],
        samples=tuple(MultiSample.model_validate(row) for row in rows),
    )
    engine = MLRouterService.load(args.artifact, allow_research_candidate=True)
    if engine.hash != frozen["ml_artifact_hash"] or not engine.multi.artifact:
        raise ValueError("Serving engine changed")
    # Offline-only evaluator object. This is never returned to a serving container
    # or serialized as a qualified artifact. Real loader still requires pilot evidence.
    policy = TaskGroupPolicy(Path("__absent_evaluator_policy__"), engine)
    policy.bundle = bundle
    thresholds = {p.config_id: p.threshold for p in engine.multi.artifact.predictors}
    reports = {
        family: {
            "holdout": [],
            "policy_serving_usd": Decimal(0),
            "prior_serving_usd": Decimal(0),
            "policy_distribution": {},
            "prior_distribution": {},
        }
        for family in ("exact_arithmetic", "structured_extraction", "vietnamese_qa")
    }
    export = []
    for row, scores, order in replay_rows(data, engine.multi, data.samples):
        original = json.loads(
            (
                run
                / "prepared"
                / (hashlib.sha256(row.task_id.encode()).hexdigest() + ".json")
            ).read_text()
        )["original_messages"][0]["content"]
        prior = next(
            (c for c in order if scores[c] >= thresholds[c]), data.reference_config_id
        )
        bound = sum(len(m.content.encode()) + 64 for m in row.messages) + 128
        rates = {r.config_id: r for r in data.costs.rates}
        prices = {
            c.config_id: (
                Decimal(bound) * rates[c.config_id].input_per_million
                + Decimal(c.max_output_tokens) * rates[c.config_id].output_per_million
            )
            / Decimal(1000000)
            for c in data.configurations
        }
        route = RouteDecision(
            model_id=next(
                c.model_id for c in data.configurations if c.config_id == prior
            ),
            config_id=prior,
            policy_id="frozen-prior",
            ml_executed=True,
            estimates=tuple(
                RouteEstimate(config_id=c, input_bound=bound, upper_usd=amount)
                for c, amount in prices.items()
            ),
        )
        task = policy.classify(
            ChatRequest(
                session_id="offline",
                client_request_id=row.task_id,
                message=original,
                mode="optimized",
            )
        )
        task["single_turn_empty_memory"] = True
        result = policy.apply(
            task,
            route,
            row.context(),
            extract_context_features(row.messages, False),
            RemainingBudget(),
        )
        chosen = result.config_id
        observations = {o.config_id: o for o in row.observations}
        a, b = observations[prior], observations[chosen]
        family = reports[row.domain]
        family["holdout"].append(
            {
                "group_id": row.group_id,
                "task_id": row.task_id,
                "prior_pass": a.qualified,
                "policy_pass": b.qualified,
                "critical_regression": row.critical and a.qualified and not b.qualified,
                "selected_config_id": chosen,
                "classified_family": task["family"],
                "classifier_source": task["source"],
                "profile_applied": result.group_profile_applied,
            }
        )
        family["policy_serving_usd"] += b.usd
        family["prior_serving_usd"] += a.usd
        for name, config in (
            ("policy_distribution", chosen),
            ("prior_distribution", prior),
        ):
            family[name][config] = family[name].get(config, 0) + 1
        export.append(
            {
                "task_id": row.task_id,
                "group": row.domain,
                "prompt": original,
                "response": json.loads(
                    (
                        directory
                        / "runs"
                        / "cache"
                        / (cache_key(frozen_manifest, chosen, row.messages) + ".json")
                    ).read_text()
                )["text"],
                "selected_config_id": chosen,
                "prior_config_id": prior,
                "quality_pass": b.qualified,
                "input_tokens": b.input_tokens,
                "output_tokens": b.output_tokens,
                "usd": str(b.usd),
                "provider_ms": b.latency_ms,
                "ml_scores": json.dumps(scores),
                "thresholds": json.dumps(result.group_thresholds),
                "measurement_scope": "measured provider replay; not E2E",
            }
        )
    for family, report in reports.items():
        rows = report["holdout"]
        regressions = sum(r["prior_pass"] and not r["policy_pass"] for r in rows)
        report.update(
            regressions=regressions,
            regression_upper_95=regression_upper_95(regressions, len(rows)),
            prior_correct=sum(r["prior_pass"] for r in rows),
            policy_correct=sum(r["policy_pass"] for r in rows),
            independent_groups=len({r["group_id"] for r in rows}),
            serving_pilot_required=True,
            serving_activation=False,
        )
        report["offline_pass"] = bool(
            family in bundle["profiles"]
            and report["independent_groups"] >= 100
            and report["regression_upper_95"] <= 0.03
            and report["policy_correct"] >= report["prior_correct"]
            and not any(r["critical_regression"] for r in rows)
            and report["policy_serving_usd"] < report["prior_serving_usd"]
        )
        for key in ("policy_serving_usd", "prior_serving_usd"):
            report[key] = str(report[key])
    output = {
        "candidate_sha256": content_hash(bundle),
        "ml_artifact_hash": engine.hash,
        "holdout_file_sha256": hashlib.sha256(
            (run / "holdout-observations.json").read_bytes()
        ).hexdigest(),
        "reports": reports,
        "provider_calls": 0,
        "serving_activation": False,
        "status": "OFFLINE_PASS_REQUIRES_PILOT"
        if any(r["offline_pass"] for r in reports.values())
        else "RETAIN_CURRENT_POLICY",
    }
    atomic_text(
        folder / "holdout-report.json", json.dumps(output, ensure_ascii=False, indent=2)
    )
    with (folder / "prompt-routing-table.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(export[0]))
        writer.writeheader()
        writer.writerows(export)
    print(
        json.dumps(
            {
                "status": output["status"],
                "family_pass": {f: r["offline_pass"] for f, r in reports.items()},
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("/app/data/router-task-family-v1-20261027"),
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=Path("/app/config/router_attention_operator_accepted.json"),
    )
    run(parser.parse_args())
