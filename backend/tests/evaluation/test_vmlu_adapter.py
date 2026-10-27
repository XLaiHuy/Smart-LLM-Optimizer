from pathlib import Path

import pytest

from app.evaluation.cases import MCQServingInput, MCQTarget
from app.evaluation.dispatcher import grade_case
from app.evaluation.sources import SourceQualificationRecord, load_source_qualification
from app.evaluation.vmlu_adapter import (
    VMLUAdapterError,
    adapt_vmlu_row,
    adapt_vmlu_rows,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE_RECORD_PATH = ROOT / "benchmark" / "sources" / "vmlu_vi_mqa_v1_5.qualification.json"


def _source_record() -> SourceQualificationRecord:
    record = load_source_qualification(SOURCE_RECORD_PATH)
    assert isinstance(record, SourceQualificationRecord)
    return record


def _row(
    *,
    record_id: str = "28-0001",
    question: str = "Hai cộng hai bằng bao nhiêu?",
) -> dict[str, object]:
    return {
        "id": record_id,
        "question": question,
        "choices": ["A. 3", "B. 4", "C. 5"],
        "answer": "B",
        "subject": "toan",
    }


def test_adapts_vmlu_without_leaking_answer() -> None:
    case = adapt_vmlu_row(
        row=_row(),
        source_record=_source_record(),
        split="dev",
    )

    assert case.case_id == "vmlu-vi-mqa-v1-5:28-0001"
    assert case.source.qualification_status == "candidate"
    assert case.source.license_id is None
    assert case.source.group_id.startswith("vmlu:")
    assert case.tags == ("vmlu", "subject:toan")

    assert isinstance(case.serving_input, MCQServingInput)
    assert isinstance(case.evaluator_target, MCQTarget)
    assert tuple(option.key for option in case.serving_input.options) == ("A", "B", "C")
    assert tuple(option.text for option in case.serving_input.options) == ("3", "4", "5")
    assert case.evaluator_target.answer_key == "B"

    serving_payload = case.serving_input.model_dump(mode="json")
    assert "answer" not in serving_payload
    assert "answer_key" not in serving_payload

    grade = grade_case(case=case, prediction="B")
    assert grade.passed is True
    assert grade.reason == "correct"


def test_batch_requires_exact_split_coverage() -> None:
    cases = adapt_vmlu_rows(
        rows=(
            _row(record_id="28-0001"),
            _row(
                record_id="28-0002",
                question="Ba cộng một bằng bao nhiêu?",
            ),
        ),
        source_record=_source_record(),
        split_by_source_record_id={
            "28-0001": "dev",
            "28-0002": "holdout",
        },
    )

    assert tuple(case.source.split for case in cases) == ("dev", "holdout")


def test_rejects_duplicate_content_across_splits() -> None:
    with pytest.raises(VMLUAdapterError, match="must not span"):
        adapt_vmlu_rows(
            rows=(_row(record_id="28-0001"), _row(record_id="28-0002")),
            source_record=_source_record(),
            split_by_source_record_id={
                "28-0001": "dev",
                "28-0002": "holdout",
            },
        )


@pytest.mark.parametrize(
    ("row", "message"),
    (
        (
            {
                "id": "bad-answer",
                "question": "Câu hỏi?",
                "choices": ["A. Một", "B. Hai"],
                "answer": "C",
            },
            "answer key",
        ),
        (
            {
                "id": "bad-prefix",
                "question": "Câu hỏi?",
                "choices": ["B. Một", "B. Hai"],
                "answer": "A",
            },
            "choice prefix",
        ),
        (
            {
                "id": "missing-answer",
                "question": "Câu hỏi?",
                "choices": ["A. Một", "B. Hai"],
            },
            "invalid VMLU source row",
        ),
    ),
)
def test_rejects_ungradeable_rows(
    row: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(VMLUAdapterError, match=message):
        adapt_vmlu_row(
            row=row,
            source_record=_source_record(),
            split="dev",
        )


def test_rejects_public_smoke_and_duplicate_ids() -> None:
    with pytest.raises(VMLUAdapterError, match="dev or holdout"):
        adapt_vmlu_row(
            row=_row(),
            source_record=_source_record(),
            split="smoke",
        )

    with pytest.raises(VMLUAdapterError, match="duplicate"):
        adapt_vmlu_rows(
            rows=(_row(), _row()),
            source_record=_source_record(),
            split_by_source_record_id={"28-0001": "dev"},
        )
