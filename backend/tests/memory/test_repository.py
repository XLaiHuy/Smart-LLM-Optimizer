import httpx
import pytest
from fastapi import FastAPI

from app.composition import Container
from app.contracts.dtos import DerivedMemory, Fact
from app.contracts.errors import AppError


async def test_derived_memory_scope_and_committed_evidence(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    c: Container = app.state.container
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "m",
            "message": "I live in Hue",
            "mode": "baseline",
        },
    )
    user, _ = await c.auth.login("alice", "password-alice")
    bob, _ = await c.auth.login("bob", "password-bob")
    detail = await c.sessions.detail(user, sid)
    with pytest.raises(AppError):
        await c.memory_store.save(
            user,
            sid,
            DerivedMemory(
                snapshot_revision=1,
                facts=(Fact(key="city", value="Hue", source_message_ids=("future",)),),
            ),
        )
    state = DerivedMemory(
        snapshot_revision=1,
        facts=(Fact(key="city", value="Hue", source_message_ids=(detail.messages[0].id,)),),
    )
    await c.memory_store.save(user, sid, state)
    assert (await c.sessions.snapshot(user, sid)).facts == state.facts
    with pytest.raises(AppError):
        await c.memory_store.load(bob, sid)
