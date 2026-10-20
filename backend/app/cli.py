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
from app.evaluation.runner import run_smoke, validate_manifest
from app.routing.experiments.cli import cli as research_cli
from app.storage.database import Database

cli = typer.Typer(no_args_is_help=True)
evaluation = typer.Typer(no_args_is_help=True)
cli.add_typer(evaluation, name="eval")
cli.add_typer(research_cli, name="research")


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
    """Read-only provider model access check; never submits generation/embedding."""
    from openai import AsyncOpenAI

    from app.providers.catalog import Catalog

    settings = Settings()
    catalog = Catalog.load(settings.model_catalog_path)
    if not settings.openai_api_key.get_secret_value():
        raise typer.BadParameter("Set OPENAI_API_KEY on the server first")

    async def verify() -> None:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(), max_retries=0
        ) as connection:
            for model in catalog.models:
                try:
                    await connection.models.retrieve(model.model_id)
                    typer.echo(
                        f"ACCESS OK: {model.config_id}; manually record verified_access and reviewed prices in a new catalog version"
                    )
                except Exception:
                    typer.echo(f"ACCESS NOT VERIFIED: {model.config_id}", err=True)
                    raise typer.Exit(1) from None

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
