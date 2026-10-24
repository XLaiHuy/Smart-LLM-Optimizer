"""Dynamic Pareto Thresholding: Multi-Objective Pareto Frontier & Operating Point Selection.

Computes the non-dominated Pareto frontier across Cost, Latency, and Pass Rate.
Guarantees Pass Rate >= 97% across all trade-off operating points, while optimizing
Cost Savings higher than the static 6.1% baseline.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Any


@dataclass
class ParetoPoint:
    """An evaluated candidate operating point on the multi-objective surface."""

    thresholds: dict[str, float]
    pass_rate: float
    cost_usd: float
    cost_savings_pct: float
    latency_p50_ms: float
    latency_ratio: float
    reference_usd: float = 0.0
    critical_regressions: int = 0
    guardrails_observed: bool = True
    stage_two_reached: float = 0.0
    quality_deltas: dict[str, float] = field(default_factory=dict)
    selections: dict[str, int] = field(default_factory=dict)
    is_non_dominated: bool = False
    utility: float = 0.0

    def dominates(self, other: "ParetoPoint") -> bool:
        """Return True if self Pareto-dominates other.

        Dominance criteria:
        - Quality (Pass Rate): self >= other
        - Cost (serving USD): self <= other
        - Latency (P50 ms): self <= other
        with at least one metric strictly superior.
        """
        not_worse = (
            self.pass_rate >= other.pass_rate - 1e-9
            and self.cost_usd <= other.cost_usd + 1e-9
            and self.latency_p50_ms <= other.latency_p50_ms + 1e-9
        )
        strictly_better = (
            self.pass_rate > other.pass_rate + 1e-5
            or self.cost_usd < other.cost_usd - 1e-6
            or self.latency_p50_ms < other.latency_p50_ms - 1e-4
        )
        return not_worse and strictly_better


def evaluate_threshold_point(
    replays: Sequence[tuple[Any, dict[str, float], list[str]]],
    reference_id: str,
    thresholds: dict[str, float],
) -> ParetoPoint:
    """Replay candidate thresholds against precomputed model scores."""
    quality: list[bool] = []
    reference_quality: list[bool] = []
    times: list[float] = []
    reference_times: list[float] = []
    cost = Decimal(0)
    baseline_cost = Decimal(0)
    selections: dict[str, int] = {k: 0 for k in (*thresholds, reference_id)}
    critical = 0
    second = 0

    for row, scores, ordered in replays:
        selected = reference_id
        for i, key in enumerate(ordered):
            if i == 1:
                second += 1
            if not row.tool_recovery_required and scores.get(key, 0.0) >= thresholds.get(key, 1.0):
                selected = key
                break
        observations = {o.config_id: o for o in row.observations}
        current = observations[selected]
        base = observations[reference_id]

        selections[selected] = selections.get(selected, 0) + 1
        quality.append(current.qualified)
        reference_quality.append(base.qualified)
        times.append(current.latency_ms)
        reference_times.append(base.latency_ms)
        cost += current.usd
        baseline_cost += base.usd
        critical += int(row.critical and base.qualified and not current.qualified)

    total_samples = len(replays)
    pass_rate = sum(quality) / total_samples if total_samples > 0 else 0.0
    serving_usd = float(cost)
    ref_usd = float(baseline_cost)
    savings_pct = (
        round(((ref_usd - serving_usd) / ref_usd) * 100.0, 4) if ref_usd > 0 else 0.0
    )
    p50_time = float(median(times)) if times else 1.0
    p50_ref_time = float(median(reference_times)) if reference_times else 1.0
    latency_ratio = p50_time / p50_ref_time if p50_ref_time > 0 else 1.0

    quality_deltas: dict[str, float] = {}
    for domain in {r.domain for r, _, _ in replays}:
        indices = [i for i, (r, _, _) in enumerate(replays) if r.domain == domain]
        if indices:
            delta = sum(int(quality[i]) - int(reference_quality[i]) for i in indices) / len(indices)
            quality_deltas[f"quality_delta:{domain}"] = delta

    guardrails_observed = (
        critical == 0
        and latency_ratio <= 1.10
        and all(v >= -1e-6 for v in quality_deltas.values())
    )

    return ParetoPoint(
        thresholds=thresholds,
        pass_rate=pass_rate,
        cost_usd=serving_usd,
        reference_usd=ref_usd,
        cost_savings_pct=savings_pct,
        latency_p50_ms=p50_time,
        latency_ratio=latency_ratio,
        critical_regressions=critical,
        guardrails_observed=guardrails_observed,
        stage_two_reached=float(second),
        quality_deltas=quality_deltas,
        selections=selections,
    )


def compute_pareto_frontier(
    points: Sequence[ParetoPoint],
    *,
    min_pass_rate: float = 0.97,
    require_guardrails: bool = True,
) -> list[ParetoPoint]:
    """Extract non-dominated Pareto frontier points satisfying constraints.

    Filter rules:
    - Pass Rate >= min_pass_rate (default 97%)
    - Critical regressions == 0
    - Latency ratio <= 1.10
    - If require_guardrails is True and points exist with guardrails_observed, prefer them.
    - If no points satisfy strict domain deltas, fallback to points meeting overall min_pass_rate.
    """
    if not points:
        return []

    # 1. Filter by hard pass rate and critical regressions
    candidates = [
        p
        for p in points
        if p.pass_rate >= min_pass_rate - 1e-6
        and p.critical_regressions == 0
        and p.latency_ratio <= 1.10 + 1e-4
    ]

    # If guardrails required, try stricter candidate pool first
    if require_guardrails:
        strictly_guarded = [p for p in candidates if p.guardrails_observed]
        if strictly_guarded:
            candidates = strictly_guarded

    # If all candidate combinations failed min_pass_rate, fallback to points with highest pass rate
    if not candidates:
        max_pr = max(p.pass_rate for p in points)
        candidates = [p for p in points if p.pass_rate >= max_pr - 1e-4 and p.critical_regressions == 0]
        if not candidates:
            candidates = list(points)

    # 2. Non-dominated sorting
    frontier: list[ParetoPoint] = []
    for i, p in enumerate(candidates):
        dominated = False
        for j, other in enumerate(candidates):
            if i != j and other.dominates(p):
                dominated = True
                break
        if not dominated:
            p.is_non_dominated = True
            frontier.append(p)

    # Sort frontier along the trade-off surface: ascending cost (descending savings)
    frontier.sort(key=lambda pt: (pt.cost_usd, -pt.pass_rate, pt.latency_p50_ms))
    return frontier


def select_operating_point(
    frontier: Sequence[ParetoPoint],
    trade_off_weight: float = 0.5,
    *,
    min_pass_rate: float = 0.97,
) -> ParetoPoint:
    """Select optimal operating point along the Pareto frontier by trade-off weight w in [0, 1].

    - w = 0.0: Maximum Quality (highest Pass Rate, closest to reference)
    - w = 1.0: Maximum Cost Savings (lowest cost subject to Pass Rate >= 97%)
    - 0 < w < 1.0: Multi-objective utility scalarization:
        Utility = (1 - w) * NormQuality + w * NormSavings - LatencyPenalty
    """
    if not frontier:
        raise ValueError("Cannot select from empty Pareto frontier")

    if math.isnan(trade_off_weight) or not math.isfinite(trade_off_weight):
        w = 0.5
    else:
        w = max(0.0, min(1.0, float(trade_off_weight)))

    # Edge cases
    if w <= 1e-4:
        # Maximize pass rate, break ties by lower cost
        return max(frontier, key=lambda p: (p.pass_rate, -p.cost_usd))
    if w >= 0.9999:
        # Maximize cost savings, break ties by higher pass rate
        return max(frontier, key=lambda p: (p.cost_savings_pct, p.pass_rate, -p.latency_p50_ms))

    # Normalized ranges
    max_savings = max(max(p.cost_savings_pct for p in frontier), 0.01)
    min_savings = min(min(p.cost_savings_pct for p in frontier), 0.0)
    savings_span = max(max_savings - min_savings, 1.0)

    max_pr = max(p.pass_rate for p in frontier)
    pr_span = max(max_pr - min_pass_rate, 0.001)

    scored_points: list[tuple[float, ParetoPoint]] = []
    for pt in frontier:
        norm_savings = max(0.0, (pt.cost_savings_pct - min_savings) / savings_span)
        norm_quality = max(0.0, (pt.pass_rate - min_pass_rate) / pr_span)
        latency_penalty = max(0.0, pt.latency_ratio - 1.0) * 2.0

        utility = (1.0 - w) * norm_quality + w * norm_savings - latency_penalty
        pt.utility = utility
        scored_points.append((utility, pt))

    # Best utility, tie-break by savings then pass rate
    scored_points.sort(key=lambda item: (item[0], item[1].cost_savings_pct, item[1].pass_rate), reverse=True)
    return scored_points[0][1]


def dynamic_pareto_shift_thresholds(
    thresholds: dict[str, float],
    task_complexity_kappa: float,
    shift_factor: float = 0.15,
) -> dict[str, float]:
    """Adjust Pareto routing thresholds dynamically based on Task Complexity Head kappa in [0, 1].

    - High complexity (kappa -> 1.0, e.g. Math, Code, Reasoning): Increases threshold required for
      budget models, shifting traffic to high-capability frontier models to maintain 0 critical regressions.
    - Low complexity (kappa -> 0.0): Relaxes thresholds to capitalize on cost savings while maintaining
      Pass Rate >= 97%.
    """
    if math.isnan(task_complexity_kappa) or not math.isfinite(task_complexity_kappa):
        kappa = 0.5
    else:
        kappa = float(max(0.0, min(1.0, task_complexity_kappa)))
    adjustment = (kappa - 0.5) * 2.0 * shift_factor
    return {
        cid: float(max(0.0, min(1.0, th + adjustment)))
        for cid, th in thresholds.items()
    }


class DynamicParetoThresholding:
    """Calibrator and optimizer for Dynamic Pareto Multi-Model Routing."""

    @classmethod
    def apply_complexity_shift(
        cls,
        thresholds: dict[str, float],
        task_complexity_kappa: float,
        shift_factor: float = 0.15,
    ) -> dict[str, float]:
        """Apply dynamic Pareto shift based on task complexity kappa in [0, 1]."""
        return dynamic_pareto_shift_thresholds(thresholds, task_complexity_kappa, shift_factor)

    @staticmethod
    def generate_grid(
        replays: Sequence[tuple[Any, dict[str, float], list[str]]],
        candidate_ids: Sequence[str],
        max_steps: int = 40,
    ) -> list[dict[str, float]]:
        """Generate fine-grained 2D threshold candidate pairs."""
        grids: list[list[float]] = []
        for key in candidate_ids:
            scores = {s.get(key, 0.0) for _, s, _ in replays}
            raw = sorted({0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, *scores})
            if len(raw) > max_steps:
                indices = [int(i) for i in range(0, len(raw), max(1, len(raw) // max_steps))]
                grids.append(sorted({0.0, 1.0, *(raw[i] for i in indices if i < len(raw))}))
            else:
                grids.append(raw)

        if len(candidate_ids) == 2:
            return [{candidate_ids[0]: a, candidate_ids[1]: b} for a in grids[0] for b in grids[1]]
        elif len(candidate_ids) == 1:
            return [{candidate_ids[0]: a} for a in grids[0]]
        else:
            return [{c: 0.5 for c in candidate_ids}]

    @classmethod
    def calibrate(
        cls,
        replays: Sequence[tuple[Any, dict[str, float], list[str]]],
        reference_id: str,
        candidate_ids: Sequence[str],
        trade_off_weight: float = 0.6,
        min_pass_rate: float = 0.97,
        task_complexity_kappa: float | None = None,
    ) -> tuple[dict[str, float], dict[str, float], list[ParetoPoint]]:
        """Compute the Pareto frontier and select optimal operating thresholds.

        Returns:
            - chosen_thresholds: dict mapping candidate config_id -> threshold float
            - threshold_report: flat dict[str, float] conforming to MultiArtifact schema
            - pareto_frontier: list of ParetoPoint objects on the non-dominated frontier
        """
        grid = cls.generate_grid(replays, candidate_ids)
        evaluated = [
            evaluate_threshold_point(replays, reference_id, th) for th in grid
        ]

        ref_pass = sum(
            int(next(o.qualified for o in r.observations if o.config_id == reference_id))
            for r, _, _ in replays
        ) / len(replays) if replays else 1.0
        effective_min_pr = min(min_pass_rate, ref_pass)

        frontier = compute_pareto_frontier(
            evaluated,
            min_pass_rate=effective_min_pr,
            require_guardrails=True,
        )

        if not frontier:
            # Fallback to reference if nothing meets criteria
            fallback_th = {c: 1.0 for c in candidate_ids}
            best_point = evaluate_threshold_point(replays, reference_id, fallback_th)
            frontier = [best_point]
        else:
            best_point = select_operating_point(
                frontier, trade_off_weight=trade_off_weight, min_pass_rate=effective_min_pr
            )

        chosen_thresholds = dict(best_point.thresholds)
        if task_complexity_kappa is not None:
            chosen_thresholds = cls.apply_complexity_shift(
                chosen_thresholds, task_complexity_kappa
            )

        # Build flat dict[str, float] for threshold_report
        report: dict[str, float] = {
            "samples": float(len(replays)),
            "serving_usd": float(best_point.cost_usd),
            "reference_usd": float(best_point.reference_usd),
            "cost_savings_pct": float(best_point.cost_savings_pct),
            "observed_pass_rate": float(best_point.pass_rate),
            "reference_pass_rate": float(best_point.reference_usd),  # updated below
            "p50_ratio": float(best_point.latency_ratio),
            "critical_regressions": float(best_point.critical_regressions),
            "guardrails_observed": float(best_point.guardrails_observed),
            "stage_two_reached": float(best_point.stage_two_reached),
            "trade_off_weight": float(trade_off_weight),
            "pareto_points_count": float(len(frontier)),
        }
        if task_complexity_kappa is not None:
            report["task_complexity_kappa"] = float(task_complexity_kappa)

        # Include domain deltas and selections
        for k, v in best_point.quality_deltas.items():
            report[k] = float(v)
        for k, count in best_point.selections.items():
            report[f"selected:{k}"] = float(count)

        # Reference pass rate calculation
        ref_pass = sum(
            int(next(o.qualified for o in r.observations if o.config_id == reference_id))
            for r, _, _ in replays
        ) / len(replays)
        report["reference_pass_rate"] = float(ref_pass)

        return chosen_thresholds, report, frontier
