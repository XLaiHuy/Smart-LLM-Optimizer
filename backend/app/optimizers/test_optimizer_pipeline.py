from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.contracts.dtos import ContextFeatures, FeatureFlags, Message, SessionSnapshot, Summary
from app.optimizers.context_benchmark import BenchmarkStrategy, ContextBenchmark
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer


@pytest.mark.asyncio
async def test_prompt_and_context_optimization_pipeline() -> None:
    prompt = "Explain AI.   \n\n\nKeep the deadline 2026-10-23."
    snapshot = SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=1,
        raw_turns=(Message(role="user", id="m1", content="Keep the deadline 2026-10-23."),),
    )
    features = ContextFeatures(
        current_turn=Message(role="user", id="current", content=prompt),
        flags=FeatureFlags(context=True, rewrite=True),
    )

    rewrite = await AdaptivePromptOptimizer(min_compress_tokens=1).optimize(
        SimpleNamespace(request=SimpleNamespace(message=prompt)),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        features.flags,
    )

    async def generate(messages: tuple[Message, ...], revision: int) -> Summary:
        return Summary(
            revision=revision,
            content="The deadline is 2026-10-23.",
            covered_message_ids=tuple(message.id for message in messages if message.id),
        )

    benchmark = ContextBenchmark(
        100,
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("1"),
    )
    result = await benchmark.run(BenchmarkStrategy.HYBRID_SUMMARY, snapshot, features, generate)

    assert rewrite.proposed == "Explain AI.\n\nKeep the deadline 2026-10-23."
    assert result.context_tokens > 0
    assert result.total_tokens >= result.context_tokens
