# Kiểm thử tích hợp và hiệu năng toàn hệ thống — 27/10/2026

Cập nhật sau: [đã tải và kiểm thử LLMLingua thật](COMPRESSION_REAL_WEIGHTS_20261027.md).
Giới hạn thiếu weights ghi trong báo cáo lịch sử bên dưới đã được xử lý.

Phạm vi là ma trận hữu hạn đại diện cho các biên đầu vào và luồng tích hợp; không
khẳng định đã thử mọi prompt có thể có. Giữ artifact ML + Attention đang được Huy
chấp nhận dùng thử, không thay bằng candidate 95/110.

## Ma trận và cách đo

- Backend: toàn bộ suite, database tạm, chặn mạng ngoài; auth/ownership, 16 tổ hợp
  cờ, lịch sử, tài liệu/RAG/jobs, quota, ledger, fallback, lỗi provider, timeout,
  disconnect, restart, router/training và hợp đồng dữ liệu.
- Ma trận thêm: ngắn/dài/code/hybrid, prompt trắng/quá dài, bảo toàn dấu âm và
  điều kiện so sánh, compressor timeout/busy, lỗi storage, 12 phiên chat đồng thời.
- Browser Chromium: chat, preset, retry cùng ID, model/trace/Galaxy, provider auth
  không đăng xuất, tài liệu/citation/full-text, nghiên cứu giả lập, usage/export,
  quota admin, VI/EN, mobile 390px và logout/expiry.
- Live: HTTP thật qua `frontend:3000/api/v1` tới backend và ledger/provider thật.
  Phiên admin tạm tự hết hạn và bị thu hồi sau lượt audit; không đổi mật khẩu.
  Lưu request trước dispatch, response/trace/progress sau phản hồi; không tự retry
  khi kết quả chưa rõ. Trần 0,01 USD/request, 0,13 USD/vòng, cùng quota/ngân sách hiện có.
- Prompt live: rỗng/trắng/50.001 ký tự; 1+1; phần trăm ngược; số âm Unicode; code;
  đoạn dài có mã cuối; hybrid rewrite/context/memory; hỏi thông tin chưa cung cấp;
  cung cấp dữ kiện rồi hỏi lại; hybrid dài.

Live audit này chứng minh tích hợp và đo thời gian quan sát, không chứng nhận
chất lượng chat mở/code/memory như benchmark nghiên cứu độc lập. RAG/document
provider faults được thử bằng mock có ledger; không gọi embeddings trả phí để
giả lập hỏng provider.

## Lỗi gốc và sửa chữa

### 1. SQLite WAL dùng chung giữa Windows và Docker

Docker bind mount `./data:/app/data` chứa database, trong khi các CLI thu/train
chạy trên Windows cũng mở file đó. Khóa/shared memory/page cache giữa hai môi
trường không phải cấu hình SQLite local một hệ điều hành được hỗ trợ. Sau các
lượt ghi, Docker nhận `unable to open database file`, rồi `database disk image
is malformed`; request chat đầu trả 500 trước dispatch (`dispatched=0`).

Backend đã dừng để tránh ghi tiếp. Snapshot ngay trước audit được xác minh bằng
`PRAGMA integrity_check = ok`, chứa 6 tài khoản và 5.357 usage rows. Snapshot này
được chuyển bằng SQLite backup sang volume Linux `smartllm-runtime-db`, database
`/app/runtime-db/smartllm.db`. File cũ không bị ghi đè; dữ liệu lỗi, bản ghi attempt
audit và log giữ tại `data/backups/system-audit-forensics-20261027/`.

Các ghi mới của lượt audit lỗi chỉ là hội thoại/attempt kiểm thử; attempt lỗi có
`dispatched=0`. Không khẳng định đã cứu nguyên mọi trang bị hỏng. Snapshot trước
audit giữ nguyên lịch sử/ledger có trước đợt này; các dữ liệu thu/train đã hoàn tất
trước snapshot vẫn được giữ. Đây là phục hồi snapshot, không phải sửa in-place file
corrupt rồi tuyên bố dữ liệu nguyên vẹn.

Compose hiện dùng native volume riêng cho DB; assets/uploads/cache vẫn ở thư mục
data. Marker `data/docker-native-storage.json` ngăn Settings live mặc định trên
Windows mở file cũ. Từ đây chạy CLI/live jobs bên trong backend container để dùng
chung một ledger, không chạy Windows CLI trên bản snapshot.

### 2. Healthcheck báo xanh trong khi storage lỗi

Trước sửa, healthcheck chỉ gọi platform-info, không truy vấn database. Đã thêm
`GET /v1/health/ready` đọc các bảng tài khoản, request, reservation và usage. Lỗi
storage trả 503 JSON an toàn. Startup chạy `PRAGMA quick_check` trước nhận traffic.
Lỗi SQLAlchemy thoát khỏi bước ghi lỗi cũng được ánh xạ sang envelope 503; không
tự giải phóng reservation hoặc coi provider call là miễn phí.

### 3. Prompt hybrid dài tải model trong request

LLMLingua lazy-load tải tokenizer/weights từ Hugging Face ngay trong lượt chat đầu.
Request hết deadline 30 giây; `asyncio.to_thread` vẫn tiếp tục tải. Backend ghi
`PROVIDER_TIMEOUT`, `dispatched=0`, chưa gọi model sinh câu trả lời. Proxy cũ đóng
socket trước khi trả JSON cho giao diện.

Đã ghim revision và chỉ tìm model trong cache local. Chuẩn bị asset là tác vụ vận
hành riêng, không còn tự tải trong chat. Bộ tối ưu chỉ được chờ 2 giây; nếu quá hạn
thì giữ prompt gốc. Một semaphore giữ slot tới khi worker thực sự kết thúc, để
timeout/cancel không tạo vô hạn thread nén phía sau. Request khác nhận `llmlingua_busy`
và tiếp tục bằng prompt gốc. Không giả rằng đã áp dụng compression.

Proxy timeout 130 giây lớn hơn deadline tối đa backend 120 giây, để ứng dụng trả
mã lỗi và request ID đúng hợp đồng. Không tăng deadline backend hay ngân sách.

### 4. Validator bảo toàn chưa nhận diện đảo chiều điều kiện

Giữ từ “không” và số 10 chưa đủ: `không ít hơn 10` và `không nhiều hơn 10` trái
nghĩa nhau. Validator nay trả `unknown` khi cụm giới hạn thay đổi, khiến optimizer
giữ nguyên prompt. Literal số có bảo vệ cả dấu `-`, `−`, `–` để không coi `−524`
và `524` là tương đương. Đây là kiểm tra cụ thể, không phải chứng nhận mọi biến
đổi ngữ nghĩa đều được phát hiện.

### 5. Tổng token bị trình bày như đầy đủ khi thiếu usage

Analytics trước đó cộng các token đã biết dù một số call còn unknown. Nay tổng
input/output là null nếu có call thiếu giá trị tương ứng; known USD subtotal và
số unknown calls vẫn được giữ riêng. Không điền 0 vào số đo chưa biết.

### 6. Kiểm thử và image frontend bị lệch cấu hình

- Fixture backend vô tình nạp artifact live từ `.env` cho mỗi app test; đã tách
  artifact test sang đường dẫn tạm. Các kiểm thử ML chuyên biệt vẫn nạp fixture
  của chính chúng. Không dùng mặc định live để chứng minh kiểm thử mock.
- Fixture provider Gemini cũ được chuyển sang endpoint generation hỗ trợ và
  fake transport, vẫn kiểm tra settlement/timeout/dispatch fence/ngân sách tích lũy.
- Test ablation cũ đòi số liệu giả lập cố định được sửa thành kiểm tra API từ chối
  khi chưa có paired runner qualified; không bật endpoint giả để làm test xanh.
- Kiểm thử render frontend bổ sung intl provider, không bỏ assertion nội dung/XSS.
- Các selector browser cập nhật theo UI hiện tại, giữ xác nhận request ID, history,
  citation, quota, quyền truy cập và xóa dữ liệu riêng tư sau logout.
- Image frontend cập nhật từng lớp thiếu `postcss.config.mjs`, khiến `@theme` bị
  bỏ qua. Đã đưa cấu hình vào build; production build sau đó không còn warning đó.
- Nút Trace thêm tên truy cập bằng ngôn ngữ hiện tại.

## Điểm nghẽn quan sát trước sửa

Các số sau từ HTTP qua proxy trên máy này, không phải SLO hoặc bảo đảm tải production:

| Prompt | HTTP | Prepare | Route | Generate và commit |
|---|---:|---:|---:|---:|
| Ngắn dễ, lần đầu | 5.880 ms | 514 ms | 283 ms | 4.889 ms |
| Phần trăm ngược | 6.554 ms | 123 ms | 38 ms | 6.309 ms |
| Số âm | 2.708 ms | 85 ms | 36 ms | 2.524 ms |
| Code | 23.629 ms | 108 ms | 45 ms | 23.386 ms |
| Ngữ cảnh dài | 2.901 ms | 109 ms | 194 ms | 2.485 ms |
| Hybrid vừa | 1.908 ms | 127 ms | 101 ms | 1.619 ms |
| Nhớ lại dữ kiện | 3.949 ms | 377 ms | 161 ms | 3.246 ms |
| Hybrid dài cold compressor | Timeout | Tải model trong request | Chưa tới | Không dispatch |

Generate thường chiếm phần lớn thời gian; code dài có thời gian provider lớn.
Cold ML/encoder cao hơn warm route. CPU nén có thể trở thành bottleneck khi tải
đầu tiên hoặc nhiều request; đã chặn thời gian chờ/worker. SQLite native vẫn là
single-writer; WAL không biến thành hệ nhiều writer không giới hạn.

## Bằng chứng

- `output/project-audit/system-backend-before.xml`: 712 passed / 16 failed trước sửa.
- `output/project-audit/system-fixes-targeted-v2.xml`: 43 passed sau sửa nhóm lỗi.
- `output/project-audit/system-matrix-mock.xml`: ma trận bổ sung và lỗi storage.
- `output/project-audit/system-concurrency-mock-20261027.json`: 12 phiên, 12 lượt
  thành công, 12 cặp message commit. p50 khoảng 2.871 ms, p95 nearest-rank khoảng
  3.079 ms khi chạy cùng các tác vụ build/test khác; mock, không suy throughput provider.
- `output/project-audit/system-frontend-before.json`, `system-frontend-after.json`.
- `data/system-audit/live-native-before-20261027/`: request, response, trace, tiến độ
  trước sửa compressor; 9 lượt thành công + 3 input bị từ chối đúng; hybrid dài
  timeout trước dispatch. Chi phí catalog đã biết 0,001763082 USD.
- `output/project-audit/system-final-20261027.json`: tổng hợp kết quả thật.
- `output/project-audit/system-backend-after.xml`: 745 ca backend đạt.
- `output/project-audit/system-module-tests.xml`: 53 ca optimizer/memory cạnh source đạt.
- `output/project-audit/system-lazy-compressor.xml`: ca thiếu weights không tải mạng,
  không import bộ nén nặng đạt; thêm ngoài 12 ca matrix đã chạy.
- `output/project-audit/system-frontend-final.json`: 27 ca frontend unit đạt.
- `output/project-audit/system-browser-after.json`: 9/9 kịch bản Chromium đạt.
- `data/system-audit/live-after-ready-20261027/`: đủ 13 kết quả đúng trạng thái,
  gồm 10 lượt trả lời và 3 đầu vào bị từ chối đúng. Cả 10 lượt trả lời đều thực sự
  chạy ML và Attention; model response/trace thống nhất, retry cùng ID không gọi trùng.

## Kết quả sau sửa và giới hạn còn lại

Trung vị 10 lượt live trả lời là **3,22 giây**; ca code lâu nhất **19,35 giây**,
phần lớn thời gian ở provider. Hybrid dài trước sửa timeout trước dispatch, sau
sửa trả lời đúng mã BLUE-851 trong **3,04 giây**. Đây là hai lượt quan sát tại máy
này, không phải benchmark tốc độ có kiểm soát hoặc cam kết production.

Chi phí live đã biết của hai vòng là **0,003491289 USD**, theo catalog ước tính.
Không có dispatch provider chưa xác định mới trong đợt audit; giữ các khoản dự
phòng cũ. Typecheck/lint frontend, kiểm tra hợp đồng OpenAPI/TS, mypy 7 file
production bị ảnh hưởng và production build đều đạt. Không suy ra toàn project
mypy sạch từ kiểm tra phạm vi đó.

LLMLingua chưa có đủ weights cục bộ: hệ thống bỏ qua nén và giữ nguyên prompt.
Đã giới hạn chờ 2 giây, tối đa một worker nén và trì hoãn import thư viện nặng tới
khi kiểm tra assets xong. Không coi trạng thái bỏ qua là đã nén thành công.
ML + Attention đang chạy artifact thử nghiệm được Huy chấp nhận; kết quả smoke
này không thay thế qualification độc lập cho chat mở, code, memory hoặc RAG.

Database sau audit có `integrity_check = ok`; bản sao nhất quán lưu tại
`data/backups/system-audit-native-final-20261027.sqlite3`. Khi vận hành, chạy CLI
qua `docker compose exec backend python -m app.cli ...` để dùng ledger hiện tại.
Backup bằng SQLite backup bên trong container; không copy bộ file WAL đang ghi
qua Windows và không dùng `docker compose down -v` để khởi động lại dịch vụ.
