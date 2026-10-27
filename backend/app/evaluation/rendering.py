from typing import Final, Literal

from pydantic import Field

from app.evaluation.cases import (
    ConversationTurn,
    EvalModel,
    ExtractiveQAServingInput,
    InstructionServingInput,
    MCQServingInput,
    MemoryServingInput,
    NonBlankString,
    ServingInput,
)

EVAL_RENDERER_VERSION: Final = "eval-serving-v1"


class RenderedEvalInput(EvalModel):
    history: tuple[ConversationTurn, ...] = ()
    current_user_message: NonBlankString
    checkpoint: int | None = Field(default=None, ge=0)
    renderer_version: Literal["eval-serving-v1"] = "eval-serving-v1"


def render_serving_input(
    serving_input: ServingInput,
) -> RenderedEvalInput:
    if isinstance(serving_input, MCQServingInput):
        options = "\n".join(f"{option.key}. {option.text}" for option in serving_input.options)

        return RenderedEvalInput(
            current_user_message=(
                "Chọn một đáp án đúng và chỉ trả lời bằng ký hiệu của lựa chọn.\n\n"
                f"Câu hỏi:\n{serving_input.question}\n\n"
                f"Các lựa chọn:\n{options}"
            ),
        )

    if isinstance(serving_input, ExtractiveQAServingInput):
        return RenderedEvalInput(
            current_user_message=(
                "Dựa vào ngữ cảnh để trả lời ngắn gọn câu hỏi.\n\n"
                f"Ngữ cảnh:\n{serving_input.context}\n\n"
                f"Câu hỏi:\n{serving_input.question}"
            ),
        )

    if isinstance(serving_input, InstructionServingInput):
        return RenderedEvalInput(
            current_user_message=serving_input.prompt,
        )

    if isinstance(serving_input, MemoryServingInput):
        return RenderedEvalInput(
            history=serving_input.turns,
            current_user_message=serving_input.question,
            checkpoint=serving_input.checkpoint,
        )

    raise TypeError(f"Unsupported serving input type: {type(serving_input).__name__}")
