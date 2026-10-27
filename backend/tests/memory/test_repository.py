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


async def test_cross_session_latest_committed_memories_use_one_scoped_query(app):
    from uuid import uuid4

    from sqlalchemy import event

    from app.storage.models import Conversation, MemoryRevision

    c = app.state.container
    owner, _ = await c.auth.login("alice", "password-alice")
    other, _ = await c.auth.login("bob", "password-bob")
    included = await c.sessions.create(owner, "included")
    excluded = await c.sessions.create(owner, "excluded")
    foreign = await c.sessions.create(other, "foreign")
    async with c.db.write() as db:
        for sid in (included.id, excluded.id, foreign.id):
            session = await db.get(Conversation, sid)
            session.revision = 2
            for revision in (1, 2, 3):
                state = DerivedMemory(
                    snapshot_revision=revision,
                    facts=(
                        Fact(
                            key="name", value=f"version-{revision}", source_message_ids=("fixture",)
                        ),
                    ),
                )
                db.add(
                    MemoryRevision(
                        id=str(uuid4()),
                        session_id=sid,
                        revision=revision,
                        snapshot_json=state.model_dump_json(),
                    )
                )
    statements = []

    def observed(connection, cursor, statement, params, context, many):
        # The application also runs document-job polling in the background.
        # Count only the memory read, not unrelated worker statements.
        if "memory_revisions" in statement:
            statements.append(statement)

    event.listen(c.db.engine.sync_engine, "before_cursor_execute", observed)
    try:
        snapshots = await c.memory_store.load_user_memories(owner.id, excluded.id)
    finally:
        event.remove(c.db.engine.sync_engine, "before_cursor_execute", observed)
    assert len(statements) == 1
    assert len(snapshots) == 1 and snapshots[0].session_id == included.id
    assert snapshots[0].facts[0].value == "version-2"
