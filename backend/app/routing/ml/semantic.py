"""Grouped-OOF learned attention features, using the same INT8 states at fit/serve."""

from collections import OrderedDict
from threading import RLock
from typing import Any

import numpy as np
from sklearn.model_selection import GroupKFold  # type: ignore[import-untyped]

from app.contracts.representations import AttentionState, EncoderSpec
from app.routing.ml.attention import numpy_features, sdpa_features, torch_module, validate_attention
from app.routing.ml.encoder import OnnxTokenEncoder


class SemanticRuntime:
    def __init__(self, state: AttentionState):
        validate_attention(state)
        self.state = state
        self.encoder = OnnxTokenEncoder(state.encoder)
        self.backend = "numpy"
        self.last_source = "none"
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.lock = RLock()
        self.numpy_weights = {k: np.asarray(v, dtype=np.float32) for k, v in state.weights.items()}
        self.modules: dict[str, Any] = {}

    def similarity(self, original: str, candidate: str) -> float | None:
        """Paragraph-level guard, using local states; never score truncated text.

        Cosine is a rejection heuristic, not proof of logical equivalence.
        Protected/task paragraphs must still be retained verbatim by the caller.
        """
        vectors = []
        for text in (original, candidate):
            if len(self.encoder.full_tokenizer.encode(text).ids) > self.encoder.spec.max_tokens:
                return None
            states, mask, _ = self.encoder.encode(text)
            vectors.append(states[mask].mean(axis=0))
        denominator = float(np.linalg.norm(vectors[0]) * np.linalg.norm(vectors[1]))
        if denominator <= 0:
            return None
        return float(np.dot(vectors[0], vectors[1]) / denominator)

    def features(self, text: str) -> np.ndarray:
        import hashlib

        key = hashlib.sha256(text.encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key].copy()
        # ORT supports concurrent Run calls. Keep expensive computation outside
        # the cache lock so independent requests can use separate CPU cores.
        states, mask, self.last_source = self.encoder.encode(text)
        if self.backend == "numpy":
            result = numpy_features(self.state, states, mask, weights=self.numpy_weights)
        else:
            with self.lock:
                result = sdpa_features(
                    self.state,
                    states,
                    mask,
                    device="cuda" if self.backend == "cuda_flash" else "cpu",
                    modules=self.modules,
                )
        with self.lock:
            self.cache[key] = result.copy()
            if len(self.cache) > 128:
                self.cache.popitem(last=False)
        return result


def train_attention(
    rows: tuple[Any, ...], encoder_spec: EncoderSpec, epochs: int, domain_loss_weight: float = 0.0
) -> tuple[AttentionState, np.ndarray]:
    import torch  # type: ignore[import-not-found, import-untyped, unused-ignore]

    from app.routing.ml.multi import feature_view

    if not 1 <= epochs <= 200:
        raise ValueError("Attention epochs must be in [1,200]")
    encoder = OnnxTokenEncoder(encoder_spec)
    tokens = [encoder.encode(feature_view(r.context())) for r in rows]
    candidate_ids = [o.config_id for o in rows[0].observations][:]
    length = max(len(x) for x, _, _ in tokens)
    x = np.zeros((len(rows), length, encoder_spec.hidden_size), dtype=np.float32)
    masks = np.zeros((len(rows), length), dtype=bool)
    for i, (states, mask, _) in enumerate(tokens):
        x[i, : len(states)] = states
        masks[i, : len(states)] = mask
    del tokens
    # Reference is explicitly removed by passing target IDs from train_semantic below.
    targets = np.asarray(
        [
            [
                float(next(o.qualified for o in r.observations if o.config_id == target))
                for target in candidate_ids[:2]
            ]
            for r in rows
        ],
        dtype=np.float32,
    )
    return _fit_oof(rows, encoder_spec, epochs, x, masks, targets, torch, domain_loss_weight)


def train_semantic(
    rows: tuple[Any, ...],
    spec: EncoderSpec,
    reference_id: str,
    epochs: int,
    domain_loss_weight: float = 0.0,
) -> tuple[AttentionState, np.ndarray]:
    # Normalize observation order so auxiliary targets are always the two candidates.
    ordered = tuple(
        r.model_copy(
            update={
                "observations": tuple(o for o in r.observations if o.config_id != reference_id)
                + tuple(o for o in r.observations if o.config_id == reference_id)
            }
        )
        for r in rows
    )
    return train_attention(ordered, spec, epochs, domain_loss_weight)


def _fit_oof(
    rows: tuple[Any, ...],
    spec: EncoderSpec,
    epochs: int,
    x: np.ndarray,
    masks: np.ndarray,
    targets: np.ndarray,
    torch: Any,
    domain_loss_weight: float = 0.0,
) -> tuple[AttentionState, np.ndarray]:
    groups = np.asarray([r.group_id for r in rows])
    n_splits = min(3, len(set(groups)))
    if n_splits < 2:
        raise ValueError("Attention needs independent groups for OOF")
    folds = list(GroupKFold(n_splits=n_splits).split(x, groups=groups))
    provenance = tuple(tuple(sorted(set(groups[val]))) for _, val in folds)
    oof = np.zeros((len(rows), 6), dtype=np.float32)

    def fit(indices: np.ndarray) -> Any:
        with torch.random.fork_rng():
            torch.manual_seed(42)
            model = torch_module(spec.hidden_size)
            optimizer = torch.optim.AdamW(model.parameters(), lr=0.003, weight_decay=0.01)
            for _ in range(epochs):
                model.train()
                for start in range(0, len(indices), 64):
                    batch = indices[start : start + 64]
                    optimizer.zero_grad()
                    scores = model(torch.from_numpy(x[batch]), torch.from_numpy(masks[batch]))
                    loss = torch.nn.functional.binary_cross_entropy_with_logits(
                        model.auxiliary(scores), torch.from_numpy(targets[batch])
                    )
                    domains = (
                        "math_reasoning",
                        "coding_algorithms",
                        "legal_regulations",
                        "medical_bio",
                        "reading_comp_rag",
                        "dialogue_chat",
                    )
                    labeled = [
                        (i, domains.index(rows[index].domain))
                        for i, index in enumerate(batch)
                        if rows[index].domain in domains
                    ]
                    if labeled and domain_loss_weight > 0:
                        positions, labels = zip(*labeled, strict=True)
                        logits = torch.logit(scores.clamp(1e-5, 1 - 1e-5))
                        loss = loss + domain_loss_weight * torch.nn.functional.cross_entropy(
                            logits[list(positions)], torch.tensor(labels)
                        )
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
        return model.eval()

    # TRAIN groups only. No calibration/threshold/HOLDOUT row enters any optimizer step.
    for train, validation in folds:
        model = fit(train)
        with torch.inference_mode():
            for start in range(0, len(validation), 64):
                batch = validation[start : start + 64]
                oof[batch] = model(
                    torch.from_numpy(x[batch]), torch.from_numpy(masks[batch])
                ).numpy()
    final = fit(np.arange(len(rows)))
    weights = {
        key: tuple(tuple(float(v) for v in line) for line in value.detach().numpy())
        for key, value in final.weights.items()
    }
    state = AttentionState(
        encoder=spec,
        weights=weights,
        train_groups=tuple(sorted(set(groups))),
        oof_groups=provenance,
        epochs=epochs,
        objective="candidate-qualification-bce-v2",
        domain_loss_weight=domain_loss_weight,
    )
    validate_attention(state)
    return state, oof
