# Kết quả triển khai ngày 27/10/2026

Nhánh: `Fix/Huy/router-provider-stability`, từ `origin/develop` tại `c2120ca`.

Cập nhật lượt chạy thật tiếp theo: [kết quả kiểm định ML + Attention](ML_LIVE_QUALIFICATION_20261027.md).
Đã thu thập 400 câu, train cả hai artifact, nhưng chất lượng theo nhóm và độ trễ
chưa đạt; không promote/bật live. Catalog hiện là v5. Các kết quả v4 bên dưới là
ghi nhận của giai đoạn triển khai trước lượt đo thật này.

## Đã triển khai

- Chat ưu tiên model thực sự gọi; trace/Galaxy dùng cùng danh tính. Không vẽ model
  mặc định cũ, không hiển thị số Attention giả khi request chưa chạy Attention.
- Trace tách ML/Attention đã nạp và đã chạy; lỗi provider giữ metadata an toàn,
  thời gian chờ và trạng thái dispatch. Lỗi khóa provider không đăng xuất người dùng.
- Preset và nhập tay dùng chung luồng gửi; mất response giữ nguyên request ID,
  double-click không tạo lần gọi trùng. Preset bộ nhớ có hướng dẫn cung cấp dữ kiện.
- Quota SQLite dùng chung giữa worker/alias/tác vụ, có RPM/RPD/TPM/TPD và Retry-After.
  OpenRouter miễn phí đọc metadata quota (không suy luận) để tính cả lượt từ ứng dụng khác.
- Catalog đang dùng là `smartllm-routing-v4`, sáu profile generation không trùng,
  output reserve 2048. Ba profile OpenAI được cho phép dự phòng trả phí theo lựa
  chọn của người dùng, sau kiểm tra access chỉ đọc; ngân sách hiện có vẫn áp dụng.
  Chấp thuận vận hành này không phải bằng chứng chất lượng benchmark.
- Tối đa hai lần chuyển model cho request tự động. Chế độ chọn trực tiếp giữ model.
  Không tự chuyển sang lần gọi trả phí khác khi lần trước còn chưa rõ kết quả/chi phí.
- `router readiness`, `prepare-catalog`, `qualify`, `provider-limits` và công cụ
  `verify-catalog` dùng đúng endpoint/key của từng provider đã có.
- Migration `h107` đã áp dụng. Bản sao lưu trước migration:
  `data/backups/before-provider-quotas-20261027-66f1f9bc.sqlite3`.
  Catalog trước đổi profile:
  `data/backups/models.before-routing-v4-20261027-8ae1af05.json`.
  Đối chiếu các hàng tài chính trước/sau migration không thấy thay đổi.

## Kiểm thử thực tế

- 82 ca backend liên quan đã qua: quota/worker/alias/reset, credential, qualification,
  hội thoại, ownership, giới hạn dự phòng, lỗi không rõ thanh toán và ngắt SSE.
- 25 ca unit frontend đã qua. Một test local bị ignore trong Git,
  `src/lib/presentation.test.ts`, không có intl provider và thất bại khi chạy tất cả
  file local; không sửa/xóa file có sẵn này. Các test còn lại chạy cùng nhau đã qua.
- Ba ca Chromium mới đã qua: danh tính model + trace, preset mất response rồi thử
  lại cùng ID ở 390px, và lỗi provider giữ đăng nhập/hiện chi tiết.
- Production frontend build, TypeScript frontend, ESLint frontend và kiểm tra khớp
  OpenAPI/TypeScript đã qua. Ruff các file thay đổi đã qua.
  Công cụ sinh contract luôn dùng mock và tắt tải model, độc lập với `.env` live.
- Probe offline chặn mạng: Attention nạp được ONNX INT8, chạy NumPy CPU trên ba
  prompt, mỗi lần có sáu đặc trưng hữu hạn và hai điểm ứng viên hữu hạn. Đây là
  bằng chứng thực thi phần mềm, không phải chứng nhận chất lượng live.
- Kiểm tra model-list chỉ đọc xác nhận access cho các model Groq/OpenAI trong
  catalog; không gửi prompt. Metadata OpenRouter xác nhận quota 50 lượt miễn phí/ngày
  tại thời điểm kiểm tra, nên mức nội bộ 40/ngày được giữ.

## Phần chưa đạt và giới hạn

**ML + Attention chưa được bật cho chat live.** Artifact đang chọn không có Attention,
  chưa qualified và lệch snapshot. Bản Attention khác dùng nhãn giả lập; `router qualify`
  từ chối promotion và không tạo file serving. Cache đo thật của pilot 96 mẫu không
  có trong bản clone này. Docker Compose gắn `/app/data` vào chính thư mục `data`
  của project, không khai báo volume dữ liệu riêng; Docker engine hiện không chạy
  nên chưa thể kiểm tra container cũ. Cần khôi phục/thu thập dữ liệu đúng profile, kiểm định độc
  lập và chạy pilot có ngân sách trước khi bật. `.env` và artifact cũ được giữ nguyên.
  Prompt đơn giản vì vậy vẫn có thể dùng baseline; không có luật giả để ép model nhỏ.

Bộ kiểm tra toàn project **chưa xanh**:

- Lượt full backend đầu có 610/628 ca qua. Ba lỗi luồng baseline/failover/SSE đã
  được sửa và kiểm tra lại trong nhóm 82 ca. Các lỗi còn lại liên quan đến bảo toàn
  phủ định của optimizer, fixture endpoint Gemini cũ, requested sizes của Lab,
  aggregate usage và các test ablation đòi kết quả giả lập từ endpoint đã khóa.
- Mypy toàn backend còn tám lỗi tại `optimizers/strategy.py` và
  `optimizers/llm_compressor.py`, không thuộc phần sửa router/provider này.
- Môi trường Python Windows hiện thiếu package `llmlingua` dù `.env` bật adaptive
  prompt. Cần cài đủ dependency backend trước khi chạy server bằng cấu hình đó;
  kiểm thử đã tắt tính năng này và không chứng minh optimizer adaptive chạy được.
- Lượt chạy browser toàn bộ mới nhất có 4/9 ca qua, gồm cả ba ca regression mới.
  Năm ca cũ còn dùng tên/tab/điều khiển trước đợt đổi UI (Optimized, Tổng quan,
  màn hình nghiên cứu/tài liệu). Không hạ điều kiện kiểm tra để che các thất bại.

Đáng lưu ý khi bàn giao cho owner optimizer: ca `không ít hơn 10` đổi thành
`không nhiều hơn 10` hiện bị validator coi là bảo toàn. Đây là lỗi ngữ nghĩa đã có,
không phải bằng chứng phần tối ưu prompt an toàn. Không chỉnh thuật toán module khác
hoặc tuyên bố toàn project hết lỗi trong đợt sửa này.

## Tài liệu và bằng chứng

- Quy trình triển khai tiếp/rollback: [ROUTER_ACTIVATION.md](ROUTER_ACTIVATION.md).
- Báo cáo trong `output/project-audit/`: `router-readiness-active-20261027.json`,
  `attention-cpu-proof-20261027.json`, `existing-artifact-qualification-20261027.json`.
- Screenshot của regression UI trong `output/playwright/results/router-stability-*`.
  Đây là fixture/mock để kiểm tra giao diện, không phải kết quả gọi model live.

Không có cuộc gọi suy luận trả phí nào được dùng trong kiểm thử.
