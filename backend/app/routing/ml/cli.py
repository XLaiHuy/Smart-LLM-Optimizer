import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Annotated

import typer

from app.contracts.representations import EncoderSpec
from app.routing.ml.dataset import LabeledDataset
from app.routing.ml.service import MLRouterService
from app.routing.ml.trainer import evaluate, train

cli = typer.Typer(no_args_is_help=True)


@cli.command("train")
def train_command(
    dataset: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    threshold: float | None = None,
    allow_test_data: bool = False,
    hybrid: Annotated[
        bool,
        typer.Option(
            "--hybrid/--no-hybrid", help="V2 grouped-OOF hybrid research candidate; default linear."
        ),
    ] = False,
) -> None:
    """Offline only. Threshold is selected on calibration, never on HOLDOUT."""
    try:
        raw = json.loads(dataset.read_text(encoding="utf-8"))
        if raw.get("format_version") == "router-dataset-v2":
            from app.routing.ml.multi_training import MultiDataset, train_multi

            multi_data = MultiDataset.model_validate(raw)
            if multi_data.purpose == "software_test" and not allow_test_data:
                raise ValueError("Synthetic data needs --allow-test-data")
            if threshold is not None:
                raise ValueError("V2 thresholds are jointly selected; do not supply --threshold")
            multi_artifact = train_multi(multi_data, hybrid=hybrid)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as target:
                target.write(multi_artifact.model_dump_json(indent=2) + "\n")
            typer.echo(
                json.dumps(
                    {
                        "output": str(output),
                        "purpose": multi_artifact.purpose,
                        "threshold_report": multi_artifact.threshold_report,
                        "live_approved": False,
                        "architecture": "hybrid_grouped_oof" if hybrid else "linear",
                    }
                )
            )
            return
        if hybrid:
            raise ValueError("--hybrid requires a router-dataset-v2 dataset")
        data = LabeledDataset.load(dataset)
        if data.purpose == "software_test" and not allow_test_data:
            raise ValueError("Synthetic inputs require --allow-test-data; never live qualified")
        if threshold is not None and not 0 <= threshold <= 1:
            raise ValueError("Threshold must be between 0 and 1")
        artifact = train(data, threshold)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as target:
            target.write(artifact.model_dump_json(indent=2) + "\n")
        typer.echo(
            json.dumps(
                {
                    "output": str(output),
                    "purpose": artifact.purpose,
                    "threshold": artifact.threshold,
                    "report": artifact.calibration_report,
                    "live_approved": False,
                },
                ensure_ascii=False,
            )
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@cli.command("auto-train")
def auto_train_command(
    dataset: Annotated[Path, typer.Option(help="Path to multi-domain training dataset")],
    output: Annotated[Path, typer.Option(help="Path to output compiled router model json")],
    flash_attention: Annotated[
        bool,
        typer.Option(
            "--flash-attention/--no-flash-attention",
            help="Train learned SDPA attention; CPU default, not a CUDA verification",
        ),
    ] = False,
    hybrid: Annotated[bool, typer.Option("--hybrid/--no-hybrid")] = True,
    allow_test_data: bool = False,
    distill_cache: Annotated[
        bool, typer.Option(help="Use the web pipeline for raw-response distillation.")
    ] = False,
    encoder: Annotated[
        Path | None,
        typer.Option(help="Pinned INT8 EncoderSpec JSON; required with --flash-attention"),
    ] = None,
    attention_epochs: int = 10,
    n_estimators: Annotated[
        int | None, typer.Option(help="Number of GBDT trees; defaults to adaptive (up to 100)")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option(help="Allow overwriting existing output model")
    ] = False,
) -> None:
    """Offline training of labeled V2 data. Raw data distillation lives in the admin pipeline."""
    try:
        if flash_attention and encoder is None:
            raise ValueError("--flash-attention requires --encoder with a pinned INT8 EncoderSpec")
        spec = (
            EncoderSpec.model_validate_json(encoder.read_text(encoding="utf-8"))
            if flash_attention and encoder
            else None
        )
        if distill_cache:
            raise ValueError("Use the admin training pipeline to distill raw cached responses")
        raw = json.loads(dataset.read_text(encoding="utf-8"))
        if raw.get("format_version") != "router-dataset-v2":
            raise ValueError("auto-train requires a router-dataset-v2 dataset")

        from app.routing.ml.multi_training import MultiDataset, train_multi

        multi_data = MultiDataset.model_validate(raw)
        if multi_data.purpose == "software_test" and not allow_test_data:
            raise ValueError("Synthetic data needs --allow-test-data")
        multi_artifact = train_multi(
            multi_data,
            hybrid=hybrid,
            encoder_spec=spec,
            attention_epochs=attention_epochs,
            n_estimators=n_estimators,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if overwrite else "x"
        with output.open(mode, encoding="utf-8") as target:
            target.write(multi_artifact.model_dump_json(indent=2) + "\n")

        typer.echo(
            json.dumps(
                {
                    "status": "success",
                    "mode": "auto-train",
                    "output": str(output),
                    "numeric_features_count": 14,
                    "features_by_candidate": {
                        p.config_id: len(p.feature_names) if p.is_hybrid else len(p.coefficients)
                        for p in multi_artifact.predictors
                    },
                    "learned_attention_ready": multi_artifact.attention is not None,
                    "inference_backend": "numpy_cpu",
                    "cuda_flash_verified": False,
                    "threshold_report": multi_artifact.threshold_report,
                },
                indent=2,
            )
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@cli.command("evaluate")
def evaluate_command(
    testset: Annotated[Path, typer.Option()],
    model: Annotated[Path, typer.Option()],
    compare_model: Annotated[
        Path | None,
        typer.Option(help="Compare another V2 artifact on the same independent HOLDOUT."),
    ] = None,
) -> None:
    """Offline replay of measured labels/costs, not live E2E or a new provider call."""
    try:
        raw = json.loads(testset.read_text(encoding="utf-8"))
        if raw.get("format_version") == "router-dataset-v2":
            from app.routing.ml.multi_training import MultiDataset, evaluate_multi

            multi_data = MultiDataset.model_validate(raw)
            engine = MLRouterService.load(model).multi
            started = perf_counter()
            multi_report = evaluate_multi(multi_data, engine)
            if compare_model is not None:
                other = MLRouterService.load(compare_model).multi
                if (
                    not engine.artifact
                    or not other.artifact
                    or engine.artifact.dataset_hash != other.artifact.dataset_hash
                ):
                    raise ValueError("Paired architecture comparison requires the same DEV dataset")
                comparison = evaluate_multi(multi_data, other)
                current_metrics = multi_report["report"]
                other_metrics = comparison["report"]
                assert isinstance(current_metrics, dict) and isinstance(other_metrics, dict)
                multi_report["comparison"] = {
                    "other": comparison,
                    "delta_current_minus_other": {
                        key: current_metrics[key] - other_metrics[key]
                        for key in (
                            "serving_usd",
                            "observed_pass_rate",
                            "p50_ratio",
                            "critical_regressions",
                        )
                    },
                    "note": "Paired offline replay; no live quality or speed conclusion",
                }
            multi_report["local_replay_ms"] = (perf_counter() - started) * 1000
            typer.echo(json.dumps(multi_report, ensure_ascii=False))
            return
        if compare_model is not None:
            raise ValueError("--compare-model currently supports V2 artifacts only")
        dataset = LabeledDataset.load(testset)
        runtime = MLRouterService.load(model)
        report = evaluate(dataset, runtime)
        timings = []
        for row in dataset.samples:
            started = perf_counter()
            runtime.score(row.messages, row.has_rag_context)
            timings.append((perf_counter() - started) * 1000)
        ordered = sorted(timings)
        report["local_routing_timing_ms"] = {
            "p50": median(ordered),
            "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
            "samples": len(ordered),
        }
        typer.echo(json.dumps(report, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


if __name__ == "__main__":
    cli()
