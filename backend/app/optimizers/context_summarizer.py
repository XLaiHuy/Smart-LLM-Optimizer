"""Summary generation and validation ports for context optimization."""

from collections.abc import Awaitable, Callable

from app.contracts.dtos import Message, SessionSnapshot, Summary

SummaryGenerator = Callable[[tuple[Message, ...], int], Awaitable[Summary | None]]


def extractive_summary_generator(*, max_characters: int = 900) -> SummaryGenerator:
    """Return a no-cost summary generator for runtime context compaction.

    It only quotes compact excerpts from committed messages; it never invents
    facts. A model-based generator can replace this dependency later.
    """
    if max_characters <= 0:
        raise ValueError("max_characters must be positive")

    async def generate(messages: tuple[Message, ...], revision: int) -> Summary | None:
        covered_ids = tuple(message.id for message in messages if message.id is not None)
        if not covered_ids:
            return None

        lines: list[str] = []
        used = 0
        for message in messages:
            content = " ".join(message.content.split())
            if not content:
                continue
            excerpt = content[:240].rstrip()
            if len(content) > len(excerpt):
                excerpt += "…"
            line = f"- {message.role}: {excerpt}"
            if used + len(line) > max_characters:
                break
            lines.append(line)
            used += len(line)

        if not lines:
            return None
        return Summary(
            revision=revision,
            content="\n".join(lines),
            covered_message_ids=covered_ids,
        )

    return generate


class SummaryValidator:
    """Validate that a summary is tied to the current committed snapshot."""

    @staticmethod
    def validate(
        summary: Summary,
        source_messages: tuple[Message, ...],
        revision: int,
    ) -> bool:
        if summary.revision != revision or not summary.content.strip():
            return False

        source_ids = {message.id for message in source_messages if message.id is not None}
        covered_ids = summary.covered_message_ids
        return (
            bool(covered_ids)
            and len(set(covered_ids)) == len(covered_ids)
            and set(covered_ids).issubset(source_ids)
        )


class ContextSummarizer:
    """Generate a validated summary through an injected async dependency."""

    def __init__(self, generator: SummaryGenerator | None = None) -> None:
        self.generator = generator

    async def summarize(
        self,
        snapshot: SessionSnapshot,
        messages: tuple[Message, ...],
    ) -> Summary | None:
        if self.generator is None or not messages:
            return None

        summary = await self.generator(messages, snapshot.revision)
        if summary is None:
            return None
        if not SummaryValidator.validate(summary, messages, snapshot.revision):
            return None
        return summary
