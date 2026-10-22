"""DEV threshold sensitivity only. Never optimize a frozen HOLDOUT."""

import argparse
import json
from pathlib import Path

from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import MultiDataset, replay_rows, report_replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=Path("data/research/router-final-dev-v3.json")
    )
    parser.add_argument(
        "--model", type=Path, default=Path("config/router_final_candidate.json")
    )
    args = parser.parse_args()
    dataset = MultiDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
    if any(r.split == "holdout" for r in dataset.samples):
        raise ValueError("Threshold sensitivity must not read HOLDOUT")
    service = MultiRouterService(args.model.read_text(encoding="utf-8"))
    if not service.artifact:
        raise ValueError("Artifact unavailable")
    rows = tuple(r for r in dataset.samples if r.split == "threshold")
    if not rows:
        raise ValueError("DEV threshold split required")
    replay = replay_rows(dataset, service, rows)
    reports = {
        str(th): report_replay(
            replay,
            dataset.reference_config_id,
            {p.config_id: th for p in service.artifact.predictors},
        )
        for th in [1.0, 0.98, 0.95, 0.9, 0.8, 0.5]
    }
    print(
        json.dumps(
            {
                "purpose": dataset.purpose,
                "split": "threshold",
                "simulation_only": dataset.purpose == "software_test",
                "reports": reports,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
