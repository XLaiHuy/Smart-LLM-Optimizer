import hashlib
import json
import re
from decimal import Decimal
from time import perf_counter

from app.config import ROOT
from app.contracts.dtos import (
    CostSnapshot,
    Message,
    ModelConfiguration,
    ProviderOptions,
    ProviderResult,
    RegistrySnapshot,
    RouteEvidence,
    RouteRate,
)
from app.contracts.errors import AppError
from app.contracts.research import FixtureCase, FixtureManifest

REGISTRY = RegistrySnapshot(
    mock_config_id="fixture-reference",
    configurations=(
        ModelConfiguration(
            config_id="fixture-reference",
            model_id="fixture-reference-v1",
            context_window=12000,
            max_output_tokens=256,
            structured_output=True,
        ),
        ModelConfiguration(
            config_id="fixture-small",
            model_id="fixture-small-v1",
            context_window=1600,
            max_output_tokens=128,
        ),
    ),
)
COSTS = CostSnapshot(
    version="simulation-rates-v1",
    rates=(
        RouteRate(
            config_id="fixture-reference",
            input_per_million=Decimal("2"),
            output_per_million=Decimal("8"),
        ),
        RouteRate(
            config_id="fixture-small",
            input_per_million=Decimal("0.2"),
            output_per_million=Decimal("0.8"),
        ),
    ),
)
EVIDENCE = tuple(
    RouteEvidence(
        config_id=model.config_id,
        domain=domain,
        qualifies=True,
        latency_ms=10,
        provenance="fixture",
    )
    for model in REGISTRY.configurations
    for domain in ("general", "code", "structured")
    if not (model.config_id == "fixture-small" and domain == "code")
)


def manifest() -> FixtureManifest:
    return FixtureManifest.model_validate_json(
        (ROOT / "config/router-fixtures.json").read_text(encoding="utf-8")
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def grade_fixture(prediction: str | None, case: FixtureCase, error: str | None) -> bool:
    if case.expected_error:
        return error == case.expected_error
    if error or prediction is None:
        return False
    if case.check == "json_code":
        try:
            return bool(json.loads(prediction) == {"code": case.expected})
        except ValueError:
            return False
    return prediction == case.expected


class FixtureProvider:
    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult:
        started = perf_counter()
        text = "\n".join(m.content for m in messages)
        if "[fixture:timeout]" in text:
            raise AppError("PROVIDER_TIMEOUT", 504, "Intentional fixture timeout; no network")
        code = re.search(r"OU-\d{2}", text)
        response = code.group() if code else "fixture response"
        if "json" in text.casefold():
            response = json.dumps({"code": response})
        return ProviderResult(
            text=response,
            duration_ms=(perf_counter() - started) * 1000,
        )
