"""Partial-DEV raw-score threshold exploration; never a serving qualification."""

import itertools
from collections import Counter
from decimal import Decimal
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from app.routing.ml.multi_training import MultiSample


def explore(rows: list[dict[str, Any]], engine: Any, originals: dict[str, str], rates: dict[str, tuple[Decimal, Decimal]]) -> dict[str, Any]:
    if not rows or any(r["split"] not in ("train", "calibration", "threshold") for r in rows):
        raise ValueError("Partial DEV only; HOLDOUT is prohibited")
    if len({r["group_id"] for r in rows}) != len(rows):
        raise ValueError("Independent source groups required")
    families = sorted({r["domain"] for r in rows})
    train = [r for r in rows if r["split"] == "train"]
    if len(families) != 3 or any(sum(r["domain"] == f for r in train) < 50 for f in families):
        raise ValueError("At least fifty TRAIN groups per family for research preview")
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=12000)
    matrix = vectorizer.fit_transform([originals[r["task_id"]] for r in train])
    classifier = LogisticRegression(C=1.0, max_iter=1000, random_state=42).fit(
        matrix, [r["domain"] for r in train]
    )
    artifact = engine.artifact
    candidates = [p.config_id for p in artifact.predictors]
    reference = artifact.reference_config_id
    current = {p.config_id: p.threshold for p in artifact.predictors}
    prepared = []
    for raw in rows:
        if raw["split"] != "threshold":
            continue
        row = MultiSample.model_validate(raw)
        scores = {c: engine.score(c, row.context(), False, False) for c in candidates}
        prob = classifier.predict_proba(vectorizer.transform([originals[row.task_id]]))[0]
        order_prob = np.sort(prob)
        family = (
            str(classifier.classes_[int(prob.argmax())])
            if max(prob) >= 0.80 and order_prob[-1] - order_prob[-2] >= 0.20
            else "unknown"
        )
        bound = sum(len(m.content.encode()) + 64 for m in row.messages) + 128
        prices = {
            c.config_id: Decimal(bound) * rates[c.config_id][0]
            + Decimal(c.max_output_tokens) * rates[c.config_id][1]
            for c in artifact.configurations
        }
        eligible = sorted(
            [c for c in candidates if prices[c] < prices[reference]], key=lambda c: (prices[c], c)
        )
        prior = next((c for c in eligible if scores[c] >= current[c]), reference)
        prepared.append(
            dict(
                row=row,
                scores=scores,
                assigned=family,
                prior=prior,
                order=eligible,
                outcomes={o.config_id: o for o in row.observations},
            )
        )
    reports = {}
    examples: list[dict[str, Any]] = []
    for family in families:
        subset = [x for x in prepared if x["row"].domain == family]
        if len(subset) < 10:
            raise ValueError("Threshold split too small even for exploratory replay")
        old_correct = sum(x["outcomes"][x["prior"]].qualified for x in subset)
        old_cost = sum((x["outcomes"][x["prior"]].usd for x in subset), Decimal(0))
        grids = {
            c: sorted(
                {1.0, current[c], *[x["scores"][c] for x in subset if x["assigned"] == family]}
            )
            for c in candidates
        }
        best = None
        for values in itertools.product(*(grids[c] for c in candidates)):
            thresholds = dict(zip(candidates, values, strict=True))
            selected = [
                next((c for c in x["order"] if x["scores"][c] >= thresholds[c]), reference)
                if x["assigned"] == family
                else x["prior"]
                for x in subset
            ]
            regression = sum(
                x["outcomes"][x["prior"]].qualified and not x["outcomes"][c].qualified
                for x, c in zip(subset, selected, strict=True)
            )
            correct = sum(x["outcomes"][c].qualified for x, c in zip(subset, selected, strict=True))
            cost = sum(
                (x["outcomes"][c].usd for x, c in zip(subset, selected, strict=True)), Decimal(0)
            )
            if regression or correct < old_correct or cost >= old_cost:
                continue
            ranking = (cost, -sum(values))
            if best is None or ranking < best[0]:
                best = (ranking, thresholds, selected, correct)
        report = dict(
            threshold_groups=len(subset),
            recognized_groups=sum(x["assigned"] == family for x in subset),
            prior_correct=old_correct,
            prior_cost_usd=str(old_cost),
            prior_distribution=dict(Counter(x["prior"] for x in subset)),
            decision="retain_current_policy",
            thresholds=current,
            serving_approved=False,
        )
        if best:
            report.update(
                decision="research_candidate_only",
                thresholds=best[1],
                correct=best[3],
                regressions_on_tuning_split=0,
                cost_usd=str(best[0][0]),
                distribution=dict(Counter(best[2])),
                saving_on_tuning_split=float((old_cost - best[0][0]) / old_cost),
            )
            for x, c in zip(subset, best[2], strict=True):
                if c != x["prior"] and sum(e["family"] == family for e in examples) < 4:
                    examples.append(
                        dict(
                            family=family,
                            task_id=x["row"].task_id,
                            prompt=originals[x["row"].task_id],
                            prior=x["prior"],
                            candidate=c,
                            score=x["scores"][c],
                            threshold=best[1].get(c),
                            candidate_pass=x["outcomes"][c].qualified,
                            prior_pass=x["outcomes"][x["prior"]].qualified,
                        )
                    )
        reports[family] = report
    return dict(
        version="partial-dev-threshold-preview-NOT-SERVING",
        ml_artifact_hash=engine.hash,
        classifier_fit_groups=len(train),
        threshold_fit_groups=len(prepared),
        classifier={
            "vocabulary": vectorizer.vocabulary_,
            "idf": vectorizer.idf_.tolist(),
            "coefficients": classifier.coef_.tolist(),
            "intercepts": classifier.intercept_.tolist(),
            "classes": classifier.classes_.tolist(),
        },
        reports=reports,
        examples=examples,
        current_thresholds=current,
        threshold_scale="existing_engine_score; not new Platt-calibrated probability",
        holdout_used=False,
        independent_quality_test=False,
        serving_activation=False,
        warning="Thresholds selected and replayed on the same DEV threshold split. Zero observed regressions here is not a generalization guarantee. Strict 600-DEV qualification is unchanged.",
    )
