# Router Lab — Huy handoff

## Trạng thái và cách chạy

Nhánh triển khai: `feature/huy-router-lab`, xuất phát từ develop. API/auth/history/documents giữ nguyên; migration additive `c102` thêm research runs/trials, reconciliation audit, nullable accounting session và run-budget linkage. Không reset DB hoặc tự tạo tài khoản mặc định.

Từ repo root, activate venv, chạy `npm run db:migrate`, rồi `npm run dev`. Đăng nhập bằng admin hiện có và mở `/research`. Main/develop chỉ nhận thay đổi sau review/checks; commit foundation đã push không tự là acceptance cho thay đổi này.

Chọn cả fixture-reference và fixture-small, tất cả policies, seed 42, repeats 1, budget giả lập 1 USD. Preflight có 120 trials / tối đa 120 calls. Đây là upper limit; từ chối trước provider có thể không tạo call. `succeeded` nghĩa worker đã hoàn tất ma trận, không phải mọi fixture đều pass hoặc quality guardrail đạt. Bảng riêng ghi errors và functional matches, bao gồm fault có chủ đích.

UI có VI/EN, mobile, preflight, run history, progress, cancel, policy table, route distribution, per-trial trace và exports. User thường bị chặn ở UI và mọi API research. Admin chỉ xem runs do chính mình tạo; global active-run limit không mở quyền đọc research của admin khác.

## Cấu hình và contracts

Registry validation offline chặn empty/duplicate IDs, sai baseline/embedding kind, output reserve vượt context và endpoint không phù hợp. `python -m app.cli validate-catalog` không mạng; `verify-catalog` chỉ kiểm tra metadata và không tự chứng nhận giá/quyền generation. GET models có availability reason/capabilities. Provider từ chối config/model mismatch và parameters chưa được review trước khi dispatch.

Router gồm fixed_reference, fixed_candidate, cheapest_feasible, seeded random_feasible và rule_guarded. Random là uniform trên feasible candidates, chưa là đối chứng matched-frequency trên workload nghiên cứu. Chi phí upper-bound không phải expected cost đã hiệu chỉnh. Analyzer dùng JSON keywords/code fences, tiếng Việt heuristic và độ dài UTF-8; không ước đoán difficulty từ benchmark label. Task dài dùng ngưỡng 4096 bytes cho tag, không phải context/token guard.

Rule router lọc capability/context/budget, rồi dùng per-group evidence và latency. Trong chat live, fixture evidence bị loại; thiếu evidence thì chọn reference với original input nếu feasible. Production chưa import quality profiles nên không tuyên bố tối ưu được model selection. Router chạy bằng input chưa biến đổi; rewrite/context/memory vẫn no-op. Controller tích hợp transforms thật và learned router/cascade thuộc gate sau.

`CostSnapshot`, `RemainingBudget`, `TaskProfile` và `RouteDecision` có giá/version, ngân sách thật, thời gian còn lại, rules/exclusions/estimates/policy hash/evidence version. Rejection trials vẫn lưu diagnostics. Contracts là nguồn chuẩn, OpenAPI/TS sinh lại; không duy trì interface client viết tay.

## Execution, isolation và dữ liệu

Fixtures nằm ở `config/router-fixtures.json`, version huy-router-fixtures-v1: 20 cases với instruction/JSON, QA/reasoning dạng kiểm tra chức năng, Unicode, history, injection text, context dài và lỗi. Fake provider chỉ nhận messages/options; checker mới nhận expected/error reference. Exact và JSON-object checks có version; không dùng substring phủ định làm preservation proof.

Run đóng băng manifest, registry, cost/evidence profiles, code SHA (có suffix dirty khi chưa commit), hashes và request/seed. Mọi policy dùng cùng messages snapshot; expected không đi vào analyzer/router/provider. Source fixture tự tạo không đủ để kết luận chất lượng tiếng Việt hay Pareto/non-inferiority. Sample exports chỉ minh họa protocol, thời gian local thay đổi theo máy.

Một research worker, concurrency 1 và tối đa một pending/running run/project (DB unique constraint + transaction). Submit trùng ID/payload trả run cũ, payload khác trả conflict. Cancel có hiệu lực trước call tiếp theo. Running sau restart thành interrupted, kết quả đã commit giữ nguyên; không paid replay. Pending chưa chạy có thể được worker nhận sau boot. Một trial commit một lần; không tạo Conversation hoặc UsageRecord/Reservation thật cho simulation.

Actual mock tokens/USD null. `simulation.estimated_upper_usd` dùng bảng giá hư cấu và byte bound, không cộng vào live analytics/quota. Local timing là thời gian routing + fake execution, dừng trước persistence của trial; không phải scientific model latency.

JSONL `router-lab-v1` bắt đầu bằng record_type=run (metadata/status/checker version/accounting), tiếp theo là trial records với nested calls. CSV có row_kind=run/trial/uncommitted_call cùng IDs/hashes, policy, chosen model, error, functional outcome, timing, bounds và usage. Không cộng run totals một lần nữa vào các trial rows. Kể cả run chưa có trial, export vẫn có metadata. Sample artifacts thật từ DB tạm: [JSONL](examples/router-fixture-example.jsonl), [CSV](examples/router-fixture-example.csv); 20 trials fixed_reference, không paid calls.

Run accounting truy vấn mọi UsageRecord theo research_run_id, kể cả process dừng sau settlement nhưng trước trial commit. UI/JSONL/CSV giữ các call chưa có trial và subtotal/unknown status; không âm thầm bỏ chi phí khỏi kết quả interrupted. Trial traces giữ cost gốc, accounting view phản ánh audited corrections. Partial exports luôn giữ trạng thái run, không giả hoàn chỉnh.

## Ledger và reconcile

MeteringContext không phụ thuộc ChatRequest: operation/principal, optional session, category và request budget. Các operation live tương lai dùng session-free Attempt và research_run_id; reserve kiểm tra aggregate run/user/project dưới write transaction. Production dispatch vẫn reserve lại, không tin remaining snapshot làm khóa quota.

Usage completion và settlement cùng transaction. Call chưa đo duration là null và bị loại khỏi percentile, API/export có timing_samples. Timeout/cancel uncertain giữ unresolved; không auto-release như free. Research simulation không dùng ledger thật; test metered fakes kiểm tra financial invariants trên DB tạm.

Admin dùng Swagger `/docs`: GET `/v1/admin/billing/unresolved` và POST `/v1/admin/billing/{reservation_id}/reconcile`. Payload gồm actual_usd, reason và evidence_reference; chỉ đưa mã/chứng từ tham chiếu, không paste secret hoặc chat riêng. Mỗi reconciliation có actor/time/reason/evidence, chỉ unresolved được settle một lần; số tiền được validate hữu hạn/không âm. Không bypass audit qua legacy reconcile signature.

Giữ native usage/cost và immutable response trace. Billing correction overlay cập nhật accounting view, charts/export và quota; không suy tokens từ USD. unknown_calls vẫn có thể >0 sau reconcile vì usage chưa xác định. Analytics báo reconciled_calls và UI giải thích correction; USD đã đối soát khác với cost tính từ usage/catalog.

## Điểm ghép và gate live sau

DatasetSource, PredictionGrader và RoutingEvidenceSource nằm trong contracts; scientific adapters/graders do Khoa phụ trách. Huy có thể thử routing fixtures ngay, không chờ implementation của Khoa. Shared signature/migration changes cần affected-owner review khi tích hợp.

`RESEARCH_LIVE_ENABLED=false` giữ live research bị chặn ở API/service, kể cả server đang dùng live chat. Batch live path đã nối qua MeteringContext/provider port/ledger và chỉ được kiểm tra bằng metered fakes; không có paid pilot hoặc bằng chứng G2/G3.

Gate sau phải khóa exact model IDs/access/capabilities, catalog version/prices, baseline và ma trận calls trong 20 USD; review budget rồi mới đặt PROVIDER_MODE=live và RESEARCH_LIVE_ENABLED=true, restart server, chọn live source và IDs thật. Không chỉ đổi nhãn execution_source. UI ghi rõ paid pilot và preflight live upper bound; live calls không đi vào simulation metrics. Run đang pending bị fail nếu catalog snapshot đổi hoặc gate bị tắt. Role/quota vẫn được kiểm tra theo DB, không dùng client identity. CLI live cũng dùng composition root/service này, không tạo worker thứ hai.

Live pilot ở suite hiện tại vẫn là functional fixture pilot. Các marker lỗi giả lập không điều khiển model thật, nên fixture match/failure không phải research score. Rule_guarded live chưa có qualified profiles sẽ về reference; fixture evidence không được dùng như DEV evidence. Dataset/quality thresholds và evidence import phải được qualification ở gate nghiên cứu sau.

## Verification

Windows local, Python 3.11.9 / Node 24.14.0:

- Backend: `pytest backend/tests -q` → **55 passed (60.65s)**. Gồm 11 router/research cases (parameterized cases đã tính), network-blocked simulation/live metered fakes, cancellation/restart, raw-history isolation, quota/run races, JSON fixture checker, audited reconcile và crash sau settlement trước trial commit.
- Ruff check/format và mypy → pass, **57 app source files**. Contracts drift check → OpenAPI/TypeScript match.
- Frontend ESLint, Prettier và TypeScript → pass. Vitest → **3 passed**.
- Chromium toàn bộ **6 flows passed**; research flow được chạy lại sau sửa cuối: **1 passed (24.1s)**, gồm VI/EN giữ seed, 120 trials, trace/export, mobile 390px không tràn ngang và user access control. Đã xem screenshots desktop/mobile thực tế.
- Next production build → pass; route `/research` được tạo cùng chat/dashboard.
- Documentation checker → **16 Markdown documents / 19 fenced examples** hợp lệ. CLI example preflight → 120 trials, live_enabled=false; sample exports được sinh bằng DB tạm và chặn socket.
- DB dev migrate `c102`, trước/sau giữ 3 users và không thay đổi session/message counts. Backup ở `data/backups/pre-router-20261020-204001.db` (gitignored). `.env` giữ nguyên, live research vẫn false.

Chưa có paid OpenAI pilot, qualified dataset/quality profiles hoặc scientific routing results. Local checks không đại diện kết quả CI Linux; kiểm tra remote CI riêng trên PR.
