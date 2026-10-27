# UX and usage reporting update

**Cập nhật 22/10/2026:** giao diện Lab nâng cao/journey ở bản trước đã được thay bởi [Lab thống nhất và popup tiến trình](COMPACT_EXPERIENCE_HANDOFF.md). Backend policies, evidence gates và các kết quả kiểm tra lịch sử bên dưới vẫn là ghi nhận của thời điểm đó.

## Delivered behavior

- Public landing keeps the hero/login available immediately. Lower sections mount within 180 px of the viewport, reserve space and reveal once. Reduced motion removes the animation. The authenticated shell, dashboard, trace inspector and advanced Lab are separate chunks; immutable chat traces load near the viewport instead of all at history load.
- OU light surfaces, local Roboto, VI/EN, consistent controls, budget feedback, responsive charts with data tables and keyboard focus. Chat exposes a collapsed journey using persisted route/module/call events, never invented live progress. The existing technical trace remains available separately.
- Personal usage shows actual recorded input/output tokens, calculated USD, operations, models and conversations. Source filters keep mock/live apart. Unknown values remain unknown, with a known cost subtotal where available. No personal Standard/Optimized savings claim.
- Today has 24 hourly buckets; 7/30-day presets use daily buckets; 12 calendar months use monthly buckets. Custom ranges use auto grouping (one day: hourly; up to 62 days: daily; otherwise monthly). All boundaries use Asia/Ho_Chi_Minh; custom maximum remains 366 days. Explicit hourly requests are limited to seven days.
- Budget bars and warnings use lifetime settled spend plus outstanding reservations, independently of report date/source filters. Warnings appear at 80% and 100%; no email or paid call is triggered.
- Admin project/account reports contain accounting statistics only. No foreign messages, titles, filenames or document excerpts are returned. Per-user exports use the same admin check. Personal recent requests are hidden when viewing project/another account.

## Persistence and compatibility

Migration `e104` adds nullable `request_attempts.e2e_ms`. It copies existing measured timings from valid traces, without inventing values for purged historical traces. New successful operations save their measured server duration atomically with the response/history. Deleting content retains this scalar measurement alongside accounting. It measures server work through history flush, not browser round-trip/TTFT or the final transaction commit.

Recent overview queries use lightweight metadata rather than loading every historical response. Old records without measurements say “Chưa có số đo” / “Not measured”. The development database was backed up before migration; accounts/history are preserved. Empty pre-existing content is not recreated.

`GET /v1/usage` and `/v1/usage/export` accept `granularity=auto|hour|day|month`, optional `model_id`/`session_id`, plus existing dates/source/project flags. Responses add `granularity` and `timeseries`; `daily` remains for compatibility. CSV uses `timeseries_{granularity}` as its time dimension. Different dimensions are alternative views of the same calls and must not be summed together.

`GET /v1/admin/users/{user_id}/usage` adds selected-account aggregates. `/v1/usage/export?user_id=...` is admin-only. `GET /v1/admin/benchmark-impact` is admin-only, takes start/end and optional user_id, and always uses live accounting records.

## Benchmark evidence and projections

The former ablation endpoint contained fixed savings/latency/quality figures. They are removed. `POST /v1/research/ablation` now returns 409 `BENCHMARK_NOT_READY`; `/v1/research/lab` keeps comparison/data sizes locked until a real paired runner is integrated. Downloaded samples or a file named `real_benchmark_600.json` do not unlock it. Functional Router Lab is retained under Advanced.

Projections are a separate read-only admin feature, disabled by `BENCHMARK_IMPACT_APPROVED=false`. No report is installed or approved by this delivery. It neither runs a benchmark nor calls a provider. Review actual evidence before setting the gate or selecting a report path.

An operator-reviewed report at `BENCHMARK_IMPACT_PATH` must match `ReviewedBenchmark` in `backend/app/analytics/impact.py`. Required metadata: version `benchmark-impact-v1`, live source, paired and independent HOLDOUT, all-in costs, passed quality guardrails, reviewer, timezone-aware review/expiry timestamps, evidence SHA-256, grader/policy versions, limitations and non-overlapping groups. Each group specifies category, reference model ID, price-catalog version, benchmark population, paired sample count and observed baseline/optimized total USD. No sample count alone establishes statistical significance. Reviewer approval asserts that source evidence, independence, quality/latency guardrails and all optimizer/indexing/judge cost allocation were checked; JSON declarations cannot prove scientific validity automatically.

Projection method: for matching reference-model spend only, estimated USD difference equals eligible baseline spend multiplied by one minus the benchmark optimized/baseline cost ratio. Categories, model IDs and price versions must match exactly. Unknown and reconciled costs are excluded from extrapolation; unknown counts remain visible. It reports matched calls, eligible baseline spend, coverage of known monetary spend, measured benchmark totals, population and limitations. Coverage is monetary eligibility, not proof that production tasks match the benchmark distribution. A negative difference means extra estimated cost. No projection changes usage, invoices, quotas or native traces.

Admin copy must continue to say “ước tính từ benchmark”; no real-world savings claim, per-answer quality probability or green savings badge is inferred. Both project and account scopes are supported; ordinary users cannot request the endpoint.

## Verification

Focused checks use temporary databases, mock providers and explicitly synthetic UI/evidence fixtures. No paid calls or research qualification is implied. Evidence is recorded here after the checks complete. The UI test build uses `.next-e2e` to avoid sharing the dev server cache; its API/database/accounts use isolated test instances.

Local verification, Windows / Python 3.11 / Node 24, 2026-10-21:

- Focused backend: `pytest backend/tests/integration/test_usage_experience.py backend/tests/integration/test_optimizer_lab.py -q` — **4 passed**. Covers local midnight/year boundaries, source/model filters, unknown metrics, account isolation/admin export authorization, reviewed-report gating and matching prices, removal of fixed ablation results, and request duration retained after content deletion.
- Frontend unit suite — **5 passed**, including VI/EN key parity and unknown-vs-zero display. No extra component/getter test suite was added.
- Chromium — **one selected UI flow passed**. It withholds the initial auth response to verify that the public hero is already visible, checks scroll mounting, login, persisted journey, unknown mock metrics, hourly/monthly grouping, a budget-only UI fixture, admin account aggregates, unavailable benchmark state, EN/VI, 390 px overflow and regular-user access. An earlier attempt timed out because the test navigated before locale refresh finished; the flow now awaits the translated content and the language control exposes a pending state. This failure is not counted as a pass.
- Screenshots of landing, chat journey, personal desktop usage and admin mobile usage were inspected. Saved under the selected flow in ignored `output/playwright/results/`; they show mock/empty metrics, not claimed live savings.
- Ruff lint and formatting passed; mypy passed for 68 app files. ESLint, Prettier, frontend typecheck and OpenAPI/generated TypeScript drift check passed. Final Next.js production build passed for `/`, `/dashboard`, `/research`, `/research-guide` and the not-found route. Documentation checks passed.
- Development database backup: ignored `data/backups/before-e104-20261021-232722.db`. Migration reached `e104`; counts stayed 3 users, 0 existing messages and 6 retained request attempts. No account, quota, key or live gate was reset. Historical purged response times remain unavailable.

The full backend/E2E suites were not rerun in this slice. Linux/remote CI, live performance, real benchmark qualification and real-world savings remain unverified. The implementation makes no numerical performance improvement claim from code splitting alone.
