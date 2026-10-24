import json
from hashlib import sha256
from pathlib import Path

from app.evaluation.cases import (
    AnswerSpan,
    ConversationTurn,
    EvalCase,
    ExtractiveQAServingInput,
    ExtractiveQATarget,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    MemoryServingInput,
    MemoryTarget,
    SourceMetadata,
)
from app.evaluation.harness import (
    FixturePairConfig,
    export_fixture_harness,
    run_fixture_pair,
)
from app.evaluation.manifests import CaseSetManifest
from app.evaluation.runs import FixturePrediction
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
)
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "benchmark" / "reports" / "four-suite-smoke"


def _source(
    *,
    suite_name: str,
    source_record_id: str,
    group_id: str,
) -> SourceMetadata:
    return SourceMetadata(
        suite_name=suite_name,
        source_name="local-functional-fixture",
        source_revision="four-suite-smoke-v1",
        source_record_id=source_record_id,
        group_id=group_id,
        split="smoke",
        language="vi",
        qualification_status="synthetic",
    )


def _write_jsonl(
    path: Path,
    rows: tuple[BaseModel, ...],
) -> None:
    content = "\n".join(row.model_dump_json() for row in rows) + "\n"

    path.write_text(
        content,
        encoding="utf-8",
    )


def main() -> None:
    FIXTURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cases = (
        EvalCase(
            case_id="sea-ifeval-smoke-001",
            task_family="instruction",
            source=_source(
                suite_name=("sea-ifeval-synthetic"),
                source_record_id="sea-record-001",
                group_id="sea-group-001",
            ),
            serving_input=InstructionServingInput(
                prompt=(
                    "Viết một câu trả lời có tiêu đề đặt trong cặp ký hiệu << và >>."
                ),
            ),
            evaluator_target=InstructionTarget(
                rules=(
                    InstructionRule(
                        instruction_id=("detectable_format:title"),
                    ),
                ),
                evaluator_version=(SEA_IFEVAL_GRADER_VERSION),
            ),
            tags=("functional", "instruction"),
        ),
        EvalCase(
            case_id="uit-viquad-smoke-001",
            task_family="extractive_qa",
            source=_source(
                suite_name=("uit-viquad-synthetic"),
                source_record_id="qa-record-001",
                group_id="qa-group-001",
            ),
            serving_input=ExtractiveQAServingInput(
                context=("Học phí là 12 triệu đồng."),
                question="Học phí là bao nhiêu?",
            ),
            evaluator_target=ExtractiveQATarget(
                answers=(
                    AnswerSpan(
                        text="12 triệu đồng",
                        answer_start=11,
                    ),
                ),
                plausible_answers=(),
                is_impossible=False,
            ),
            tags=("functional", "qa"),
        ),
        EvalCase(
            case_id="vi-dialog-smoke-001",
            task_family="conversation_memory",
            source=_source(
                suite_name=("vi-dialog-memory-synthetic"),
                source_record_id=("memory-record-001"),
                group_id="memory-group-001",
            ),
            serving_input=MemoryServingInput(
                turns=(
                    ConversationTurn(
                        turn_id="memory-turn-001",
                        turn_index=1,
                        role="user",
                        content="Tên tôi là Khoa.",
                    ),
                    ConversationTurn(
                        turn_id="memory-turn-002",
                        turn_index=2,
                        role="assistant",
                        content=("Tôi đã ghi nhận tên của bạn."),
                    ),
                ),
                checkpoint=2,
                question="Người dùng tên gì?",
            ),
            evaluator_target=MemoryTarget(
                gold_answers=("Khoa",),
                evidence_turn_ids=("memory-turn-001",),
                probe_type="recall",
                protocol_version=("vi-dialog-memory-probes-v1"),
                review_status="draft",
            ),
            tags=("functional", "memory"),
        ),
        EvalCase(
            case_id="vmlu-smoke-001",
            task_family=("multidisciplinary_mcq"),
            source=_source(
                suite_name="vmlu-synthetic",
                source_record_id="vmlu-record-001",
                group_id="vmlu-group-001",
            ),
            serving_input=MCQServingInput(
                question=("Thủ đô của Việt Nam là gì?"),
                options=(
                    MCQOption(
                        key="A",
                        text="Huế",
                    ),
                    MCQOption(
                        key="B",
                        text="Hà Nội",
                    ),
                    MCQOption(
                        key="C",
                        text="Đà Nẵng",
                    ),
                    MCQOption(
                        key="D",
                        text="Cần Thơ",
                    ),
                ),
            ),
            evaluator_target=MCQTarget(
                answer_key="B",
            ),
            tags=("functional", "mcq"),
        ),
    )

    baseline_predictions = (
        FixturePrediction(
            case_id="sea-ifeval-smoke-001",
            prediction="Không có tiêu đề.",
        ),
        FixturePrediction(
            case_id="uit-viquad-smoke-001",
            prediction="10 triệu đồng",
        ),
        FixturePrediction(
            case_id="vi-dialog-smoke-001",
            prediction="Roland",
        ),
        FixturePrediction(
            case_id="vmlu-smoke-001",
            prediction="B",
        ),
    )

    optimized_predictions = (
        FixturePrediction(
            case_id="sea-ifeval-smoke-001",
            prediction="<<Tiêu đề>>",
        ),
        FixturePrediction(
            case_id="uit-viquad-smoke-001",
            prediction="12 triệu đồng",
        ),
        FixturePrediction(
            case_id="vi-dialog-smoke-001",
            prediction="Khoa",
        ),
        FixturePrediction(
            case_id="vmlu-smoke-001",
            prediction="B",
        ),
    )

    cases_path = FIXTURE_DIR / "cases.jsonl"
    baseline_path = FIXTURE_DIR / "baseline.predictions.jsonl"
    optimized_path = FIXTURE_DIR / "optimized.predictions.jsonl"
    manifest_path = FIXTURE_DIR / "manifest.json"

    _write_jsonl(
        cases_path,
        cases,
    )
    _write_jsonl(
        baseline_path,
        baseline_predictions,
    )
    _write_jsonl(
        optimized_path,
        optimized_predictions,
    )

    cases_sha256 = sha256(
        cases_path.read_bytes(),
    ).hexdigest()

    manifest = CaseSetManifest(
        case_set_id=("four-suite-synthetic-smoke-v1"),
        cases_file="cases.jsonl",
        data_sha256=cases_sha256,
        case_count=len(cases),
        suite_names=(
            "sea-ifeval-synthetic",
            "uit-viquad-synthetic",
            "vi-dialog-memory-synthetic",
            "vmlu-synthetic",
        ),
        task_families=(
            "instruction",
            "extractive_qa",
            "conversation_memory",
            "multidisciplinary_mcq",
        ),
        splits=("smoke",),
        qualification_statuses=("synthetic",),
    )

    manifest_path.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_fixture_pair(
        case_manifest_path=manifest_path,
        baseline_predictions_path=(baseline_path),
        variant_predictions_path=(optimized_path),
        config=FixturePairConfig(
            baseline_run_id=("four-suite-baseline-run"),
            baseline_config_id=("four-suite-baseline"),
            variant_run_id=("four-suite-optimized-run"),
            variant_config_id=("four-suite-optimized"),
            seed=7,
        ),
        language_detector=lambda _: "vi",
    )

    receipt = export_fixture_harness(
        result=result,
        output_dir=REPORT_DIR,
        overwrite=True,
    )

    baseline_passed = sum(
        group.passed_count for group in result.baseline_aggregate.groups
    )
    optimized_passed = sum(
        group.passed_count for group in result.variant_aggregate.groups
    )

    outcomes = {pair.case_id: pair.outcome for pair in result.comparison.pairs}

    assert result.baseline_aggregate.total_case_count == 4
    assert result.variant_aggregate.total_case_count == 4
    assert baseline_passed == 1
    assert optimized_passed == 4
    assert outcomes == {
        "sea-ifeval-smoke-001": "improvement",
        "uit-viquad-smoke-001": "improvement",
        "vi-dialog-smoke-001": "improvement",
        "vmlu-smoke-001": "both_pass",
    }
    assert result.research_eligible is False

    print(
        "BASELINE:",
        f"{baseline_passed}/4 passed",
    )
    print(
        "OPTIMIZED:",
        f"{optimized_passed}/4 passed",
    )

    for pair in result.comparison.pairs:
        print(
            pair.case_id,
            "=>",
            pair.outcome,
        )

    print(
        "REPORT:",
        receipt.report_path,
    )
    print(
        "REPORT_SHA256:",
        receipt.report_sha256,
    )
    print(
        "RESEARCH_ELIGIBLE:",
        result.research_eligible,
    )


if __name__ == "__main__":
    main()
