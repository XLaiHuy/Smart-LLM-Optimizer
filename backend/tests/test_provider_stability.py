"""Offline fault tests: persistent admission, credentials and uncertain billing."""

import asyncio
from decimal import Decimal

import pytest

from app.config import Settings
from app.contracts.errors import AppError
from app.providers.catalog import ModelEntry
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.quota import ProviderQuota, reset_seconds, retry_seconds
from app.storage.database import Database


def entry(config_id="groq-one", model="openai/gpt-oss-120b", host="api.groq.com"):
    return ModelEntry(
        config_id=config_id,
        model_id=model,
        kind="generation",
        context_window=20000,
        max_output_tokens=128,
        input_per_million=Decimal(".15"),
        output_per_million=Decimal(".6"),
        source_url="https://console.groq.com/docs/rate-limits",
        effective_at="2026-10-26",
        verified_access=True,
        pricing_verified=True,
        endpoint="chat_completions",
        base_url=f"https://{host}/openai/v1",
        api_key_env="GROQ_API_KEY",
    )


@pytest.mark.asyncio
async def test_aliases_workers_and_restart_share_quota(app):
    c = app.state.container
    settings = c.settings.model_copy(update={"groq_quota_rpm": 2})
    other = Database(settings)

    def clock():
        return 1700000000.0

    first = ProviderQuota(c.db, settings, clock)
    second = ProviderQuota(other, settings, clock)
    try:
        results = await asyncio.gather(
            first.acquire(entry(), 200),
            second.acquire(entry("groq-alias"), 200),
            first.acquire(entry(), 200),
            return_exceptions=True,
        )
        assert sum(isinstance(r, str) for r in results) == 2
        assert sum(isinstance(r, AppError) for r in results) == 1
        restarted = ProviderQuota(other, settings, clock)
        with pytest.raises(AppError) as caught:
            await restarted.acquire(entry("yet-another-alias"), 200)
        assert caught.value.dispatch_state == "not_dispatched"
        assert caught.value.retry_after_seconds == 60
    finally:
        await other.close()


@pytest.mark.asyncio
async def test_unknown_tokens_are_retained_but_known_usage_reconciles(app):
    c = app.state.container
    limiter = ProviderQuota(
        c.db, c.settings.model_copy(update={"groq_quota_tpm": 10}), lambda: 1700000000.0
    )
    ticket = await limiter.acquire(entry(), 6)
    await limiter.reconcile(entry(), ticket, None)
    with pytest.raises(AppError):
        await limiter.acquire(entry(), 6)
    await limiter.reconcile(entry(), ticket, 2)
    assert await limiter.acquire(entry(), 6)


@pytest.mark.asyncio
async def test_retry_after_and_headers_override_fixed_cooldown(app):
    c = app.state.container
    clock = [1700000000.0]
    limiter = ProviderQuota(c.db, c.settings, lambda: clock[0])
    await limiter.observe(entry(), {"retry-after": "125"}, 429)
    clock[0] += 61
    with pytest.raises(AppError) as caught:
        await limiter.acquire(entry(), 200)
    assert caught.value.retry_after_seconds == 64
    clock[0] += 65
    assert await limiter.acquire(entry(), 200)
    await limiter.observe(
        entry(), {"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "7.66s"}, 200
    )
    with pytest.raises(AppError) as caught:
        await limiter.acquire(entry(), 200)
    assert caught.value.retry_after_seconds == 8


@pytest.mark.asyncio
async def test_openrouter_daily_pool_spans_free_models_and_resets_utc(app):
    c = app.state.container
    clock = [1700000000.0]
    limiter = ProviderQuota(
        c.db, c.settings.model_copy(update={"openrouter_free_rpd": 1}), lambda: clock[0]
    )
    await limiter.acquire(entry(model="one:free", host="openrouter.ai"), 200)
    with pytest.raises(AppError):
        await limiter.acquire(entry(model="two:free", host="openrouter.ai"), 200)
    clock[0] += 86400
    assert await limiter.acquire(entry(model="two:free", host="openrouter.ai"), 200)


@pytest.mark.asyncio
async def test_account_metadata_accounts_for_calls_from_other_applications(app):
    c = app.state.container
    limiter = ProviderQuota(c.db, c.settings, lambda: 1700000000.0)
    model = entry(model="one:free", host="openrouter.ai")
    # A real 50/day account already used 39 requests elsewhere: the 40/day
    # safety ceiling leaves just one attempt, not another fresh pool of 40.
    await limiter.sync_free_metadata(
        model, {"free_model_daily_requests": {"used": 39, "limit": 50, "remaining": 11}}
    )
    assert not await limiter.free_metadata_due(model)
    await limiter.acquire(model, 200)
    with pytest.raises(AppError) as caught:
        await limiter.acquire(model, 200)
    assert caught.value.retry_after_seconds > 60


@pytest.mark.asyncio
async def test_oversized_output_profile_is_rejected_before_dispatch(app):
    c = app.state.container
    with pytest.raises(AppError) as caught:
        await ProviderQuota(c.db, c.settings).acquire(entry(), 8192)
    assert caught.value.code == "PROVIDER_REQUEST_TOO_LARGE"
    assert caught.value.dispatch_state == "not_dispatched"


@pytest.mark.asyncio
async def test_client_is_bound_to_exact_key_and_missing_named_key_never_borrows(monkeypatch):
    from app.providers.catalog import Catalog

    item = entry()
    catalog = Catalog.model_construct(
        models=(item,), version="test", baseline_config=item.config_id, embedding_config="unused"
    )
    provider = OpenAICompatibleProvider("dummy-groq", catalog, Settings(_env_file=None))
    try:
        client = provider._get_client(None, "dummy-openai")
        assert client is not provider.client
        assert client.api_key == "dummy-openai"
        assert provider._get_client(None, "dummy-openai") is client
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(AppError) as caught:
            provider.get_client(item)
        assert caught.value.code == "PROVIDER_CONFIGURATION_ERROR"
        assert caught.value.status == 503
    finally:
        await provider.close()


def test_status_and_retry_metadata_never_expose_provider_message():
    error = OpenAICompatibleProvider._provider_status_error(401, "secret-private-provider-message")
    assert error.status == 503
    assert error.upstream_status == 401
    assert error.dispatch_state == "rejected"
    assert "secret-private" not in error.message
    assert retry_seconds("120") == 120
    assert reset_seconds("1m2.5s") == 62.5


def test_health_is_shared_by_alias_and_success_does_not_erase_retry_after():
    from app.routing.model_health import ModelHealth

    health = ModelHealth({"old": "host|credential|model", "new": "host|credential|model"})
    health.record_failure("old", status_code=429, retry_after_seconds=125)
    health.record_success("new")
    assert not health.is_available("new")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,setting",
    [("openrouter.ai", "openrouter_paid_rpm"), ("api.openai.com", "openai_quota_rpm")],
)
async def test_paid_profiles_are_paced_across_aliases_before_dispatch(app, host, setting):
    c = app.state.container
    clock = [1700000000.0]
    settings = c.settings.model_copy(update={setting: 1})
    limiter = ProviderQuota(c.db, settings, lambda: clock[0])
    model = entry(model="paid-model", host=host)
    await limiter.acquire(model, 200)
    with pytest.raises(AppError) as caught:
        await ProviderQuota(c.db, settings, lambda: clock[0]).acquire(
            model.model_copy(update={"config_id": "same-model-alias"}), 200
        )
    assert caught.value.dispatch_state == "not_dispatched"
    assert caught.value.code == "RATE_LIMITED"
    clock[0] += 61
    assert await limiter.acquire(model, 200)
