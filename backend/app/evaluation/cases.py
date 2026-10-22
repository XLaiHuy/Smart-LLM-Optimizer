from typing import Annotated, Literal, Self, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _require_non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankString: TypeAlias = Annotated[str, AfterValidator(_require_non_blank)]

TaskFamily = Literal[
    "instruction",
    "extractive_qa",
    "conversation_memory",
    "multidisciplinary_mcq",
]

DatasetSplit = Literal["smoke", "dev", "holdout"]

QualificationStatus = Literal[
    "synthetic",
    "candidate",
    "qualified",
    "rejected",
]


class EvalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceMetadata(EvalModel):
    suite_name: NonBlankString
    source_name: NonBlankString
    source_revision: NonBlankString
    source_record_id: NonBlankString
    group_id: NonBlankString
    split: DatasetSplit
    language: NonBlankString
    qualification_status: QualificationStatus
    license_id: NonBlankString | None = None

    @model_validator(mode="after")
    def require_license_for_qualified_source(self) -> Self:
        if self.qualification_status == "qualified" and self.license_id is None:
            raise ValueError("qualified source must declare license_id")
        return self


class MCQOption(EvalModel):
    key: NonBlankString
    text: NonBlankString


class MCQServingInput(EvalModel):
    kind: Literal["multidisciplinary_mcq"] = "multidisciplinary_mcq"
    question: NonBlankString
    options: tuple[MCQOption, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def require_unique_option_keys(self) -> Self:
        option_keys = tuple(option.key for option in self.options)
        if len(set(option_keys)) != len(option_keys):
            raise ValueError("MCQ option keys must be unique")
        return self


class MCQTarget(EvalModel):
    kind: Literal["multidisciplinary_mcq"] = "multidisciplinary_mcq"
    answer_key: NonBlankString


class AnswerSpan(EvalModel):
    text: NonBlankString
    answer_start: int = Field(ge=0)


class ExtractiveQAServingInput(EvalModel):
    kind: Literal["extractive_qa"] = "extractive_qa"
    context: NonBlankString
    question: NonBlankString


class ExtractiveQATarget(EvalModel):
    kind: Literal["extractive_qa"] = "extractive_qa"
    answers: tuple[AnswerSpan, ...] = ()
    plausible_answers: tuple[AnswerSpan, ...] = ()
    is_impossible: bool

    @model_validator(mode="after")
    def validate_answerability(self) -> Self:
        if self.is_impossible and self.answers:
            raise ValueError("unanswerable case must not contain gold answers")

        if not self.is_impossible and not self.answers:
            raise ValueError("answerable case must contain at least one gold answer")

        return self


InstructionScalar: TypeAlias = str | int | float | bool | None
InstructionValue: TypeAlias = InstructionScalar | tuple[InstructionScalar, ...]


class InstructionArgument(EvalModel):
    name: NonBlankString
    value: InstructionValue


class InstructionRule(EvalModel):
    instruction_id: NonBlankString
    kwargs: tuple[InstructionArgument, ...] = ()


class InstructionServingInput(EvalModel):
    kind: Literal["instruction"] = "instruction"
    prompt: NonBlankString


class InstructionTarget(EvalModel):
    kind: Literal["instruction"] = "instruction"
    rules: tuple[InstructionRule, ...] = Field(min_length=1)
    evaluator_version: NonBlankString


class ConversationTurn(EvalModel):
    turn_id: NonBlankString
    turn_index: int = Field(ge=0)
    role: Literal["user", "assistant"]
    content: NonBlankString
    speaker: NonBlankString | None = None


class MemoryServingInput(EvalModel):
    kind: Literal["conversation_memory"] = "conversation_memory"
    turns: tuple[ConversationTurn, ...] = Field(min_length=1)
    checkpoint: int = Field(ge=0)
    question: NonBlankString

    @model_validator(mode="after")
    def validate_visible_turns(self) -> Self:
        turn_ids = tuple(turn.turn_id for turn in self.turns)
        if len(set(turn_ids)) != len(turn_ids):
            raise ValueError("conversation turn IDs must be unique")

        turn_indexes = tuple(turn.turn_index for turn in self.turns)
        if any(
            current <= previous
            for previous, current in zip(turn_indexes, turn_indexes[1:], strict=False)
        ):
            raise ValueError("conversation turn indexes must be strictly increasing")

        if any(index > self.checkpoint for index in turn_indexes):
            raise ValueError("serving input must not contain turns after checkpoint")

        return self


MemoryProbeType = Literal[
    "recall",
    "cross_session",
    "temporal",
    "knowledge_update",
    "abstention",
]

ReviewStatus = Literal["draft", "reviewed", "rejected"]


class MemoryTarget(EvalModel):
    kind: Literal["conversation_memory"] = "conversation_memory"
    gold_answers: tuple[NonBlankString, ...] = Field(min_length=1)
    evidence_turn_ids: tuple[NonBlankString, ...] = ()
    probe_type: MemoryProbeType
    protocol_version: NonBlankString
    annotator: NonBlankString | None = None
    reviewer: NonBlankString | None = None
    review_status: ReviewStatus = "draft"

    @model_validator(mode="after")
    def validate_annotation(self) -> Self:
        if self.probe_type != "abstention" and not self.evidence_turn_ids:
            raise ValueError("non-abstention memory probe must contain evidence turn IDs")

        if self.review_status == "reviewed" and (self.annotator is None or self.reviewer is None):
            raise ValueError("reviewed memory probe requires annotator and reviewer")

        return self


ServingInput: TypeAlias = Annotated[
    MCQServingInput | ExtractiveQAServingInput | InstructionServingInput | MemoryServingInput,
    Field(discriminator="kind"),
]

EvaluatorTarget: TypeAlias = Annotated[
    MCQTarget | ExtractiveQATarget | InstructionTarget | MemoryTarget,
    Field(discriminator="kind"),
]


class EvalCase(EvalModel):
    case_id: NonBlankString
    task_family: TaskFamily
    source: SourceMetadata
    serving_input: ServingInput
    evaluator_target: EvaluatorTarget
    tags: tuple[NonBlankString, ...] = ()

    @model_validator(mode="after")
    def validate_case_consistency(self) -> Self:
        if self.serving_input.kind != self.task_family:
            raise ValueError("serving input kind must match task_family")

        if self.evaluator_target.kind != self.task_family:
            raise ValueError("evaluator target kind must match task_family")

        if isinstance(self.serving_input, MCQServingInput) and isinstance(
            self.evaluator_target,
            MCQTarget,
        ):
            valid_keys = {option.key for option in self.serving_input.options}
            if self.evaluator_target.answer_key not in valid_keys:
                raise ValueError("MCQ answer key must match one visible option")

        if isinstance(self.serving_input, MemoryServingInput) and isinstance(
            self.evaluator_target,
            MemoryTarget,
        ):
            visible_turn_ids = {turn.turn_id for turn in self.serving_input.turns}
            unknown_evidence = set(self.evaluator_target.evidence_turn_ids) - visible_turn_ids
            if unknown_evidence:
                raise ValueError("memory evidence turn IDs must exist in the visible checkpoint")

        return self
