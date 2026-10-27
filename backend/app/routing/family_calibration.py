"""DEV-only classifier/Platt/threshold fitting for a frozen serving engine."""

import itertools
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from app.contracts.dtos import ChatRequest
from app.routing.task_groups import TaskGroupPolicy, content_hash


def probability(score: float, values: list[float]) -> float:
    a, b = values
    z = a * math.log(max(1e-9, score) / max(1e-9, 1 - score)) + b
    return 1 / (1 + math.exp(-max(-60, min(60, z))))


def fit_dev(rows: list[dict[str, Any]], engine: Any, originals: dict[str, str]) -> dict[str, Any]:
    if not rows or any(r["split"] == "holdout" for r in rows):
        raise ValueError("DEV-only fit; HOLDOUT is prohibited")
    artifact = engine.artifact
    if not artifact:
        raise ValueError("Frozen serving artifact required")
    reference = artifact.reference_config_id
    candidates = [p.config_id for p in artifact.predictors]
    current = {p.config_id: p.threshold for p in artifact.predictors}
    train = [r for r in rows if r["split"] == "train"]
    groups = {}
    for r in rows:
        if r["group_id"] in groups and groups[r["group_id"]] != r["split"]:
            raise ValueError("Source group crosses DEV splits")
        groups[r["group_id"]] = r["split"]
    families = sorted({r["domain"] for r in rows})
    if len(families) != 3 or any(sum(r["domain"] == f for r in train) < 100 for f in families):
        raise ValueError("Complete independent TRAIN required")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=12000, sublinear_tf=False)
    matrix = vectorizer.fit_transform([originals[r["task_id"]] for r in train])
    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    model.fit(matrix, [r["domain"] for r in train])
    classifier = {
        "vocabulary": {k: int(v) for k, v in vectorizer.vocabulary_.items()},
        "idf": vectorizer.idf_.tolist(),
        "coefficients": model.coef_.tolist(),
        "intercepts": model.intercept_.tolist(),
        "classes": model.classes_.tolist(),
        "minimum_confidence": 0.80,
        "minimum_margin": 0.20,
        "minimum_text_similarity": 0.15,
        "train_vectors": [
            {
                str(i): float(v)
                for i, v in zip(matrix.getrow(n).indices, matrix.getrow(n).data, strict=True)
            }
            for n in range(len(train))
        ],
    }
    classification = TaskGroupPolicy(Path("__offline_family_classifier__"), None)
    classification.bundle = {"classifier": classifier, "profiles": {}}
    scored = []
    from app.routing.ml.multi_training import MultiSample

    for raw in rows:
        row = MultiSample.model_validate(raw)
        scores = {c: engine.score(c, row.context(), False, False) for c in candidates}
        observations = {o.config_id: o for o in row.observations}
        order = sorted(
            candidates,
            key=lambda c: (
                next(x for x in artifact.configurations if x.config_id == c).max_output_tokens,
                c,
            ),
        )
        # Bound-cost order must be supplied by actual serving pricing; measured
        # per-response cost must not influence a decision before generation.
        scored.append((row, scores, observations, order))
    profiles, reports = {}, {}
    for family in families:
        calibration = [x for x in scored if x[0].domain == family and x[0].split == "calibration"]
        threshold = [x for x in scored if x[0].domain == family and x[0].split == "threshold"]
        if len(calibration) < 50 or len(threshold) < 50:
            raise ValueError("Complete calibration and threshold groups required")
        platt = {}
        counts = {}
        for c in candidates:
            y = [int(x[2][c].qualified) for x in calibration]
            counts[c] = dict(Counter(y))
            if min(y.count(0), y.count(1)) < 10:
                continue
            logits = np.asarray(
                [[math.log(max(1e-9, x[1][c]) / max(1e-9, 1 - x[1][c]))] for x in calibration]
            )
            fitted = LogisticRegression(C=1.0, max_iter=1000, random_state=42).fit(logits, y)
            platt[c] = [float(fitted.coef_[0][0]), float(fitted.intercept_[0])]
        reports[family] = {
            "calibration_class_counts": counts,
            "eligible_candidates": sorted(platt),
            "decision": "retain_current_policy",
        }
        if not platt:
            reports[family]["reason"] = "CALIBRATION_NEEDS_10_EACH_CLASS"
            continue
        # Optimize only the deterministic, observable classification assignment.
        assigned = []
        for x in threshold:
            text = originals[x[0].task_id]
            task = classification.classify(
                ChatRequest(
                    session_id="offline",
                    client_request_id=x[0].task_id,
                    message=text,
                    mode="optimized",
                )
            )
            if task["family"] != family or task["source"] == "observable_shadow":
                continue
            assigned.append(x)
        if len(assigned) < 25:
            reports[family]["reason"] = "CLASSIFIER_THRESHOLD_COVERAGE_INSUFFICIENT"
            continue
        configs = sorted(platt)
        grids = {
            c: sorted(
                {
                    1.0,
                    0.5,
                    0.6,
                    0.7,
                    0.8,
                    0.85,
                    0.9,
                    0.92,
                    0.95,
                    0.975,
                    0.99,
                    *[probability(x[1][c], platt[c]) for x in assigned],
                }
            )
            for c in configs
        }
        best = None
        # Rates are frozen in measured dataset provenance by the caller.
        rates = getattr(engine, "family_rates", None)
        if not rates:
            raise ValueError("Reviewed cost rates required")

        def choose(x, values, calibrated, rates=rates, platt=platt):
            row, scores, _, _ = x
            bound = sum(len(m.content.encode()) + 64 for m in row.messages) + 128

            costs = {
                c: Decimal(bound) * rates[c][0]
                + Decimal(
                    next(m.max_output_tokens for m in artifact.configurations if m.config_id == c)
                )
                * rates[c][1]
                for c in (*candidates, reference)
            }
            ordered = sorted(values, key=lambda c: (costs[c], c))
            for c in ordered:
                score = probability(scores[c], platt[c]) if calibrated else scores[c]
                if costs[c] <= costs[reference] and score >= values[c]:
                    return c
            return reference

        prior = [choose(x, current, False) for x in assigned]
        for values in itertools.product(*(grids[c] for c in configs)):
            thresholds = dict(zip(configs, values, strict=True))
            selected = [choose(x, thresholds, True) for x in assigned]
            regression = sum(
                x[2][old].qualified and not x[2][new].qualified
                for x, old, new in zip(assigned, prior, selected, strict=True)
            )
            correct = sum(x[2][new].qualified for x, new in zip(assigned, selected, strict=True))
            old_correct = sum(x[2][old].qualified for x, old in zip(assigned, prior, strict=True))
            cost = sum(
                (x[2][new].usd for x, new in zip(assigned, selected, strict=True)), Decimal(0)
            )
            old_cost = sum(
                (x[2][old].usd for x, old in zip(assigned, prior, strict=True)), Decimal(0)
            )
            if regression or correct < old_correct or cost >= old_cost:
                continue
            key = (cost, -sum(values))
            if best is None or key < best[0]:
                best = (key, thresholds, selected, correct, str(old_cost))
        if best:
            profiles[family] = {
                "thresholds": best[1],
                "platt": platt,
                "quality_fallbacks": [],
                "scope": "single_turn_no_memory_no_tools",
                "grader_review_id": "source-span-numeric-adapters-v1",
            }
            reports[family].update(
                decision="candidate_requires_fresh_holdout_and_pilot",
                thresholds=best[1],
                threshold_groups=len(assigned),
                correct=best[3],
                distribution=dict(Counter(best[2])),
                cost_usd=str(best[0][0]),
                prior_cost_usd=best[4],
            )
        else:
            reports[family]["reason"] = "NO_DEV_QUALITY_AND_COST_GAIN"
    bundle = {
        "version": "task-groups-v1",
        "policy_version": "family-calibration-v1",
        "ml_artifact_hash": engine.hash,
        "configuration_hashes": artifact.configuration_hashes,
        "costs_hash": artifact.costs_hash,
        "classifier": classifier,
        "profiles": profiles,
    }
    return {
        "bundle_candidate": bundle,
        "dev_report": reports,
        "frozen_candidate_sha256": content_hash(bundle),
        "holdout_read": False,
        "serving_activation": False,
    }
