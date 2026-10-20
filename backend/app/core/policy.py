from app.contracts.dtos import (
    ChatRequest,
    EffectiveConfiguration,
    FeatureFlags,
    ModuleName,
    OptimizationState,
)


def resolve_configuration(req: ChatRequest) -> EffectiveConfiguration:
    if req.mode == "baseline":
        return EffectiveConfiguration(policy_id="baseline", flags=FeatureFlags())
    return EffectiveConfiguration(
        policy_id="foundation-mock-v3",
        flags=req.flags or FeatureFlags(router=True, rewrite=True, context=True, memory=True),
    )


def noop_state(module: ModuleName, enabled: bool) -> OptimizationState:
    return OptimizationState(
        module=module,
        status="not_implemented" if enabled else "disabled",
        reason="optimizer_not_implemented_g0" if enabled else "feature_disabled",
    )
