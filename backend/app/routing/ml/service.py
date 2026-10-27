"""Data-only JSON artifacts: loading never unpickles code or fits a model."""

import hashlib
import json
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, model_validator
from scipy.sparse import csr_matrix, hstack  # type: ignore[import-untyped]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

from app.contracts.dtos import DTO, Message
from app.contracts.representations import SharedRepresentationPort
from app.routing.features import extract_context_features, serving_text

FEATURE_VERSION = "full-serving-word-char-numeric-v1"


class VectorizerState(DTO):
    analyzer: Literal["word", "char_wb"]
    vocabulary: dict[str, int]
    idf: tuple[float, ...]

    @model_validator(mode="after")
    def dimensions(self) -> "VectorizerState":
        if not self.vocabulary or set(self.vocabulary.values()) != set(range(len(self.idf))):
            raise ValueError("Invalid vectorizer dimensions")
        if not all(np.isfinite(self.idf)):
            raise ValueError("Invalid IDF")
        return self


class RouterArtifact(DTO):
    format_version: Literal["router-json-v1"] = "router-json-v1"
    feature_version: Literal["full-serving-word-char-numeric-v1"] = (
        "full-serving-word-char-numeric-v1"
    )
    model_version: str
    trained_at: str
    dataset_hash: str
    provenance: str
    grader_version: str
    purpose: Literal["qualified_dev", "software_test"]
    candidate_config_id: str
    candidate_model_id: str
    reference_config_id: str
    reference_model_id: str
    train_group_ids: tuple[str, ...]
    calibration_group_ids: tuple[str, ...]
    input_hashes: tuple[str, ...]
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    max_quality_loss: float = Field(default=0, ge=0, le=1)
    max_latency_ratio: float = Field(default=1.10, gt=0)
    score_semantics: Literal["uncalibrated_logistic_score"] = "uncalibrated_logistic_score"
    word: VectorizerState
    char: VectorizerState
    coefficients: tuple[float, ...]
    intercept: float = Field(allow_inf_nan=False)
    calibration_report: dict[str, float]

    @model_validator(mode="after")
    def dimensions(self) -> "RouterArtifact":
        if len(self.coefficients) != len(self.word.idf) + len(self.char.idf) + 4:
            raise ValueError("Invalid coefficient dimensions")
        if not all(np.isfinite(self.coefficients)):
            raise ValueError("Invalid coefficients")
        if set(self.train_group_ids) & set(self.calibration_group_ids):
            raise ValueError("Calibration overlaps training")
        return self


def numeric_features(messages: tuple[Message, ...], has_rag: bool) -> list[float]:
    profile = extract_context_features(messages, has_rag)
    return [
        float(np.log1p(profile.total_input_bytes)),
        float(has_rag),
        profile.code_ratio,
        float(profile.requires_structured),
    ]


class MLRouterService:
    def bind_shared_representation(self, port: SharedRepresentationPort) -> None:
        if self.multi.semantic:
            with self.multi.semantic.lock:
                self.multi.semantic.encoder.shared = port
                self.multi.semantic.cache.clear()

    def __init__(
        self,
        artifact_json: str | None = None,
        *,
        live_approved: bool = False,
        allow_research_candidate: bool = False,
    ):
        from app.routing.ml.multi import MultiRouterService

        self.multi = MultiRouterService(
            live_approved=live_approved,
            allow_research_candidate=allow_research_candidate,
        )
        self.artifact: RouterArtifact | None = None
        self.hash: str | None = None
        self.artifact_json: str | None = None
        self.live_approved = live_approved
        self.allow_research_candidate = allow_research_candidate
        self.status = "ML_ARTIFACT_MISSING_FALLBACK"
        self.word = None
        self.char = None
        if artifact_json is not None:
            try:
                document = json.loads(artifact_json)
                if not isinstance(document, dict):
                    raise ValueError("Artifact must be an object")
                if document.get("format_version") == "router-json-v2":
                    self.multi = MultiRouterService(
                        artifact_json,
                        live_approved=live_approved,
                        allow_research_candidate=allow_research_candidate,
                    )
                    self.hash, self.artifact_json, self.status = (
                        self.multi.hash,
                        self.multi.artifact_json,
                        self.multi.status,
                    )
                    return
                self.artifact = RouterArtifact.model_validate_json(artifact_json)
                self.artifact_json = self.artifact.model_dump_json()
                self.hash = hashlib.sha256(self.artifact_json.encode()).hexdigest()
                self.word = self._vectorizer(self.artifact.word)
                self.char = self._vectorizer(self.artifact.char)
                self.status = "ML_ARTIFACT_READY"
            except (ValueError, TypeError):
                self.artifact = None
                self.status = "ML_ARTIFACT_INVALID_FALLBACK"

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        live_approved: bool = False,
        allow_research_candidate: bool = False,
    ) -> "MLRouterService":
        try:
            if path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Artifact too large")
            return cls(
                path.read_text(encoding="utf-8"),
                live_approved=live_approved,
                allow_research_candidate=allow_research_candidate,
            )
        except FileNotFoundError:
            return cls(
                live_approved=live_approved,
                allow_research_candidate=allow_research_candidate,
            )
        except (OSError, ValueError):
            service = cls(
                live_approved=live_approved,
                allow_research_candidate=allow_research_candidate,
            )
            service.status = "ML_ARTIFACT_INVALID_FALLBACK"
            return service

    @staticmethod
    def _vectorizer(state: VectorizerState) -> TfidfVectorizer:
        vectorizer = TfidfVectorizer(
            analyzer=state.analyzer,
            ngram_range=(1, 2) if state.analyzer == "word" else (3, 5),
            vocabulary=state.vocabulary,
        )
        vectorizer.idf_ = np.asarray(state.idf)
        return vectorizer

    def score(self, messages: tuple[Message, ...], has_rag: bool = False) -> float:
        if not self.artifact or self.word is None or self.char is None:
            raise ValueError("No valid ML artifact")
        text = [serving_text(messages)]
        matrix = hstack(
            [
                self.word.transform(text),
                self.char.transform(text),
                csr_matrix([numeric_features(messages, has_rag)]),
            ]
        )
        value = (
            float((matrix @ np.asarray(self.artifact.coefficients))[0]) + self.artifact.intercept
        )
        return float(1 / (1 + np.exp(-np.clip(value, -700, 700))))


def input_hash(messages: tuple[Message, ...]) -> str:
    return hashlib.sha256(
        json.dumps([m.model_dump() for m in messages], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
