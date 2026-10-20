# MVP extension handoff

## Trạng thái

Mốc 1 có implementation: OpenAI Responses adapter, catalog/pricing, metered generation/embedding, upload/extraction, session-scoped hybrid RAG, full-text/compare jobs, owned analytics/export và admin quota audit. Mock vẫn là default. Mốc 2 (thuật toán Tân/Khoa, same-snapshot optimized comparison và scientific reports) chưa được nhận gate; UI không tạo savings/quality score giả.

Verification thực tế của đợt mở rộng được ghi ở mục cuối sau khi các checks hoàn tất. Không suy passing fakes thành model access hoặc research evidence. Dữ liệu dev đã backup dưới `data/backups` trước migration `b901`; không reset accounts/history, không ghi đè `.env`.

## Bật live từ repo root

1. Activate `.venv`. Giữ key tại root `.env`, không đưa vào frontend hoặc chat. Đặt `OPENAI_API_KEY` bằng key do operator sở hữu. Không có paid call trong setup, CI hoặc tests.
2. Copy `config/models.example.json` sang `config/models.json` nếu chưa có. File runtime được gitignore; điền `baseline_config`, `embedding_config`, version và ít nhất hai entries theo schema dưới đây. Có thể thêm generation candidates; routing hiện fixed baseline vì chưa có measured optimizer evidence.
3. Điền giá từ nguồn chính thức tại thời điểm review, đúng model/tier/category. Ví dụ schema dưới dùng placeholders, **không phải giá thật**. `effective_at` ghi thời điểm áp dụng; đổi bất kỳ giá/config snapshot thì tăng catalog version.
4. Chạy `python -m app.cli verify-catalog`: chỉ GET metadata model, không generation/embedding. Thành công chỉ chứng minh metadata access, không tự chứng minh generation capability/quota/quality. Ghi `verified_access=true` sau khi kiểm tra quyền phù hợp; đặt `pricing_verified=true` chỉ sau operator review giá. Hai flags phải true mới dùng entry trong live.
5. Chạy `python -m app.cli tokenizer-setup` để cache tokenizer công khai, rồi restart app. Thiếu cache có conservative byte-bound splitter offline; version được lưu trên chunks, không giả provider usage.
6. Đặt `PROVIDER_MODE=live`, `MODEL_CATALOG_PATH=config/models.json`, kiểm tra project/user budgets rồi restart `npm run dev`. `OPENAI_MODEL` legacy không chọn model; catalog mới là nguồn chuẩn. Không auto-run paid pilot khi boot.
7. Paid pilot nhỏ là bước riêng do operator chọn, trong project envelope 20 USD gồm cả embedding/eval. Ghi usage/catalog/access/actual caps trước live research; chưa được thực hiện trong đợt handoff này.

```json
{
  "version": "reviewed-YYYY-MM-DD-v1",
  "baseline_config": "baseline",
  "embedding_config": "embedding",
  "embedding_revision": "v1",
  "models": [
    {
      "config_id": "baseline",
      "model_id": "REPLACE_WITH_EXACT_GENERATION_MODEL_ID",
      "kind": "generation",
      "context_window": 1,
      "max_output_tokens": 1,
      "input_per_million": "REPLACE_WITH_REVIEWED_USD_RATE",
      "output_per_million": "REPLACE_WITH_REVIEWED_USD_RATE",
      "cached_per_million": null,
      "cache_write_per_million": null,
      "source_url": "https://developers.openai.com/api/docs/pricing",
      "effective_at": "REPLACE_WITH_REVIEW_TIME",
      "verified_access": false,
      "pricing_verified": false
    },
    {
      "config_id": "embedding",
      "model_id": "text-embedding-3-small",
      "kind": "embedding",
      "context_window": 1,
      "max_output_tokens": 1,
      "input_per_million": "REPLACE_WITH_REVIEWED_USD_RATE",
      "output_per_million": "0",
      "source_url": "https://developers.openai.com/api/docs/pricing",
      "effective_at": "REPLACE_WITH_REVIEW_TIME",
      "verified_access": false,
      "pricing_verified": false
    }
  ]
}
```

Giá trị `1` ở context/output chỉ là placeholder buộc operator thay đúng capabilities. Null cache rates không có nghĩa mọi cache đều miễn phí: usage có category chưa được catalog hỗ trợ sẽ thành unknown. Cache-write field thiếu chỉ được coi không có category tính riêng khi catalog đã review không có rate đó. Cached tokens nằm trong input, reasoning nằm trong output; không cộng hai lần.

## Luồng dùng tài liệu

- Tài liệu theo từng hội thoại, không có shared library. TXT/MD UTF-8, PDF có chữ, DOCX paragraphs/tables; không OCR/ảnh/macros. Bản này xử lý text đã trích xuất, không đảm bảo giữ nguyên layout, biểu đồ, footnotes hoặc nội dung ảnh.
- Mặc định 10 MiB/file, 5 files, 200 PDF pages, 200000 chars/file. Parser subprocess timeout 30s, DOCX kiểm tra uncompressed-size/ratio trước parse. File raw tạm được xóa sau extraction; text/chunks nằm trong SQLite, không nằm public assets.
- Preview không gọi API. **Lập chỉ mục** tạo metered embeddings; chọn ready documents rồi chat sẽ thêm query embedding và evidence. Mock dùng hash embedding có nhãn rõ, chỉ functional fixture.
- Full-document summary map tất cả chunks rồi reduce. Compare map toàn bộ, tổng hợp từng nguồn rồi synthesis; không dùng top-k làm toàn văn. Default job budget 0.50 USD, server cap 1 USD; preflight có thể từ chối trước paid generation. Giới hạn 128 map/reduce calls. Reduce không vừa conservative context bound thì fail, không tự cắt evidence.
- Job có durable pending/running/succeeded/failed/interrupted, current progress. Chỉ complete result mới commit user/assistant pair. Pending chưa dispatch có thể chạy sau restart; running không auto-replay. Failed/interrupted hiển thị incomplete, không giả hoàn chỉnh.
- Một active operation/session; mutation/delete bị chặn khi active. Retry upload cùng hash và ready indexing cùng version không phát sinh lại embedding. Đổi embedding model/revision phải reindex. Retry failed paid jobs phải chủ động dùng ID mới sau xem trạng thái/chi phí cũ.
- Citation source membership được validate, source drawer xem đoạn đã dùng. Đây chưa là factuality/entailment grader. Source IDs được snapshot qua session lease; chunk order/location và index version được giữ.

## Usage, privacy và ngân sách

`GET /v1/usage` mặc định 7 ngày/current mode; `source=mock|live` tách lịch sử. Ngày theo Asia/Ho_Chi_Minh, lưu UTC, custom tối đa 366 ngày. Calls là generation/embedding calls; operations gồm chat và document jobs. Chart latency là **call duration**, không TTFT hoặc browser end-to-end. p95 dùng nearest observed rank, có sample count.

Input/output có tổng; cached/reasoning ở trace là subsets. Chi phí estimated từ actual usage/catalog, không phải invoice. Missing usage/cost giữ null, known subtotal chỉ có khi có priced calls. Mock not_billable/null không thành giá live zero. Quota và reservation lifetime độc lập date/source filter. Serving/indexing/evaluation tách categories; indexing không tính lại mỗi turn.

Xóa session purge raw history/derived memory/documents/chunks/FTS/job payload/success traces; giữ attempts tombstone, minimal UsageRecord/ledger và price/audit không chứa prompt/excerpt/title riêng. Admin project analytics thấy accounting IDs/model/counters, không đọc foreign sessions/documents. Quota không hạ dưới spend+outstanding, mọi thay đổi có actor/reason/time. CSV/JSON giữ cùng filters; CSV có dimension total/day/model/category/session, null xuất ô trống.

## Ownership và mốc 2

Huy: core/API/auth/storage/ledger/provider/catalog, document ingestion/retrieval baseline/task service, analytics/admin/frontend và integration. Tân: prompt/context/preservation algorithms; Khoa: conversation memory/evaluation/reports. ContextManager vẫn duy nhất assemble current turn và evidence; không bypass ledger/ports bằng provider SDK trong algorithms.

Chưa có accepted optimizer algorithms, scientific dataset qualification, same-snapshot comparison endpoint/report import. Tiếp tục G1–G8 theo spec: nhận module đã test → frozen same-snapshot baseline/optimized pair → all-in cost/quality/latency + uncertainty. Không bật compare như một savings demo khi các nhánh vẫn no-op. Không chạm nhánh/module riêng của Tân/Khoa để tạo kết quả nghiên cứu giả.

## Verification

Kết quả kiểm tra thực tế trên Windows local (Python 3.11.9, Node 24.14.0):

1. **Backend Unit & Integration Tests:** `.venv\Scripts\python.exe -m pytest backend/tests -q` → `44 passed in 56.68s` (bao gồm migration b901 từ DB G0, dedupe, document lifecycle, hybrid RAG, full-text jobs, accounting & quota audit).
2. **Frontend Unit Tests:** `npm run test:frontend` (Vitest) → `3 passed (1.55s)`.
3. **Contracts Check:** `npm run contracts:check` → `OpenAPI / TypeScript contracts match` (docs/openapi.json và frontend/src/lib/generated/api.d.ts đồng bộ hoàn toàn).
4. **Backend Linting:** `.venv\Scripts\python.exe -m ruff check backend scripts` → `All checks passed!`.
5. **Frontend Linting:** `npm run lint --workspace frontend` (ESLint) → exit 0, không có warning/error.
6. **Backend Typecheck:** `.venv\Scripts\python.exe -m mypy --config-file backend/pyproject.toml backend/app` → `Success: no issues found in 47 source files`.
7. **Frontend Typecheck:** `npm run typecheck --workspace frontend` (`tsc --noEmit`) → exit 0, không có lỗi types.
8. **Documentation Links & Fenced Examples:** `.venv\Scripts\python.exe scripts/check-docs.py` → `15 Markdown documents valid; 18 fenced examples checked`.
9. **Next.js Production Build:** `npm run build` → Compiled successfully, static & dynamic routes generated (`/`, `/_not-found`, `/dashboard`).
10. **Playwright E2E UI Tests:** `npm run test:ui` (Chromium isolated ports 3001/8001) → `5 passed (29.2s)`:
    - Chat sở hữu riêng, no-op flags, trace inspector, chuyển đổi ngôn ngữ VI/EN giữ nguyên draft, resume, overview và logout.
    - Cách ly dữ liệu user thứ hai và kiểm tra credentials không hợp lệ.
    - Mobile 390px, network retry giữ nguyên request ID, hết hạn phiên xóa UI riêng tư.
    - Upload tài liệu, trích xuất text/preview, lập chỉ mục mock metered, hỏi đáp RAG kèm trích dẫn nguồn, tác vụ tóm tắt toàn văn đa bước, xóa phiên purge nội dung, kiểm tra xuất CSV/JSON và responsive 390px không tràn ngang (`root: 390, viewport: 390`).
    - Quyền admin: xem thống kê aggregated toàn project và cập nhật quota có audit log.
11. **Evaluation Smoke:** `.venv\Scripts\python.exe -m app.cli eval run --purpose smoke --manifest benchmark/manifests/smoke.json` → `3 functional cases; mock, quality/savings unknown`.
12. **Database & Migration:** Database dev `data/smartllm.db` đã migrate lên `b901 (head)`, bản sao lưu trước migrate lưu tại `data/backups/pre-mvp-20261020-170854.db`.

*Lưu ý:* Remote Linux CI và paid OpenAI pilot thực tế chưa kích hoạt (vẫn tuân thủ hạn mức ngân sách 20 USD, chỉ chạy khi operator cấu hình catalog đã review và server key).
