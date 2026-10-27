"""Loaded Attention artifacts must never reuse another artifact's cached weights."""

from types import SimpleNamespace

import numpy as np

from app.routing.ml import attention


def test_stale_identity_cache_does_not_change_new_artifact_predictions():
    old = {
        k: np.ones(shape, dtype=np.float32).tolist() for k, shape in attention.shapes(2, 4).items()
    }
    new = {
        k: np.zeros(shape, dtype=np.float32).tolist() for k, shape in attention.shapes(2, 4).items()
    }
    state = SimpleNamespace(weights=new, width=4, heads=2)
    states, mask = np.ones((3, 2), dtype=np.float32), np.ones(3, dtype=bool)
    old_arrays = {k: np.asarray(v, dtype=np.float32) for k, v in old.items()}
    attention._WEIGHTS_CACHE.clear()
    try:
        # Deterministically emulate a stale/reused identity without relying on GC.
        attention._WEIGHTS_CACHE[id(new)] = (old, old_arrays)
        actual = attention.numpy_features(state, states, mask)
        expected = attention.numpy_features(
            state,
            states,
            mask,
            weights={k: np.asarray(v, dtype=np.float32) for k, v in new.items()},
        )
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual, np.full(6, 0.5))
        assert attention._WEIGHTS_CACHE[id(new)][0] is new
        np.testing.assert_array_equal(attention.numpy_features(state, states, mask), expected)
    finally:
        attention._WEIGHTS_CACHE.clear()
