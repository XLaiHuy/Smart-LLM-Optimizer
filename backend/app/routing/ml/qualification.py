"""Offline promotion of measured, independently evaluated router artifacts.

An operator review is an assertion, never inferred from a model's filename or
purpose. Synthetic artifacts remain useful for software testing only.
"""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Literal, TypeGuard

from pydantic import Field

from app.config import ROOT
from app.contracts.dtos import DTO, ContextResult
from app.routing.ml.multi import MultiArtifact, MultiRouterService


class QualificationReview(DTO):
    version: str = "router-live-review-v1"
    artifact_hash: str
    dataset_hash: str
    holdout_hash: str
    configuration_hashes: dict[str, str]
    costs_hash: str
    reviewed_by: str = Field(min_length=3)
    domains: tuple[str, ...] = Field(min_length=1)
    measured_e2e_report_sha256: str
    holdout_report: dict[str, Any]
    ablation_report: dict[str, Any]
    passed: bool


class ResearchAcceptance(DTO):
    """Explicit operator decision, separate from scientific qualification."""

    version: Literal["router-research-acceptance-v1"] = "router-research-acceptance-v1"
    artifact_hash: str
    dataset_hash: str
    configuration_hashes: dict[str, str]
    costs_hash: str
    accepted_by: str = Field(min_length=3)
    accepted_at: str = Field(min_length=10)
    decision: str = Field(min_length=10)
    scope: Literal["development_chat"] = "development_chat"
    formal_qualification_passed: Literal[False] = False
    qualification_report_path: str
    qualification_report_sha256: str


def research_acceptance_failure(engine: MultiRouterService, path: Path | None) -> str | None:
    a = engine.artifact
    if a is None or synthetic_artifact(a) or a.attention is None:
        return "ML_RESEARCH_ARTIFACT_INVALID_FALLBACK"
    if a.purpose != "research_candidate":
        return "ML_RESEARCH_ARTIFACT_INVALID_FALLBACK"
    if path is None:
        return "ML_RESEARCH_ACCEPTANCE_REQUIRED_FALLBACK"
    try:
        receipt = ResearchAcceptance.model_validate_json(path.read_text(encoding="utf-8"))
        report_path = Path(receipt.qualification_report_path)
        report_bytes = (report_path if report_path.is_absolute() else ROOT / report_path).read_bytes()
        report = json.loads(report_bytes)
        if (
            receipt.artifact_hash != engine.hash
            or receipt.dataset_hash != a.dataset_hash
            or receipt.configuration_hashes != a.configuration_hashes
            or receipt.costs_hash != a.costs_hash
            or hashlib.sha256(report_bytes).hexdigest() != receipt.qualification_report_sha256
            or report.get("passed") is not False
        ):
            return "ML_RESEARCH_ACCEPTANCE_MISMATCH_FALLBACK"
    except (OSError, ValueError, TypeError, AttributeError):
        return "ML_RESEARCH_ACCEPTANCE_INVALID_FALLBACK"
    return None


def regression_upper_95(regressions: int, groups: int) -> float:
    from scipy.stats import beta  # type: ignore[import-untyped]

    if groups <= 0 or not 0 <= regressions <= groups:
        raise ValueError("Independent group counts are invalid")
    return (
        float(beta.ppf(0.95, regressions + 1, groups - regressions))
        if regressions < groups
        else 1.0
    )


def synthetic_artifact(artifact: MultiArtifact) -> bool:
    return (
        "synthetic" in artifact.grader_version.lower()
        or artifact.purpose == "software_test"
        or any(c.execution_source != "live" for c in artifact.configurations)
    )


def review_failure(engine: MultiRouterService, path: Path | None) -> str | None:
    a = engine.artifact
    if a is None:
        return "ML_ARTIFACT_MISSING_FALLBACK"
    if synthetic_artifact(a):
        return "ML_SYNTHETIC_EVIDENCE_FALLBACK"
    if a.attention is None:
        return "ML_ATTENTION_REQUIRED_FALLBACK"
    if path is None or not path.is_file():
        return "ML_REVIEW_REQUIRED_FALLBACK"
    try:
        review = QualificationReview.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return "ML_REVIEW_INVALID_FALLBACK"
    if (
        not review.passed
        or review.version != "router-live-review-v1"
        or (
            review.artifact_hash != engine.hash
            or review.dataset_hash != a.dataset_hash
            or review.configuration_hashes != a.configuration_hashes
            or review.costs_hash != a.costs_hash
        )
    ):
        return "ML_REVIEW_MISMATCH_FALLBACK"
    return None


def reviewed_scope_failure(prepared: ContextResult, path: Path) -> str | None:
    """Conservative serving envelope for the measured single-turn source slices.

    General chat, memory, code, tools and retrieved context need their own measured
    protocol. A domain name in a review never grants universal chat coverage.
    """
    try:
        review = QualificationReview.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "ML_REVIEW_INVALID_FALLBACK"
    messages = prepared.messages
    if len(messages) != 1 or messages[0].role != "user" or prepared.tools:
        return "ML_UNREVIEWED_SCOPE_FALLBACK"
    text = messages[0].content
    scope = None
    if "```" not in text:
        if text.endswith("\nGive only the final numeric answer."):
            scope = "math_reasoning"
        elif text.endswith("\nChỉ trả lời một chữ cái trong các lựa chọn."):
            choices = re.findall(r"(?:^|\n)[ \t]*([A-E])[.)][ \t]+", text, re.IGNORECASE)
            if 3 <= len(choices) <= 5 and [c.upper() for c in choices] == list(
                "ABCDE"[: len(choices)]
            ):
                scope = "vietnamese_mcq"
    if scope is None or scope not in review.domains:
        return "ML_UNREVIEWED_SCOPE_FALLBACK"
    return None


def runtime_guard_issues(report: dict[str, Any], ablation: dict[str, Any]) -> list[str]:
    """Provider-only replay latency cannot certify the complete routing policy."""
    issues = []
    ratio = report.get("all_in_p50_ratio")
    ml_ratio = ablation.get("all_in_p50_ratio")

    def valid(value: Any) -> TypeGuard[float]:
        return type(value) in (int, float) and math.isfinite(value) and value > 0

    if not valid(ratio) or ratio > 1.10:
        issues.append("HOLDOUT_LATENCY_GUARD_FAILED")
    if not valid(ml_ratio):
        issues.append("ABLATION_ROUTING_TIMING_REQUIRED")
        return issues
    current, ml = report.get("report", {}), ablation.get("report", {})
    if valid(ratio) and all(
        type(row.get(key)) in (int, float) and math.isfinite(row[key])
        for row in (current, ml)
        for key in ("observed_pass_rate", "serving_usd")
    ):
        if (
            ml["observed_pass_rate"] >= current["observed_pass_rate"]
            and ml["serving_usd"] <= current["serving_usd"]
            and ml_ratio <= ratio
            and (
                ml["observed_pass_rate"] > current["observed_pass_rate"]
                or ml["serving_usd"] < current["serving_usd"]
                or ml_ratio < ratio
            )
        ):
            issues.append("ML_WITHOUT_ATTENTION_DOMINATES")
    return issues


def qualify(
    dev_path: Path,
    holdout_path: Path,
    artifact_path: Path,
    ablation_path: Path,
    e2e_path: Path,
    reviewer: str,
) -> tuple[dict[str, Any], QualificationReview | None]:
    """No provider calls, no writes. Returns reasons rather than promoting on failure."""
    from app.routing.ml.multi_training import MultiDataset
    from app.routing.ml.pilot import timed_evaluate

    dev = MultiDataset.model_validate_json(dev_path.read_text(encoding="utf-8"))
    holdout = MultiDataset.model_validate_json(holdout_path.read_text(encoding="utf-8"))
    engine = MultiRouterService(artifact_path.read_text(encoding="utf-8"))
    baseline = MultiRouterService(ablation_path.read_text(encoding="utf-8"))
    a = engine.artifact
    issues: list[str] = []
    if not a or not baseline.artifact:
        return {"passed": False, "issues": ["ARTIFACT_INVALID"]}, None
    if a.attention is None or baseline.artifact.attention is not None:
        issues.append("PAIRED_ML_AND_ATTENTION_ARTIFACTS_REQUIRED")
    if synthetic_artifact(a) or any(c.execution_source != "live" for c in dev.configurations):
        issues.append("SYNTHETIC_EVIDENCE")
    if (
        hashlib.sha256(dev.model_dump_json().encode()).hexdigest() != a.dataset_hash
        or a.dataset_hash != baseline.artifact.dataset_hash
    ):
        issues.append("TRAINING_DATA_HASH_MISMATCH")
    if (
        a.configuration_hashes != baseline.artifact.configuration_hashes
        or a.costs_hash != baseline.artifact.costs_hash
    ):
        issues.append("ABLATION_CONFIGURATION_MISMATCH")
    for dataset in (dev, holdout):
        if "synthetic" in dataset.grader_version.lower() or dataset.purpose == "software_test":
            issues.append("SYNTHETIC_EVIDENCE")
        if any(
            o.label_source not in ("dataset_gold", "human_verified")
            or not o.response_sha256
            or not o.grader_version
            for row in dataset.samples
            for o in row.observations
        ):
            issues.append("MEASURED_REVIEWED_LABELS_REQUIRED")
    try:
        report = timed_evaluate(holdout, artifact_path.read_text(encoding="utf-8"))
        ablation = timed_evaluate(holdout, ablation_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"passed": False, "issues": [*issues, str(exc)]}, None
    observed = report.get("report", {})
    if not isinstance(observed, dict):
        issues.append("HOLDOUT_REPORT_INVALID")
    else:
        if observed.get("critical_regressions") != 0:
            issues.append("HOLDOUT_CRITICAL_REGRESSION")
        issues.extend(runtime_guard_issues(report, ablation))
        saving = observed.get("serving_usd")
        reference_cost = observed.get("reference_usd")
        if (
            not isinstance(saving, (int, float))
            or not isinstance(reference_cost, (int, float))
            or saving >= reference_cost
        ):
            issues.append("NO_MEASURED_ROUTING_COST_BENEFIT")
    # Replay selected outcomes on independent source groups. The exact one-sided
    # 95% bound avoids the zero-variance bootstrap trap on very small samples.
    from app.routing.ml.multi_training import replay_rows

    groups: dict[str, dict[str, bool]] = {}
    for row, scores, ordered in replay_rows(holdout, engine, holdout.samples):
        selected = a.reference_config_id
        thresholds = {p.config_id: p.threshold for p in a.predictors}
        for config_id in ordered:
            if not row.tool_recovery_required and scores[config_id] >= thresholds[config_id]:
                selected = config_id
                break
        observations = {o.config_id: o for o in row.observations}
        regression = (
            observations[a.reference_config_id].qualified and not observations[selected].qualified
        )
        domain_groups = groups.setdefault(row.domain, {})
        domain_groups[row.group_id] = domain_groups.get(row.group_id, False) or regression
    bounds = {}
    for domain, outcomes in groups.items():
        n, failures = len(outcomes), sum(outcomes.values())
        upper = regression_upper_95(failures, n)
        bounds[domain] = {
            "independent_groups": n,
            "regressions": failures,
            "regression_upper_95": upper,
        }
        if upper > 0.03:
            issues.append(f"INSUFFICIENT_OR_FAILED_DOMAIN_EVIDENCE:{domain}")
    if {r.domain for r in dev.samples} - set(groups):
        issues.append("HOLDOUT_DOMAIN_COVERAGE_MISSING")
    try:
        pilot = json.loads(e2e_path.read_text(encoding="utf-8"))
        if not isinstance(pilot, dict):
            pilot = {}
    except (OSError, ValueError):
        pilot = {}
    if (
        pilot.get("execution_source") != "live"
        or pilot.get("configuration_hashes") != a.configuration_hashes
        or not pilot.get("provider_call_ids")
    ):
        issues.append("MEASURED_E2E_PILOT_REQUIRED")
    if (
        pilot.get("attention_artifact_hash") != engine.hash
        or pilot.get("ml_artifact_hash") != baseline.hash
    ):
        issues.append("E2E_ARTIFACT_HASH_MISMATCH")
    ratio = pilot.get("p50_latency_ratio")
    if not isinstance(ratio, (float, int)) or not 0 < ratio <= 1.10:
        issues.append("E2E_LATENCY_GUARD_FAILED")
    if pilot.get("critical_regressions") != 0:
        issues.append("E2E_CRITICAL_REGRESSION")
    result = {
        "passed": not issues,
        "issues": sorted(set(issues)),
        "domains": bounds,
        "holdout": report,
        "ml_without_attention": ablation,
        "pilot": pilot,
    }
    if issues:
        return result, None
    promoted = a.model_copy(update={"purpose": "qualified_dev"})
    promoted_engine = MultiRouterService(promoted.model_dump_json())
    review = QualificationReview(
        artifact_hash=promoted_engine.hash or "",
        dataset_hash=a.dataset_hash,
        holdout_hash=hashlib.sha256(holdout.model_dump_json().encode()).hexdigest(),
        configuration_hashes=a.configuration_hashes,
        costs_hash=a.costs_hash,
        reviewed_by=reviewer,
        domains=tuple(sorted(groups)),
        measured_e2e_report_sha256=hashlib.sha256(e2e_path.read_bytes()).hexdigest(),
        holdout_report=result,
        ablation_report=ablation,
        passed=True,
    )
    return result, review
