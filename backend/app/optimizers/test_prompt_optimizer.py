from types import SimpleNamespace

import pytest

from app.contracts.dtos import ContextResult, FeatureFlags, Message, OptimizationState
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer


def context() -> ContextResult:
    return ContextResult(
        messages=(),
        provenance=(),
        state=OptimizationState(module="context", status="disabled", reason="test"),
    )


def context_with_messages(*messages: Message) -> ContextResult:
    return ContextResult(
        messages=messages,
        provenance=tuple(message.id or message.role for message in messages),
        state=OptimizationState(module="context", status="applied", reason="test"),
    )


def request(message: str) -> SimpleNamespace:
    return SimpleNamespace(request=SimpleNamespace(message=message))


@pytest.mark.asyncio
async def test_disabled_rewrite_keeps_original() -> None:
    result = await AdaptivePromptOptimizer().optimize(
        request("short prompt"),  # type: ignore[arg-type]
        context(),
        FeatureFlags(rewrite=False),
    )
    assert result.state.status == "disabled"
    assert result.proposed == "short prompt"


@pytest.mark.asyncio
async def test_short_prompt_is_skipped() -> None:
    result = await AdaptivePromptOptimizer(min_compress_tokens=10).optimize(
        request("short prompt"),  # type: ignore[arg-type]
        context(),
        FeatureFlags(rewrite=True),
    )
    assert result.state.status == "skipped"
    assert result.state.reason == "under_threshold"


@pytest.mark.asyncio
async def test_llm_result_requires_preservation() -> None:
    fake = SimpleNamespace(
        compress=lambda prompt: {
            "compressed": "shortened prompt",
            "status": "applied",
            "preservation": "unknown",
            "original_tokens": 600,
            "compressed_tokens": 300,
        }
    )
    result = await AdaptivePromptOptimizer(
        llm_compressor=fake, min_compress_tokens=10, llm_threshold=20
    ).optimize(
        request("Explain machine learning. " * 100),  # type: ignore[arg-type]
        context(),
        FeatureFlags(rewrite=True),
    )
    assert result.state.status == "skipped"
    assert result.proposed == result.original


@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_original() -> None:
    def fail(_: str) -> dict[str, object]:
        raise RuntimeError("model unavailable")

    fake = SimpleNamespace(compress=fail)
    result = await AdaptivePromptOptimizer(
        llm_compressor=fake, min_compress_tokens=10, llm_threshold=20
    ).optimize(
        request("Explain machine learning. " * 100),  # type: ignore[arg-type]
        context(),
        FeatureFlags(rewrite=True),
    )

    assert result.state.status == "skipped"
    assert result.state.reason == "llmlingua_error"
    assert result.proposed == result.original


@pytest.mark.asyncio
async def test_llm_without_token_savings_is_skipped() -> None:
    fake = SimpleNamespace(
        compress=lambda prompt: {
            "compressed": "same length",
            "status": "applied",
            "preservation": "preserved",
            "original_tokens": 100,
            "compressed_tokens": 100,
        }
    )
    result = await AdaptivePromptOptimizer(
        llm_compressor=fake, min_compress_tokens=10, llm_threshold=20
    ).optimize(
        request("Explain machine learning. " * 100),  # type: ignore[arg-type]
        context(),
        FeatureFlags(rewrite=True),
    )

    assert result.state.status == "skipped"
    assert result.state.reason == "llmlingua_no_token_savings"


@pytest.mark.asyncio
async def test_context_messages_are_compressed_not_only_current_request() -> None:
    calls: list[str] = []

    def compress(prompt: str) -> dict[str, object]:
        calls.append(prompt)
        return {
            "compressed": "compressed history",
            "status": "applied",
            "preservation": "preserved",
            "original_tokens": 600,
            "compressed_tokens": 200,
        }

    history = "long history " * 5
    current = "Please answer using the history."
    result = await AdaptivePromptOptimizer(
        llm_compressor=SimpleNamespace(compress=compress),
        min_compress_tokens=1,
        llm_threshold=5,
    ).optimize(
        request(current),  # type: ignore[arg-type]
        context_with_messages(
            Message(role="system", content="Keep system instructions."),
            Message(role="assistant", id="history", content=history),
            Message(role="user", id="current", content=current),
        ),
        FeatureFlags(rewrite=True),
    )

    assert result.state.status == "applied"
    assert calls == [history, current]
    assert result.messages is not None
    assert result.messages[0].content == "Keep system instructions."
    assert result.messages[1].content == "compressed history"


def test_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(ValueError):
        AdaptivePromptOptimizer(min_compress_tokens=100, llm_threshold=50)
