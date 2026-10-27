# Docker test: global thresholds requested by Huy

Deployed 27 October 2026, Asia/Saigon. URL: http://localhost:3000. Backend: http://localhost:8000/v1/health/ready.

User explicitly superseded the earlier math-only suggestion: global OSS20B threshold **0.690085**, Luna **0.71**. The existing router still filters capabilities/context/deadline/quota/budget, then chooses the cheapest eligible candidate that meets its threshold. A higher Luna threshold does not force a fixed share of Luna traffic; it is selected when cheaper candidates fail or are infeasible. OSS120B remains the reference. This is an operator-accepted development trial, not new scientific quality qualification.

- Artifact: `config/router_attention_operator_thresholds_0690085_071.json`.
- Semantic hash: `0a9ca485fce8159ea3fbad539b25e11c26202f8d95d618267c08c96b71eebeef`.
- Receipt: `config/router_operator_thresholds_acceptance.json`, explicitly formal_qualification_passed=false.
- Evidence: `config/router_operator_thresholds_evidence.json`, passed=false; prior results are not relabeled as validation for the new global settings.
- Previous artifact/receipt/evidence remain intact. No weights were retrained. No qualified task-group bundle overrides these thresholds.
- `.env` selects the new artifact/receipt, research-candidate allowed in development, live-qualified flag false. API keys, budgets, quota and unknown reservations were not changed.

Images were built from current source and deployed via Docker Compose:

- `smartllmplatform-backend:operator-thresholds-0690085-071`, also `latest`; image manifest `2b3c70b0439e8a105630cf1f8b0d37283c30a6c34b224b1828ebc52887f31925`.
- `smartllmplatform-frontend:operator-thresholds-0690085-071`, also `latest`; image manifest `e294d71d68f2aeec610d3f1197c4aea44b9dea81bc1803186eb590a001813c63`.

Checks: 37 backend routing/chat/failover tests passed with mocked providers, including equality and just-below boundaries selecting each of small/Luna/reference; frontend production build and TypeScript passed. Backend Docker healthy; HTTP homepage, backend readiness, proxied readiness and three-model metadata returned 200. Browser rendered the actual Smart LLM OU homepage. Runtime frontend proxy timeout is 130000 ms. Container environment, mounted artifact and acceptance hash match the requested thresholds. This verification made no new provider requests; the operator will test new chat requests manually.

Storage backup: `data/backups/pre-global-thresholds-0690085-071-20261027.sqlite3`, integrity=ok, revision h108, SHA256 `72ca39d027e49282b8d90aadf8ae6be2fe87bf0e9087858a40151f710e3e1f51`. Post-deployment comparison preserved all original columns in users, budget_reservations, usage_records, inference_calls, messages, sessions, request_attempts and the analytics epoch. The old unknown call `ee5c9467-6f10-44dc-b08b-dde858e32942` remains unresolved at USD0.00173715. No research collection worker or monitor was restarted.

Machine-readable evidence:

- `output/project-audit/operator-thresholds-routing-tests-20261027.xml`
- `output/project-audit/operator-thresholds-0690085-071-20261027.json`
- `data/operator-thresholds-0690085-071/storage-verification.json`
- `data/operator-thresholds-0690085-071/runtime-verification.json`

Rollback settings and exact old image tags: `config/router_thresholds_rollback_20261027.json`. Restore only those listed nonsecret environment keys, retag the saved old images to latest and recreate services without deleting volumes. The database backup is for recovery; a normal threshold rollback does not need to restore or erase the database.

For browser testing: log in with the existing account, start a fresh conversation, select automatic routing, and open Trace to inspect selected model, per-model score/threshold and the real call sequence. Historical answers/traces retain their original models and policies.
