"""Independent fit/calibration/threshold splits; replay, never paid execution."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.sparse import csr_matrix, hstack  # type: ignore[import-untyped]
from sklearn.ensemble import GradientBoostingClassifier  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore[import-untyped]

from app.contracts.dtos import (
    DTO,
    ContextResult,
    CostSnapshot,
    FeatureFlags,
    Message,
    ModelConfiguration,
    OptimizationState,
    PolicySnapshot,
    RegistrySnapshot,
    RemainingBudget,
    ToolDefinition,
)
from app.contracts.representations import EncoderSpec
from app.routing.features import extract_context_features
from app.routing.ml.attention import ATTENTION_FEATURES
from app.routing.ml.independence import content_key
from app.routing.ml.multi import (
    HYBRID_FEATURE_NAMES,
    HYBRID_FEATURE_VERSION,
    LinearPredictor,
    MultiArtifact,
    MultiRouterService,
    OOFFold,
    configuration_hash,
    feature_view,
    numeric_view,
)
from app.routing.ml.service import VectorizerState, input_hash
from app.routing.ml.tree_compiler import compile_sklearn_gbdt, evaluate_forest_prob


class Observation(DTO):
    config_id: str
    qualified: bool
    usd: Decimal = Field(ge=0, allow_inf_nan=False)
    latency_ms: float = Field(gt=0, allow_inf_nan=False)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    label_source: (
        Literal["dataset_gold", "human_verified", "teacher_judged", "synthetic_verified"] | None
    ) = None
    grader_version: str | None = None
    grade_metrics: dict[str, float] = Field(default_factory=dict)
    response_sha256: str | None = None


class MultiSample(DTO):
    task_id: str
    group_id: str
    domain: str
    split: Literal["train", "calibration", "threshold", "holdout"]
    messages: tuple[Message, ...] = Field(min_length=1)
    observations: tuple[Observation, ...]
    tools: tuple[ToolDefinition, ...] = ()
    has_rag_context: bool = False
    tool_recovery_required: bool = False
    critical: bool = False
    max_usd: Decimal | None = Field(default=None, gt=0)
    deadline_ms: float | None = Field(default=None, gt=0)

    def context(self) -> ContextResult:
        return ContextResult(
            messages=self.messages,
            tools=self.tools,
            provenance=(),
            state=OptimizationState(module="context", status="disabled", reason="offline_replay"),
        )


class MultiDataset(DTO):
    format_version: Literal["router-dataset-v2"]
    version: str
    purpose: Literal["qualified_dev", "qualified_holdout", "software_test", "research_candidate"]
    provenance: str = Field(min_length=1)
    grader_version: str
    configurations: tuple[ModelConfiguration, ModelConfiguration, ModelConfiguration]
    reference_config_id: str
    costs: CostSnapshot
    samples: tuple[MultiSample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def independence(self) -> "MultiDataset":
        ids = {c.config_id for c in self.configurations}
        if (
            len(ids) != 3
            or self.reference_config_id not in ids
            or ids != {r.config_id for r in self.costs.rates}
        ):
            raise ValueError("Exactly three unique configs and complete price rates required")
        groups: dict[str, str] = {}
        hashes: dict[str, str] = {}
        tasks = set()
        for row in self.samples:
            if (
                row.task_id in tasks
                or {o.config_id for o in row.observations} != ids
                or len(row.observations) != 3
            ):
                raise ValueError("Duplicate task or incomplete measured observations")
            tasks.add(row.task_id)
            digest = content_key(row.messages)
            if (
                groups.get(row.group_id, row.split) != row.split
                or hashes.get(digest, row.split) != row.split
            ):
                raise ValueError("Source/input crosses splits")
            groups[row.group_id], hashes[digest] = row.split, row.split
        return self


def replay_rows(
    dataset: MultiDataset, engine: MultiRouterService, rows: tuple[MultiSample, ...]
) -> list[tuple[MultiSample, dict[str, float], list[str]]]:
    # Use the same feasibility filter as serving, then replay measured outcomes.
    from app.routing.policies import PolicyRouter, RoutingRejected

    result = []
    registry = RegistrySnapshot(
        configurations=dataset.configurations, mock_config_id=dataset.reference_config_id
    )
    for row in rows:
        context = row.context()
        profile = extract_context_features(row.messages, row.has_rag_context)
        feasible = []
        for config in dataset.configurations:
            if (
                engine.artifact
                and row.deadline_ms is not None
                and engine.artifact.latency_ms[config.config_id] > row.deadline_ms
            ):
                continue
            try:
                route = PolicyRouter().select(
                    profile,
                    context,
                    registry,
                    dataset.costs,
                    PolicySnapshot(
                        policy_id="fixed",
                        strategy="fixed_candidate",
                        candidate_id=config.config_id,
                        flags=FeatureFlags(router=True),
                        sandbox=True,
                    ),
                    RemainingBudget(usd=row.max_usd, deadline_ms=row.deadline_ms),
                )
                estimate = next(
                    e.upper_usd for e in route.estimates if e.config_id == config.config_id
                )
                feasible.append((config.config_id, estimate or Decimal(0)))
            except RoutingRejected:
                pass
        if dataset.reference_config_id not in {c for c, _ in feasible}:
            raise ValueError(
                "Research calibration/evaluation requires a feasible reference; boundary refusals belong in functional fixtures"
            )
        score = (
            {
                p.config_id: engine.score(
                    p.config_id, context, row.has_rag_context, row.tool_recovery_required
                )
                for p in engine.artifact.predictors
            }
            if engine.artifact
            else {}
        )
        reference_upper = next(v for c, v in feasible if c == dataset.reference_config_id)
        ordered = [
            c
            for c, value in sorted(feasible, key=lambda pair: (pair[1], pair[0]))
            if c != dataset.reference_config_id and value <= reference_upper
        ]
        result.append((row, score, ordered))
    return result


def report_replay(
    replays: list[tuple[MultiSample, dict[str, float], list[str]]],
    reference: str,
    thresholds: dict[str, float],
) -> dict[str, float]:
    quality, reference_quality, times, reference_times = [], [], [], []
    cost = Decimal(0)
    baseline_cost = Decimal(0)
    selections = {key: 0 for key in (*thresholds, reference)}
    critical = 0
    second = 0
    for row, scores, ordered in replays:
        selected = reference
        for i, key in enumerate(ordered):
            if i == 1:
                second += 1
            if not row.tool_recovery_required and scores[key] >= thresholds[key]:
                selected = key
                break
        observations = {o.config_id: o for o in row.observations}
        current, base = observations[selected], observations[reference]
        selections[selected] += 1
        quality.append(current.qualified)
        reference_quality.append(base.qualified)
        times.append(current.latency_ms)
        reference_times.append(base.latency_ms)
        cost += current.usd
        baseline_cost += base.usd
        critical += int(row.critical and base.qualified and not current.qualified)
    report = {
        "samples": float(len(replays)),
        "serving_usd": float(cost),
        "reference_usd": float(baseline_cost),
        "observed_pass_rate": sum(quality) / len(quality),
        "reference_pass_rate": sum(reference_quality) / len(quality),
        "p50_ratio": median(times) / median(reference_times),
        "critical_regressions": float(critical),
        "stage_two_reached": float(second),
    }
    for domain in {r.domain for r, _, _ in replays}:
        indices = [i for i, (r, _, _) in enumerate(replays) if r.domain == domain]
        report[f"quality_delta:{domain}"] = sum(
            int(quality[i]) - int(reference_quality[i]) for i in indices
        ) / len(indices)
    for key, count in selections.items():
        report[f"selected:{key}"] = float(count)
    report["guardrails_observed"] = float(
        critical == 0
        and report["p50_ratio"] <= 1.10
        and all(v >= 0 for k, v in report.items() if k.startswith("quality_delta:"))
    )
    return report


def _fit_text_encoder(
    rows: tuple[MultiSample, ...], target: str
) -> tuple[TfidfVectorizer, TfidfVectorizer, LogisticRegression]:
    word = TfidfVectorizer(ngram_range=(1, 2), max_features=4000)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=6000)
    texts = [feature_view(row.context()) for row in rows]
    matrix = hstack([word.fit_transform(texts), char.fit_transform(texts)])
    labels = [
        int(next(o.qualified for o in row.observations if o.config_id == target)) for row in rows
    ]
    model = LogisticRegression(solver="liblinear", random_state=42, max_iter=500).fit(
        matrix, labels
    )
    return word, char, model


def _oof_text_probabilities(
    rows: tuple[MultiSample, ...],
    target: str,
) -> tuple[np.ndarray, tuple[OOFFold, ...]]:
    labels = np.array(
        [int(next(o.qualified for o in r.observations if o.config_id == target)) for r in rows]
    )
    groups = np.array([r.group_id for r in rows])
    class_groups = [len(set(groups[labels == label])) for label in (0, 1)]
    limit = min(5, len(set(groups)), *class_groups)
    folds = None
    for count in range(limit, 1, -1):
        splitter = StratifiedGroupKFold(n_splits=count, shuffle=True, random_state=42)
        proposed = list(splitter.split(np.zeros(len(rows)), labels, groups))
        if all(len(set(labels[train])) == 2 for train, _ in proposed):
            folds = proposed
            break
    if folds is None:
        raise ValueError(
            "Hybrid needs at least two independent source groups per class for grouped OOF"
        )
    probabilities = np.full(len(rows), np.nan)
    provenance = []
    for train, validation in folds:
        fitting = tuple(rows[i] for i in train)
        word, char, model = _fit_text_encoder(fitting, target)
        texts = [feature_view(rows[i].context()) for i in validation]
        matrix = hstack([word.transform(texts), char.transform(texts)])
        probabilities[validation] = model.predict_proba(matrix)[:, 1]
        provenance.append(
            OOFFold(
                train_groups=tuple(sorted(set(groups[train]))),
                validation_groups=tuple(sorted(set(groups[validation]))),
            )
        )
    if not np.isfinite(probabilities).all():
        raise ValueError("Incomplete OOF predictions")
    return probabilities, tuple(provenance)


def train_multi(
    dataset: MultiDataset,
    *,
    hybrid: bool = False,
    encoder_spec: EncoderSpec | None = None,
    attention_epochs: int = 10,
    n_estimators: int | None = None,
    domain_loss_weight: float = 0.0,
) -> MultiArtifact:
    if dataset.purpose == "qualified_holdout" or any(r.split == "holdout" for r in dataset.samples):
        raise ValueError("Training must not read HOLDOUT")
    splits = {
        name: tuple(r for r in dataset.samples if r.split == name)
        for name in ("train", "calibration", "threshold")
    }
    if any(len(rows) < 4 for rows in splits.values()):
        raise ValueError(
            "Need >=4 independent samples in each DEV split; this is only a software floor"
        )
    attention = None
    semantic_train = None
    semantic_runtime = None
    if encoder_spec:
        if not hybrid:
            raise ValueError("Attention requires hybrid GBDT")
        from app.routing.ml.semantic import SemanticRuntime, train_semantic

        attention, semantic_train = train_semantic(
            splits["train"],
            encoder_spec,
            dataset.reference_config_id,
            attention_epochs,
            domain_loss_weight,
        )
        semantic_runtime = SemanticRuntime(attention)
    fitted = []
    for config in dataset.configurations:
        if config.config_id == dataset.reference_config_id:
            continue

        def labels(rows: tuple[MultiSample, ...], target: str = config.config_id) -> list[int]:
            return [
                int(next(o.qualified for o in r.observations if o.config_id == target))
                for r in rows
            ]

        label_counts = {
            split_name: {
                "pass": sum(labels(rows)),
                "fail": len(rows) - sum(labels(rows)),
            }
            for split_name, rows in splits.items()
        }
        missing = [
            f"{split_name}:{label}"
            for split_name, counts in label_counts.items()
            for label, count in counts.items()
            if count == 0 and split_name in ("train", "calibration")
        ]
        if missing:
            summary = "; ".join(
                f"{split_name}=PASS:{counts['pass']}/FAIL:{counts['fail']}"
                for split_name, counts in label_counts.items()
            )
            raise ValueError(
                "Each candidate needs both labels in train and calibration; "
                f"candidate={config.config_id}; missing={','.join(missing)}; {summary}"
            )

        if hybrid:
            train_text_probs, oof_folds = _oof_text_probabilities(splits["train"], config.config_id)

            train_meta = [
                numeric_view(
                    r.context(), r.has_rag_context, r.tool_recovery_required, legacy_7=False
                )
                for r in splits["train"]
            ]
            X_stage2 = np.column_stack([train_text_probs, train_meta])
            feature_names: tuple[str, ...] = HYBRID_FEATURE_NAMES
            if semantic_train is not None:
                X_stage2 = np.column_stack([X_stage2, semantic_train])
                feature_names = (*feature_names, *ATTENTION_FEATURES)

            trees_count = (
                n_estimators
                if n_estimators is not None
                else min(100, max(10, len(splits["train"])))
            )
            gbdt = GradientBoostingClassifier(
                n_estimators=trees_count,
                max_depth=3,
                learning_rate=0.1,
                random_state=42,
            ).fit(X_stage2, labels(splits["train"]))

            # Select on TRAIN only, then refit so compiled feature indices stay coherent.
            keep = [
                i
                for i, value in enumerate(gbdt.feature_importances_)
                if value >= 0.01 or i == 0 or feature_names[i] in ATTENTION_FEATURES
            ]
            if len(keep) < len(feature_names):
                X_stage2 = X_stage2[:, keep]
                feature_names = tuple(feature_names[i] for i in keep)
                gbdt.fit(X_stage2, labels(splits["train"]))

            trees, feat_imp, init_score = compile_sklearn_gbdt(gbdt, feature_names)

            # Refit the serving text encoder only after fitting GBDT on held-out fold scores.
            word, char, text_model = _fit_text_encoder(splits["train"], config.config_id)

            calibration = splits["calibration"]
            caltexts = [feature_view(r.context()) for r in calibration]
            cal_text_matrix = hstack([word.transform(caltexts), char.transform(caltexts)])
            cal_text_probs = text_model.predict_proba(cal_text_matrix)[:, 1]
            cal_meta = [
                numeric_view(
                    r.context(), r.has_rag_context, r.tool_recovery_required, legacy_7=False
                )
                for r in calibration
            ]
            X_cal_stage2 = np.column_stack([cal_text_probs, cal_meta])
            if semantic_runtime:
                X_cal_stage2 = np.column_stack(
                    [
                        X_cal_stage2,
                        [semantic_runtime.features(feature_view(r.context())) for r in calibration],
                    ]
                )
            X_cal_stage2 = X_cal_stage2[:, keep]
            raw_cal_probs = [
                evaluate_forest_prob(trees, row_feat, init_score=init_score, learning_rate=0.1)
                for row_feat in X_cal_stage2
            ]
            cal_logits = np.array(
                [np.log(max(p, 1e-7) / max(1.0 - p, 1e-7)) for p in raw_cal_probs]
            ).reshape(-1, 1)
            calibrator = LogisticRegression(solver="liblinear", random_state=42).fit(
                cal_logits, labels(calibration)
            )

            fitted.append(
                LinearPredictor(
                    config_id=config.config_id,
                    word=VectorizerState(
                        analyzer="word", vocabulary=word.vocabulary_, idf=tuple(word.idf_)
                    ),
                    char=VectorizerState(
                        analyzer="char_wb", vocabulary=char.vocabulary_, idf=tuple(char.idf_)
                    ),
                    coefficients=tuple(text_model.coef_[0]),
                    intercept=float(text_model.intercept_[0]),
                    calibration_a=float(calibrator.coef_[0][0]),
                    calibration_b=float(calibrator.intercept_[0]),
                    threshold=1,
                    is_hybrid=True,
                    trees=trees,
                    feature_names=feature_names,
                    feature_importances=feat_imp,
                    tree_init_score=init_score,
                    learning_rate=0.1,
                    oof_folds=oof_folds,
                )
            )
        else:
            word = TfidfVectorizer(ngram_range=(1, 2), max_features=4000)
            char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=6000)
            texts = [feature_view(r.context()) for r in splits["train"]]
            matrix = hstack(
                [
                    word.fit_transform(texts),
                    char.fit_transform(texts),
                    csr_matrix(
                        [
                            numeric_view(
                                r.context(),
                                r.has_rag_context,
                                r.tool_recovery_required,
                                legacy_7=False,
                            )
                            for r in splits["train"]
                        ]
                    ),
                ]
            )
            model = LogisticRegression(solver="liblinear", random_state=42, max_iter=500).fit(
                matrix, labels(splits["train"])
            )
            calibration = splits["calibration"]
            caltexts = [feature_view(r.context()) for r in calibration]
            calmatrix = hstack(
                [
                    word.transform(caltexts),
                    char.transform(caltexts),
                    csr_matrix(
                        [
                            numeric_view(
                                r.context(),
                                r.has_rag_context,
                                r.tool_recovery_required,
                                legacy_7=False,
                            )
                            for r in calibration
                        ]
                    ),
                ]
            )
            logits = model.decision_function(calmatrix).reshape(-1, 1)
            calibrator = LogisticRegression(solver="liblinear", random_state=42).fit(
                logits, labels(calibration)
            )
            fitted.append(
                LinearPredictor(
                    config_id=config.config_id,
                    word=VectorizerState(
                        analyzer="word", vocabulary=word.vocabulary_, idf=tuple(word.idf_)
                    ),
                    char=VectorizerState(
                        analyzer="char_wb", vocabulary=char.vocabulary_, idf=tuple(char.idf_)
                    ),
                    coefficients=tuple(model.coef_[0]),
                    intercept=float(model.intercept_[0]),
                    calibration_a=float(calibrator.coef_[0][0]),
                    calibration_b=float(calibrator.intercept_[0]),
                    threshold=1,
                    is_hybrid=False,
                )
            )
    artifact = MultiArtifact(
        feature_version="onnx-int8-sdpa-oof-v4"
        if attention
        else HYBRID_FEATURE_VERSION
        if hybrid
        else "intent-recent-rag-numeric-v2",
        attention=attention,
        model_version=dataset.version,
        purpose=dataset.purpose,
        trained_at=datetime.now(UTC).isoformat(),
        dataset_hash=hashlib.sha256(dataset.model_dump_json().encode()).hexdigest(),
        provenance=dataset.provenance,
        grader_version=dataset.grader_version,
        catalog_version=dataset.costs.version,
        costs_hash=hashlib.sha256(dataset.costs.model_dump_json().encode()).hexdigest(),
        reference_config_id=dataset.reference_config_id,
        configuration_hashes={c.config_id: configuration_hash(c) for c in dataset.configurations},
        configurations=dataset.configurations,
        latency_ms={
            c.config_id: median(
                next(o.latency_ms for o in row.observations if o.config_id == c.config_id)
                for row in splits["calibration"]
            )
            for c in dataset.configurations
        },
        predictors=(fitted[0], fitted[1]),
        group_ids=tuple(sorted({r.group_id for r in dataset.samples})),
        input_hashes=tuple(input_hash(r.messages) for r in dataset.samples),
        content_hashes=tuple(sorted({content_key(r.messages) for r in dataset.samples})),
        threshold_report={},
    )
    return select_thresholds(dataset, artifact)


def select_thresholds(dataset: MultiDataset, artifact: MultiArtifact) -> MultiArtifact:
    """Freeze thresholds on DEV only, with separate quality/cost/latency criteria."""
    if any(r.split == "holdout" for r in dataset.samples):
        raise ValueError("Threshold selection must not read HOLDOUT")
    if artifact.dataset_hash != hashlib.sha256(dataset.model_dump_json().encode()).hexdigest():
        raise ValueError("Threshold selection needs the original DEV dataset")
    fitted = artifact.predictors
    rows = tuple(r for r in dataset.samples if r.split == "threshold")
    if not rows:
        raise ValueError("DEV threshold split required")
    replay = replay_rows(dataset, MultiRouterService(artifact.model_dump_json()), rows)
    ids = [p.config_id for p in fitted]
    from app.routing.ml.dynamic_pareto import DynamicParetoThresholding

    chosen_thresholds, report, _ = DynamicParetoThresholding.calibrate(
        replay,
        dataset.reference_config_id,
        ids,
        trade_off_weight=0.6,
        min_pass_rate=0.97,
    )
    if report.get("guardrails_observed", 0.0) != 1.0:
        raw_grids = [
            sorted(
                {
                    0.0,
                    1.0,
                    *(s[key] for _, s, _ in replay),
                    *(float(np.nextafter(s[key], 1)) for _, s, _ in replay),
                }
            )
            for key in ids
        ]
        grids = []
        for g in raw_grids:
            if len(g) > 50:
                indices = np.linspace(0, len(g) - 1, 50, dtype=int)
                grids.append(sorted({0.0, 1.0, *(g[i] for i in indices)}))
            else:
                grids.append(g)
        best = None
        for a in grids[0]:
            for b in grids[1]:
                rep = report_replay(replay, dataset.reference_config_id, {ids[0]: a, ids[1]: b})
                if rep["guardrails_observed"]:
                    score = (rep["serving_usd"], rep["p50_ratio"], -a, -b)
                    if best is None or score < best[3]:
                        best = (a, b, rep, score)
        if best is not None:
            chosen_thresholds = {ids[0]: best[0], ids[1]: best[1]}
            report = best[2]
        else:
            raise ValueError("No joint thresholds meet observed guardrails")

    return artifact.model_copy(
        update={
            "predictors": (
                fitted[0].model_copy(update={"threshold": chosen_thresholds[ids[0]]}),
                fitted[1].model_copy(update={"threshold": chosen_thresholds[ids[1]]}),
            ),
            "threshold_report": report,
        }
    )


def evaluate_multi(dataset: MultiDataset, engine: MultiRouterService) -> dict[str, object]:
    artifact = engine.artifact
    if (
        not artifact
        or dataset.purpose not in ("qualified_holdout", "software_test", "research_candidate")
        or any(r.split != "holdout" for r in dataset.samples)
    ):
        raise ValueError("V2 evaluation needs an artifact and independent HOLDOUT")
    if (
        dataset.grader_version != artifact.grader_version
        or {c.config_id: configuration_hash(c) for c in dataset.configurations}
        != artifact.configuration_hashes
        or hashlib.sha256(dataset.costs.model_dump_json().encode()).hexdigest()
        != artifact.costs_hash
    ):
        raise ValueError("HOLDOUT config/catalog/grader mismatch")
    if any(
        r.group_id in artifact.group_ids
        or input_hash(r.messages) in artifact.input_hashes
        or content_key(r.messages) in artifact.content_hashes
        for r in dataset.samples
    ):
        raise ValueError("HOLDOUT overlaps DEV")
    replay = replay_rows(dataset, engine, dataset.samples)
    # Report every measured fixed configuration, even if it outperforms routing.
    # Infeasible fixed policies are explicitly marked rather than silently compared.
    from app.routing.policies import PolicyRouter, RoutingRejected

    fixed: dict[str, object] = {}
    registry = RegistrySnapshot(
        configurations=dataset.configurations, mock_config_id=dataset.reference_config_id
    )
    for config in dataset.configurations:
        observations = [
            next(o for o in row.observations if o.config_id == config.config_id)
            for row in dataset.samples
        ]
        feasible_count = 0
        for row in dataset.samples:
            try:
                PolicyRouter().select(
                    extract_context_features(row.messages, row.has_rag_context),
                    row.context(),
                    registry,
                    dataset.costs,
                    PolicySnapshot(
                        policy_id="fixed",
                        strategy="fixed_candidate",
                        candidate_id=config.config_id,
                        flags=FeatureFlags(router=True),
                        sandbox=True,
                    ),
                    RemainingBudget(usd=row.max_usd, deadline_ms=row.deadline_ms),
                )
                if (
                    row.deadline_ms is None
                    or artifact.latency_ms[config.config_id] <= row.deadline_ms
                ):
                    feasible_count += 1
            except RoutingRejected:
                pass
        fixed[config.config_id] = {
            "samples": len(observations),
            "feasible_samples": feasible_count,
            "comparable_on_all_cases": feasible_count == len(observations),
            "measured_usd": str(sum((o.usd for o in observations), Decimal(0))),
            "observed_pass_rate": sum(o.qualified for o in observations) / len(observations),
            "p50_ms": median(o.latency_ms for o in observations),
        }
    return {
        "purpose": dataset.purpose,
        "measurement": "offline_replay_excludes_live_router_and_storage_overhead",
        "artifact_hash": engine.hash,
        "fixed_configurations": fixed,
        "report": report_replay(
            replay,
            artifact.reference_config_id,
            {p.config_id: p.threshold for p in artifact.predictors},
        ),
        "conclusion": "OBSERVED_ONLY_NOT_STATISTICAL_PROOF",
    }
