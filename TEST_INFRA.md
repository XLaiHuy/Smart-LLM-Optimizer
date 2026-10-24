# Smart LLM Optimizer — E2E Test Infrastructure Specification

## 1. Test Philosophy & Principles

The Smart LLM Optimizer platform undergoes testing under a **requirement-driven, opaque-box end-to-end (E2E)** methodology. Every test case in this suite originates directly from the authoritative specifications defined in `ORIGINAL_REQUEST.md` and architectural interface contracts in `PROJECT.md`.

### Core Axioms
1. **Zero Financial Exposure & Safe Isolation**:
   - Live external endpoints (`Groq`, `Hugging Face`, `OpenRouter`, `OpenAI`) are accessed exclusively via deterministic simulated transports or local mock servers during test execution.
   - `RESEARCH_LIVE_ENABLED` remains strictly `False` during all test suite invocations. Tests must NEVER incur monetary costs or deplete live API quotas.
2. **Opaque-Box Verification**:
   - Tests interact with the system via defined public interfaces: REST endpoints, Server-Sent Events (SSE) streaming protocols, CLI entrypoints, schema validation contracts, and documented module APIs.
   - Assertions verify external contracts, observable states, mathematical invariants (e.g. Pareto non-domination, Pass Rate $\ge 97\%$, cost savings $> 6.1\%$), and error codes without relying on private implementation details.
3. **No Facade / Anti-Slop Integrity**:
   - Tests assert real behavioral outcomes, side effects (database records, ledger ledger entries, session history), and performance guarantees. Dummy assertions (`assert True`) or tests written solely to mirror flawed implementations are strictly forbidden.
4. **Self-Contained & Deterministic**:
   - Each test fixture sets up its own isolated database (e.g. temporary SQLite instance in WAL mode) and cleans up on completion. No test depends on the execution order or shared state of another test.

---

## 2. 4-Tier Test Architecture

The E2E test suite is structured into four distinct hierarchical tiers:

```
backend/tests/e2e/
├── conftest.py                   # Shared fixtures (isolated DB, async HTTP client, mock providers)
├── test_e2e_tier1_features.py    # Tier 1: Isolated Happy-Path Feature Coverage (>=5 tests per feature)
├── test_e2e_tier2_boundaries.py  # Tier 2: Boundary, Edge & Corner Cases (>=5 tests per feature)
├── test_e2e_tier3_interactions.py# Tier 3: Pairwise & Cross-Feature Interaction Matrix
└── test_e2e_tier4_scenarios.py   # Tier 4: Realistic End-to-End Application & Benchmark Scenarios
```

### Tier 1: Feature Coverage (Isolated Happy Path)
Verifies each feature independently with at least 5 test cases per feature:
- **Feature 1: Free Tier Providers Catalog & Client**:
  - Groq Llama 3.3 70B Versatile configuration validation
  - Groq Qwen 2.5 Coder 32B high-throughput configuration
  - Hugging Face Serverless endpoint mapping and base_url routing
  - OpenRouter `:free` model discovery and pricing zero-rating
  - OpenAI-compatible adapter dispatch to standard chat completions
- **Feature 2: Automatic 429 Fallback Cascade**:
  - Detection of HTTP 429 / rate limits from primary provider
  - Cascade to secondary eligible provider without user turn abort
  - Ledger refund of unspent reservations and re-reservation for target model
  - Trace recording of fallback events and attempt audits
  - Successful multi-turn fallback continuity
- **Feature 3: Real-Time SSE Token Streaming**:
  - Server-Sent Events content type header (`text/event-stream`)
  - Incremental `event: token` token-by-token streaming
  - Metadata `event: trace` emission containing routing and attention vectors
  - Completion `event: done` with accurate token usage accounting
  - Stream completion preserving session history in SQLite
- **Feature 4: SQLite WAL High Concurrency & Lock**:
  - Verification of `PRAGMA journal_mode=WAL` and `busy_timeout=10000`
  - In-process `_write_lock` serialization preventing database lock collisions
  - Concurrent read-while-write transactional integrity
  - Rapid multi-turn sequential write transactions
  - ACID rollback on unexpected transaction aborts
- **Feature 5: Dynamic Pareto Routing**:
  - Non-dominated candidate model selection across cost, latency, quality
  - Trade-off slider sweep ($w \in [0, 1]$) smoothly altering decision thresholds
  - Minimum quality threshold guarantee ($\text{Pass Rate} \ge 97\%$)
  - Minimum cost savings threshold ($> 6.1\%$)
  - NumPy vectorized attention CPU inference latency $< 0.5\text{ ms}$
- **Feature 6: 3D Visualization Component Contracts**:
  - `NeuralRoutingCosmos3D` prop validation (6 attention dimensions + routed candidate)
  - Cubic Bezier trajectory calculation for energy particle beam
  - `ParetoScatterSurface3D` prop validation and coordinate normalization (Cost × Latency × Pass Rate)
  - Raycaster hover tooltip data structure contract
  - WebGL lifecycle contract (`forceContextLoss()`, geometry/material disposal on unmount)
- **Feature 7: Quick Benchmark Mode & Router Lab**:
  - Retrieval of 3 top KPI summary metrics (Cost Savings %, Pass Rate %, Latency P50/P90)
  - 1-Click quick benchmark trigger and status polling
  - Interactive slider updates reflecting immediate candidate prediction
  - Collapsible Advanced Analytics payload integrity (candidate matrix, feature importances)
  - Export data serialization (JSONL/CSV format compliance)
- **Feature 8: Multi-Task Vietnamese Dataset Loading**:
  - VMLU dataset loading with 1,047 verified gold answer keys
  - UIT-ViQuAD 2.0 reading comprehension and answer span extraction
  - Authentic Vietnamese Legal-QA administrative legal provisions
  - PhoQA multi-domain Wikipedia QA loading
  - Strict 4-way anti-leakage splitting (Train/Calibration/Threshold/Holdout with 0 overlap)

### Tier 2: Boundary & Corner Cases
Stress tests limits and edge conditions with at least 5 test cases per feature:
- **Rate Limits & 429 Status**: Complete cascade exhaustion handling, exponential backoff headers, rapid burst quota limits, 429 recovery after cooldown, zero-turn partial refund.
- **Authentication & Tokens**: Missing cookie/header, malformed session tokens, expired sessions, cross-tenant resource tampering, invalid login credentials.
- **Extreme Slider Values**: Slider at exactly 0.0 (maximum quality), slider at exactly 1.0 (maximum cost savings), negative slider out of bounds, slider $>1.0$, NaN/null slider defaults.
- **Oversized & Malformed Prompts**: Empty string prompt, whitespace-only prompt, prompt exceeding model context window, single token prompt, ultra-long Vietnamese text with complex diacritics.
- **Streaming Disconnects**: Mid-stream client disconnect detection (`request.is_disconnected()`), generator cleanup, partial token consumption settlement, shielded commit preventing orphaned reservations.
- **Dataset Anomalies**: Missing gold answer keys in VMLU, malformed JSONL rows, unanswerable questions (`is_impossible`), empty contexts, corrupted span offsets.

### Tier 3: Cross-Feature Interactions
Evaluates pairwise and systemic cross-cutting capabilities:
1. **Streaming + Fallback**: Mid-stream 429 exception triggers transparent provider switch without tearing down the SSE connection.
2. **Concurrency + Ledger Shield**: Concurrent burst requests while clients abort mid-flight; `asyncio.shield` ensures ledger never leaves dangling pending reservations.
3. **Pareto Thresholding + Vietnamese QA**: Routing authentic Vietnamese prompts across tasks (VMLU vs ViQuAD vs Legal-QA) under different trade-off weights, verifying domain-adaptive routing.
4. **3D Candidate Tooltips + Benchmark Metrics**: Verification that metrics emitted from benchmark runs directly align with the 3D Pareto coordinate space and tooltip schemas.
5. **Free Provider Catalog + Pareto Routing**: Inclusion of 0-cost free tier models in Pareto optimization, ensuring mathematical stability (no division by zero) and dominance filtering.

### Tier 4: Real-World Application Scenarios
Simulates realistic production workflows:
1. **Multi-Turn Vietnamese Student Advising**: End-to-end session creation, multi-turn conversation in Vietnamese, context retention, streaming responses, and ledger billing.
2. **1-Click Quick Benchmark Evaluation Workflow**: Executing quick benchmark on Vietnamese datasets, generating 3 KPI cards, rendering Pareto frontier, and exporting analytics.
3. **Provider Outage & Resilience Workflow**: Graceful degradation during primary provider outage, automatic fallback to free tier, trace logging, and ledger reconciliation.
4. **High-Concurrency Multi-User Burst**: 20+ concurrent user sessions performing chats, streaming, and session mutations simultaneously on SQLite WAL.
5. **Multi-Task Legal & Educational Evaluation Pipeline**: Running full evaluation over VMLU gold + Legal-QA with deterministic graders, scoring Exact Match and Token F1.

---

## 3. Test Runner Invocation

To execute the complete E2E test suite:

```bash
# Full E2E suite
.venv\Scripts\python -m pytest backend/tests/e2e -q

# Run by tier
.venv\Scripts\python -m pytest backend/tests/e2e/test_e2e_tier1_features.py -q
.venv\Scripts\python -m pytest backend/tests/e2e/test_e2e_tier2_boundaries.py -q
.venv\Scripts\python -m pytest backend/tests/e2e/test_e2e_tier3_interactions.py -q
.venv\Scripts\python -m pytest backend/tests/e2e/test_e2e_tier4_scenarios.py -q

# Parallel execution with verbose output
.venv\Scripts\python -m pytest backend/tests/e2e -v
```

---

## 4. Coverage Thresholds & Quality Gates

| Metric | Target Threshold | Validation Command |
|---|---|---|
| E2E Test Pass Rate | **100%** (0 failures, 0 errors) | `pytest backend/tests/e2e -q` |
| Tan Optimizers Suite | **100%** (27/27 pass) | `pytest backend/app/optimizers -q` |
| Khoa Evaluation Suite | **100%** (158/158 pass) | `pytest backend/tests/evaluation -q` |
| API Contracts Schema Check | **0 breaking changes** | `npm run contracts:check` |
| Python Linting | **0 errors** | `ruff check backend` |
| CPU Attention Latency | **< 0.5 ms** | Vectorized NumPy cross-attention benchmark |
| Pareto Quality Guarantee | **Pass Rate $\ge 97\%$** | Holdout split evaluation across all $w \in [0, 1]$ |
| Pareto Cost Savings | **$> 6.1\%$** | Compared to single baseline model |
