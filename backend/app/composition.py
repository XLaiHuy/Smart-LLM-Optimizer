from app.analytics.service import AnalyticsService
from app.auth.service import AuthService
from app.config import Settings
from app.contracts.dtos import ModelConfiguration, RegistrySnapshot
from app.contracts.errors import AppError
from app.core.metering import MeteredCalls
from app.core.orchestrator import Orchestrator
from app.documents.service import DocumentService
from app.documents.tasks import DocumentTaskProcessor
from app.memory.memory_manager import NoOpMemoryManager
from app.optimizers.context_manager import PassThroughContext
from app.optimizers.prompt_optimizer import NoOpPromptOptimizer
from app.providers.catalog import Catalog
from app.providers.live import OpenAIProvider
from app.providers.mock_provider import DeterministicMockProvider
from app.routing.analyzer import UnknownTaskAnalyzer
from app.routing.router import FixedMockRouter
from app.storage.database import Database
from app.storage.ledger import SqlBudgetLedger
from app.storage.repositories import SqlMemoryStore, SqlSessionStore, SqlTraceStore


class Container:
    """The sole concrete wiring root; algorithms consume typed ports."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings)
        self.analytics = AnalyticsService(self.db, settings)
        self.auth = AuthService(self.db, settings)
        self.sessions = SqlSessionStore(self.db)
        self.memory_store = SqlMemoryStore(self.db)
        self.traces = SqlTraceStore(self.db)
        self.ledger = SqlBudgetLedger(self.db, settings.project_budget_usd)
        self.registry = RegistrySnapshot(
            mock_config_id=settings.mock_config_id,
            configurations=(
                ModelConfiguration(config_id="mock-baseline", model_id="mock-echo-v1"),
            ),
        )
        catalog = (
            Catalog.load(settings.model_catalog_path) if settings.provider_mode == "live" else None
        )
        live = None
        if catalog:
            if not settings.openai_api_key.get_secret_value():
                raise AppError("DEPENDENCY_UNAVAILABLE", 503, "Live mode requires a server API key")
            baseline = catalog.entry(catalog.baseline_config)
            embedding = catalog.entry(catalog.embedding_config)
            if baseline.kind != "generation" or embedding.kind != "embedding":
                raise AppError("VALIDATION_ERROR", 422, "Catalog config kinds are invalid")
            live = OpenAIProvider(settings.openai_api_key.get_secret_value(), catalog)
            self.registry = RegistrySnapshot(
                mock_config_id=catalog.baseline_config,
                configurations=tuple(
                    ModelConfiguration(
                        config_id=m.config_id,
                        model_id=m.model_id,
                        execution_source="live",
                        context_window=m.context_window,
                        available=m.verified_access,
                    )
                    for m in catalog.models
                    if m.kind == "generation"
                ),
            )
        self.live = live
        self.provider = live or DeterministicMockProvider()
        self.metering = MeteredCalls(self.db, settings, self.ledger, catalog, live)
        self.documents = DocumentService(
            self.db,
            settings,
            self.sessions,
            self.metering,
            self.provider,
            DocumentTaskProcessor(settings, self.sessions, self.metering, self.provider),
        )
        self.orchestrator = Orchestrator(
            self.sessions,
            self.provider,
            UnknownTaskAnalyzer(),
            NoOpMemoryManager(),
            PassThroughContext(),
            NoOpPromptOptimizer(),
            FixedMockRouter(),
            self.registry,
        )
        self.orchestrator.metering = self.metering
        self.orchestrator.documents = self.documents
