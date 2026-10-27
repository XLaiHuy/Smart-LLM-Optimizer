"""Check a frozen research preview on unused CAL rows; never retune or activate."""

import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np
from app.routing.ml.multi_training import MultiSample
from app.routing.ml.service import MLRouterService
from sklearn.feature_extraction.text import TfidfVectorizer

p = Path("/app/data/router-task-family-v1-20261027")
candidate = p / "threshold-preview-450/candidate.json"
preview = json.loads(candidate.read_text())
output = candidate.with_name("unused-calibration-check.json")
if output.exists():
    raise ValueError("Do not repeatedly inspect or retune this check")
job = json.loads((p / "job.json").read_text())["job_id"]
folder = p / "runs" / job
raw = (folder / "dev-observations.json").read_bytes()
if hashlib.sha256(raw).hexdigest() != preview["dev_file_sha256"]:
    raise ValueError("DEV changed after fitting preview")
engine = MLRouterService.load(
    Path("/app/config/router_attention_operator_accepted.json"),
    allow_research_candidate=True,
)
if engine.hash != preview["ml_artifact_hash"]:
    raise ValueError("Frozen engine changed")
manifest = json.loads((folder / "manifest.json").read_text())
rates = {
    r["config_id"]: (Decimal(r["input_per_million"]), Decimal(r["output_per_million"]))
    for r in manifest["costs"]["rates"]
}
cfg = preview["classifier"]
vectorizer = TfidfVectorizer(vocabulary=cfg["vocabulary"], ngram_range=(1, 2))
vectorizer.idf_ = np.asarray(cfg["idf"])
reports = {
    f: {
        "groups": 0,
        "recognized_groups": 0,
        "prior_correct": 0,
        "candidate_correct": 0,
        "regressions": 0,
        "gains": 0,
        "prior_usd": Decimal(0),
        "candidate_usd": Decimal(0),
        "distribution": Counter(),
    }
    for f in preview["reports"]
}
for raw_row in json.loads(raw):
    if raw_row["split"] != "calibration":
        continue
    row = MultiSample.model_validate(raw_row)
    original = json.loads(
        (
            folder
            / "prepared"
            / (hashlib.sha256(row.task_id.encode()).hexdigest() + ".json")
        ).read_text()
    )["original_messages"][0]["content"]
    vector = vectorizer.transform([original])
    logits = np.asarray((vector @ np.asarray(cfg["coefficients"]).T)[0]) + np.asarray(
        cfg["intercepts"]
    )
    prob = np.exp(logits - logits.max())
    prob /= prob.sum()
    ordered = np.sort(prob)
    family = (
        cfg["classes"][int(prob.argmax())]
        if max(prob) >= 0.8 and ordered[-1] - ordered[-2] >= 0.2
        else "unknown"
    )
    scores = {
        c: engine.multi.score(c, row.context(), False, False)
        for c in preview["current_thresholds"]
    }
    bound = sum(len(m.content.encode()) + 64 for m in row.messages) + 128
    prices = {
        c.config_id: Decimal(bound) * rates[c.config_id][0]
        + Decimal(c.max_output_tokens) * rates[c.config_id][1]
        for c in engine.multi.artifact.configurations
    }
    reference = engine.multi.artifact.reference_config_id
    eligible = sorted(
        [c for c in scores if prices[c] < prices[reference]],
        key=lambda c: (prices[c], c),
    )
    prior = next(
        (c for c in eligible if scores[c] >= preview["current_thresholds"][c]),
        reference,
    )
    thresholds = (
        preview["reports"][family]["thresholds"]
        if family in preview["reports"]
        else None
    )
    selected = (
        next((c for c in eligible if scores[c] >= thresholds[c]), reference)
        if thresholds
        else prior
    )
    obs = {o.config_id: o for o in row.observations}
    report = reports[row.domain]
    report["groups"] += 1
    report["recognized_groups"] += family == row.domain
    report["prior_correct"] += obs[prior].qualified
    report["candidate_correct"] += obs[selected].qualified
    report["regressions"] += obs[prior].qualified and not obs[selected].qualified
    report["gains"] += not obs[prior].qualified and obs[selected].qualified
    report["prior_usd"] += obs[prior].usd
    report["candidate_usd"] += obs[selected].usd
    report["distribution"][selected] += 1
for report in reports.values():
    report["survived_this_dev_check"] = (
        report["regressions"] == 0
        and report["candidate_correct"] >= report["prior_correct"]
        and report["candidate_usd"] < report["prior_usd"]
    )
    report["prior_usd"] = str(report["prior_usd"])
    report["candidate_usd"] = str(report["candidate_usd"])
result = {
    "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
    "reports": reports,
    "thresholds_retuned": False,
    "holdout_used": False,
    "serving_activation": False,
    "scope": "unused DEV calibration split; not formal HOLDOUT or serving pilot",
}
output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result), flush=True)
