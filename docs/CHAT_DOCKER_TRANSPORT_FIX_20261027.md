# Lỗi chat dài qua Docker proxy — 27/10/2026

## Bằng chứng và nguyên nhân

Hội thoại `052f95dc-31b9-4771-9cf2-27ea985a6b27`:

| Request | Backend | Thời gian | Kết quả kế toán |
|---|---|---:|---|
| 6537f79a-a0f9-4189-89dc-bb5bf66ed788 — toán ngắn | succeeded | 8,166 s | 0,000085350 USD estimated |
| 0b8aca48-038a-4c34-a221-8cf3bd266dba — QuickSort | succeeded, đã commit | 39,634 s | 0,000766950 USD estimated |
| c9a30608-7139-4531-a280-96574a1edf85 — VAE | PROVIDER_TIMEOUT | deadline 60 s | dispatch/cost unknown, giữ reservation |

Cả ba request đều đi qua ML + Attention và chọn GPT-OSS 120B; không có 429 trong các lần gọi này. QuickSort có 3.858 ký tự trả lời và 1.172 output token, đã được lưu trước khi điều tra.

Dockerfile frontend cũ chỉ copy `.next`, dependencies và assets, không mang cấu hình runtime. `required-server-files.json` có `proxyTimeout=130000`, nhưng gọi trực tiếp `loadConfig('phase-production-server','/app')` trong container trả về timeout không được cấu hình. Next.js dùng mặc định 30.000 ms. Log frontend có `Failed to proxy ... socket hang up / ECONNRESET`. Vì vậy lỗi truyền tải xảy ra trước khi request QuickSort hoàn thành. VAE còn có lỗi độc lập: frontend đặt deadline 60.000 ms, backend hủy provider khi hết hạn, không có kết quả usage/cost hoàn chỉnh.

Giao diện trước đây biến HTTP 500 không có envelope thành UNKNOWN, xóa pending request và không đọc lại kết quả; vì vậy kết quả đã commit không được khôi phục.

## Sửa

- Thêm `next.runtime.config.mjs`: runtime đọc đúng timeout từ metadata build. Cả Dockerfile cài mới và runtime-update đều copy thành `/app/next.config.mjs`.
- Chat đặt deadline 120.000 ms trong trần backend hiện có; proxy 130.000 ms. Timeout riêng của provider vẫn được giữ. Không đổi output profile, catalog, artifact, ngưỡng ML hoặc ngân sách.
- Khi transport lỗi: giữ client_request_id, chỉ GET progress/trace/execution để khôi phục. Thành công thì tải câu trả lời đã lưu; thất bại thì hiển thị error_code và request ID thực. Không tự POST hoặc paid fallback.
- Thông báo timeout và mất kết nối rõ ràng bằng VI/EN; vẫn giữ prompt khi request thật sự thất bại.
- Lần VAE giữ reservation unresolved 0,00230895 USD, không được gọi lại hoặc coi là miễn phí. Không thu thêm data hoặc paid API để kiểm tra bản sửa.

## Kiểm thử

- Unit frontend: 30 passed, gồm recovery thành công, timeout, pending, lỗi đọc trạng thái và không POST.
- TypeScript và ESLint: passed.
- Browser E2E: 10 passed, gồm khôi phục GET không POST trùng và proxy 500 khôi phục đúng lỗi backend.
- Docker production riêng: response 200 sau 38,100 s với upstream delay 36 s; timeout JSON 504 sau 32,008 s với upstream delay 32 s. Cả hai vượt mốc 30 s cũ và giữ đúng JSON. Runtime đã đo lại: 130.000 ms.
- Bằng chứng: `output/project-audit/docker-chat-transport-20261027.json`, `output/project-audit/chat-docker-transport-fix-20261027.json`, `output/playwright/report/`.
- Backend không thay đổi trong bản sửa này; không migration mới.

## Triển khai

Đã triển khai frontend `chat-transport-verified` (image SHA `862475d852fd4027b81c2d2e15d0c30623151991c4c8c50b38fea2c99b798a5d`). Runtime live đo được 130.000 ms, trang chủ HTTP 200 và backend healthy. GET qua frontend xác nhận câu trả lời QuickSort 3.858 ký tự còn nguyên; execution VAE vẫn PROVIDER_TIMEOUT/dispatch unknown. Không phát sinh provider call mới. Không restart backend hoặc thay database.
