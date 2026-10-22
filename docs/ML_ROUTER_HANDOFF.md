# Lightweight ML router — Huy handoff (2026-10-21)

This document describes the preserved V1 pair policy. The implemented three-model extension, separate calibration/threshold splits, tool-aware features and V2 artifact are documented in [Platform V2 handoff](PLATFORM_V2_HANDOFF.md). V1 uncalibrated-score limitations below do not describe V2's separately fitted sigmoid; neither score is an assurance that an answer is correct.

## Implemented behavior

Chat defaults to Automatic (`optimized` on the wire); Standard retains `baseline`. User-facing VI/EN reasons do not expose classifier scores as answer confidence or claim savings. Mock chat still uses the deterministic provider. Select `ml_router` separately in the admin Lab to exercise the new policy.

Training uses word/character TF-IDF plus total input size, RAG presence, code ratio and a structured-output keyword heuristic, with logistic regression. Runtime loads a data-only JSON artifact once; it never unpickles code, trains, or calls providers. ContextManager remains the only message assembler. The analyzer then reads full role-preserving serving messages, including history and RAG. Keywords do not enforce JSON Schema; `json_schema_required` remains false until an explicit structured-output contract exists.

The artifact predicts qualification for exactly one candidate/reference pair, not an arbitrary third model. Model identities must match; frozen config IDs must represent unchanged generation settings. Changing effort/output/settings requires new config IDs and evidence. Both choices pass the existing capability/context/budget filter, and paid dispatch still requires atomic ledger reservation. The ranking uses conservative upper cost estimates, not a guaranteed expected bill. Missing/invalid/mismatched artifacts fall back visibly to `rule_guarded`; absent quality evidence then selects a feasible reference or refuses. Timeouts retain unresolved accounting and are not automatically retried.

Research snapshots freeze artifact JSON/hash. Traces and CSV/JSONL expose internal score, selected threshold, model/artifact version and reason code. Old trace/run JSON remains readable with nullable/default fields. No DB migration/reset is needed. Simulation does not create live usage or quota charges.

## Offline dataset and CLI

From repo root with `.venv` activated, Windows PowerShell or POSIX:

```text
python -m app.cli router train --dataset data/router/dev.json --output config/router_model.json
python -m app.cli router evaluate --testset data/router/holdout.json --model config/router_model.json
```

Canonical schema: `app.routing.ml.dataset.LabeledDataset`.

- Metadata: `version`, `purpose` (`qualified_dev`, `qualified_holdout`, `software_test`), `provenance`, `grader_version`, `candidate_config_id`, `candidate_model_id`, `reference_config_id`, `reference_model_id`.
- `samples`: `task_id`, source/document/conversation `group_id`, `domain`, `split` (`train`, `calibration`, `holdout`), full role/content `messages`, `has_rag_context`, measured `small_qualified`/`reference_qualified`, `small_usd`/`reference_usd` (decimal strings), and `small_ms`/`reference_ms`.
- No gold/reference answers or hidden labels in serving messages. Domain/qualification labels remain evaluator metadata. Record exact public release/revision/license, qualification review, generation settings and source groups in provenance. `qualified_dev` is a reviewed operator assertion, not an automatic verification of a dataset.

Training rejects HOLDOUT, duplicate task IDs, source groups/duplicate text crossing splits, missing train/calibration partitions and one-class training. Vocabulary/classifier fit only on train. Threshold is selected on independent calibration by minimum observed USD subject to no per-domain pass-rate loss and p50 latency ratio <=1.10. Manual `--threshold` must pass the same guards. These conservative software defaults do not silently settle the spec's scientific quality margins. There is no arbitrary cost-plus-lambda objective.

Scores are explicitly **uncalibrated logistic scores**, not calibrated probabilities of correct answers. Separate probability calibration and statistically supported non-inferiority remain future work. Four train/four calibration samples are merely a validation floor, not adequate research evidence. Evaluate requires separate HOLDOUT and rejects model/grader/source/input overlap with DEV. Near duplicates still require data review. Replay cost/latency does not include measured online router/integration overhead; confirm accepted policies with a paired end-to-end pilot.

Synthetic unit tests use separate generated data, not the 20 research fixtures. CLI accepts synthetic data only with `--allow-test-data`; its artifact is marked `software_test` and cannot enable learned live selection. Output creation refuses to overwrite existing artifacts. JSON is used instead of the proposed joblib format to avoid executable deserialization. No qualified DEV/HOLDOUT or research weights are fabricated or bundled.

## Activation and rollback

`.env.example` adds `AUTO_ROUTING_STRATEGY=rule_guarded`, `ML_ROUTER_ARTIFACT_PATH=config/router_model.json`, `ML_ROUTER_LIVE_APPROVED=false`. Existing `.env` is not modified. Mock and `RESEARCH_LIVE_ENABLED=false` defaults remain.

Before changing to `AUTO_ROUTING_STRATEGY=ml_router` and explicitly approving live, review dataset qualifications, grouped splits, exact generation configs, access/prices, per-domain quality/uncertainty, routing overhead, paired E2E latency and actual remaining project/user/run budgets. Runtime requires qualified-DEV artifact purpose as well as operator approval. Synthetic artifacts never pass that gate. Revert the strategy and restart to return to the existing policy. Keep the best fixed model if routing has no demonstrated benefit.

## Verification and limits

From root: backend pytest/Ruff/mypy, frontend unit tests/typecheck/lint/build, `npm run contracts:check`, `npm run check:docs`, and `npm run test:ui`. Tests block network and cover deterministic loading/scoring, identities, high/low scores, constraints, fallback budgets, missing/corrupt artifacts, split leakage, CLI, simulation exports and zero live ledger rows. UI checks cover VI/EN, Auto labels, research, history, and 390px layout. Record actual results after running, separately from intended checks.

Performance is measured with local p50/p95 and sample counts; no sub-2ms inference/load guarantee is made. No paid pilot, real savings, answer-confidence percentage or statistical quality conclusion is delivered by this implementation. Khoa still owns benchmark qualification/graders; Tân's optimizers remain untouched.

Local verification on Windows / Python 3.11 / Node 24: 68 backend tests passed, including 12 ML unit tests and the simulation export/ledger integration. Frontend unit tests (3), typecheck, lint/format, generated-contract drift, documentation checks and production build passed. Six existing Chromium flows passed together; the new learned-policy flow passed in a targeted rerun after fixing its async list readiness. Desktop and 390px research screenshots were captured; no live API was used. The E2E launcher now waits for backend health before opening the frontend to avoid startup proxy failures.
