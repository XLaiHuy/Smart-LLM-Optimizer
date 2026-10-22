import hashlib
import random
from decimal import Decimal

from app.contracts.dtos import (
    CandidateExclusion,
    ContextResult,
    CostSnapshot,
    ModelConfiguration,
    PolicySnapshot,
    RegistrySnapshot,
    RemainingBudget,
    RouteDecision,
    RouteEstimate,
    RoutingStage,
    TaskProfile,
)
from app.contracts.errors import AppError
from app.core.metering import input_bound
from app.routing.ml.feedback import RoutingDrift
from app.routing.ml.service import MLRouterService


class RoutingRejected(AppError):
    def __init__(
        self,
        code: str,
        exclusions: tuple[CandidateExclusion, ...],
        estimates: tuple[RouteEstimate, ...],
    ):
        super().__init__(
            code,
            504 if code == "DEADLINE_EXCEEDED" else 413 if code == "CONTEXT_OVERFLOW" else 422,
            "No feasible model/reference",
        )
        self.exclusions, self.estimates = exclusions, estimates


class PolicyRouter:
    def __init__(self, ml: MLRouterService | None = None, drift: RoutingDrift | None = None):
        self.ml = ml or MLRouterService()
        self.drift = drift

    def select(
        self,
        profile: TaskProfile,
        prepared: ContextResult,
        registry: RegistrySnapshot,
        costs: CostSnapshot,
        policy: PolicySnapshot,
        remaining: RemainingBudget,
    ) -> RouteDecision:
        bound = input_bound(prepared.messages, prepared.tools, prepared.continuation_items)
        rates = {r.config_id: r for r in costs.rates}
        excluded: list[CandidateExclusion] = []
        estimates: list[RouteEstimate] = []
        feasible: list[ModelConfiguration] = []
        prices: dict[str, Decimal] = {}
        for model in registry.configurations:
            rate = rates.get(model.config_id)
            upper = (
                (
                    Decimal(bound) * rate.input_per_million
                    + Decimal(model.max_output_tokens) * rate.output_per_million
                )
                / Decimal(1000000)
                if rate
                else None
            )
            estimates.append(
                RouteEstimate(config_id=model.config_id, input_bound=bound, upper_usd=upper)
            )
            reason = None
            if not model.available:
                reason = model.availability_reason
            elif model.endpoint != "responses" and not (
                policy.sandbox and model.endpoint == "gemini_chat_completions"
            ):
                reason = "unsupported_endpoint"
            elif (
                model.context_window is not None
                and bound + model.max_output_tokens > model.context_window
            ):
                reason = "context_overflow"
            elif profile.requires_structured and not model.structured_output:
                reason = "structured_output_unsupported"
            elif prepared.tools and not model.function_calling:
                reason = "function_calling_unsupported"
            elif upper is None:
                reason = "price_unknown"
            elif upper is not None and remaining.usd is not None and upper > remaining.usd:
                reason = "budget_exceeded"
            if reason:
                excluded.append(CandidateExclusion(config_id=model.config_id, reason=reason))
            else:
                feasible.append(model)
                if upper is not None:
                    prices[model.config_id] = upper
        if remaining.deadline_ms is not None and remaining.deadline_ms <= 0:
            raise RoutingRejected("DEADLINE_EXCEEDED", tuple(excluded), tuple(estimates))
        reference = next((m for m in feasible if m.config_id == registry.mock_config_id), None)
        if policy.strategy == "ml_multi_model":
            from app.routing.ml.multi import configuration_hash

            engine = self.ml.multi
            artifact2 = engine.artifact
            why = self.ml.status if artifact2 is None else None
            if artifact2 is None and self.ml.artifact:
                why = "ML_ARTIFACT_FORMAT_MISMATCH_FALLBACK"
            if (
                artifact2
                and not policy.sandbox
                and (not self.ml.live_approved or artifact2.purpose != "qualified_dev")
            ):
                why = "ML_NOT_QUALIFIED_FALLBACK"
            if artifact2 and not why:
                identities = {
                    m.config_id: configuration_hash(m)
                    for m in registry.configurations
                    if m.config_id in artifact2.configuration_hashes
                }
                if (
                    identities != artifact2.configuration_hashes
                    or registry.mock_config_id != artifact2.reference_config_id
                ):
                    why = "ML_MODEL_MISMATCH_FALLBACK"
                elif (
                    costs.version != artifact2.catalog_version
                    or hashlib.sha256(costs.model_dump_json().encode()).hexdigest()
                    != artifact2.costs_hash
                ):
                    why = "ML_CATALOG_CHANGED_FALLBACK"
                elif policy.ml_artifact_hash and policy.ml_artifact_hash != self.ml.hash:
                    why = "ML_ARTIFACT_CHANGED_FALLBACK"
            if why:
                guarded = self.select(
                    profile,
                    prepared,
                    registry,
                    costs,
                    policy.model_copy(update={"strategy": "rule_guarded"}),
                    remaining,
                )
                return guarded.model_copy(
                    update={
                        "reason": why,
                        "reason_code": why,
                        "fallback_used": True,
                        "ml_artifact_hash": self.ml.hash,
                    }
                )
            assert artifact2
            stages = []
            selected2 = None
            for predictor in sorted(
                artifact2.predictors,
                key=lambda p: (prices.get(p.config_id, Decimal("Infinity")), p.config_id),
            ):
                candidate2 = next((m for m in feasible if m.config_id == predictor.config_id), None)
                if (
                    candidate2
                    and remaining.deadline_ms is not None
                    and artifact2.latency_ms[predictor.config_id] > remaining.deadline_ms
                ):
                    excluded.append(
                        CandidateExclusion(
                            config_id=predictor.config_id, reason="deadline_exceeded"
                        )
                    )
                    candidate2 = None
                if not candidate2:
                    stages.append(
                        RoutingStage(
                            config_id=predictor.config_id,
                            threshold=predictor.threshold,
                            status="infeasible",
                        )
                    )
                    continue
                try:
                    score2 = engine.score(
                        predictor.config_id,
                        prepared,
                        profile.has_rag_context,
                        profile.tool_recovery_required,
                    )
                except (ValueError, KeyError, TypeError, IndexError, FloatingPointError):
                    guarded = self.select(
                        profile,
                        prepared,
                        registry,
                        costs,
                        policy.model_copy(update={"strategy": "rule_guarded"}),
                        remaining,
                    )
                    return guarded.model_copy(
                        update={
                            "reason": "ML_INFERENCE_FAILED_FALLBACK",
                            "reason_code": "ML_INFERENCE_FAILED_FALLBACK",
                            "fallback_used": True,
                            "ml_artifact_hash": self.ml.hash,
                            "stages": tuple(stages),
                        }
                    )
                shift = (
                    self.drift.shift(self.ml.hash or "", predictor.config_id)
                    if self.drift and not policy.sandbox
                    else 0.0
                )
                threshold = min(1.0, predictor.threshold + shift)
                passed = (
                    score2 >= threshold
                    and not (shift > 0 and threshold >= 1)
                    and (
                        reference is None
                        or prices[predictor.config_id] <= prices[reference.config_id]
                    )
                )
                stages.append(
                    RoutingStage(
                        config_id=predictor.config_id,
                        score=score2,
                        threshold=threshold,
                        base_threshold=predictor.threshold,
                        drift_shift=shift,
                        status="selected" if passed else "below_threshold_or_reference_cheaper",
                    )
                )
                if passed:
                    selected2 = candidate2
                    break
                excluded.append(
                    CandidateExclusion(
                        config_id=predictor.config_id,
                        reason="ml_score_below_threshold_or_reference_cheaper",
                    )
                )
            selected2 = selected2 or reference
            if (
                selected2
                and remaining.deadline_ms is not None
                and artifact2.latency_ms[selected2.config_id] > remaining.deadline_ms
            ):
                raise RoutingRejected("DEADLINE_EXCEEDED", tuple(excluded), tuple(estimates))
            if selected2 is None:
                reasons = {e.reason for e in excluded if e.config_id == registry.mock_config_id}
                code = (
                    "BUDGET_EXCEEDED"
                    if "budget_exceeded" in reasons
                    else "CONTEXT_OVERFLOW"
                    if "context_overflow" in reasons
                    else "NO_COMPATIBLE_MODEL"
                )
                raise RoutingRejected(code, tuple(excluded), tuple(estimates))
            fallback2 = selected2.config_id == registry.mock_config_id
            reason2 = "ROUTE_ML_MULTI_REFERENCE" if fallback2 else "ROUTE_ML_MULTI_CANDIDATE"
            return RouteDecision(
                config_id=selected2.config_id,
                model_id=selected2.model_id,
                policy_id=policy.policy_id,
                reason=reason2,
                reason_code=reason2,
                fallback_used=fallback2,
                use_original_context=fallback2,
                rules_matched=profile.rules_matched,
                exclusions=tuple(excluded),
                estimates=tuple(estimates),
                stages=tuple(stages),
                ml_artifact_hash=self.ml.hash,
                ml_model_version=artifact2.model_version,
                policy_hash=hashlib.sha256(
                    (policy.model_dump_json() + (self.ml.hash or "")).encode()
                ).hexdigest(),
            )
        if policy.strategy == "ml_router":
            artifact = self.ml.artifact
            why = self.ml.status if artifact is None else None
            if artifact is None and self.ml.multi.artifact:
                why = "ML_ARTIFACT_FORMAT_MISMATCH_FALLBACK"
            if (
                artifact
                and not policy.sandbox
                and (not self.ml.live_approved or artifact.purpose != "qualified_dev")
            ):
                why = "ML_NOT_QUALIFIED_FALLBACK"
            if artifact and not why:
                identities = {m.config_id: m.model_id for m in registry.configurations}
                if (
                    registry.mock_config_id != artifact.reference_config_id
                    or identities.get(artifact.reference_config_id) != artifact.reference_model_id
                    or identities.get(artifact.candidate_config_id) != artifact.candidate_model_id
                ):
                    why = "ML_MODEL_MISMATCH_FALLBACK"
                elif policy.ml_artifact_hash and policy.ml_artifact_hash != self.ml.hash:
                    why = "ML_ARTIFACT_CHANGED_FALLBACK"
            if why:
                guarded = self.select(
                    profile,
                    prepared,
                    registry,
                    costs,
                    policy.model_copy(update={"strategy": "rule_guarded"}),
                    remaining,
                )
                return guarded.model_copy(
                    update={
                        "fallback_used": True,
                        "reason_code": why,
                        "reason": why,
                        "ml_artifact_hash": self.ml.hash,
                    }
                )
            assert artifact
            excluded.extend(
                CandidateExclusion(config_id=m.config_id, reason="ml_model_not_profiled")
                for m in feasible
                if m.config_id not in (artifact.candidate_config_id, artifact.reference_config_id)
            )
            try:
                score = self.ml.score(prepared.messages, profile.has_rag_context)
            except (ValueError, ArithmeticError):
                guarded = self.select(
                    profile,
                    prepared,
                    registry,
                    costs,
                    policy.model_copy(update={"strategy": "rule_guarded"}),
                    remaining,
                )
                return guarded.model_copy(
                    update={
                        "fallback_used": True,
                        "reason_code": "ML_INFERENCE_FAILED_FALLBACK",
                        "reason": "ML_INFERENCE_FAILED_FALLBACK",
                    }
                )
            candidate = next(
                (m for m in feasible if m.config_id == artifact.candidate_config_id), None
            )
            choose_candidate = (
                score >= artifact.threshold
                and candidate is not None
                and (
                    reference is None or prices[candidate.config_id] <= prices[reference.config_id]
                )
            )
            selected = candidate if choose_candidate else reference
            if selected is None:
                reason_set = {e.reason for e in excluded if e.config_id == registry.mock_config_id}
                code = (
                    "BUDGET_EXCEEDED"
                    if "budget_exceeded" in reason_set
                    else "CONTEXT_OVERFLOW"
                    if "context_overflow" in reason_set
                    else "NO_COMPATIBLE_MODEL"
                )
                raise RoutingRejected(code, tuple(excluded), tuple(estimates))
            reason = "ROUTE_ML_CANDIDATE" if choose_candidate else "ROUTE_ML_REFERENCE"
            if not choose_candidate and candidate is not None and score < artifact.threshold:
                excluded.append(
                    CandidateExclusion(
                        config_id=candidate.config_id, reason="ml_score_below_threshold"
                    )
                )
            return RouteDecision(
                config_id=selected.config_id,
                model_id=selected.model_id,
                policy_id=policy.policy_id,
                reason=reason,
                reason_code=reason,
                fallback_used=not choose_candidate,
                use_original_context=not choose_candidate,
                rules_matched=profile.rules_matched,
                exclusions=tuple(excluded),
                estimates=tuple(estimates),
                policy_hash=hashlib.sha256(
                    (policy.model_dump_json() + (self.ml.hash or "")).encode()
                ).hexdigest(),
                evidence_version=policy.evidence_version,
                ml_score=score,
                calibrated_threshold=artifact.threshold,
                ml_artifact_hash=self.ml.hash,
                ml_model_version=artifact.model_version,
            )
        fallback = False
        reason = policy.strategy
        evidence = {
            e.config_id: e
            for e in policy.evidence
            if e.domain == profile.domain and (policy.sandbox or e.provenance == "qualified_dev")
        }
        if not policy.sandbox or policy.strategy == "rule_guarded":
            eligible = []
            for model in feasible:
                item = evidence.get(model.config_id)
                why = (
                    "quality_evidence_unknown"
                    if not item or item.qualifies is not True
                    else "latency_evidence_unknown"
                    if item.latency_ms is None
                    else "deadline_exceeded"
                    if remaining.deadline_ms is not None and item.latency_ms > remaining.deadline_ms
                    else None
                )
                if why:
                    excluded.append(CandidateExclusion(config_id=model.config_id, reason=why))
                else:
                    eligible.append(model)
            if policy.strategy == "fixed_reference" or (
                not policy.sandbox and not policy.flags.router
            ):
                selected = reference
                reason = "fixed_reference"
            elif eligible:
                selected = min(
                    eligible,
                    key=lambda m: (
                        prices.get(m.config_id, Decimal("Infinity")),
                        evidence[m.config_id].latency_ms or 0,
                        m.config_id,
                    ),
                )
            else:
                selected, fallback, reason = reference, True, "baseline_quality_uncertain"
                if reference and reference.config_id in evidence:
                    latency = evidence[reference.config_id].latency_ms
                    if (
                        latency is not None
                        and remaining.deadline_ms is not None
                        and latency > remaining.deadline_ms
                    ):
                        raise RoutingRejected(
                            "DEADLINE_EXCEEDED", tuple(excluded), tuple(estimates)
                        )
        elif policy.strategy == "fixed_reference":
            selected = reference
        elif policy.strategy == "fixed_candidate":
            selected = next((m for m in feasible if m.config_id == policy.candidate_id), None)
        elif policy.strategy == "random_feasible":
            selected = (
                random.Random(policy.seed).choice(sorted(feasible, key=lambda m: m.config_id))
                if feasible
                else None
            )
        else:
            selected = (
                min(
                    feasible,
                    key=lambda m: (prices.get(m.config_id, Decimal("Infinity")), m.config_id),
                )
                if feasible
                else None
            )
        if selected is None:
            reasons = {e.reason for e in excluded}
            code = (
                "BUDGET_EXCEEDED"
                if "budget_exceeded" in reasons
                else "CONTEXT_OVERFLOW"
                if "context_overflow" in reasons
                else "NO_COMPATIBLE_MODEL"
            )
            raise RoutingRejected(code, tuple(excluded), tuple(estimates))
        return RouteDecision(
            model_id=selected.model_id,
            config_id=selected.config_id,
            policy_id=policy.policy_id,
            reason=reason,
            fallback_used=fallback,
            use_original_context=fallback,
            rules_matched=profile.rules_matched,
            exclusions=tuple(excluded),
            estimates=tuple(estimates),
            policy_hash=hashlib.sha256(policy.model_dump_json().encode()).hexdigest(),
            evidence_version=policy.evidence_version,
        )
