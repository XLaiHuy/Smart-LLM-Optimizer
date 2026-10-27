"""Package only independently passed families, validate with the serving loader.

Writes a reviewable output directory, never the active config. Operator deployment
is a separate step after checks; no source/weights/thresholds are edited in place.
"""

import argparse
import hashlib
import json
from pathlib import Path

from app.routing.ml.pipeline import atomic_text
from app.routing.ml.service import MLRouterService
from app.routing.task_groups import TaskGroupPolicy, content_hash


def run(args):
    directory = args.directory
    candidate_path = directory / "calibration/candidate.json"
    frozen = json.loads((directory / "calibration/frozen.json").read_text())
    if (
        hashlib.sha256(candidate_path.read_bytes()).hexdigest()
        != frozen["candidate_file_sha256"]
    ):
        raise ValueError("Frozen candidate changed")
    bundle = json.loads(candidate_path.read_text())
    offline = json.loads((directory / "calibration/holdout-report.json").read_text())
    pilot = json.loads((directory / "serving-pilot/report.json").read_text())
    if offline["candidate_sha256"] != content_hash(bundle):
        raise ValueError("HOLDOUT belongs to another candidate")
    job = json.loads((directory / "job.json").read_text())["job_id"]
    dev = json.loads((directory / "runs" / job / "dev-observations.json").read_text())
    dev_groups = [r["group_id"] for r in dev]
    if args.output.exists():
        raise ValueError("Do not overwrite packaged evidence")
    args.output.mkdir(parents=True)
    approved = {}
    for family, profile in bundle["profiles"].items():
        report = offline["reports"][family]
        live = pilot["families"].get(family)
        if not report["offline_pass"] or not live or not live["passed"]:
            continue
        payload = {
            k: v
            for k, v in profile.items()
            if k not in ("evidence_path", "evidence_sha256")
        }
        evidence = {
            **report,
            "family": family,
            "thresholds": profile["thresholds"],
            "profile_sha256": content_hash(payload),
            "classifier_sha256": content_hash(bundle["classifier"]),
            "ml_artifact_hash": bundle["ml_artifact_hash"],
            "configuration_hashes": bundle["configuration_hashes"],
            "costs_hash": bundle["costs_hash"],
            "latency_scope": "serving_e2e",
            "all_in_p50_ratio": live["all_in_p50_ratio"],
            "serving_pilot": live,
            "dev_group_ids": dev_groups,
            "synthetic": False,
            "reviewed_by": "automated deterministic source-gold protocol under Huy authorization; not a human outcome review",
            "grader_review_id": profile["grader_review_id"],
            "holdout_file_sha256": offline["holdout_file_sha256"],
            "candidate_frozen_file_sha256": frozen["candidate_file_sha256"],
        }
        relative = Path("task_family_evidence") / "v1" / (family + ".json")
        raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()
        path = args.output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        approved[family] = {
            **profile,
            "evidence_path": relative.as_posix(),
            "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        }
    if not approved:
        raise ValueError("No family passed all gates; retain prior serving policy")
    bundle["profiles"] = approved
    bundle["policy_version"] = "family-calibration-v1-qualified-groups"
    path = args.output / "task_routing_profiles.json"
    atomic_text(path, json.dumps(bundle, ensure_ascii=False, separators=(",", ":")))
    engine = MLRouterService.load(args.artifact, allow_research_candidate=True)
    checked = TaskGroupPolicy(path, engine)
    if checked.status != "GROUP_POLICY_READY":
        raise ValueError("Serving loader rejected packaged evidence; do not deploy")
    result = {
        "groups": sorted(approved),
        "scope": "single-turn no memory/tools",
        "serving_loader": checked.status,
        "artifact_changed": False,
        "deployed": False,
        "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    atomic_text(args.output / "package-report.json", json.dumps(result, indent=2))
    print(json.dumps(result))


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
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
