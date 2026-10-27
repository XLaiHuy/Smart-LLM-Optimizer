"""Run/resume a bounded measured pilot under an existing local admin account.

Live dispatch is explicit and still requires the research gate, reviewed manifest,
provider quotas and the existing account/project ledger. No serving activation.
"""

import argparse
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.config import ROOT, Settings
from app.contracts.dtos import (
    CallRecord,
    Message,
    Principal,
    ProviderOptions,
    ProviderResult,
)
from app.contracts.errors import AppError
from app.contracts.training import TrainingRequest, TrainingResume
from app.providers.catalog import Catalog
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.quota import ProviderQuota
from app.routing.ml.pipeline import RouterTrainingPipeline
from app.storage.database import Database
from app.storage.ledger import SqlBudgetLedger
from app.storage.models import UsageRecord, User
from sqlalchemy import select


def quota_category(message: str) -> str:
    lower = message.casefold()
    return next(
        (
            name
            for needle, name in (
                ("tokens per day", "tokens_per_day"),
                ("tokens per minute", "tokens_per_minute"),
                ("requests per day", "requests_per_day"),
                ("requests per minute", "requests_per_minute"),
            )
            if needle in lower
        ),
        "unspecified",
    )


class PilotProvider(OpenAICompatibleProvider):
    last_quota_category = "unspecified"

    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult:
        self.last_quota_category = "unspecified"
        try:
            return await super().generate(messages, opts)
        except AppError as exc:
            if exc.code == "RATE_LIMITED" and exc.upstream_status == 429:
                # Keep only a fixed safe label, never the provider's private text.
                self.last_quota_category = quota_category(
                    str(getattr(exc.__cause__, "message", ""))
                )
            raise


def quota_retry_delay(call: CallRecord | None, remaining_wait: float) -> float | None:
    if (
        not call
        or call.error_code != "RATE_LIMITED"
        or call.dispatch_state not in ("not_dispatched", "rejected")
    ):
        return None
    delay = max(2.0, (call.retry_after_seconds or 60) + 1)
    return delay if delay <= remaining_wait else None


async def run(args) -> int:
    settings = Settings(
        router_training_manifest_path=args.manifest,
        **({"router_training_directory": args.directory} if args.directory else {}),
    )
    db = Database(settings)
    provider = None
    if args.live:
        if settings.app_env == "test" or not settings.research_live_enabled:
            raise ValueError(
                "Live pilot requires development mode and RESEARCH_LIVE_ENABLED"
            )
        catalog = Catalog.load(settings.model_catalog_path)
        provider = PilotProvider(
            settings.openai_api_key.get_secret_value(),
            catalog,
            settings,
            ProviderQuota(db, settings) if settings.provider_quota_enabled else None,
        )
    pipeline = RouterTrainingPipeline(
        settings,
        db,
        SqlBudgetLedger(db, settings.project_budget_usd),
        lambda engine: None,
        provider,
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
                    client_request_id=args.request_id,
                    mode="live" if args.live else "cache",
                    budget_usd=args.budget,
                    phase=args.phase,
                    flash_attention=True,
                    auto_import=False,
                    collection_batches=args.batches,
                ),
            )
        print(
            json.dumps(
                {
                    "job_id": job.id,
                    "budget_usd": str(job.request.budget_usd),
                    "phase": args.phase,
                }
            ),
            flush=True,
        )
        quota_waited = 0.0
        last_progress = None
        while True:
            while pipeline.tasks:
                await asyncio.sleep(5)
                saved = await pipeline.get(user, job.id)
                progress = (saved.status, saved.stage, saved.completed, saved.api_calls)
                if progress != last_progress:
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
                    last_progress = progress
            saved = await pipeline.get(user, job.id)
            if (
                args.phase == "full"
                and saved.status == "succeeded"
                and saved.pilot_report.get("partial_collection")
                and saved.pilot_report.get("collection_stopped_reason")
                == "BATCH_COMPLETE"
            ):
                # A batch is a checkpoint, not permission to freeze incomplete DEV.
                job = await pipeline.resume(
                    user, saved.id, TrainingResume(phase="full")
                )
                continue
            if provider and provider.last_quota_category in (
                "tokens_per_day",
                "requests_per_day",
            ):
                print(
                    json.dumps(
                        {
                            "job_id": saved.id,
                            "stage": "daily_quota_exhausted",
                            "quota_category": provider.last_quota_category,
                            "resume_same_job_after_capacity_returns": True,
                        }
                    ),
                    flush=True,
                )
                break
            if (
                not args.wait_for_quota
                or saved.status != "failed"
                or saved.error_code != "RATE_LIMITED"
            ):
                break
            async with db.sessions() as session:
                record = await session.scalar(
                    select(UsageRecord.record_json)
                    .where(UsageRecord.operation_id == saved.id)
                    .order_by(UsageRecord.created_at.desc())
                    .limit(1)
                )
            call = CallRecord.model_validate_json(record) if record else None
            delay = quota_retry_delay(call, args.max_quota_wait - quota_waited)
            if delay is None:
                break
            quota_waited += delay
            print(
                json.dumps(
                    {
                        "job_id": saved.id,
                        "stage": "quota_wait",
                        "seconds": delay,
                        "same_budget_and_cache": True,
                    }
                ),
                flush=True,
            )
            while delay > 0:
                interval = min(10, delay)
                await asyncio.sleep(interval)
                delay -= interval
            job = await pipeline.resume(
                user, saved.id, TrainingResume(phase=args.phase)
            )
        saved = await pipeline.get(user, job.id)
        output = settings.router_training_directory
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
                    "total": saved.total,
                    "complete_corpus": saved.completed == saved.total
                    and saved.total > 0,
                    "spent_usd": str(saved.spent_usd),
                    "unknown_cost_calls": saved.unknown_cost_calls,
                    "error_code": saved.error_code,
                    "artifact_hash": saved.artifact_hash,
                    "report_path": str(pipeline.directory(job.id) / "report.json"),
                }
            ),
            flush=True,
        )
        complete = saved.completed == saved.total and saved.total > 0
        return (
            0
            if saved.status == "succeeded" and (args.phase != "full" or complete)
            else 1
        )
    finally:
        await pipeline.close()
        if provider:
            await provider.close()
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--budget", type=Decimal, default=Decimal(1))
    parser.add_argument("--request-id", default="approved-gold-pilot-v1")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "data/router-pilot-v1/manifest.json"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the configured live providers under the existing ledger limits",
    )
    parser.add_argument("--resume")
    parser.add_argument(
        "--wait-for-quota",
        action="store_true",
        help="Wait and resume only confirmed quota rejections, with the same job/budget/cache",
    )
    parser.add_argument(
        "--max-quota-wait",
        type=float,
        default=1800,
        help="Total permitted quota wait seconds; never bypass daily limits",
    )
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
