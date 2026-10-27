from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.contracts.dtos import DTO, Message


class LabeledTaskSample(DTO):
    task_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    split: Literal["train", "calibration", "holdout"]
    messages: tuple[Message, ...] = Field(min_length=1)
    has_rag_context: bool = False
    critical: bool = False
    reference_qualified: bool
    small_qualified: bool
    reference_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    small_usd: Decimal = Field(ge=0, allow_inf_nan=False)
    reference_ms: float = Field(gt=0, allow_inf_nan=False)
    small_ms: float = Field(gt=0, allow_inf_nan=False)


class LabeledDataset(DTO):
    version: str = Field(min_length=1)
    purpose: Literal["qualified_dev", "qualified_holdout", "software_test"]
    provenance: str = Field(min_length=1)
    grader_version: str = Field(min_length=1)
    candidate_config_id: str = Field(min_length=1)
    candidate_model_id: str = Field(min_length=1)
    reference_config_id: str = Field(min_length=1)
    reference_model_id: str = Field(min_length=1)
    samples: tuple[LabeledTaskSample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def independent_splits(self) -> "LabeledDataset":
        groups: dict[str, str] = {}
        texts: dict[str, str] = {}
        ids = set()
        for row in self.samples:
            if row.task_id in ids:
                raise ValueError("Duplicate task ID")
            ids.add(row.task_id)
            text = "\n".join(m.content.strip().casefold() for m in row.messages)
            if (
                groups.get(row.group_id, row.split) != row.split
                or texts.get(text, row.split) != row.split
            ):
                raise ValueError("Source group or duplicate input crosses splits")
            groups[row.group_id], texts[text] = row.split, row.split
        if self.candidate_config_id == self.reference_config_id:
            raise ValueError("Candidate and reference must differ")
        return self

    @classmethod
    def load(cls, path: Path) -> "LabeledDataset":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
