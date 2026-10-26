from app.contracts.dtos import ChatRequest, FeatureFlags
from app.core.policy import resolve_configuration


def test_manual_model_keeps_enabled_optimizers_except_router() -> None:
    request = ChatRequest(
        session_id="session-1",
        client_request_id="request-1",
        message="Remember my deadline.",
        mode="baseline",
        policy_id="fixed_candidate:groq-gpt-oss-20b",
        flags=FeatureFlags(router=True, rewrite=True, context=True, memory=True),
    )

    config = resolve_configuration(request)

    assert config.candidate_id == "groq-gpt-oss-20b"
    assert config.flags == FeatureFlags(router=False, rewrite=True, context=True, memory=True)
