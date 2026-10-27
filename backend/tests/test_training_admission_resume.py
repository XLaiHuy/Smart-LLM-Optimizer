"""Resumption fences and frozen splits, with fake dispatch and a temporary DB."""

import hashlib
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.contracts.dtos import CostSnapshot, Message, ModelConfiguration, RouteRate
from app.contracts.errors import AppError
from app.contracts.training import (
    GradingSpec,
    RawTrainingSample,
    TrainingCorpus,
    TrainingJob,
    TrainingManifest,
    TrainingRequest,
    TrainingSource,
)
from app.routing.ml.pilot import prepare_samples
from app.routing.ml.pipeline import cache_key
from app.storage.models import Attempt, Reservation
from app.storage.repositories import now, uid


def manifest(source):
    models = tuple(
        ModelConfiguration(
            config_id=key,
            model_id=key,
            context_window=16000,
            max_output_tokens=128,
        )
        for key in ("reference", "small", "medium")
    )
    return TrainingManifest(
        version="functional-resume-test",
        reviewed_by="test-only",
        pricing_source="fake",
        software_test=True,
        source=source,
        configurations=models,
        reference_config_id="reference",
        costs=CostSnapshot(
            version="fake",
            rates=tuple(
                RouteRate(
                    config_id=key,
                    input_per_million=".1",
                    output_per_million=".2",
                )
                for key in ("reference", "small", "medium")
            ),
        ),
        pilot=True,
        min_interval_seconds=0,
        max_samples=16,
        split_protocol="frozen_canonical",
    )


def source_file(tmp_path, corpus=None):
    path = tmp_path / "source.json"
    path.write_text(corpus.model_dump_json() if corpus else "{}", encoding="utf-8")
    return TrainingSource(
        local_path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        license="functional fixture",
        provenance="generated for offline software tests only",
        license_url="https://example.com/test-only",
        license_reviewed=True,
        allow_training=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dispatch_state", ["not_dispatched", "rejected", "unknown"])
async def test_only_known_rejection_allows_repeated_dispatch(
    app, tmp_path, monkeypatch, dispatch_state
):
    c = app.state.container
    user = await c.auth.create_user("eval-admin", "test-password-123", role="admin")
    request = TrainingRequest(
        client_request_id="resume-test", mode="live", budget_usd=Decimal(".05")
    )
    job = TrainingJob(id=uid(), request=request)
    async with c.db.write() as db:
        db.add(
            Attempt(
                id=job.id,
                owner_user_id=user.id,
                session_id=None,
                client_request_id="router-training:resume-test",
                payload_hash="test",
                status="running",
                execution_source="mock",
                created_at=now(),
                response_json=job.model_dump_json(),
            )
        )

    class FakeProvider:
        calls = 0

        async def generate(self, messages, opts):
            self.calls += 1
            raise AppError("TEST_FAILURE", 503, "fake", dispatch_state=dispatch_state)

    fake = FakeProvider()
    pipeline = c.training
    pipeline.provider = fake
    # Only the dispatch-fence behavior is under test. No live wiring/key is created.
    monkeypatch.setattr(pipeline, "live_allowed", lambda _: True)
    plan = manifest(source_file(tmp_path))
    messages = (Message(role="user", content="Offline test prompt"),)
    marker = (
        pipeline.settings.router_training_directory
        / "cache"
        / (cache_key(plan, "small", messages) + ".dispatch.json")
    )
    with pytest.raises(AppError, match="fake"):
        await pipeline._generation(user, job, plan, "small", messages)
    assert marker.exists() == (dispatch_state == "unknown")
    with pytest.raises(AppError) as error:
        await pipeline._generation(user, job, plan, "small", messages)
    assert error.value.code == (
        "DISPATCH_REVIEW_REQUIRED" if dispatch_state == "unknown" else "TEST_FAILURE"
    )
    assert fake.calls == (1 if dispatch_state == "unknown" else 2)
    async with c.db.sessions() as db:
        reservations = list(
            await db.scalars(select(Reservation).where(Reservation.request_id == job.id))
        )
    assert {r.status for r in reservations} == (
        {"unresolved"} if dispatch_state == "unknown" else {"settled"}
    )
    if dispatch_state != "unknown":
        assert all(Decimal(r.settled_usd) == 0 for r in reservations)


@pytest.mark.asyncio
async def test_canonical_splits_stay_frozen_and_cross_split_source_is_rejected(tmp_path):
    rows = tuple(
        RawTrainingSample(
            task_id=str(i),
            group_id=f"source-{i}",
            domain="functional",
            split=split,
            messages=(Message(role="user", content=f"Functional source question {i}"),),
            gold="1",
            grading=GradingSpec(kind="numeric"),
        )
        for i, split in enumerate(
            ["train"] * 4 + ["calibration"] * 4 + ["threshold"] * 4 + ["holdout"] * 4
        )
    )
    corpus = TrainingCorpus(samples=rows)
    prepared = await prepare_samples(manifest(source_file(tmp_path, corpus)))
    assert {r.group_id: r.split for r in prepared.samples} == {r.group_id: r.split for r in rows}
    bad_rows = list(rows)
    bad_rows[-1] = bad_rows[-1].model_copy(update={"group_id": rows[0].group_id})
    with pytest.raises(AppError) as error:
        await prepare_samples(
            manifest(source_file(tmp_path, TrainingCorpus(samples=tuple(bad_rows))))
        )
    assert error.value.code == "SOURCE_SPLIT_LEAKAGE"
