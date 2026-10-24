from decimal import Decimal

import pytest

from app.contracts.dtos import (
    ContextFeatures,
    Fact,
    FeatureFlags,
    Message,
    SessionSnapshot,
    Summary,
)
from app.optimizers.context_benchmark import BenchmarkStrategy, ContextBenchmark


def _snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        owner_user_id="u1",
        session_id="s1",
        revision=2,
        raw_turns=(
            Message(role="user", id="m1", content="The deadline is 2026-10-23."),
            Message(role="assistant", id="m2", content="I will keep the deadline."),
        ),
        facts=(Fact(key="deadline", value="2026-10-23", source_message_ids=("m1",)),),
    )


def _features() -> ContextFeatures:
    return ContextFeatures(
        current_turn=Message(role="user", id="current", content="What is the deadline?"),
        flags=FeatureFlags(context=True),
    )


async def _summary(messages: tuple[Message, ...], revision: int) -> Summary:
    return Summary(
        revision=revision,
        content="The deadline is 2026-10-23.",
        covered_message_ids=tuple(message.id for message in messages if message.id),
    )


@pytest.mark.asyncio
async def test_all_four_configurations_are_measurable() -> None:
    benchmark = ContextBenchmark(
        token_budget=100,
        input_price_per_million=Decimal("1"),
        output_price_per_million=Decimal("2"),
    )
    results = [
        await benchmark.run(strategy, _snapshot(), _features(), _summary)
        for strategy in BenchmarkStrategy
    ]

    assert {result.strategy for result in results} == set(BenchmarkStrategy)
    assert all(result.context_tokens > 0 for result in results)
    assert all(result.total_tokens >= result.context_tokens for result in results)
    assert results[2].summary_input_tokens > 0
    assert results[2].summary_output_tokens > 0
    assert results[2].factual_consistency.status == "preserved"
    assert results[2].estimated_cost_usd > 0


@pytest.mark.asyncio
async def test_missing_fact_is_reported_as_violation() -> None:
    async def incomplete(messages: tuple[Message, ...], revision: int) -> Summary:
        return Summary(
            revision=revision,
            content="The task is in progress.",
            covered_message_ids=tuple(message.id for message in messages if message.id),
        )

    result = await ContextBenchmark(100).run(
        BenchmarkStrategy.SUMMARY_ONLY, _snapshot(), _features(), incomplete
    )

    assert result.factual_consistency.status == "violation"
    assert result.factual_consistency.missing_fact_keys == ("deadline",)
