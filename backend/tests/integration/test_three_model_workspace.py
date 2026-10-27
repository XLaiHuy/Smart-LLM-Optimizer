from datetime import UTC, datetime
from uuid import uuid4

from app.contracts.dtos import ChatRequest
from app.core.validation import validate_answer
from app.storage.models import AnalyticsEpoch, User


async def chat(client, text="hello", **kwargs):
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": str(uuid4()),
            "message": text,
            "mode": "optimized",
            **kwargs,
        },
    )
    return sid, response


async def test_runtime_contains_only_three_current_models_and_no_secrets(client):
    response = await client.get("/v1/runtime-settings")
    assert response.status_code == 200
    data = response.json()
    assert [m["model_id"] for m in data["models"]] == [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "gpt-6-luna",
    ]
    assert "api_key" not in response.text.lower()
    assert data["group_policy_status"].endswith("SHADOW")


async def test_owned_execution_survives_failure_and_never_crosses_accounts(client, app):
    from app.contracts.dtos import ProviderResult

    class Wrong:
        async def generate(self, messages, opts):
            return ProviderResult(text="8899", execution_source="live", duration_ms=1)

    app.state.container.orchestrator.provider = Wrong()
    sid, response = await chat(
        client, "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số."
    )
    assert response.status_code == 502
    rid = response.json()["error"]["request_id"]
    evidence = (await client.get(f"/v1/requests/{rid}/execution")).json()
    assert evidence["status"] == "failed"
    assert any(e["stage"] == "validation" and e["status"] == "failed" for e in evidence["events"])
    assert len(evidence["calls"]) == 1
    await client.post("/v1/auth/logout")
    await client.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
    assert (await client.get(f"/v1/requests/{rid}/execution")).status_code == 404


async def test_reporting_epoch_resets_reports_but_not_balances(client, app):
    c = app.state.container
    _, first = await chat(client)
    assert first.status_code == 200
    before = (await client.get("/v1/usage")).json()
    async with c.db.write() as db:
        db.add(
            AnalyticsEpoch(
                id="test", started_at=datetime.now(UTC).isoformat(), reason="test watermark"
            )
        )
    empty = (await client.get("/v1/usage")).json()
    assert empty["totals"]["calls"] == 0 and empty["requests"] == 0
    assert empty["available_usd"] == before["available_usd"]
    assert empty["settled_usd"] == before["settled_usd"]
    assert empty["reserved_usd"] == before["reserved_usd"]
    _, second = await chat(client)
    assert second.status_code == 200
    current = (await client.get("/v1/usage")).json()
    assert current["requests"] == 1 and current["reporting_epoch"]
    assert (await client.get("/v1/overview")).json()["total_requests"] == 1
    owner, _ = await c.auth.login("alice", "password-alice")
    async with c.db.write() as db:
        user = await db.get(User, owner.id)
        user.account_purpose = "internal_audit"
    filtered = (await client.get("/v1/usage")).json()
    assert filtered["requests"] == 0 and filtered["totals"]["calls"] == 0
    assert filtered["available_usd"] == current["available_usd"]


async def test_schema_ref_is_rejected_before_any_call(client):
    _, response = await chat(client, response_schema={"$ref": "https://example.com/private"})
    assert response.status_code == 422


def test_json_schema_and_entity_bound_memory_validation():
    request = ChatRequest(
        session_id="s",
        client_request_id="r",
        mode="optimized",
        message="Nhắc lại hạn chót dưới dạng JSON.",
        response_schema={
            "type": "object",
            "properties": {"deadline": {"type": "string"}},
            "required": ["deadline"],
            "additionalProperties": False,
        },
    )
    assert (
        validate_answer(request, '{"deadline":"18/11/2026"}', {"deadline": "25/11/2026"}).status
        == "fail"
    )
    assert (
        validate_answer(request, '{"deadline":"25/11/2026"}', {"deadline": "25/11/2026"}).status
        == "pass"
    )
    assert validate_answer(request, '{"deadline":2}').status == "fail"
    assert validate_answer(request, "not json").status == "fail"


async def test_24_turn_memory_correction_cross_session_and_user_isolation(client, app):
    from app.memory.memory_manager import RetrievalMemoryManager
    from app.memory.retrieval import MemoryRetriever

    c = app.state.container
    c.orchestrator.memory = RetrievalMemoryManager(MemoryRetriever(), c.memory_store)
    owner, _ = await c.auth.login("alice", "password-alice")
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    for index in range(24):
        message = (
            "Tên tôi là An Khang. Hạn chót là 18/11/2026."
            if index == 0
            else (
                "Hạn chót là 25/11/2026, thay cho 18/11/2026."
                if index == 12
                else f"Ghi chú phụ số {index}: tiếp tục hội thoại."
            )
        )
        response = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": f"long-{index}",
                "message": message,
                "mode": "baseline",
            },
        )
        assert response.status_code == 200, response.text
    detail = (await client.get(f"/v1/sessions/{sid}")).json()
    assert len(detail["messages"]) == 48
    facts = (await c.memory_store.load(owner, sid)).facts
    assert {f.key: f.value for f in facts}["name"] == "An Khang"
    assert {f.key: f.value for f in facts}["deadline"].startswith("25/11/2026")
    from app.contracts.dtos import MemoryPlan

    other_session = await c.sessions.create(owner, "Recall")
    recalled = await c.orchestrator.memory.prepare(
        await c.sessions.snapshot(owner, other_session.id),
        MemoryPlan(enabled=True, query="Nhắc lại tên tôi và hạn chót mới nhất", token_budget=512),
    )
    memory_text = "\n".join(m.content for m in recalled.memory_messages)
    assert "An Khang" in memory_text and "25/11/2026" in memory_text
    bob, _ = await c.auth.login("bob", "password-bob")
    clean = await c.sessions.create(bob, "Clean")
    isolated = await c.orchestrator.memory.prepare(
        await c.sessions.snapshot(bob, clean.id),
        MemoryPlan(enabled=True, query="Nhắc lại tên tôi và hạn chót", token_budget=512),
    )
    assert not isolated.memory_messages
