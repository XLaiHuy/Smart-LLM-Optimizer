from collections.abc import Iterable, Mapping
from typing import Literal, TypeAlias

from pydantic import Field, ValidationError

from app.evaluation.cases import (
    ConversationTurn,
    DatasetSplit,
    EvalCase,
    EvalModel,
    MemoryProbeType,
    MemoryServingInput,
    MemoryTarget,
    NonBlankString,
    ReviewStatus,
    SourceMetadata,
)

VI_DIALOG_MEMORY_PROTOCOL_VERSION = "vi-dialog-memory-probes-v1"

DecodedViDialogRow: TypeAlias = Mapping[str, object]


class ViDialogAdapterError(ValueError):
    pass


class ViDialogCandidateSource(EvalModel):
    source_id: NonBlankString
    suite_name: NonBlankString = "vi-dialog-memory"
    source_name: NonBlankString
    source_revision: NonBlankString
    language: Literal["vi"] = "vi"
    qualification_status: Literal["candidate"] = "candidate"


class _TurnRow(EvalModel):
    turn_id: NonBlankString
    turn_index: int = Field(ge=0)
    role: Literal["user", "assistant"]
    content: NonBlankString
    speaker: NonBlankString | None = None


class _ProbeRow(EvalModel):
    probe_id: NonBlankString
    checkpoint: int = Field(ge=0)
    question: NonBlankString
    gold_answers: tuple[NonBlankString, ...] = Field(min_length=1)
    evidence_turn_ids: tuple[NonBlankString, ...] = ()
    probe_type: MemoryProbeType
    protocol_version: NonBlankString
    annotator: NonBlankString | None = None
    reviewer: NonBlankString | None = None
    review_status: ReviewStatus = "draft"


class _SourceRow(EvalModel):
    conversation_id: NonBlankString
    turns: tuple[_TurnRow, ...] = Field(min_length=1)
    probes: tuple[_ProbeRow, ...] = Field(min_length=1)


def _decode_row(row: DecodedViDialogRow) -> _SourceRow:
    try:
        return _SourceRow.model_validate(row)
    except ValidationError as exc:
        raise ViDialogAdapterError(f"invalid Vi-Dialog source row: {exc}") from exc


def _turns(row: _SourceRow) -> tuple[ConversationTurn, ...]:
    converted = tuple(
        ConversationTurn(
            turn_id=turn.turn_id,
            turn_index=turn.turn_index,
            role=turn.role,
            content=turn.content,
            speaker=turn.speaker,
        )
        for turn in row.turns
    )

    indexes = tuple(turn.turn_index for turn in converted)
    if any(current <= previous for previous, current in zip(indexes, indexes[1:], strict=False)):
        raise ViDialogAdapterError("Vi-Dialog turn indexes must be strictly increasing")

    turn_ids = tuple(turn.turn_id for turn in converted)
    if len(turn_ids) != len(set(turn_ids)):
        raise ViDialogAdapterError("Vi-Dialog turn IDs must be unique")

    return converted


def _adapt_probe(
    *,
    source_row: _SourceRow,
    turns: tuple[ConversationTurn, ...],
    probe: _ProbeRow,
    source: ViDialogCandidateSource,
    split: DatasetSplit,
) -> EvalCase:
    if probe.protocol_version != VI_DIALOG_MEMORY_PROTOCOL_VERSION:
        raise ViDialogAdapterError("Vi-Dialog probe protocol version is not supported")

    visible_turns = tuple(turn for turn in turns if turn.turn_index <= probe.checkpoint)
    if not visible_turns:
        raise ViDialogAdapterError("Vi-Dialog probe checkpoint has no visible turns")

    visible_ids = {turn.turn_id for turn in visible_turns}
    unknown_evidence = set(probe.evidence_turn_ids) - visible_ids
    if unknown_evidence:
        raise ViDialogAdapterError(
            "Vi-Dialog probe evidence must exist at or before the checkpoint"
        )

    return EvalCase(
        case_id=(f"{source.source_id}:{source_row.conversation_id}:{probe.probe_id}"),
        task_family="conversation_memory",
        source=SourceMetadata(
            suite_name=source.suite_name,
            source_name=source.source_name,
            source_revision=source.source_revision,
            source_record_id=(f"{source_row.conversation_id}:{probe.probe_id}"),
            group_id=source_row.conversation_id,
            split=split,
            language=source.language,
            qualification_status=source.qualification_status,
            license_id=None,
        ),
        serving_input=MemoryServingInput(
            turns=visible_turns,
            checkpoint=probe.checkpoint,
            question=probe.question,
        ),
        evaluator_target=MemoryTarget(
            gold_answers=probe.gold_answers,
            evidence_turn_ids=probe.evidence_turn_ids,
            probe_type=probe.probe_type,
            protocol_version=probe.protocol_version,
            annotator=probe.annotator,
            reviewer=probe.reviewer,
            review_status=probe.review_status,
        ),
        tags=("vi-dialog", f"probe:{probe.probe_type}"),
    )


def _adapt_decoded_row(
    *,
    row: _SourceRow,
    source: ViDialogCandidateSource,
    split: DatasetSplit,
) -> tuple[EvalCase, ...]:
    if split == "smoke":
        raise ViDialogAdapterError("public Vi-Dialog rows must use dev or holdout")

    turns = _turns(row)
    probe_ids = tuple(probe.probe_id for probe in row.probes)
    if len(probe_ids) != len(set(probe_ids)):
        raise ViDialogAdapterError("Vi-Dialog probe IDs must be unique within a conversation")

    return tuple(
        _adapt_probe(
            source_row=row,
            turns=turns,
            probe=probe,
            source=source,
            split=split,
        )
        for probe in row.probes
    )


def adapt_vi_dialog_row(
    *,
    row: DecodedViDialogRow,
    source: ViDialogCandidateSource,
    split: DatasetSplit,
) -> tuple[EvalCase, ...]:
    return _adapt_decoded_row(
        row=_decode_row(row),
        source=source,
        split=split,
    )


def adapt_vi_dialog_rows(
    *,
    rows: Iterable[DecodedViDialogRow],
    source: ViDialogCandidateSource,
    split_by_conversation_id: Mapping[str, DatasetSplit],
) -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    seen_conversation_ids: set[str] = set()

    for raw_row in rows:
        row = _decode_row(raw_row)
        if row.conversation_id in seen_conversation_ids:
            raise ViDialogAdapterError(
                f"duplicate Vi-Dialog conversation ID: {row.conversation_id!r}"
            )

        split = split_by_conversation_id.get(row.conversation_id)
        if split is None:
            raise ViDialogAdapterError(
                "missing frozen split assignment for Vi-Dialog conversation ID: "
                f"{row.conversation_id!r}"
            )

        cases.extend(
            _adapt_decoded_row(
                row=row,
                source=source,
                split=split,
            )
        )
        seen_conversation_ids.add(row.conversation_id)

    if not cases:
        raise ViDialogAdapterError("Vi-Dialog rows must not be empty")

    unexpected = sorted(set(split_by_conversation_id) - seen_conversation_ids)
    if unexpected:
        raise ViDialogAdapterError(
            f"Vi-Dialog split assignments contain unknown conversation IDs: {unexpected!r}"
        )

    return tuple(cases)
