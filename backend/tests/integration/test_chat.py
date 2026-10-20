import asyncio
from itertools import product
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.composition import Container
from app.contracts.dtos import FeatureFlags, Message, ProviderOptions, ProviderResult
from app.storage.models import Attempt, InferenceCall, StoredMessage


async def session(client: httpx.AsyncClient) -> str:
    response = await client.post("/v1/sessions", json={"title": "Unicode tiếng Việt"})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize("values", list(product((False, True), repeat=4)))
async def test_all_flags_preserve_history_and_one_call(
    client: httpx.AsyncClient, app: FastAPI, values: tuple[bool, ...]
) -> None:
    sid = await session(client)
    flags = dict(zip(FeatureFlags.model_fields, values, strict=True))
    body = {
        "session_id": sid,
        "client_request_id": "first",
        "message": "Không ít hơn 10. ĐH Mở",
        "mode": "optimized",
        "flags": flags,
    }
    result = await client.post("/v1/chat", json=body)
    assert result.status_code == 200, result.text
    data = result.json()
    assert len(data["calls"]) == 1
    assert data["cost"] == {
        "scope": "all_calls",
        "status": "not_billable",
        "serving_usd": None,
        "price_catalog_version": None,
        "known_subtotal_usd": None,
    }
    assert data["quality_score"] is None and data["cost_saving_ratio"] is None
    assert data["usage"]["input_tokens"] is None and data["timing"]["ttft_ms"] is None
    for state in data["optimizations"]:
        assert state["status"] == ("not_implemented" if flags[state["module"]] else "disabled")
    replay = await client.post("/v1/chat", json=body)
    assert replay.json() == data
    body["message"] = "payload differs"
    assert (await client.post("/v1/chat", json=body)).status_code == 409
    second = await client.post(
        "/v1/chat",
        json={
            **body,
            "client_request_id": "second",
            "mode": "baseline",
            "flags": {k: False for k in flags},
        },
    )
    assert second.status_code == 200
    assert "3 messages received" in second.json()["response"]["content"]
    history = (await client.get(f"/v1/sessions/{sid}")).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert history["messages"][0]["content"] == "Không ít hơn 10. ĐH Mở"
    assert history["revision"] == 2
    c: Container = app.state.container
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(InferenceCall)) == 2


async def test_baseline_conflicts_and_public_fields(client: httpx.AsyncClient) -> None:
    sid = await session(client)
    payload = {"session_id": sid, "client_request_id": "x", "message": "hi", "mode": "baseline"}
    for extra in (
        {"flags": {"rewrite": True}},
        {"user_id": "spoof"},
        {"history": []},
        {"message": "  "},
        {"policy_id": "foundation-mock-v3"},
    ):
        response = await client.post("/v1/chat", json={**payload, **extra})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (await client.get(f"/v1/sessions/{sid}")).json()["messages"] == []


async def test_concurrent_dedupe_session_lease_and_failure(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    c: Container = app.state.container
    sid = await session(client)
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingProvider:
        async def generate(
            self, messages: tuple[Message, ...], opts: ProviderOptions
        ) -> ProviderResult:
            entered.set()
            await release.wait()
            return ProviderResult(text="done", duration_ms=1)

    c.orchestrator.provider = BlockingProvider()
    body = {
        "session_id": sid,
        "client_request_id": "concurrent",
        "message": "hello",
        "mode": "baseline",
    }
    task = asyncio.create_task(client.post("/v1/chat", json=body))
    await asyncio.wait_for(entered.wait(), 5)
    assert (await client.post("/v1/chat", json=body)).json()["error"][
        "code"
    ] == "REQUEST_IN_PROGRESS"
    assert (await client.post("/v1/chat", json={**body, "client_request_id": "other"})).json()[
        "error"
    ]["code"] == "SESSION_BUSY"
    assert (await client.delete(f"/v1/sessions/{sid}")).status_code == 409
    release.set()
    assert (await task).status_code == 200
    c.orchestrator.provider = AsyncMock()
    c.orchestrator.provider.generate.side_effect = RuntimeError("private provider detail")
    failed = await client.post("/v1/chat", json={**body, "client_request_id": "failed"})
    assert failed.status_code == 503 and "private provider" not in failed.text
    assert (
        await client.post("/v1/chat", json={**body, "client_request_id": "failed"})
    ).status_code == 409
    assert len((await client.get(f"/v1/sessions/{sid}")).json()["messages"]) == 2


async def test_storage_commit_rollback(client: httpx.AsyncClient, app: FastAPI) -> None:
    c: Container = app.state.container
    sid = await session(client)
    from sqlalchemy import event

    def fail_after_insert(*args: object) -> None:
        raise RuntimeError("simulated disk failure after insert")

    event.listen(StoredMessage, "after_insert", fail_after_insert)
    try:
        response = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": "disk",
                "message": "x",
                "mode": "baseline",
            },
        )
    finally:
        event.remove(StoredMessage, "after_insert", fail_after_insert)
    assert response.status_code == 503
    assert (await client.get(f"/v1/sessions/{sid}")).json()["messages"] == []
    async with c.db.sessions() as db:
        attempt = await db.scalar(select(Attempt))
        assert attempt.status == "failed"


async def test_timeout_and_cancellation_release_session(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    c: Container = app.state.container
    sid = await session(client)
    entered = asyncio.Event()

    class WaitingProvider:
        async def generate(
            self, messages: tuple[Message, ...], opts: ProviderOptions
        ) -> ProviderResult:
            entered.set()
            await asyncio.sleep(20)
            return ProviderResult(text="unreachable", duration_ms=20000)

    c.orchestrator.provider = WaitingProvider()
    body = {
        "session_id": sid,
        "client_request_id": "timeout",
        "message": "hello",
        "mode": "baseline",
        "constraints": {"deadline_ms": 100},
    }
    timed_out = await client.post("/v1/chat", json=body)
    assert timed_out.status_code == 504
    assert (await client.get(f"/v1/sessions/{sid}")).json()["active"] is False
    entered.clear()
    body["client_request_id"] = "cancel"
    body["constraints"] = {"deadline_ms": 30000}
    task = asyncio.create_task(client.post("/v1/chat", json=body))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    detail = (await client.get(f"/v1/sessions/{sid}")).json()
    assert detail["messages"] == [] and detail["active"] is False
