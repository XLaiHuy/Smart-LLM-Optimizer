import pytest

from app.providers.openai_compatible import OpenAICompatibleProvider


@pytest.mark.parametrize(
    ("provider_status", "expected_code", "expected_status"),
    [
        (401, "PROVIDER_CONFIGURATION_ERROR", 503),
        (404, "MODEL_NOT_FOUND", 503),
        (429, "RATE_LIMITED", 429),
        (500, "DEPENDENCY_UNAVAILABLE", 503),
        (503, "DEPENDENCY_UNAVAILABLE", 503),
    ],
)
def test_provider_status_error_is_preserved_for_router_health(
    provider_status: int,
    expected_code: str,
    expected_status: int,
) -> None:
    error = OpenAICompatibleProvider._provider_status_error(provider_status, "provider failure")

    assert error.code == expected_code
    assert error.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "credential", "model", "effort", "limit_key"),
    [
        (
            "https://api.openai.com/v1",
            "OPENAI_API_KEY",
            "gpt-6-luna",
            "none",
            "max_completion_tokens",
        ),
        (
            "https://api.groq.com/openai/v1",
            "GROQ_API_KEY",
            "openai/gpt-oss-20b",
            "low",
            "max_tokens",
        ),
        (
            "https://openrouter.ai/api/v1",
            "OPENROUTER_API_KEY",
            "openai/gpt-oss-20b",
            "low",
            "max_tokens",
        ),
    ],
)
async def test_sdk_dispatch_uses_reviewed_completion_limit_and_effort(
    monkeypatch, url, credential, model, effort, limit_key
):
    """Exercise the serialized SDK request without any external connection."""
    import json

    import httpx
    from openai import AsyncOpenAI

    from app.config import Settings
    from app.contracts.dtos import Message, ProviderOptions
    from app.providers.catalog import Catalog, ModelEntry

    captured = []
    headers = []

    def respond(request):
        captured.append(json.loads(request.content))
        headers.append(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "2"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13},
            },
        )

    item = ModelEntry(
        config_id="reviewed-profile",
        model_id=model,
        kind="generation",
        context_window=16000,
        max_output_tokens=2048,
        input_per_million=".1",
        output_per_million=".5",
        source_url="https://example.com/test",
        effective_at="test",
        verified_access=True,
        pricing_verified=True,
        endpoint="chat_completions",
        base_url=url,
        api_key_env=credential,
        reasoning_effort=effort,
    )
    catalog = Catalog.model_construct(
        models=(item,), version="test", baseline_config=item.config_id, embedding_config="unused"
    )
    monkeypatch.setenv(credential, "test-only-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    provider = OpenAICompatibleProvider("test-only-key", catalog, Settings(_env_file=None))
    client = AsyncOpenAI(
        api_key="test-only-key",
        base_url=url,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    provider._clients[(url, "test-only-key")] = client
    try:
        result = await provider.generate(
            (Message(role="user", content="1+1?"),),
            ProviderOptions(
                request_id="test", call_id="test", config_id=item.config_id, model_id=model
            ),
        )
        assert result.text == "2" and result.usage.output_tokens == 1
        assert len(captured) == 1
        assert captured[0][limit_key] == 2048
        assert captured[0]["reasoning_effort"] == effort
        assert ("max_tokens" in captured[0]) != ("max_completion_tokens" in captured[0])
        assert headers[0].get("x-client-request-id") == (
            "test" if credential == "OPENAI_API_KEY" else None
        )
        if credential == "OPENROUTER_API_KEY":
            assert captured[0]["provider"] == {
                "require_parameters": True,
                "max_price": {"prompt": 0.1, "completion": 0.5, "request": 0},
            }
        else:
            assert "provider" not in captured[0]
    finally:
        await provider.close()
