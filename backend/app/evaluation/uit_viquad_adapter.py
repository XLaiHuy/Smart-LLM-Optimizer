import hashlib
from collections.abc import Iterable, Mapping
from typing import Literal, Self, TypeAlias

from pydantic import ValidationError, model_validator

from app.evaluation.cases import (
    AnswerSpan,
    DatasetSplit,
    EvalCase,
    EvalModel,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    NonBlankString,
    SourceMetadata,
)

DecodedUITViQuADRow: TypeAlias = Mapping[str, object]


class UITViQuADAdapterError(ValueError):
    pass


class UITViQuADCandidateSource(EvalModel):
    source_id: NonBlankString
    suite_name: NonBlankString = "uit-viquad-2"
    source_name: NonBlankString = "taidng/UIT-ViQuAD2.0"
    source_revision: NonBlankString
    language: Literal["vi"] = "vi"
    qualification_status: Literal["candidate"] = "candidate"


class _AnswerBundle(EvalModel):
    text: tuple[NonBlankString, ...] = ()
    answer_start: tuple[int, ...] = ()

    @model_validator(mode="after")
    def require_parallel_values(self) -> Self:
        if len(self.text) != len(self.answer_start):
            raise ValueError("answer text and answer_start must have equal lengths")

        if any(start < 0 for start in self.answer_start):
            raise ValueError("answer_start values must be non-negative")

        return self


class _SourceRow(EvalModel):
    id: NonBlankString
    uit_id: NonBlankString | None = None
    title: NonBlankString
    context: NonBlankString
    question: NonBlankString
    answers: _AnswerBundle
    is_impossible: bool
    plausible_answers: _AnswerBundle | None = None


def _decode_row(row: DecodedUITViQuADRow) -> _SourceRow:
    try:
        return _SourceRow.model_validate(row)
    except ValidationError as exc:
        raise UITViQuADAdapterError(f"invalid UIT-ViQuAD source row: {exc}") from exc


def _spans(bundle: _AnswerBundle | None) -> tuple[AnswerSpan, ...]:
    if bundle is None:
        return ()

    return tuple(
        AnswerSpan(
            text=text,
            answer_start=start,
        )
        for text, start in zip(bundle.text, bundle.answer_start, strict=True)
    )


def _validate_spans(
    *,
    context: str,
    spans: tuple[AnswerSpan, ...],
    field_name: str,
) -> None:
    for span in spans:
        observed = context[span.answer_start : span.answer_start + len(span.text)]
        if observed != span.text:
            raise UITViQuADAdapterError(
                f"{field_name} span does not match context at offset {span.answer_start}"
            )


def _group_id(title: str) -> str:
    digest = hashlib.sha256(title.strip().encode("utf-8")).hexdigest()
    return f"uit-viquad:{digest}"


def _adapt_decoded_row(
    *,
    row: _SourceRow,
    source: UITViQuADCandidateSource,
    split: DatasetSplit,
) -> EvalCase:
    if split == "smoke":
        raise UITViQuADAdapterError("public UIT-ViQuAD rows must use dev or holdout")

    answers = _spans(row.answers)
    plausible_answers = _spans(row.plausible_answers)

    _validate_spans(
        context=row.context,
        spans=answers,
        field_name="gold answer",
    )
    _validate_spans(
        context=row.context,
        spans=plausible_answers,
        field_name="plausible answer",
    )

    if row.is_impossible and answers:
        raise UITViQuADAdapterError("unanswerable UIT-ViQuAD row must not contain gold answers")

    if not row.is_impossible and not answers:
        raise UITViQuADAdapterError("answerable UIT-ViQuAD row must contain gold answers")

    tags = ["uit-viquad", f"title:{row.title}"]
    if row.uit_id is not None:
        tags.append(f"uit-id:{row.uit_id}")

    return EvalCase(
        case_id=f"{source.source_id}:{row.id}",
        task_family="extractive_qa",
        source=SourceMetadata(
            suite_name=source.suite_name,
            source_name=source.source_name,
            source_revision=source.source_revision,
            source_record_id=row.id,
            group_id=_group_id(row.title),
            split=split,
            language=source.language,
            qualification_status=source.qualification_status,
            license_id=None,
        ),
        serving_input=ExtractiveQAServingInput(
            context=row.context,
            question=row.question,
        ),
        evaluator_target=ExtractiveQATarget(
            answers=answers,
            plausible_answers=plausible_answers,
            is_impossible=row.is_impossible,
        ),
        tags=tuple(tags),
    )


def adapt_uit_viquad_row(
    *,
    row: DecodedUITViQuADRow,
    source: UITViQuADCandidateSource,
    split: DatasetSplit,
) -> EvalCase:
    return _adapt_decoded_row(
        row=_decode_row(row),
        source=source,
        split=split,
    )


def adapt_uit_viquad_rows(
    *,
    rows: Iterable[DecodedUITViQuADRow],
    source: UITViQuADCandidateSource,
    split_by_source_record_id: Mapping[str, DatasetSplit],
) -> tuple[EvalCase, ...]:
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    split_by_group_id: dict[str, DatasetSplit] = {}

    for raw_row in rows:
        row = _decode_row(raw_row)
        if row.id in seen_ids:
            raise UITViQuADAdapterError(f"duplicate UIT-ViQuAD source record ID: {row.id!r}")

        split = split_by_source_record_id.get(row.id)
        if split is None:
            raise UITViQuADAdapterError(
                f"missing frozen split assignment for UIT-ViQuAD source record ID: {row.id!r}"
            )

        case = _adapt_decoded_row(
            row=row,
            source=source,
            split=split,
        )
        previous_split = split_by_group_id.setdefault(case.source.group_id, split)
        if previous_split != split:
            raise UITViQuADAdapterError(
                "UIT-ViQuAD document group must not span multiple frozen splits"
            )

        cases.append(case)
        seen_ids.add(row.id)

    if not cases:
        raise UITViQuADAdapterError("UIT-ViQuAD rows must not be empty")

    unexpected = sorted(set(split_by_source_record_id) - seen_ids)
    if unexpected:
        raise UITViQuADAdapterError(
            f"UIT-ViQuAD split assignments contain unknown source record IDs: {unexpected!r}"
        )

    return tuple(cases)
