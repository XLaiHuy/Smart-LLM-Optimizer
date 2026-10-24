from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from app.evaluation.cases import (
    DatasetSplit,
    InstructionServingInput,
    InstructionTarget,
)
from app.evaluation.sea_ifeval import (
    SEA_IFEVAL_GRADER_VERSION,
)
from app.evaluation.sea_ifeval_adapter import (
    SeaIFEvalAdapterError,
    adapt_sea_ifeval_row,
    adapt_sea_ifeval_rows,
)
from app.evaluation.sources import (
    InstructionSourceQualificationRecord,
    load_source_qualification,
)

ROOT = Path(__file__).resolve().parents[3]

SOURCE_RECORD_PATH = ROOT / "benchmark" / "sources" / "sea_ifeval_vi_v1_1.qualification.json"


def _source_record() -> InstructionSourceQualificationRecord:
    record = load_source_qualification(
        SOURCE_RECORD_PATH,
    )

    assert isinstance(
        record,
        InstructionSourceQualificationRecord,
    )

    return record


def _row(
    *,
    record_id: str = "3439",
    instruction_id: str = "keywords:existence",
    kwargs: dict[str, object] | None = None,
) -> dict[str, object]:
    category = instruction_id.split(
        ":",
        maxsplit=1,
    )[0]

    return {
        "id": record_id,
        "prompts": [
            {
                "text": "Hãy dùng các từ bắt buộc.",
            }
        ],
        "metadata": {
            "category": category,
            "language": "vi",
            "subcategory": instruction_id,
        },
        "kwargs": [
            kwargs
            if kwargs is not None
            else {
                "keywords": [
                    "nhà kinh tế học",
                    "bình",
                    "dũng",
                ]
            }
        ],
    }


def _object(
    value: object,
) -> dict[str, object]:
    assert isinstance(value, dict)

    return cast(
        dict[str, object],
        value,
    )


def _array(
    value: object,
) -> list[object]:
    assert isinstance(value, list)

    return cast(
        list[object],
        value,
    )


def test_adapts_row_without_leaking_evaluator_metadata() -> None:
    case = adapt_sea_ifeval_row(
        row=_row(),
        source_record=_source_record(),
        split="dev",
    )

    assert case.case_id == "sea-ifeval-vi-v1-1:3439"
    assert case.task_family == "instruction"
    assert case.source.source_record_id == "3439"
    assert case.source.group_id == "3439"
    assert case.source.split == "dev"
    assert case.source.qualification_status == "candidate"
    assert case.source.license_id == "CC-BY-4.0"

    assert isinstance(
        case.serving_input,
        InstructionServingInput,
    )
    assert isinstance(
        case.evaluator_target,
        InstructionTarget,
    )

    serving_payload = case.serving_input.model_dump(
        mode="json",
    )

    assert "instruction_id" not in serving_payload
    assert "kwargs" not in serving_payload

    rule = case.evaluator_target.rules[0]

    assert rule.instruction_id == "keywords:existence"
    assert rule.kwargs[0].name == "keywords"
    assert rule.kwargs[0].value == (
        "nhà kinh tế học",
        "bình",
        "dũng",
    )
    assert case.evaluator_target.evaluator_version == SEA_IFEVAL_GRADER_VERSION


def test_batch_requires_exact_frozen_split_coverage() -> None:
    rows = (
        _row(
            record_id="3439",
        ),
        _row(
            record_id="100",
            instruction_id=("detectable_format:title"),
            kwargs={},
        ),
    )

    cases = adapt_sea_ifeval_rows(
        rows=rows,
        source_record=_source_record(),
        split_by_source_record_id={
            "3439": "dev",
            "100": "holdout",
        },
    )

    assert tuple(case.source.source_record_id for case in cases) == (
        "3439",
        "100",
    )

    assert tuple(case.source.split for case in cases) == (
        "dev",
        "holdout",
    )


@pytest.mark.parametrize(
    "split_assignments",
    (
        {},
        {
            "3439": "dev",
            "unknown": "holdout",
        },
    ),
)
def test_batch_rejects_split_coverage_mismatch(
    split_assignments: dict[
        str,
        DatasetSplit,
    ],
) -> None:
    with pytest.raises(
        SeaIFEvalAdapterError,
        match="split assignment",
    ):
        adapt_sea_ifeval_rows(
            rows=(_row(),),
            source_record=_source_record(),
            split_by_source_record_id=(split_assignments),
        )


def test_batch_rejects_duplicate_source_record_ids() -> None:
    with pytest.raises(
        SeaIFEvalAdapterError,
        match="duplicate",
    ):
        adapt_sea_ifeval_rows(
            rows=(
                _row(),
                _row(),
            ),
            source_record=_source_record(),
            split_by_source_record_id={
                "3439": "dev",
            },
        )


def test_rejects_smoke_split_for_public_source() -> None:
    with pytest.raises(
        SeaIFEvalAdapterError,
        match="dev or holdout",
    ):
        adapt_sea_ifeval_row(
            row=_row(),
            source_record=_source_record(),
            split="smoke",
        )


def _blank_id(
    row: dict[str, object],
) -> None:
    row["id"] = " "


def _missing_prompt(
    row: dict[str, object],
) -> None:
    row["prompts"] = []


def _wrong_language(
    row: dict[str, object],
) -> None:
    metadata = _object(
        row["metadata"],
    )
    metadata["language"] = "en"


def _wrong_category(
    row: dict[str, object],
) -> None:
    metadata = _object(
        row["metadata"],
    )
    metadata["category"] = "length_constraints"


def _missing_required_kwarg(
    row: dict[str, object],
) -> None:
    row["kwargs"] = [{}]


def _unsupported_instruction(
    row: dict[str, object],
) -> None:
    metadata = _object(
        row["metadata"],
    )
    metadata["category"] = "unknown"
    metadata["subcategory"] = "unknown:rule"


def _nested_argument(
    row: dict[str, object],
) -> None:
    kwargs = _object(
        _array(
            row["kwargs"],
        )[0]
    )
    kwargs["keywords"] = [
        {
            "nested": True,
        }
    ]


@pytest.mark.parametrize(
    (
        "mutate",
        "message",
    ),
    (
        (
            _blank_id,
            "must not be blank",
        ),
        (
            _missing_prompt,
            "at least 1 item",
        ),
        (
            _wrong_language,
            "row language",
        ),
        (
            _wrong_category,
            "does not match category",
        ),
        (
            _missing_required_kwarg,
            "missing",
        ),
        (
            _unsupported_instruction,
            "unsupported",
        ),
        (
            _nested_argument,
            "unsupported value type",
        ),
    ),
)
def test_rejects_malformed_or_unsupported_rows(
    mutate: Callable[
        [dict[str, object]],
        None,
    ],
    message: str,
) -> None:
    row = _row()
    mutate(row)

    with pytest.raises(
        SeaIFEvalAdapterError,
        match=message,
    ):
        adapt_sea_ifeval_row(
            row=row,
            source_record=_source_record(),
            split="dev",
        )


def test_rejects_evaluator_version_mismatch() -> None:
    source_record = _source_record()

    changed_schema = source_record.observed_schema.model_copy(
        update={
            "evaluator_version": ("different-evaluator"),
        }
    )

    changed_record = source_record.model_copy(
        update={
            "observed_schema": changed_schema,
        }
    )

    with pytest.raises(
        SeaIFEvalAdapterError,
        match="evaluator version",
    ):
        adapt_sea_ifeval_row(
            row=_row(),
            source_record=changed_record,
            split="dev",
        )
