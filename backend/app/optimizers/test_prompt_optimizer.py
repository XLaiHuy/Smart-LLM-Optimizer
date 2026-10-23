from types import SimpleNamespace

import pytest

from app.contracts.dtos import ContextResult, FeatureFlags, OptimizationState
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer


def context() -> ContextResult:
    return ContextResult(
        messages=(),
        provenance=(),
        state=OptimizationState(module="context", status="disabled", reason="test"),
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


def test_invalid_thresholds_are_rejected() -> None:
    with pytest.raises(ValueError):
        AdaptivePromptOptimizer(min_compress_tokens=100, llm_threshold=50)
