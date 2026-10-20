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
from app.storage.database import Database

cli = typer.Typer(no_args_is_help=True)
evaluation = typer.Typer(no_args_is_help=True)
cli.add_typer(evaluation, name="eval")


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
            for name in ("e2e-a", "e2e-b"):
                await service.create_user(name, os.environ["E2E_PASSWORD"])
        finally:
            await db.close()

    asyncio.run(create())


if __name__ == "__main__":
    cli()
