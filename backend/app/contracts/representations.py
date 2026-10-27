"""Versioned encoder identity and an ephemeral port for future context compression."""

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field

from app.contracts.dtos import DTO


class EncoderSpec(DTO):
    repository: str
    revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    model_path: str
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tokenizer_path: str
    tokenizer_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    hidden_size: int = Field(default=384, ge=1, le=4096)
    max_tokens: int = Field(default=128, ge=8, le=512)
    recipe: str = "feature-view-v1-token-states"
    quantization: str = "int8"

    @property
    def fingerprint(self) -> str:
        # File locations are deployment details, not representation identity.
        return hashlib.sha256(
            self.model_dump_json(exclude={"model_path", "tokenizer_path"}).encode()
        ).hexdigest()


@dataclass(frozen=True)
class SharedRepresentation:
    """Request-local arrays, never stored in traces/OpenAPI/history.

    Tân's adapter must return states from exactly this encoder/recipe over the
    same feature-view input. Different layers/models/tokenization fall back to
    standalone ONNX. Arrays must remain immutable during routing.
    """

    encoder_fingerprint: str
    input_digest: str
    hidden_states: Any
    attention_mask: Any


class SharedRepresentationPort(Protocol):
    def representation_for(
        self, text: str, encoder: EncoderSpec
    ) -> SharedRepresentation | None: ...


class AttentionState(DTO):
    encoder: EncoderSpec
    width: int = Field(default=64, ge=8, le=128)
    heads: int = Field(default=4, ge=1, le=8)
    weights: dict[str, tuple[tuple[float, ...], ...]]
    train_groups: tuple[str, ...]
    oof_groups: tuple[tuple[str, ...], ...]
    epochs: int = Field(ge=1, le=200)
    objective: str = "two-candidate-bce-sdpa-v1"
    domain_loss_weight: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
