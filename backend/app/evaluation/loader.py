import hashlib
from pathlib import Path

from pydantic import Field, ValidationError

from app.evaluation.cases import EvalCase, EvalModel


class CaseLoadError(ValueError):
    pass


class LoadedCaseSet(EvalModel):
    cases: tuple[EvalCase, ...] = Field(min_length=1)
    data_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()

    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise CaseLoadError("expected_sha256 must contain exactly 64 hexadecimal characters")

    return normalized


def load_cases(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> LoadedCaseSet:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise CaseLoadError(f"Could not read eval cases file: {path}") from exc

    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    if expected_sha256 is not None:
        normalized_expected = _normalize_sha256(expected_sha256)

        if actual_sha256 != normalized_expected:
            raise CaseLoadError(
                f"Eval cases SHA-256 mismatch: expected {normalized_expected}, got {actual_sha256}"
            )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaseLoadError("Eval cases file must be valid UTF-8") from exc

    cases: list[EvalCase] = []
    case_lines: dict[str, int] = {}

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        try:
            case = EvalCase.model_validate_json(line)
        except ValidationError as exc:
            raise CaseLoadError(f"Invalid eval case at line {line_number}") from exc

        previous_line = case_lines.get(case.case_id)
        if previous_line is not None:
            raise CaseLoadError(
                f"Duplicate case_id {case.case_id!r} at line "
                f"{line_number}; first declared at line {previous_line}"
            )

        case_lines[case.case_id] = line_number
        cases.append(case)

    if not cases:
        raise CaseLoadError("Eval cases file must contain at least one case")

    return LoadedCaseSet(
        cases=tuple(cases),
        data_sha256=actual_sha256,
    )
