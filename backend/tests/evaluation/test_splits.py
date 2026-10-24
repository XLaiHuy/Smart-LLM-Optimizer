import json
from pathlib import Path
from typing import cast

import pytest

from app.evaluation.sources import (
    InstructionSourceQualificationRecord,
    load_source_qualification,
)
from app.evaluation.splits import (
    SourceSplitLoadError,
    SourceSplitValidationError,
    load_source_split,
    validate_instruction_source_split,
)

ROOT = Path(__file__).resolve().parents[3]

SPLIT_PATH = ROOT / "benchmark" / "splits" / "sea_ifeval_vi_v1_1.split.json"

SOURCE_PATH = ROOT / "benchmark" / "sources" / "sea_ifeval_vi_v1_1.qualification.json"


def _split_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            SPLIT_PATH.read_text(
                encoding="utf-8",
            )
        ),
    )


def _object(
    value: object,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")

    return cast(
        dict[str, object],
        value,
    )


def _array(
    value: object,
) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError("expected JSON array")

    return cast(
        list[object],
        value,
    )


def _write_split(
    path: Path,
    payload: dict[str, object],
) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _source_record() -> InstructionSourceQualificationRecord:
    record = load_source_qualification(
        SOURCE_PATH,
    )

    assert isinstance(
        record,
        InstructionSourceQualificationRecord,
    )

    return record


def test_checked_in_split_matches_source() -> None:
    split_record = load_source_split(
        SPLIT_PATH,
    )

    split_mapping = validate_instruction_source_split(
        split_record=split_record,
        source_record=_source_record(),
    )

    assert split_record.split_id == ("sea-ifeval-vi-v1-1-balanced-42-v1")
    assert split_record.source_record_count == 105
    assert split_record.selected_record_count == 42
    assert split_record.reserve_record_count == 63
    assert split_record.qualification_status == ("candidate")
    assert split_record.holdout_status == ("frozen_not_blind_public_source")

    assert len(split_mapping) == 42

    assert sum(split_name == "dev" for split_name in split_mapping.values()) == 21

    assert sum(split_name == "holdout" for split_name in split_mapping.values()) == 21

    instruction_ids = {item.instruction_id for item in split_record.assignments}

    assert len(instruction_ids) == 21
    assert split_mapping["2465"] == "dev"
    assert split_mapping["2071"] == "holdout"


def test_rejects_missing_split_file(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-split.json"

    with pytest.raises(
        SourceSplitLoadError,
        match="Could not read",
    ):
        load_source_split(
            missing_path,
        )


def test_rejects_duplicate_source_record_id(
    tmp_path: Path,
) -> None:
    payload = _split_payload()

    assignments = _array(
        payload["assignments"],
    )
    reserve = _array(
        payload["reserve"],
    )

    first_assignment = _object(
        assignments[0],
    )
    first_reserve = _object(
        reserve[0],
    )

    first_reserve["source_record_id"] = first_assignment["source_record_id"]

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    with pytest.raises(
        SourceSplitLoadError,
        match="must be unique",
    ):
        load_source_split(path)


def test_rejects_missing_holdout_coverage(
    tmp_path: Path,
) -> None:
    payload = _split_payload()

    assignments = _array(
        payload["assignments"],
    )

    second_assignment = _object(
        assignments[1],
    )
    second_assignment["split"] = "dev"

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    with pytest.raises(
        SourceSplitLoadError,
        match="exactly one DEV and one HOLDOUT",
    ):
        load_source_split(path)


def test_rejects_changed_deterministic_assignment(
    tmp_path: Path,
) -> None:
    payload = _split_payload()

    assignments = _array(
        payload["assignments"],
    )

    first_assignment = _object(
        assignments[0],
    )
    second_assignment = _object(
        assignments[1],
    )

    first_record_id = first_assignment["source_record_id"]
    second_record_id = second_assignment["source_record_id"]

    first_assignment["source_record_id"] = second_record_id
    second_assignment["source_record_id"] = first_record_id

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    with pytest.raises(
        SourceSplitLoadError,
        match="deterministic SHA-256",
    ):
        load_source_split(path)


def test_rejects_declared_count_mismatch(
    tmp_path: Path,
) -> None:
    payload = _split_payload()
    payload["selected_record_count"] = 41

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    with pytest.raises(
        SourceSplitLoadError,
        match="selected_record_count",
    ):
        load_source_split(path)


def test_rejects_unknown_split_field(
    tmp_path: Path,
) -> None:
    payload = _split_payload()
    payload["unexpected_field"] = True

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    with pytest.raises(
        SourceSplitLoadError,
        match="unexpected_field",
    ):
        load_source_split(path)


@pytest.mark.parametrize(
    (
        "field_name",
        "changed_value",
        "error_message",
    ),
    (
        (
            "source_revision",
            "0" * 40,
            "source revision",
        ),
        (
            "source_file_sha256",
            "0" * 64,
            "source file SHA-256",
        ),
    ),
)
def test_rejects_source_evidence_mismatch(
    tmp_path: Path,
    field_name: str,
    changed_value: str,
    error_message: str,
) -> None:
    payload = _split_payload()
    payload[field_name] = changed_value

    path = tmp_path / "split.json"
    _write_split(
        path,
        payload,
    )

    split_record = load_source_split(path)

    with pytest.raises(
        SourceSplitValidationError,
        match=error_message,
    ):
        validate_instruction_source_split(
            split_record=split_record,
            source_record=_source_record(),
        )
