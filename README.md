# Smart LLM Optimizer · OU

MVP mở rộng từ foundation G0 cho nghiên cứu tối ưu model, prompt, context và memory. FastAPI + Next.js + SQLite; giao diện trắng–xanh OU, Việt/Anh. **Mock provider mặc định**; có adapter OpenAI, tài liệu/hybrid RAG, full-text jobs, dashboard usage/USD và admin quota. Live chỉ bật khi có key và catalog được review. Optimizers hiện là typed no-ops, chưa có kết quả tiết kiệm hay chất lượng live.

## Yêu cầu

- Python **3.11**, Node **24**, npm **11**; Git để làm việc nhóm.
- Windows PowerShell là môi trường đã dùng để kiểm tra. Commands POSIX bên dưới; CI Windows/Linux nằm trong repo, kết quả remote CI chỉ có sau khi push.
- Không cần Docker, GPU hoặc API key ở G0. Tải dependencies/browser cần Internet; ứng dụng mock dùng tài nguyên local sau setup.

## Setup Windows PowerShell

Mọi lệnh từ **repo root**, ví dụ:

```powershell
Set-Location 'D:\Documents\OU-TongHop-Project\SmartLLMPlatform'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r backend/requirements.lock
python -m pip install --no-deps --no-build-isolation -e 'backend[dev]'
npm ci
npm run setup
npm run doctor
npm run db:migrate
npm run account:create -- --username huy --role admin
npm run dev
```

CLI yêu cầu nhập/xác nhận mật khẩu ẩn (8–256 ký tự). Không truyền mật khẩu thật qua option/command history. Không có tài khoản/mật khẩu mặc định. Nếu PowerShell chặn activation, dùng terminal được phép chạy venv hoặc gọi `.\.venv\Scripts\python.exe` thay `python`; không cần đổi execution policy toàn máy.

## Setup macOS / Linux

Từ repo root:

```bash
cd /path/to/SmartLLMPlatform
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r backend/requirements.lock
python -m pip install --no-deps --no-build-isolation -e 'backend[dev]'
npm ci
npm run setup
npm run doctor
npm run db:migrate
npm run account:create -- --username huy --role admin
npm run dev
```

UI: **http://localhost:3000** · API docs: **http://127.0.0.1:8000/docs**. Browser UI gọi `/api/*` cùng origin qua Next proxy. Dùng `localhost` cho UI để cookie/Origin nhất quán. Cả hai service bind local; chưa hỗ trợ LAN/public deployment. `Ctrl+C` dừng cả hai service.

`npm run setup` chỉ copy `.env.example` nếu `.env` chưa tồn tại. Migration không reset DB; account CLI không ghi đè user có sẵn. Mỗi clone/worktree dùng DB riêng, mặc định `data/smartllm.db`; path luôn resolve theo repo root. Không chia sẻ/commit DB hoặc history riêng.

## Cấu hình và API key

Root `.env` được backend đọc bằng Pydantic Settings. `PROVIDER_MODE=mock` mặc định không gọi paid API. Để bật live, làm theo [hướng dẫn MVP](docs/MVP_HANDOFF.md): cấu hình server `OPENAI_API_KEY`, catalog model/giá có version, rồi đặt `PROVIDER_MODE=live`. Catalog là nguồn cấu hình chuẩn, `OPENAI_MODEL` chỉ là biến legacy chưa dùng để chọn model. Không đặt key trong `NEXT_PUBLIC_*`, UI hoặc source code.

Từ root, sau khi activate venv, có thể chạy `python -m app.cli tokenizer-setup` để tải tokenizer công khai một lần. Không có cache, chunker dùng conservative UTF-8 byte-bound splitter offline và ghi version khác; đây không phải usage provider.

Các defaults: auth expiry 8 giờ, cookie HttpOnly/SameSite=Lax, Secure=false riêng HTTP local; project budget 20 USD, user budget mặc định 5 USD. Mock là not_billable và không trừ tiền. Các giá trị quota phải review cùng live pricing/call matrix trước paid pilot; không phải cam kết kiểm soát hóa đơn của key dùng ngoài platform.

Nếu đổi backend port, sửa command chạy backend và copy `frontend/.env.local.example` thành `frontend/.env.local` để đổi `BACKEND_URL`. Không cần frontend env cho cấu hình mặc định. `ALLOWED_ORIGINS` trong backend là JSON array, mặc định `["http://localhost:3000"]`.

## Commands từ repo root

Activate `.venv` trước các commands Python/npm checks; `npm run dev` tự tìm Python trong `.venv`.

| Command | Công dụng |
|---|---|
| `npm run dev` | Backend + frontend đồng thời |
| `npm run dev:backend` / `npm run dev:frontend` | Chạy riêng service |
| `npm run db:migrate` | Alembic upgrade head |
| `npm run account:create -- --username <name>` | Tạo account, mật khẩu nhập ẩn |
| `npm run contracts:generate` / `npm run contracts:check` | Sinh/kiểm tra OpenAPI + TypeScript |
| `npm run lint` / `npm run typecheck` | Ruff/ESLint và mypy/TypeScript |
| `npm run format` / `npm run format:check` | Format/check code, không sửa generated types |
| `npm run test:backend` / `npm run test:frontend` | Pytest / frontend unit tests |
| `npm run build` | Production frontend build |
| `npm run eval:smoke` | Synthetic functional smoke, DB tạm riêng |
| `npm run test:ui` | Chromium UI flows, DB/accounts tạm riêng |

Trước lần đầu chạy UI tests:

```text
npx playwright install chromium
```

UI tests chạy service test trên ports **3001/8001**, không đụng DB dev và không dùng lại server đang chạy. Artifacts ở `output/playwright/` (gitignored). Eval smoke xuất `benchmark/reports/smoke.jsonl` (gitignored); chỉ predictions/status tái lập, không yêu cầu timestamps/UUID/timing giống byte-for-byte. `live_research` vẫn bị chặn trong smoke runner; chưa có scientific benchmark qualified.

Để cập nhật backend lockfile, maintainer cài uv và chạy từ root:

```text
uv pip compile backend/pyproject.toml --extra dev --universal --generate-hashes --output-file backend/requirements.lock
```

Không chạy upgrade/format cả repo trong PR thuật toán. Locks và generated artifacts do Huy tích hợp cùng affected-owner review.

## Module boundaries và làm việc nhóm

Backend dùng `app/contracts` cho DTOs/ports, `core` cho lifecycle, `storage` cho adapters. Composition root wiring ở `backend/app/composition.py`. Frontend dùng API types sinh tự động; không duy trì schema client viết tay.

- **Huy:** contracts/API/auth/storage/migrations/ledger/provider/router/wiring/frontend/tooling, document ingestion/RAG và document task service.
- **Tân:** `backend/app/optimizers/` và module tests, sau handoff G0.
- **Khoa:** `backend/app/memory/`, `evaluation/`, `benchmark/` và module tests, sau handoff G0.

Tân/Khoa dùng repository/provider ports; không import private ORM hoặc SDK. ContextManager assemble messages duy nhất; MemoryManager không thay raw history/persistence. Cả nhóm tách branches từ cùng foundation commit sau acceptance; PR nhỏ, merge tuần tự. Xem [ownership/handoff](docs/G0_HANDOFF.md) và [CONTRIBUTING](CONTRIBUTING.md).

## Hiểu đúng trạng thái G0

True optimizer flag → `not_implemented`; false → `disabled`. Baseline tắt optional transforms nhưng vẫn auth/history/accounting. Các cờ thay đổi request tiếp theo; trace giữ effective configuration lúc chạy. Duplicate succeeded ID/payload trả stored response, không gọi lại provider; in-progress/payload conflict/session busy trả 409.

Mock cost `not_billable/null`, usage không giả provider tokens; quality/savings null, nonstreaming TTFT null. Dashboard chỉ tổng hợp owned requests. Đổi ngôn ngữ không dịch history hoặc xóa draft. Xóa session purge nội dung/trace, giữ tombstones/accounting tối thiểu để chống replay.

Timing trong mock trace có `measurement_scope=server_through_history_flush`: gồm xử lý và flush history, dừng trước lần ghi/commit trace cuối. HTTP header `Server-Timing` đo tới lúc gửi response headers, gồm transaction commit. Cả hai là local server timings, không phải browser end-to-end hoặc scientific latency comparison; G2 phải đo protocol live riêng theo spec.

Đây là local research foundation, chưa triển khai API thật/classifier/optimization algorithms, streaming/cache/cascade, public benchmark qualification hoặc scientific claims. Các gate tiếp theo ở [Design Spec V3](SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md); [Master Prompt](docs/SKELETON_MASTER_PROMPT.md) ghi implementation brief và thay đổi nhận diện.

## License / assets

Code tự viết: MIT. Logo OU và font có quyền/giấy phép riêng; xem [asset provenance](docs/ASSETS.md). Không suy ra MIT cho dữ liệu benchmark, logo trường hoặc model weights.


## Tài liệu và thống kê

Trong chat mở **Tài liệu hội thoại**, upload TXT/MD UTF-8, PDF có chữ hoặc DOCX, chọn file rồi **Lập chỉ mục**. Chọn nguồn đã ready để hỏi đáp; các nút **Tóm tắt toàn văn** / **Đối chiếu tài liệu** chạy job riêng có budget và tiến độ. Tóm tắt/đối chiếu xử lý toàn bộ chunks, từ chối trước generation nếu preflight không đủ budget; failed/interrupted không được trình bày như kết quả hoàn chỉnh. Preview trích xuất không cần paid API; live indexing/query embedding có phí. File gốc tạm được xóa sau trích xuất; text/chunks nằm trong DB ngoài public directory.

**Tổng quan** có ngày/model/session/category, nguồn mock/live tách biệt, input/output token charts, USD/model costs, call-latency p50/p95, bảng và CSV/JSON. Quota là lifetime và không đổi theo date filter. Usage trước bản mở rộng có thể chưa có call records; không backfill số liệu giả. Xóa session purge nội dung/tài liệu/job/trace, vẫn giữ usage/accounting tối thiểu. Admin chỉ thấy thống kê và sửa quota có audit; không tự được đọc nội dung riêng.

So sánh baseline–optimized và báo cáo khoa học chờ các module/gates của Tân/Khoa. Không coi mock hoặc no-op là thuật toán đã đạt quality guardrails. Xem [MVP handoff](docs/MVP_HANDOFF.md).
