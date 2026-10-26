import pytest

from app.providers.openai_compatible import OpenAICompatibleProvider


@pytest.mark.parametrize(
    ("provider_status", "expected_code", "expected_status"),
    [
        (401, "UNAUTHORIZED", 401),
        (404, "MODEL_NOT_FOUND", 404),
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
