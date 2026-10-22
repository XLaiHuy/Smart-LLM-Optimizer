"""Disabled-by-default live pilot wiring. No network occurs at construction."""

from dataclasses import dataclass
from decimal import Decimal

from app.config import Settings
from app.contracts.dtos import CostSnapshot, RegistrySnapshot, RouteRate
from app.contracts.protocols import LLMProvider, SessionStore
from app.core.metering import MeteredCalls


@dataclass(frozen=True)
class LiveResearchWiring:
    settings: Settings
    metering: MeteredCalls
    provider: LLMProvider
    sessions: SessionStore
    registry: RegistrySnapshot

    @property
    def enabled(self) -> bool:
        return (
            self.settings.research_live_enabled
            and self.settings.provider_mode == "live"
            and self.metering.catalog is not None
        )

    def costs(self) -> CostSnapshot:
        catalog = self.metering.catalog
        assert catalog
        return CostSnapshot(
            version=catalog.version,
            rates=tuple(
                RouteRate(
                    config_id=m.config_id,
                    input_per_million=max(
                        m.input_per_million,
                        m.cached_per_million or Decimal(0),
                        m.cache_write_per_million or Decimal(0),
                    ),
                    output_per_million=m.output_per_million,
                )
                for m in catalog.models
                if m.kind == "generation"
            ),
        )
