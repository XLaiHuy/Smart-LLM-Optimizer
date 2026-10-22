from typing import Literal, Self

from pydantic import Field, model_validator

from app.evaluation.cases import (
    EvalCase,
    EvalModel,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    MCQServingInput,
    MCQTarget,
    NonBlankString,
    TaskFamily,
)
from app.evaluation.graders import grade_extractive_qa, grade_mcq

MetricName = Literal[
    "accuracy",
    "exact_match",
    "token_f1",
]


class MetricValue(EvalModel):
    name: MetricName
    value: float = Field(ge=0.0, le=1.0)


class CaseGrade(EvalModel):
    case_id: NonBlankString
    task_family: TaskFamily
    passed: bool
    metrics: tuple[MetricValue, ...] = Field(min_length=1)
    normalized_prediction: str | None
    reason: NonBlankString
    grader_version: NonBlankString

    @model_validator(mode="after")
    def require_unique_metrics(self) -> Self:
        metric_names = tuple(metric.name for metric in self.metrics)

        if len(set(metric_names)) != len(metric_names):
            raise ValueError("metric names must be unique")

        return self


class UnsupportedGraderError(ValueError):
    pass


def grade_case(
    *,
    case: EvalCase,
    prediction: str,
) -> CaseGrade:
    serving_input = case.serving_input
    evaluator_target = case.evaluator_target

    if isinstance(serving_input, MCQServingInput) and isinstance(
        evaluator_target,
        MCQTarget,
    ):
        valid_keys = tuple(option.key for option in serving_input.options)

        mcq_grade = grade_mcq(
            prediction=prediction,
            answer_key=evaluator_target.answer_key,
            valid_keys=valid_keys,
        )

        return CaseGrade(
            case_id=case.case_id,
            task_family=case.task_family,
            passed=mcq_grade.passed,
            metrics=(
                MetricValue(
                    name="accuracy",
                    value=float(mcq_grade.passed),
                ),
            ),
            normalized_prediction=mcq_grade.normalized_prediction,
            reason=mcq_grade.reason,
            grader_version=mcq_grade.grader_version,
        )

    if isinstance(serving_input, ExtractiveQAServingInput) and isinstance(
        evaluator_target,
        ExtractiveQATarget,
    ):
        qa_grade = grade_extractive_qa(
            prediction=prediction,
            gold_answers=tuple(answer.text for answer in evaluator_target.answers),
            is_impossible=evaluator_target.is_impossible,
        )

        return CaseGrade(
            case_id=case.case_id,
            task_family=case.task_family,
            passed=qa_grade.passed,
            metrics=(
                MetricValue(
                    name="exact_match",
                    value=qa_grade.exact_match,
                ),
                MetricValue(
                    name="token_f1",
                    value=qa_grade.token_f1,
                ),
            ),
            normalized_prediction=qa_grade.normalized_prediction,
            reason=qa_grade.reason,
            grader_version=qa_grade.grader_version,
        )

    raise UnsupportedGraderError(
        f"No deterministic grader implemented for task family: {case.task_family}"
    )
