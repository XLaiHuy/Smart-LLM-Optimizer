# Router training — 22/10/2026

**Cập nhật final candidate:** xem [trạng thái hiện tại](ROUTER_FINAL_READINESS.md) cho ONNX INT8, SDPA, shared-state port, drift, migration `g106`, dữ liệu V3 và kiểm tra readiness. Các số kiểm thử/lỗi UI ở phần cuối tài liệu này là lịch sử của lượt triển khai đầu tiên.

Admin mở `/research` → **Tự huấn luyện router** → chọn **Dữ liệu và cache local** hoặc **Hugging Face + Gemini live** → **Lấy dữ liệu, distill và train**. Mặc định tự import vào Lab sau khi HOLDOUT đạt guardrails; có thể bỏ chọn để tải và kiểm tra artifact trước khi bấm **Import vào Lab**.

Đây là huấn luyện bộ chọn model TF-IDF + 14 đặc trưng cấu trúc + GBDT grouped OOF, có tùy chọn ONNX INT8 và learned attention SDPA; không fine-tune Gemini. Shared-state port chờ adapter của Tân; drift đã nối DB và routing. Chưa xác minh CUDA FlashAttention. Artifact mới mang `research_candidate` (hoặc `software_test`), không tự biến thành `qualified_dev`.

## Thiết lập một lần trên server

Không có manifest/dữ liệu được review sẵn trong repo. Nút hiển thị hướng dẫn thiết lập và không gửi API khi thiếu cấu hình. Không dùng các giá trị placeholder trong ví dụ làm giá/model thật.

1. Copy [manifest mẫu](../config/router-training.example.json) vào `data/router-training/manifest.json`. Điền người review, phiên bản, nguồn/giấy phép, model IDs đã xác minh quyền truy cập, giới hạn context/output, reasoning effort nếu dùng và bảng giá **đúng tier tài khoản**. Các số 0 trong rates chỉ là placeholder; chỉ giữ 0 khi đã xác nhận chính tier/model được miễn phí. `access_verified=false` trong mẫu khóa live.
2. Chọn file nguồn công khai đã review. Ghi full HF commit SHA 40 ký tự, file path và SHA-256 của **bytes file gốc**. Dùng `Get-FileHash -Algorithm SHA256 <file>` để lấy hash. Không dùng `main` làm revision. Quyền truy cập mirror không tự xác nhận giấy phép dữ liệu gốc.
3. Đặt `source.local_path` cho bản local. Dùng cùng bytes/hash cho hai chế độ. Live tải file đã ghim và kiểm tra hash trước khi dùng; cache chỉ đọc local. Nguồn mặc định tối đa 20 MiB, 2.000 mẫu; `max_samples` chọn prefix cố định, cần review độ phủ miền và split trước khi chạy. Đây không phải tự tải toàn bộ 32 benchmark trong plan.
4. Chỉ khi chạy live: đặt `GEMINI_API_KEY` phía server, `RESEARCH_LIVE_ENABLED=true`, `access_verified=true`, `software_test=false`; cả ba cấu hình có `execution_source=live` và `endpoint=gemini_chat_completions`. Giữ `PROVIDER_MODE=mock` nếu chat vẫn chạy mock. Không đặt key trong frontend. Restart backend sau đổi Settings. Test/CI (`APP_ENV=test`) luôn khóa live.

Tùy chọn đường dẫn trong `.env`:

```text
ROUTER_TRAINING_MANIFEST_PATH=data/router-training/manifest.json
ROUTER_TRAINING_DIRECTORY=data/router-training
```

Jobs dùng `request_attempts`; paid calls dùng usage/reservations/ledger hiện có. Feedback drift cần migration `g106`. Cấu hình một backend worker như nền tảng SQLite hiện tại. UI test server và backend tests dùng đường dẫn tạm riêng.

## Định dạng nguồn

- `adapter=vmlu`: JSON array, `{"data":[...]}` hoặc JSONL. Mỗi row có `id`, `question`, `choices`, `answer`, tùy chọn `subject`. Giữ đủ 2–26 lựa chọn, kể cả E; bỏ tiền tố A./B. có sẵn trước khi dựng prompt để tránh lặp. [Mirror VMLU](https://huggingface.co/datasets/tridm/VMLU/tree/main) có JSONL; vẫn cần review original license/revision.
- `adapter=viquad2`: JSON SQuAD `data[].title`, `paragraphs[].context`, `qas[]`; giữ tất cả gold answers và `is_impossible`, không dùng `plausible_answers` làm gold. Tất cả paragraphs/questions cùng document ở một split. [Mirror taidng](https://huggingface.co/datasets/taidng/UIT-ViQuAD2.0/tree/main) hiện dùng Parquet; adapter này **không đọc Parquet**, cần export bản JSON có provenance/hash rồi ghim nó hoặc dùng bản JSON gốc đã review.
- `adapter=canonical`: JSON `{"samples":[...]}` theo `TrainingCorpus` trong [contracts](../backend/app/contracts/training.py). Mỗi mẫu có `task_id`, `group_id`, `domain`, `split`, `messages`, `gold`; tùy chọn `has_rag_context`, `critical`. `gold` chỉ vào judge, không vào generation prompt. Khi đổi bộ chấm/source protocol cần version mới.

Với VMLU/ViQuAD2, split dựa trên hash group: 50% train, 20% calibration, 15% threshold, 15% holdout. Canonical giữ split đã review. Cần ít nhất 4 samples ở mỗi split; train/calibration phải có cả nhãn pass/fail cho từng candidate; grouped OOF cần đủ group ở cả hai lớp. Đây chỉ là sàn kiểm thử phần mềm, không phải sample size đủ cho kết luận nghiên cứu. Review biến thể/near-duplicates và task coverage riêng.

## Distillation và cache

Mỗi mẫu có tối đa 4 calls khi cache trống: generation cho ba model, rồi reference model chấm cả ba output ẩn danh theo rubric `blind-grounded-absolute-80-v1`. Điểm ≥80/100 là qualified cho từng model **độc lập**; không giả định Pro luôn đúng hoặc dùng 80% điểm Pro để coi câu trả lời sai là đạt. Judge prompt chứa gold và output dưới dạng dữ liệu JSON không đáng tin. Self-judging vẫn có bias; cần human calibration và deterministic graders của owner evaluation trước khi qualification.

Mỗi completed generation/judge được ghi cache ngay. Key bao gồm full role-preserving input, model/config fingerprint, bảng giá và rubric. Cache giữ text, provider token counts, measured latency và cost estimate. `cache` chỉ chấm lại cached judge output rồi train; thiếu/malformed cache thì dừng, không tự gọi API. Cache cũ `gemini_eval_cache.json` không chứa đủ schema/provenance để tự chuyển sang cache mới.

Live dùng endpoint tương thích [OpenAI của Gemini](https://ai.google.dev/gemini-api/docs/openai). Calls chạy tuần tự với khoảng cách từ manifest; 4,2 giây là throttle cấu hình, không phải bảo đảm “free tier 15 RPM”. [Quota chính thức](https://ai.google.dev/gemini-api/docs/rate-limits) phụ thuộc project/model/tier, gồm cả token và daily limits. Xác minh trên AI Studio trước khi chạy.

Ledger reserve trước mỗi generation/judge, cộng vào budget của job, user và project; judge cost tách khỏi serving observations dùng train. HTTP timeout/429/usage thiếu không tự retry; dừng job và giữ reservation unresolved để admin đối soát. Output bị cắt nhưng có usage hợp lệ vẫn được settle, không được cache hoặc dùng train. UI báo cả số calls chưa rõ cost. Không suy unknown thành 0. Rerun sau gián đoạn chỉ dùng lại các completed cache entries; calls unresolved không có cache phải đối soát trước khi chủ động chạy một request mới.

## Huấn luyện, kiểm tra và import

Train/calibration/threshold tách biệt; TF-IDF fit từng fold của train. Feature pruning chọn trên train theo impurity importance ≥1%, luôn giữ text score, rồi refit và compile lại indices. Không tuyên bố luôn giữ 10–14 features: số lượng phụ thuộc dữ liệu. Linear mới cũng dùng 14 đặc trưng; runtime giữ hỗ trợ artifact 7/11/14 cũ.

HOLDOUT chỉ được evaluate sau khi đóng băng artifact/threshold. Guardrails phần mềm hiện tại: không mất observed pass rate ở mỗi domain, không critical regression, median latency ratio ≤1,10. Không dùng kết quả HOLDOUT để tự chỉnh ngưỡng hay train lại. Đây là offline replay, chưa gồm đo all-in router/storage overhead và paired uncertainty. Có thể model mới không tốt hơn model cũ hoặc chỉ chọn reference; report không gọi đó là cải thiện đã chứng minh.

Mỗi job lưu `manifest.json`, `dev.json`, `holdout.json`, `artifact.json`, `report.json` dưới thư mục ID riêng. Không ghi đè artifact đang dùng. HOLDOUT fail giữ bản ứng viên để xem nhưng chặn import. Import lưu `imported.json` và đổi model cho **nghiên cứu tiếp theo**, không đổi active chat hoặc frozen snapshots. Manual import kiểm tra lại artifact hash; startup load imported candidate với `live_approved=false`. Xóa/đổi `imported.json` khi backend dừng để rollback lựa chọn nghiên cứu; các phiên bản job vẫn còn.

Gemini artifacts giữ endpoint identity `gemini_chat_completions`; replay/sandbox cho phép endpoint này, production chat hiện chỉ có OpenAI Responses adapter. Router Lab fixtures có model IDs/catalog riêng nên chạy fixture với artifact Gemini sẽ fallback vì mismatch, không được coi là benchmark Gemini. Báo cáo HOLDOUT của training job là nơi kiểm tra candidate Gemini. Việc đưa Gemini vào chat thật cần serving adapter/wiring và qualification riêng; pipeline không tự viết lại catalog/chat settings.

API admin: `GET /v1/research/training`, `GET /latest`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/import`, `GET /jobs/{id}/artifact` (các suffix sau prefix `/v1/research/training`). Dedupe theo owner + request ID + payload; không chạy hai job đồng thời. GET/download/import chỉ owner của job. Restart đánh dấu jobs đang chạy là interrupted; không tự replay paid dispatch.

## Kiểm tra

Backend integration dùng cached synthetic generation/judge, cả chuỗi train/HOLDOUT/import, owner isolation/dedupe, cache miss, source hash, gate live, HOLDOUT fail, adapter transport giả, budget trước dispatch và unresolved timeout. Regression tests kiểm tra legacy linear dimensions, pruning/compiler hiện có, flags CLI, không overwrite, hash pooler ổn định giữa process và throttle/concurrent cache. Không gửi paid API hay tải benchmark thật trong tests.

Kiểm tra local Windows: backend suite 148 tests qua; vòng regression mới nhất sau sửa settlement 32 tests qua, gồm Gemini output bị cắt có usage, HF transport giả và JSONL với lựa chọn E. Ruff, mypy, frontend TypeScript/ESLint, 5 frontend unit tests, production build, generated-contract check và docs check đều qua. Đã xem ảnh giao diện 1440px và 390px ở `output/playwright/router-training-{desktop,mobile}.png`.

Hai UI regression cũ chưa xanh: `compact-experience.spec.ts` đợi `.lazy-models` không có trong landing hiện tại; test `optimizer lab readiness` đăng nhập/mở Lab và đổi router được nhưng đợi tên nút “Chạy kiểm tra”, trong khi giao diện hiện có “⚡ Chạy thử nghiệm hiệu năng”. Không sửa các selector/flow cũ ngoài phạm vi để che lỗi; ảnh và error contexts nằm trong `output/playwright/`. Chưa có bằng chứng chạy Gemini thật hoặc benchmark khoa học qualified.
