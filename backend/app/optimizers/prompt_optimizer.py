from app.contracts.dtos import ContextResult, ExecutionRequest, FeatureFlags, OptimizedPrompt
from app.core.policy import noop_state


class NoOpPromptOptimizer:
    async def optimize(
        self, req: ExecutionRequest, context: ContextResult, flags: FeatureFlags
    ) -> OptimizedPrompt:
        return OptimizedPrompt(
            original=req.request.message,
            proposed=req.request.message,
            state=noop_state("rewrite", flags.rewrite),
        )
