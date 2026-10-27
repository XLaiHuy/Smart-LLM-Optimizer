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


@cli.command("qualify")
def qualify_command(
    dataset: Annotated[Path, typer.Option()],
    holdout: Annotated[Path, typer.Option()],
    model: Annotated[Path, typer.Option()],
    compare_model: Annotated[Path, typer.Option()],
    e2e_report: Annotated[Path, typer.Option()],
    reviewed_by: Annotated[str, typer.Option()],
    report: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    review_output: Annotated[Path, typer.Option()],
) -> None:
    """Offline qualification; only reviewed PASS writes a serving artifact."""
    from app.routing.ml.multi import MultiArtifact
    from app.routing.ml.qualification import qualify

    try:
        targets = [report.resolve(), output.resolve(), review_output.resolve()]
        if len(set(targets)) != 3 or any(p.exists() for p in targets):
            raise ValueError(
                "Use distinct new output paths; existing artifacts are never overwritten"
            )
        result, review = qualify(dataset, holdout, model, compare_model, e2e_report, reviewed_by)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if review is None:
            typer.echo(
                json.dumps({"passed": False, "issues": result["issues"], "report": str(report)})
            )
            raise typer.Exit(2)
        artifact = MultiArtifact.model_validate_json(model.read_text(encoding="utf-8"))
        for path in (output, review_output):
            path.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(
                artifact.model_copy(update={"purpose": "qualified_dev"}).model_dump_json(indent=2)
                + "\n"
            )
        with review_output.open("x", encoding="utf-8") as stream:
            stream.write(review.model_dump_json(indent=2) + "\n")
        typer.echo(
            json.dumps(
                {
                    "passed": True,
                    "artifact_hash": review.artifact_hash,
                    "activation": "Select artifact and review paths explicitly, then restart backend",
                }
            )
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@cli.command("readiness")
def readiness_command(output: Path | None = None) -> None:
    """Read-only deployment diagnosis; never dispatches to a provider."""
    from app.config import Settings
    from app.contracts.dtos import ModelConfiguration
    from app.providers.catalog import Catalog
    from app.routing.ml.multi import configuration_hash
    from app.routing.ml.qualification import research_acceptance_failure, review_failure
    from app.routing.policies import _artifact_cost_hash

    settings = Settings()
    engine = MLRouterService.load(
        settings.ml_router_artifact_path,
        live_approved=settings.ml_router_live_approved,
        allow_research_candidate=settings.research_chat_enabled,
    )
    artifact = engine.multi.artifact
    issues = []
    if not settings.ml_router_live_approved or artifact and artifact.purpose != "qualified_dev":
        issues.append("ML_NOT_QUALIFIED_FALLBACK")
    failure = review_failure(engine.multi, settings.ml_router_qualification_path)
    if failure:
        issues.append(failure)
    research_failure: str | None = "ML_RESEARCH_NOT_ENABLED"
    if engine.allow_research_candidate:
        research_failure = research_acceptance_failure(
            engine.multi, settings.ml_router_research_acceptance_path
        )
    catalog = Catalog.load(settings.model_catalog_path)
    if artifact:
        configurations = [
            ModelConfiguration(
                **{
                    k: getattr(m, k)
                    for k in (
                        "config_id",
                        "model_id",
                        "context_window",
                        "max_output_tokens",
                        "endpoint",
                        "structured_output",
                        "function_calling",
                        "reasoning_effort",
                        "supported_parameters",
                    )
                }
            )
            for m in catalog.models
            if m.kind == "generation"
        ]
        if (
            {
                c.config_id: configuration_hash(c)
                for c in configurations
                if c.config_id in artifact.configuration_hashes
            }
            != artifact.configuration_hashes
            or catalog.baseline_config != artifact.reference_config_id
        ):
            issues.append("ML_MODEL_MISMATCH_FALLBACK")
        costs = catalog.cost_snapshot()
        if (
            costs.version != artifact.catalog_version
            or _artifact_cost_hash(costs, set(artifact.configuration_hashes)) != artifact.costs_hash
        ):
            issues.append("ML_CATALOG_CHANGED_FALLBACK")
    result = {
        "ml_loaded": artifact is not None,
        "attention_loaded": engine.multi.semantic is not None,
        "serving_strategy": settings.auto_routing_strategy,
        "live_ready": not issues,
        "scientifically_qualified": not issues,
        "research_chat_ready": research_failure is None
        and not any(
            issue in ("ML_MODEL_MISMATCH_FALLBACK", "ML_CATALOG_CHANGED_FALLBACK")
            for issue in issues
        ),
        "research_acceptance_issue": research_failure,
        "artifact_hash": engine.hash,
        "issues": issues,
        "profiles_exceeding_groq_tpm": [
            m.config_id
            for m in catalog.models
            if m.base_url
            and "api.groq.com" in m.base_url
            and m.max_output_tokens >= settings.groq_quota_tpm
        ],
        "fallback_approved_configs": [m.config_id for m in catalog.models if m.fallback_approved],
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(result, ensure_ascii=False))


@cli.command("provider-limits")
def provider_limits_command() -> None:
    """Read OpenRouter quota and balance separately (no inference or key output)."""
    import httpx

    from app.config import Settings

    settings = Settings()
    key = settings.openrouter_api_key.get_secret_value()
    if not key:
        raise typer.BadParameter("OPENROUTER_API_KEY is not configured")
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.get(
                "https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}
            )
            credits_response = client.get(
                "https://openrouter.ai/api/v1/credits",
                headers={"Authorization": f"Bearer {key}"},
            )
        if response.status_code != 200:
            raise typer.BadParameter(
                f"OpenRouter metadata request failed: HTTP {response.status_code}"
            )
        data = response.json().get("data", {})
        quota = data.get("free_model_daily_requests", {})
        credits = (
            credits_response.json().get("data", {}) if credits_response.status_code == 200 else {}
        )
        total, used = credits.get("total_credits"), credits.get("total_usage")
        from decimal import Decimal, InvalidOperation

        balance = None
        try:
            if total is not None and used is not None:
                amount = Decimal(str(total)) - Decimal(str(used))
                if amount.is_finite():
                    balance = str(amount)
        except (InvalidOperation, ValueError):
            pass
        typer.echo(
            json.dumps(
                {
                    "source": "OpenRouter /api/v1/key",
                    "free_model_daily_requests": quota,
                    "suggested_rpd": int(quota["limit"] * 0.8)
                    if isinstance(quota.get("limit"), int)
                    else None,
                    "suggested_rpm": 16,
                    "key_spend_cap_usd": data.get("limit"),
                    "key_cap_remaining_usd": data.get("limit_remaining"),
                    "account_balance_usd": balance,
                    "balance_source": "OpenRouter /api/v1/credits",
                    "balance_http_status": credits_response.status_code,
                    "key_cap_is_account_balance": False,
                }
            )
        )
    except httpx.HTTPError as exc:
        raise typer.BadParameter("OpenRouter quota metadata is unavailable") from exc


@cli.command("prepare-catalog")
def prepare_catalog_command(
    source: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    version: Annotated[str, typer.Option()],
    max_output_tokens: int = 2048,
) -> None:
    """Create a canonical output profile for review; never rewrite the active catalog."""
    import hashlib
    import re

    from app.providers.catalog import Catalog

    try:
        catalog = Catalog.load(source)
        if version == catalog.version or output.exists() or not 0 < max_output_tokens <= 4096:
            raise ValueError("A new version/output and an output reserve in 1..4096 are required")
        models = []
        seen: dict[tuple[object, ...], str] = {}
        baseline = None
        for entry in catalog.models:
            if entry.kind != "generation":
                models.append(entry)
                continue
            identity = (
                entry.base_url,
                entry.api_key_env,
                entry.model_id,
                entry.endpoint,
                entry.reasoning_effort,
                entry.supported_parameters,
                entry.structured_output,
                entry.function_calling,
                entry.input_per_million,
                entry.output_per_million,
                entry.cached_per_million,
                entry.cache_write_per_million,
            )
            if identity not in seen:
                slug = re.sub(r"[^a-zA-Z0-9.-]+", "-", entry.model_id).strip("-")
                prefix = (entry.api_key_env or "provider").removesuffix("_API_KEY").lower()
                config_id = f"{prefix}-{slug}-o{max_output_tokens}"[:100]
                if config_id in seen.values():
                    config_id = (
                        config_id[:90]
                        + "-"
                        + hashlib.sha256(repr(identity).encode()).hexdigest()[:8]
                    )
                seen[identity] = config_id
                models.append(
                    entry.model_copy(
                        update={
                            "config_id": config_id,
                            "max_output_tokens": max_output_tokens,
                            "fallback_approved": False,
                        }
                    )
                )
            if entry.config_id == catalog.baseline_config:
                baseline = seen[identity]
        prepared = Catalog.model_validate(
            {
                **catalog.model_dump(),
                "version": version,
                "baseline_config": baseline,
                "models": models,
            }
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(prepared.model_dump_json(indent=2) + "\n")
        typer.echo(
            json.dumps(
                {
                    "output": str(output),
                    "activation": "Review access, fallback approvals and configuration evidence before activation",
                }
            )
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


if __name__ == "__main__":
    cli()
