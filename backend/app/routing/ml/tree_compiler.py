"""Bounded, data-only binary GBDT trees with sklearn-compatible split precision."""

import math
from typing import Any

import numpy as np


def _compile_single_tree(tree_obj: Any) -> dict[str, Any]:
    children_left = tree_obj.children_left
    children_right = tree_obj.children_right
    feature = tree_obj.feature
    threshold = tree_obj.threshold
    value = tree_obj.value

    def recurse(node_id: int) -> dict[str, Any]:
        if children_left[node_id] == -1 and children_right[node_id] == -1:
            return {"leaf": float(value[node_id][0][0])}
        return {
            "feat": int(feature[node_id]),
            "th": float(threshold[node_id]),
            "left": recurse(children_left[node_id]),
            "right": recurse(children_right[node_id]),
        }

    return recurse(0)


def compile_sklearn_gbdt(
    clf: Any, feature_names: tuple[str, ...]
) -> tuple[tuple[dict[str, Any], ...], dict[str, float], float]:
    """Compiles scikit-learn GradientBoostingClassifier into a pure JSON tree forest."""
    if len(clf.classes_) != 2 or len(feature_names) != clf.n_features_in_:
        raise ValueError("Only binary GBDT with matching feature names is supported")
    compiled_trees: list[dict[str, Any]] = [
        _compile_single_tree(est[0].tree_) for est in clf.estimators_
    ]

    # Feature importances
    importances = np.maximum(clf.feature_importances_, 0.0)
    total_imp = float(np.sum(importances)) or 1.0
    feat_imp = {
        name: float(np.clip(imp / total_imp, 0.0, 1.0))
        for name, imp in zip(feature_names, importances, strict=True)
    }
    total_norm = sum(feat_imp.values())
    if total_norm > 0:
        feat_imp = {name: float(np.clip(v / total_norm, 0.0, 1.0)) for name, v in feat_imp.items()}

    # Initial baseline raw logit (intercept / prior)
    init_score = 0.0
    if isinstance(clf.init_, str) and clf.init_ == "zero":
        init_score = 0.0
    elif hasattr(clf.init_, "class_prior_"):
        priors = clf.init_.class_prior_
        epsilon = np.finfo(np.float32).eps
        probability = np.clip(priors[1], epsilon, 1 - epsilon)
        init_score = float(np.log(probability / (1 - probability)))
    else:
        raise ValueError("Custom GBDT initial estimators are not supported")

    validate_forest(tuple(compiled_trees), len(feature_names))
    return tuple(compiled_trees), feat_imp, init_score


def validate_forest(trees: tuple[dict[str, Any], ...], feature_count: int) -> None:
    """Reject malformed/oversized forests before any serving request uses them."""
    if not 1 <= len(trees) <= 256 or feature_count < 1:
        raise ValueError("Invalid forest size or feature count")
    pending = [(tree, 0) for tree in trees]
    nodes = 0
    while pending:
        node, depth = pending.pop()
        nodes += 1
        if nodes > 32768 or depth > 16 or not isinstance(node, dict):
            raise ValueError("Invalid or oversized tree")
        if set(node) == {"leaf"}:
            value = node["leaf"]
        elif set(node) == {"feat", "th", "left", "right"}:
            if type(node["feat"]) is not int or not 0 <= node["feat"] < feature_count:
                raise ValueError("Tree feature index out of range")
            value = node["th"]
            pending.extend(((node["left"], depth + 1), (node["right"], depth + 1)))
        else:
            raise ValueError("Invalid tree node schema")
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("Tree values must be finite numbers")


def evaluate_forest_prob(
    trees: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    features: list[float] | tuple[float, ...] | np.ndarray,
    init_score: float = 0.0,
    learning_rate: float = 0.1,
) -> float:
    """Evaluate validated trees; sklearn casts tree inputs to float32 before splitting."""
    with np.errstate(over="raise", invalid="raise"):
        values = np.asarray(features, dtype=np.float32)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Invalid tree input")
    total = init_score
    for tree in trees:
        curr = tree
        depth = 0
        while "leaf" not in curr:
            depth += 1
            if depth > 16:
                raise ValueError("Tree depth exceeded")
            feat_idx = curr["feat"]
            if type(feat_idx) is not int or not 0 <= feat_idx < len(values):
                raise ValueError("Tree feature index out of range")
            if float(values[feat_idx]) <= curr["th"]:
                curr = curr["left"]
            else:
                curr = curr["right"]
        total += learning_rate * curr["leaf"]

    # Sigmoid function
    if not math.isfinite(total):
        raise ValueError("Non-finite tree output")
    clipped = np.clip(total, -700.0, 700.0)
    return float(1.0 / (1.0 + np.exp(-clipped)))
