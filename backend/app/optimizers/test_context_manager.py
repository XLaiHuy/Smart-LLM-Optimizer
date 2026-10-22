import pytest

from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    FeatureFlags,
    Message,
    SessionSnapshot,
)
from app.optimizers.context_manager import HybridContextManager
from app.optimizers.context_selection import count_messages_tokens


def test_current_user_is_kept_once() -> None:
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=1,
        raw_turns=(
            Message(role="user", content="old question"),
            Message(role="assistant", content="old answer"),
        ),
        server_instructions=(Message(role="system", content="Answer safely"),),
    )

    features = ContextFeatures(
        current_turn=Message(
            role="user",
            content="current question",
        ),
        flags=FeatureFlags(context=True),
    )

    result = HybridContextManager(token_budget=100).prepare(
        snapshot,
        ContextBudgets(),
        features,
    )

    current_messages = [
        message for message in result.messages if message.content == "current question"
    ]

    assert len(current_messages) == 1


def test_mandatory_context_overflow() -> None:
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=1,
        server_instructions=(Message(role="system", content="Important system instruction"),),
    )

    features = ContextFeatures(
        current_turn=Message(
            role="user",
            content="Current question",
        ),
        flags=FeatureFlags(context=True),
    )

    with pytest.raises(ValueError, match="context_overflow"):
        HybridContextManager(token_budget=1).prepare(
            snapshot,
            ContextBudgets(),
            features,
        )


def test_recent_turn_overflow_does_not_fail() -> None:
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=1,
        raw_turns=(
            Message(role="user", content="old question"),
            Message(role="assistant", content="old answer"),
            Message(role="user", content="recent question"),
            Message(role="assistant", content="recent answer"),
        ),
    )

    features = ContextFeatures(
        current_turn=Message(
            role="user",
            content="Current question",
        ),
        flags=FeatureFlags(context=True),
    )

    mandatory = (features.current_turn,)

    recent_turn = (
        snapshot.raw_turns[2],
        snapshot.raw_turns[3],
    )

    budget = count_messages_tokens(
        (
            *mandatory,
            *recent_turn,
        )
    )

    result = HybridContextManager(token_budget=budget).prepare(
        snapshot,
        ContextBudgets(),
        features,
    )

    assert result.messages[-1].content == "Current question"
