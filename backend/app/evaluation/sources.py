from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from app.evaluation.cases import (
    EvalModel,
    MCQKey,
    NonBlankString,
    QualificationStatus,
    TaskFamily,
)

Sha256: TypeAlias = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{64}$"),
]

RepositoryRevision: TypeAlias = Annotated[
    str,
    Field(pattern=(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")),
]

PositiveInteger: TypeAlias = Annotated[
    int,
    Field(gt=0),
]

NonNegativeInteger: TypeAlias = Annotated[
    int,
    Field(ge=0),
]

SourceDecision: TypeAlias = Literal[
    "QUALIFIED",
    "BLOCKED",
    "REJECTED",
]


class SourceQualificationLoadError(ValueError):
    pass


class SourceNotQualifiedError(ValueError):
    pass


class OfficialSourceEvidence(EvalModel):
    paper_url: NonBlankString
    repository_url: NonBlankString
    repository_revision: RepositoryRevision
    dataset_page_url: NonBlankString
    advertised_dataset_version: NonBlankString
    code_license: NonBlankString | None
    dataset_license: NonBlankString | None


class SourceFileEvidence(EvalModel):
    name: NonBlankString
    rows: PositiveInteger
    has_gold_answers: bool
    sha256: Sha256


class CandidateMirrorEvidence(EvalModel):
    repository_url: NonBlankString
    repository_revision: RepositoryRevision
    declared_license: NonBlankString | None
    declared_citation: NonBlankString | None
    files: tuple[SourceFileEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_file_names(self) -> Self:
        names = tuple(source_file.name for source_file in self.files)

        if len(names) != len(set(names)):
            raise ValueError("candidate mirror file names must not contain duplicates")

        return self


class ObservedSourceSchema(EvalModel):
    gold_rows: tuple[
        NonBlankString,
        ...,
    ] = Field(min_length=1)

    hidden_test_rows: tuple[
        NonBlankString,
        ...,
    ] = Field(min_length=1)

    choice_count_values: tuple[
        PositiveInteger,
        ...,
    ] = Field(min_length=1)

    answer_key_values: tuple[
        MCQKey,
        ...,
    ] = Field(min_length=1)

    subject_field_present: bool
    category_field_present: bool

    @model_validator(mode="after")
    def require_unique_schema_values(self) -> Self:
        if len(self.gold_rows) != len(set(self.gold_rows)):
            raise ValueError("gold_rows must not contain duplicates")

        if len(self.hidden_test_rows) != len(set(self.hidden_test_rows)):
            raise ValueError("hidden_test_rows must not contain duplicates")

        if len(self.choice_count_values) != len(set(self.choice_count_values)):
            raise ValueError("choice_count_values must not contain duplicates")

        if len(self.answer_key_values) != len(set(self.answer_key_values)):
            raise ValueError("answer_key_values must not contain duplicates")

        return self


class SourceAudit(EvalModel):
    total_rows: PositiveInteger
    gold_rows: NonNegativeInteger
    hidden_gold_rows: NonNegativeInteger
    duplicate_ids: NonNegativeInteger
    duplicate_question_groups_exact_text: NonNegativeInteger
    cross_split_exact_payload_duplicate_groups: NonNegativeInteger
    invalid_json_rows: NonNegativeInteger
    blank_required_values: NonNegativeInteger
    answers_outside_visible_options: NonNegativeInteger


class SourceQualificationRecord(EvalModel):
    schema_version: Literal["source-qualification-v1"] = "source-qualification-v1"

    source_id: NonBlankString
    suite_name: NonBlankString
    task_family: TaskFamily
    language: NonBlankString
    qualification_status: QualificationStatus
    decision: SourceDecision
    accessed_at: date

    official_source: OfficialSourceEvidence
    candidate_mirror: CandidateMirrorEvidence
    observed_schema: ObservedSourceSchema
    audit: SourceAudit

    blockers: tuple[NonBlankString, ...] = ()
    permitted_current_use: tuple[
        NonBlankString,
        ...,
    ] = ()
    prohibited_current_use: tuple[
        NonBlankString,
        ...,
    ] = ()
    required_resolution: tuple[
        NonBlankString,
        ...,
    ] = ()

    reviewed_by: NonBlankString | None = None
    reviewed_at: date | None = None

    @model_validator(mode="after")
    def validate_qualification_evidence(self) -> Self:
        file_rows = sum(source_file.rows for source_file in self.candidate_mirror.files)

        if file_rows != self.audit.total_rows:
            raise ValueError("audit total_rows must equal the sum of candidate mirror file rows")

        observed_gold_rows = sum(
            source_file.rows
            for source_file in self.candidate_mirror.files
            if source_file.has_gold_answers
        )

        if observed_gold_rows != self.audit.gold_rows:
            raise ValueError("audit gold_rows must equal the rows in files with gold answers")

        observed_hidden_gold_rows = sum(
            source_file.rows
            for source_file in self.candidate_mirror.files
            if not source_file.has_gold_answers
        )

        if observed_hidden_gold_rows != self.audit.hidden_gold_rows:
            raise ValueError(
                "audit hidden_gold_rows must equal the rows in files without gold answers"
            )

        if self.audit.gold_rows + self.audit.hidden_gold_rows != self.audit.total_rows:
            raise ValueError("audit gold_rows and hidden_gold_rows must sum to total_rows")

        review_fields_are_incomplete = (self.reviewed_by is None) != (self.reviewed_at is None)

        if review_fields_are_incomplete:
            raise ValueError("reviewed_by and reviewed_at must be declared together")

        if self.decision == "QUALIFIED":
            if self.qualification_status != "qualified":
                raise ValueError("QUALIFIED decision requires qualification_status='qualified'")

            if self.official_source.dataset_license is None:
                raise ValueError("QUALIFIED source must declare dataset_license")

            if self.reviewed_by is None:
                raise ValueError("QUALIFIED source must have review evidence")

            if self.blockers:
                raise ValueError("QUALIFIED source must not contain blockers")

            if self.required_resolution:
                raise ValueError("QUALIFIED source must not contain unresolved requirements")

            if self.prohibited_current_use:
                raise ValueError("QUALIFIED source must not contain prohibited current uses")

        if self.decision == "BLOCKED":
            if self.qualification_status != "candidate":
                raise ValueError("BLOCKED source must remain qualification_status='candidate'")

            if not self.blockers:
                raise ValueError("BLOCKED source must explain at least one blocker")

            if not self.required_resolution:
                raise ValueError("BLOCKED source must declare required resolutions")

            if not self.prohibited_current_use:
                raise ValueError("BLOCKED source must declare prohibited current uses")

        if self.decision == "REJECTED":
            if self.qualification_status != "rejected":
                raise ValueError("REJECTED decision requires qualification_status='rejected'")

            if not self.blockers:
                raise ValueError("REJECTED source must explain the rejection reason")

            if self.reviewed_by is None:
                raise ValueError("REJECTED source must have review evidence")

        return self


class InstructionSourceFileEvidence(EvalModel):
    name: NonBlankString
    rows: PositiveInteger
    byte_count: PositiveInteger
    sha256: Sha256


class InstructionDatasetSourceEvidence(EvalModel):
    dataset_url: NonBlankString
    dataset_revision: RepositoryRevision
    config_name: NonBlankString
    split_name: NonBlankString
    file_format: NonBlankString
    declared_license: NonBlankString | None
    declared_citation: NonBlankString | None
    files: tuple[InstructionSourceFileEvidence, ...] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def require_unique_file_names(self) -> Self:
        names = tuple(source_file.name for source_file in self.files)

        if len(names) != len(set(names)):
            raise ValueError("instruction source file names must not contain duplicates")

        return self


class InstructionObservedSourceSchema(EvalModel):
    top_level_fields: tuple[NonBlankString, ...] = Field(
        min_length=1,
    )
    prompt_text_path: NonBlankString
    instruction_id_path: NonBlankString
    instruction_kwargs_path: NonBlankString
    source_language_path: NonBlankString

    prompt_count_values: tuple[PositiveInteger, ...] = Field(
        min_length=1,
    )
    rule_count_values: tuple[PositiveInteger, ...] = Field(
        min_length=1,
    )
    source_language_values: tuple[NonBlankString, ...] = Field(
        min_length=1,
    )
    instruction_ids: tuple[NonBlankString, ...] = Field(
        min_length=1,
    )
    evaluator_version: NonBlankString

    @model_validator(mode="after")
    def require_unique_schema_values(self) -> Self:
        if len(self.top_level_fields) != len(set(self.top_level_fields)):
            raise ValueError("top_level_fields must not contain duplicates")

        if len(self.prompt_count_values) != len(set(self.prompt_count_values)):
            raise ValueError("prompt_count_values must not contain duplicates")

        if len(self.rule_count_values) != len(set(self.rule_count_values)):
            raise ValueError("rule_count_values must not contain duplicates")

        if len(self.source_language_values) != len(set(self.source_language_values)):
            raise ValueError("source_language_values must not contain duplicates")

        if len(self.instruction_ids) != len(set(self.instruction_ids)):
            raise ValueError("instruction_ids must not contain duplicates")

        return self


class InstructionIdCount(EvalModel):
    instruction_id: NonBlankString
    rows: PositiveInteger


class InstructionSourceAudit(EvalModel):
    total_rows: PositiveInteger
    unique_ids: PositiveInteger
    duplicate_id_rows: NonNegativeInteger
    exact_duplicate_prompt_groups: NonNegativeInteger
    invalid_rows: NonNegativeInteger
    blank_id_rows: NonNegativeInteger
    blank_prompt_rows: NonNegativeInteger
    blank_instruction_id_rows: NonNegativeInteger
    missing_required_kwargs_rows: NonNegativeInteger
    unsupported_instruction_id_rows: NonNegativeInteger
    wrong_source_language_rows: NonNegativeInteger
    instruction_id_counts: tuple[
        InstructionIdCount,
        ...,
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_instruction_counts(self) -> Self:
        instruction_ids = tuple(item.instruction_id for item in self.instruction_id_counts)

        if len(instruction_ids) != len(set(instruction_ids)):
            raise ValueError("instruction_id_counts must not contain duplicates")

        return self


class InstructionSourceQualificationRecord(EvalModel):
    schema_version: Literal["instruction-source-qualification-v1"] = (
        "instruction-source-qualification-v1"
    )

    source_id: NonBlankString
    suite_name: NonBlankString
    task_family: Literal["instruction"] = "instruction"
    language: NonBlankString
    qualification_status: QualificationStatus
    decision: SourceDecision
    accessed_at: date

    official_source: OfficialSourceEvidence
    dataset_source: InstructionDatasetSourceEvidence
    observed_schema: InstructionObservedSourceSchema
    audit: InstructionSourceAudit

    blockers: tuple[NonBlankString, ...] = ()
    permitted_current_use: tuple[
        NonBlankString,
        ...,
    ] = ()
    prohibited_current_use: tuple[
        NonBlankString,
        ...,
    ] = ()
    required_resolution: tuple[
        NonBlankString,
        ...,
    ] = ()

    reviewed_by: NonBlankString | None = None
    reviewed_at: date | None = None

    @model_validator(mode="after")
    def validate_qualification_evidence(self) -> Self:
        file_rows = sum(source_file.rows for source_file in self.dataset_source.files)

        if file_rows != self.audit.total_rows:
            raise ValueError("instruction audit total_rows must equal the sum of source file rows")

        observed_id_rows = self.audit.unique_ids + self.audit.duplicate_id_rows

        if observed_id_rows != self.audit.total_rows:
            raise ValueError("instruction unique_ids and duplicate_id_rows must sum to total_rows")

        counted_rows = sum(item.rows for item in self.audit.instruction_id_counts)

        if counted_rows != self.audit.total_rows:
            raise ValueError("instruction_id_counts rows must sum to total_rows")

        counted_instruction_ids = {item.instruction_id for item in self.audit.instruction_id_counts}
        observed_instruction_ids = set(self.observed_schema.instruction_ids)

        if counted_instruction_ids != observed_instruction_ids:
            raise ValueError("instruction_id_counts must match observed instruction_ids")

        if set(self.observed_schema.source_language_values) != {self.language}:
            raise ValueError("observed source languages must match the qualification language")

        review_fields_are_incomplete = (self.reviewed_by is None) != (self.reviewed_at is None)

        if review_fields_are_incomplete:
            raise ValueError("reviewed_by and reviewed_at must be declared together")

        if self.decision == "QUALIFIED":
            if self.qualification_status != "qualified":
                raise ValueError("QUALIFIED decision requires qualification_status='qualified'")

            if self.official_source.dataset_license is None:
                raise ValueError("QUALIFIED source must declare dataset_license")

            if self.reviewed_by is None:
                raise ValueError("QUALIFIED source must have review evidence")

            if self.blockers:
                raise ValueError("QUALIFIED source must not contain blockers")

            if self.required_resolution:
                raise ValueError("QUALIFIED source must not contain unresolved requirements")

            if self.prohibited_current_use:
                raise ValueError("QUALIFIED source must not contain prohibited current uses")

        if self.decision == "BLOCKED":
            if self.qualification_status != "candidate":
                raise ValueError("BLOCKED source must remain qualification_status='candidate'")

            if not self.blockers:
                raise ValueError("BLOCKED source must explain at least one blocker")

            if not self.required_resolution:
                raise ValueError("BLOCKED source must declare required resolutions")

            if not self.prohibited_current_use:
                raise ValueError("BLOCKED source must declare prohibited current uses")

        if self.decision == "REJECTED":
            if self.qualification_status != "rejected":
                raise ValueError("REJECTED decision requires qualification_status='rejected'")

            if not self.blockers:
                raise ValueError("REJECTED source must explain the rejection reason")

            if self.reviewed_by is None:
                raise ValueError("REJECTED source must have review evidence")

        return self


AnySourceQualificationRecord: TypeAlias = Annotated[
    SourceQualificationRecord | InstructionSourceQualificationRecord,
    Field(discriminator="schema_version"),
]

_SOURCE_QUALIFICATION_ADAPTER = TypeAdapter[AnySourceQualificationRecord](
    AnySourceQualificationRecord,  # type: ignore[arg-type]
)


def load_source_qualification(
    path: Path,
) -> AnySourceQualificationRecord:
    try:
        record_text = path.read_text(
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as exc:
        raise SourceQualificationLoadError(
            f"Could not read source qualification record: {path}"
        ) from exc

    try:
        return _SOURCE_QUALIFICATION_ADAPTER.validate_json(record_text)
    except ValidationError as exc:
        raise SourceQualificationLoadError(f"Invalid source qualification record: {exc}") from exc


def require_live_research_qualified(
    record: AnySourceQualificationRecord,
) -> AnySourceQualificationRecord:
    if record.decision != "QUALIFIED" or record.qualification_status != "qualified":
        raise SourceNotQualifiedError(
            f"Source {record.source_id!r} is not "
            "qualified for live research: "
            f"qualification_status="
            f"{record.qualification_status!r}, "
            f"decision={record.decision!r}"
        )

    return record
