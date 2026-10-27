"""Freeze DEV-only family calibration without reading HOLDOUT or changing serving."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from app.routing.family_calibration import fit_dev
from app.routing.ml.pipeline import atomic_text
from app.routing.ml.service import MLRouterService


def run(args):
    directory = args.directory
    output = directory / "calibration"
    if (output / "candidate.json").exists():
        raise ValueError("Frozen candidate already exists; never retune after HOLDOUT")
    job_id = json.loads((directory / "job.json").read_text())["job_id"]
    run = directory / "runs" / job_id
    rows = json.loads((run / "dev-observations.json").read_text())
    if len(rows) != 600:
        raise ValueError("All 600 DEV cases required before freezing candidate")
    originals = {}
    for row in rows:
        prepared = json.loads(
            (
                run
                / "prepared"
                / (hashlib.sha256(row["task_id"].encode()).hexdigest() + ".json")
            ).read_text()
        )
        originals[row["task_id"]] = prepared["original_messages"][0]["content"]
    engine = MLRouterService.load(args.artifact, allow_research_candidate=True)
    if not engine.multi.artifact or not engine.multi.semantic:
        raise ValueError("Existing ML + Attention must load; no retraining")
    manifest = json.loads((directory / "manifest.json").read_text())
    engine.multi.family_rates = {
        r["config_id"]: (
            Decimal(r["input_per_million"]),
            Decimal(r["output_per_million"]),
        )
        for r in manifest["costs"]["rates"]
    }
    result = fit_dev(rows, engine.multi, originals)
    output.mkdir(parents=True, exist_ok=True)
    atomic_text(
        output / "candidate.json",
        json.dumps(result["bundle_candidate"], ensure_ascii=False, indent=2),
    )
    atomic_text(
        output / "dev-report.json",
        json.dumps(
            {k: v for k, v in result.items() if k != "bundle_candidate"},
            ensure_ascii=False,
            indent=2,
        ),
    )
    frozen = {
        "candidate_file_sha256": hashlib.sha256(
            (output / "candidate.json").read_bytes()
        ).hexdigest(),
        "dev_file_sha256": hashlib.sha256(
            (run / "dev-observations.json").read_bytes()
        ).hexdigest(),
        "ml_artifact_hash": engine.hash,
        "holdout_read": False,
        "fit_complete": True,
        "groups_requiring_holdout": list(result["bundle_candidate"]["profiles"]),
    }
    atomic_text(output / "frozen.json", json.dumps(frozen, indent=2))
    print(json.dumps(frozen), flush=True)


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
