# Master Prompt — Triển khai G0 Smart LLM Optimizer

Trạng thái: **brief G0 đã được hiện thực**, giữ để đối chiếu design/acceptance. [README](../README.md) và [handoff](G0_HANDOFF.md) mô tả code/checks thực tế. Không scaffold lại đè workspace có code. Bản này đồng bộ với [Design Spec V3](../SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md) ngày 20/10/2026; các yêu cầu dưới đây không phải tự động bằng chứng tests đã pass.

## 1. Nhiệm vụ khi prompt được dùng cho bước triển khai

Bạn là kỹ sư triển khai foundation G0 cho nhóm ba người. Đọc spec, hướng dẫn repo và skills liên quan trước khi code. Hoàn thành một foundation chạy thật từ clean setup với FastAPI, Next.js, SQLite WAL, deterministic mock provider, optimizer no-op và giao diện hoàn thiện. Chia việc thành các chặng có kiểm tra ở mục 7; sửa lỗi và hoàn thành acceptance mục 8, không dừng ở cây thư mục hoặc một chat demo đơn giản.

**Phạm vi G0:** contracts/config/locks, account CLI/auth, owned session/history, repositories/migrations, dedupe/concurrency/ledger, orchestration/trace, mock/no-ops, frontend hoàn thiện, eval smoke, offline CI, README và handoff. Không triển khai live provider adapter, classifier, thuật toán tối ưu thật, tải benchmark nghiên cứu, streaming, cache, cascade, GPU serving hoặc tool/agent loop. Các hạng mục đó thuộc gates sau G0. G0 không cần key hay model network calls; package installation là setup dependencies riêng.

Đọc hiện trạng workspace trước khi tạo files; không giả định V1 skeleton/repo/Git remote tồn tại, không ghi đè thay đổi ngoài phạm vi. Nếu một artifact ở blueprint chưa có thì tạo khi thực hiện G0, không mô tả nó như đã tồn tại. Không tạo remote/push/deploy hoặc gọi paid API từ prompt này. Dùng cây §14.2 làm cấu trúc tối thiểu; được thêm files thực sự cần để chạy/test.

## 2. Nguồn chuẩn và ownership

1. **Spec §04 là nguồn chuẩn DTO/ports, API, precedence, errors/accounting.** Blueprint §14 cụ thể hóa G0; §05/§11 là gates và ownership. Prompt này không tạo API/DTO song song. Nếu phát hiện xung đột chưa giải quyết, nêu đúng vị trí và sửa đồng bộ trong phạm vi hoặc hỏi khi quyết định sản phẩm còn thiếu; không tự bỏ acceptance.
2. DTO/result types ở `backend/app/contracts/dtos.py`; `contracts/protocols.py` import DTOs và định nghĩa ports một lần, kể cả `LLMProvider`. Không để result DTOs trong protocols hoặc tái định nghĩa provider ở adapters. Cụ thể hóa types theo §04 rồi review/freeze trước consumer code.
3. FastAPI OpenAPI là schema thực thi; export snapshot và sinh TypeScript bằng openapi-typescript. Không hand-edit generated TS. Composition root duy nhất wiring adapters; business modules dùng ports, không import private ORM/API/provider SDK để bypass.
4. **Huy (A)** sở hữu G0 toàn bộ, sau đó core/API/auth/storage/migrations/ledger/provider/router/wiring/frontend/generated TS/CI. **Tân (B)** nhận prompt/context/preservation sau G0. **Khoa (C)** nhận memory và evaluation/adapters/graders/runner/reports sau G0. Tân/Khoa review contracts/qualification trong G0; chỉ tạo feature branches sau toàn bộ acceptance G0 và cùng foundation commit.
5. Huy tích hợp shared contracts/migrations/wiring/locks; affected owner review. Mỗi người feature branch/DB/run dir riêng, PR nhỏ, merge tuần tự và kiểm tra integration. Không hứa không conflict hoặc merge tự động tuyệt đối. G0 estimate 1–2 ngày để lập lịch, không cam kết ngày đầu.

Áp dụng `.agents/skills/fastapi-sqlite-clean-arch`, `taste-skill`, `impeccable` cho nền tảng/UI; đọc các skills prompt/context, memory, router, eval để giữ đúng boundaries/no-op, không vì đọc skill mà triển khai thuật toán ngoài G0. Chỉ dùng codegraph-navigation nếu repo đã được index và có `.codegraph/` theo hướng dẫn repo.

## 3. Contracts và invariant bắt buộc

### Public API và auth

- Chat nhận **lượt user mới**: session_id, client_request_id, message, mode và optional policy_id/flags/constraints theo §04. Public schema reject user_id/trusted roles/full history/arbitrary provider options/experiment_id. User lấy từ auth; history từ SessionStore; server instructions tách riêng. DTO frozen phải bảo vệ nested mutable state, không chỉ frozen bề mặt.
- Cung cấp health, auth login/logout/me, models, owned sessions CRUD, chat, owned traces và current-user overview và CLI tạo user/eval smoke theo §04. Không thêm public batch launch/admin signup/BYOK. Dashboard G0 dùng GET /v1/overview đã định nghĩa tại canonical API, scope current-user/all-time, kiểm tra isolation. Admin live experiment report endpoints chưa bắt buộc G0.
- Admin/operator tạo account bằng CLI, password nhập ẩn và hash Argon2. Opaque auth token chỉ lưu hash/expiry/revocation; cookie HttpOnly/SameSite=Lax, Secure trong HTTPS với dev override rõ. Next proxy cùng origin; kiểm tra Origin cho browser writes, giới hạn login attempts/payload. Auth-session và conversation-session là hai loại khác nhau. Không account/password/key thật trong Git/logs/browser config.
- Logout/expiry làm token mất hiệu lực và clear client owned caches. ID không thuộc owner trả 404; admin-only action 403. Dùng error envelope/status mapping §04, không lộ raw provider exception/secret/history người khác.

### History, assembly và no-ops

- SessionStore thực hiện persistence thật độc lập memory flag. Load immutable scoped snapshot, commit original user + assistant nguyên tử khi success; failure/interrupted attempt riêng, không orphan user turn. Revision/order ổn định khi resume.
- **ContextManager là nơi duy nhất assemble messages** từ server instructions + committed snapshot + current turn. Current turn đi qua features, đúng một lần. Orchestrator không append lại; không trộn raw với summary trùng coverage. No-op/baseline dùng full original raw history và current content/roles không biến đổi.
- MemoryManager.prepare(snapshot, plan) no-op giữ nguyên snapshot/raw/derived state/revision; không tạo summary/facts hoặc gọi provider. Không dùng empty recent_turns hoặc `save_turn(): pass`. Summary/facts algorithms thuộc Khoa sau G0; lưu qua MemoryStore do Huy sở hữu.
- PromptOptimizer giữ original mutable content. Router G0 chọn configured mock_config_id từ registry; analyzer trả unknown. Không classifier heuristic giả, không model/giá hardcode. Context “no-op” vẫn làm assembly chuẩn, không compaction.
- Theo signatures §04; không thay optimize bằng `(prompt: str, constraints: list[str])`, không đổi router select thành một route(dict) khác. Trước consumer code, thống nhất DTO input/output/side effects và tests ở canonical contracts.

### Modes, flags và provenance

- Baseline tắt bốn optional optimizers nhưng giữ auth/history/accounting/trace; conflict true flag/policy theo §04 trả 422. G0 optimized resolve `foundation-mock-v3` trong mock deployment; không default một live quality policy chưa triển khai.
- False flag → disabled. True + no-op → not_implemented. Skipped chỉ khi implementation có thật nhưng điều kiện/policy không cho chạy; applied cần hành vi thật; failed có reason/recovery/error. No-op không sinh optimizer inference calls. Kiểm tra đủ 16 tổ hợp.
- API/trace expose requested và effective policy/version/flags/availability/status/reason. UI không suy effective chỉ từ checkbox. Trace cũ giữ config snapshot ngay cả khi đổi toggles cho request tiếp theo.
- Mock artifacts: execution_source=mock, cost.status=not_billable, serving_usd=null. Usage là mock/estimated/unknown có nguồn, không provider usage. Quality và nghiên cứu savings null; nonstreaming TTFT null. Không chế số để vẽ chart/badge. Missing usage/cost không lấp zero.
- Smoke là functional verification; export giữ purpose/provenance. Live research validator phải reject mock/unqualified sources/thiếu manifest; chưa chạy live ở G0.

### Concurrency và accounting

- Dedupe theo `(owner_user_id, client_request_id)` + canonical validated payload hash (không hash timestamp/generated metadata). Same succeeded payload trả stored response/request_id không call mới. Payload khác, in-progress hoặc attempt failed/interrupted trả 409 theo §04; không tự tạo attempt trả phí khác.
- Một active attempt/session, lease/restart handling rõ. Không dùng process lock thay DB correctness; test hai concurrent callers/session và khác sessions khi quota gần hết. Session purge lúc active trả 409.
- SQLite local một worker, WAL/foreign keys/busy timeout, short write transactions. Không giữ DB transaction qua inference, không share AsyncSession đồng thời. Alembic upgrade từ DB rỗng và repository mapping theo migrations.
- CostCatalog pricing tách BudgetLedger. Reserve/settle/release/reconcile nguyên tử ở request/user/project; số tiền decimal, remaining trừ settled và outstanding reservations. Mọi inference sau G0 phải qua metered port/ledger. Không dispatch thì release; dispatch không rõ usage thì giữ unresolved để reconcile, không tự refund hay replay.
- Mock not_billable không bịa tiền reservation/usage. Dùng metered fake/fault fixture riêng để kiểm tra nonzero budget, race, timeout/unknown usage và settle; fixture không là live scientific result và không bị export như mock miễn phí.
- Aggregate tất cả calls theo §04, tránh cộng cached/reasoning twice; unknown/partial fields null với known subtotal/provenance nếu có. Token estimate có source/status/model/tokenizer/version; không dùng `len(text)//4` như provider usage hoặc exact context guard. G0 có thể unknown; live cần conservative configured bound/verified estimator hoặc lỗi rõ, không giả chính xác.

## 4. UI G0 hoàn thiện

Dùng giao diện sáng trắng–xanh OU: #034EA2 chính, #387EC1 phụ, nền trắng/xám nhạt, text đủ contrast. Roboto local có tiếng Việt; giữ nguyên logo người dùng cung cấp và license assets. Mono cho IDs/trace. UI Việt/Anh bằng next-intl, default vi và cookie locale; đổi locale không đổi content hoặc mất draft. Không thêm theme tối trong G0. Dùng components/theme nhất quán và spacing hợp lý.

Hoàn thiện các luồng:

- Login/logout/auth-expired; labels, hidden password, error rõ, không lưu token trong localStorage.
- Sidebar owned sessions/create/delete/resume; empty history, active/busy state; không rò history sau đổi user.
- Chat composer và transcript giữ roles/order; submit/loading/error, duplicate-submit handling; không tự retry uncertain dispatched request bằng ID mới. Hiển thị mock mode xuyên suốt.
- Baseline/optimized và bốn flags, requested/effective state, no-op availability/reasons; config snapshot trong request/trace, state rõ khi request chạy.
- Trace inspector gồm route/config/status, call list, actual timings, usage/cost provenance/error; không log key/private raw prompts trong telemetry. Nội dung hội thoại chỉ ở owned history/API đúng quyền.
- Dashboard dùng owned actual mock counts/timings/traces. Cost/quality/savings chưa đo ghi **“chưa có dữ liệu live”**, không fake Pareto/green saving badge/preview research score. Các biểu đồ live chỉ xuất hiện sau artifacts đủ điều kiện ở G8.

Mọi màn hình có responsive/narrow viewport, keyboard/focus, readable contrast/touch targets, loading/error/empty/disabled states và reduced-motion. Error retry phải theo error/dedupe semantics, không ngầm gọi trả phí. Kiểm tra UI flows thật sau khi code; không chỉ ảnh tĩnh hoặc build thành công.

## 5. Dependencies, commands và artifacts

- Chọn compatible exact versions cho Python/Node và dependencies, commit npm package-lock cùng backend requirements.lock. Python 3.11+ / Pydantic V2 / SQLAlchemy async. Ghi rõ supported versions và setup trong README.
- Đối chiếu [Next.js installation](https://nextjs.org/docs/app/getting-started/installation) và [Tailwind Next.js guide](https://tailwindcss.com/docs/installation/framework-guides/nextjs) tại lúc tạo G0. Không ép Tailwind config/PostCSS của major cũ vào major khác. Không lấy “latest” thay lock.
- Implement root commands theo §14.5: backend editable package + locked deps (gồm hatchling/editables cho no-build-isolation), Alembic/account CLI/uvicorn; root dev chạy cả hai service, npm workspace dev/contracts:generate/contracts:check/typecheck/build/test:ui; `python -m pytest backend/tests`; `python -m app.cli eval run --purpose smoke --manifest benchmark/manifests/smoke.json`.
- README tách Windows PowerShell và POSIX activation, mọi lệnh working directory rõ. Tests dùng temp DB/run dirs; không reset/xóa DB dev thật. Config resolves root DB path nhất quán, proxy/ports/cookie host rõ. `.env.example` mock mặc định, không secret; không overwrite `.env` có sẵn.
- Generated OpenAPI/types và smoke report có schema/purpose/source rõ; chỉ commit artifacts được chủ định, không DB/private history/credentials/temporary build outputs.

## 6. Benchmark boundary cho bước sau G0

G0 chỉ synthetic smoke. Không tải/chạy full public benchmark hoặc trả tiền để hoàn thành foundation. Four suites vẫn là targets cần qualification theo §06: SEA-IFEval config vi/split eval; ViQuAD2 multiple gold + no-answer và plausible_answers không làm gold; Vi-Dialog probes chuyển thể có checkpoint/evidence/version/review; VMLU MCQ retain options/keys/topics.

140–170 là tổng đơn vị DEV + HOLDOUT, báo riêng câu hỏi/conversation/turn/probe và group split trước tune. Pilot quyết định call matrix trong khoảng 20 USD gồm development/optimizer/judge/reruns. Không cam kết 5–8 USD, statistical significance hoặc non-inferiority 3 pp. Gold/reference/evidence chỉ vào evaluator; deterministic graders theo constraint thực, không dùng “có từ không” làm proof. Open-ended cần blind judge/human calibration ở gate nghiên cứu, không score giả trong G0. Dữ liệu hội thoại ngắn không tự chứng minh long-term memory/context dài.

## 7. Các chặng triển khai và điều kiện chuyển chặng

### A. Contracts/config/locks

Khảo sát files hiện có, xác nhận scope; tạo root/backend/frontend configs và canonical DTOs/ports, settings/mock registry, error mapping. Chọn/lock dependencies tương thích; concretize internal DTO shapes §04 một lần. Kiểm tra schema examples, public-field rejection, precedence, nullable/source semantics và dependency boundaries trước viết consumers. Snapshot OpenAPI/TS có thể sinh sau routes, nhưng toolchain/generator command phải được định nghĩa từ chặng này.

### B. Auth/storage/ledger/mock pipeline

Migrations/repositories/account CLI, auth/ownership, dedupe/lease, BudgetLedger và request lifecycle; composition wiring mock và four no-ops. Hoàn thành create→chat→atomic commit→resume→trace và fault/restart paths. Chạy backend contract/integration tests gồm isolation, all flag combinations, race/budget/unknown usage với fakes. Sửa failure trước thêm UI dependency vào flow chưa ổn.

### C. Frontend hoàn thiện

Sinh API types và xây các UI flows mục 4 từ real backend/mock. Không cài API client schema riêng theo trí nhớ. Chạy typecheck/build và UI tests cho hai user, flags/effective config, trace, logout/expiry/error/empty/mobile/keyboard. Chỉ thêm charts dùng actual eligible data; G0 research metrics vẫn empty.

### D. Integration/README/handoff

Eval smoke/reproducible exports, offline CI/contract drift, clean install/migrations/account CLI theo README. Hoàn tất mục 8, ghi actual commands/results và known limits. Nếu thiếu môi trường/OS/browser để kiểm tra thì báo chưa kiểm tra; không tick pass. Huy bàn giao một foundation commit sau checks; Tân/Khoa nhận commit đó để tách feature branches, không chia nhánh sớm chỉ vì chặng A xong.

## 8. Acceptance và báo cáo bàn giao

Toàn bộ checklist spec §14.8 là điều kiện G0, gồm:

- Clean locked setup, migrations, account CLI; mock offline/no key; ghi đúng OS thực kiểm tra.
- Hai users cách ly history/session/trace; logout/expiry/revocation và admin namespace đúng.
- Atomic original pair/history resume, memory off vẫn persist; failures không orphan turns.
- Current user đúng một lần, roles/input nguyên vẹn; 16 flags combinations, baseline precedence và zero optimizer calls từ no-op.
- Dedupe/concurrent requests/session busy/quota race; interrupted dispatch không auto replay.
- Reservation/settlement/release/reconcile request/user/project, unknown usage/cost giữ đúng provenance/null trên API/UI/exports.
- Smoke tái lập, mock/live research validation; không tạo quality/savings giả.
- OpenAPI/generated TS nhất quán, boundary checks; backend tests, frontend typecheck/build và UI flows thực đạt.
- Full UI polished/responsive/loading/error/empty/accessibility và effective config đúng từng request.
- Foundation commit, ownership, commands/evidence/known limits và next tickets.

Kết thúc bằng báo cáo ngắn: files/behavior đã tạo, chặng và acceptance đã kiểm tra, exact commands + exit results, chưa kiểm tra/limitations, commit bàn giao nếu đã có Git và next gates. Không ghi “100% pass”, “không conflict” hoặc tiết kiệm nghiên cứu khi không có bằng chứng. Nếu còn mục G0 thiếu, tiếp tục sửa phần có thể làm và nêu blocker cụ thể; không đổi gate để tuyên bố hoàn thành.
