from collections.abc import Iterable, Mapping
from typing import TypeAlias

from pydantic import Field, ValidationError

from app.evaluation.cases import (
    DatasetSplit,
    EvalCase,
    EvalModel,
    InstructionArgument,
    InstructionRule,
    InstructionScalar,
    InstructionServingInput,
    InstructionTarget,
    InstructionValue,
    NonBlankString,
    SourceMetadata,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
    SeaIFEvalConfigurationError,
    validate_sea_ifeval_rule,
)
from app.evaluation.sources import (
    InstructionSourceQualificationRecord,
)

DecodedSeaIFEvalRow: TypeAlias = Mapping[str, object]


class SeaIFEvalAdapterError(ValueError):
    pass


class _PromptRecord(EvalModel):
    text: NonBlankString


class _MetadataRecord(EvalModel):
    category: NonBlankString
    language: NonBlankString
    subcategory: NonBlankString


class _SourceRow(EvalModel):
    id: NonBlankString
    prompts: tuple[_PromptRecord, ...] = Field(
        min_length=1,
        max_length=1,
    )
    metadata: _MetadataRecord
    kwargs: tuple[
        dict[NonBlankString, object],
        ...,
    ] = Field(
        min_length=1,
        max_length=1,
    )


def _decode_row(
    row: DecodedSeaIFEvalRow,
) -> _SourceRow:
    try:
        return _SourceRow.model_validate(row)
    except ValidationError as exc:
        raise SeaIFEvalAdapterError(f"invalid SEA-IFEval source row: {exc}") from exc


def _convert_scalar(
    value: object,
    *,
    path: str,
) -> InstructionScalar:
    if value is None or isinstance(
        value,
        str | int | float | bool,
    ):
        return value

    raise SeaIFEvalAdapterError(f"{path} contains an unsupported value type")


def _convert_argument_value(
    value: object,
    *,
    path: str,
) -> InstructionValue:
    if isinstance(value, list | tuple):
        return tuple(
            _convert_scalar(
                item,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        )

    return _convert_scalar(
        value,
        path=path,
    )


def _validate_source_record(
    record: InstructionSourceQualificationRecord,
) -> None:
    if record.language != "vi" or record.dataset_source.config_name != "vi":
        raise SeaIFEvalAdapterError("SEA-IFEval adapter currently supports only config vi")

    if record.dataset_source.split_name != "eval":
        raise SeaIFEvalAdapterError("SEA-IFEval source split must be eval")

    if record.qualification_status == "rejected" or record.decision == "REJECTED":
        raise SeaIFEvalAdapterError("rejected SEA-IFEval source cannot be adapted")

    if record.observed_schema.evaluator_version != SEA_IFEVAL_GRADER_VERSION:
        raise SeaIFEvalAdapterError("SEA-IFEval evaluator version does not match the pinned grader")


def _adapt_decoded_row(
    *,
    row: _SourceRow,
    source_record: InstructionSourceQualificationRecord,
    split: DatasetSplit,
) -> EvalCase:
    if split == "smoke":
        raise SeaIFEvalAdapterError("public SEA-IFEval rows must use dev or holdout")

    if row.metadata.language != source_record.language:
        raise SeaIFEvalAdapterError("row language does not match source qualification")

    if not row.metadata.subcategory.startswith(f"{row.metadata.category}:"):
        raise SeaIFEvalAdapterError("instruction subcategory does not match category")

    arguments = tuple(
        InstructionArgument(
            name=name,
            value=_convert_argument_value(
                value,
                path=f"row.kwargs[0].{name}",
            ),
        )
        for name, value in sorted(row.kwargs[0].items())
        if value is not None
    )

    rule = InstructionRule(
        instruction_id=row.metadata.subcategory,
        kwargs=arguments,
    )

    try:
        validate_sea_ifeval_rule(rule)
    except SeaIFEvalConfigurationError as exc:
        raise SeaIFEvalAdapterError(
            f"invalid SEA-IFEval rule for source record {row.id!r}: {exc}"
        ) from exc

    return EvalCase(
        case_id=(f"{source_record.source_id}:{row.id}"),
        task_family="instruction",
        source=SourceMetadata(
            suite_name=source_record.suite_name,
            source_name=source_record.source_id,
            source_revision=(source_record.dataset_source.dataset_revision),
            source_record_id=row.id,
            group_id=row.id,
            split=split,
            language=row.metadata.language,
            qualification_status=(source_record.qualification_status),
            license_id=(source_record.official_source.dataset_license),
        ),
        serving_input=InstructionServingInput(
            prompt=row.prompts[0].text,
        ),
        evaluator_target=InstructionTarget(
            rules=(rule,),
            evaluator_version=(SEA_IFEVAL_GRADER_VERSION),
        ),
        tags=("sea-ifeval",),
    )


def adapt_sea_ifeval_row(
    *,
    row: DecodedSeaIFEvalRow,
    source_record: InstructionSourceQualificationRecord,
    split: DatasetSplit,
) -> EvalCase:
    _validate_source_record(source_record)

    return _adapt_decoded_row(
        row=_decode_row(row),
        source_record=source_record,
        split=split,
    )


def adapt_sea_ifeval_rows(
    *,
    rows: Iterable[DecodedSeaIFEvalRow],
    source_record: InstructionSourceQualificationRecord,
    split_by_source_record_id: Mapping[
        str,
        DatasetSplit,
    ],
) -> tuple[EvalCase, ...]:
    _validate_source_record(source_record)

    cases: list[EvalCase] = []
    seen_source_record_ids: set[str] = set()

    for raw_row in rows:
        row = _decode_row(raw_row)

        if row.id in seen_source_record_ids:
            raise SeaIFEvalAdapterError(f"duplicate SEA-IFEval source record ID: {row.id!r}")

        split = split_by_source_record_id.get(row.id)

        if split is None:
            raise SeaIFEvalAdapterError(
                f"missing frozen split assignment for source record ID: {row.id!r}"
            )

        cases.append(
            _adapt_decoded_row(
                row=row,
                source_record=source_record,
                split=split,
            )
        )
        seen_source_record_ids.add(row.id)

    if not cases:
        raise SeaIFEvalAdapterError("SEA-IFEval rows must not be empty")

    unexpected_assignments = sorted(set(split_by_source_record_id) - seen_source_record_ids)

    if unexpected_assignments:
        raise SeaIFEvalAdapterError(
            f"split assignments contain unknown source record IDs: {unexpected_assignments!r}"
        )

    return tuple(cases)
