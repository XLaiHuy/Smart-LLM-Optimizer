from app.evaluation.cases import (
    ConversationTurn,
    EvalCase,
    ExtractiveQAServingInput,
    InstructionArgument,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MemoryServingInput,
    SourceMetadata,
)
from app.evaluation.rendering import (
    EVAL_RENDERER_VERSION,
    render_serving_input,
)


def _candidate_source() -> SourceMetadata:
    return SourceMetadata(
        suite_name="fixture-suite",
        source_name="local-fixture",
        source_revision="fixture-v1",
        source_record_id="record-001",
        group_id="group-001",
        split="dev",
        language="vi",
        qualification_status="candidate",
    )


def test_render_mcq_preserves_option_order() -> None:
    rendered = render_serving_input(
        MCQServingInput(
            question="Thủ đô của Việt Nam là gì?",
            options=(
                MCQOption(key="A", text="Huế"),
                MCQOption(key="B", text="Hà Nội"),
            ),
        )
    )

    assert rendered.current_user_message == (
        "Chọn một đáp án đúng và chỉ trả lời bằng ký hiệu của lựa chọn.\n\n"
        "Câu hỏi:\nThủ đô của Việt Nam là gì?\n\n"
        "Các lựa chọn:\n"
        "A. Huế\n"
        "B. Hà Nội"
    )
    assert rendered.history == ()
    assert rendered.checkpoint is None


def test_render_extractive_qa_preserves_context_and_question() -> None:
    rendered = render_serving_input(
        ExtractiveQAServingInput(
            context="Đại học Mở Thành phố Hồ Chí Minh được thành lập năm 1990.",
            question="Trường được thành lập năm nào?",
        )
    )

    assert rendered.current_user_message == (
        "Dựa vào ngữ cảnh để trả lời ngắn gọn câu hỏi.\n\n"
        "Ngữ cảnh:\n"
        "Đại học Mở Thành phố Hồ Chí Minh được thành lập năm 1990.\n\n"
        "Câu hỏi:\n"
        "Trường được thành lập năm nào?"
    )
    assert rendered.history == ()


def test_render_instruction_preserves_original_prompt_exactly() -> None:
    prompt = "Viết đúng ba câu bằng tiếng Việt."

    rendered = render_serving_input(
        InstructionServingInput(prompt=prompt),
    )

    assert rendered.current_user_message == prompt
    assert rendered.renderer_version == EVAL_RENDERER_VERSION


def test_render_memory_keeps_history_separate_from_probe_question() -> None:
    turns = (
        ConversationTurn(
            turn_id="turn-1",
            turn_index=1,
            role="user",
            content="Tên tôi là Khoa.",
        ),
        ConversationTurn(
            turn_id="turn-2",
            turn_index=2,
            role="assistant",
            content="Tôi đã ghi nhận.",
        ),
    )

    rendered = render_serving_input(
        MemoryServingInput(
            turns=turns,
            checkpoint=2,
            question="Người dùng tên gì?",
        )
    )

    assert rendered.history == turns
    assert rendered.current_user_message == "Người dùng tên gì?"
    assert rendered.checkpoint == 2
    assert all(turn.content != rendered.current_user_message for turn in rendered.history)


def test_renderer_does_not_serialize_evaluator_target() -> None:
    case = EvalCase(
        case_id="instruction-001",
        task_family="instruction",
        source=_candidate_source(),
        serving_input=InstructionServingInput(
            prompt="Trả lời đúng ba câu.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id="hidden-rule-id",
                    kwargs=(
                        InstructionArgument(
                            name="hidden-value",
                            value="evaluator-only-secret",
                        ),
                    ),
                ),
            ),
            evaluator_version="hidden-evaluator-version",
        ),
    )

    rendered_json = render_serving_input(
        case.serving_input,
    ).model_dump_json()

    assert "evaluator_target" not in rendered_json
    assert "hidden-rule-id" not in rendered_json
    assert "evaluator-only-secret" not in rendered_json
    assert "hidden-evaluator-version" not in rendered_json
