from app.contracts.dtos import Fact, Message, SessionSnapshot, Summary
from app.memory.retrieval import MemoryRetriever, recall_at_k


def snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=4,
        raw_turns=(
            Message(role="user", id="m1", content="My project uses Python."),
            Message(role="assistant", id="m2", content="Noted."),
            Message(role="user", id="m3", content="The deadline is Friday."),
        ),
        facts=(
            Fact(key="language", value="Python", source_message_ids=("m1",)),
            Fact(key="deadline", value="Friday", source_message_ids=("m3",)),
        ),
        summaries=(
            Summary(
                revision=3,
                content="The user is building a data project.",
                covered_message_ids=("m1", "m2"),
            ),
        ),
    )


def test_retrieval_ranks_relevant_memory_and_reports_savings() -> None:
    result = MemoryRetriever().retrieve(snapshot(), "When is the deadline?", 100)

    assert result.selected[0].key == "deadline"
    assert result.latency_ms >= 0
    assert result.token_savings >= 0
    assert "m3" in result.selected_source_ids
    assert recall_at_k(result, {"m3"}) == 1.0


def test_retrieval_respects_token_budget() -> None:
    result = MemoryRetriever().retrieve(snapshot(), "Python deadline project", 1)

    assert result.messages == ()


def test_retrieval_can_rank_memory_across_sessions() -> None:
    other = snapshot().model_copy(
        update={
            "session_id": "s2",
            "facts": (Fact(key="timezone", value="UTC+7", source_message_ids=("x1",)),),
        }
    )
    result = MemoryRetriever().retrieve_snapshots(
        (snapshot(), other), "What is the timezone?", 100
    )

    assert any(item.key == "s2:timezone" for item in result.selected)
