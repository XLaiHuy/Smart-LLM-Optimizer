"""Real collector/ledger path, fake providers only; never paid network."""

import asyncio
import hashlib
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.contracts.dtos import (
    CostSnapshot,
    Message,
    ModelConfiguration,
    ProviderResult,
    RouteRate,
    Usage,
)
from app.contracts.errors import AppError
from app.contracts.training import TrainingJob, TrainingManifest, TrainingRequest, TrainingSource
from app.routing.ml.family_campaign import FamilyCollection, _CallLane, _DispatchGate
from app.storage.models import Attempt, Reservation
from app.storage.repositories import now, uid


@pytest.mark.parametrize("failure", [False, True])
async def test_two_lanes_preserve_billing_cache_and_stop_after_unknown(
    app, tmp_path, monkeypatch, failure
):
    container = app.state.container
    user = await container.auth.create_user("parallel-admin", "test-password", "admin")
    active = peak = 0
    started, finished = [], []
    both_started = asyncio.Event()

    class Provider:
        async def generate(self, messages, opts):
            nonlocal active, peak
            started.append(opts.config_id)
            active += 1
            peak = max(peak, active)
            if active == 2:
                both_started.set()
            try:
                await asyncio.wait_for(both_started.wait(), timeout=5)
                await asyncio.sleep(0.02 if opts.config_id == "a" else 0.06)
                if failure and opts.config_id == "a":
                    raise TimeoutError("fixture unknown dispatch")
                finished.append(opts.config_id)
                return ProviderResult(
                    text="42",
                    execution_source="live",
                    duration_ms=20,
                    usage=Usage(
                        scope="call", usage_source="provider", input_tokens=10, output_tokens=2
                    ),
                )
            finally:
                active -= 1

    pipeline = FamilyCollection(
        SimpleNamespace(
            settings=container.settings, db=container.db, ledger=container.ledger, live=Provider()
        )
    )
    monkeypatch.setattr(_CallLane, "live_allowed", lambda self, m: True)
    source = tmp_path / "source.json"
    source.write_bytes(b"{}")
    configs = tuple(
        ModelConfiguration(
            config_id=k,
            model_id=k,
            endpoint="chat_completions",
            context_window=10000,
            max_output_tokens=128,
        )
        for k in ("a", "b", "c")
    )
    manifest = TrainingManifest(
        version="task-family-v1-20261027",
        reviewed_by="test",
        pricing_source="test",
        software_test=True,
        pilot=True,
        min_interval_seconds=0,
        source=TrainingSource(
            local_path=str(source),
            sha256=hashlib.sha256(b"{}").hexdigest(),
            license="fixture",
            provenance="fixture only",
        ),
        configurations=configs,
        reference_config_id="c",
        costs=CostSnapshot(
            version="test",
            rates=tuple(
                RouteRate(config_id=k, input_per_million="1", output_per_million="1")
                for k in ("a", "b", "c")
            ),
        ),
    )
    job = TrainingJob(
        id=uid(),
        request=TrainingRequest(
            client_request_id="parallel-fixture", mode="live", budget_usd=Decimal(".01")
        ),
        active_phase="collect",
    )
    async with container.db.write() as db:
        db.add(
            Attempt(
                id=job.id,
                owner_user_id=user.id,
                session_id=None,
                client_request_id="router-training:parallel-fixture",
                payload_hash="fixture",
                status="running",
                created_at=now(),
                execution_source="live",
                response_json=job.model_dump_json(),
            )
        )
    messages = (Message(role="user", content="What is 6 * 7?"),)
    if failure:
        with pytest.raises(TimeoutError):
            await pipeline._collect_answers(user, job, manifest, configs, messages)
        saved = await pipeline.get(user, job.id)
        assert started == ["a", "b"]
        assert finished == ["b"]  # peer drained and billed, never cancelled
        assert saved.api_calls == 2 and saved.unknown_cost_calls == 1
        assert saved.spent_usd == Decimal(".000012")
        async with container.db.sessions() as db:
            reservations = list(
                await db.scalars(select(Reservation).where(Reservation.request_id == job.id))
            )
        assert sorted(r.status for r in reservations) == ["settled", "unresolved"]
    else:
        answers, saved = await pipeline._collect_answers(user, job, manifest, configs, messages)
        assert set(answers) == {"a", "b", "c"}
        assert saved.api_calls == 3 and saved.spent_usd == Decimal(".000036")
        _, replay = await pipeline._collect_answers(user, saved, manifest, configs, messages)
        assert len(started) == 3 and replay.cache_hits == 3  # no duplicate dispatch
        assert replay.api_calls == 3 and replay.spent_usd == saved.spent_usd
    assert peak == 2 and active == 0


async def test_waiting_gate_does_not_dispatch_after_failure():
    calls = []

    class Provider:
        async def generate(self):
            calls.append(1)
            raise TimeoutError("fixture")

    gate = _DispatchGate(Provider())
    gate.interval = 0.03
    results = await asyncio.gather(gate.generate(), gate.generate(), return_exceptions=True)
    assert len(calls) == 1
    assert isinstance(results[0], TimeoutError)
    assert isinstance(results[1], AppError)
    assert results[1].dispatch_state == "not_dispatched"
