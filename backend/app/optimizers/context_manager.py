from app.contracts.dtos import (
    ContextBudgets,
    ContextFeatures,
    ContextResult,
    OptimizationState,
    SessionSnapshot,
)
from app.core.policy import noop_state
from app.optimizers.context_selection import (
    count_messages_tokens,
    group_conversation_turns,
    select_hybrid_turns,
)


class PassThroughContext:
    """Keep the original context when hybrid selection is disabled."""

    def prepare(
        self,
        snapshot: SessionSnapshot,
        budgets: ContextBudgets,
        features: ContextFeatures,
    ) -> ContextResult:
        current = features.current_turn
        if features.approved_current_content is not None:
            current = current.model_copy(update={"content": features.approved_current_content})

        messages = (
            *snapshot.server_instructions,
            *snapshot.raw_turns,
            *features.evidence,
            current,
        )
        return ContextResult(
            messages=messages,
            provenance=tuple(message.id or message.role for message in messages),
            state=noop_state("context", features.flags.context),
            token_estimates=budgets.estimates,
        )


class HybridContextManager:
    def __init__(self, token_budget: int) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")

        self.token_budget = token_budget

    def prepare(
        self,
        snapshot: SessionSnapshot,
        budgets: ContextBudgets,
        features: ContextFeatures,
    ) -> ContextResult:
        current = features.current_turn

        if features.approved_current_content is not None:
            current = current.model_copy(
                update={
                    "content": features.approved_current_content,
                }
            )

        mandatory = (
            *snapshot.server_instructions,
        *features.memory,
            *features.evidence,
            current,
        )

        if not features.flags.context:
            messages = (
                *snapshot.server_instructions,
                *snapshot.raw_turns,
                *features.evidence,
                current,
            )
            return ContextResult(
                messages=messages,
                provenance=tuple(message.id or message.role for message in messages),
                state=noop_state("context", features.flags.context),
                token_estimates=budgets.estimates,
            )

        mandatory_tokens = count_messages_tokens(mandatory)
        remaining_budget = self.token_budget - mandatory_tokens

        if remaining_budget < 0:
            raise ValueError("context_overflow")

        turns = group_conversation_turns(snapshot.raw_turns)

        selected_turns = select_hybrid_turns(
            query=current.content,
            turns=turns,
            token_budget=remaining_budget,
        )

        selected_history = tuple(message for turn in selected_turns for message in turn)

        messages = (
            *snapshot.server_instructions,
        *features.memory,
            *selected_history,
            *features.evidence,
            current,
        )

        total_tokens = count_messages_tokens(messages)
        while total_tokens > self.token_budget and selected_turns:
            selected_turns = selected_turns[1:]
            selected_history = tuple(message for turn in selected_turns for message in turn)
            messages = (
                *snapshot.server_instructions,
                *selected_history,
                *features.evidence,
                current,
            )
            total_tokens = count_messages_tokens(messages)

        if total_tokens > self.token_budget:
            raise ValueError("context_overflow")

        provenance = tuple(message.id or message.role for message in messages)

        return ContextResult(
            messages=messages,
            provenance=provenance,
            state=OptimizationState(
                module="context",
                status="applied",
                reason="hybrid_relevance_recency_selection",
            ),
            token_estimates=budgets.estimates,
        )
