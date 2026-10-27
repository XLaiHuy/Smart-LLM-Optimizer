"""Whole chat/ledger/error flow with fake providers; never uses a server key."""

from decimal import Decimal

import pytest

from app.contracts.dtos import ModelConfiguration, ProviderResult, RegistrySnapshot, Usage
from app.contracts.errors import AppError
from app.providers.catalog import Catalog, ModelEntry, price


def install(app, *, rejected=True, succeed_at=None):
    c = app.state.container
    models = tuple(
        ModelEntry(
            config_id=f"candidate-{i}",
            model_id=f"fake-{i}",
            kind="generation",
            context_window=10000,
            max_output_tokens=128,
            input_per_million=Decimal(".1"),
            output_per_million=Decimal(".2"),
            source_url="https://example.com/test-only",
            effective_at="test",
            verified_access=True,
            pricing_verified=True,
            fallback_approved=True,
            endpoint="chat_completions",
            base_url="https://example.com/v1",
        )
        for i in range(4)
    )
    embedding = models[0].model_copy(
        update={"config_id": "embedding", "kind": "embedding", "endpoint": "embeddings"}
    )
    catalog = Catalog(
        version="test-only-failover",
        baseline_config=models[0].config_id,
        embedding_config="embedding",
        models=(*models, embedding),
    )

    class FakeProvider:
        calls = 0

        def __init__(self):
            self.catalog = catalog

        async def generate(self, messages, opts):
            self.calls += 1
            if succeed_at == self.calls:
                usage = Usage(
                    scope="call",
                    usage_source="provider",
                    input_tokens=10,
                    output_tokens=2,
                    cached_input_tokens=0,
                    reasoning_tokens=0,
                )
                return ProviderResult(
                    text="hai",
                    execution_source="live",
                    usage=usage,
                    cost=price(catalog.entry(opts.config_id), usage, catalog.version),
                    provider_response_id="test-only-response",
                    duration_ms=1.0,
                )
            raise AppError(
                "RATE_LIMITED" if rejected else "DEPENDENCY_UNAVAILABLE",
                429 if rejected else 503,
                "fake provider fault",
                upstream_status=429 if rejected else None,
                retry_after_seconds=125 if rejected else None,
                dispatch_state="rejected" if rejected else "unknown",
            )

    provider = FakeProvider()
    c.orchestrator.provider = provider
    c.orchestrator.registry = RegistrySnapshot(
        mock_config_id=catalog.baseline_config,
        configurations=tuple(
            ModelConfiguration(
                config_id=e.config_id,
                model_id=e.model_id,
                execution_source="live",
                context_window=e.context_window,
                max_output_tokens=e.max_output_tokens,
                endpoint=e.endpoint,
            )
            for e in models
        ),
    )
    c.metering.catalog = catalog
    c.metering.settings = c.settings.model_copy(update={"provider_mode": "live"})
    return provider


async def request(client, key="fault"):
    session = (await client.post("/v1/sessions", json={"title": "Fault test"})).json()
    return await client.post(
        "/v1/chat",
        json={
            "session_id": session["id"],
            "client_request_id": key,
            "message": "1+1?",
            "mode": "optimized",
            "flags": {"router": False, "rewrite": False, "context": False, "memory": False},
        },
    )


async def test_known_rejection_failover_is_capped_and_failed_calls_are_owned(app, client):
    provider = install(app)
    response = await request(client)
    assert response.status_code == 429
    assert provider.calls == 3  # primary plus at most two failovers
    error = response.json()["error"]
    assert error["request_id"] and error["retry_after_seconds"] == 125
    assert response.headers["retry-after"] == "125"
    calls = await client.get(f"/v1/traces/{error['request_id']}/calls")
    assert calls.status_code == 200
    assert len(calls.json()) == 3
    assert all(
        call["error_code"] == "RATE_LIMITED" and call["upstream_status"] == 429
        for call in calls.json()
    )
    assert all(call["cost"]["serving_usd"] == "0" for call in calls.json())
    await client.post("/v1/auth/logout")
    await client.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
    assert (await client.get(f"/v1/traces/{error['request_id']}/calls")).status_code == 404


async def test_uncertain_dispatch_never_calls_another_paid_model(app, client):
    provider = install(app, rejected=False)
    response = await request(client)
    assert response.status_code == 503
    assert provider.calls == 1
    calls = (await client.get(f"/v1/traces/{response.json()['error']['request_id']}/calls")).json()
    assert calls[0]["cost"]["status"] == "unknown"
    assert calls[0]["dispatch_state"] == "unknown"
    assert calls[0]["cost"]["serving_usd"] is None


async def test_successful_failover_reports_actual_model_and_preserves_initial_route(app, client):
    provider = install(app, succeed_at=2)
    response = await request(client)
    assert response.status_code == 200, response.text
    data = response.json()
    assert provider.calls == 2
    assert data["route"]["model_id"] == "fake-1"
    assert data["route"]["initial_model_id"] == "fake-0"
    assert data["calls"][-1]["model_id"] == data["route"]["model_id"]
    assert data["calls"][-1]["dispatch_state"] == "completed"


async def test_sse_unexpected_error_never_exposes_private_exception(app, client, monkeypatch):
    async def broken_stream(*args, **kwargs):
        raise RuntimeError("private-prompt-and-provider-secret")
        yield {}

    monkeypatch.setattr(app.state.container.orchestrator, "execute_stream", broken_stream)
    session = (await client.post("/v1/sessions", json={"title": "SSE error"})).json()
    response = await client.post(
        "/v1/chat/stream",
        json={
            "session_id": session["id"],
            "client_request_id": "sse-error",
            "message": "hello",
            "mode": "baseline",
        },
    )
    assert "event: error" in response.text
    assert "DEPENDENCY_UNAVAILABLE" in response.text
    assert "private-prompt" not in response.text


async def test_verified_quality_failure_switches_once_and_keeps_both_call_costs(
    app, client, monkeypatch
):
    provider = install(app, succeed_at=1)

    async def replies(messages, opts):
        provider.calls += 1
        usage = Usage(
            scope="call",
            usage_source="provider",
            input_tokens=10,
            output_tokens=2,
            cached_input_tokens=0,
            reasoning_tokens=0,
        )
        return ProviderResult(
            text="8899" if provider.calls == 1 else "8900",
            execution_source="live",
            usage=usage,
            cost=price(provider.catalog.entry(opts.config_id), usage, provider.catalog.version),
            provider_response_id=f"quality-test-{provider.calls}",
            duration_ms=1.0,
        )

    monkeypatch.setattr(provider, "generate", replies)
    monkeypatch.setattr(
        app.state.container.orchestrator.group_policy,
        "quality_candidates",
        lambda task: {"candidate-1"},
    )
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "quality-switch",
            "message": "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            "mode": "optimized",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert provider.calls == 2 and data["response"]["content"] == "8900"
    assert data["route"]["reason"] == "QUALITY_VALIDATION_FALLBACK"
    assert [v["status"] for v in data["validation_results"]] == ["fail", "pass"]
    assert len(data["calls"]) == 2
    assert all(c["dispatch_state"] == "completed" for c in data["calls"])
    assert len((await client.get(f"/v1/sessions/{sid}")).json()["messages"]) == 2



@pytest.mark.parametrize("last_correct", [True, False])
async def test_provider_and_quality_switches_share_one_cap(app, client, monkeypatch, last_correct):
    provider = install(app)
    original = provider.generate

    async def mixed(messages, opts):
        if provider.calls == 0:
            return await original(messages, opts)  # known 429, never dispatched
        provider.calls += 1
        usage = Usage(
            scope="call",
            usage_source="provider",
            input_tokens=10,
            output_tokens=2,
            cached_input_tokens=0,
            reasoning_tokens=0,
        )
        return ProviderResult(
            text="8900" if provider.calls == 3 and last_correct else "8899",
            execution_source="live",
            usage=usage,
            cost=price(provider.catalog.entry(opts.config_id), usage, provider.catalog.version),
            duration_ms=1,
        )

    monkeypatch.setattr(provider, "generate", mixed)
    monkeypatch.setattr(
        app.state.container.orchestrator.group_policy,
        "quality_candidates",
        lambda task: {"candidate-1", "candidate-2", "candidate-3"},
    )
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "mixed-quality-cap",
            "message": "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            "mode": "optimized",
        },
    )
    assert provider.calls == 3
    assert response.status_code == (200 if last_correct else 502), response.text
    data = response.json()
    rid = data["request_id"] if last_correct else data["error"]["request_id"]
    calls = (await client.get(f"/v1/traces/{rid}/calls")).json()
    assert len(calls) == 3
    assert sum(Decimal(call["cost"]["serving_usd"]) for call in calls) > 0
    assert len((await client.get(f"/v1/sessions/{sid}")).json()["messages"]) == (
        2 if last_correct else 0
    )
