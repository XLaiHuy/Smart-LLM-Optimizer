"""Learned six-query pooling: SDPA training/inference and matching NumPy CPU path."""

from typing import Any

import numpy as np

from app.contracts.representations import AttentionState

ATTENTION_FEATURES = tuple(f"task_attention_{i}" for i in range(6))


def shapes(input_size: int, width: int) -> dict[str, tuple[int, int]]:
    return {
        "projection": (input_size, width),
        "queries": (6, width),
        "q": (width, width),
        "k": (width, width),
        "v": (width, width),
        "out": (width, width),
        "readout": (6, width),
        "bias": (1, 6),
    }


def validate_attention(state: AttentionState) -> None:
    expected = shapes(state.encoder.hidden_size, state.width)
    if state.width % state.heads or set(state.weights) != set(expected):
        raise ValueError("Invalid attention schema")
    for key, shape in expected.items():
        array = np.asarray(state.weights[key])
        if array.shape != shape or not np.isfinite(array).all():
            raise ValueError("Invalid attention weights")
    if (
        len(set(state.train_groups)) != len(state.train_groups)
        or set(g for fold in state.oof_groups for g in fold) != set(state.train_groups)
        or sum(map(len, state.oof_groups)) != len(state.train_groups)
        or len(state.oof_groups) < 2
    ):
        raise ValueError("Invalid attention OOF provenance")


def numpy_features(
    state: AttentionState,
    states: np.ndarray,
    mask: np.ndarray,
    *,
    weights: dict[str, np.ndarray] | None = None,
) -> np.ndarray:
    w = (
        weights
        if weights is not None
        else {key: np.asarray(value, dtype=np.float32) for key, value in state.weights.items()}
    )
    x = states @ w["projection"]
    h, d = state.heads, state.width // state.heads
    q = (w["queries"] @ w["q"]).reshape(6, h, d).transpose(1, 0, 2)
    k = (x @ w["k"]).reshape(-1, h, d).transpose(1, 0, 2)
    v = (x @ w["v"]).reshape(-1, h, d).transpose(1, 0, 2)
    scores = (q @ k.transpose(0, 2, 1)) / np.sqrt(d)
    scores[:, :, ~mask] = -np.inf
    scores -= scores.max(axis=-1, keepdims=True)
    attention = np.exp(scores)
    attention /= attention.sum(axis=-1, keepdims=True)
    out = (attention @ v).transpose(1, 0, 2).reshape(6, state.width) @ w["out"]
    logits = (out * w["readout"]).sum(axis=-1) + w["bias"][0]
    return np.asarray(1 / (1 + np.exp(-np.clip(logits, -80, 80))), dtype=np.float32)


def torch_module(input_size: int, width: int = 64, heads: int = 4) -> Any:
    import torch  # type: ignore[import-not-found, import-untyped, unused-ignore]
    from torch import nn  # type: ignore[import-not-found, import-untyped, unused-ignore]
    from torch.nn import functional as f  # type: ignore[import-not-found, import-untyped, unused-ignore]

    class Pooler(nn.Module):  # type: ignore[misc, unused-ignore]
        def __init__(self) -> None:
            super().__init__()
            self.weights = nn.ParameterDict(
                {
                    key: nn.Parameter(torch.randn(shape) * (1 / np.sqrt(shape[-1])))
                    for key, shape in shapes(input_size, width).items()
                }
            )
            self.auxiliary = nn.Linear(6, 2)

        def forward(self, states: Any, mask: Any) -> Any:
            w = self.weights
            x = states @ w["projection"]
            size, length, _ = x.shape
            d = width // heads
            q = (
                (w["queries"] @ w["q"])
                .reshape(6, heads, d)
                .transpose(0, 1)
                .unsqueeze(0)
                .expand(size, -1, -1, -1)
            )
            k = (x @ w["k"]).reshape(size, length, heads, d).transpose(1, 2)
            v = (x @ w["v"]).reshape(size, length, heads, d).transpose(1, 2)
            attended = f.scaled_dot_product_attention(
                q, k, v, attn_mask=mask[:, None, None, :], dropout_p=0.0
            )
            out = attended.transpose(1, 2).reshape(size, 6, width) @ w["out"]
            return torch.sigmoid((out * w["readout"]).sum(-1) + w["bias"])

    return Pooler()


def sdpa_features(
    state: AttentionState,
    states: np.ndarray,
    mask: np.ndarray,
    device: str = "cpu",
    *,
    modules: dict[str, Any] | None = None,
) -> np.ndarray:
    from contextlib import nullcontext

    import torch  # type: ignore[import-not-found, import-untyped, unused-ignore]

    dtype = torch.float16 if device == "cuda" else torch.float32
    module = modules.get(device) if modules is not None else None
    if module is None:
        with torch.random.fork_rng():
            module = torch_module(state.encoder.hidden_size, state.width, state.heads)
        module.weights.load_state_dict(
            {k: torch.tensor(v, dtype=torch.float32) for k, v in state.weights.items()}
        )
        module.to(device=device, dtype=dtype).eval()
        if modules is not None:
            modules[device] = module
    kernel = (
        torch.nn.attention.sdpa_kernel(torch.nn.attention.SDPBackend.FLASH_ATTENTION)
        if device == "cuda"
        else nullcontext()
    )
    with torch.inference_mode(), kernel:
        output = module(
            torch.as_tensor(states.copy(), dtype=dtype, device=device).unsqueeze(0),
            torch.as_tensor(mask.copy(), dtype=torch.bool, device=device).unsqueeze(0),
        )
    return np.asarray(output[0].float().cpu().numpy(), dtype=np.float32)
