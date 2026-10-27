"""Read reviewed benchmark evidence; never execute models from an analytics request."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from sqlalchemy import select

from app.analytics.service import ZONE, administrator
from app.config import Settings
from app.contracts.dtos import DTO, CallRecord, Principal
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import UsageRecord, User


class BenchmarkGroup(DTO):
    category: str
    baseline_model_id: str
    price_catalog_version: str
    population: str = Field(min_length=5)
    paired_samples: int = Field(gt=0)
    baseline_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    optimized_usd: Decimal = Field(ge=0, allow_inf_nan=False)


class ReviewedBenchmark(DTO):
    version: Literal["benchmark-impact-v1"]
    execution_source: Literal["live"]
    paired: Literal[True]
    independent_holdout: Literal[True]
    all_in_costs: Literal[True]
    quality_guardrails_passed: Literal[True]
    reviewed_by: str = Field(min_length=1)
    reviewed_at: datetime
    valid_until: datetime
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    grader_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    limitations: str = Field(min_length=10)
    groups: tuple[BenchmarkGroup, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_groups(self) -> "ReviewedBenchmark":
        keys = [(g.category, g.baseline_model_id, g.price_catalog_version) for g in self.groups]
        if len(set(keys)) != len(keys):
            raise ValueError("Ambiguous overlapping benchmark groups")
        if self.reviewed_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("Review timestamps require timezones")
        if self.valid_until <= self.reviewed_at:
            raise ValueError("Evidence expiry must follow review")
        return self


class BenchmarkImpact(DTO):
    status: Literal["available", "unavailable"] = "unavailable"
    reason: str = "BENCHMARK_NOT_APPROVED"
    scope: Literal["project", "selected_user"] = "project"
    estimated_savings_usd: Decimal | None = None
    eligible_baseline_usd: Decimal | None = None
    known_live_usd: Decimal | None = None
    matched_calls: int = 0
    unknown_cost_calls: int = 0
    coverage_ratio: float | None = None
    paired_samples: int = 0
    benchmark_baseline_usd: Decimal | None = None
    benchmark_optimized_usd: Decimal | None = None
    evidence_sha256: str | None = None
    policy_version: str | None = None
    limitations: str | None = None
    populations: tuple[str, ...] = ()
    method: Literal["benchmark_ratio_on_matched_baseline_spend"] = (
        "benchmark_ratio_on_matched_baseline_spend"
    )


async def benchmark_impact(
    db: Database,
    settings: Settings,
    principal: Principal,
    start: date | None = None,
    end: date | None = None,
    user_id: str | None = None,
) -> BenchmarkImpact:
    administrator(principal)
    end = end or datetime.now(ZONE).date()
    start = start or end - timedelta(days=6)
    if start > end or (end - start).days > 365:
        raise AppError("VALIDATION_ERROR", 422, "Date range must be ordered and at most 366 days")
    scope: Literal["project", "selected_user"] = "selected_user" if user_id else "project"
    async with db.sessions() as connection:
        if user_id and await connection.get(User, user_id) is None:
            raise AppError("USER_NOT_FOUND", 404, "User not found")
    if not settings.benchmark_impact_approved:
        return BenchmarkImpact(scope=scope)
    try:
        evidence = ReviewedBenchmark.model_validate_json(
            settings.benchmark_impact_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError):
        return BenchmarkImpact(scope=scope, reason="BENCHMARK_INVALID")
    current = datetime.now(UTC)
    if not evidence.reviewed_at <= current < evidence.valid_until:
        return BenchmarkImpact(scope=scope, reason="BENCHMARK_EXPIRED")
    lower = datetime.combine(start, time.min, ZONE).astimezone(UTC).isoformat()
    upper = datetime.combine(end + timedelta(days=1), time.min, ZONE).astimezone(UTC).isoformat()
    async with db.sessions() as connection:
        query = select(UsageRecord).where(
            UsageRecord.execution_source == "live",
            UsageRecord.created_at >= lower,
            UsageRecord.created_at < upper,
        )
        from app.analytics.epoch import current_epoch, product_attempts
        from app.storage.models import Attempt

        epoch = await current_epoch(connection)
        if epoch:
            query = query.where(
                UsageRecord.operation_id.in_(
                    select(Attempt.id).where(
                        *product_attempts(),
                        Attempt.created_at >= epoch.started_at,
                    )
                )
            )
        if user_id:
            query = query.where(UsageRecord.owner_user_id == user_id)
        records = list(await connection.scalars(query))
    groups = {
        (g.category, g.baseline_model_id, g.price_catalog_version): g for g in evidence.groups
    }
    savings, eligible, known = Decimal(0), Decimal(0), Decimal(0)
    matched = unknown = 0
    for row in records:
        call = CallRecord.model_validate_json(row.record_json)
        amount = call.reconciled_usd if call.reconciled_usd is not None else call.cost.serving_usd
        if amount is None:
            unknown += 1
            continue
        known += amount
        version = call.cost.price_catalog_version
        group = groups.get((row.category, row.model_id, version)) if version else None
        if group and call.reconciliation_id is None and call.cost.status in ("known", "estimated"):
            eligible += amount
            savings += amount * (1 - group.optimized_usd / group.baseline_usd)
            matched += 1
    return BenchmarkImpact(
        status="available" if matched else "unavailable",
        reason="BENCHMARK_ESTIMATE" if matched else "NO_MATCHING_BASELINE_USAGE",
        scope=scope,
        estimated_savings_usd=savings if matched else None,
        eligible_baseline_usd=eligible if matched else None,
        known_live_usd=known if records else None,
        matched_calls=matched,
        unknown_cost_calls=unknown,
        coverage_ratio=float(eligible / known) if known else None,
        paired_samples=sum(g.paired_samples for g in evidence.groups),
        benchmark_baseline_usd=sum((g.baseline_usd for g in evidence.groups), Decimal(0)),
        benchmark_optimized_usd=sum((g.optimized_usd for g in evidence.groups), Decimal(0)),
        evidence_sha256=evidence.evidence_sha256,
        policy_version=evidence.policy_version,
        limitations=evidence.limitations,
        populations=tuple(g.population for g in evidence.groups),
    )
