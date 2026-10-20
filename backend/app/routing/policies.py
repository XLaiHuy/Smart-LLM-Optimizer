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
    TaskProfile,
)
from app.contracts.errors import AppError
from app.core.metering import input_bound


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
    def select(
        self,
        profile: TaskProfile,
        prepared: ContextResult,
        registry: RegistrySnapshot,
        costs: CostSnapshot,
        policy: PolicySnapshot,
        remaining: RemainingBudget,
    ) -> RouteDecision:
        bound = input_bound(prepared.messages)
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
            elif model.endpoint != "responses":
                reason = "unsupported_endpoint"
            elif (
                model.context_window is not None
                and bound + model.max_output_tokens > model.context_window
            ):
                reason = "context_overflow"
            elif profile.requires_structured and not model.structured_output:
                reason = "structured_output_unsupported"
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
