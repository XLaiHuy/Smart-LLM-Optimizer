import asyncio
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.composition import Container
from app.contracts.dtos import ChatRequest, ExecutionRequest
from app.contracts.errors import AppError
from app.storage.models import Reservation, User
from app.storage.repositories import uid


@pytest.mark.parametrize("limit_scope", ("project", "user"))
async def test_reservation_race_unknown_release_reconcile_and_recovery(
    client: httpx.AsyncClient, app: FastAPI, limit_scope: str
) -> None:
    c: Container = app.state.container
    principal, _ = await c.auth.login("alice", "password-alice")
    requests = []
    for i in range(2):
        session = await c.sessions.create(principal, str(i))
        execution = ExecutionRequest(
            request_id=uid(),
            principal=principal,
            request=ChatRequest(
                session_id=session.id, client_request_id=str(i), message="fixture", mode="baseline"
            ),
        )
        await c.sessions.claim(execution, str(i))
        requests.append(execution)
    if limit_scope == "project":
        c.ledger.project_limit = Decimal("0.100000001")
    else:
        async with c.db.write() as db:
            user = await db.get(User, principal.id)
            assert user is not None
            user.quota_usd = "0.100000001"

    async def reserve(index: int) -> str:
        return await c.ledger.reserve(
            principal, requests[index].request_id, f"call-{index}", Decimal("0.06"), Decimal("1")
        )

    results = await asyncio.gather(reserve(0), reserve(1), return_exceptions=True)
    assert sum(isinstance(r, str) for r in results) == 1
    assert next(r for r in results if isinstance(r, AppError)).code == "QUOTA_EXCEEDED"
    reservation = next(r for r in results if isinstance(r, str))
    await c.ledger.mark_dispatched(reservation)
    await c.ledger.settle(reservation, None)
    try:
        await c.ledger.release(reservation)
    except AppError as exc:
        assert exc.status == 409
    else:
        raise AssertionError("Unresolved charges cannot be released")
    admin = await c.auth.create_user("ledger-admin", "ledger-admin-password", "admin")
    await c.ledger.reconcile(
        admin, reservation, Decimal("0.000000001"), "fixture statement", "test-evidence-001"
    )
    async with c.db.sessions() as db:
        row = await db.get(Reservation, reservation)
        assert row.settled_usd == "1E-9" and row.status == "settled"
    remaining_request = requests[0] if isinstance(results[0], AppError) else requests[1]
    reserved = await c.ledger.reserve(
        principal, remaining_request.request_id, "crash", Decimal("0.1"), Decimal("0.1")
    )
    await c.sessions.mark_dispatched(remaining_request.request_id)
    await c.sessions.recover_interrupted()
    async with c.db.sessions() as db:
        row = await db.get(Reservation, reserved)
        assert row.status == "unresolved"
    try:
        await c.sessions.claim(remaining_request, "same")
    except AppError as exc:
        assert exc.status == 409


async def test_request_budget_and_undispatched_release(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    c: Container = app.state.container
    principal, _ = await c.auth.login("alice", "password-alice")
    session = await c.sessions.create(principal, "budget")
    req = ExecutionRequest(
        request_id=uid(),
        principal=principal,
        request=ChatRequest(
            session_id=session.id, client_request_id="budget", message="x", mode="baseline"
        ),
    )
    await c.sessions.claim(req, "budget")
    try:
        await c.ledger.reserve(principal, req.request_id, "too-big", Decimal("1"), Decimal("0.5"))
    except AppError as exc:
        assert exc.code == "BUDGET_EXCEEDED"
    reserved = await c.ledger.reserve(
        principal, req.request_id, "not-sent", Decimal("0.4"), Decimal("0.5")
    )
    await c.ledger.release(reserved)
    async with c.db.sessions() as db:
        rows = list(await db.scalars(select(Reservation)))
        assert len(rows) == 1 and rows[0].status == "released"
