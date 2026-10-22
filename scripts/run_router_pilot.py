"""Run/resume the approved 5 USD pilot under an existing local admin account."""

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.config import ROOT, Settings
from app.contracts.dtos import Principal
from app.contracts.training import TrainingRequest, TrainingResume
from app.routing.ml.pipeline import RouterTrainingPipeline
from app.storage.database import Database
from app.storage.ledger import SqlBudgetLedger
from app.storage.models import User
from sqlalchemy import select


async def run(args) -> int:
    settings = Settings(router_training_manifest_path=args.manifest)
    db = Database(settings)
    pipeline = RouterTrainingPipeline(
        settings,
        db,
        SqlBudgetLedger(db, settings.project_budget_usd),
        lambda engine: None,
    )
    try:
        async with db.sessions() as session:
            row = await session.scalar(
                select(User).where(User.username == args.owner, User.role == "admin")
            )
            if not row:
                raise ValueError(
                    "Existing admin owner required; no account is created automatically"
                )
            user = Principal(
                id=row.id,
                username=row.username,
                role="admin",
                quota_usd=Decimal(row.quota_usd),
            )
        if args.resume:
            job = await pipeline.resume(
                user, args.resume, TrainingResume(phase=args.phase)
            )
        else:
            job = await pipeline.start(
                user,
                TrainingRequest(
                    client_request_id="approved-gold-pilot-v1",
                    mode="huggingface_gemini" if args.live else "cache",
                    budget_usd=Decimal(5),
                    phase=args.phase,
                    flash_attention=True,
                    auto_import=True,
                    collection_batches=args.batches,
                ),
            )
        print(
            json.dumps({"job_id": job.id, "budget_usd": "5", "phase": args.phase}),
            flush=True,
        )
        while pipeline.tasks:
            await asyncio.sleep(5)
            saved = await pipeline.get(user, job.id)
            print(
                json.dumps(
                    {
                        "job_id": saved.id,
                        "status": saved.status,
                        "stage": saved.stage,
                        "completed": saved.completed,
                        "total": saved.total,
                        "calls": saved.api_calls,
                        "spent_usd": str(saved.spent_usd),
                        "error_code": saved.error_code,
                    }
                ),
                flush=True,
            )
        saved = await pipeline.get(user, job.id)
        output = ROOT / "output/router-pilot"
        output.mkdir(parents=True, exist_ok=True)
        (output / "latest.json").write_text(
            saved.model_dump_json(indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "job_id": saved.id,
                    "status": saved.status,
                    "completed": saved.completed,
                    "spent_usd": str(saved.spent_usd),
                    "unknown_cost_calls": saved.unknown_cost_calls,
                    "error_code": saved.error_code,
                    "artifact_hash": saved.artifact_hash,
                    "report": saved.pilot_report,
                }
            ),
            flush=True,
        )
        return 0 if saved.status == "succeeded" else 1
    finally:
        await pipeline.close()
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "data/router-pilot-v1/manifest.json"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the server key inside the original 5 USD cap",
    )
    parser.add_argument("--resume")
    parser.add_argument(
        "--batches",
        type=int,
        default=2,
        help="25 prompts per batch; campaign still at most 500 and USD 5",
    )
    parser.add_argument("--phase", choices=("full", "collect", "train"), default="full")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
