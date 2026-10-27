import asyncio
import json
import socket
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.contracts.dtos import (
    CallRecord,
    ContextResult,
    CostEstimate,
    FeatureFlags,
    MeteringContext,
    OptimizationState,
    PolicySnapshot,
    RemainingBudget,
    Usage,
)
from app.contracts.errors import AppError
from app.providers.catalog import Catalog
from app.routing.experiments.fixtures import COSTS, EVIDENCE, REGISTRY, grade_fixture, manifest
from app.routing.features import extract_features
from app.routing.policies import PolicyRouter
from app.storage.models import (
    Attempt,
    Conversation,
    Reconciliation,
    ResearchRun,
    ResearchTrial,
    Reservation,
    UsageRecord,
)
from app.storage.repositories import now, uid


async def admin_login(app, client):
    admin = await app.state.container.auth.create_user(
        "research-admin", "password-for-tests", "admin"
    )
    response = await client.post(
        "/v1/auth/login", json={"username": "research-admin", "password": "password-for-tests"}
    )
    assert response.status_code == 200
    return admin


async def wait_run(client, run_id):
    for _ in range(400):
        response = await client.get(f"/v1/research/runs/{run_id}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] not in ("pending", "running"):
            return result
        await asyncio.sleep(0.02)
    raise AssertionError("Research worker did not finish")


def test_catalog_rejects_empty_duplicate_and_wrong_kind():
    with pytest.raises(ValidationError):
        Catalog(version="x", baseline_config="b", embedding_config="e", models=())
    from app.providers.catalog import ModelEntry

    base = ModelEntry(
        config_id="b",
        model_id="fake",
        kind="generation",
        context_window=2000,
        max_output_tokens=100,
        input_per_million=Decimal(1),
        source_url="https://example.org",
        effective_at="test",
    )
    embed = base.model_copy(update={"config_id": "e", "kind": "embedding"})
    with pytest.raises(ValidationError):
        Catalog(version="x", baseline_config="b", embedding_config="e", models=(base, base, embed))
    with pytest.raises(ValidationError):
        Catalog(version="x", baseline_config="e", embedding_config="b", models=(base, embed))


def test_fixture_checker_does_not_treat_code_presence_as_json_preservation():
    case = manifest().cases[3]
    assert not grade_fixture(case.expected, case, None)
    assert not grade_fixture('{"code":"wrong"}', case, None)
    assert grade_fixture(json.dumps({"code": case.expected}), case, None)


@pytest.mark.parametrize(
    "case_number,expected",
    [
        (0, "fixture-small"),
        (3, "fixture-reference"),
        (6, "fixture-reference"),
        (18, "fixture-reference"),
    ],
)
def test_router_capability_evidence_and_context(case_number, expected):
    case = manifest().cases[case_number]
    profile = extract_features(case.messages[-1].content)
    prepared = ContextResult(
        messages=case.messages,
        provenance=(),
        state=OptimizationState(module="context", status="disabled", reason="test"),
    )
    policy = PolicySnapshot(
        policy_id="test",
        flags=FeatureFlags(router=True),
        sandbox=True,
        evidence=EVIDENCE,
        evidence_version="fixture",
    )
    result = PolicyRouter().select(
        profile, prepared, REGISTRY, COSTS, policy, RemainingBudget(usd=Decimal(1), deadline_ms=100)
    )
    assert result.config_id == expected
    assert result.policy_hash
    # Fixture evidence is never accepted by production routing.
    production = PolicyRouter().select(
        profile,
        prepared,
        REGISTRY,
        COSTS,
        policy.model_copy(update={"sandbox": False}),
        RemainingBudget(usd=Decimal(1)),
    )
    assert production.config_id == REGISTRY.mock_config_id
    assert production.reason == "baseline_quality_uncertain"


async def test_research_offline_matrix_isolated_deduped_and_exported(app, client, monkeypatch):
    assert (await client.get("/v1/research/configs")).status_code == 403
    await admin_login(app, client)

    lab = (await client.get("/v1/research/lab")).json()
    modules = {module["id"]: module for module in lab["modules"]}
    assert modules["router"] == {
        "id": "router",
        "implemented": True,
        "status": "requires_qualified_data",
    }
    assert modules["prompt"] == {
        "id": "prompt",
        "implemented": False,
        "status": "not_implemented",
    }
    assert modules["memory"] == {
        "id": "memory",
        "implemented": False,
        "status": "not_implemented",
    }

    unavailable = await client.post(
        "/v1/research/ablation",
        json={"size": 500, "router": True, "prompt": True, "memory": True},
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "BENCHMARK_NOT_READY"

    def no_network(*args, **kwargs):
        raise AssertionError("Simulation opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    c = app.state.container
    assert (await client.get("/v1/research/configs")).json()["cases"] == 20
    request = {"client_request_id": "matrix"}
    preflight = await client.post("/v1/research/preflight", json=request)
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["trials"] == 120
    before = (await client.get("/v1/sessions")).json()
    created = await client.post("/v1/research/runs", json=request)
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert (await client.post("/v1/research/runs", json=request)).json()["id"] == run_id
    assert (await client.post("/v1/research/runs", json={**request, "seed": 1})).status_code == 409
    complete = await wait_run(client, run_id)
    assert complete["status"] == "succeeded", complete
    assert complete["completed"] == 120
    assert (await client.get("/v1/sessions")).json() == before
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Reservation)) == 0
        assert await db.scalar(select(func.count()).select_from(UsageRecord)) == 0
    export = await client.get(f"/v1/research/runs/{run_id}/export")
    records = [json.loads(line) for line in export.text.splitlines()]
    assert records[0]["record_type"] == "run"
    rows = records[1:]
    assert len(rows) == 120
    for case_id in {r["trial"]["case_id"] for r in rows}:
        assert (
            len({r["trial"]["snapshot_hash"] for r in rows if r["trial"]["case_id"] == case_id})
            == 1
        )
    for row in rows:
        for call in row["trial"]["calls"]:
            assert call["usage"]["input_tokens"] is None
            assert call["cost"]["serving_usd"] is None
    summary = (await client.get(f"/v1/research/runs/{run_id}/summary")).json()
    assert len(summary["routes"]) == 2
    assert sum(p["trials"] for p in summary["policies"]) == 120
    assert (
        "simulation_upper_usd"
        in (await client.get(f"/v1/research/runs/{run_id}/export?format=csv")).text
    )
    # Same seed/snapshot yields identical model choices and exclusions.
    second = (await client.post("/v1/research/runs", json={"client_request_id": "matrix-2"})).json()
    await wait_run(client, second["id"])
    again = [
        json.loads(line)["trial"]
        for line in (await client.get(f"/v1/research/runs/{second['id']}/export")).text.splitlines()
        if json.loads(line)["record_type"] == "trial"
    ]
    assert [r["trial"]["route"] for r in rows] == [r["route"] for r in again]
    assert (
        await client.post(
            "/v1/research/runs", json={"client_request_id": "live", "execution_source": "live"}
        )
    ).status_code == 422


async def test_research_cancel_busy_ownership_restart(app, client):
    admin = await admin_login(app, client)
    c = app.state.container
    entered, finish = asyncio.Event(), asyncio.Event()
    original = c.research.provider.generate

    async def slow(messages, opts):
        entered.set()
        await finish.wait()
        return await original(messages, opts)

    c.research.provider.generate = slow
    run = (await client.post("/v1/research/runs", json={"client_request_id": "cancel"})).json()
    await asyncio.wait_for(entered.wait(), 5)
    assert (
        await client.post("/v1/research/runs", json={"client_request_id": "busy"})
    ).status_code == 409
    assert (await client.post(f"/v1/research/runs/{run['id']}/cancel")).status_code == 200
    finish.set()
    done = await wait_run(client, run["id"])
    assert done["status"] == "cancelled" and done["completed"] == 1
    other = await c.auth.create_user("other-admin", "another-password", "admin")
    with pytest.raises(AppError) as missing:
        await c.research.get(other, run["id"])
    assert missing.value.status == 404
    await c.research.close()
    async with c.db.write() as db:
        row = await db.get(ResearchRun, run["id"])
        row.status = "running"
    await c.research.start()
    assert (await c.research.get(admin, run["id"])).status == "interrupted"
    assert (await c.research.get(admin, run["id"])).completed == 1


async def test_accounting_operation_without_chat_and_audited_overlay(app, client):
    admin = await admin_login(app, client)
    c = app.state.container
    operation = uid()
    async with c.db.write() as db:
        db.add(
            Attempt(
                id=operation,
                owner_user_id=admin.id,
                session_id=None,
                client_request_id="meter-only",
                payload_hash="test",
                status="running",
                dispatched=False,
                created_at=now(),
                execution_source="live",
            )
        )
    reservation = await c.ledger.reserve(
        admin, operation, "unknown-call", Decimal("0.1"), Decimal("0.2")
    )
    await c.ledger.mark_dispatched(reservation)
    async with c.db.write() as db:
        db.add(
            UsageRecord(
                id="unknown-call",
                owner_user_id=admin.id,
                operation_id=operation,
                session_id=None,
                created_at=now(),
                category="evaluation",
                execution_source="live",
                model_id="fixture",
                record_json=CallRecord(
                    call_id="unknown-call",
                    model_id="fixture",
                    usage=Usage(usage_source="unknown"),
                    cost=CostEstimate(status="unknown"),
                ).model_dump_json(),
            )
        )
    call = CallRecord(
        call_id="unknown-call",
        model_id="fixture",
        usage=Usage(usage_source="unknown"),
        cost=CostEstimate(status="unknown"),
    )
    await c.ledger.finish_call(call, reservation)
    listed = (await client.get("/v1/admin/billing/unresolved")).json()
    assert listed[0]["id"] == reservation
    response = await client.post(
        f"/v1/admin/billing/{reservation}/reconcile",
        json={
            "actual_usd": "0.02",
            "reason": "provider statement",
            "evidence_reference": "billing-reference-001",
        },
    )
    assert response.status_code == 200, response.text
    assert (
        await client.post(
            f"/v1/admin/billing/{reservation}/reconcile",
            json={
                "actual_usd": "0.02",
                "reason": "provider statement",
                "evidence_reference": "billing-reference-001",
            },
        )
    ).status_code == 409
    report = (await client.get("/v1/usage?source=live")).json()
    assert Decimal(report["totals"]["usd"]) == Decimal("0.02")
    assert report["totals"]["input_tokens"] is None
    assert report["totals"]["p50_ms"] is None
    assert Decimal(report["settled_usd"]) == Decimal("0.02")
    assert "0.02" in (await client.get("/v1/usage/export?source=live&format=csv")).text
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Reconciliation)) == 1
        assert await db.scalar(select(func.count()).select_from(Conversation)) == 0
        record = await db.get(UsageRecord, "unknown-call")
        assert CallRecord.model_validate_json(record.record_json).cost.status == "unknown"
    # Metering supports a session-free context and retains unknown duration until completion.
    context = MeteringContext(
        operation_id=operation, principal=admin, max_total_usd=Decimal(1), category="evaluation"
    )
    call_id, _ = await c.metering._start(context, "provider", "fake", Decimal(0))
    async with c.db.sessions() as db:
        record = await db.get(UsageRecord, call_id)
        assert record.session_id is None
        assert CallRecord.model_validate_json(record.record_json).duration_ms is None


async def test_run_budget_across_operations_and_atomic_finish_rollback(app, client):
    admin = await admin_login(app, client)
    c = app.state.container
    run_id = uid()
    ids = [uid(), uid()]
    async with c.db.write() as db:
        db.add(
            ResearchRun(
                id=run_id,
                owner_user_id=admin.id,
                client_request_id="budget-group",
                payload_hash="fixture",
                snapshot_json="{}",
                status="running",
                cancel_requested=False,
                budget_usd="0.1",
                created_at=now(),
            )
        )
        await db.flush()
        for i, operation in enumerate(ids):
            db.add(
                Attempt(
                    id=operation,
                    owner_user_id=admin.id,
                    session_id=None,
                    research_run_id=run_id,
                    client_request_id=f"trial-budget-{i}",
                    payload_hash="fixture",
                    status="running",
                    dispatched=False,
                    execution_source="live",
                    created_at=now(),
                )
            )
    results = await asyncio.gather(
        *(
            c.ledger.reserve(admin, op, f"call-{i}", Decimal("0.06"), Decimal(1))
            for i, op in enumerate(ids)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, str) for r in results) == 1
    assert next(r for r in results if isinstance(r, AppError)).code == "BUDGET_EXCEEDED"
    assert (await c.ledger.remaining(admin, ids[0], Decimal(1))).usd == Decimal("0.04")
    reservation = next(r for r in results if isinstance(r, str))
    # Missing usage row must not partially settle the financial reservation.
    with pytest.raises(AppError):
        await c.ledger.finish_call(
            CallRecord(
                call_id="missing",
                model_id="fixture",
                cost=CostEstimate(status="estimated", serving_usd=Decimal("0.01")),
            ),
            reservation,
        )
    async with c.db.sessions() as db:
        row = await db.get(Reservation, reservation)
        assert row.status == "reserved" and row.settled_usd is None


async def test_disabled_live_path_can_be_exercised_with_metered_fakes_only(
    app, client, monkeypatch
):
    from app.config import Settings
    from app.contracts.dtos import ProviderResult
    from app.providers.catalog import ModelEntry, price
    from app.routing.experiments.fixtures import FixtureProvider
    from app.routing.experiments.live import LiveResearchWiring
    from app.routing.experiments.service import ResearchService

    admin = await admin_login(app, client)
    c = app.state.container

    def no_network(*args, **kwargs):
        raise AssertionError("Metered fake attempted network access")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    entries = tuple(
        ModelEntry(
            config_id=m.config_id,
            model_id=m.model_id,
            kind="generation",
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            structured_output=m.structured_output,
            input_per_million=Decimal("1"),
            output_per_million=Decimal("2"),
            cached_per_million=Decimal("0.1"),
            verified_access=True,
            pricing_verified=True,
            source_url="https://example.org/fixture",
            effective_at="fixture",
        )
        for m in REGISTRY.configurations
    )
    embedding = entries[0].model_copy(update={"config_id": "embed", "kind": "embedding"})
    catalog = Catalog(
        version="metered-test",
        baseline_config="fixture-reference",
        embedding_config="embed",
        models=(*entries, embedding),
    )
    settings = Settings(
        database_path=c.settings.database_path,
        app_env="test",
        provider_mode="live",
        research_live_enabled=True,
    )
    c.metering.catalog, c.metering.settings = catalog, settings
    fake = FixtureProvider()

    class MeteredFake:
        async def generate(self, messages, opts):
            result = await fake.generate(messages, opts)
            usage = Usage(
                scope="call",
                usage_source="provider",
                input_tokens=10,
                output_tokens=4,
                cached_input_tokens=0,
                reasoning_tokens=0,
            )
            return ProviderResult(
                text=result.text,
                duration_ms=1,
                execution_source="live",
                usage=usage,
                cost=price(catalog.entry(opts.config_id), usage, catalog.version),
            )

    live_registry = REGISTRY.model_copy(
        update={
            "configurations": tuple(
                m.model_copy(update={"execution_source": "live"}) for m in REGISTRY.configurations
            )
        }
    )
    await c.research.close()
    from app.contracts.dtos import Message, ProviderOptions

    with pytest.raises(AppError) as invalid:
        await c.metering.generate(
            MeteringContext(operation_id="not-created", principal=admin, max_total_usd=Decimal(1)),
            (Message(role="user", content="test"),),
            ProviderOptions(
                request_id="not-created",
                call_id="not-dispatched",
                config_id="fixture-reference",
                model_id="fixture-reference-v1",
                temperature=0.2,
            ),
            MeteredFake(),
        )
    assert invalid.value.code == "VALIDATION_ERROR"
    c.research = ResearchService(
        c.db, LiveResearchWiring(settings, c.metering, MeteredFake(), c.sessions, live_registry)
    )
    await c.research.start()
    assert (await client.get("/v1/research/configs")).json()["live_enabled"] is True
    created = await client.post(
        "/v1/research/runs",
        json={
            "client_request_id": "live-fake",
            "execution_source": "live",
            "policies": ["fixed_reference"],
        },
    )
    assert created.status_code == 201, created.text
    result = await wait_run(client, created.json()["id"])
    assert result["status"] == "succeeded", result
    assert result["execution_source"] == "live" and result["run_purpose"] == "live_pilot"
    assert (await client.get("/v1/overview")).json()["total_requests"] == 0
    rows = await c.research.trials(admin, result["id"], 0, 100)
    assert all(r.simulation is None for r in rows)
    assert any(r.calls and r.calls[0].usage.input_tokens == 10 for r in rows)
    report = await c.analytics.report(admin, None, None, source="live")
    assert report.totals.known_subtotal_usd > 0
    assert report.reserved_usd > 0  # intentional timeout is unresolved, not free
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Conversation)) == 0
        assert all(
            r.category == "evaluation" and r.session_id is None
            for r in await db.scalars(select(UsageRecord))
        )
    # Crash after settlement but before committing a trial must not hide its paid call.
    first = next(row for row in rows if row.calls)
    async with c.db.write() as db:
        await db.execute(delete(ResearchTrial).where(ResearchTrial.id == first.id))
        interrupted = await db.get(ResearchRun, result["id"])
        interrupted.status = "interrupted"
    recovered = await c.research.get(admin, result["id"])
    assert recovered.accounting and len(recovered.accounting.uncommitted_calls) == 1
    exported = [
        json.loads(line)
        for line in (await client.get(f"/v1/research/runs/{result['id']}/export")).text.splitlines()
    ]
    assert (
        exported[0]["run"]["accounting"]["uncommitted_calls"][0]["call"]["usage"]["input_tokens"]
        == 10
    )
    assert (
        "uncommitted_call"
        in (await client.get(f"/v1/research/runs/{result['id']}/export?format=csv")).text
    )
