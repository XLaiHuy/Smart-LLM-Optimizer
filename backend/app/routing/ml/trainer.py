"""Offline fitting and independent threshold selection; never calls an API."""

import hashlib
from datetime import UTC, datetime
from statistics import median

import numpy as np
from scipy.sparse import csr_matrix, hstack  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from app.routing.features import serving_text
from app.routing.ml.dataset import LabeledDataset, LabeledTaskSample
from app.routing.ml.service import (
    MLRouterService,
    RouterArtifact,
    VectorizerState,
    input_hash,
    numeric_features,
)


def measured_report(
    rows: tuple[LabeledTaskSample, ...],
    scores: list[float],
    threshold: float,
    max_loss: float,
    latency_ratio: float,
) -> dict[str, float]:
    choices = [score >= threshold for score in scores]
    report: dict[str, float] = {"samples": float(len(rows))}
    qualified = [
        r.small_qualified if c else r.reference_qualified
        for r, c in zip(rows, choices, strict=True)
    ]
    report["observed_pass_rate"] = sum(qualified) / len(rows)
    report["reference_pass_rate"] = sum(r.reference_qualified for r in rows) / len(rows)
    report["serving_usd"] = float(
        sum(r.small_usd if c else r.reference_usd for r, c in zip(rows, choices, strict=True))
    )
    report["reference_usd"] = float(sum(r.reference_usd for r in rows))
    report["candidate_selection_rate"] = sum(choices) / len(rows)
    report["p50_ratio"] = median(
        r.small_ms if c else r.reference_ms for r, c in zip(rows, choices, strict=True)
    ) / median(r.reference_ms for r in rows)
    report["critical_regressions"] = float(
        sum(
            r.critical and r.reference_qualified and not passed
            for r, passed in zip(rows, qualified, strict=True)
        )
    )
    passes = report["p50_ratio"] <= latency_ratio and report["critical_regressions"] == 0
    for domain in sorted({r.domain for r in rows}):
        indices = [i for i, row in enumerate(rows) if row.domain == domain]
        delta = sum(int(qualified[i]) - int(rows[i].reference_qualified) for i in indices) / len(
            indices
        )
        report[f"quality_delta:{domain}"] = delta
        passes &= delta >= -max_loss
    report["guardrails_observed"] = float(passes)
    return report


def train(
    dataset: LabeledDataset,
    threshold: float | None = None,
    max_quality_loss: float = 0,
    max_latency_ratio: float = 1.10,
) -> RouterArtifact:
    if dataset.purpose == "qualified_holdout" or any(r.split == "holdout" for r in dataset.samples):
        raise ValueError("Training must not read HOLDOUT samples")
    rows = tuple(r for r in dataset.samples if r.split == "train")
    calibration = tuple(r for r in dataset.samples if r.split == "calibration")
    if len(rows) < 4 or len(calibration) < 4 or len({r.small_qualified for r in rows}) != 2:
        raise ValueError("Need train/calibration splits (>=4 each), with both training labels")
    texts = [serving_text(r.messages) for r in rows]
    word = TfidfVectorizer(ngram_range=(1, 2), max_features=4000)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), max_features=6000)
    matrix = hstack(
        [
            word.fit_transform(texts),
            char.fit_transform(texts),
            csr_matrix([numeric_features(r.messages, r.has_rag_context) for r in rows]),
        ]
    )
    classifier = LogisticRegression(C=1.0, solver="liblinear", random_state=42, max_iter=500)
    classifier.fit(matrix, [int(r.small_qualified) for r in rows])
    artifact = RouterArtifact(
        model_version=dataset.version,
        trained_at=datetime.now(UTC).isoformat(),
        dataset_hash=hashlib.sha256(dataset.model_dump_json().encode()).hexdigest(),
        provenance=dataset.provenance,
        grader_version=dataset.grader_version,
        purpose=dataset.purpose,
        candidate_config_id=dataset.candidate_config_id,
        candidate_model_id=dataset.candidate_model_id,
        reference_config_id=dataset.reference_config_id,
        reference_model_id=dataset.reference_model_id,
        train_group_ids=tuple(sorted({r.group_id for r in rows})),
        calibration_group_ids=tuple(sorted({r.group_id for r in calibration})),
        input_hashes=tuple(input_hash(r.messages) for r in dataset.samples),
        threshold=1.0,
        max_quality_loss=max_quality_loss,
        max_latency_ratio=max_latency_ratio,
        word=VectorizerState(analyzer="word", vocabulary=word.vocabulary_, idf=tuple(word.idf_)),
        char=VectorizerState(analyzer="char_wb", vocabulary=char.vocabulary_, idf=tuple(char.idf_)),
        coefficients=tuple(classifier.coef_[0]),
        intercept=float(classifier.intercept_[0]),
        calibration_report={},
    )
    runtime = MLRouterService(artifact.model_dump_json())
    scores = [runtime.score(r.messages, r.has_rag_context) for r in calibration]
    thresholds = (
        [threshold]
        if threshold is not None
        else sorted({0.0, 1.0, *scores, *(min(1.0, float(np.nextafter(s, 1))) for s in scores)})
    )
    candidates = [
        (t, measured_report(calibration, scores, t, max_quality_loss, max_latency_ratio))
        for t in thresholds
    ]
    feasible = [(t, report) for t, report in candidates if report["guardrails_observed"]]
    if not feasible:
        raise ValueError("No threshold meets observed per-domain quality and latency constraints")
    chosen, report = min(feasible, key=lambda item: (item[1]["serving_usd"], -item[0]))
    return artifact.model_copy(update={"threshold": chosen, "calibration_report": report})


def evaluate(dataset: LabeledDataset, runtime: MLRouterService) -> dict[str, object]:
    artifact = runtime.artifact
    if not artifact:
        raise ValueError("Invalid or missing artifact")
    if dataset.purpose not in ("qualified_holdout", "software_test") or any(
        r.split != "holdout" for r in dataset.samples
    ):
        raise ValueError("Evaluation requires a separate HOLDOUT dataset")
    if (
        dataset.candidate_config_id,
        dataset.candidate_model_id,
        dataset.reference_config_id,
        dataset.reference_model_id,
    ) != (
        artifact.candidate_config_id,
        artifact.candidate_model_id,
        artifact.reference_config_id,
        artifact.reference_model_id,
    ):
        raise ValueError("Model configurations differ from training")
    if dataset.grader_version != artifact.grader_version:
        raise ValueError("Grader version differs from training")
    groups = set(artifact.train_group_ids) | set(artifact.calibration_group_ids)
    if any(
        r.group_id in groups or input_hash(r.messages) in artifact.input_hashes
        for r in dataset.samples
    ):
        raise ValueError("HOLDOUT overlaps DEV")
    scores = [runtime.score(r.messages, r.has_rag_context) for r in dataset.samples]
    return {
        "artifact_hash": runtime.hash,
        "purpose": dataset.purpose,
        "status": "PASS_OBSERVED_OR_FAIL_ONLY_NOT_STATISTICAL_PROOF",
        "report": measured_report(
            dataset.samples,
            scores,
            artifact.threshold,
            artifact.max_quality_loss,
            artifact.max_latency_ratio,
        ),
    }
