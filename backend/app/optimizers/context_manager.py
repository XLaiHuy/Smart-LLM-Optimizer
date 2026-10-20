from app.contracts.dtos import ContextBudgets, ContextFeatures, ContextResult, SessionSnapshot
from app.core.policy import noop_state


class PassThroughContext:
    def prepare(
        self, snapshot: SessionSnapshot, budgets: ContextBudgets, features: ContextFeatures
    ) -> ContextResult:
        current = features.current_turn
        if features.approved_current_content is not None:
            current = current.model_copy(update={"content": features.approved_current_content})
        return ContextResult(
            messages=(
                *snapshot.server_instructions,
                *snapshot.raw_turns,
                *features.evidence,
                current,
            ),
            provenance=tuple(m.id or "server_instruction" for m in snapshot.raw_turns)
            + ("current_turn",),
            state=noop_state("context", features.flags.context),
            token_estimates=budgets.estimates,
        )
