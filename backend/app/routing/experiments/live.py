"""Disabled-by-default live pilot wiring. No network occurs at construction."""

from dataclasses import dataclass

from app.config import Settings
from app.contracts.dtos import CostSnapshot, RegistrySnapshot
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
        return catalog.cost_snapshot()
