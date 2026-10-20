from decimal import Decimal

from sqlalchemy import select

from app.contracts.dtos import CallRecord, Principal, RemainingBudget
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import Attempt, Reconciliation, ResearchRun, Reservation, UsageRecord, User
from app.storage.repositories import uid


def amount(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0:
        raise AppError("VALIDATION_ERROR", 422, "Invalid monetary amount")
    return value


def charged(row: Reservation) -> Decimal:
    if row.status == "released":
        return Decimal(0)
    return Decimal(row.settled_usd) if row.settled_usd is not None else Decimal(row.reserved_usd)


class SqlBudgetLedger:
    def __init__(self, db: Database, project_limit: Decimal):
        self.db = db
        self.project_limit = project_limit

    async def reserve(
        self,
        principal: Principal,
        request_id: str,
        call_id: str,
        upper_usd: Decimal,
        request_limit: Decimal,
    ) -> str:
        amount(upper_usd)
        amount(request_limit)
        async with self.db.write() as db:
            attempt = await db.get(Attempt, request_id)
            user = await db.get(User, principal.id)
            if (
                not attempt
                or attempt.owner_user_id != principal.id
                or attempt.status != "running"
                or not user
            ):
                raise AppError("ATTEMPT_NOT_REPLAYABLE", 409, "Invalid reservation owner/attempt")
            rows = list(await db.scalars(select(Reservation)))
            if attempt.research_run_id:
                run = await db.get(ResearchRun, attempt.research_run_id)
                operation_ids = set(
                    await db.scalars(
                        select(Attempt.id).where(Attempt.research_run_id == attempt.research_run_id)
                    )
                )
                if (
                    not run
                    or run.status != "running"
                    or run.owner_user_id != principal.id
                    or sum((charged(r) for r in rows if r.request_id in operation_ids), Decimal(0))
                    + upper_usd
                    > Decimal(run.budget_usd)
                ):
                    raise AppError("BUDGET_EXCEEDED", 422, "Research run budget exhausted")
            if any(r.request_id == request_id and r.call_id == call_id for r in rows):
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Reservation already exists")
            request_spend = sum(
                (charged(r) for r in rows if r.request_id == request_id), Decimal(0)
            )
            user_spend = sum((charged(r) for r in rows if r.user_id == principal.id), Decimal(0))
            project_spend = sum((charged(r) for r in rows), Decimal(0))
            if request_spend + upper_usd > request_limit:
                raise AppError("BUDGET_EXCEEDED", 422, "Request budget exhausted")
            if (
                user_spend + upper_usd > Decimal(user.quota_usd)
                or project_spend + upper_usd > self.project_limit
            ):
                raise AppError("QUOTA_EXCEEDED", 429, "User/project quota exhausted")
            reservation_id = uid()
            db.add(
                Reservation(
                    id=reservation_id,
                    user_id=principal.id,
                    request_id=request_id,
                    call_id=call_id,
                    reserved_usd=str(upper_usd),
                    status="reserved",
                )
            )
            return reservation_id

    async def mark_dispatched(self, reservation_id: str) -> None:
        async with self.db.write() as db:
            row = await db.get(Reservation, reservation_id)
            if row is None or row.status != "reserved":
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Reservation not dispatchable")
            row.status = "dispatched"
            attempt = await db.get(Attempt, row.request_id)
            if attempt:
                attempt.dispatched = True

    async def settle(self, reservation_id: str, actual_usd: Decimal | None) -> None:
        if actual_usd is not None:
            amount(actual_usd)
        async with self.db.write() as db:
            row = await db.get(Reservation, reservation_id)
            if row is None or row.status not in ("reserved", "dispatched", "unresolved"):
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Reservation already finalized")
            row.settled_usd = str(actual_usd) if actual_usd is not None else None
            row.status = "settled" if actual_usd is not None else "unresolved"

    async def release(self, reservation_id: str) -> None:
        async with self.db.write() as db:
            row = await db.get(Reservation, reservation_id)
            if row is None or row.status != "reserved":
                raise AppError(
                    "IDEMPOTENCY_CONFLICT", 409, "Only undispatched reservations can release"
                )
            row.status = "released"

    async def remaining(
        self, principal: Principal, operation_id: str, request_limit: Decimal
    ) -> RemainingBudget:
        async with self.db.sessions() as db:
            rows = list(await db.scalars(select(Reservation)))
            user = await db.get(User, principal.id)
            if not user:
                raise AppError("AUTH_REQUIRED", 401, "User no longer exists")
            available = min(
                request_limit
                - sum((charged(r) for r in rows if r.request_id == operation_id), Decimal(0)),
                Decimal(user.quota_usd)
                - sum((charged(r) for r in rows if r.user_id == principal.id), Decimal(0)),
                self.project_limit - sum((charged(r) for r in rows), Decimal(0)),
            )
            attempt = await db.get(Attempt, operation_id)
            if attempt and attempt.research_run_id:
                run = await db.get(ResearchRun, attempt.research_run_id)
                ids = set(
                    await db.scalars(
                        select(Attempt.id).where(Attempt.research_run_id == attempt.research_run_id)
                    )
                )
                if run:
                    available = min(
                        available,
                        Decimal(run.budget_usd)
                        - sum((charged(r) for r in rows if r.request_id in ids), Decimal(0)),
                    )
            return RemainingBudget(usd=max(Decimal(0), available))

    async def finish_call(self, call: CallRecord, reservation_id: str | None) -> None:
        """Usage and financial settlement share the same commit boundary."""
        async with self.db.write() as db:
            usage = await db.get(UsageRecord, call.call_id)
            if not usage:
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Missing started call")
            if reservation_id:
                row = await db.get(Reservation, reservation_id)
                if not row or row.status not in ("reserved", "dispatched", "unresolved"):
                    raise AppError("IDEMPOTENCY_CONFLICT", 409, "Call already settled")
                if (
                    row.call_id != call.call_id
                    or row.request_id != usage.operation_id
                    or row.user_id != usage.owner_user_id
                ):
                    raise AppError(
                        "IDEMPOTENCY_CONFLICT", 409, "Reservation/call ownership mismatch"
                    )
                if call.cost.serving_usd is not None:
                    amount(call.cost.serving_usd)
                row.settled_usd = (
                    str(call.cost.serving_usd) if call.cost.serving_usd is not None else None
                )
                row.status = "settled" if call.cost.serving_usd is not None else "unresolved"
            usage.record_json = call.model_dump_json()

    async def unresolved(
        self, principal: Principal, offset: int, limit: int
    ) -> list[dict[str, str]]:
        if principal.role != "admin":
            raise AppError("FORBIDDEN_ACTION", 403, "Administrator required")
        async with self.db.sessions() as db:
            rows = await db.scalars(
                select(Reservation)
                .where(Reservation.status == "unresolved")
                .order_by(Reservation.id)
                .offset(offset)
                .limit(limit)
            )
            return [
                {
                    "id": r.id,
                    "operation_id": r.request_id,
                    "call_id": r.call_id,
                    "user_id": r.user_id,
                    "reserved_usd": r.reserved_usd,
                }
                for r in rows
            ]

    async def reconcile(
        self,
        principal: Principal,
        reservation_id: str,
        actual_usd: Decimal,
        reason: str,
        evidence_reference: str,
    ) -> str:
        if principal.role != "admin":
            raise AppError("FORBIDDEN_ACTION", 403, "Administrator required")
        amount(actual_usd)
        from app.storage.repositories import now

        async with self.db.write() as db:
            row = await db.get(Reservation, reservation_id)
            if not row or row.status != "unresolved":
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Reservation is not unresolved")
            audit_id = uid()
            db.add(
                Reconciliation(
                    id=audit_id,
                    reservation_id=row.id,
                    actor_id=principal.id,
                    amount_usd=str(actual_usd),
                    reason=reason,
                    evidence_reference=evidence_reference,
                    created_at=now(),
                )
            )
            row.settled_usd, row.status = str(actual_usd), "settled"
            # Overlay billing evidence; native usage/immutable success traces stay untouched.
            usage = await db.get(UsageRecord, row.call_id)
            if usage:
                call = CallRecord.model_validate_json(usage.record_json)
                usage.record_json = call.model_copy(
                    update={"reconciled_usd": actual_usd, "reconciliation_id": audit_id}
                ).model_dump_json()
            return audit_id
