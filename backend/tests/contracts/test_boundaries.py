import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    FeatureFlags,
    MemoryPlan,
    Message,
    SessionSnapshot,
)
from app.memory.memory_manager import NoOpMemoryManager
from app.optimizers.context_manager import PassThroughContext
from app.optimizers.preservation import check_preservation


async def test_noops_keep_immutable_snapshot_and_roles() -> None:
    raw = (
        Message(role="user", content="earlier", id="one"),
        Message(role="assistant", content="answer", id="two"),
    )
    snapshot = SessionSnapshot(
        owner_user_id="a",
        session_id="s",
        revision=1,
        raw_turns=raw,
        server_instructions=(Message(role="system", content="trusted"),),
    )
    result = await NoOpMemoryManager().prepare(snapshot, MemoryPlan(enabled=True))
    assert result.snapshot is snapshot
    features = ContextFeatures(
        current_turn=Message(role="user", content="current"), flags=FeatureFlags()
    )
    prepared = PassThroughContext().prepare(result.snapshot, ContextBudgets(), features)
    assert [m.content for m in prepared.messages] == ["trusted", "earlier", "answer", "current"]
    assert [m.role for m in prepared.messages] == ["system", "user", "assistant", "user"]
    with pytest.raises(ValidationError):
        snapshot.raw_turns[0].content = "mutated"
    assert check_preservation("không ít hơn 10", "không nhiều hơn 10") == "unknown"


def test_algorithm_import_boundaries() -> None:
    root = Path(__file__).resolve().parents[2] / "app"
    for area in ("optimizers", "memory", "routing"):
        for source in (root / area).glob("*.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [n.name for n in node.names]
                    if isinstance(node, ast.Import)
                    else []
                )
                assert not any(
                    name.startswith(("app.storage", "app.api", "openai", "sqlalchemy"))
                    for name in names
                ), source
