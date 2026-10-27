"""Async orchestration for hybrid context selection plus optional summary."""

from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    ContextResult,
    Message,
    SessionSnapshot,
    Summary,
)
from app.memory.retrieval import MemoryRetriever
from app.optimizers.context_manager import HybridContextManager
from app.optimizers.context_selection import count_messages_tokens
from app.optimizers.context_summarizer import ContextSummarizer


class ContextOptimizer:
    """Add validated summaries to the output of the synchronous selector.

    The selector remains the only component that chooses raw messages. This
    wrapper only summarizes messages omitted by that selector and falls back to
    the selected context whenever summary generation or budget validation fails.
    """

    def __init__(
        self,
        token_budget: int,
        summarizer: ContextSummarizer | None = None,
        memory_retriever: MemoryRetriever | None = None,
        summary_reserve_tokens: int = 384,
    ) -> None:
        if summary_reserve_tokens < 0:
            raise ValueError("summary_reserve_tokens must be non-negative")
        self.summarizer = summarizer or ContextSummarizer()
        self.memory_retriever = memory_retriever
        self.token_budget = token_budget
        self.summary_reserve_tokens = summary_reserve_tokens

    async def optimize(
        self,
        snapshot: SessionSnapshot,
        budgets: ContextBudgets,
        features: ContextFeatures,
    ) -> ContextResult:
        if self.memory_retriever is not None and features.flags.memory:
            fixed = (
                *snapshot.server_instructions,
                *features.evidence,
                features.current_turn,
            )
            memory_budget = max(0, self.token_budget - count_messages_tokens(fixed))
            memory = self.memory_retriever.retrieve(
                snapshot,
                features.current_turn.content,
                min(memory_budget, self.token_budget // 3),
            )
            features = features.model_copy(update={"memory": memory.messages})
        reserve = min(self.summary_reserve_tokens, max(0, self.token_budget // 4))
        try:
            selected = HybridContextManager(self.token_budget - reserve).prepare(
                snapshot, budgets, features
            )
        except ValueError:
            # Mandatory system/context content leaves no room to reserve.
            selected = HybridContextManager(self.token_budget).prepare(snapshot, budgets, features)
        if not features.flags.context or selected.state.status != "applied":
            return selected

        selected_object_ids = {id(message) for message in selected.messages}
        omitted = tuple(
            message for message in snapshot.raw_turns if id(message) not in selected_object_ids
        )
        summary = await self.summarizer.summarize(snapshot, omitted)
        if summary is None:
            return selected

        summary_message = self._as_message(summary)
        candidate = self._insert_summary(selected.messages, summary_message)
        if count_messages_tokens(candidate) > self.token_budget:
            return selected

        return selected.model_copy(
            update={
                "messages": candidate,
                "provenance": self._provenance(candidate, summary),
                "summary_needed": False,
                "state": selected.state.model_copy(
                    update={"reason": "hybrid_selection_with_validated_summary"}
                ),
            }
        )

    @staticmethod
    def _as_message(summary: Summary) -> Message:
        return Message(
            role="assistant",
            id=f"summary:{summary.revision}",
            content=f"[Conversation summary]\n{summary.content}",
        )

    @staticmethod
    def _insert_summary(messages: tuple[Message, ...], summary: Message) -> tuple[Message, ...]:
        user_indices = [index for index, message in enumerate(messages) if message.role == "user"]
        current_index = user_indices[-1] if user_indices else len(messages)
        return messages[:current_index] + (summary,) + messages[current_index:]

    @staticmethod
    def _provenance(messages: tuple[Message, ...], summary: Summary) -> tuple[str, ...]:
        source = ",".join(summary.covered_message_ids)
        summary_provenance = f"summary:{summary.revision}:{source}"
        return tuple(
            summary_provenance
            if message.id == f"summary:{summary.revision}"
            else message.id or message.role
            for message in messages
        )
