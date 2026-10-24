from app.contracts.dtos import (
    ChatRequest,
    EffectiveConfiguration,
    FeatureFlags,
    ModuleName,
    OptimizationState,
)


def resolve_configuration(req: ChatRequest) -> EffectiveConfiguration:
    if req.mode == "baseline":
        candidate_id = None
        policy_id = req.policy_id or "baseline"
        if policy_id.startswith("fixed_candidate:"):
            candidate_id = policy_id.split(":", 1)[1]
        return EffectiveConfiguration(
            policy_id=policy_id,
            flags=FeatureFlags(router=False, rewrite=False, context=False, memory=False),
            candidate_id=candidate_id,
        )
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
