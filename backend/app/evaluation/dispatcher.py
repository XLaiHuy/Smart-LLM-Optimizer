from typing import Literal, Self

from pydantic import Field, model_validator

from app.evaluation.cases import (
    EvalCase,
    EvalModel,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    InstructionServingInput,
    InstructionTarget,
    MCQServingInput,
    MCQTarget,
    MemoryServingInput,
    MemoryTarget,
    NonBlankString,
    TaskFamily,
)
from app.evaluation.graders import (
    MEMORY_GRADER_VERSION,
    grade_extractive_qa,
    grade_mcq,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
    LanguageDetector,
    grade_sea_ifeval_rule,
)

MetricName = Literal[
    "accuracy",
    "exact_match",
    "token_f1",
    "overall_acc",
    "correct_language_rate",
    "overall_lang_normalized_acc",
    "case_all_pass_rate",
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
    language_detector: LanguageDetector | None = None,
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
            normalized_prediction=(mcq_grade.normalized_prediction),
            reason=mcq_grade.reason,
            grader_version=mcq_grade.grader_version,
        )

    if isinstance(
        serving_input,
        ExtractiveQAServingInput,
    ) and isinstance(
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
            normalized_prediction=(qa_grade.normalized_prediction),
            reason=qa_grade.reason,
            grader_version=qa_grade.grader_version,
        )

    if isinstance(
        serving_input,
        MemoryServingInput,
    ) and isinstance(
        evaluator_target,
        MemoryTarget,
    ):
        memory_grade = grade_extractive_qa(
            prediction=prediction,
            gold_answers=evaluator_target.gold_answers,
            is_impossible=False,
        )

        return CaseGrade(
            case_id=case.case_id,
            task_family=case.task_family,
            passed=memory_grade.passed,
            metrics=(
                MetricValue(
                    name="exact_match",
                    value=memory_grade.exact_match,
                ),
                MetricValue(
                    name="token_f1",
                    value=memory_grade.token_f1,
                ),
            ),
            normalized_prediction=(memory_grade.normalized_prediction),
            reason=memory_grade.reason,
            grader_version=MEMORY_GRADER_VERSION,
        )

    if isinstance(
        serving_input,
        InstructionServingInput,
    ) and isinstance(
        evaluator_target,
        InstructionTarget,
    ):
        if evaluator_target.evaluator_version != SEA_IFEVAL_GRADER_VERSION:
            raise UnsupportedGraderError(
                f"Unsupported instruction evaluator version: {evaluator_target.evaluator_version!r}"
            )

        if language_detector is None:
            raise UnsupportedGraderError(
                "SEA-IFEval instruction grading requires a language detector"
            )

        rule_grades = tuple(
            grade_sea_ifeval_rule(
                response=prediction,
                source_language=case.source.language,
                rule=rule,
                language_detector=language_detector,
            )
            for rule in evaluator_target.rules
        )

        rule_count = len(rule_grades)
        overall_acc = sum(grade.constraint_passed for grade in rule_grades) / rule_count
        correct_language_rate = sum(grade.correct_language for grade in rule_grades) / rule_count
        overall_lang_normalized_acc = sum(grade.passed for grade in rule_grades) / rule_count
        passed = all(grade.passed for grade in rule_grades)

        if passed:
            reason = "all_rules_passed"
        else:
            failures = ",".join(
                f"{grade.instruction_id}={grade.reason}"
                for grade in rule_grades
                if not grade.passed
            )
            reason = f"failed_rules:{failures}"

        return CaseGrade(
            case_id=case.case_id,
            task_family=case.task_family,
            passed=passed,
            metrics=(
                MetricValue(
                    name="overall_acc",
                    value=overall_acc,
                ),
                MetricValue(
                    name="correct_language_rate",
                    value=correct_language_rate,
                ),
                MetricValue(
                    name="overall_lang_normalized_acc",
                    value=overall_lang_normalized_acc,
                ),
                MetricValue(
                    name="case_all_pass_rate",
                    value=float(passed),
                ),
            ),
            normalized_prediction=None,
            reason=reason,
            grader_version=SEA_IFEVAL_GRADER_VERSION,
        )

    raise UnsupportedGraderError(
        f"No deterministic grader implemented for task family: {case.task_family}"
    )
