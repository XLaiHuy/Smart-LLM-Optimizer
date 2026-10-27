"""V2: two independently measured candidates, one reference, data-only predictors."""

import hashlib
import json
import re
from typing import Any, Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.sparse import csr_matrix, hstack  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

from app.contracts.dtos import DTO, ContextResult, ModelConfiguration
from app.contracts.representations import AttentionState
from app.routing.features import extract_context_features
from app.routing.ml.attention import ATTENTION_FEATURES, validate_attention
from app.routing.ml.service import MLRouterService, VectorizerState
from app.routing.ml.tree_compiler import evaluate_forest_prob, validate_forest

FEATURE_VERSION_V2 = "intent-recent-rag-numeric-v2"
NUMERIC_FEATURE_NAMES_11 = (
    "log_total_bytes",
    "log_prompt_bytes",
    "code_ratio",
    "has_rag",
    "requires_structured",
    "tools_count",
    "tool_recovery",
    "math_symbol_density",
    "turn_count",
    "question_density",
    "rag_evidence_ratio",
)

NUMERIC_FEATURE_NAMES_14 = (
    *NUMERIC_FEATURE_NAMES_11,
    "constraint_step_density",
    "type_token_ratio",
    "uppercase_ratio",
)

NUMERIC_FEATURE_NAMES = NUMERIC_FEATURE_NAMES_14

HYBRID_FEATURE_VERSION: Literal["intent-recent-rag-hybrid-oof-v3"] = (
    "intent-recent-rag-hybrid-oof-v3"
)
HYBRID_FEATURE_NAMES_11 = ("text_complexity", *NUMERIC_FEATURE_NAMES_11)
HYBRID_FEATURE_NAMES_14 = ("text_complexity", *NUMERIC_FEATURE_NAMES_14)
HYBRID_FEATURE_NAMES = HYBRID_FEATURE_NAMES_14


class OOFFold(DTO):
    train_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]

    @model_validator(mode="after")
    def disjoint(self) -> "OOFFold":
        if (
            not self.train_groups
            or not self.validation_groups
            or set(self.train_groups) & set(self.validation_groups)
        ):
            raise ValueError("OOF groups must be nonempty and disjoint")
        return self


def configuration_hash(config: ModelConfiguration) -> str:
    keys = (
        "config_id",
        "model_id",
        "context_window",
        "max_output_tokens",
        "endpoint",
        "structured_output",
        "function_calling",
        "reasoning_effort",
        "supported_parameters",
    )
    return hashlib.sha256(
        json.dumps({k: getattr(config, k) for k in keys}, sort_keys=True).encode()
    ).hexdigest()


def feature_view(context: ContextResult) -> str:
    """Only feature extraction is bounded. Provider messages are never truncated here."""
    messages = context.messages
    last_user = next(
        (i for i in range(len(messages) - 1, -1, -1) if messages[i].role == "user"),
        len(messages) - 1,
    )
    current = messages[last_user].content if messages else ""
    history: list[str] = []
    for m in messages[:last_user]:
        if m.role == "user":
            history.append(f"user: {m.content[:500]}")
        elif m.role == "assistant" and not m.content.startswith("Untrusted document evidence"):
            # Strip code blocks from past assistant responses for router feature view
            cleaned = re.sub(r"```[\s\S]*?```", "[code block]", m.content)
            history.append(f"assistant: {cleaned[:350]}")
    history = history[-4:]
    evidence = [m.content for m in messages if m.content.startswith("Untrusted document evidence")]
    return (
        "CURRENT\n"
        + current[:8000]
        + "\nRECENT\n"
        + "\n".join(history)
        + "\nEVIDENCE\n"
        + "\n".join(evidence)[:4000]
    )


def numeric_view(
    context: ContextResult,
    has_rag: bool,
    recovery: bool,
    *,
    legacy_7: bool = False,
    legacy_11: bool = False,
) -> list[float]:
    profile = extract_context_features(context.messages, has_rag)
    current = next((m.content for m in reversed(context.messages) if m.role == "user"), "")
    base = [
        float(np.log1p(profile.total_input_bytes)),
        float(np.log1p(len(current.encode("utf-8")))),
        profile.code_ratio,
        float(has_rag),
        float(profile.requires_structured),
        float(len(context.tools)),
        float(recovery),
    ]
    if legacy_7:
        return base

    math_chars = set("+-*/=^%<>≤≥√∑∫π()[]{}")
    math_density = float(sum(1 for ch in current if ch in math_chars) / max(len(current), 1))
    turn_count = float(len([m for m in context.messages if m.role == "user"]))
    question_density = float(current.count("?") / max(len(current.split()), 1))
    evidence_bytes = sum(
        len(m.content.encode("utf-8"))
        for m in context.messages
        if m.content.startswith("Untrusted document evidence")
    )
    rag_ratio = float(evidence_bytes / max(profile.total_input_bytes, 1))

    features_11 = [
        *base,
        math_density,
        turn_count,
        question_density,
        rag_ratio,
    ]
    if legacy_11:
        return features_11

    # 3 additional structural features (Total: 14)
    step_matches = len(
        re.findall(
            r"(?im)(?:^\s*(?:\d+[\.\)]|[a-zA-Z][\.\)]|[-*•])\s+|bước\s*\d+|step\s*\d+)",
            current,
        )
    )
    constraint_step_density = float(step_matches / max(len(current.split()), 1))

    words = [w.lower() for w in re.findall(r"\w+", current)]
    type_token_ratio = float(len(set(words)) / max(len(words), 1))

    letters = [c for c in current if c.isalpha()]
    uppercase_ratio = float(sum(1 for c in letters if c.isupper()) / max(len(letters), 1))

    return [
        *features_11,
        constraint_step_density,
        type_token_ratio,
        uppercase_ratio,
    ]


class LinearPredictor(DTO):
    config_id: str
    word: VectorizerState
    char: VectorizerState
    coefficients: tuple[float, ...]
    intercept: float = Field(allow_inf_nan=False)
    calibration_a: float = Field(default=1, allow_inf_nan=False)
    calibration_b: float = Field(default=0, allow_inf_nan=False)
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    is_hybrid: bool = False
    trees: tuple[dict[str, Any], ...] = ()
    feature_names: tuple[str, ...] = ()
    feature_importances: dict[str, float] = Field(default_factory=dict)
    tree_init_score: float = Field(default=0.0, allow_inf_nan=False)
    learning_rate: float = Field(default=0.1, gt=0, allow_inf_nan=False)
    oof_folds: tuple[OOFFold, ...] = ()

    @model_validator(mode="after")
    def dimensions(self) -> "LinearPredictor":
        text_dim = len(self.word.idf) + len(self.char.idf)
        valid_dims = (
            {text_dim}
            if self.is_hybrid
            else {text_dim + 7, text_dim + 11, text_dim + len(NUMERIC_FEATURE_NAMES)}
        )
        if len(self.coefficients) not in valid_dims or not all(np.isfinite(self.coefficients)):
            raise ValueError("Invalid V2 predictor dimensions")
        if self.is_hybrid:
            valid_schemas = {HYBRID_FEATURE_NAMES_11, HYBRID_FEATURE_NAMES_14}
            if self.feature_names not in valid_schemas and not (
                set(self.feature_names).issubset(
                    set((*HYBRID_FEATURE_NAMES_14, *ATTENTION_FEATURES))
                )
                and "text_complexity" in self.feature_names
                and len(set(self.feature_names)) == len(self.feature_names)
            ):
                raise ValueError("Unknown hybrid feature schema/order")
            validate_forest(self.trees, len(self.feature_names))
            if set(self.feature_importances) != set(self.feature_names) or any(
                not np.isfinite(v) or not -1e-6 <= v <= 1.0 + 1e-6
                for v in self.feature_importances.values()
            ):
                raise ValueError("Invalid feature importances")
            total = sum(self.feature_importances.values())
            if total != 0 and not np.isclose(total, 1, atol=1e-4):
                raise ValueError("Feature importances must sum to one or be all zero")
            if len(self.oof_folds) < 2:
                raise ValueError("Hybrid requires grouped OOF provenance; retrain old artifacts")
            validations = [g for fold in self.oof_folds for g in fold.validation_groups]

            if len(set(validations)) != len(validations):
                raise ValueError("OOF validation groups repeat")
            for fold in self.oof_folds:
                if set(fold.train_groups) != set(validations) - set(fold.validation_groups):
                    raise ValueError("OOF training must cover the other folds")
        elif self.trees or self.oof_folds or self.feature_importances:
            raise ValueError("Linear predictor cannot contain hybrid state")
        return self


class MultiArtifact(DTO):
    format_version: Literal["router-json-v2"] = "router-json-v2"
    feature_version: Literal[
        "intent-recent-rag-numeric-v2", "intent-recent-rag-hybrid-oof-v3", "onnx-int8-sdpa-oof-v4"
    ] = "intent-recent-rag-numeric-v2"
    model_version: str
    purpose: Literal["qualified_dev", "software_test", "research_candidate"]
    trained_at: str
    dataset_hash: str
    provenance: str
    grader_version: str
    catalog_version: str
    costs_hash: str
    reference_config_id: str
    configuration_hashes: dict[str, str]
    configurations: tuple[ModelConfiguration, ModelConfiguration, ModelConfiguration]
    latency_ms: dict[str, float]
    predictors: tuple[LinearPredictor, LinearPredictor]
    group_ids: tuple[str, ...]
    input_hashes: tuple[str, ...]
    content_hashes: tuple[str, ...] = ()
    threshold_report: dict[str, float]
    max_quality_loss: float = Field(default=0, ge=0, le=1)
    max_latency_ratio: float = Field(default=1.1, gt=0)
    attention: AttentionState | None = None

    @model_validator(mode="after")
    def coherent(self) -> "MultiArtifact":
        hybrid = {p.is_hybrid for p in self.predictors}
        if len(hybrid) != 1 or (
            self.feature_version in (HYBRID_FEATURE_VERSION, "onnx-int8-sdpa-oof-v4")
        ) != (True in hybrid):
            raise ValueError("Feature version and predictor architecture disagree")
        if (self.attention is not None) != (self.feature_version == "onnx-int8-sdpa-oof-v4"):
            raise ValueError("Attention state/version mismatch")
        if self.attention:
            validate_attention(self.attention)
            if set(self.attention.train_groups) - set(self.group_ids):
                raise ValueError("Attention trained outside artifact DEV groups")
        elif any(set(p.feature_names) & set(ATTENTION_FEATURES) for p in self.predictors):
            raise ValueError("Semantic features need trained attention state")
        ids = {self.reference_config_id, *(p.config_id for p in self.predictors)}
        if len(ids) != 3 or ids != set(self.configuration_hashes):
            raise ValueError("V2 requires two distinct candidates and one reference")
        if {
            c.config_id: configuration_hash(c) for c in self.configurations
        } != self.configuration_hashes:
            raise ValueError("V2 settings fingerprints disagree")
        if set(self.latency_ms) != ids or any(
            not np.isfinite(v) or v <= 0 for v in self.latency_ms.values()
        ):
            raise ValueError("V2 needs measured latency profiles")
        return self


class MultiRouterService:
    def __init__(
        self,
        raw: str | None = None,
        *,
        live_approved: bool = False,
        allow_research_candidate: bool = False,
    ):
        self.artifact: MultiArtifact | None = None
        self.hash: str | None = None
        self.artifact_json: str | None = None
        self.live_approved = live_approved
        self.allow_research_candidate = allow_research_candidate
        self.status = "ML_ARTIFACT_MISSING_FALLBACK"
        self.vectors: dict[str, tuple[TfidfVectorizer, TfidfVectorizer]] = {}
        self.coefficients: dict[str, np.ndarray] = {}
        from app.routing.ml.semantic import SemanticRuntime

        self.semantic: SemanticRuntime | None = None
        if raw:
            try:
                artifact = MultiArtifact.model_validate_json(raw)
                self.artifact = artifact
                self.artifact_json = artifact.model_dump_json()
                self.hash = hashlib.sha256(self.artifact_json.encode()).hexdigest()
                self.vectors = {
                    p.config_id: (
                        MLRouterService._vectorizer(p.word),
                        MLRouterService._vectorizer(p.char),
                    )
                    for p in artifact.predictors
                }
                self.status = "ML_ARTIFACT_READY"
                self.coefficients = {
                    p.config_id: np.asarray(p.coefficients) for p in artifact.predictors
                }
                if artifact.attention:
                    self.semantic = SemanticRuntime(artifact.attention)
            except (ValueError, TypeError, KeyError, IndexError, OSError, ImportError):
                self.artifact = None
                self.hash, self.artifact_json = None, None
                self.vectors = {}
                self.coefficients = {}
                self.status = "ML_ARTIFACT_INVALID_FALLBACK"

    def score(
        self, config_id: str, context: ContextResult, has_rag: bool, recovery: bool = False
    ) -> float:
        if not self.artifact:
            raise ValueError("V2 artifact unavailable")
        predictor = next(p for p in self.artifact.predictors if p.config_id == config_id)
        word, char = self.vectors[config_id]
        texts = [feature_view(context)]

        if predictor.is_hybrid:
            # Candidate qualification score from text; not a measured difficulty score.
            text_matrix = hstack([word.transform(texts), char.transform(texts)])
            raw_text = float((text_matrix @ self.coefficients[config_id])[0]) + predictor.intercept
            text_complexity = float(1.0 / (1.0 + np.exp(-np.clip(raw_text, -500.0, 500.0))))

            # Stage 2: Dense Meta-features + text_complexity into GBDT trees
            feat_14 = numeric_view(context, has_rag, recovery, legacy_7=False, legacy_11=False)
            feat_map = dict(zip(NUMERIC_FEATURE_NAMES_14, feat_14, strict=True))
            feat_map["text_complexity"] = text_complexity
            if self.semantic:
                feat_map.update(
                    zip(ATTENTION_FEATURES, self.semantic.features(texts[0]), strict=True)
                )

            if predictor.feature_names:
                stage2_input = [feat_map[name] for name in predictor.feature_names]
            else:
                stage2_input = [text_complexity, *feat_14[:11]]

            raw_prob = evaluate_forest_prob(
                predictor.trees,
                stage2_input,
                init_score=predictor.tree_init_score,
                learning_rate=predictor.learning_rate,
            )
            # Platt scaling calibration
            logit = (
                predictor.calibration_a
                * float(np.log(max(raw_prob, 1e-7) / max(1.0 - raw_prob, 1e-7)))
                + predictor.calibration_b
            )
            return float(1.0 / (1.0 + np.exp(-np.clip(logit, -500.0, 500.0))))
        else:
            text_dim = len(predictor.word.idf) + len(predictor.char.idf)
            legacy_7 = len(predictor.coefficients) == text_dim + 7
            legacy_11 = len(predictor.coefficients) == text_dim + 11
            matrix = hstack(
                [
                    word.transform(texts),
                    char.transform(texts),
                    csr_matrix(
                        [
                            numeric_view(
                                context, has_rag, recovery, legacy_7=legacy_7, legacy_11=legacy_11
                            )
                        ]
                    ),
                ]
            )
            raw = float((matrix @ self.coefficients[config_id])[0]) + predictor.intercept
            logit = predictor.calibration_a * raw + predictor.calibration_b
            return float(1 / (1 + np.exp(-np.clip(logit, -700, 700))))
