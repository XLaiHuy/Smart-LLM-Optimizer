# Bàn giao — Lab thống nhất và tiến trình chat (22/10/2026)

## Đã triển khai

- Một trang thử nghiệm: chọn module → chạy preflight/tạo run bằng một nút → theo dõi/lịch sử → xem tình huống/tải kết quả. Default simulation suite V2 ba model, seed 42, một lần lặp; các thuật toán chuyên sâu đặt trong Tùy chọn. Tắt Router chỉ chạy reference. Module chưa có vẫn khóa; không mở ablation/quality/savings bằng fixtures.
- Bỏ trang Router Lab nâng cao lồng trong flex gây lệch phải; các phần dùng cùng chiều rộng, bảng cuộn trong panel. Feature importance/raw trace thu gọn.
- ProgressSink + processing_events + owned APIs. Trạng thái được phát từ Orchestrator, tool errors đánh failed; commit/fail/restart đóng bước đang chạy. Không chứa input/output riêng tư. SessionDetail có active_client_request_id để reload theo dõi, không tự POST lại. Dedupe/history/accounting giữ nguyên.
- Chat chỉ một dòng trạng thái với spinner khi xử lý; popup xem lại ≤340 px, theo bước mới, không sticky. Đóng bằng Escape/outside/trigger khuất. Khi xong, nút ở góc phải dưới trả lời; model/token/USD/thời gian vẫn hiện. Bỏ Chi tiết tối ưu và journey danh sách. Nonstreaming giữ nguyên; spinner không là phần trăm hay reasoning nội bộ.
- Landing tải một lần, nhưng ẩn/hiện lại theo viewport cả hai hướng; không unmount/refetch, không ẩn keyboard focus; reduced motion giữ nội dung hiện ổn định.
- [B3/PoF](B3_READINESS.md), [metadata dependency](THIRD_PARTY_INVENTORY.json), CHANGELOG và footer source/Issues. Chưa xác nhận quyền công bố logo, tính tương thích mọi giấy phép hoặc điểm PoF.

## Setup và tương thích

Từ repo root: backup DB, activate venv rồi `npm run db:migrate` (`f105` additive sau `e104`), sau đó `npm run dev`. Không reset account/history hoặc env. Chạy `npm run contracts:generate` nếu sửa DTO; `npm run contracts:check` kiểm tra drift. API progress scoped owner; admin không được đọc conversation của người khác. Lượt cũ không có events báo chưa có lịch sử, không dựng lại tiến độ giả.

## Kiểm tra và giới hạn

Bằng chứng kiểm tra cuối đợt được ghi bổ sung sau khi chạy checks. Không tính ảnh/fixtures là kết quả live. Không tạo release/push hoặc sửa thiết lập GitHub. Clean clone trên máy mới, Linux/remote CI, PoF và paid pilot phải kiểm tra riêng. Cấu hình live giữ tắt; không gọi provider network trong tests.


## Bằng chứng kiểm tra tại Windows (22/10/2026)

- Backend: **5 passed** — ba test trong `test_progress.py`, regression tool accounting/history/isolation/purge và rollback history. Kiểm tra progress khi provider fake đang bị giữ, đọc từ principal khác, dedupe không sinh thêm calls/events, failed/interrupted không replay, migration từ `e104` giữ account.
- Frontend unit: **3 passed** trong `format.test.ts` — unknown khác zero, baseline flags, parity VI/EN gồm Processing/steps/Research.
- Chromium: **một luồng smoke đã đạt**, được chạy lại sau sửa vị trí popup. Kiểm tra landing reveal → ẩn → reveal mà không unmount, reduced motion, một nút chạy simulation, hai module khóa, kết quả và export, căn lề/không tràn tại 390/768/1440 px, chat tools, popup xem lại, Escape/focus, đóng khi trigger ra khỏi viewport, reload và VI/EN. Fake transport giữ response chỉ trong test; không thêm độ trễ trình diễn vào app.
- Ảnh Lab desktop/mobile và popup được xem trực quan. Lần kiểm tra ảnh đầu phát hiện popup bị composer che; đã sửa theo viewport vùng chat và thêm assertion chiều cao/vị trí. Ảnh cuối cho thấy popup mở phía trên và không che bởi composer. Artifacts ở ignored `output/playwright/results/compact-experience-compact-a72cc--lab-and-processing-popover-chromium/`.
- Ruff và mypy 70 app files đạt; ESLint/frontend typecheck, OpenAPI/TypeScript drift và docs checks đạt. Production build cuối các routes /, /dashboard, /research, /research-guide và not-found đã đạt sau sửa popup; Prettier các file thay đổi đạt.
- DB dev được backup tại ignored `data/backups/before-f105-20261022-003430.db`, nâng lên `f105`. Counts trước/sau giữ **3 users, 2 messages, 7 attempts**. Không thay password/quota/env/live gate.

Không chạy full suites theo yêu cầu kiểm thử gọn. Chưa có bằng chứng paid/live, qualification ba module, clean clone máy mới, Linux/remote CI hoặc điểm PoF chính thức. Unit tests không phải bằng chứng chất lượng mô hình. Không push hoặc tạo release trong đợt này.
