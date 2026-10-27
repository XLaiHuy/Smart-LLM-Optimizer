from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    Fact,
    FeatureFlags,
    Message,
    SessionSnapshot,
    Summary,
)
from app.memory.retrieval import MemoryRetriever
from app.optimizers.context_optimizer import ContextOptimizer
from app.optimizers.context_summarizer import ContextSummarizer


async def test_context_optimizer_adds_validated_summary_for_omitted_history() -> None:
    raw_turns = (
        Message(role="user", id="u1", content="old project constraint " * 5),
        Message(role="assistant", id="a1", content="old answer " * 5),
        Message(role="user", id="u2", content="recent project question " * 5),
        Message(role="assistant", id="a2", content="recent answer " * 5),
    )
    snapshot = SessionSnapshot(
        owner_user_id="user-1",
        session_id="session-1",
        revision=4,
        raw_turns=raw_turns,
    )

    async def generate(messages: tuple[Message, ...], revision: int) -> Summary:
        return Summary(
            revision=revision,
            content="Old constraint: use the approved project scope.",
            covered_message_ids=tuple(message.id for message in messages if message.id),
        )

    result = await ContextOptimizer(
        token_budget=55,
        summarizer=ContextSummarizer(generate),
    ).optimize(
        snapshot,
        ContextBudgets(),
        ContextFeatures(
            current_turn=Message(role="user", content="current question"),
            flags=FeatureFlags(context=True),
        ),
    )

    assert any(message.id == "summary:4" for message in result.messages)
    assert any(item.startswith("summary:4:") for item in result.provenance)


async def test_context_optimizer_integrates_ranked_memory() -> None:
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=4,
        raw_turns=(Message(role="user", id="m1", content="The deadline is Friday."),),
        facts=(Fact(key="deadline", value="Friday", source_message_ids=("m1",)),),
    )
    features = ContextFeatures(
        current_turn=Message(role="user", content="When is the deadline?"),
        flags=FeatureFlags(context=True, memory=True),
    )

    result = await ContextOptimizer(
        token_budget=100,
        memory_retriever=MemoryRetriever(),
    ).optimize(snapshot, ContextBudgets(), features)

    assert any(message.id == "memory:fact:deadline" for message in result.messages)
