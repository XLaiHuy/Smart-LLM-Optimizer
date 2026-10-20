from app.contracts.dtos import MemoryPlan, MemoryResult, SessionSnapshot
from app.core.policy import noop_state


class NoOpMemoryManager:
    async def prepare(self, snapshot: SessionSnapshot, plan: MemoryPlan) -> MemoryResult:
        return MemoryResult(snapshot=snapshot, state=noop_state("memory", plan.enabled))
