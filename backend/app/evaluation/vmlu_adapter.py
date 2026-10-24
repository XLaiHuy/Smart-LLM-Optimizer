import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import TypeAlias

from pydantic import Field, ValidationError

from app.evaluation.cases import (
    DatasetSplit,
    EvalCase,
    EvalModel,
    MCQKey,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    NonBlankString,
    SourceMetadata,
)
from app.evaluation.sources import SourceQualificationRecord

DecodedVMLURow: TypeAlias = Mapping[str, object]

_CHOICE_PREFIX = re.compile(r"^([A-Z])[.)]\s*(.+)$", re.IGNORECASE | re.DOTALL)


class VMLUAdapterError(ValueError):
    pass


class _SourceRow(EvalModel):
    id: NonBlankString
    question: NonBlankString
    choices: tuple[NonBlankString, ...] = Field(min_length=2, max_length=26)
    answer: MCQKey
    subject: NonBlankString | None = None


def _decode_row(row: DecodedVMLURow) -> _SourceRow:
    try:
        return _SourceRow.model_validate(row)
    except ValidationError as exc:
        raise VMLUAdapterError(f"invalid VMLU source row: {exc}") from exc


def _validate_source_record(record: SourceQualificationRecord) -> None:
    if record.task_family != "multidisciplinary_mcq" or record.language != "vi":
        raise VMLUAdapterError("VMLU adapter requires a Vietnamese MCQ source record")

    if record.qualification_status == "rejected" or record.decision == "REJECTED":
        raise VMLUAdapterError("rejected VMLU source cannot be adapted")

    if not any(source_file.has_gold_answers for source_file in record.candidate_mirror.files):
        raise VMLUAdapterError("VMLU source record does not declare any gradeable rows")


def _option_text(*, choice: str, expected_key: str) -> str:
    match = _CHOICE_PREFIX.match(choice.strip())

    if match is None:
        return choice.strip()

    observed_key, text = match.groups()
    if observed_key.upper() != expected_key:
        raise VMLUAdapterError(
            f"choice prefix {observed_key!r} does not match expected option {expected_key!r}"
        )

    return text.strip()


def _group_id(*, question: str, options: tuple[MCQOption, ...]) -> str:
    identity = json.dumps(
        {
            "question": question.strip(),
            "choices": [option.text.strip() for option in options],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"vmlu:{digest}"


def _adapt_decoded_row(
    *,
    row: _SourceRow,
    source_record: SourceQualificationRecord,
    split: DatasetSplit,
) -> EvalCase:
    if split == "smoke":
        raise VMLUAdapterError("public VMLU rows must use dev or holdout")

    option_keys = tuple(chr(ord("A") + index) for index in range(len(row.choices)))
    if row.answer not in option_keys:
        raise VMLUAdapterError("VMLU answer key does not match a visible option")

    options = tuple(
        MCQOption(
            key=key,
            text=_option_text(
                choice=choice,
                expected_key=key,
            ),
        )
        for key, choice in zip(option_keys, row.choices, strict=True)
    )

    tags = ("vmlu",) if row.subject is None else ("vmlu", f"subject:{row.subject}")

    return EvalCase(
        case_id=f"{source_record.source_id}:{row.id}",
        task_family="multidisciplinary_mcq",
        source=SourceMetadata(
            suite_name=source_record.suite_name,
            source_name=source_record.source_id,
            source_revision=source_record.candidate_mirror.repository_revision,
            source_record_id=row.id,
            group_id=_group_id(
                question=row.question,
                options=options,
            ),
            split=split,
            language=source_record.language,
            qualification_status=source_record.qualification_status,
            license_id=source_record.official_source.dataset_license,
        ),
        serving_input=MCQServingInput(
            question=row.question,
            options=options,
        ),
        evaluator_target=MCQTarget(
            answer_key=row.answer,
        ),
        tags=tags,
    )


def adapt_vmlu_row(
    *,
    row: DecodedVMLURow,
    source_record: SourceQualificationRecord,
    split: DatasetSplit,
) -> EvalCase:
    _validate_source_record(source_record)
    return _adapt_decoded_row(
        row=_decode_row(row),
        source_record=source_record,
        split=split,
    )


def adapt_vmlu_rows(
    *,
    rows: Iterable[DecodedVMLURow],
    source_record: SourceQualificationRecord,
    split_by_source_record_id: Mapping[str, DatasetSplit],
) -> tuple[EvalCase, ...]:
    _validate_source_record(source_record)

    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    split_by_group_id: dict[str, DatasetSplit] = {}

    for raw_row in rows:
        row = _decode_row(raw_row)
        if row.id in seen_ids:
            raise VMLUAdapterError(f"duplicate VMLU source record ID: {row.id!r}")

        split = split_by_source_record_id.get(row.id)
        if split is None:
            raise VMLUAdapterError(
                f"missing frozen split assignment for VMLU source record ID: {row.id!r}"
            )

        case = _adapt_decoded_row(
            row=row,
            source_record=source_record,
            split=split,
        )
        previous_split = split_by_group_id.setdefault(case.source.group_id, split)
        if previous_split != split:
            raise VMLUAdapterError("duplicate VMLU content must not span multiple frozen splits")

        cases.append(case)
        seen_ids.add(row.id)

    if not cases:
        raise VMLUAdapterError("VMLU rows must not be empty")

    unexpected = sorted(set(split_by_source_record_id) - seen_ids)
    if unexpected:
        raise VMLUAdapterError(
            f"VMLU split assignments contain unknown source record IDs: {unexpected!r}"
        )

    return tuple(cases)
