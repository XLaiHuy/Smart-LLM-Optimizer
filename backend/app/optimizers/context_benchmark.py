"""Benchmark the four context strategies without making provider calls.

The benchmark is intentionally explicit about summary overhead.  A summary is
not free: its input/output tokens and wall-clock time are included in the
result instead of being hidden behind the final request measurement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    Fact,
    Message,
    SessionSnapshot,
    Summary,
)
from app.optimizers.context_manager import HybridContextManager
from app.optimizers.context_optimizer import ContextOptimizer
from app.optimizers.context_selection import count_messages_tokens
from app.optimizers.context_summarizer import ContextSummarizer, SummaryValidator


class BenchmarkStrategy(StrEnum):
    FULL_HISTORY = "full_history"
    HYBRID_ONLY = "hybrid_only"
    SUMMARY_ONLY = "summary_only"
    HYBRID_SUMMARY = "hybrid_summary"


class BenchmarkSummaryGenerator(Protocol):
    async def __call__(self, messages: tuple[Message, ...], revision: int) -> Summary | None: ...


@dataclass(frozen=True)
class FactualConsistency:
    status: str
    checked_facts: int
    preserved_facts: int
    missing_fact_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextBenchmarkResult:
    strategy: BenchmarkStrategy
    context_tokens: int
    source_tokens: int
    summary_input_tokens: int
    summary_output_tokens: int
    total_tokens: int
    summary_latency_ms: float
    estimated_cost_usd: Decimal
    factual_consistency: FactualConsistency
    selected_message_ids: tuple[str, ...]


def evaluate_factual_consistency(
    summary: Summary | None,
    facts: tuple[Fact, ...],
) -> FactualConsistency:
    """Conservatively check facts; absence of a summary is ``unknown``.

    This is a deterministic smoke metric, not an entailment judge.  A fact is
    counted as preserved only when its value occurs in the summary text.  A
    production semantic judge can be added later without changing the result
    contract.
    """

    if summary is None:
        return FactualConsistency("unknown", 0, 0)
    normalized = summary.content.casefold()
    missing = tuple(fact.key for fact in facts if fact.value.casefold() not in normalized)
    preserved = len(facts) - len(missing)
    return FactualConsistency(
        "preserved" if not missing else "violation",
        len(facts),
        preserved,
        missing,
    )


class ContextBenchmark:
    """Run comparable, provider-independent context benchmarks."""

    def __init__(
        self,
        token_budget: int,
        *,
        input_price_per_million: Decimal = Decimal("0"),
        output_price_per_million: Decimal = Decimal("0"),
    ) -> None:
        self.token_budget = token_budget
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million

    async def run(
        self,
        strategy: BenchmarkStrategy,
        snapshot: SessionSnapshot,
        features: ContextFeatures,
        generator: BenchmarkSummaryGenerator | None = None,
    ) -> ContextBenchmarkResult:
        source_messages = tuple(snapshot.raw_turns)
        source_tokens = count_messages_tokens(source_messages)
        summary: Summary | None = None
        summary_input_tokens = 0
        summary_output_tokens = 0
        summary_latency_ms = 0.0

        if strategy is BenchmarkStrategy.FULL_HISTORY:
            messages = self._full_history(snapshot, features.current_turn)
        elif strategy is BenchmarkStrategy.HYBRID_ONLY:
            messages = HybridContextManager(self.token_budget).prepare(
                snapshot, ContextBudgets(), features
            ).messages
        elif strategy is BenchmarkStrategy.SUMMARY_ONLY:
            summary, summary_input_tokens, summary_output_tokens, summary_latency_ms = (
                await self._make_summary(generator, source_messages, snapshot)
            )
            messages = self._summary_context(snapshot, features.current_turn, summary)
        else:
            summarizer = ContextSummarizer(generator)
            started = time.perf_counter()
            selected = await ContextOptimizer(
                self.token_budget, summarizer=summarizer
            ).optimize(snapshot, ContextBudgets(), features)
            summary_latency_ms = (time.perf_counter() - started) * 1000
            messages = selected.messages
            summary = self._summary_from_context(selected, snapshot)
            if summary is not None:
                summary_input_tokens = count_messages_tokens(
                    tuple(
                        message
                        for message in source_messages
                        if message.id in summary.covered_message_ids
                    )
                )
                summary_output_tokens = count_messages_tokens((self._summary_message(summary),))

        context_tokens = count_messages_tokens(messages)
        total_tokens = context_tokens + summary_input_tokens + summary_output_tokens
        cost = (
            Decimal(summary_input_tokens + context_tokens) * self.input_price_per_million
            + Decimal(summary_output_tokens) * self.output_price_per_million
        ) / Decimal(1_000_000)
        consistency = evaluate_factual_consistency(summary, snapshot.facts)
        return ContextBenchmarkResult(
            strategy=strategy,
            context_tokens=context_tokens,
            source_tokens=source_tokens,
            summary_input_tokens=summary_input_tokens,
            summary_output_tokens=summary_output_tokens,
            total_tokens=total_tokens,
            summary_latency_ms=summary_latency_ms,
            estimated_cost_usd=cost,
            factual_consistency=consistency,
            selected_message_ids=tuple(message.id or message.role for message in messages),
        )

    @staticmethod
    def _full_history(snapshot: SessionSnapshot, current: Message) -> tuple[Message, ...]:
        return (*snapshot.server_instructions, *snapshot.raw_turns, current)

    @staticmethod
    def _summary_context(
        snapshot: SessionSnapshot, current: Message, summary: Summary | None
    ) -> tuple[Message, ...]:
        if summary is None:
            return (*snapshot.server_instructions, current)
        summary_message = ContextBenchmark._summary_message(summary)
        return (*snapshot.server_instructions, summary_message, current)

    @staticmethod
    def _summary_message(summary: Summary) -> Message:
        return Message(
            role="assistant",
            id=f"summary:{summary.revision}",
            content=f"[Conversation summary]\n{summary.content}",
        )

    @staticmethod
    def _summary_from_context(context: object, snapshot: SessionSnapshot) -> Summary | None:
        messages = getattr(context, "messages", ())
        for message in messages:
            if message.id == f"summary:{snapshot.revision}":
                provenance = getattr(context, "provenance", ())
                prefix = f"summary:{snapshot.revision}:"
                covered: list[str] = next(
                    (
                        item.removeprefix(prefix).split(",")
                        for item in provenance
                        if item.startswith(prefix)
                    ),
                    [],
                )
                return Summary(
                    revision=snapshot.revision,
                    content=message.content.removeprefix("[Conversation summary]\n"),
                    covered_message_ids=tuple(item for item in covered if item),
                )
        return None

    async def _make_summary(
        self,
        generator: BenchmarkSummaryGenerator | None,
        messages: tuple[Message, ...],
        snapshot: SessionSnapshot,
    ) -> tuple[Summary | None, int, int, float]:
        if generator is None or not messages:
            return None, 0, 0, 0.0
        started = time.perf_counter()
        summary = await generator(messages, snapshot.revision)
        elapsed = (time.perf_counter() - started) * 1000
        if summary is None:
            return None, count_messages_tokens(messages), 0, elapsed
        if not SummaryValidator.validate(summary, messages, snapshot.revision):
            return None, count_messages_tokens(messages), 0, elapsed
        return (
            summary,
            count_messages_tokens(messages),
            count_messages_tokens((self._summary_message(summary),)),
            elapsed,
        )
