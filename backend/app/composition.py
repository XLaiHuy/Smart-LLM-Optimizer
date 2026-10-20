from app.auth.service import AuthService
from app.config import Settings
from app.contracts.dtos import ModelConfiguration, RegistrySnapshot
from app.core.orchestrator import Orchestrator
from app.memory.memory_manager import NoOpMemoryManager
from app.optimizers.context_manager import PassThroughContext
from app.optimizers.prompt_optimizer import NoOpPromptOptimizer
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
        self.orchestrator = Orchestrator(
            self.sessions,
            DeterministicMockProvider(),
            UnknownTaskAnalyzer(),
            NoOpMemoryManager(),
            PassThroughContext(),
            NoOpPromptOptimizer(),
            FixedMockRouter(),
            self.registry,
        )
