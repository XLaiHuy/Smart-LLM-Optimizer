"""Deterministic memory retrieval for context optimization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter

from app.contracts.dtos import Message, SessionSnapshot
from app.optimizers.context_selection import count_messages_tokens, hybrid_score


@dataclass(frozen=True)
class MemoryCandidate:
    kind: str
    key: str
    content: str
    source_message_ids: tuple[str, ...]
    importance: float
    score: float = 0.0


@dataclass(frozen=True)
class MemoryRetrievalResult:
    messages: tuple[Message, ...]
    selected: tuple[MemoryCandidate, ...]
    candidates: tuple[MemoryCandidate, ...]
    latency_ms: float
    token_savings: int

    @property
    def selected_source_ids(self) -> tuple[str, ...]:
        return tuple(
            source_id
            for item in self.selected
            for source_id in item.source_message_ids
        )


def recall_at_k(result: MemoryRetrievalResult, relevant_source_ids: set[str]) -> float:
    """Return source-level Recall@K for a retrieval result."""

    if not relevant_source_ids:
        return 1.0
    selected = set(result.selected_source_ids)
    return len(selected & relevant_source_ids) / len(relevant_source_ids)


class MemoryRetriever:
    """Rank persisted facts and summaries and fit them into a token budget."""

    def __init__(self, *, alpha: float = 0.7, importance_weight: float = 0.2) -> None:
        if not 0 <= alpha <= 1:
            raise ValueError("alpha must be between 0 and 1")
        if not 0 <= importance_weight <= 1:
            raise ValueError("importance_weight must be between 0 and 1")
        self.alpha = alpha
        self.importance_weight = importance_weight

    def retrieve(
        self,
        snapshot: SessionSnapshot,
        query: str,
        token_budget: int,
        *,
        top_k: int | None = None,
    ) -> MemoryRetrievalResult:
        if token_budget < 0:
            raise ValueError("token_budget must be non-negative")
        started = perf_counter()
        candidates = self._candidates(snapshot)
        indexed = {message.id: index for index, message in enumerate(snapshot.raw_turns)}
        total = max(1, len(snapshot.raw_turns))
        ranked = tuple(
            sorted(
                (
                    replace(item, score=self._score(query, item, indexed, total))
                    for item in candidates
                ),
                key=lambda item: (item.score, item.importance, item.key),
                reverse=True,
            )
        )
        if top_k is not None:
            if top_k < 0:
                raise ValueError("top_k must be non-negative")
            ranked = ranked[:top_k]

        selected: list[MemoryCandidate] = []
        used = 0
        for item in ranked:
            message = self._message(item)
            item_tokens = count_messages_tokens((message,))
            if used + item_tokens > token_budget:
                continue
            selected.append(item)
            used += item_tokens

        all_tokens = sum(
            count_messages_tokens((self._message(item),)) for item in candidates
        )
        messages = tuple(self._message(item) for item in selected)
        return MemoryRetrievalResult(
            messages=messages,
            selected=tuple(selected),
            candidates=candidates,
            latency_ms=(perf_counter() - started) * 1000,
            token_savings=max(0, all_tokens - used),
        )

    def retrieve_snapshots(
        self,
        snapshots: tuple[SessionSnapshot, ...],
        query: str,
        token_budget: int,
        *,
        top_k: int | None = None,
    ) -> MemoryRetrievalResult:
        """Retrieve and rank memory across multiple owned sessions."""

        candidates: list[MemoryCandidate] = []
        for snapshot in snapshots:
            prefix = snapshot.session_id if len(snapshots) > 1 else ""
            candidates.extend(self._candidates(snapshot, prefix=prefix))
        return self._retrieve_candidates(tuple(candidates), query, token_budget, top_k=top_k)

    def _retrieve_candidates(
        self,
        candidates: tuple[MemoryCandidate, ...],
        query: str,
        token_budget: int,
        *,
        top_k: int | None = None,
    ) -> MemoryRetrievalResult:
        started = perf_counter()
        total = max(1, len(candidates))
        ranked = tuple(
            sorted(
                (
                    replace(
                        item,
                        score=(1 - self.importance_weight)
                        * hybrid_score(query, item.content, index, total, self.alpha)
                        + self.importance_weight * item.importance,
                    )
                    for index, item in enumerate(candidates)
                ),
                key=lambda item: (item.score, item.importance, item.key),
                reverse=True,
            )
        )
        if top_k is not None:
            ranked = ranked[:top_k]
        selected: list[MemoryCandidate] = []
        used = 0
        for item in ranked:
            item_tokens = count_messages_tokens((self._message(item),))
            if used + item_tokens <= token_budget:
                selected.append(item)
                used += item_tokens
        all_tokens = sum(count_messages_tokens((self._message(item),)) for item in candidates)
        return MemoryRetrievalResult(
            messages=tuple(self._message(item) for item in selected),
            selected=tuple(selected),
            candidates=candidates,
            latency_ms=(perf_counter() - started) * 1000,
            token_savings=max(0, all_tokens - used),
        )

    def _score(
        self,
        query: str,
        item: MemoryCandidate,
        indexes: dict[str | None, int],
        total: int,
    ) -> float:
        latest_index = max((indexes.get(source_id, 0) for source_id in item.source_message_ids), default=0)
        hybrid = hybrid_score(query, item.content, latest_index, total, self.alpha)
        return (1 - self.importance_weight) * hybrid + self.importance_weight * item.importance

    @staticmethod
    def _candidates(
        snapshot: SessionSnapshot, *, prefix: str = ""
    ) -> tuple[MemoryCandidate, ...]:
        facts = tuple(
            MemoryCandidate(
                kind="fact",
                key=f"{prefix}:{fact.key}" if prefix else fact.key,
                content=f"{fact.key}: {fact.value}",
                source_message_ids=fact.source_message_ids,
                importance=1.0,
            )
            for fact in snapshot.facts
        )
        summaries = tuple(
            MemoryCandidate(
                kind="summary",
                key=(f"{prefix}:summary:{summary.revision}" if prefix else f"summary:{summary.revision}"),
                content=summary.content,
                source_message_ids=summary.covered_message_ids,
                importance=0.8,
            )
            for summary in snapshot.summaries
        )
        return facts + summaries

    @staticmethod
    def _message(item: MemoryCandidate) -> Message:
        return Message(
            role="system",
            id=f"memory:{item.kind}:{item.key}",
            content=f"[Retrieved memory]\n{item.content}",
        )
