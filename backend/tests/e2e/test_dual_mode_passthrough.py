from app.contracts.dtos import (
    ChatRequest,
    FeatureFlags,
)
from app.core.policy import resolve_configuration


def test_baseline_fixed_candidate_configuration():
    req = ChatRequest(
        session_id="test-session",
        client_request_id="req-1",
        message="Xin chao Viet Nam",
        mode="baseline",
        policy_id="fixed_candidate:groq-llama-3.3-70b-versatile",
    )
    config = resolve_configuration(req)
    assert config.policy_id == "fixed_candidate:groq-llama-3.3-70b-versatile"
    assert config.candidate_id == "groq-llama-3.3-70b-versatile"
    assert config.flags == FeatureFlags(router=False, rewrite=False, context=False, memory=False)


def test_optimized_mode_configuration():
    req = ChatRequest(
        session_id="test-session",
        client_request_id="req-2",
        message="Xin chao Viet Nam",
        mode="optimized",
    )
    config = resolve_configuration(req)
    assert config.policy_id == "foundation-mock-v3"
    assert config.candidate_id is None
    assert config.flags.router is True
    assert config.flags.rewrite is True
    assert config.flags.context is True
    assert config.flags.memory is True
