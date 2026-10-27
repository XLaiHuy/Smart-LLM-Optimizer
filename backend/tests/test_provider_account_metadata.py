"""Account balance must never be inferred from the key's spending cap."""

import json

import httpx
import pytest
from typer.testing import CliRunner

from app.routing.ml.cli import cli


@pytest.mark.parametrize(
    "status,credits,expected",
    [
        (200, {"total_credits": 0, "total_usage": 0.0290206}, "-0.0290206"),
        (200, {"total_credits": 10, "total_usage": 0.25}, "9.75"),
        (403, {}, None),
        (200, {"total_credits": "NaN", "total_usage": 0}, None),
    ],
)
def test_account_balance_is_separate_from_key_cap(monkeypatch, status, credits, expected):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    urls = []

    def get(self, url, **kwargs):
        urls.append(url)
        if url.endswith("/credits"):
            return httpx.Response(status, json={"data": credits})
        return httpx.Response(
            200,
            json={
                "data": {
                    "limit": 100,
                    "limit_remaining": 99.97,
                    "free_model_daily_requests": {"limit": 50, "remaining": 50},
                }
            },
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    result = CliRunner().invoke(cli, ["provider-limits"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["account_balance_usd"] == expected
    assert data["key_cap_remaining_usd"] == 99.97
    assert not data["key_cap_is_account_balance"]
    assert data["suggested_rpd"] == 40
    assert "test-only-secret" not in result.output
    assert urls == ["https://openrouter.ai/api/v1/key", "https://openrouter.ai/api/v1/credits"]
