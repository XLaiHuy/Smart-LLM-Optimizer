"""Operator-reviewed, versioned prices. No model-name or free-price guesses."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl

from app.contracts.dtos import DTO, CostEstimate, Usage
from app.contracts.errors import AppError


class ModelEntry(DTO):
    config_id: str
    model_id: str
    kind: Literal["generation", "embedding"]
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(default=1024, gt=0)
    input_per_million: Decimal = Field(ge=0)
    output_per_million: Decimal = Field(default=Decimal(0), ge=0)
    cached_per_million: Decimal | None = Field(default=None, ge=0)
    cache_write_per_million: Decimal | None = Field(default=None, ge=0)
    source_url: HttpUrl
    effective_at: str
    verified_access: bool = False
    pricing_verified: bool = False


class Catalog(DTO):
    version: str
    baseline_config: str
    embedding_revision: str = "v1"
    embedding_config: str
    models: tuple[ModelEntry, ...]

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        try:
            return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise AppError(
                "DEPENDENCY_UNAVAILABLE", 503, "Configure a reviewed model catalog first"
            ) from exc

    def entry(self, config_id: str) -> ModelEntry:
        entry = next((m for m in self.models if m.config_id == config_id), None)
        if not entry or not entry.verified_access or not entry.pricing_verified:
            raise AppError(
                "NO_COMPATIBLE_MODEL", 422, "Model access not verified in configured catalog"
            )
        return entry


def price(
    entry: ModelEntry, usage: Usage, version: str, cache_write: int | None = 0
) -> CostEstimate:
    known = usage.input_tokens is not None and usage.output_tokens is not None
    cached = usage.cached_input_tokens
    if cached is None or cache_write is None:
        known = False
    if not known:
        return CostEstimate(scope="call", status="unknown", price_catalog_version=version)
    assert usage.input_tokens is not None and usage.output_tokens is not None
    assert cached is not None and cache_write is not None
    # Cached/cache-write input are subsets; reasoning is already included in output.
    uncached = usage.input_tokens - cached - cache_write
    if (
        uncached < 0
        or (cached and entry.cached_per_million is None)
        or (cache_write and entry.cache_write_per_million is None)
    ):
        return CostEstimate(scope="call", status="unknown", price_catalog_version=version)
    total = (
        Decimal(uncached) * entry.input_per_million
        + Decimal(cached) * (entry.cached_per_million or 0)
        + Decimal(cache_write) * (entry.cache_write_per_million or 0)
        + Decimal(usage.output_tokens) * entry.output_per_million
    ) / Decimal(1000000)
    return CostEstimate(
        scope="call", status="estimated", serving_usd=total, price_catalog_version=version
    )


def upper_cost(entry: ModelEntry, input_bound: int) -> Decimal:
    # Covers every configured input category; output limit includes hidden reasoning.
    rate = max(
        entry.input_per_million, entry.cached_per_million or 0, entry.cache_write_per_million or 0
    )
    return (
        Decimal(input_bound) * rate + Decimal(entry.max_output_tokens) * entry.output_per_million
    ) / Decimal(1000000)
