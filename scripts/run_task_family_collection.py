"""Operator-only 1.50 USD collection, two-call limit, lock and same-job resume."""

import argparse
import asyncio
import fcntl
import json
from decimal import Decimal
from pathlib import Path

from app.composition import Container
from app.config import Settings
from app.contracts.dtos import Principal
from app.contracts.training import TrainingRequest, TrainingResume
from app.routing.ml.family_campaign import FamilyCollection
from app.routing.ml.pipeline import atomic_text
from app.storage.models import User
from sqlalchemy import select


async def run(args):
    directory = args.directory
    with (directory / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        settings = Settings(
            router_training_manifest_path=directory / "manifest.json",
            router_training_directory=directory / "runs",
        )
        if (
            not args.live
            or settings.provider_mode != "live"
            or settings.app_env == "test"
            or not settings.research_live_enabled
        ):
            raise ValueError("Explicit live research configuration required")
        container = Container(settings)
        pipeline = FamilyCollection(container)
        try:
            async with container.db.sessions() as db:
                owner = await db.scalar(
                    select(User).where(User.role == "admin").order_by(User.id)
                )
                if owner is None:
                    raise ValueError("Existing admin required")
                user = Principal(
                    id=owner.id,
                    username=owner.username,
                    role="admin",
                    quota_usd=Decimal(owner.quota_usd),
                )
            pointer = directory / "job.json"
            if pointer.exists():
                job = await pipeline.get(
                    user, json.loads(pointer.read_text())["job_id"]
                )
                if job.status == "succeeded" and job.completed == 900:
                    print(job.model_dump_json(), flush=True)
                    return
                # Only operator-requested resume; uncertain calls keep fences.
                if not args.resume:
                    raise ValueError("Existing job; explicit same-job resume required")
                job = await pipeline.resume(
                    user, job.id, TrainingResume(phase="collect")
                )
            else:
                job = await pipeline.start(
                    user,
                    TrainingRequest(
                        client_request_id="task-family-v1-20261027",
                        mode="live",
                        budget_usd=Decimal("1.50"),
                        phase="collect",
                        auto_import=False,
                        flash_attention=False,
                        collection_batches=20,
                    ),
                )
                atomic_text(pointer, json.dumps({"job_id": job.id, "cap_usd": "1.50"}))
            print(
                json.dumps({"job_id": job.id, "stage": "started", "cap_usd": "1.50"}),
                flush=True,
            )
            previous = None
            while pipeline.tasks:
                await asyncio.sleep(10)
                saved = await pipeline.get(user, job.id)
                progress = (
                    saved.status,
                    saved.completed,
                    saved.api_calls,
                    saved.error_code,
                )
                if progress != previous:
                    print(
                        json.dumps(
                            {
                                "job_id": job.id,
                                "status": saved.status,
                                "completed": saved.completed,
                                "total": saved.total,
                                "api_calls": saved.api_calls,
                                "spent_usd": str(saved.spent_usd),
                                "error_code": saved.error_code,
                            }
                        ),
                        flush=True,
                    )
                    atomic_text(
                        directory / "status.json", saved.model_dump_json(indent=2)
                    )
                    previous = progress
            saved = await pipeline.get(user, job.id)
            atomic_text(directory / "status.json", saved.model_dump_json(indent=2))
            print(saved.model_dump_json(), flush=True)
        finally:
            await pipeline.close()
            if container.live:
                await container.live.close()
            await container.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("/app/data/router-task-family-v1-20261027"),
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--resume", action="store_true")
    asyncio.run(run(parser.parse_args()))
