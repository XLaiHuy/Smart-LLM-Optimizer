"""Compatibility command: evaluate frozen candidate once; no HOLDOUT threshold tuning."""

import json
from pathlib import Path

from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import MultiDataset, evaluate_multi

ROOT = Path(__file__).resolve().parents[1]


def main():
    dataset = MultiDataset.model_validate_json(
        (ROOT / "data/research/router-final-holdout-v3.json").read_text(
            encoding="utf-8"
        )
    )
    engine = MultiRouterService(
        (ROOT / "config/router_final_candidate.json").read_text(encoding="utf-8")
    )
    report = evaluate_multi(dataset, engine)
    report["limitations"] = [
        "SOFTWARE TEST: labels, costs and latency are simulated",
        "No live quality, real savings or CUDA speed conclusion",
    ]
    output = ROOT / "output/router-final/holdout.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
