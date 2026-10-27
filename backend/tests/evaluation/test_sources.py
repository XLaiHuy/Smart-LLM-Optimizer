import json
from pathlib import Path
from typing import cast

import pytest

from app.evaluation.sources import (
    InstructionSourceQualificationRecord,
    SourceNotQualifiedError,
    SourceQualificationLoadError,
    SourceQualificationRecord,
    load_source_qualification,
    require_live_research_qualified,
)

ROOT = Path(__file__).resolve().parents[3]

VMLU_RECORD_PATH = ROOT / "benchmark" / "sources" / "vmlu_vi_mqa_v1_5.qualification.json"

SEA_IFEVAL_RECORD_PATH = ROOT / "benchmark" / "sources" / "sea_ifeval_vi_v1_1.qualification.json"


def _record_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(VMLU_RECORD_PATH.read_text(encoding="utf-8")),
    )


def _sea_record_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            SEA_IFEVAL_RECORD_PATH.read_text(
                encoding="utf-8",
            )
        ),
    )


def _object(
    value: object,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected JSON object")

    return cast(dict[str, object], value)


def _array(
    value: object,
) -> list[object]:
    if not isinstance(value, list):
        raise AssertionError("expected JSON array")

    return cast(list[object], value)


def _write_record(
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


def _mark_as_qualified(
    payload: dict[str, object],
) -> None:
    payload["qualification_status"] = "qualified"
    payload["decision"] = "QUALIFIED"
    payload["blockers"] = []
    payload["required_resolution"] = []
    payload["prohibited_current_use"] = []


def test_loads_checked_in_vmlu_record() -> None:
    record = load_source_qualification(VMLU_RECORD_PATH)

    assert isinstance(
        record,
        SourceQualificationRecord,
    )

    assert record.source_id == "vmlu-vi-mqa-v1-5"
    assert record.qualification_status == "candidate"
    assert record.decision == "BLOCKED"
    assert record.audit.total_rows == 10_880
    assert record.audit.gold_rows == 1_047
    assert record.audit.hidden_gold_rows == 9_833
    assert record.official_source.dataset_license is None

    assert tuple(source_file.name for source_file in record.candidate_mirror.files) == (
        "train.jsonl",
        "valid.jsonl",
        "test.jsonl",
    )


def test_rejects_missing_record(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(
        SourceQualificationLoadError,
        match="Could not read",
    ):
        load_source_qualification(missing_path)


def test_rejects_inconsistent_audit_total(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    audit = _object(payload["audit"])
    audit["total_rows"] = 10_881

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="audit total_rows",
    ):
        load_source_qualification(path)


def test_rejects_duplicate_mirror_file_names(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    mirror = _object(payload["candidate_mirror"])
    files = _array(mirror["files"])
    files.append(files[0])

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="file names must not contain duplicates",
    ):
        load_source_qualification(path)


def test_rejects_unknown_record_fields(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    payload["unexpected_field"] = True

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="unexpected_field",
    ):
        load_source_qualification(path)


def test_live_research_gate_rejects_blocked_source() -> None:
    record = load_source_qualification(VMLU_RECORD_PATH)

    with pytest.raises(
        SourceNotQualifiedError,
        match="decision='BLOCKED'",
    ):
        require_live_research_qualified(record)


def test_qualified_source_requires_dataset_license(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    _mark_as_qualified(payload)

    payload["reviewed_by"] = "reviewer"
    payload["reviewed_at"] = "2026-10-22"

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="dataset_license",
    ):
        load_source_qualification(path)


def test_qualified_source_requires_review(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    _mark_as_qualified(payload)

    official_source = _object(payload["official_source"])
    official_source["dataset_license"] = "Example-Research-License-1.0"

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="review evidence",
    ):
        load_source_qualification(path)


def test_qualified_source_rejects_prohibited_use(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    _mark_as_qualified(payload)

    official_source = _object(payload["official_source"])
    official_source["dataset_license"] = "Example-Research-License-1.0"

    payload["reviewed_by"] = "reviewer"
    payload["reviewed_at"] = "2026-10-22"
    payload["prohibited_current_use"] = ["Do not use for live research"]

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="prohibited current uses",
    ):
        load_source_qualification(path)


def test_live_research_gate_accepts_complete_record(
    tmp_path: Path,
) -> None:
    payload = _record_payload()
    _mark_as_qualified(payload)

    official_source = _object(payload["official_source"])
    official_source["dataset_license"] = "Example-Research-License-1.0"

    payload["reviewed_by"] = "reviewer"
    payload["reviewed_at"] = "2026-10-22"
    payload["permitted_current_use"] = ["Live research under a frozen manifest"]

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    record = load_source_qualification(path)
    accepted = require_live_research_qualified(record)

    assert accepted is record
    assert accepted.decision == "QUALIFIED"


def test_loads_checked_in_sea_ifeval_record() -> None:
    record = load_source_qualification(
        SEA_IFEVAL_RECORD_PATH,
    )

    assert isinstance(
        record,
        InstructionSourceQualificationRecord,
    )
    assert record.source_id == "sea-ifeval-vi-v1-1"
    assert record.task_family == "instruction"
    assert record.qualification_status == "candidate"
    assert record.decision == "BLOCKED"
    assert record.audit.total_rows == 105
    assert record.audit.unique_ids == 105
    assert record.audit.duplicate_id_rows == 0
    assert len(record.observed_schema.instruction_ids) == 21
    assert record.observed_schema.evaluator_version == "sea-ifeval-v1.1+sea-helm-v1.3.0@9be3986d"

    source_file = record.dataset_source.files[0]

    assert source_file.rows == 105
    assert source_file.byte_count == 28_569
    assert source_file.sha256 == "576a68a9c2ea0f05a122bcacffbd36f19aec96a7014afcba3cfbe4b754476889"


def test_live_research_gate_rejects_blocked_sea_ifeval() -> None:
    record = load_source_qualification(
        SEA_IFEVAL_RECORD_PATH,
    )

    with pytest.raises(
        SourceNotQualifiedError,
        match="sea-ifeval-vi-v1-1",
    ):
        require_live_research_qualified(record)


def test_instruction_source_rejects_task_family_mismatch(
    tmp_path: Path,
) -> None:
    payload = _sea_record_payload()
    payload["task_family"] = "multidisciplinary_mcq"

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="task_family",
    ):
        load_source_qualification(path)


def test_instruction_source_rejects_inconsistent_counts(
    tmp_path: Path,
) -> None:
    payload = _sea_record_payload()
    audit = _object(payload["audit"])
    instruction_counts = _array(audit["instruction_id_counts"])
    first_count = _object(instruction_counts[0])
    first_count["rows"] = 4

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="instruction_id_counts rows",
    ):
        load_source_qualification(path)


def test_instruction_source_rejects_duplicate_instruction_ids(
    tmp_path: Path,
) -> None:
    payload = _sea_record_payload()
    observed_schema = _object(payload["observed_schema"])
    instruction_ids = _array(observed_schema["instruction_ids"])
    instruction_ids.append(instruction_ids[0])

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="instruction_ids must not contain duplicates",
    ):
        load_source_qualification(path)


def test_instruction_source_requires_complete_review_pair(
    tmp_path: Path,
) -> None:
    payload = _sea_record_payload()
    payload["reviewed_by"] = "reviewer"

    path = tmp_path / "qualification.json"
    _write_record(path, payload)

    with pytest.raises(
        SourceQualificationLoadError,
        match="must be declared together",
    ):
        load_source_qualification(path)
