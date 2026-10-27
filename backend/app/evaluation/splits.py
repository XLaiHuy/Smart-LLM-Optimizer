from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Literal, Self, TypeAlias

from pydantic import Field, ValidationError, model_validator

from app.evaluation.cases import (
    EvalModel,
    NonBlankString,
)
from app.evaluation.sources import (
    InstructionSourceQualificationRecord,
    RepositoryRevision,
    Sha256,
)

ResearchSplit: TypeAlias = Literal[
    "dev",
    "holdout",
]


class SourceSplitLoadError(ValueError):
    pass


class SourceSplitValidationError(ValueError):
    pass


class SplitAssignment(EvalModel):
    source_record_id: NonBlankString
    instruction_id: NonBlankString
    split: ResearchSplit


class ReserveRecord(EvalModel):
    source_record_id: NonBlankString
    instruction_id: NonBlankString


def _selection_digest(
    *,
    seed: str,
    instruction_id: str,
    source_record_id: str,
) -> str:
    payload = f"{seed}\0{instruction_id}\0{source_record_id}"

    return sha256(payload.encode("utf-8")).hexdigest()


class SourceSplitRecord(EvalModel):
    schema_version: Literal["eval-source-split-v1"] = "eval-source-split-v1"

    split_id: NonBlankString
    source_id: NonBlankString
    source_revision: RepositoryRevision
    source_file_sha256: Sha256

    qualification_status: Literal[
        "candidate",
        "qualified",
    ]

    selection_algorithm: Literal["sha256-per-instruction-v1"]
    selection_seed: NonBlankString
    selection_rule: NonBlankString
    selection_rationale: NonBlankString

    holdout_status: Literal["frozen_not_blind_public_source"]
    holdout_use_policy: NonBlankString

    source_record_count: int = Field(gt=0)
    selected_record_count: int = Field(gt=0)
    reserve_record_count: int = Field(ge=0)

    assignments: tuple[
        SplitAssignment,
        ...,
    ] = Field(min_length=1)

    reserve: tuple[
        ReserveRecord,
        ...,
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_frozen_split(self) -> Self:
        if len(self.assignments) != self.selected_record_count:
            raise ValueError("selected_record_count must match the number of assignments")

        if len(self.reserve) != self.reserve_record_count:
            raise ValueError("reserve_record_count must match the number of reserve records")

        if self.selected_record_count + self.reserve_record_count != self.source_record_count:
            raise ValueError("selected and reserve counts must sum to source_record_count")

        all_record_ids = tuple(item.source_record_id for item in self.assignments) + tuple(
            item.source_record_id for item in self.reserve
        )

        if len(all_record_ids) != len(set(all_record_ids)):
            raise ValueError("source record IDs must be unique across assignments and reserve")

        selected_instruction_ids = {item.instruction_id for item in self.assignments}

        reserve_instruction_ids = {item.instruction_id for item in self.reserve}

        if selected_instruction_ids != reserve_instruction_ids:
            raise ValueError("selected and reserve instruction IDs must match")

        for instruction_id in sorted(selected_instruction_ids):
            instruction_assignments = tuple(
                item for item in self.assignments if (item.instruction_id == instruction_id)
            )

            instruction_reserve = tuple(
                item for item in self.reserve if (item.instruction_id == instruction_id)
            )

            observed_splits = sorted(item.split for item in instruction_assignments)

            if observed_splits != [
                "dev",
                "holdout",
            ]:
                raise ValueError(
                    "each instruction ID must have exactly one DEV and one HOLDOUT assignment"
                )

            if len(instruction_reserve) != 3:
                raise ValueError("each instruction ID must have exactly three reserve records")

            instruction_record_ids = tuple(
                item.source_record_id for item in instruction_assignments
            ) + tuple(item.source_record_id for item in instruction_reserve)

            ranked_record_ids = sorted(
                instruction_record_ids,
                key=lambda source_record_id: (
                    _selection_digest(
                        seed=self.selection_seed,
                        instruction_id=(instruction_id),
                        source_record_id=(source_record_id),
                    ),
                    source_record_id,
                ),
            )

            expected_assignments: dict[
                str,
                ResearchSplit,
            ] = {
                ranked_record_ids[0]: "dev",
                ranked_record_ids[1]: "holdout",
            }

            observed_assignments = {
                item.source_record_id: item.split for item in instruction_assignments
            }

            if observed_assignments != expected_assignments:
                raise ValueError(
                    "assignments do not match the deterministic SHA-256 selection algorithm"
                )

        return self

    def split_by_source_record_id(
        self,
    ) -> dict[str, ResearchSplit]:
        return {item.source_record_id: item.split for item in self.assignments}


def load_source_split(
    path: Path,
) -> SourceSplitRecord:
    try:
        record_text = path.read_text(
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as exc:
        raise SourceSplitLoadError(f"Could not read source split: {path}") from exc

    try:
        return SourceSplitRecord.model_validate_json(record_text)
    except ValidationError as exc:
        raise SourceSplitLoadError(f"Invalid source split record: {exc}") from exc


def validate_instruction_source_split(
    *,
    split_record: SourceSplitRecord,
    source_record: (InstructionSourceQualificationRecord),
) -> dict[str, ResearchSplit]:
    if split_record.source_id != source_record.source_id:
        raise SourceSplitValidationError("split source_id does not match source qualification")

    if split_record.source_revision != source_record.dataset_source.dataset_revision:
        raise SourceSplitValidationError(
            "split source revision does not match source qualification"
        )

    source_file_hashes = {source_file.sha256 for source_file in source_record.dataset_source.files}

    if split_record.source_file_sha256 not in source_file_hashes:
        raise SourceSplitValidationError(
            "split source file SHA-256 does not match source qualification"
        )

    if split_record.source_record_count != source_record.audit.total_rows:
        raise SourceSplitValidationError(
            "split source record count does not match source qualification"
        )

    if split_record.qualification_status != source_record.qualification_status:
        raise SourceSplitValidationError(
            "split qualification status does not match source qualification"
        )

    expected_instruction_counts = {
        item.instruction_id: item.rows for item in source_record.audit.instruction_id_counts
    }

    observed_instruction_counts = Counter(item.instruction_id for item in split_record.assignments)

    observed_instruction_counts.update(item.instruction_id for item in split_record.reserve)

    if dict(observed_instruction_counts) != expected_instruction_counts:
        raise SourceSplitValidationError(
            "split instruction counts do not match source qualification"
        )

    return split_record.split_by_source_record_id()
