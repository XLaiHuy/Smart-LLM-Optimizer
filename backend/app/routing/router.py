from app.contracts.dtos import (
    ContextResult,
    CostSnapshot,
    PolicySnapshot,
    RegistrySnapshot,
    RemainingBudget,
    RouteDecision,
    TaskProfile,
)
from app.contracts.errors import AppError


class FixedMockRouter:
    def select(
        self,
        profile: TaskProfile,
        prepared: ContextResult,
        registry: RegistrySnapshot,
        costs: CostSnapshot,
        policy: PolicySnapshot,
        remaining: RemainingBudget,
    ) -> RouteDecision:
        config = next(
            (c for c in registry.configurations if c.config_id == registry.mock_config_id), None
        )
        if config is None:
            raise AppError("NO_COMPATIBLE_MODEL", 422, "Mock registry configuration missing")
        return RouteDecision(
            model_id=config.model_id,
            config_id=config.config_id,
            policy_id=policy.policy_id,
            reason="baseline_quality_uncertain"
            if config.execution_source == "live"
            else "foundation_fixed_mock",
        )
