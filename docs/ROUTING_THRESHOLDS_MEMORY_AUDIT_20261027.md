# Ngưỡng routing, toán và memory dài — 27/10/2026

## Vì sao câu dễ vẫn vào 120B?

Router hiện có 2 head ML: GPT OSS 20B và GPT-6 Luna; reference là GPT OSS 120B.
Điểm head là ước lượng khả năng đạt của candidate theo dữ liệu đã học, không phải
độ khó toán học thực của câu. Không được gán sáu đầu ra Attention thành sáu năng
lực đã được chứng nhận. Bộ hiện tại được đo chủ yếu ở toán/MCQ, chưa calibration
đầy đủ cho lời chào, chat mở, code hay memory. Dữ liệu và độ tin cậy còn thiếu
khiến router thận trọng, không đồng nghĩa model nhỏ không giải nổi 1+1.

Ví dụ 1+1: 20B score 0,8618 < 0,9229; Luna 0,377 < 0,9 → 120B. Đây là
`ROUTE_ML_RESEARCH_REFERENCE`, không phải ML chưa load/chưa chạy.

## Thử hạ ngưỡng trên DEV, không đọc HOLDOUT

Script `scripts/audit_routing_thresholds.py`, dùng **73 câu split threshold** trong
DEV, có phản hồi thật đã thu. Không train lại, không đổi serving, không trả phí.
Khóa tiêu chí: không giảm tổng/per-domain số đúng và không tăng regression so
với policy hiện tại. Bản fine là vòng DEV tiếp tục hiệu chỉnh, không phải test mới.

Luna giữ ngưỡng 0,9 trong bảng sau:

| Ngưỡng 20B | Chọn 20B / Luna / 120B | Đúng / 73 | Baseline đúng nhưng route sai | Chi phí cache quan sát USD |
|---|---|---:|---:|---:|
| Hiện tại 0,9229 | 4 / 5 / 64 | 63 | 0 | 0,004459468 |
| 0,92 | 4 / 5 / 64 | 63 | 0 | 0,004459468 |
| 0,915 | 7 / 5 / 61 | 62 | 1 | Xem JSON |
| 0,91 | 10 / 5 / 58 | 62 | 1 | Xem JSON |
| 0,90 | 22 / 2 / 49 | 62 | 2 | 0,003404478 |
| 0,85 | 33 / 1 / 39 | 61 | 3 | 0,002895538 |

Các regression mới trong bảng xuất hiện ở MCQ tiếng Việt. Nhóm math 39 câu giữ
37 đúng, nhưng không được dùng nhãn domain evaluator làm classifier phục vụ.
Không triển khai hạ ngưỡng riêng cho 'math' khi chưa có bộ nhận diện serving và
kiểm định tương ứng. Giữ ngưỡng hiện tại: 0,92 không tạo thêm coverage, còn thấp
hơn không đạt tiêu chí DEV. Kết quả DEV không chứng minh non-inferiority trên
population; HOLDOUT cũ đã được xem trước đây không dùng để tune hay cấp chứng nhận.

## Prompt kích hoạt model: có cả dry run và live

Trên context mới, không history; thay context/cấu hình có thể đổi lựa chọn.

| Prompt | Auto hiện tại | Nếu cả hai threshold = 0,85 |
|---|---|---|
| 1+1 bằng mấy? Chỉ trả lời một từ. | 120B | 20B — chỉ dry run |
| Xin chào! | 120B | Luna — chỉ dry run |
| Thủ đô của Việt Nam là thành phố nào? Chỉ trả lời tên. | 120B | Luna — chỉ dry run |
| Tính (−313)+(−211). Chỉ trả lời kết quả. | 20B, đã chạy live đúng −524 | 20B |
| Viết hàm Python tìm phần tử xuất hiện nhiều nhất, hòa chọn phần tử đầu tiên. | 120B | 20B — chất lượng code chưa chứng nhận |
| Giải thích ELBO trong VAE. | 120B | 20B — chưa chứng nhận câu trả lời |

Prompt Luna đã chạy live hai vòng:

> Số nào trong các số sau đây là bội của cả 2, 3, 5 và 9?
> A. 4 536 — B. 3 240 — C. 9 805 — D. 12 065
> Chỉ trả lời một chữ cái trong các lựa chọn.

20B score 0,9067 không qua 0,9229; Luna score 0,9169 qua 0,9 → Luna trả **B**.
Sau sửa: 2,23 giây, 71 input / 4 output, 0,0000091 USD catalog estimated.
20B: score 0,9314 qua ngưỡng, 1,76 giây, 85 input / 27 output,
0,000003960 USD estimated cho câu số âm. Đây là route ML thật, không manual pin.

### Groq, free và GPT-6.1 Sol

Metadata checks không gọi generation: Groq `/models` trả **403**; chưa xác định
đây là lỗi key, quyền, mạng hay account, không suy 'hết quota ngày' từ 403.
OpenAI `/models` trả 200 và có `gpt-6-luna`, `gpt-6.1-sol`. OpenRouter `/models`
trả 200 và có các ID `:free`; danh sách public không chứng minh key được generation.

Artifact/dataset v2 hiện cố định 2 candidate + reference; catalog chat hiện chỉ
có ba generation profile được thu/đánh giá trên. **Không có prompt ML nào chọn
Groq/free/Sol trong cấu hình này**, dù đổi threshold. Không thêm profile bằng
cách gắn cờ qualified hoặc giả nhãn. Để mở rộng cần profile/giá/capability/quota
được xác minh, data đo trên cùng prompt và artifact hỗ trợ thêm candidate/head,
calibration/DEV/test độc lập. Fallback theo provider là cơ chế khác với ML chọn.
Luna đã có fallback approved, vẫn phải qua quota/budget/context và trạng thái
dispatch; không có paid retry nếu lần trước chưa rõ.

## Kiểm thử thật bằng tài khoản sạch

Mỗi vòng tạo hai tài khoản audit riêng, password ngẫu nhiên, auth tạm được thu
hồi cuối vòng; không in/lưu token. Giữ account/ledger để đối soát, không xóa số
liệu chi phí hoặc memory thật của Huy. Trần **0,13 USD/vòng**, **0,01/request**;
các lượt đều qua frontend proxy/backend/ledger/provider đang chạy.

Mỗi vòng **34 lượt**, bao gồm:

- Chưa có dữ kiện: nói rõ chưa biết, không nhầm Huy/SmartLLM Router vào user mới.
- 3 lần bài 8722 giảm 2%, hai bài phần trăm khác, kích hoạt 20B và Luna: 7/7 đáp án
  số/chữ cái đúng trong cả hai vòng. Ba lần 8722 mới đúng không xóa lần 8899 sai cũ.
- Hội thoại **24 lượt, 48 message commit**, khoảng **35.079 ký tự user input**.
  Cung cấp tên/ngành/trường/đề tài/deadline; chen các đoạn dài; sửa deadline lượt 12;
  hỏi lại tại 6/18/24 và trong session mới.
- User B chưa có dữ kiện không biết dữ kiện của A; đọc session A trả **404**.

### Root cause memory và sửa

Trước sửa, regex deadline có từ nối `là/is` tùy chọn. Câu hỏi 'hạn chót mới nhất'
bị ghi thành giá trị deadline 'mới nhất'. Dữ kiện có sẵn bị ghi đè bằng câu hỏi.
Trong session cũ, model vẫn thấy ngày qua raw history; session mới chỉ nhận fact
sai nên hỏi xác nhận lại ngày. Đây là lỗi phần mềm, không phải hết token/API.

Đã bắt buộc câu khai báo có từ nối hoặc dấu `:`, loại câu nghi vấn và xử lý label
lặp trong câu sửa deadline. Test chống biến câu hỏi name/major/school/deadline
thành fact. Không viết đè memory revision lịch sử hay giả vờ đã sửa dữ liệu cũ;
evidence trước sửa giữ nguyên. Vòng mới dùng account sạch chứng minh lỗi không tái tạo.

Tên 'An Khang' có lúc được trả bằng narrow no-break space; grader v1 báo fail giả.
Grader v2 chuẩn hóa Unicode whitespace. Điểm 18/24 trước sửa thực ra đủ năm dữ kiện;
lỗi thật là cross-session deadline. Không thay response gốc để làm PASS.

Sau sửa: đủ cả năm dữ kiện tại **6/18/24 và session mới**, deadline mới 25/11/2026.
34/34 HTTP thành công; 7/7 exact answers và 27/27 kiểm tra literal/isolation đạt.
Phân bố model: **120B 30 lượt / 20B 3 lượt / Luna 1 lượt**; không đổi threshold.
p50 34 lượt khoảng **3,29 giây**; recall session mới khoảng **12,98 giây**.
Không khẳng định đã chứng nhận hội thoại vô hạn hoặc mọi dạng memory.

### Root cause/bottleneck SQL và sửa

`load_user_memories` trước đây SELECT từng session rồi SELECT revision từng cái:
**1+N query**. Nay dùng window function chọn latest revision đã commit của từng
session trong **một query**, lọc owner/excluded session trước ranking. Test đo query
và có dữ liệu foreign/future revision; chỉ phiên đúng owner và revision hợp lệ được trả.
Worker nền có SQL riêng, không tính nhầm vào số query memory.

### Toán sai: chặn trong phạm vi kiểm tra được

Thêm `core/numeric_validation.py` kiểm tra các template số học rõ ràng: phần trăm
ngược/thuận và biểu thức đơn giản yêu cầu chỉ trả số, kết quả nguyên. Dùng Decimal
và calculator AST allowlist đã có; không suy công thức từ bài toán tùy ý hoặc gold.
Sai số nguyên → `OUTPUT_INVALID`, không commit câu sai, không tự gọi paid fallback.
Billing/call records của lần đã hoàn tất vẫn giữ nguyên. Không thay câu sai bằng
đáp án bịa là model đã trả. Ngoài grammar/kết quả phân số/rounding không rõ → unknown.

## Chi phí, kiểm thử và vận hành

Hai vòng known estimated: **0,012525610 + 0,011462023 = 0,023987633 USD**.
Không dispatch unknown mới; giữ nguyên các khoản dự phòng cũ và budget project.
Backup nhất quán: `data/backups/after-routing-memory-math-20261027.sqlite3`;
source và backup integrity check đều `ok`.

- Full backend/source tests: **830 passed**, 243,43 giây.
- Sau siết so sánh số nguyên chính xác: **15 tests guard passed**; không dùng
  relative tolerance có thể làm lọt chênh một đơn vị ở số lớn.
- Ruff, mypy 4 production files, diff check đạt. Không paid API trong tests/CI.
- Các sửa đã đưa vào backend; ngưỡng/artifact/catalog không đổi.

Bằng chứng:

- `data/system-audit/routing-threshold-dev-fine-20261027.json`.
- `data/system-audit/fresh-memory-math-long-20261027/` — trước sửa.
- `data/system-audit/fresh-memory-math-long-fixed-20261027/` — sau sửa.
- `output/project-audit/routing-memory-math-full-20261027.xml`.
- `output/project-audit/numeric-exact-guard-20261027.xml`.
- `output/project-audit/memory-single-query-20261027.xml`.

Giới hạn còn lại: baseline đôi khi sai; code/open chat chưa qualification; ngưỡng
hạ toàn cục làm giảm quality; Groq đang 403; thêm model cần thêm bằng chứng/head.
Nén CPU, provider reasoning/output và recall dài vẫn có overhead; 24 lượt/1 hội
thoại synthetic không là chứng nhận nghiên cứu memory hoặc SLO production.
