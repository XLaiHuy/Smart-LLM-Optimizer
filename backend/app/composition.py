from app.analytics.service import AnalyticsService
from app.auth.service import AuthService
from app.config import Settings
from app.contracts.dtos import ModelConfiguration, RegistrySnapshot
from app.contracts.errors import AppError
from app.contracts.protocols import PromptOptimizer
from app.core.metering import MeteredCalls
from app.core.orchestrator import Orchestrator
from app.core.tools import ToolExecutor
from app.documents.service import DocumentService
from app.documents.tasks import DocumentTaskProcessor
from app.memory.memory_manager import NoOpMemoryManager
from app.optimizers.context_manager import HybridContextManager, PassThroughContext
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer, NoOpPromptOptimizer
from app.providers.catalog import Catalog
from app.providers.mock_provider import DeterministicMockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.routing.experiments.live import LiveResearchWiring
from app.routing.experiments.service import ResearchService
from app.routing.features import ObservableTaskAnalyzer
from app.routing.ml.feedback import RouterFeedbackService, RoutingDrift
from app.routing.ml.pipeline import RouterTrainingPipeline
from app.routing.ml.service import MLRouterService
from app.routing.policies import PolicyRouter
from app.routing.router import FixedMockRouter
from app.storage.database import Database
from app.storage.ledger import SqlBudgetLedger
from app.storage.progress import SqlProgressStore
from app.storage.repositories import SqlMemoryStore, SqlSessionStore, SqlTraceStore
from app.storage.tools import SqlToolStore


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
        catalog = (
            Catalog.load(settings.model_catalog_path)
            if settings.model_catalog_path.exists()
            else None
        )
        live = None
        server_key = (
            settings.groq_api_key.get_secret_value()
            or settings.openrouter_api_key.get_secret_value()
            or settings.openai_api_key.get_secret_value()
        )
        if catalog:
            if settings.provider_mode == "live":
                if not server_key:
                    raise AppError("DEPENDENCY_UNAVAILABLE", 503, "Live mode requires a server API key")
                baseline = catalog.entry(catalog.baseline_config)
                embedding = catalog.entry(catalog.embedding_config)
                if baseline.kind != "generation" or embedding.kind != "embedding":
                    raise AppError("VALIDATION_ERROR", 422, "Catalog config kinds are invalid")
                live = OpenAICompatibleProvider(server_key, catalog, settings=settings)
            gen_configs = [
                ModelConfiguration(
                    config_id=m.config_id,
                    model_id=m.model_id,
                    execution_source="live" if live else "mock",
                    context_window=m.context_window,
                    available=m.verified_access and m.pricing_verified,
                    availability_reason="reviewed"
                    if m.verified_access and m.pricing_verified
                    else "access_or_pricing_unverified",
                    max_output_tokens=m.max_output_tokens,
                    structured_output=m.structured_output,
                    function_calling=m.function_calling,
                    reasoning_effort=m.reasoning_effort,
                    supported_parameters=m.supported_parameters,
                )
                for m in catalog.models
                if m.kind == "generation"
            ]
            if not any(c.config_id == "mock-baseline" for c in gen_configs):
                gen_configs.append(
                    ModelConfiguration(
                        config_id="mock-baseline",
                        model_id="mock-echo-v1",
                        execution_source="mock",
                        context_window=128000,
                        available=True,
                        function_calling=True,
                    )
                )
            self.registry = RegistrySnapshot(
                mock_config_id="mock-baseline" if not live else catalog.baseline_config,
                configurations=tuple(gen_configs),
            )
        else:
            self.registry = RegistrySnapshot(
                mock_config_id=settings.mock_config_id,
                configurations=(
                    ModelConfiguration(
                        config_id="mock-baseline", model_id="mock-echo-v1", function_calling=True
                    ),
                ),
            )
        self.live = live
        self.provider = live or DeterministicMockProvider()
        self.metering = MeteredCalls(
            self.db, settings, self.ledger, catalog if settings.provider_mode == "live" else None, live
        )
        self.ml_router = MLRouterService.load(
            settings.ml_router_artifact_path, live_approved=settings.ml_router_live_approved
        )
        self.router_drift = RoutingDrift()
        self.router_feedback = RouterFeedbackService(self.db, self.router_drift)
        self.research = ResearchService(
            self.db,
            LiveResearchWiring(settings, self.metering, self.provider, self.sessions, self.registry)
            if live
            else None,
            ml=self.ml_router,
        )
        self.training = RouterTrainingPipeline(
            settings, self.db, self.ledger, self.import_research_router
        )
        imported = settings.router_training_directory / "imported.json"
        if imported.exists():
            candidate = MLRouterService.load(imported, live_approved=False)
            if candidate.status == "ML_ARTIFACT_READY":
                self.import_research_router(candidate)
                self.training.active_hash = candidate.hash
        self.documents = DocumentService(
            self.db,
            settings,
            self.sessions,
            self.metering,
            self.provider,
            DocumentTaskProcessor(settings, self.sessions, self.metering, self.provider),
        )
        if settings.adaptive_prompt_enabled:
            # Import and load the model only when the feature is explicitly enabled.
            from app.optimizers.llmlingua_compressor import LLMLinguaCompressor

            prompt_optimizer: PromptOptimizer = AdaptivePromptOptimizer(
                llm_compressor=LLMLinguaCompressor(),
            )
        else:
            prompt_optimizer = NoOpPromptOptimizer()

        self.orchestrator = Orchestrator(
            self.sessions,
            self.provider,
            ObservableTaskAnalyzer(),
            NoOpMemoryManager(),
            (
                HybridContextManager(settings.context_token_budget)
                if settings.hybrid_context_enabled
                else PassThroughContext()
            ),
            prompt_optimizer,
            PolicyRouter(self.ml_router, self.router_drift) if live else FixedMockRouter(),
            self.registry,
        )
        self.orchestrator.metering = self.metering
        self.orchestrator.outcomes = self.router_feedback
        self.orchestrator.documents = self.documents
        self.progress = SqlProgressStore(self.db)
        self.orchestrator.progress = self.progress
        self.tools = SqlToolStore(self.db)
        self.orchestrator.tools = ToolExecutor(self.tools)

    def import_research_router(self, engine: MLRouterService) -> None:
        """New experiments see the candidate; active chat and frozen runs retain theirs."""
        self.research.ml = engine
        self.research.router = PolicyRouter(engine)
