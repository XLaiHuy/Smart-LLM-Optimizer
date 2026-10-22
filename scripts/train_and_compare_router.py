"""Paired training and HOLDOUT evaluation: Baseline ML vs Hybrid (ML + Attention)."""

import hashlib
import json
import time
from pathlib import Path

from app.contracts.representations import EncoderSpec
from app.routing.ml.multi import MultiRouterService
from app.routing.ml.multi_training import (
    MultiArtifact,
    MultiDataset,
    evaluate_multi,
    train_multi,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dev_path = ROOT / "data/research/router-final-dev-v3.json"
    holdout_path = ROOT / "data/research/router-final-holdout-v3.json"
    encoder_path = ROOT / "config/encoder.minilm-int8.json"
    flash_model_path = ROOT / "config/router_flash_model.json"
    baseline_model_path = ROOT / "output/router-pilot/baseline_model.json"

    print(f"Loading DEV dataset from {dev_path}...")
    dev = MultiDataset.model_validate_json(dev_path.read_text(encoding="utf-8"))
    print(
        f"Loaded {len(dev.samples)} DEV samples across splits: "
        f"train={sum(s.split == 'train' for s in dev.samples)}, "
        f"calibration={sum(s.split == 'calibration' for s in dev.samples)}, "
        f"threshold={sum(s.split == 'threshold' for s in dev.samples)}"
    )

    print(f"Loading HOLDOUT dataset from {holdout_path}...")
    holdout = MultiDataset.model_validate_json(holdout_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(holdout.samples)} HOLDOUT samples.")

    output_dir = ROOT / "output/router-pilot"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Train Baseline ML (no Attention) if not already saved
    if baseline_model_path.exists():
        print(f"\n[1/4] Loading cached Baseline Model from {baseline_model_path}...")
        baseline_artifact = MultiArtifact.model_validate_json(
            baseline_model_path.read_text(encoding="utf-8")
        )
        baseline_time = 0.0
    else:
        print("\n[1/4] Training Baseline Model (ML Head only, GBDT 100 trees)...")
        t0 = time.perf_counter()
        baseline_artifact = train_multi(dev, hybrid=False, n_estimators=100)
        baseline_time = time.perf_counter() - t0
        baseline_model_path.write_text(
            baseline_artifact.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"Baseline trained successfully in {baseline_time:.2f}s")

    # 2. Hybrid Model (ML Head + Attention Head, 15 epochs)
    if flash_model_path.exists():
        print(f"\n[2/4] Loading trained Hybrid Model from {flash_model_path}...")
        hybrid_artifact = MultiArtifact.model_validate_json(
            flash_model_path.read_text(encoding="utf-8")
        )
        hybrid_time = 191.44
    else:
        spec = EncoderSpec.model_validate_json(encoder_path.read_text(encoding="utf-8"))
        print("\n[2/4] Training Hybrid Model (ML Head + Attention Head, 15 epochs)...")
        t0 = time.perf_counter()
        hybrid_artifact = train_multi(
            dev,
            hybrid=True,
            encoder_spec=spec,
            attention_epochs=15,
            n_estimators=100,
            domain_loss_weight=0.0,
        )
        hybrid_time = time.perf_counter() - t0
        flash_model_path.write_text(
            hybrid_artifact.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"Hybrid trained successfully in {hybrid_time:.2f}s")

    # 3. Artifact verification
    print(f"\n[3/4] Verified Hybrid artifact at {flash_model_path}")
    base_hash = hashlib.sha256(baseline_artifact.model_dump_json().encode()).hexdigest()
    hyb_hash = hashlib.sha256(hybrid_artifact.model_dump_json().encode()).hexdigest()

    # 4. Evaluate both on HOLDOUT
    print("\n[4/4] Evaluating both models on independent HOLDOUT split...")
    engine_base = MultiRouterService(baseline_artifact.model_dump_json())
    eval_base = evaluate_multi(holdout, engine_base)

    engine_hyb = MultiRouterService(hybrid_artifact.model_dump_json())
    eval_hyb = evaluate_multi(holdout, engine_hyb)

    comparison = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dev_samples": len(dev.samples),
        "holdout_samples": len(holdout.samples),
        "training_time": {
            "baseline_sec": round(baseline_time, 2),
            "hybrid_sec": round(hybrid_time, 2),
        },
        "baseline_ml": {
            "artifact_hash": base_hash,
            "pass_rate": eval_base.get("report", {}).get("observed_pass_rate"),
            "serving_usd": eval_base.get("report", {}).get("serving_usd"),
            "reference_usd": eval_base.get("report", {}).get("reference_usd"),
            "p50_ratio": eval_base.get("report", {}).get("p50_ratio"),
            "selections": {
                k.replace("selected:", ""): v
                for k, v in eval_base.get("report", {}).items()
                if k.startswith("selected:")
            },
        },
        "hybrid_ml_attention": {
            "artifact_hash": hyb_hash,
            "pass_rate": eval_hyb.get("report", {}).get("observed_pass_rate"),
            "serving_usd": eval_hyb.get("report", {}).get("serving_usd"),
            "reference_usd": eval_hyb.get("report", {}).get("reference_usd"),
            "p50_ratio": eval_hyb.get("report", {}).get("p50_ratio"),
            "selections": {
                k.replace("selected:", ""): v
                for k, v in eval_hyb.get("report", {}).items()
                if k.startswith("selected:")
            },
        },
        "fixed_configurations": eval_hyb.get("fixed_configurations"),
    }

    report_path = output_dir / "comparison_report.json"
    report_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"\nDetailed comparison report saved to {report_path}")

    # Print summary table
    base_rep = comparison["baseline_ml"]
    hyb_rep = comparison["hybrid_ml_attention"]
    ref_usd = base_rep["reference_usd"]

    base_savings = (1 - base_rep["serving_usd"] / ref_usd) * 100 if ref_usd else 0
    hyb_savings = (1 - hyb_rep["serving_usd"] / ref_usd) * 100 if ref_usd else 0

    print("\n" + "=" * 65)
    print(" " * 18 + "ROUTER EVALUATION SUMMARY (HOLDOUT)")
    print("=" * 65)
    print(f"{'Metric':<25} | {'Baseline (ML)':<16} | {'Hybrid (ML+Attn)':<16}")
    print("-" * 65)
    print(
        f"{'Observed Pass Rate':<25} | {base_rep['pass_rate'] * 100:.2f}%{' ':>10} | {hyb_rep['pass_rate'] * 100:.2f}%{' ':>10}"
    )
    print(
        f"{'Serving Cost ($)':<25} | ${base_rep['serving_usd']:.4f}{' ':>9} | ${hyb_rep['serving_usd']:.4f}{' ':>9}"
    )
    print(
        f"{'Cost Savings vs Ref':<25} | {base_savings:.1f}%{' ':>11} | {hyb_savings:.1f}%{' ':>11}"
    )
    print(
        f"{'Latency p50 Ratio':<25} | {base_rep['p50_ratio']:.2f}x{' ':>11} | {hyb_rep['p50_ratio']:.2f}x{' ':>11}"
    )
    print(
        f"{'Training Duration':<25} | {comparison['training_time']['baseline_sec']}s{' ':>12} | {comparison['training_time']['hybrid_sec']}s{' ':>12}"
    )
    print("=" * 65)
    print("\nCandidate Model Selections on HOLDOUT (604 samples):")
    print("  Baseline ML:")
    for k, v in base_rep["selections"].items():
        print(f"    - {k}: {int(v)} ({v / 604 * 100:.1f}%)")
    print("  Hybrid ML + Attention:")
    for k, v in hyb_rep["selections"].items():
        print(f"    - {k}: {int(v)} ({v / 604 * 100:.1f}%)")
    print("=" * 65)


if __name__ == "__main__":
    main()
