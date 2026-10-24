"""Train and Calibrate Vietnamese Multi-Task Router for smartllm-live-catalog-v2.

Trains on authentic Vietnamese multi-task benchmark sources & augmented domain queries:
- VMLU (Gold Train & Valid, multi-subject reasoning)
- UIT-ViQuAD 2.0 (Reading comprehension & extractive QA)
- Vietnamese Legal-QA (Civil, Labor, Enterprise, Commercial Law)
- PhoQA (Vietnamese multi-domain knowledge)
- Augmented Real Vietnamese Queries (dialogue_chat, coding_algorithms, math_reasoning)

Outputs calibrated model artifact to:
- config/router_multitask_vietnamese_model.json
- config/router_model.json
Evaluates strictly on unseen HOLDOUT with Pass Rate, Cost Savings %, Latency P50.
"""

import json
import time
from pathlib import Path

from app.contracts.representations import EncoderSpec
from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import (
    MultiDataset,
    evaluate_multi,
    train_multi,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dev_path = ROOT / "data/research/router-live-dev-v1.json"
    holdout_path = ROOT / "data/research/router-live-holdout-v1.json"
    encoder_path = ROOT / "config/encoder.minilm-int8.json"
    target_model_path = ROOT / "config/router_multitask_vietnamese_model.json"
    target_model_path_v2 = ROOT / "config/router_model.json"

    print("======================================================================")
    print("  VIETNAMESE MULTI-TASK ROUTER TRAINING PIPELINE (LIVE CATALOG V2)   ")
    print("======================================================================")

    if not dev_path.exists() or not holdout_path.exists():
        print("DEV/HOLDOUT datasets not found. Building fresh live catalog datasets...")
        from prepare_live_multitask_dataset import build_live_catalog_dataset

        dev, holdout, _ = build_live_catalog_dataset()
        dev_path.parent.mkdir(parents=True, exist_ok=True)
        dev_path.write_text(dev.model_dump_json(indent=2), encoding="utf-8")
        holdout_path.write_text(holdout.model_dump_json(indent=2), encoding="utf-8")
    else:
        print(f"Loading pre-split DEV dataset: {dev_path}")
        dev = MultiDataset.model_validate_json(dev_path.read_text(encoding="utf-8"))
        print(f"Loading pre-split HOLDOUT dataset: {holdout_path}")
        holdout = MultiDataset.model_validate_json(
            holdout_path.read_text(encoding="utf-8")
        )

    train_count = sum(s.split == "train" for s in dev.samples)
    calib_count = sum(s.split == "calibration" for s in dev.samples)
    thresh_count = sum(s.split == "threshold" for s in dev.samples)
    holdout_count = len(holdout.samples)

    print("\nDataset Split Breakdown (Zero-leakage partition):")
    print(f"  - Train:       {train_count:5d} samples (Model parameter updates)")
    print(
        f"  - Calibration: {calib_count:5d} samples (Isotonic probability calibration)"
    )
    print(f"  - Threshold:   {thresh_count:5d} samples (Pareto threshold tuning)")
    print(
        f"  - HOLDOUT:     {holdout_count:5d} samples (Strictly frozen test evaluation)"
    )
    print(
        f"  Total:         {train_count + calib_count + thresh_count + holdout_count:5d} samples"
    )

    spec = EncoderSpec.model_validate_json(
        encoder_path.read_text(encoding="utf-8")
    )

    print(
        "\n[Step 1/3] Training Hybrid Multi-Task Model (ML Head + CPU Attention Head)..."
    )
    t0 = time.perf_counter()
    v4_artifact = train_multi(
        dev,
        hybrid=True,
        encoder_spec=spec,
        attention_epochs=15,
        n_estimators=100,
        domain_loss_weight=0.0,
    )
    train_duration = time.perf_counter() - t0
    print(f"  -> Model trained successfully in {train_duration:.2f}s")

    v4_artifact = v4_artifact.model_copy(
        update={
            "model_version": "vietnamese-multitask-v4.2-live",
            "purpose": "qualified_dev",
        }
    )

    print(f"\n[Step 2/3] Saving model artifacts to:\n  - {target_model_path}\n  - {target_model_path_v2}...")
    artifact_json = v4_artifact.model_dump_json(indent=2)
    target_model_path.write_text(artifact_json, encoding="utf-8")
    target_model_path_v2.write_text(artifact_json, encoding="utf-8")
    model_size_kb = target_model_path.stat().st_size / 1024
    print(f"  -> Artifact written ({model_size_kb:.1f} KB).")

    print("\n[Step 3/3] Evaluating on Frozen HOLDOUT Dataset...")
    engine_v4 = MultiRouterService(v4_artifact.model_dump_json())
    eval_results = evaluate_multi(holdout, engine_v4)

    rep = eval_results.get("report", {})
    pass_rate = rep.get("observed_pass_rate", 0.0)
    serving_usd = float(rep.get("serving_usd", 0.0))
    reference_usd = float(rep.get("reference_usd", 0.0))
    savings_pct = (
        ((reference_usd - serving_usd) / reference_usd * 100)
        if reference_usd > 0
        else 0.0
    )
    p50_ratio = rep.get("p50_ratio", 1.0)

    print("\n======================================================================")
    print("                    HOLDOUT EVALUATION METRICS                        ")
    print("======================================================================")
    print(f"Observed Pass Rate:          {pass_rate * 100:.2f}% (Target: >= 97.0%)")
    print(f"Serving Cost:                ${serving_usd:.6f}")
    print(f"Reference Baseline Cost:     ${reference_usd:.6f}")
    print(f"Cost Savings:                {savings_pct:+.2f}%")
    print(f"Median Latency P50 Ratio:    {p50_ratio:.4f}x")

    assert pass_rate >= 0.97, f"Holdout Pass Rate {pass_rate * 100:.2f}% is below 97.0% threshold"

    print("\nModel Dispatch Distribution:")
    for k, v in rep.items():
        if k.startswith("selected:"):
            cid = k.replace("selected:", "")
            pct = (float(v) / holdout_count * 100) if holdout_count > 0 else 0
            print(f"  - {cid:35s}: {int(v):4d} requests ({pct:5.1f}%)")

    # Save evaluation summary
    summary_path = ROOT / "output/router-pilot/multitask_v4_holdout_report.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model_version": v4_artifact.model_version,
                "model_artifact": str(target_model_path.name),
                "holdout_samples": holdout_count,
                "pass_rate": pass_rate,
                "serving_usd": serving_usd,
                "reference_usd": reference_usd,
                "savings_pct": savings_pct,
                "p50_ratio": p50_ratio,
                "report": rep,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nReport saved to: {summary_path}")
    print("======================================================================")
    print(
        f"Training & Holdout Evaluation Complete! V4 Model: {target_model_path}"
    )
    print("======================================================================")


if __name__ == "__main__":
    main()
