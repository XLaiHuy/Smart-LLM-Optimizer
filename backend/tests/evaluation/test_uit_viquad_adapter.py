import pytest

from app.evaluation.cases import ExtractiveQAServingInput, ExtractiveQATarget
from app.evaluation.dispatcher import grade_case
from app.evaluation.uit_viquad_adapter import (
    UITViQuADAdapterError,
    UITViQuADCandidateSource,
    adapt_uit_viquad_row,
    adapt_uit_viquad_rows,
)


def _source() -> UITViQuADCandidateSource:
    return UITViQuADCandidateSource(
        source_id="uit-viquad-2-candidate",
        source_revision="fixture-revision",
    )


def _row(*, record_id: str = "0001-0001-0001") -> dict[str, object]:
    return {
        "id": record_id,
        "uit_id": "uit_000001",
        "title": "Trường Đại học Mở",
        "context": "Khoa học tại Thành phố Hồ Chí Minh.",
        "question": "Địa điểm ở đâu?",
        "answers": {
            "text": ["Thành phố Hồ Chí Minh", "Hồ Chí Minh"],
            "answer_start": [13, 23],
        },
        "is_impossible": False,
        "plausible_answers": None,
    }


def test_adapts_multiple_golds_without_leaking_targets() -> None:
    case = adapt_uit_viquad_row(
        row=_row(),
        source=_source(),
        split="dev",
    )

    assert case.source.qualification_status == "candidate"
    assert case.source.license_id is None
    assert case.source.group_id.startswith("uit-viquad:")
    assert isinstance(case.serving_input, ExtractiveQAServingInput)
    assert isinstance(case.evaluator_target, ExtractiveQATarget)
    assert tuple(answer.text for answer in case.evaluator_target.answers) == (
        "Thành phố Hồ Chí Minh",
        "Hồ Chí Minh",
    )

    serving_payload = case.serving_input.model_dump(mode="json")
    assert "answers" not in serving_payload
    assert "plausible_answers" not in serving_payload
    assert "is_impossible" not in serving_payload

    grade = grade_case(case=case, prediction="Hồ Chí Minh")
    assert grade.passed is True
    assert grade.reason == "exact_match"


def test_preserves_unanswerable_and_plausible_answers() -> None:
    row = _row()
    row["answers"] = {"text": [], "answer_start": []}
    row["is_impossible"] = True
    row["plausible_answers"] = {
        "text": ["Thành phố Hồ Chí Minh"],
        "answer_start": [13],
    }

    case = adapt_uit_viquad_row(
        row=row,
        source=_source(),
        split="holdout",
    )

    assert isinstance(case.evaluator_target, ExtractiveQATarget)
    assert case.evaluator_target.answers == ()
    assert case.evaluator_target.is_impossible is True
    assert tuple(answer.text for answer in case.evaluator_target.plausible_answers) == (
        "Thành phố Hồ Chí Minh",
    )


@pytest.mark.parametrize(
    ("answers", "is_impossible", "message"),
    (
        (
            {"text": ["sai vị trí"], "answer_start": [0]},
            False,
            "does not match context",
        ),
        (
            {"text": [], "answer_start": []},
            False,
            "must contain gold answers",
        ),
        (
            {"text": ["Hồ Chí Minh"], "answer_start": [23]},
            True,
            "must not contain gold answers",
        ),
    ),
)
def test_rejects_invalid_answerability_or_spans(
    answers: dict[str, object],
    is_impossible: bool,
    message: str,
) -> None:
    row = _row()
    row["answers"] = answers
    row["is_impossible"] = is_impossible

    with pytest.raises(UITViQuADAdapterError, match=message):
        adapt_uit_viquad_row(
            row=row,
            source=_source(),
            split="dev",
        )


def test_batch_groups_titles_and_requires_exact_split_coverage() -> None:
    cases = adapt_uit_viquad_rows(
        rows=(_row(record_id="0001-0001-0001"), _row(record_id="0001-0002-0001")),
        source=_source(),
        split_by_source_record_id={
            "0001-0001-0001": "dev",
            "0001-0002-0001": "dev",
        },
    )

    assert cases[0].source.group_id == cases[1].source.group_id

    with pytest.raises(UITViQuADAdapterError, match="unknown source record"):
        adapt_uit_viquad_rows(
            rows=(_row(),),
            source=_source(),
            split_by_source_record_id={
                "0001-0001-0001": "dev",
                "unknown": "holdout",
            },
        )


def test_rejects_document_group_across_splits() -> None:
    with pytest.raises(UITViQuADAdapterError, match="must not span"):
        adapt_uit_viquad_rows(
            rows=(
                _row(record_id="0001-0001-0001"),
                _row(record_id="0001-0002-0001"),
            ),
            source=_source(),
            split_by_source_record_id={
                "0001-0001-0001": "dev",
                "0001-0002-0001": "holdout",
            },
        )


def test_rejects_public_smoke_split() -> None:
    with pytest.raises(UITViQuADAdapterError, match="dev or holdout"):
        adapt_uit_viquad_row(
            row=_row(),
            source=_source(),
            split="smoke",
        )
