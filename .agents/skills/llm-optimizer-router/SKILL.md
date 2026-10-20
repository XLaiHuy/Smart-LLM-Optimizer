---
name: llm-optimizer-router
description: Algorithms and architectural patterns for Dynamic Multi-LLM Model Routing, Task Classification, Cost-Latency Pareto Optimization, and FrugalGPT Cascades. Use when developing model router logic, task analyzers, fallback controllers, or budget allocation policies.
---

# Routing policies and controller

Huy owns analyzer/router/provider/registry/ledger/wiring/frontend. Tân owns prompt/context, Khoa memory/evaluation. Use spec §04/§08 interfaces and §06 evidence gates; do not redefine DTOs/providers/signatures here.

## G0 fixed mock route

Analyzer returns unknown with reason. Fixed router selects configured mock_config_id from allowlisted registry, records foundation_fixed_mock and makes no network call. Flags exercise disabled/not_implemented states, not a classifier or learned policy. No hardcoded cheapest real model, fabricated price/quality/savings. Live adapter/classifier/routing algorithms belong after G0.

## Policy after G0

1. Extract only observable serving features/capabilities/constraints; support unknown language/difficulty. Keywords/character ratios are heuristics, not verified difficulty/exact usage. Hidden benchmark labels/gold are excluded.
2. Filter registry entries by endpoint/capabilities/context/output reserve/effort and remaining budget/deadline. Token estimates retain model/tokenizer/version/source/status. Missing usage/pricing is unknown, not zero; conservative bounds require explicit configured provenance.
3. Qualify using versioned DEV quality/latency profiles per task group, then minimize projected all-in cost with latency guard/tie-break. Include analyzer/rewrite/summary/router inference overhead; USD and ms remain separate.
4. Insufficient quality evidence → configured reference baseline with original prompt/full raw history if feasible under remaining limits; otherwise mapped error. Never silently choose an unverified cheap candidate. Baseline quality is measured, not guaranteed per request.
5. Persist reasons/exclusions/policy hash/per-call accounting through ports. BudgetLedger handles request/user/project reserve/settle independently of CostCatalog. Unknown dispatch retains unresolved billing; no automatic paid retry in P0. Post-generation cascade/cache/streaming are P1.

Verify actual IDs/access/usage/pricing at G2; names do not imply universal quality/capacity/price ranking. Benchmark against fixed reference, cheapest feasible and best feasible fixed chosen on DEV; report coverage/per-group regressions/negative overhead, not no-op savings.

## Guardrails versus Pareto

An eligible policy meets frozen per-group quality and observed median latency ratio ≤1.10, with uncertainty/limits reported. Eligibility is not Pareto non-dominance: A dominates B if quality is at least as high, cost and latency no higher, and at least one metric strictly better. Compare measured configurations pairwise. A feasible point can be dominated; a non-dominated point can fail a guardrail. No weighted USD+ms scalar or noisy point estimate proves certainty. Use PASS_OBSERVED/INSUFFICIENT_EVIDENCE/FAIL; do not claim proven 3 pp non-inferiority without the required paired uncertainty analysis.
