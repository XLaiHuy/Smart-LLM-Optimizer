import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation.cases import (
    DatasetSplit,
    EvalCase,
    MCQOption,
    MCQServingInput,
    MCQTarget,
    SourceMetadata,
)
from app.evaluation.manifests import (
    ManifestLoadError,
    load_case_set_manifest,
)


def _case(
    case_id: str,
    *,
    group_id: str = "group-001",
    split: DatasetSplit = "dev",
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        task_family="multidisciplinary_mcq",
        source=SourceMetadata(
            suite_name="fixture-suite",
            source_name="local-fixture",
            source_revision="fixture-v1",
            source_record_id=case_id,
            group_id=group_id,
            split=split,
            language="vi",
            qualification_status="candidate",
        ),
        serving_input=MCQServingInput(
            question="Thủ đô Việt Nam là gì?",
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


def _write_manifest(
    path: Path,
    cases_path: Path,
    cases: tuple[EvalCase, ...],
    **overrides: object,
) -> None:
    payload: dict[str, object] = {
        "schema_version": "eval-case-set-v1",
        "case_set_id": "g1-fixture-case-set-v1",
        "cases_file": cases_path.name,
        "data_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "case_count": len(cases),
        "suite_names": sorted({case.source.suite_name for case in cases}),
        "task_families": sorted({case.task_family for case in cases}),
        "splits": sorted({case.source.split for case in cases}),
        "qualification_statuses": sorted({case.source.qualification_status for case in cases}),
    }
    payload.update(overrides)

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_load_case_set_manifest_resolves_and_validates_cases(
    tmp_path: Path,
) -> None:
    cases = (_case("mcq-001"),)
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"

    _write_cases(cases_path, cases)
    _write_manifest(manifest_path, cases_path, cases)

    resolved = load_case_set_manifest(manifest_path)

    assert resolved.manifest.case_set_id == "g1-fixture-case-set-v1"
    assert resolved.cases_path == cases_path.resolve()
    assert resolved.loaded.cases == cases
    assert resolved.loaded.data_sha256 == hashlib.sha256(cases_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("override", "error_message"),
    [
        ({"case_count": 2}, "case_count mismatch"),
        ({"suite_names": ["other-suite"]}, "suite_names mismatch"),
        (
            {"task_families": ["extractive_qa"]},
            "task_families mismatch",
        ),
        ({"splits": ["holdout"]}, "splits mismatch"),
        (
            {"qualification_statuses": ["qualified"]},
            "qualification_statuses mismatch",
        ),
    ],
)
def test_case_set_manifest_rejects_incorrect_declarations(
    tmp_path: Path,
    override: dict[str, object],
    error_message: str,
) -> None:
    cases = (_case("mcq-001"),)
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"

    _write_cases(cases_path, cases)
    _write_manifest(
        manifest_path,
        cases_path,
        cases,
        **override,
    )

    with pytest.raises(ManifestLoadError, match=error_message):
        load_case_set_manifest(manifest_path)


def test_case_set_manifest_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    cases = (_case("mcq-001"),)
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"

    _write_cases(cases_path, cases)
    _write_manifest(
        manifest_path,
        cases_path,
        cases,
        data_sha256="0" * 64,
    )

    with pytest.raises(
        ManifestLoadError,
        match="SHA-256 mismatch",
    ):
        load_case_set_manifest(manifest_path)


def test_case_set_manifest_rejects_group_split_leakage(
    tmp_path: Path,
) -> None:
    cases = (
        _case(
            "mcq-dev-001",
            group_id="shared-group",
            split="dev",
        ),
        _case(
            "mcq-holdout-001",
            group_id="shared-group",
            split="holdout",
        ),
    )
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"

    _write_cases(cases_path, cases)
    _write_manifest(manifest_path, cases_path, cases)

    with pytest.raises(
        ManifestLoadError,
        match="group_id crosses dataset splits",
    ):
        load_case_set_manifest(manifest_path)


def test_case_set_manifest_rejects_duplicate_declarations(
    tmp_path: Path,
) -> None:
    cases = (_case("mcq-001"),)
    cases_path = tmp_path / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"

    _write_cases(cases_path, cases)
    _write_manifest(
        manifest_path,
        cases_path,
        cases,
        splits=["dev", "dev"],
    )

    with pytest.raises(
        ManifestLoadError,
        match="splits must not contain duplicates",
    ):
        load_case_set_manifest(manifest_path)
