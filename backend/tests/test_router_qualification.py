"""Qualification is separate from loading and per-request execution."""

from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest

from app.contracts.dtos import (
    ContextResult,
    CostSnapshot,
    FeatureFlags,
    Message,
    ModelConfiguration,
    OptimizationState,
    PolicySnapshot,
    RegistrySnapshot,
    RemainingBudget,
    RouteRate,
    TaskProfile,
)
from app.routing.ml.multi import configuration_hash
from app.routing.ml.qualification import QualificationReview, regression_upper_95, review_failure
from app.routing.policies import PolicyRouter, _artifact_cost_hash


def test_catalog_identity_does_not_substitute_admission_cache_write_price():
    from app.providers.catalog import Catalog, ModelEntry

    entry = ModelEntry(
        config_id="candidate",
        model_id="fake",
        kind="generation",
        context_window=10000,
        max_output_tokens=128,
        input_per_million=".1",
        output_per_million=".5",
        cache_write_per_million=".125",
        source_url="https://example.com/test",
        effective_at="test",
        verified_access=True,
        pricing_verified=True,
    )
    catalog = Catalog.model_construct(version="reviewed", models=(entry,))
    costs = catalog.cost_snapshot()
    assert costs.rates[0].input_per_million == Decimal(".1")
    profile = TaskProfile()
    prepared = ContextResult(
        messages=(Message(role="user", content="test"),),
        provenance=(),
        state=OptimizationState(module="context", status="disabled", reason="test"),
    )
    registry = RegistrySnapshot(
        configurations=(
            ModelConfiguration(
                config_id="candidate", model_id="fake", context_window=10000, max_output_tokens=128
            ),
        ),
        mock_config_id="candidate",
    )
    route = PolicyRouter(admission_input_rates=catalog.admission_input_rates()).select(
        profile,
        prepared,
        registry,
        costs,
        PolicySnapshot(policy_id="fixed", strategy="fixed_reference", flags=FeatureFlags()),
        RemainingBudget(),
    )
    estimate = route.estimates[0]
    assert estimate.upper_usd == (
        Decimal(estimate.input_bound) * Decimal(".125") + Decimal(128) * Decimal(".5")
    ) / Decimal(1000000)
    assert costs.rates[0].input_per_million == Decimal(".1")


def setup_engine():
    models = tuple(
        ModelConfiguration(
            config_id=k,
            model_id=k,
            execution_source="live",
            context_window=10000,
            max_output_tokens=128,
        )
        for k in ("small", "medium", "reference")
    )
    registry = RegistrySnapshot(configurations=models, mock_config_id="reference")
    costs = CostSnapshot(
        version="measured-v1",
        rates=tuple(
            RouteRate(
                config_id=c.config_id,
                input_per_million=Decimal(i + 1),
                output_per_million=Decimal(i + 1),
            )
            for i, c in enumerate(models)
        ),
    )
    artifact = SimpleNamespace(
        purpose="qualified_dev",
        grader_version="reviewed-gold-v1",
        configurations=models,
        attention=object(),
        dataset_hash="b" * 64,
        configuration_hashes={c.config_id: configuration_hash(c) for c in models},
        costs_hash=_artifact_cost_hash(costs, {c.config_id for c in models}),
        catalog_version=costs.version,
        reference_config_id="reference",
        model_version="test-only",
        latency_ms={c.config_id: 1.0 for c in models},
        predictors=(
            SimpleNamespace(config_id="small", threshold=0.8),
            SimpleNamespace(config_id="medium", threshold=0.8),
        ),
    )
    semantic = SimpleNamespace(
        features=lambda _: np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]), backend="numpy"
    )
    multi = SimpleNamespace(
        artifact=artifact, hash="a" * 64, semantic=semantic, score=lambda *_: 0.9
    )
    engine = SimpleNamespace(
        multi=multi,
        artifact=None,
        hash=multi.hash,
        live_approved=True,
        allow_research_candidate=False,
        status="ML_ARTIFACT_READY",
    )
    return engine, registry, costs


@pytest.mark.parametrize(
    "small_score,luna_score,expected",
    [
        (0.690085, 0.99, "small"),
        (0.690084, 0.71, "medium"),
        (0.690084, 0.709999, "reference"),
    ],
)
def test_operator_requested_global_threshold_boundaries(
    tmp_path, small_score, luna_score, expected
):
    engine, registry, costs = setup_engine()
    engine.multi.artifact.purpose = "research_candidate"
    engine.allow_research_candidate = True
    engine.live_approved = False
    engine.multi.artifact.predictors[0].threshold = 0.690085
    engine.multi.artifact.predictors[1].threshold = 0.71
    engine.multi.score = lambda config, *_: small_score if config == "small" else luna_score
    path, _ = research_receipt(engine, tmp_path)
    result = PolicyRouter(engine, require_review=True, research_acceptance_path=path).select(
        TaskProfile(),
        context(),
        registry,
        costs,
        PolicySnapshot(
            policy_id="operator-threshold-test",
            strategy="ml_multi_model",
            flags=FeatureFlags(router=True),
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )
    assert result.config_id == expected
    assert result.ml_executed and result.attention_executed
    assert "operator_accepted_research" in result.rules_matched


def context():
    return ContextResult(
        messages=(Message(role="user", content="1+1?\nGive only the final numeric answer."),),
        provenance=(),
        state=OptimizationState(module="context", status="disabled", reason="test"),
    )


def receipt(engine, path):
    a = engine.multi.artifact
    path.write_text(
        QualificationReview(
            artifact_hash=engine.hash,
            dataset_hash=a.dataset_hash,
            holdout_hash="c" * 64,
            configuration_hashes=a.configuration_hashes,
            costs_hash=a.costs_hash,
            reviewed_by="test-operator",
            domains=("math_reasoning",),
            measured_e2e_report_sha256="d" * 64,
            holdout_report={},
            ablation_report={},
            passed=True,
        ).model_dump_json(),
        encoding="utf-8",
    )


def route(engine, registry, costs, path):
    return PolicyRouter(engine, review_path=path, require_review=True).select(
        TaskProfile(),
        context(),
        registry,
        costs,
        PolicySnapshot(
            policy_id="test", strategy="ml_multi_model", flags=FeatureFlags(router=True)
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )


def test_loaded_is_not_executed_without_review(tmp_path):
    engine, registry, costs = setup_engine()
    result = route(engine, registry, costs, tmp_path / "missing.json")
    assert result.reason == "ML_REVIEW_REQUIRED_FALLBACK"
    assert result.ml_loaded and result.attention_loaded
    assert result.ml_executed is False and result.attention_executed is False
    assert result.stages == ()


def test_valid_review_executes_ml_attention_and_records_request_values(tmp_path):
    engine, registry, costs = setup_engine()
    path = tmp_path / "review.json"
    receipt(engine, path)
    result = route(engine, registry, costs, path)
    assert result.config_id == "small"
    assert result.ml_executed and result.attention_executed
    assert result.attention_features == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    assert result.stages[0].score == 0.9


def test_qualified_tag_cannot_override_synthetic_labels(tmp_path):
    engine, registry, costs = setup_engine()
    engine.multi.artifact.grader_version = "synthetic-labels-v3-not-a-grader"
    path = tmp_path / "review.json"
    receipt(engine, path)
    result = route(engine, registry, costs, path)
    assert result.reason == "ML_SYNTHETIC_EVIDENCE_FALLBACK"
    assert result.ml_executed is False


def test_missing_attention_corrupt_or_stale_review_is_rejected(tmp_path):
    engine, _, _ = setup_engine()
    path = tmp_path / "review.json"
    path.write_text("not json", encoding="utf-8")
    assert review_failure(engine.multi, path) == "ML_REVIEW_INVALID_FALLBACK"
    receipt(engine, path)
    engine.multi.hash = "f" * 64
    assert review_failure(engine.multi, path) == "ML_REVIEW_MISMATCH_FALLBACK"
    engine.multi.artifact.attention = None
    assert review_failure(engine.multi, path) == "ML_ATTENTION_REQUIRED_FALLBACK"


def test_catalog_changes_block_execution_even_with_review(tmp_path):
    engine, registry, costs = setup_engine()
    path = tmp_path / "review.json"
    receipt(engine, path)
    result = route(engine, registry, costs.model_copy(update={"version": "changed"}), path)
    assert result.reason == "ML_CATALOG_CHANGED_FALLBACK"
    assert not result.ml_executed


def test_tiny_perfect_samples_do_not_prove_the_quality_margin():
    assert regression_upper_95(0, 10) > 0.03
    assert regression_upper_95(0, 100) < 0.03
    assert regression_upper_95(3, 100) > 0.03


@pytest.mark.parametrize(
    "text",
    [
        "Bạn có nhớ tên tôi không?",
        "Viết hàm Python tính tổng",
        "1+1?",
        "A. một\nB. hai\nB. ba\nChỉ trả lời một chữ cái trong các lựa chọn.",
        "```python\nprint(1)\n```\nGive only the final numeric answer.",
    ],
)
def test_review_does_not_grant_general_chat_coverage(tmp_path, text):
    engine, registry, costs = setup_engine()
    path = tmp_path / "review.json"
    receipt(engine, path)
    result = PolicyRouter(engine, review_path=path, require_review=True).select(
        TaskProfile(),
        context().model_copy(update={"messages": (Message(role="user", content=text),)}),
        registry,
        costs,
        PolicySnapshot(
            policy_id="test", strategy="ml_multi_model", flags=FeatureFlags(router=True)
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )
    assert result.reason == "ML_UNREVIEWED_SCOPE_FALLBACK"
    assert not result.ml_executed and not result.attention_executed


def test_reviewed_numeric_scope_does_not_cover_history_or_rag(tmp_path):
    from app.routing.ml.qualification import reviewed_scope_failure

    engine, registry, costs = setup_engine()
    path = tmp_path / "review.json"
    receipt(engine, path)
    history = context().model_copy(
        update={
            "messages": (
                Message(role="assistant", content="previous answer"),
                *context().messages,
            )
        }
    )
    assert reviewed_scope_failure(history, path) == "ML_UNREVIEWED_SCOPE_FALLBACK"
    result = PolicyRouter(engine, review_path=path, require_review=True).select(
        TaskProfile(has_rag_context=True),
        context(),
        registry,
        costs,
        PolicySnapshot(
            policy_id="test", strategy="ml_multi_model", flags=FeatureFlags(router=True)
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )
    assert result.reason == "ML_UNREVIEWED_SCOPE_FALLBACK"


def test_mcq_needs_its_own_reviewed_domain(tmp_path):
    from app.routing.ml.qualification import reviewed_scope_failure

    engine, _, _ = setup_engine()
    path = tmp_path / "review.json"
    receipt(engine, path)
    question = context().model_copy(
        update={
            "messages": (
                Message(
                    role="user",
                    content="Chọn\nA. một\nB. hai\nC. ba\nChỉ trả lời một chữ cái trong các lựa chọn.",
                ),
            )
        }
    )
    assert reviewed_scope_failure(question, path) == "ML_UNREVIEWED_SCOPE_FALLBACK"
    review = QualificationReview.model_validate_json(path.read_text(encoding="utf-8"))
    path.write_text(
        review.model_copy(update={"domains": ("vietnamese_mcq",)}).model_dump_json(),
        encoding="utf-8",
    )
    assert reviewed_scope_failure(question, path) is None


def research_receipt(engine, tmp_path):
    import hashlib

    from app.routing.ml.qualification import ResearchAcceptance

    report = tmp_path / "failed-qualification.json"
    report.write_text('{"passed":false,"issues":["functional-test-only"]}', encoding="utf-8")
    a = engine.multi.artifact
    path = tmp_path / "acceptance.json"
    path.write_text(
        ResearchAcceptance(
            artifact_hash=engine.hash,
            dataset_hash=a.dataset_hash,
            configuration_hashes=a.configuration_hashes,
            costs_hash=a.costs_hash,
            accepted_by="test operator",
            accepted_at="2026-10-27T00:00:00Z",
            decision="Explicitly accept the measured research model for development chat.",
            qualification_report_path=str(report),
            qualification_report_sha256=hashlib.sha256(report.read_bytes()).hexdigest(),
        ).model_dump_json(),
        encoding="utf-8",
    )
    return path, report


def test_operator_accepted_research_executes_attention_without_forging_qualification(tmp_path):
    engine, registry, costs = setup_engine()
    engine.multi.artifact.purpose = "research_candidate"
    engine.allow_research_candidate = True
    engine.live_approved = False
    path, report = research_receipt(engine, tmp_path)
    result = PolicyRouter(engine, require_review=True, research_acceptance_path=path).select(
        TaskProfile(),
        context().model_copy(update={"messages": (Message(role="user", content="1+1?"),)}),
        registry,
        costs,
        PolicySnapshot(
            policy_id="test", strategy="ml_multi_model", flags=FeatureFlags(router=True)
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )
    assert result.reason == "ROUTE_ML_RESEARCH_CANDIDATE"
    assert "operator_accepted_research" in result.rules_matched
    assert result.ml_executed and result.attention_executed
    assert engine.multi.artifact.purpose == "research_candidate"
    assert '"passed":false' in report.read_text(encoding="utf-8")


def test_research_switch_alone_does_not_replace_operator_acceptance(tmp_path):
    engine, registry, costs = setup_engine()
    engine.multi.artifact.purpose = "research_candidate"
    engine.allow_research_candidate = True
    result = route(engine, registry, costs, tmp_path / "missing-review.json")
    assert result.reason == "ML_RESEARCH_ACCEPTANCE_REQUIRED_FALLBACK"
    assert not result.ml_executed


def test_research_acceptance_cannot_override_disabled_switch_or_catalog_mismatch(tmp_path):
    engine, registry, costs = setup_engine()
    engine.multi.artifact.purpose = "research_candidate"
    path, _ = research_receipt(engine, tmp_path)
    router = PolicyRouter(engine, require_review=True, research_acceptance_path=path)
    args = (
        TaskProfile(),
        context(),
        registry,
        costs,
        PolicySnapshot(
            policy_id="test", strategy="ml_multi_model", flags=FeatureFlags(router=True)
        ),
        RemainingBudget(usd=Decimal(1), deadline_ms=60000),
    )
    assert router.select(*args).reason == "ML_NOT_QUALIFIED_FALLBACK"
    engine.allow_research_candidate = True
    bad = list(args)
    bad[3] = costs.model_copy(update={"version": "changed"})
    assert router.select(*bad).reason == "ML_CATALOG_CHANGED_FALLBACK"


def test_research_acceptance_is_bound_to_exact_artifact_and_failed_report(tmp_path):
    from app.routing.ml.qualification import research_acceptance_failure

    engine, _, _ = setup_engine()
    engine.multi.artifact.purpose = "research_candidate"
    path, report = research_receipt(engine, tmp_path)
    assert research_acceptance_failure(engine.multi, path) is None
    report.write_text('{"passed":true}', encoding="utf-8")
    assert (
        research_acceptance_failure(engine.multi, path)
        == "ML_RESEARCH_ACCEPTANCE_MISMATCH_FALLBACK"
    )
    path, report = research_receipt(engine, tmp_path)
    engine.multi.hash = "changed"
    assert (
        research_acceptance_failure(engine.multi, path)
        == "ML_RESEARCH_ACCEPTANCE_MISMATCH_FALLBACK"
    )
    engine.multi.artifact.grader_version = "synthetic-labels"
    assert (
        research_acceptance_failure(engine.multi, path) == "ML_RESEARCH_ARTIFACT_INVALID_FALLBACK"
    )


@pytest.mark.parametrize(
    "environment,enabled,expected",
    [("test", True, False), ("development", False, False), ("development", True, True)],
)
def test_research_chat_is_development_only(environment, enabled, expected):
    from app.config import Settings

    settings = Settings(
        _env_file=None, app_env=environment, ml_router_allow_research_candidate=enabled
    )
    assert settings.research_chat_enabled is expected
