# Three-model routing, bounded tools and public UX — 2026-10-21

## Optimizer Lab UI readiness (2026-10-21)

`/research` now opens Performance experiments / Thử nghiệm hiệu năng. Advanced Router Lab is retained behind an explicit expander, with the same policies, owned history, preflight, decisions and exports. Normal users are blocked; admin-only `GET /v1/research/lab` supplies explicit readiness metadata, not evaluation results.

Model Router can be selected for a future paired comparison; prompt/context and memory switches are locked because their integrated algorithms are not available. The 50/200/600 sizes and run button are locked: current synthetic files are `software_test` and do not qualify the ablation runner. Metrics stay unknown and no fake bars/deltas are drawn. This release implements the UI and readiness contract, **not** an ablation executor or a qualified dataset loader. Actual activation needs reviewed data/graders, module adapters, a paired execution service, validated accounting and a separate integration change. It is not automatically enabled by changing a file's purpose field or wiring a single adapter.

Chat uses a small safe formatting subset: paragraphs, bold/italic, unordered/ordered lists and fenced/inline code. Raw HTML is escaped, code is preserved, user messages remain plain text and only the exact legacy mock footer can be hidden from assistant mock text. New mock responses omit the debug footer and identify themselves as illustrative. No inferred school fee deadline is presented as authoritative. Token totals require both input and output usage; missing counts remain unknown. Message typography is 15.5px/1.65, document panels remain in normal flow, and local Roboto/OU blue-white/reduced motion are retained.

Verification for this UI-only/readiness slice was deliberately targeted: **2 backend tests**, **5 small frontend tests** (including two new formatting/unknown-usage checks), and **one Chromium flow** passed. The UI flow covered locked modules/sizes/run, reference selection, retained advanced preflight, VI/EN, 390px overflow, formatted mock prose and the optimization log. Desktop/mobile screenshots were visually inspected. Ruff/format, mypy, ESLint, TypeScript, generated-contract drift, documentation validation and production build passed. The full backend suite and scientific benchmark were not rerun or claimed. Ownership algorithms, dependency locks, live gates, databases and accounts are unchanged by this slice.

## Implementation and boundaries

Huy owns this extension. FastAPI/Next.js/SQLite, owned history, auth, documents and ledger remain in place. No agent framework, Docker, arbitrary execution or network tool was added. Tân/Khoa algorithms and benchmark runner are unchanged. Work remains on the current feature branch; no automatic merge/push.

Chat exposes Automatic / Standard, not model thresholds. Standard uses the configured reference with the same allowed tools and selected sources. ContextManager assembles the user turn once. Mock uses deterministic trigger phrases (`Tính: (12.5+7.5)*2`, `Tra cứu tài liệu: ...`); it is a functional fake, not a language-understanding model.

`ml_multi_model` filters full messages, tool schemas and output reserve against capability/context, estimated upper cost, remaining quota and deadline. Two candidates are sorted by projected cost; data-only predictors accept/reject in that order, then fall back to the feasible reference. Artifact latency profiles also filter deadlines. This is prediction before dispatch, not three paid trial calls. Selection never implies guaranteed per-request quality. V1 `ml_router` and artifact loading remain supported.

The optional example `config/models.openai.example.json` names GPT-6 Luna / GPT-5.6 Luna / GPT-5.6 Terra and reference Terra. Access/pricing verification remain false. It is not the active catalog; review exact IDs, current prices, limits, endpoint and supported settings before use. No active `.env`, key, real artifact or access approval is supplied/changed.

## V2 research data and commands

Dataset `format_version=router-dataset-v2` has version, purpose, provenance, grader_version, exactly three `configurations`, `reference_config_id`, complete versioned `costs`, and `samples`. Each sample has task_id, source/document/conversation group_id, domain, split, full role/content messages, optional tool definitions/RAG/recovery metadata, constraints and three observations. Observations contain config_id, qualified, measured USD, latency_ms, input_tokens and output_tokens. Missing usage/cost is not zero: qualify or exclude such rows before training and disclose exclusions.

DEV splits are `train`, `calibration`, `threshold`; final `holdout` is separate. Sources and exact input hashes cannot cross partitions. Review near-duplicates manually. TF-IDF word/char + numeric logistic predictors fit train; sigmoid fits calibration; both thresholds are selected jointly on whole-policy replay in the threshold partition, including cases reaching stage two. Guards: no observed per-domain pass-rate drop, no observed critical regression, median latency ratio ≤1.10. Small software validation floors are not statistical power requirements or quality evidence.

The feature view is versioned `intent-recent-rag-numeric-v2`: current text up to 8,000 characters, two recent pairs up to 2,000 characters/message, selected evidence up to 8,000 characters, plus full-context numeric statistics/tools/recovery. These limits affect feature extraction only. Full provider input is not silently truncated. Gold/hidden domain labels are not serving features.

Artifact `router-json-v2` freezes both vectorizers/weights, sigmoid parameters, thresholds, complete generation settings and hashes, price/catalog identity, source/input groups, grader/provenance, latency profiles and threshold report. Loader reads JSON only; no pickle/joblib execution. Catalog/settings/artifact mismatch or missing/unqualified data falls back with reason codes. No research weights are learned from the functional fixture suite.

From **repo root**, with the venv activated (PowerShell or POSIX):

```text
python -m app.cli router train --dataset data/research/dev-v2.json --output config/router_model.json
python -m app.cli router evaluate --testset data/research/holdout-v2.json --model config/router_model.json
```

Outputs refuse overwrite. Synthetic `software_test` data requires `--allow-test-data` and never qualifies live routing. V2 refuses a manual `--threshold`: joint selection uses DEV threshold data. HOLDOUT is never used for tuning. Report offline replay separately from measured end-to-end routing latency/paid usage. A fixed model that performs better remains a valid result.

Lab supports V1 (20 cases, two fakes) and V2 (21 cases, three fakes). The extra tools case tests tool-capability routing metadata, not an agent benchmark. V2 fixture suite is blocked from live execution until a qualified tool-execution research adapter/protocol exists. Chat tool execution is implemented separately. Lab exports include stage decisions and policy summaries include reference fallback counts/rates. Actual mock tokens/USD stay null, estimates stay under simulation, and no live quota/history is fabricated.

## Tools, accounting and recovery

`calculate(expression)` accepts Decimal +, −, ×, ÷ and parentheses only; length 256, parenthesis/AST depth 16, node limit 128, finite bounded literals. No eval/shell/code execution. `search_selected_documents(query)` accepts only query text; sources are server-selected, owned and frozen by content/chunk revision. It reuses hybrid retrieval with at most eight budgeted source chunks. Query embedding is metered; indexing is not billed again.

One model per operation; maximum three generation calls, four sequential tool executions, two tool calls in one response. Every generation/embedding call reserves/settles independently under the same request budget/deadline. Native continuation preserves function calls, opaque reasoning items and outputs. Schemas are strict and server-validated. Calculator has timing but no inference tokens. Tools and continuation count toward the next input guard. Cached/reasoning usage is not counted twice.

Schema/unknown-tool errors are persisted server events and returned to the current model as structured errors. A successful current answer does not clear the newly raised recovery flag. The **next** user turn uses a feasible reference, and its clean successful completion clears the flag. The model never switches halfway through a tool loop. Exhaustion/incomplete/timeout does not commit a fake successful user/assistant pair. Already incurred accounting stays. Restart marks running work interrupted; no automatic paid replay.

Migration `d103_tools` adds session recovery state and deduplicated tool invocations without resetting accounts/history. Same operation + call ID + same raw payload reuses an event; a different payload conflicts. Tool events live in owned trace/activity, not extra user turns, and are purged with session content.

## Public and private UX

Logged-out `/` shows OU landing, keyboard-accessible login and model configuration states. Signed-in users go directly to workspace; deep links stay intact. `/research-guide` explains method/limits in VI/EN. Public `/v1/platform-info` allowlists names, execution mode and configuration state; no keys, quota, filesystem paths, user data or fresh provider probe. It does not imply verified access.

Chat shows actual model and a short explanation; tool activity has readable names and expandable results. Technical stage scores/thresholds/hashes remain in Lab/trace. No invented savings, answer-confidence badge or charts are published. History persistence remains distinct from unimplemented memory optimization.

## Hybrid correction — research candidate (2026-10-21)

Linear remains the default V2 trainer. Hybrid is explicitly selected with `--hybrid`; `--no-hybrid` retains the linear baseline. The CLI command is `router train`, not `multi-train`. Hybrid has no proven savings, quality, sub-7ms latency, throughput, memory footprint or SOTA result. Functional fixtures are not SEA-IFEval/ViQuAD/VMLU/Vi-Dialog research evidence. In the optional example catalog Terra is reference; candidate order is calculated from reviewed catalog costs, never inferred from model names.

Hybrid training uses deterministic grouped out-of-fold text scores for the GBDT training features. Every fold fits its own vocabulary, IDF and text classifier on other source groups only. Too few independent groups/classes produces a clear error, never an in-sample substitute. The serving text encoder is refit on all train rows after fitting the booster. Calibration and joint threshold selection still use their separate DEV partitions; final HOLDOUT is untouched until evaluation.

Hybrid artifacts retain JSON format V2 but use feature version `intent-recent-rag-hybrid-oof-v3`, full tree precision, float32 input comparisons matching sklearn, exact ordered feature names, grouped OOF provenance and bounded/validated trees. Old experimental hybrid artifacts without this protocol are rejected and must be retrained. V1 and original V2 linear artifacts remain readable. Runtime predictor faults use feasibility-checked policy fallback; no uncalibrated substitute score is invented.

Lab reports separate global training importances for each candidate from the run's frozen artifact, not the current server artifact. These impurity-based values are neither per-question explanations nor answer-confidence probabilities. The old flat importance field stays empty for compatibility. The VI/EN UI labels the text score as candidate qualification from text, not semantic complexity.

From repo root with venv activated, no paid calls:

```text
python -m app.cli router train --dataset data/research/dev-v2.json --output data/research/linear.json --no-hybrid
python -m app.cli router train --dataset data/research/dev-v2.json --output data/research/hybrid.json --hybrid
python -m app.cli router evaluate --testset data/research/holdout-v2.json --model data/research/hybrid.json --compare-model data/research/linear.json
```

Comparison requires the same DEV identity and independent HOLDOUT for both artifacts; it reports observed paired cost/pass-rate/latency-ratio deltas and fixed configurations. These are offline replay metrics, not measured serving overhead. Synthetic data additionally requires `--allow-test-data` and stays marked software-only. Output files refuse overwrite; live gates remain off. No dependency lock, database, account, real model access or qualified artifact is changed by this correction.

## Live gates and verification

Mock is default. `TOOLS_LIVE_APPROVED=false`, `ML_ROUTER_LIVE_APPROVED=false`, `RESEARCH_LIVE_ENABLED=false`. Activating one is insufficient to activate the others. Live needs reviewed catalog/access/prices, server key, qualified data/artifact for learned selection, budget/call matrix review, then explicit operator approval. The project USD20 envelope remains; CI/test paths force mock and disable gates. No paid calls were made for this delivery.

Verification evidence is recorded below after local checks. It proves implementation behavior using fakes and SDK MockTransport, not model quality, real access, prices on an invoice or live savings. Linux/remote CI and paid pilot remain unverified locally.

Earlier foundation checks on Windows, Python 3.11 / Node 24 (before the hybrid correction):

- Final complete backend suite: **95 passed** (124.66s). Coverage includes V1/V2 route stages, constraints/catalog identity, split isolation/CLI replay, provider native strict schemas and opaque reasoning continuation, tool errors/limits/dedupe/restart, selected-source ownership/accounting and migration/history regression. All provider execution used deterministic fakes or SDK MockTransport; no paid pilot.

- Ruff, formatting, mypy (66 application files), ESLint, TypeScript and generated OpenAPI/TypeScript drift checks passed. Frontend Vitest: three tests passed. Next.js production build passed, including `/research-guide`.
- Chromium: nine flows passed together (landing/login/guide, locale, ownership, history, auth expiry, documents, analytics/admin and calculator tools); the added three-model suite flow passed in a targeted rerun after the selector received its explicit accessible label. Layout screenshots at 390/768/1440px were captured; desktop and mobile landing were visually inspected with no horizontal overflow. Earlier assertion failures were corrected and are not counted as passes.
- Development DB was backed up locally, then upgraded to `d103`; counts stayed three users, one session and two messages. Backup remains in ignored `data/backups/`; no password/account reset.

Hybrid correction verification (2026-10-21, same local environment):

- Complete backend suite: **112 passed** (187.23s), including 37 unit checks. New regressions exercise exact compiler parity at float32 boundaries (absolute tolerance 1e-12), malformed artifacts, runtime fallback, grouped OOF fitting, insufficient groups, both CLI architectures and paired HOLDOUT replay. API integration verifies both frozen-run predictor importances after replacing the active artifact, plus access control.
- Frontend Vitest: **3 passed**. Complete Chromium suite: **10 passed together** (1.8m), including separate predictor charts, VI/EN labels and 390px overflow check. The chart renderer uses explicit UI fixtures; the API integration independently checks real frozen-snapshot behavior with software-only artifacts. No research importance weights or model quality were inferred from UI fixtures.
- An initial browser attempt timed out during localhost startup. Subsequent runs exposed a shared-IP login rate-limit and a transient duplicate activity selector; test helpers now honor throttling and select persisted assistant activity explicitly. Application auth throttling remains intact. Failures are not reported as successful checks.
- Ruff lint/format, mypy, generated contracts, frontend lint/typecheck/format and documentation checks passed. **Next.js production build passed**, including TypeScript and all five application routes. No paid calls, real artifact activation, database migration or account changes were performed for this correction. Remote Linux/Windows CI still requires a separate push/run.
