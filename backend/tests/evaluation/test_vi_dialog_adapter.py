from typing import cast

import pytest

from app.evaluation.cases import MemoryServingInput, MemoryTarget
from app.evaluation.dispatcher import grade_case
from app.evaluation.vi_dialog_adapter import (
    VI_DIALOG_MEMORY_PROTOCOL_VERSION,
    ViDialogAdapterError,
    ViDialogCandidateSource,
    adapt_vi_dialog_row,
    adapt_vi_dialog_rows,
)


def _source() -> ViDialogCandidateSource:
    return ViDialogCandidateSource(
        source_id="vi-dialog-candidate",
        source_name="candidate-public-release",
        source_revision="fixture-revision",
    )


def _row(*, conversation_id: str = "conversation-001") -> dict[str, object]:
    return {
        "conversation_id": conversation_id,
        "turns": [
            {
                "turn_id": "turn-001",
                "turn_index": 1,
                "role": "user",
                "content": "Tên tôi là Khoa.",
            },
            {
                "turn_id": "turn-002",
                "turn_index": 2,
                "role": "assistant",
                "content": "Tôi đã ghi nhận.",
            },
            {
                "turn_id": "turn-003",
                "turn_index": 3,
                "role": "user",
                "content": "Thông tin xuất hiện sau checkpoint.",
            },
        ],
        "probes": [
            {
                "probe_id": "probe-001",
                "checkpoint": 2,
                "question": "Người dùng tên gì?",
                "gold_answers": ["Khoa"],
                "evidence_turn_ids": ["turn-001"],
                "probe_type": "recall",
                "protocol_version": VI_DIALOG_MEMORY_PROTOCOL_VERSION,
                "annotator": "annotator-1",
                "reviewer": "reviewer-1",
                "review_status": "reviewed",
            }
        ],
    }


def test_adapts_checkpoint_without_future_or_gold_leakage() -> None:
    (case,) = adapt_vi_dialog_row(
        row=_row(),
        source=_source(),
        split="dev",
    )

    assert case.source.group_id == "conversation-001"
    assert case.source.qualification_status == "candidate"
    assert case.source.license_id is None
    assert isinstance(case.serving_input, MemoryServingInput)
    assert isinstance(case.evaluator_target, MemoryTarget)
    assert tuple(turn.turn_id for turn in case.serving_input.turns) == (
        "turn-001",
        "turn-002",
    )
    assert case.evaluator_target.gold_answers == ("Khoa",)
    assert case.evaluator_target.evidence_turn_ids == ("turn-001",)
    assert case.evaluator_target.review_status == "reviewed"

    serving_payload = case.serving_input.model_dump(mode="json")
    assert "turn-003" not in str(serving_payload)
    assert "gold_answers" not in serving_payload
    assert "evidence_turn_ids" not in serving_payload

    grade = grade_case(case=case, prediction="Khoa")
    assert grade.passed is True
    assert grade.reason == "exact_match"


def test_flattens_probes_but_keeps_conversation_group() -> None:
    row = _row()
    probes = list(cast(list[dict[str, object]], row["probes"]))
    probes.append(
        {
            "probe_id": "probe-002",
            "checkpoint": 3,
            "question": "Có đủ thông tin về tuổi không?",
            "gold_answers": ["Không đủ thông tin"],
            "evidence_turn_ids": [],
            "probe_type": "abstention",
            "protocol_version": VI_DIALOG_MEMORY_PROTOCOL_VERSION,
            "review_status": "draft",
        }
    )
    row["probes"] = probes

    cases = adapt_vi_dialog_row(
        row=row,
        source=_source(),
        split="holdout",
    )

    assert len(cases) == 2
    assert {case.source.group_id for case in cases} == {"conversation-001"}


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        ("future-evidence", "at or before the checkpoint"),
        ("wrong-protocol", "protocol version"),
        ("duplicate-turn", "turn IDs must be unique"),
    ),
)
def test_rejects_invalid_probe_or_conversation(
    mutate: str,
    message: str,
) -> None:
    row = _row()
    turns = list(cast(list[dict[str, object]], row["turns"]))
    probes = list(cast(list[dict[str, object]], row["probes"]))

    if mutate == "future-evidence":
        probes[0] = {**probes[0], "evidence_turn_ids": ["turn-003"]}
    elif mutate == "wrong-protocol":
        probes[0] = {**probes[0], "protocol_version": "unknown"}
    else:
        turns[1] = {**turns[1], "turn_id": "turn-001"}

    row["turns"] = turns
    row["probes"] = probes

    with pytest.raises(ViDialogAdapterError, match=message):
        adapt_vi_dialog_row(
            row=row,
            source=_source(),
            split="dev",
        )


def test_batch_splits_by_conversation_and_requires_exact_coverage() -> None:
    cases = adapt_vi_dialog_rows(
        rows=(
            _row(conversation_id="conversation-001"),
            _row(conversation_id="conversation-002"),
        ),
        source=_source(),
        split_by_conversation_id={
            "conversation-001": "dev",
            "conversation-002": "holdout",
        },
    )

    assert tuple(case.source.split for case in cases) == ("dev", "holdout")

    with pytest.raises(ViDialogAdapterError, match="unknown conversation"):
        adapt_vi_dialog_rows(
            rows=(_row(),),
            source=_source(),
            split_by_conversation_id={
                "conversation-001": "dev",
                "unknown": "holdout",
            },
        )


def test_rejects_public_smoke_split() -> None:
    with pytest.raises(ViDialogAdapterError, match="dev or holdout"):
        adapt_vi_dialog_row(
            row=_row(),
            source=_source(),
            split="smoke",
        )
