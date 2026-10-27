# Đo thật để quyết định bật ML + Attention

Lượt này chạy theo yêu cầu của Huy: tự thu thập, huấn luyện, kiểm định rồi bật nếu
đạt. Đây là hoạt động đánh giá live có ngân sách, tách khỏi tests/CI dùng provider giả.

## Cấu hình và dữ liệu đóng băng

- Catalog `smartllm-routing-v5`: GPT OSS 120B làm reference, GPT OSS 20B và GPT-6
  Luna là hai ứng viên. Giới hạn đầu ra 2048, GPT OSS dùng reasoning `low`.
- Lượt gọi thử phát hiện OpenAI Chat Completions bị 400 khi gửi `max_tokens`.
  Adapter đã dùng `max_completion_tokens` cho OpenAI native và gửi đúng reasoning
  effort trong catalog cho cả đường generate/stream. Không tự đổi model sau lỗi này.
- Gói thăm dò 48 câu GSM8K: 144 lần gọi, 0,005597625 USD theo catalog. Dừng huấn
  luyện vì chưa đủ nhãn đúng/sai trong từng split. Không promote.
- Gói kiểm định tiếp theo: 400 nhóm nguồn, gồm 200 câu toán GSM8K và 200 câu trắc
  nghiệm tiếng Việt chuyển thể từ Aya. 120 TRAIN, 40 CALIBRATION, 40 THRESHOLD,
  200 HOLDOUT (100 mỗi nhóm). Loại các nhóm của gói thăm dò trước.
- Đáp án số và chữ cái lấy từ dữ liệu gốc; không đặt nhãn model đúng/sai theo tên
  hoặc độ lớn model. Bộ chấm deterministic ghi phiên bản và hash response.
- Hai nguồn đã được đối chiếu với file Parquet gốc và SHA-256 ở revision lưu sẵn.
  Nguồn: [GSM8K](https://github.com/openai/grade-school-math/blob/master/LICENSE),
  [Aya](https://huggingface.co/datasets/CohereLabs/aya_dataset).
- Đây là protocol MCQ chuyển thể, không phải điểm benchmark Aya chính thức. Chưa
  chứng nhận code, viết mở, RAG hoặc bộ nhớ nhiều lượt; độc lập theo họ paraphrase
  ngoài khớp nội dung chuẩn hóa cũng chưa được chứng minh.

## Vận hành

Job thăm dò: `37aa8281-8e01-46b0-b5f5-9f1473c7fa9f`.

Job kiểm định: `55d52e80-6646-45e7-ba0b-477a8d39a93b`.

Mỗi job có trần 1 USD, vẫn chịu quota tài khoản và project; không tăng hạn mức.
Tất cả lượt gọi qua ledger và bộ quota chung của chat. Sau 260 câu, quota nội bộ
từ chối trước dispatch, yêu cầu chờ 2 giây. Job được tiếp tục bằng cùng ID/ngân
sách/cache; không có phí không rõ và không gọi lại các phản hồi đã lưu.

Hai artifact đã được train offline trên 200 mẫu DEV, đóng băng trước khi xem điểm
HOLDOUT. Attention có sáu đặc trưng hữu hạn và chạy được NumPy CPU trên ba prompt.
Đây mới là bằng chứng thực thi phần mềm; quyết định bật cần kết quả độc lập phía dưới.

Snapshot giá dùng cùng giá catalog tại training/readiness/chat. Giá bảo thủ dùng
để dự phòng ngân sách được giữ riêng, tránh lỗi sai hash vì trộn giá cache-write
vào giá input của ML. Không gán giá zero cho API chỉ vì có free quota.

## Tái hiện

Từ repo root với Python của `.venv`, lệnh dưới có thể tiêu API và chỉ dùng khi đã
được phép chạy live. Resume giữ nguyên job/budget; không tạo job mới để né quota.

```powershell
python scripts/run_router_pilot.py --owner admin --manifest data/router-live-qualification-20261027/final-gold-v5/manifest.json --directory data/router-live-qualification-20261027/final-gold-v5/runs --live --resume 55d52e80-6646-45e7-ba0b-477a8d39a93b --phase full --batches 16
```

Bằng chứng giữ ở `data/router-live-qualification-20261027/`, không commit phản hồi
và dữ liệu bên thứ ba. Báo cáo holdout của job nằm trong thư mục `runs/<job-id>`.

## Kết quả và quyết định

Đã hoàn thành 400/400 câu, 1.200 phản hồi đo thật. Có thêm một lần admission bị
quota chặn trước dispatch. Chi phí gói này ước tính **0,041275675 USD**; tổng cả
gọi thử và gói thăm dò là **0,046955800 USD**. Không có reservation chưa rõ chi phí.

| Trên 200 câu HOLDOUT | Reference cố định | ML không Attention | ML + Attention |
|---|---:|---:|---:|
| Đúng theo đáp án gốc | 162/200 (81%) | 166/200 (83%) | 163/200 (81,5%) |
| Chi phí phản hồi được chọn, USD | 0,01270665 | 0,008653675 | 0,010729 |
| Tỷ lệ p50 gồm thời gian router cục bộ | 1,000 | 1,096 | 1,120 |
| Câu reference đúng nhưng policy sai | — | 7 | 6 |

Chi phí trong bảng là replay phản hồi đã đo, không phải ba serving run độc lập.
Độ trễ gồm provider và router CPU, chưa gồm HTTP/DB/browser E2E. Không suy ra TTFT.

| Nhóm HOLDOUT | Reference đúng | ML + Attention đúng | Regression gộp | Cận trên 95% regression |
|---|---:|---:|---:|---:|
| Toán | 95/100 | 90/100 | 5/100 | 10,23% |
| Trắc nghiệm tiếng Việt | 67/100 | 73/100 | 1/100 | 4,66% |

**Quyết định: không bật ML live.** Cả hai nhóm không đạt cận regression tối đa
3% đã khóa. Nhóm toán giảm ròng 5 điểm phần trăm; điểm chung tăng không che được
regression này. Tỷ lệ độ trễ 1,120 vượt giới hạn 1,10; Attention chưa chứng minh
lợi ích so với ML không Attention. Chênh lệch pass-rate Attention trừ ML là −1,5
điểm phần trăm, bootstrap 95% [−5,5; +3,0]; chưa chứng minh khác biệt chắc chắn.

`router qualify` đã từ chối promotion. Hai file serving/review v5 **không được tạo**,
`.env` không đổi và server live không được khởi động lại. Chưa chạy pilot E2E
trả phí vì frozen HOLDOUT đã không đạt; các mã lỗi E2E trong báo cáo qualification
biểu thị **thiếu bằng chứng**, không phải một lần đo E2E đã diễn ra rồi thất bại.

Attention đã chạy trên artifact huấn luyện thật, không chỉ bật flag. Bằng chứng:
`attention-execution-proof.json`; sáu regression nằm ở `regression-cases.json`.
Báo cáo qualification: `output/project-audit/live-qualification-v5-20261027.json`.

## Root cause và hướng cải thiện tiếp theo

- Gate live hiện chặn đúng: bản router mới tổng quát hóa chưa đủ tốt. Đây không
  còn đơn thuần là lỗi chưa chọn đúng file artifact hoặc chưa bật công tắc.
- Ngưỡng học trên 40 câu THRESHOLD đạt điểm quan sát nhưng không giữ được chất
  lượng toán trên 100 câu chưa thấy. Cần tăng dữ liệu DEV độc lập và kiểm định
  lựa chọn ngưỡng trên nhiều fold; không sửa ngưỡng theo 200 câu HOLDOUT đã xem.
- Attention thêm khoảng 49 ms p50 CPU cho đo toàn candidate/feasibility, so với
  khoảng 9 ms ở ML không Attention. Cần đo từng bước encoder/attention/GBDT và
  tối ưu không đổi semantics, thay vì mặc định thêm Attention sẽ nhanh hơn.
- Training, replay và serving phải dùng một hàm chọn route duy nhất. Thứ tự
  candidate cần theo chi phí dự phòng của request và cấu hình endpoint thực tế;
  kiểm chứng lại sau các sửa này bằng HOLDOUT mới.
- Chưa có dữ liệu đạt chuẩn cho code, viết mở, RAG và bộ nhớ. Hai nhóm trong lượt
  này không đủ chứng nhận bật router cho mọi prompt. Giữ baseline ở phạm vi thiếu
  bằng chứng; chuẩn bị protocol/gold phù hợp trước khi mở rộng.

35 kiểm thử offline liên quan đã qua; trước đó 59 ca backend có chat/failover đã
qua sau sửa snapshot giá. Ruff, kiểm tra kiểu các module thay đổi và đối chiếu
OpenAPI/TypeScript đã qua. Các ca này không tiêu API suy luận.

Bộ duyệt tự động từ chối chỉnh sửa gom thông báo E2E vì đánh giá có thể làm yếu
điều kiện qualification. Chỉnh sửa đó không được áp dụng; các kiểm tra được giữ.
