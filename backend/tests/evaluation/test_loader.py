import hashlib
from pathlib import Path

import pytest

from app.evaluation.cases import (
    EvalCase,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    SourceMetadata,
)
from app.evaluation.loader import CaseLoadError, load_cases


def _case(case_id: str) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="multidisciplinary_mcq",
        source=SourceMetadata(
            suite_name="fixture-suite",
            source_name="local-fixture",
            source_revision="fixture-v1",
            source_record_id=case_id,
            group_id=f"group-{case_id}",
            split="dev",
            language="vi",
            qualification_status="candidate",
        ),
        serving_input=MCQServingInput(
            question="Thủ đô của Việt Nam là gì?",
            options=(
                MCQOption(key="A", text="Huế"),
                MCQOption(key="B", text="Hà Nội"),
            ),
        ),
        evaluator_target=MCQTarget(answer_key="B"),
    )


def _write_cases(
    path: Path,
    cases: tuple[EvalCase, ...],
) -> None:
    content = "\n".join(case.model_dump_json() for case in cases)
    path.write_text(content + "\n", encoding="utf-8")


def test_load_cases_returns_cases_and_exact_file_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    _write_cases(
        path,
        (
            _case("mcq-001"),
            _case("mcq-002"),
        ),
    )

    loaded = load_cases(path)

    assert tuple(case.case_id for case in loaded.cases) == (
        "mcq-001",
        "mcq-002",
    )
    assert loaded.data_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_cases_accepts_matching_expected_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    _write_cases(path, (_case("mcq-001"),))
    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    loaded = load_cases(
        path,
        expected_sha256=expected_hash,
    )

    assert loaded.data_sha256 == expected_hash


def test_load_cases_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    _write_cases(path, (_case("mcq-001"),))

    with pytest.raises(
        CaseLoadError,
        match="SHA-256 mismatch",
    ):
        load_cases(
            path,
            expected_sha256="0" * 64,
        )


def test_load_cases_rejects_duplicate_case_ids(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    duplicate = _case("mcq-001")
    _write_cases(path, (duplicate, duplicate))

    with pytest.raises(
        CaseLoadError,
        match=r"Duplicate case_id 'mcq-001' at line 2",
    ):
        load_cases(path)


def test_load_cases_reports_invalid_line_number(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        _case("mcq-001").model_dump_json() + '\n{"broken":\n',
        encoding="utf-8",
    )

    with pytest.raises(
        CaseLoadError,
        match="Invalid eval case at line 2",
    ):
        load_cases(path)


def test_load_cases_rejects_empty_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(
        CaseLoadError,
        match="at least one case",
    ):
        load_cases(path)
