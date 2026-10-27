import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

import typer
from alembic import command
from alembic.config import Config

from app.auth.service import AuthService
from app.config import ROOT, Settings
from app.contracts.errors import AppError
from app.evaluation.harness import (
    FixturePairConfig,
    export_fixture_harness,
    run_fixture_pair,
)
from app.evaluation.runner import run_smoke, validate_manifest
from app.routing.experiments.cli import cli as research_cli
from app.routing.ml.cli import cli as router_cli
from app.storage.database import Database

cli = typer.Typer(no_args_is_help=True)
evaluation = typer.Typer(no_args_is_help=True)
cli.add_typer(evaluation, name="eval")
cli.add_typer(evaluation, name="evaluation")
cli.add_typer(research_cli, name="research")
cli.add_typer(router_cli, name="router")


@cli.command("start-reporting-epoch")
def start_reporting_epoch(
    reason: str = "Three-model chat reporting", key: str = "three-model-chat-v1"
) -> None:
    """Idempotent reporting watermark. Does not change financial balances."""

    async def run():
        from app.storage.models import AnalyticsEpoch
        from app.storage.repositories import now

        db = Database(Settings())
        try:
            async with db.write() as session:
                existing = await session.get(AnalyticsEpoch, key)
                if existing is None:
                    existing = AnalyticsEpoch(id=key, started_at=now(), reason=reason)
                    session.add(existing)
                typer.echo(existing.started_at)
        finally:
            await db.close()

    asyncio.run(run())


@cli.command("mark-audit-user")
def mark_audit_user(user_id: str) -> None:
    """Explicit IDs only; never infer account purpose from its username."""

    async def run():
        from app.storage.models import User

        db = Database(Settings())
        try:
            async with db.write() as session:
                user = await session.get(User, user_id)
                if user is None:
                    raise ValueError("User not found")
                user.account_purpose = "internal_audit"
        finally:
            await db.close()

    asyncio.run(run())


def migrate(path: Path) -> None:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.attributes["database_path"] = path
    command.upgrade(config, "head")


@cli.command("create-user")
def create_user(
    username: Annotated[str, typer.Option()],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
    role: Literal["user", "admin"] = "user",
) -> None:
    async def create() -> None:
        settings = Settings()
        db = Database(settings)
        try:
            user = await AuthService(db, settings).create_user(username, password, role)
            typer.echo(f"Created {user.username} ({user.role})")
        finally:
            await db.close()

    try:
        asyncio.run(create())
    except AppError as exc:
        typer.echo(f"{exc.code}: {exc.message}", err=True)
        raise typer.Exit(1) from exc


@cli.command("openapi")
def openapi(output: Annotated[Path, typer.Option()]) -> None:
    from app.main import create_app

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


@evaluation.command("run")
def eval_run(
    purpose: str = "smoke",
    manifest: Path = ROOT / "benchmark/manifests/smoke.json",
    output: Path = ROOT / "benchmark/reports/smoke.jsonl",
) -> None:
    try:
        validate_manifest(manifest, purpose)
        with TemporaryDirectory(prefix="smartllm-smoke-") as directory:
            db_path = Path(directory) / "smoke.db"
            migrate(db_path)
            count = asyncio.run(
                run_smoke(manifest, Settings(database_path=db_path, app_env="test"), output)
            )
        typer.echo(
            f"SMOKE ONLY: {count} functional cases; mock, quality/savings unknown. Output: {output}"
        )
    except (AppError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@evaluation.command("fixture-pair")
def eval_fixture_pair(
    case_manifest: Annotated[
        Path,
        typer.Option(),
    ],
    baseline_predictions: Annotated[
        Path,
        typer.Option(),
    ],
    variant_predictions: Annotated[
        Path,
        typer.Option(),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(),
    ] = ROOT / "benchmark/reports/g1-fixture",
    seed: int = 0,
    overwrite: bool = False,
) -> None:
    try:
        result = run_fixture_pair(
            case_manifest_path=case_manifest,
            baseline_predictions_path=(baseline_predictions),
            variant_predictions_path=(variant_predictions),
            config=FixturePairConfig(
                baseline_run_id=("g1-fixture-baseline-run"),
                baseline_config_id=("g1-fixture-baseline"),
                variant_run_id=("g1-fixture-variant-run"),
                variant_config_id=("g1-fixture-variant"),
                seed=seed,
            ),
        )

        receipt = export_fixture_harness(
            result=result,
            output_dir=output_dir,
            overwrite=overwrite,
        )

        typer.echo(
            "FIXTURE ONLY: "
            f"{result.comparison.total_pair_count} "
            "paired cases; synthetic, "
            "research_eligible=false. "
            f"Report: {receipt.report_path}"
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@evaluation.command("four-suite")
def eval_four_suite(
    manifest: Annotated[
        Path,
        typer.Option(help="Path to case set manifest JSON"),
    ] = ROOT / "benchmark/fixtures/four_suite_smoke/manifest.json",
    baseline_predictions: Annotated[
        Path,
        typer.Option(help="Path to baseline predictions JSONL"),
    ] = ROOT / "benchmark/fixtures/four_suite_smoke/baseline.predictions.jsonl",
    optimized_predictions: Annotated[
        Path,
        typer.Option(help="Path to optimized predictions JSONL"),
    ] = ROOT / "benchmark/fixtures/four_suite_smoke/optimized.predictions.jsonl",
    output_dir: Annotated[
        Path,
        typer.Option(help="Directory to write evaluation report"),
    ] = ROOT / "benchmark/reports/four-suite-smoke",
    seed: int = 7,
    overwrite: bool = True,
) -> None:
    """Run four-suite benchmark evaluation across Vietnamese multi-task families."""
    try:
        result = run_fixture_pair(
            case_manifest_path=manifest,
            baseline_predictions_path=baseline_predictions,
            variant_predictions_path=optimized_predictions,
            config=FixturePairConfig(
                baseline_run_id="four-suite-baseline-run",
                baseline_config_id="four-suite-baseline",
                variant_run_id="four-suite-optimized-run",
                variant_config_id="four-suite-optimized",
                seed=seed,
            ),
            language_detector=lambda _: "vi",
        )

        receipt = export_fixture_harness(
            result=result,
            output_dir=output_dir,
            overwrite=overwrite,
        )

        baseline_passed = sum(group.passed_count for group in result.baseline_aggregate.groups)
        optimized_passed = sum(group.passed_count for group in result.variant_aggregate.groups)
        total_cases = result.comparison.total_pair_count

        typer.echo("============================================================")
        typer.echo("      FOUR-SUITE VIETNAMESE BENCHMARK EVALUATION (SMOKE)    ")
        typer.echo("============================================================")
        typer.echo(f"Total Paired Cases: {total_cases}")
        typer.echo(
            f"Baseline Pass Rate: {baseline_passed}/{total_cases} ({baseline_passed / total_cases * 100:.1f}%)"
        )
        typer.echo(
            f"Optimized Pass Rate: {optimized_passed}/{total_cases} ({optimized_passed / total_cases * 100:.1f}%)"
        )
        typer.echo("------------------------------------------------------------")
        typer.echo("Task Family Breakdown:")
        for pair in result.comparison.pairs:
            typer.echo(f"  • {pair.case_id:<28} => {pair.outcome.upper()}")
        typer.echo("------------------------------------------------------------")
        typer.echo(f"Report Generated: {receipt.report_path}")
        typer.echo(f"Report SHA-256:   {receipt.report_sha256}")
        typer.echo(f"Research Eligible: {result.research_eligible} (Synthetic functional test)")
        typer.echo("============================================================")
    except Exception as exc:
        typer.echo(f"Evaluation error: {exc}", err=True)
        raise typer.Exit(1) from exc


@cli.command("test-accounts", hidden=True)
def test_accounts() -> None:
    """E2E bootstrap only: explicit test environment and temporary DB required."""
    settings = Settings()
    if settings.app_env != "test" or not os.environ.get("E2E_PASSWORD"):
        raise typer.BadParameter("Requires APP_ENV=test and E2E_PASSWORD")
    migrate(settings.database_path)

    async def create() -> None:
        db = Database(settings)
        try:
            service = AuthService(db, settings)
            for name in ("e2e-a", "e2e-b", "e2e-admin"):
                await service.create_user(
                    name, os.environ["E2E_PASSWORD"], "admin" if name == "e2e-admin" else "user"
                )
        finally:
            await db.close()

    asyncio.run(create())


@cli.command("verify-catalog")
def verify_catalog() -> None:
    """Read-only access check using each entry's own endpoint/credential."""
    from app.providers.catalog import Catalog
    from app.providers.openai_compatible import OpenAICompatibleProvider

    settings = Settings()
    catalog = Catalog.load(settings.model_catalog_path)
    provider = OpenAICompatibleProvider("", catalog, settings)

    async def verify() -> None:
        available = {}
        failed = False
        try:
            for model in catalog.models:
                if model.model_id == "mock-hash-embedding-v1":
                    typer.echo(f"LOCAL ONLY: {model.config_id}; no provider access claim")
                    continue
                try:
                    client = provider.get_client(model)
                    if client not in available:
                        listing = await client.models.list()
                        available[client] = {entry.id for entry in listing.data}
                    if model.model_id not in available[client]:
                        raise ValueError("Model is not listed for this credential")
                    typer.echo(
                        f"ACCESS OK: {model.config_id}; pricing/quality review remains separate"
                    )
                except Exception:
                    failed = True
                    typer.echo(f"ACCESS NOT VERIFIED: {model.config_id}", err=True)
        finally:
            await provider.close()
        if failed:
            raise typer.Exit(1)

    asyncio.run(verify())


@cli.command("validate-catalog")
def validate_catalog() -> None:
    """Offline structural validation; does not assert access/pricing review."""
    from app.providers.catalog import Catalog

    try:
        catalog = Catalog.load(Settings().model_catalog_path)
        typer.echo(
            f"VALID STRUCTURE: {len(catalog.models)} configurations; version {catalog.version}; access/pricing not verified"
        )
    except AppError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1) from exc


@cli.command("tokenizer-setup")
def tokenizer_setup() -> None:
    """Download public tokenizer data once during setup; not a paid API call."""
    import tiktoken

    from app.documents.chunking import CACHE

    CACHE.mkdir(parents=True, exist_ok=True)
    tiktoken.get_encoding("cl100k_base")
    typer.echo("cl100k_base tokenizer cache ready")


if __name__ == "__main__":
    cli()
