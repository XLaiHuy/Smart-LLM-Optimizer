from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import median
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.config import Settings
from app.contracts.dtos import (
    AdminUser,
    Analytics,
    CallRecord,
    MetricBucket,
    Principal,
    QuotaUpdate,
)
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.ledger import charged
from app.storage.models import Attempt, Conversation, QuotaAudit, Reservation, UsageRecord, User
from app.storage.repositories import now, uid

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def bucket(key: str, records: list[UsageRecord]) -> MetricBucket:
    calls = [CallRecord.model_validate_json(row.record_json) for row in records]
    costs = [
        c.reconciled_usd if c.reconciled_usd is not None else c.cost.serving_usd for c in calls
    ]
    known_costs = [value for value in costs if value is not None]
    subtotal = sum(known_costs, Decimal(0))
    timings = sorted(c.duration_ms for c in calls if c.duration_ms is not None)
    return MetricBucket(
        key=key,
        calls=len(calls),
        input_tokens=sum(c.usage.input_tokens for c in calls if c.usage.input_tokens is not None)
        if calls and all(c.usage.input_tokens is not None for c in calls)
        else None,
        output_tokens=sum(c.usage.output_tokens for c in calls if c.usage.output_tokens is not None)
        if calls and all(c.usage.output_tokens is not None for c in calls)
        else None,
        # A total is meaningful only when every recorded call has a known
        # serving cost. Do not present partial or mock usage as $0.
        usd=subtotal if calls and len(known_costs) == len(calls) else None,
        known_subtotal_usd=subtotal if known_costs else None,
        unknown_calls=sum(
            c.cost.status == "unknown" or c.usage.usage_source == "unknown" for c in calls
        ),
        p50_ms=median(timings) if timings else None,
        timing_samples=len(timings),
        reconciled_calls=sum(c.reconciliation_id is not None for c in calls),
        p95_ms=timings[min(len(timings) - 1, int((len(timings) - 1) * 0.95 + 0.5))]
        if timings
        else None,
    )


def administrator(principal: Principal) -> None:
    if principal.role != "admin":
        raise AppError("FORBIDDEN_ACTION", 403, "Administrator role required")


def series_keys(start: date, end: date, granularity: str) -> list[str]:
    cursor = datetime.combine(start, time.min, ZONE)
    stop = datetime.combine(end + timedelta(days=1), time.min, ZONE)
    if granularity == "month":
        cursor = cursor.replace(day=1)
    result = []
    while cursor < stop:
        result.append(series_key(cursor, granularity))
        if granularity == "month":
            cursor = cursor.replace(
                year=cursor.year + (cursor.month == 12), month=cursor.month % 12 + 1
            )
        else:
            cursor += timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    return result


def series_key(value: datetime, granularity: str) -> str:
    local = value.astimezone(ZONE)
    if granularity == "hour":
        return local.replace(minute=0, second=0, microsecond=0).isoformat()
    if granularity == "month":
        return local.date().replace(day=1).isoformat()
    return local.date().isoformat()


class AnalyticsService:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    async def report(
        self,
        principal: Principal,
        start: date | None,
        end: date | None,
        project: bool = False,
        source: Literal["mock", "live"] | None = None,
        user_id: str | None = None,
        granularity: Literal["auto", "hour", "day", "month"] = "auto",
        model_id: str | None = None,
        session_id: str | None = None,
    ) -> Analytics:
        if project or user_id:
            administrator(principal)
        target_id = user_id or principal.id
        if project and user_id:
            raise AppError("VALIDATION_ERROR", 422, "Choose project or user scope")
        source = source or self.settings.provider_mode
        today = datetime.now(ZONE).date()
        end = end or today
        start = start or end - timedelta(days=6)
        if start > end or (end - start).days > 365:
            raise AppError(
                "VALIDATION_ERROR", 422, "Date range must be ordered and at most 366 days"
            )
        if granularity == "auto":
            granularity = "hour" if start == end else "day" if (end - start).days <= 61 else "month"
        if granularity == "hour" and (end - start).days > 6:
            raise AppError("VALIDATION_ERROR", 422, "Hourly series is limited to seven days")
        lower = datetime.combine(start, time.min, ZONE).astimezone(UTC).isoformat()
        upper = (
            datetime.combine(end + timedelta(days=1), time.min, ZONE).astimezone(UTC).isoformat()
        )
        async with self.db.sessions() as db:
            from app.analytics.epoch import current_epoch, product_attempts

            epoch = await current_epoch(db)
            query = select(UsageRecord).where(
                UsageRecord.created_at >= lower,
                UsageRecord.created_at < upper,
                UsageRecord.execution_source == source,
            )
            attempts_query = (
                select(Attempt)
                .options(
                    load_only(
                        Attempt.id,
                        Attempt.owner_user_id,
                        Attempt.status,
                        Attempt.created_at,
                        Attempt.execution_source,
                    )
                )
                .where(
                    Attempt.created_at >= lower,
                    Attempt.created_at < upper,
                    Attempt.execution_source == source,
                )
            )
            if not project:
                query = query.where(UsageRecord.owner_user_id == target_id)
                attempts_query = attempts_query.where(Attempt.owner_user_id == target_id)
            if epoch:
                product_ids = select(Attempt.id).where(
                    *product_attempts(), Attempt.created_at >= epoch.started_at
                )
                query = query.where(UsageRecord.operation_id.in_(product_ids))
                attempts_query = attempts_query.where(
                    *product_attempts(), Attempt.created_at >= epoch.started_at
                )
            if session_id:
                session = await db.get(Conversation, session_id)
                if session is None or (not project and session.owner_user_id != target_id):
                    raise AppError("SESSION_NOT_FOUND", 404, "Session not found")
                query = query.where(UsageRecord.session_id == session_id)
                attempts_query = attempts_query.where(Attempt.session_id == session_id)
            if model_id:
                query = query.where(UsageRecord.model_id == model_id)
            records = list(await db.scalars(query))
            if model_id:
                attempts_query = attempts_query.where(
                    Attempt.id.in_([r.operation_id for r in records])
                )
            attempts = list(await db.scalars(attempts_query))
            reservations = list(await db.scalars(select(Reservation)))
            user = await db.get(User, target_id)
            if not user:
                raise AppError("USER_NOT_FOUND", 404, "User not found")
            quota = self.settings.project_budget_usd if project else Decimal(user.quota_usd)
        scoped = reservations if project else [r for r in reservations if r.user_id == target_id]
        settled = sum(
            (
                Decimal(r.settled_usd)
                for r in scoped
                if r.settled_usd is not None and r.status == "settled"
            ),
            Decimal(0),
        )
        reserved = sum(
            (charged(r) for r in scoped if r.status not in ("settled", "released")), Decimal(0)
        )
        groups: dict[str, dict[str, list[UsageRecord]]] = {
            name: defaultdict(list) for name in ("daily", "models", "categories", "sessions")
        }
        cursor = start
        while cursor <= end:
            groups["daily"][cursor.isoformat()] = []
            cursor += timedelta(days=1)
        for row in records:
            groups["daily"][
                datetime.fromisoformat(row.created_at).astimezone(ZONE).date().isoformat()
            ].append(row)
            groups["models"][row.model_id].append(row)
            groups["categories"][row.category].append(row)
            # Project admin sees accounting IDs only, never titles or raw content.
            groups["sessions"][row.session_id or "research"].append(row)
        series: dict[str, list[UsageRecord]] = {
            key: [] for key in series_keys(start, end, granularity)
        }
        for row in records:
            series[series_key(datetime.fromisoformat(row.created_at), granularity)].append(row)
        return Analytics(
            reporting_epoch=epoch.started_at if epoch else None,
            granularity=granularity,
            timeseries=tuple(bucket(k, v) for k, v in series.items()),
            scope="project" if project else "selected_user" if user_id else "current_user",
            execution_source=source,
            start=start.isoformat(),
            end=end.isoformat(),
            totals=bucket("total", records),
            daily=tuple(bucket(k, v) for k, v in sorted(groups["daily"].items())),
            models=tuple(bucket(k, v) for k, v in sorted(groups["models"].items())),
            categories=tuple(bucket(k, v) for k, v in sorted(groups["categories"].items())),
            sessions=tuple(bucket(k, v) for k, v in sorted(groups["sessions"].items())),
            quota_usd=quota,
            settled_usd=settled,
            reserved_usd=reserved,
            available_usd=max(Decimal(0), quota - settled - reserved),
            project_available_usd=max(
                Decimal(0),
                self.settings.project_budget_usd
                - sum((charged(r) for r in reservations), Decimal(0)),
            ),
            requests=len(attempts),
            succeeded=sum(r.status == "succeeded" for r in attempts),
            failed=sum(r.status in ("failed", "interrupted") for r in attempts),
        )

    async def users(self, principal: Principal, offset: int, limit: int) -> tuple[AdminUser, ...]:
        administrator(principal)
        async with self.db.sessions() as db:
            users = list(
                await db.scalars(select(User).order_by(User.username).offset(offset).limit(limit))
            )
            rows = list(await db.scalars(select(Reservation)))
            return tuple(
                AdminUser(
                    id=u.id,
                    username=u.username,
                    role=u.role,
                    quota_usd=Decimal(u.quota_usd),
                    settled_usd=sum(
                        (
                            Decimal(r.settled_usd)
                            for r in rows
                            if r.user_id == u.id
                            and r.status == "settled"
                            and r.settled_usd is not None
                        ),
                        Decimal(0),
                    ),
                    reserved_usd=sum(
                        (
                            charged(r)
                            for r in rows
                            if r.user_id == u.id and r.status not in ("settled", "released")
                        ),
                        Decimal(0),
                    ),
                )
                for u in users
            )

    async def quota(self, principal: Principal, user_id: str, update: QuotaUpdate) -> None:
        administrator(principal)
        async with self.db.write() as db:
            user = await db.get(User, user_id)
            if not user:
                raise AppError("USER_NOT_FOUND", 404, "User not found")
            rows = await db.scalars(select(Reservation).where(Reservation.user_id == user_id))
            if update.quota_usd < sum((charged(r) for r in rows), Decimal(0)):
                raise AppError(
                    "BUDGET_EXCEEDED",
                    422,
                    "Quota cannot fall below spent plus outstanding reservations",
                )
            db.add(
                QuotaAudit(
                    id=uid(),
                    actor_id=principal.id,
                    user_id=user_id,
                    before_usd=user.quota_usd,
                    after_usd=str(update.quota_usd),
                    reason=update.reason,
                    created_at=now(),
                )
            )
            user.quota_usd = str(update.quota_usd)
