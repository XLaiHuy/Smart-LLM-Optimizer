"""DEV-only diagnostics after a user-requested stop; never qualifies a policy."""

from collections import Counter, defaultdict
from typing import Any


def diagnose(rows: list[dict[str, Any]], config_ids: set[str]) -> dict[str, Any]:
    families = ("exact_arithmetic", "structured_extraction", "vietnamese_qa")
    required = {"train": 100, "calibration": 50, "threshold": 50}
    if len({r["task_id"] for r in rows}) != len(rows) or len({r["group_id"] for r in rows}) != len(
        rows
    ):
        raise ValueError("Duplicate DEV task/source group")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    metrics: dict[str, Any] = {}
    for row in rows:
        family, split = row["domain"], row["split"]
        if family not in families or split not in required:
            raise ValueError("Diagnostics accepts only frozen DEV families/splits")
        observations = row["observations"]
        if (
            len(observations) != len(config_ids)
            or {o["config_id"] for o in observations} != config_ids
        ):
            raise ValueError("Missing or duplicated paired model observation")
        counts[family][split] += 1
        for observation in observations:
            if type(observation["qualified"]) is not bool:
                raise ValueError("Invalid source-grader verdict")
            key = family + "/" + observation["config_id"]
            metric = metrics.setdefault(key, {"observed": 0, "correct": 0, "failed_task_ids": []})
            metric["observed"] += 1
            metric["correct"] += observation["qualified"]
            if not observation["qualified"]:
                metric["failed_task_ids"].append(row["task_id"])
    missing = {f: {s: max(0, n - counts[f][s]) for s, n in required.items()} for f in families}
    return {
        "measurement_scope": "exploratory_DEV_only_not_quality_certification",
        "completed": len(rows),
        "required_dev": 600,
        "counts": {f: dict(counts[f]) for f in families},
        "missing_dev": missing,
        "model_diagnostics": metrics,
        "holdout_read": False,
        "calibration_ready": len(rows) == 600
        and not any(v for f in missing.values() for v in f.values()),
        "trained": False,
        "live_qualified": False,
        "serving_changed": False,
    }
