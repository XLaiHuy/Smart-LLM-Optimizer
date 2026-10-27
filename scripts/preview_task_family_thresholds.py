"""User-authorized 450-case exploratory fit; no API calls or serving writes."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from app.routing.family_threshold_preview import explore
from app.routing.ml.service import MLRouterService


def run(directory):
    status = json.loads((directory / "status.json").read_text())
    if status["status"] == "running" or status["completed"] != 450:
        raise ValueError("Stopped 450-case checkpoint required")
    job = json.loads((directory / "job.json").read_text())["job_id"]
    folder = directory / "runs" / job
    raw = (folder / "dev-observations.json").read_bytes()
    rows = json.loads(raw)
    if len(rows) != 450:
        raise ValueError("450 complete DEV rows required")
    originals = {
        r["task_id"]: json.loads(
            (
                folder
                / "prepared"
                / (hashlib.sha256(r["task_id"].encode()).hexdigest() + ".json")
            ).read_text()
        )["original_messages"][0]["content"]
        for r in rows
    }
    manifest = json.loads((folder / "manifest.json").read_text())
    rates = {
        r["config_id"]: (
            Decimal(r["input_per_million"]),
            Decimal(r["output_per_million"]),
        )
        for r in manifest["costs"]["rates"]
    }
    engine = MLRouterService.load(
        Path("/app/config/router_attention_operator_accepted.json"),
        allow_research_candidate=True,
    )
    output = directory / "threshold-preview-450"
    output.mkdir(exist_ok=True)
    if (output / "candidate.json").exists():
        raise ValueError("Preview already exists; do not overwrite")
    result = explore(rows, engine.multi, originals, rates)
    result["dev_file_sha256"] = hashlib.sha256(raw).hexdigest()
    # sklearn vocabulary indices can be numpy integer values.
    (output / "candidate.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=lambda v: int(v))
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("classifier", "examples")},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("/app/data/router-task-family-v1-20261027"),
    )
    run(parser.parse_args().directory)
