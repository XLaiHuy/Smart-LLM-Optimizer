import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.contracts.dtos import CallRecord, CostEstimate, Usage
from app.evaluation.cases import (
    DatasetSplit,
    EvalCase,
    InstructionRule,
    InstructionServingInput,
    InstructionTarget,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    QualificationStatus,
    SourceMetadata,
)
from app.evaluation.exporting import ExportError
from app.evaluation.live_exporting import (
    export_live_suite,
)
from app.evaluation.live_harness import (
    LiveHarnessError,
    LiveSuiteConfig,
    LiveSuiteResult,
    run_live_suite,
)
from app.evaluation.live_runner import (
    LiveExecutionRequest,
    LiveExecutionResult,
)
from app.evaluation.sea_ifeval import SEA_IFEVAL_GRADER_VERSION


def _case(
    index: int,
    *,
    split: DatasetSplit = "dev",
    qualification_status: QualificationStatus = "qualified",
) -> EvalCase:
    return EvalCase(
        case_id=f"sea-ifeval-dev-{index:03d}",
        task_family="instruction",
        source=SourceMetadata(
            suite_name="sea-ifeval-vi",
            source_name="sea-ifeval-vi-v1-1",
            source_revision="fixture-revision",
            source_record_id=f"source-{index:03d}",
            group_id=f"source-{index:03d}",
            split=split,
            language="vi",
            qualification_status=qualification_status,
            license_id="CC-BY-4.0",
        ),
        serving_input=InstructionServingInput(
            prompt=f"Viết câu trả lời có tiêu đề cho trường hợp {index}.",
        ),
        evaluator_target=InstructionTarget(
            rules=(
                InstructionRule(
                    instruction_id="detectable_format:title",
                ),
            ),
            evaluator_version=SEA_IFEVAL_GRADER_VERSION,
        ),
        tags=("sea-ifeval",),
    )


def _mcq_case(index: int) -> EvalCase:
    return EvalCase(
        case_id=f"vmlu-dev-{index:03d}",
        task_family="multidisciplinary_mcq",
        source=SourceMetadata(
            suite_name="vmlu-functional-fixture",
            source_name="local-mcq-live-fixture",
            source_revision="fixture-revision",
            source_record_id=f"mcq-source-{index:03d}",
            group_id=f"mcq-group-{index:03d}",
            split="dev",
            language="vi",
            qualification_status="qualified",
            license_id="MIT",
        ),
        serving_input=MCQServingInput(
            question="Thủ đô của Việt Nam là gì?",
            options=(
                MCQOption(
                    key="A",
                    text="Huế",
                ),
                MCQOption(
                    key="B",
                    text="Hà Nội",
                ),
            ),
        ),
        evaluator_target=MCQTarget(
            answer_key="B",
        ),
        tags=("vmlu", "functional-fixture"),
    )


class FakeLiveExecutor:
    def __init__(
        self,
        *,
        incomplete_baseline_case_id: str | None = None,
    ) -> None:
        self.requests: list[LiveExecutionRequest] = []
        self.incomplete_baseline_case_id = incomplete_baseline_case_id

    async def execute(
        self,
        request: LiveExecutionRequest,
    ) -> LiveExecutionResult:
        self.requests.append(request)

        if request.serving_input.kind == "multidisciplinary_mcq":
            prediction = "B" if request.mode == "optimized" else "A"
        else:
            passing = request.mode == "optimized" or request.case_id == "sea-ifeval-dev-002"
            prediction = "<<Tiêu đề>>" if passing else "Không có tiêu đề."

        incomplete = (
            request.mode == "baseline" and request.case_id == self.incomplete_baseline_case_id
        )

        if incomplete:
            aggregate_usage = Usage(
                scope="all_calls",
                input_tokens=None,
                output_tokens=None,
                cached_input_tokens=None,
                reasoning_tokens=None,
                usage_source="unknown",
            )
            aggregate_cost = CostEstimate(
                scope="all_calls",
                status="unknown",
                serving_usd=None,
                price_catalog_version=None,
            )
        else:
            aggregate_usage = Usage(
                scope="all_calls",
                input_tokens=10,
                output_tokens=5,
                cached_input_tokens=0,
                reasoning_tokens=0,
                usage_source="provider",
            )
            aggregate_cost = CostEstimate(
                scope="all_calls",
                status="estimated",
                serving_usd=Decimal("0.001"),
                price_catalog_version="test-catalog-v1",
            )

        call_usage = aggregate_usage.model_copy(
            update={"scope": "call"},
        )
        call_cost = aggregate_cost.model_copy(
            update={"scope": "call"},
        )

        return LiveExecutionResult(
            operation_key=request.operation_key,
            mode=request.mode,
            prediction=prediction,
            model_id="fake-live-model",
            config_id=f"{request.mode}-config",
            usage=aggregate_usage,
            cost=aggregate_cost,
            duration_ms=10.0,
            calls=(
                CallRecord(
                    call_id=f"call-{request.operation_key}",
                    model_id="fake-live-model",
                    usage=call_usage,
                    cost=call_cost,
                    duration_ms=10.0,
                ),
            ),
        )


async def test_live_suite_aggregates_paired_results() -> None:
    executor = FakeLiveExecutor()

    result = await run_live_suite(
        cases=(
            _case(2),
            _case(1),
        ),
        config=LiveSuiteConfig(
            run_id="engineering-suite-001",
            seed=7,
            max_total_usd_per_arm=Decimal("0.01"),
            max_suite_usd=Decimal("0.04"),
        ),
        executor=executor,
        language_detector=lambda _: "vi",
    )

    assert tuple(pair.case_id for pair in result.pairs) == (
        "sea-ifeval-dev-001",
        "sea-ifeval-dev-002",
    )
    assert len(executor.requests) == 4
    assert all("evaluator_target" not in request.model_dump_json() for request in executor.requests)

    assert result.baseline.passed_count == 1
    assert result.baseline.failed_count == 1
    assert result.baseline.pass_rate == 0.5
    assert result.optimized.passed_count == 2
    assert result.optimized.pass_rate == 1.0

    assert result.baseline.usage.input_tokens.complete_total == 20
    assert result.optimized.usage.output_tokens.complete_total == 10
    assert result.baseline.cost.complete_total_usd == Decimal("0.002")
    assert result.optimized.cost.complete_total_usd == Decimal("0.002")
    assert result.baseline.latency.p50_ms == 10.0
    assert result.baseline.latency.p95_ms == 10.0
    assert result.baseline.call_count == 2

    assert result.comparison.improvement_count == 1
    assert result.comparison.regression_count == 0
    assert result.comparison.both_pass_count == 1
    assert result.comparison.both_fail_count == 0
    assert result.research_eligible is False


async def test_live_suite_supports_mcq_without_language_detector() -> None:
    executor = FakeLiveExecutor()

    result = await run_live_suite(
        cases=(
            _mcq_case(2),
            _mcq_case(1),
        ),
        config=LiveSuiteConfig(
            run_id="engineering-mcq-suite-001",
            seed=7,
            max_total_usd_per_arm=Decimal("0.01"),
            max_suite_usd=Decimal("0.04"),
        ),
        executor=executor,
    )

    assert tuple(pair.case_id for pair in result.pairs) == (
        "vmlu-dev-001",
        "vmlu-dev-002",
    )

    assert result.baseline.passed_count == 0
    assert result.optimized.passed_count == 2
    assert result.comparison.improvement_count == 2
    assert result.comparison.regression_count == 0

    assert all(
        request.serving_input.kind == "multidisciplinary_mcq" for request in executor.requests
    )

    assert all("evaluator_target" not in request.model_dump_json() for request in executor.requests)

    assert result.research_eligible is False


async def test_live_suite_preserves_unknown_usage_and_cost() -> None:
    first_case = _case(1)
    executor = FakeLiveExecutor(
        incomplete_baseline_case_id=first_case.case_id,
    )

    result = await run_live_suite(
        cases=(first_case, _case(2)),
        config=LiveSuiteConfig(
            run_id="engineering-suite-unknown",
            max_total_usd_per_arm=Decimal("0.01"),
            max_suite_usd=Decimal("0.04"),
        ),
        executor=executor,
        language_detector=lambda _: "vi",
    )

    assert result.baseline.usage.input_tokens.known_subtotal == 10
    assert result.baseline.usage.input_tokens.unknown_case_count == 1
    assert result.baseline.usage.input_tokens.complete_total is None

    assert result.baseline.cost.priced_case_count == 1
    assert result.baseline.cost.unknown_case_count == 1
    assert result.baseline.cost.known_subtotal_usd == Decimal("0.001")
    assert result.baseline.cost.complete_total_usd is None

    assert result.optimized.cost.priced_case_count == 2
    assert result.optimized.cost.unknown_case_count == 0
    assert result.optimized.cost.complete_total_usd == Decimal("0.002")


async def test_live_suite_rejects_duplicate_case_before_execution() -> None:
    duplicate = _case(1)
    executor = FakeLiveExecutor()

    with pytest.raises(
        LiveHarnessError,
        match="duplicate case_id",
    ):
        await run_live_suite(
            cases=(duplicate, duplicate),
            config=LiveSuiteConfig(
                run_id="engineering-suite-duplicate",
                max_total_usd_per_arm=Decimal("0.01"),
                max_suite_usd=Decimal("0.04"),
            ),
            executor=executor,
            language_detector=lambda _: "vi",
        )

    assert executor.requests == []


async def test_live_suite_rejects_unqualified_case_before_execution() -> None:
    executor = FakeLiveExecutor()

    with pytest.raises(
        LiveHarnessError,
        match="qualified",
    ):
        await run_live_suite(
            cases=(
                _case(
                    1,
                    qualification_status="candidate",
                ),
            ),
            config=LiveSuiteConfig(
                run_id="engineering-suite-candidate",
                max_total_usd_per_arm=Decimal("0.01"),
                max_suite_usd=Decimal("0.02"),
            ),
            executor=executor,
            language_detector=lambda _: "vi",
        )

    assert executor.requests == []


async def test_live_suite_rejects_budget_plan_before_execution() -> None:
    executor = FakeLiveExecutor()

    with pytest.raises(
        LiveHarnessError,
        match="max_suite_usd",
    ):
        await run_live_suite(
            cases=(_case(1), _case(2)),
            config=LiveSuiteConfig(
                run_id="engineering-suite-over-budget",
                max_total_usd_per_arm=Decimal("0.02"),
                max_suite_usd=Decimal("0.05"),
            ),
            executor=executor,
            language_detector=lambda _: "vi",
        )

    assert executor.requests == []


async def _exportable_live_suite() -> LiveSuiteResult:
    return await run_live_suite(
        cases=(
            _case(2),
            _case(1),
        ),
        config=LiveSuiteConfig(
            run_id="engineering-export-001",
            seed=7,
            max_total_usd_per_arm=(Decimal("0.01")),
            max_suite_usd=Decimal("0.04"),
        ),
        executor=FakeLiveExecutor(),
        language_detector=lambda _: "vi",
    )


async def test_live_suite_export_writes_reproducible_bundle(
    tmp_path: Path,
) -> None:
    result = await _exportable_live_suite()

    first = export_live_suite(
        result=result,
        output_dir=tmp_path / "first",
    )
    second = export_live_suite(
        result=result,
        output_dir=tmp_path / "second",
    )

    first_pair_bytes = first.pair_results.output_path.read_bytes()
    second_pair_bytes = second.pair_results.output_path.read_bytes()
    first_report_bytes = first.report_path.read_bytes()
    second_report_bytes = second.report_path.read_bytes()

    assert first_pair_bytes == second_pair_bytes
    assert first_report_bytes == second_report_bytes
    assert first.pair_results.content_sha256 == second.pair_results.content_sha256
    assert first.report_sha256 == second.report_sha256

    pair_text = first_pair_bytes.decode(
        "utf-8",
    )
    pair_records = tuple(json.loads(line) for line in pair_text.splitlines())

    assert tuple(record["result"]["case_id"] for record in pair_records) == (
        "sea-ifeval-dev-001",
        "sea-ifeval-dev-002",
    )
    assert all(record["schema_version"] == "eval-live-pair-result-v1" for record in pair_records)
    assert all(record["record_type"] == "live_pair" for record in pair_records)

    assert first.pair_results.row_count == 2
    assert first.pair_results.byte_count == len(first_pair_bytes)
    assert (
        first.pair_results.content_sha256
        == hashlib.sha256(
            first_pair_bytes,
        ).hexdigest()
    )

    report_text = first_report_bytes.decode(
        "utf-8",
    )
    report = json.loads(report_text)

    assert report["schema_version"] == "eval-live-suite-report-v1"
    assert report["research_eligible"] is False
    assert report["comparison"]["pair_count"] == 2
    assert "pairs" not in report

    assert first.report_byte_count == len(first_report_bytes)
    assert first.report_sha256 == (
        hashlib.sha256(
            first_report_bytes,
        ).hexdigest()
    )

    assert "evaluator_target" not in pair_text
    assert "evaluator_target" not in report_text


async def test_live_suite_export_refuses_overwrite_by_default(
    tmp_path: Path,
) -> None:
    result = await _exportable_live_suite()
    output_dir = tmp_path / "report"

    first = export_live_suite(
        result=result,
        output_dir=output_dir,
    )
    original_pair_bytes = first.pair_results.output_path.read_bytes()
    original_report_bytes = first.report_path.read_bytes()

    with pytest.raises(
        ExportError,
        match="Output already exists",
    ):
        export_live_suite(
            result=result,
            output_dir=output_dir,
        )

    assert first.pair_results.output_path.read_bytes() == original_pair_bytes
    assert first.report_path.read_bytes() == original_report_bytes

    overwritten = export_live_suite(
        result=result,
        output_dir=output_dir,
        overwrite=True,
    )

    assert overwritten.pair_results.overwrote_existing is True
    assert overwritten.report_overwrote_existing is True


async def test_live_suite_export_rejects_pair_metadata_mismatch(
    tmp_path: Path,
) -> None:
    result = await _exportable_live_suite()
    invalid_first_pair = result.pairs[0].model_copy(
        update={
            "run_id": "different-run",
        },
    )
    invalid_result = result.model_copy(
        update={
            "pairs": (
                invalid_first_pair,
                *result.pairs[1:],
            ),
        },
    )

    with pytest.raises(
        ExportError,
        match="run metadata mismatch",
    ):
        export_live_suite(
            result=invalid_result,
            output_dir=tmp_path / "report",
        )
