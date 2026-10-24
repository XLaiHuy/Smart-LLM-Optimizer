from app.contracts.dtos import Message, SessionSnapshot, Summary
from app.optimizers.context_summarizer import ContextSummarizer, SummaryValidator


def source_snapshot() -> tuple[SessionSnapshot, tuple[Message, ...]]:
    messages = (
        Message(role="user", id="m1", content="Tôi ở Huế."),
        Message(role="assistant", id="m2", content="Đã ghi nhận."),
    )
    return (
        SessionSnapshot(owner_user_id="u1", session_id="s1", revision=3, raw_turns=messages),
        messages,
    )


async def test_valid_summary_is_returned() -> None:
    snapshot, messages = source_snapshot()

    async def generate(source: tuple[Message, ...], revision: int) -> Summary:
        return Summary(
            revision=revision,
            content="Người dùng ở Huế.",
            covered_message_ids=tuple(message.id for message in source if message.id),
        )

    result = await ContextSummarizer(generate).summarize(snapshot, messages)

    assert result is not None
    assert result.covered_message_ids == ("m1", "m2")


async def test_invalid_summary_falls_back_to_none() -> None:
    snapshot, messages = source_snapshot()

    async def generate(source: tuple[Message, ...], revision: int) -> Summary:
        return Summary(
            revision=revision,
            content="Summary",
            covered_message_ids=("not-committed",),
        )

    assert await ContextSummarizer(generate).summarize(snapshot, messages) is None


def test_validator_rejects_duplicate_coverage() -> None:
    snapshot, messages = source_snapshot()
    summary = Summary(revision=3, content="x", covered_message_ids=("m1", "m1"))

    assert SummaryValidator.validate(summary, messages, snapshot.revision) is False
