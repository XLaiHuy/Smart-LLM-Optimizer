from app.contracts.dtos import (
    DerivedMemory,
    ExecutionRequest,
    MemoryPlan,
    MemoryResult,
    SessionSnapshot,
)
from app.contracts.protocols import MemoryStore
from app.core.policy import noop_state
from app.memory.extractor import extract_explicit_facts
from app.memory.retrieval import MemoryRetriever


class NoOpMemoryManager:
    async def prepare(self, snapshot: SessionSnapshot, plan: MemoryPlan) -> MemoryResult:
        return MemoryResult(snapshot=snapshot, state=noop_state("memory", plan.enabled))

    async def update(self, execution: ExecutionRequest, snapshot: SessionSnapshot) -> None:
        del execution, snapshot


class RetrievalMemoryManager:
    """Retrieve persisted memory for the current request."""

    def __init__(
        self,
        retriever: MemoryRetriever | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.retriever = retriever or MemoryRetriever()
        self.store = store

    async def prepare(self, snapshot: SessionSnapshot, plan: MemoryPlan) -> MemoryResult:
        if not plan.enabled or not plan.query or plan.token_budget == 0:
            return MemoryResult(snapshot=snapshot, state=noop_state("memory", plan.enabled))

        snapshots: tuple[SessionSnapshot, ...] = (snapshot,)
        if self.store is not None:
            snapshots += await self.store.load_user_memories(
                execution_principal=snapshot.owner_user_id,
                exclude_session_id=snapshot.session_id,
            )
        result = self.retriever.retrieve_snapshots(
            snapshots, plan.query, plan.token_budget, top_k=plan.top_k
        )
        return MemoryResult(
            snapshot=snapshot,
            memory_messages=result.messages,
            state=noop_state("memory", True).model_copy(
                update={
                    "status": "applied" if result.selected else "skipped",
                    "reason": "memory_retrieval" if result.selected else "no_relevant_memory",
                }
            ),
        )

    async def update(self, execution: ExecutionRequest, snapshot: SessionSnapshot) -> None:
        if self.store is None:
            return
        user_message = next(
            (
                message
                for message in reversed(snapshot.raw_turns)
                if message.role == "user" and message.request_id == execution.request_id
            ),
            None,
        )
        if user_message is None or user_message.id is None:
            return
        facts = extract_explicit_facts(user_message.content, user_message.id)
        if not facts:
            return
        current = await self.store.load(execution.principal, snapshot.session_id)
        by_key = {fact.key: fact for fact in current.facts}
        by_key.update({fact.key: fact for fact in facts})
        await self.store.save(
            execution.principal,
            snapshot.session_id,
            DerivedMemory(
                snapshot_revision=snapshot.revision,
                summaries=current.summaries,
                facts=tuple(by_key.values()),
            ),
        )
