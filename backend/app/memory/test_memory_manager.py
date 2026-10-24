from types import SimpleNamespace

from app.contracts.dtos import DerivedMemory, MemoryPlan, Message, SessionSnapshot
from app.memory.memory_manager import RetrievalMemoryManager


class FakeStore:
    def __init__(self) -> None:
        self.state = DerivedMemory(snapshot_revision=0)
        self.saved: DerivedMemory | None = None

    async def load(self, principal: object, session_id: str) -> DerivedMemory:
        del principal, session_id
        return self.state

    async def save(self, principal: object, session_id: str, state: DerivedMemory) -> None:
        del principal, session_id
        self.saved = state

    async def load_user_memories(
        self, execution_principal: str, exclude_session_id: str
    ) -> tuple[SessionSnapshot, ...]:
        del execution_principal, exclude_session_id
        return ()


async def test_update_persists_explicit_fact_after_commit() -> None:
    store = FakeStore()
    manager = RetrievalMemoryManager(store=store)
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=2,
        raw_turns=(
            Message(
                role="user",
                id="message-1",
                request_id="request-1",
                content="My name is An.",
            ),
        ),
    )

    await manager.update(
        SimpleNamespace(request_id="request-1", principal=object()),  # type: ignore[arg-type]
        snapshot,
    )

    assert store.saved is not None
    assert store.saved.snapshot_revision == 2
    assert store.saved.facts[0].key == "name"
    assert store.saved.facts[0].source_message_ids == ("message-1",)


async def test_prepare_uses_cross_session_store() -> None:
    store = FakeStore()
    manager = RetrievalMemoryManager(store=store)
    result = await manager.prepare(
        SessionSnapshot(owner_user_id="u1", session_id="s1", revision=1),
        MemoryPlan(enabled=True, query="deadline", token_budget=100),
    )

    assert result.memory_messages == ()
