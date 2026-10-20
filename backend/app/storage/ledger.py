from decimal import Decimal

from sqlalchemy import select

from app.contracts.dtos import Principal
from app.contracts.errors import AppError
from app.storage.database import Database
from app.storage.models import Attempt, Reservation, User
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

    async def reconcile(self, reservation_id: str, actual_usd: Decimal) -> None:
        async with self.db.sessions() as db:
            row = await db.get(Reservation, reservation_id)
            if row is None or row.status != "unresolved":
                raise AppError("IDEMPOTENCY_CONFLICT", 409, "Reservation is not unresolved")
        await self.settle(reservation_id, actual_usd)
