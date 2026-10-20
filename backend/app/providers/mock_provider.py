import asyncio
from time import perf_counter

from app.contracts.dtos import Message, ProviderOptions, ProviderResult


class DeterministicMockProvider:
    async def generate(
        self, messages: tuple[Message, ...], opts: ProviderOptions
    ) -> ProviderResult:
        started = perf_counter()
        await asyncio.sleep(0)  # A real async boundary, no external inference.
        current = messages[-1].content
        return ProviderResult(
            text=f"[MOCK · G0]\n\n{current}\n\n— Mock provider · {len(messages)} messages received. No model API was called.",
            duration_ms=(perf_counter() - started) * 1000,
        )
