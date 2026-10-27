"""Data-only local classifier and independently reviewed per-family profiles.

No bundle or insufficient evidence => observable shadow hints only. Never lower
the serving ML thresholds from task keywords or a self-issued 'passed' flag.
"""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, cast

from app.contracts.dtos import (
    ChatRequest,
    ContextResult,
    RemainingBudget,
    RouteDecision,
    RoutingStage,
    TaskProfile,
)
from app.core.numeric_validation import numeric_answer_verdict
from app.routing.ml.qualification import regression_upper_95

FAMILIES = (
    "simple_conversation",
    "exact_arithmetic",
    "structured_extraction",
    "vietnamese_qa",
    "summarization",
    "memory_recall",
)


def content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def hint(request: ChatRequest) -> dict[str, Any]:
    text = request.message.casefold().strip()
    base = {"family": "unknown", "confidence": None, "source": "observable_shadow"}
    if "```" in text or re.search(
        r"\b(?:python|javascript|sql|code|elbo|chứng minh|thuật toán)\b", text
    ):
        return {**base, "family": "code_reasoning"}
    matches = []
    if numeric_answer_verdict(request.message, "0") is not None:
        matches.append("exact_arithmetic")
    if request.response_schema or re.search(r"\b(?:json|trích xuất|extract)\b", text):
        matches.append("structured_extraction")
    if re.search(r"tóm tắt|summari[sz]e", text):
        matches.append("summarization")
    if re.search(r"(?:nhớ|nhắc lại|remember|recall|tên tôi|hạn chót mới nhất)", text):
        matches.append("memory_recall")
    if re.fullmatch(r"(?:xin chào|chào bạn|hello|hi)[!.\s]*", text):
        matches.append("simple_conversation")
    if len(matches) > 1:
        return {**base, "family": "hybrid"}
    if matches:
        return {**base, "family": matches[0]}
    return base


class TaskGroupPolicy:
    def __init__(self, path: Path, engine: Any) -> None:
        self.bundle: dict[str, Any] | None = None
        self.status = "GROUP_POLICY_MISSING_SHADOW"
        self.engine = engine
        try:
            raw = path.read_bytes()
            if len(raw) > 2_000_000:
                raise ValueError("Bundle too large")
            bundle = json.loads(raw)
            if bundle["version"] != "task-groups-v1" or bundle["ml_artifact_hash"] != engine.hash:
                raise ValueError("Bundle/ML mismatch")
            a = engine.multi.artifact
            if (
                not a
                or bundle["configuration_hashes"] != a.configuration_hashes
                or bundle["costs_hash"] != a.costs_hash
            ):
                raise ValueError("Configuration mismatch")
            classifier = bundle.get("classifier")
            if classifier:
                vocabulary = classifier["vocabulary"]
                classes = classifier["classes"]
                n = len(vocabulary)
                if (
                    not n
                    or n > 30000
                    or sorted(vocabulary.values()) != list(range(n))
                    or len(classes) < 3
                    or len(set(classes)) != len(classes)
                    or set(classes) - set(FAMILIES)
                    or len(classifier["idf"]) != n
                    or len(classifier["coefficients"]) != len(classes)
                    or len(classifier["intercepts"]) != len(classes)
                    or not 0.5 <= classifier["minimum_confidence"] <= 1
                ):
                    raise ValueError("Classifier dimensions")
                for row in [
                    classifier["idf"],
                    classifier["intercepts"],
                    *classifier["coefficients"],
                ]:
                    if not all(math.isfinite(v) for v in row):
                        raise ValueError("Classifier finite values")
                if any(len(row) != n for row in classifier["coefficients"]):
                    raise ValueError("Classifier weights")
            for family, profile in bundle["profiles"].items():
                if family not in FAMILIES:
                    raise ValueError("Unknown family")
                thresholds = profile["thresholds"]
                if set(thresholds) - {p.config_id for p in a.predictors}:
                    raise ValueError("Unknown head")
                if any(not math.isfinite(v) or not 0 <= v <= 1 for v in thresholds.values()):
                    raise ValueError("Threshold")
                for values in profile.get("platt", {}).values():
                    if len(values) != 2 or not all(math.isfinite(v) for v in values):
                        raise ValueError("Calibration")
                self._evidence(path.parent, family, profile, bundle)
            self.bundle = bundle
            self.status = "GROUP_POLICY_READY"
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            self.status = "GROUP_POLICY_INVALID_SHADOW"

    @staticmethod
    def _evidence(
        directory: Path, family: str, profile: dict[str, Any], bundle: dict[str, Any]
    ) -> None:
        path = (directory / profile["evidence_path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Evidence outside bundle")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != profile["evidence_sha256"]:
            raise ValueError("Evidence hash")
        report = json.loads(raw)
        profile_payload = {
            k: v for k, v in profile.items() if k not in ("evidence_path", "evidence_sha256")
        }
        if (
            report["profile_sha256"] != content_hash(profile_payload)
            or report["classifier_sha256"] != content_hash(bundle.get("classifier"))
            or report["ml_artifact_hash"] != bundle["ml_artifact_hash"]
            or report["configuration_hashes"] != bundle["configuration_hashes"]
            or report["costs_hash"] != bundle["costs_hash"]
            or report["latency_scope"] != "serving_e2e"
        ):
            raise ValueError("Evidence must bind complete serving policy")
        rows = report["holdout"]
        groups = {r["group_id"] for r in rows}
        if (
            len(rows) < 100
            or len(groups) != len(rows)
            or groups & set(report["dev_group_ids"])
            or not report["reviewed_by"]
            or not report["grader_review_id"]
            or report["synthetic"]
            or report["family"] != family
            or report["thresholds"] != profile["thresholds"]
        ):
            raise ValueError("Independent evidence required")
        regressions = sum(r["prior_pass"] and not r["policy_pass"] for r in rows)
        if (
            regression_upper_95(regressions, len(groups)) > 0.03
            or sum(r["policy_pass"] for r in rows) < sum(r["prior_pass"] for r in rows)
            or any(r["critical_regression"] for r in rows)
            or not 0 < report["all_in_p50_ratio"] <= 1.10
        ):
            raise ValueError("Quality/latency gate")
        if profile.get("scope") == "single_turn_no_memory_no_tools":
            pilot = report["serving_pilot"]
            pairs = pilot["pairs"]
            # Reject corrupt metrics before comparisons (NaN would silently
            # bypass a gate, and zero baseline latency would divide by zero).
            for pair in pairs:
                for key in ("prior_usd", "policy_usd", "prior_ms", "policy_ms"):
                    value = float(pair[key])
                    if not math.isfinite(value) or value < 0 or (
                        key.endswith("_ms") and value == 0
                    ):
                        raise ValueError("Invalid paired serving measurement")
                if any(
                    type(pair[key]) is not bool
                    for key in ("prior_pass", "policy_pass", "critical_regression")
                ):
                    raise ValueError("Invalid paired quality verdict")
            for key in ("policy_serving_usd", "prior_serving_usd"):
                if not math.isfinite(float(report[key])) or float(report[key]) < 0:
                    raise ValueError("Invalid HOLDOUT serving cost")
            if (
                len(pairs) < 20
                or len({r["pair_id"] for r in pairs}) != len(pairs)
                or pilot["profile_sha256"] != report["profile_sha256"]
                or pilot["classifier_sha256"] != report["classifier_sha256"]
                or pilot["all_costs_resolved"] is not True
                or any(
                    r["critical_regression"] or (r["prior_pass"] and not r["policy_pass"])
                    for r in pairs
                )
                or sum(float(r["policy_usd"]) for r in pairs)
                >= sum(float(r["prior_usd"]) for r in pairs)
                or float(report["policy_serving_usd"]) >= float(report["prior_serving_usd"])
            ):
                raise ValueError("Paired serving quality/cost gate")
            from statistics import median

            if median(r["policy_ms"] for r in pairs) / median(r["prior_ms"] for r in pairs) > 1.10:
                raise ValueError("Paired serving latency gate")
        for config in profile.get("quality_fallbacks", []):
            if config not in bundle["configuration_hashes"]:
                raise ValueError("Unknown escalation configuration")
            outcomes = report["fallback_outcomes"][config]
            if (
                len(outcomes) != len(rows)
                or not all(type(v) is bool for v in outcomes)
                or sum(outcomes) < sum(r["prior_pass"] for r in rows)
                or regression_upper_95(
                    sum(r["prior_pass"] and not v for r, v in zip(rows, outcomes, strict=True)),
                    len(rows),
                )
                > 0.03
            ):
                raise ValueError("Escalation lacks independent quality evidence")

    def classify(self, request: ChatRequest) -> dict[str, Any]:
        result = hint(request)
        if not self.bundle:
            return result
        if result["family"] in ("code_reasoning", "hybrid"):
            return result
        if result["family"] in ("exact_arithmetic", "simple_conversation") or (
            result["family"] == "structured_extraction" and request.response_schema
        ):
            return {**result, "confidence": 1.0, "source": "deterministic_contract_v1"}
        classifier = self.bundle.get("classifier")
        if not classifier:
            return result
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

            vectorizer = TfidfVectorizer(vocabulary=classifier["vocabulary"], ngram_range=(1, 2))
            vectorizer.idf_ = np.asarray(classifier["idf"])
            vector = vectorizer.transform([request.message])
            scores = np.asarray(
                (vector @ np.asarray(classifier["coefficients"]).T)[0]
            ) + np.asarray(classifier["intercepts"])
            scores = np.exp(scores - scores.max())
            scores /= scores.sum()
            index = int(scores.argmax())
            confidence = float(scores[index])
            ordered = np.sort(scores)
            if confidence - float(ordered[-2]) < classifier.get("minimum_margin", 0.0):
                return result
            if classifier.get("train_vectors"):
                sparse = dict(zip(vector.indices, vector.data, strict=True))
                similarity = max(
                    sum(sparse.get(int(i), 0.0) * v for i, v in row.items())
                    for row in classifier["train_vectors"]
                )
                if similarity < classifier.get("minimum_text_similarity", 0.0):
                    return result
            family = classifier["classes"][index]
            if family not in FAMILIES or confidence < classifier["minimum_confidence"]:
                return result
            return {
                "family": family,
                "confidence": confidence,
                "source": "local_tfidf_classifier_v1",
            }
        except (ValueError, KeyError, TypeError, IndexError):
            return result

    def profile(self, task: dict[str, Any]) -> dict[str, Any] | None:
        if not self.bundle or task["source"] == "observable_shadow":
            return None
        profile = cast(dict[str, Any] | None, self.bundle["profiles"].get(task["family"]))
        if (
            profile
            and profile.get("scope") == "single_turn_no_memory_no_tools"
            and task.get("single_turn_empty_memory") is not True
        ):
            return None
        return profile

    def apply(
        self,
        task: dict[str, Any],
        route: RouteDecision,
        prepared: ContextResult,
        profile_features: TaskProfile,
        remaining: RemainingBudget,
    ) -> RouteDecision:
        profile = self.profile(task)
        metadata = dict(
            task_family=task["family"],
            task_confidence=task["confidence"],
            classifier_source=task["source"],
            group_policy_version=self.bundle["policy_version"] if self.bundle else None,
        )
        if not profile or not route.ml_executed:
            return route.model_copy(update=metadata)
        if profile.get("scope") == "single_turn_no_memory_no_tools" and (
            len(prepared.messages) != 1
            or prepared.messages[0].role != "user"
            or prepared.tools
            or prepared.continuation_items
            or profile_features.has_rag_context
            or profile_features.tool_recovery_required
        ):
            return route.model_copy(update=metadata)
        # Reuse serving's already-feasible candidates and cost bounds, never
        # re-admit models that context/capability/budget filtering excluded.
        excluded = {
            e.config_id
            for e in route.exclusions
            if e.reason != "ml_score_below_threshold_or_reference_cheaper"
        }
        prices = {e.config_id: e.upper_usd for e in route.estimates if e.upper_usd is not None}
        selected = None
        stages = []
        for config in sorted(profile["thresholds"], key=lambda c: (prices.get(c, float("inf")), c)):
            if config in excluded or config not in prices:
                continue
            if (
                remaining.deadline_ms is not None
                and self.engine.multi.artifact.latency_ms[config] > remaining.deadline_ms
            ):
                continue
            reference_price = prices.get(self.engine.multi.artifact.reference_config_id)
            if reference_price is not None and prices[config] >= reference_price:
                continue
            score = self.engine.multi.score(
                config,
                prepared,
                profile_features.has_rag_context,
                profile_features.tool_recovery_required,
            )
            a, b = profile.get("platt", {}).get(config, [1.0, 0.0])
            logit = a * math.log(max(1e-9, score) / max(1e-9, 1 - score)) + b
            score = 1 / (1 + math.exp(-max(-60.0, min(60.0, logit))))
            stages.append(
                RoutingStage(
                    config_id=config,
                    score=score,
                    threshold=profile["thresholds"][config],
                    status="passed"
                    if score >= profile["thresholds"][config]
                    else "below_threshold",
                )
            )
            if score >= profile["thresholds"][config]:
                selected = config
                break
        if selected is None:
            selected = self.engine.multi.artifact.reference_config_id
        if selected not in prices or selected in excluded:
            return route.model_copy(update=metadata)
        if (
            remaining.deadline_ms is not None
            and self.engine.multi.artifact.latency_ms[selected] > remaining.deadline_ms
        ):
            return route.model_copy(update=metadata)
        model = next(
            c for c in self.engine.multi.artifact.configurations if c.config_id == selected
        )
        return route.model_copy(
            update={
                **metadata,
                "config_id": selected,
                "model_id": model.model_id,
                "group_profile_applied": True,
                "group_thresholds": profile["thresholds"],
                "stages": tuple(stages),
                "fallback_used": selected == self.engine.multi.artifact.reference_config_id,
                "ml_score": next((s.score for s in stages if s.config_id == selected), None),
                "calibrated_threshold": profile["thresholds"].get(selected),
                "reason": "ROUTE_TASK_GROUP_PROFILE",
                "reason_code": "ROUTE_TASK_GROUP_PROFILE",
            }
        )

    def quality_candidates(self, task: dict[str, Any]) -> set[str]:
        profile = self.profile(task)
        return set(profile.get("quality_fallbacks", [])) if profile else set()
