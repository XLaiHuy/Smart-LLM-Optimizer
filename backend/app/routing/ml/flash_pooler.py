"""Experimental attention pooler, not a trained semantic encoder or serving feature.

Provides cross-attention task pooling over token embeddings using:
1. Multi-head NumPy cross-attention over caller-supplied embeddings.
2. Stable hash-based text fixtures for software experiments only; no ONNX encoder.
3. Dual-Mode Input:
   - Standalone Mode: Generates hash-based random text fixtures, not semantic embeddings.
   - Shared Representation Mode: Directly takes `hidden_states` tensor from Tan's compression module (encoder reuse; pooling still costs time).
"""

from __future__ import annotations

import hashlib
import math
from typing import cast

import numpy as np

TASK_DOMAINS = (
    "math_reasoning",
    "coding_algorithms",
    "legal_regulations",
    "medical_bio",
    "reading_comp_rag",
    "dialogue_chat",
)

NUM_TASKS = len(TASK_DOMAINS)
DEFAULT_EMBED_DIM = 64
DEFAULT_NUM_HEADS = 4


def _softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Numerically stable softmax in NumPy."""
    x_max = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - x_max)
    return cast(np.ndarray, exp_x / np.sum(exp_x, axis=axis, keepdims=True))


class FlashAttentionTaskPooler:
    """Multi-Head Cross-Attention Pooler targeting multi-domain task queries."""

    def __init__(
        self,
        embed_dim: int = DEFAULT_EMBED_DIM,
        num_task_queries: int = NUM_TASKS,
        num_heads: int = DEFAULT_NUM_HEADS,
        weights: dict[str, np.ndarray] | None = None,
        seed: int = 42,
    ) -> None:
        if embed_dim <= 0 or num_heads <= 0 or embed_dim % num_heads or num_task_queries <= 0:
            raise ValueError("Positive dimensions and embed_dim divisible by num_heads required")
        self.embed_dim = embed_dim
        self.num_task_queries = num_task_queries
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        rng = np.random.RandomState(seed)
        if weights is not None:
            self.task_queries = np.asarray(weights["task_queries"], dtype=np.float32)
            self.w_q = np.asarray(weights["w_q"], dtype=np.float32)
            self.w_k = np.asarray(weights["w_k"], dtype=np.float32)
            self.w_v = np.asarray(weights["w_v"], dtype=np.float32)
            self.w_out = np.asarray(weights["w_out"], dtype=np.float32)
        else:
            scale = 1.0 / math.sqrt(embed_dim)
            # (num_task_queries, embed_dim)
            self.task_queries = rng.normal(0, scale, (num_task_queries, embed_dim)).astype(
                np.float32
            )
            self.w_q = rng.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
            self.w_k = rng.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
            self.w_v = rng.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)
            self.w_out = rng.normal(0, scale, (embed_dim, embed_dim)).astype(np.float32)

    def export_weights(self) -> dict[str, list[list[float]]]:
        """Export pooler weights to JSON-serializable dictionary."""
        return {
            "task_queries": self.task_queries.tolist(),
            "w_q": self.w_q.tolist(),
            "w_k": self.w_k.tolist(),
            "w_v": self.w_v.tolist(),
            "w_out": self.w_out.tolist(),
        }

    def pool_tokens(self, token_embeddings: np.ndarray) -> np.ndarray:
        """Cross-attend task queries over token embeddings X: (L, embed_dim).

        Returns:
            task_affinity_scores: 1D array of length `num_task_queries` in [0, 1].
        """
        if token_embeddings.ndim == 1:
            token_embeddings = token_embeddings.reshape(1, -1)
        if (
            token_embeddings.ndim != 2
            or not len(token_embeddings)
            or not np.isfinite(token_embeddings).all()
        ):
            raise ValueError("Expected nonempty finite token embeddings")
        if token_embeddings.shape[1] != self.embed_dim:
            # Linear projection or truncation to match embed_dim
            current_dim = token_embeddings.shape[1]
            if current_dim > self.embed_dim:
                token_embeddings = token_embeddings[:, : self.embed_dim]
            else:
                padded = np.zeros((token_embeddings.shape[0], self.embed_dim), dtype=np.float32)
                padded[:, :current_dim] = token_embeddings
                token_embeddings = padded

        if (
            token_embeddings.ndim != 2
            or not len(token_embeddings)
            or not np.isfinite(token_embeddings).all()
        ):
            raise ValueError("Expected nonempty finite token embeddings")
        token_embeddings = np.asarray(token_embeddings, dtype=np.float32)
        # The CPU implementation follows the same per-head attention as SDPA.
        queries = (
            (self.task_queries @ self.w_q)
            .reshape(self.num_task_queries, self.num_heads, self.head_dim)
            .transpose(1, 0, 2)
        )
        keys = (
            (token_embeddings @ self.w_k)
            .reshape(-1, self.num_heads, self.head_dim)
            .transpose(1, 0, 2)
        )
        values = (
            (token_embeddings @ self.w_v)
            .reshape(-1, self.num_heads, self.head_dim)
            .transpose(1, 0, 2)
        )
        scores = (queries @ keys.transpose(0, 2, 1)) / math.sqrt(self.head_dim)
        attended = (
            (_softmax(scores) @ values)
            .transpose(1, 0, 2)
            .reshape(self.num_task_queries, self.embed_dim)
        )
        out = attended @ self.w_out

        # Normalize and compute task affinity magnitude: (K,)
        norms = np.linalg.norm(out, axis=-1)
        total_energy = float(np.sum(norms)) + 1e-6
        return cast(np.ndarray, (norms / total_energy).astype(np.float32))

    def extract_from_text(self, text: str, shared_tensor: np.ndarray | None = None) -> np.ndarray:
        """Dual-Mode feature extraction:

        1. If `shared_tensor` is provided (from Tan's token compression), reuse directly (encoder reuse; pooling still costs time).
        2. Else, run lightweight standalone character/token projection to generate input tensor.
        """
        if shared_tensor is not None:
            return self.pool_tokens(np.asarray(shared_tensor, dtype=np.float32))

        # Standalone lightweight deterministic token embedding projection
        # Breaks text into word/subword chunks and hashes into (L, embed_dim)
        words = text.split()
        if not words:
            words = ["<empty>"]
        seq_len = min(len(words), 256)
        matrix = np.zeros((seq_len, self.embed_dim), dtype=np.float32)

        for i in range(seq_len):
            w = words[i]
            h = int.from_bytes(hashlib.sha256(w.encode("utf-8")).digest()[:8], "big")
            rng_word = np.random.RandomState(abs(h) % (2**31 - 1))
            matrix[i] = rng_word.normal(0, 1.0, self.embed_dim)

        return self.pool_tokens(matrix)
