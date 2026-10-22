import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Literal

import typer
from sqlalchemy import select

from app.composition import Container
from app.config import Settings
from app.contracts.dtos import Principal
from app.contracts.errors import AppError
from app.contracts.research import ResearchRequest
from app.routing.experiments.exports import encode_export
from app.routing.experiments.service import ResearchService
from app.storage.database import Database
from app.storage.models import User

cli = typer.Typer(no_args_is_help=True)


async def operator(db: Database, username: str) -> Principal:
    async with db.sessions() as session:
        user = await session.scalar(
            select(User).where(User.username == username, User.role == "admin")
        )
        if not user:
            raise AppError("FORBIDDEN_ACTION", 403, "Select an existing administrator account")
        return Principal(
            id=user.id, username=user.username, role="admin", quota_usd=Decimal(user.quota_usd)
        )


@cli.command("preflight")
def preflight(manifest: Path) -> None:
    """Offline validation only; never starts a worker or model call."""
    request = ResearchRequest.model_validate_json(manifest.read_text(encoding="utf-8"))
    container = Container(Settings()) if request.execution_source == "live" else None
    db = container.db if container else Database(Settings())
    service = container.research if container else ResearchService(db)
    try:
        typer.echo(
            service.preflight(
                Principal(id="offline", username="offline", role="admin", quota_usd=Decimal(0)),
                request,
            ).model_dump_json(indent=2)
        )
    finally:
        if container and container.live:
            asyncio.run(container.live.client.close())
        asyncio.run(db.close())


@cli.command("run")
def run(manifest: Path, username: str) -> None:
    """Enqueue only. Run npm run dev so its single worker processes the run."""
    request = ResearchRequest.model_validate_json(manifest.read_text(encoding="utf-8"))

    async def enqueue() -> None:
        container = Container(Settings()) if request.execution_source == "live" else None
        db = container.db if container else Database(Settings())
        service = container.research if container else ResearchService(db)
        try:
            principal = await operator(db, username)
            typer.echo((await service.create(principal, request)).model_dump_json(indent=2))
        finally:
            if container and container.live:
                await container.live.client.close()
            await db.close()

    asyncio.run(enqueue())


@cli.command("status")
def status(run_id: str, username: str) -> None:
    async def read() -> None:
        db = Database(Settings())
        try:
            typer.echo(
                (
                    await ResearchService(db).get(await operator(db, username), run_id)
                ).model_dump_json(indent=2)
            )
        finally:
            await db.close()

    asyncio.run(read())


@cli.command("export")
def export(
    run_id: str, username: str, output: Path, format: Literal["jsonl", "csv"] = "jsonl"
) -> None:
    async def read() -> None:
        db = Database(Settings())
        try:
            service, principal = ResearchService(db), await operator(db, username)
            content = encode_export(
                await service.get(principal, run_id),
                await service.trials(principal, run_id, 0, 1000),
                format,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8", newline="") as target:
                target.write(content)
            typer.echo(f"Exported {output}")
        finally:
            await db.close()

    asyncio.run(read())
