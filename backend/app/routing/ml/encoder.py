"""Offline-only INT8 ONNX token encoder; construction never downloads weights."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from app.config import ROOT
from app.contracts.representations import EncoderSpec, SharedRepresentationPort


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def resolve_asset(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


class OnnxTokenEncoder:
    def __init__(self, spec: EncoderSpec):
        try:
            self._load(spec)
        except Exception as exc:
            raise ValueError("ENCODER_LOAD_FAILED") from exc

    def _load(self, spec: EncoderSpec) -> None:
        if spec.recipe not in {
            "feature-view-v1-token-states",
            "feature-view-v2-balanced-token-budget",
        }:
            raise ValueError("ENCODER_RECIPE_UNSUPPORTED")
        import onnx  # type: ignore[import-not-found, import-untyped, unused-ignore]
        import onnxruntime as ort  # type: ignore[import-not-found, import-untyped, unused-ignore]
        from tokenizers import Tokenizer  # type: ignore[import-not-found, import-untyped, unused-ignore]

        model, tokenizer = resolve_asset(spec.model_path), resolve_asset(spec.tokenizer_path)
        if file_hash(model) != spec.model_sha256 or file_hash(tokenizer) != spec.tokenizer_sha256:
            raise ValueError("ENCODER_HASH_MISMATCH")
        graph = onnx.load(str(model), load_external_data=False)
        if spec.quantization != "int8" or not any(
            n.op_type
            in {"MatMulInteger", "QLinearMatMul", "DynamicQuantizeLinear", "DequantizeLinear"}
            for n in graph.graph.node
        ):
            raise ValueError("ENCODER_NOT_INT8")
        if any(t.data_location == onnx.TensorProto.EXTERNAL for t in graph.graph.initializer):
            raise ValueError("External encoder weights require a separately hashed bundle")
        del graph
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.tokenizer.enable_truncation(max_length=spec.max_tokens)
        self.full_tokenizer = Tokenizer.from_file(str(tokenizer))
        self.full_tokenizer.no_truncation()
        self.special_ids = self.full_tokenizer.encode("").ids
        self.spec = spec
        self.shared: SharedRepresentationPort | None = None

    def encode(self, text: str) -> tuple[np.ndarray, np.ndarray, str]:
        try:
            return self._encode(text)
        except Exception as exc:
            raise ValueError("ENCODER_INFERENCE_FAILED") from exc

    def _encode(self, text: str) -> tuple[np.ndarray, np.ndarray, str]:
        digest = hashlib.sha256(text.encode()).hexdigest()
        if self.shared:
            try:
                supplied = self.shared.representation_for(text, self.spec)
            except Exception:
                supplied = None
            if (
                supplied is not None
                and supplied.encoder_fingerprint == self.spec.fingerprint
                and supplied.input_digest == digest
            ):
                try:
                    states = np.asarray(supplied.hidden_states, dtype=np.float32)
                    mask = np.asarray(supplied.attention_mask, dtype=bool)
                except (ValueError, TypeError):
                    states, mask = np.empty((0, 0), dtype=np.float32), np.empty(0, dtype=bool)
                if (
                    states.ndim == 2
                    and states.shape[1] == self.spec.hidden_size
                    and 0 < len(states) <= self.spec.max_tokens
                    and mask.shape == (len(states),)
                    and mask.any()
                    and np.isfinite(states).all()
                ):
                    return states, mask, "shared"
        if self.spec.recipe == "feature-view-v2-balanced-token-budget":
            current, _, rest = text.removeprefix("CURRENT\n").partition("\nRECENT\n")
            recent, _, evidence = rest.partition("\nEVIDENCE\n")
            parts = [
                self.full_tokenizer.encode(p, add_special_tokens=False).ids
                for p in (current, recent, evidence)
            ]
            budget = self.spec.max_tokens - 2
            side = min(budget // 4, sum(len(p) for p in parts[1:]))
            current_budget = budget - side

            # Preserve the beginning and, especially, the final question/instructions.
            def bounded(tokens: list[int], count: int) -> list[int]:
                if count <= 0:
                    return []
                if len(tokens) <= count:
                    return tokens
                head = count // 4
                return tokens[:head] + tokens[-(count - head) :]

            selected = bounded(parts[0], current_budget)
            remaining = budget - len(selected)
            for i, part in enumerate(parts[1:]):
                count = (
                    remaining
                    if i == 1
                    else min(len(part), remaining - min(len(parts[2]), remaining // 2))
                )
                chosen = bounded(part, count)
                selected.extend(chosen)
                remaining -= len(chosen)
            if len(self.special_ids) != 2:
                raise ValueError("ENCODER_SPECIAL_TOKENS_UNSUPPORTED")
            ids = [self.special_ids[0], *selected, self.special_ids[-1]]
        else:
            ids = self.tokenizer.encode(text).ids
        arrays = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.ones((1, len(ids)), dtype=np.int64),
            "token_type_ids": np.zeros((1, len(ids)), dtype=np.int64),
        }
        inputs = {entry.name: arrays[entry.name] for entry in self.session.get_inputs()}
        outputs: list[Any] = self.session.run(None, inputs)
        states = np.asarray(outputs[0], dtype=np.float32)[0]
        mask = arrays["attention_mask"][0].astype(bool)
        if (
            states.shape != (len(mask), self.spec.hidden_size)
            or not mask.any()
            or not np.isfinite(states).all()
        ):
            raise ValueError("ENCODER_OUTPUT_INVALID")
        return states, mask, "onnx_int8"
