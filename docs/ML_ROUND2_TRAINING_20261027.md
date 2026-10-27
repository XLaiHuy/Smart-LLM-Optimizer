# Huấn luyện bổ sung ML + Attention — vòng 2

**Cập nhật tiếp theo:** đã thử lại cả hai key Groq, chuyển thu dữ liệu và huấn luyện
riêng qua OpenAI. Hiện chờ đối soát một lần gọi mất kết nối theo lựa chọn của Huy;
xem [báo cáo mới](ML_PROVIDER_CONTINUATION_20261027.md). Các số bên dưới là snapshot
của vòng 2 trước đợt tiếp tục này.

**Đã huấn luyện lại; chưa đủ điều kiện bật live.** Hạn mức token/ngày của Groq
đang chặn thu thập phần kiểm định còn thiếu. Đây là lỗi 429 thực từ provider,
đã nhận diện loại giới hạn mà không lưu khóa hoặc thông báo riêng tư.

## Đã thực hiện

- Thu thêm 151 bộ phản hồi ba model trong campaign đầu, giữ nguyên toàn bộ cache
  và sổ chi phí. Campaign được thay thế bằng danh sách đã gom nguồn trùng, không
  sửa corpus hoặc kết quả đã đóng băng của job cũ.
- Huấn luyện mở rộng từ 200 mẫu DEV ở vòng trước lên **543 mẫu có chấm điểm thật**,
  thuộc **474 nhóm nguồn**. Split theo nhóm: 324 TRAIN, 109 CALIBRATION, 110 THRESHOLD.
  HOLDOUT của vòng trước được ghi rõ là đã nghỉ vai trò kiểm định và chuyển sang DEV.
- Chặn mạng trong quá trình train. Train một bản ML không Attention và ba công
  thức Attention: 64 token/5 epoch, 64 token/15 epoch, 128 token/15 epoch. Cả ba giữ
  nguyên dữ liệu, giá và cấu hình generation v5; thay giới hạn token encoder không
  cắt prompt gửi provider.
- Chọn **64 token, 5 epoch** chỉ bằng DEV, ưu tiên ít regression trước điểm đúng,
  chi phí và thời gian. Lưu artifact cùng hash trước khi đọc điểm test mới.
- Tìm được nhiều câu Aya chỉ khác phần lời dẫn. Đã gom thành phần liên thông bằng
  TF-IDF ký tự 3–5/cosine ≥0,90; các biến thể chung nhóm luôn ở cùng split. Đây là
  cách loại trùng bảo thủ theo văn bản, chưa phải chứng minh độc lập ngữ nghĩa tuyệt đối.
- Khóa tập kiểm định mới gồm **100 nhóm toán + 100 nhóm tiếng Việt**. Để đủ nhóm
  tiếng Việt chưa xuất hiện trong DEV, bổ sung 40 câu gốc có dòng đáp án rõ trong
  nguồn: 28 nhóm cho test và 12 nhóm cho DEV. Không nhờ model sinh đáp án chuẩn.

## Kết quả quan sát

Không so trực tiếp tỷ lệ của tập mới với tỷ lệ vòng trước vì câu hỏi và cách gom
nguồn đã thay đổi. Mỗi so sánh dưới đây dùng cùng các câu trong chính hàng đó.

| Phần dữ liệu | Reference cố định | ML không Attention | ML + Attention được chọn |
|---|---:|---:|---:|
| 110 mẫu THRESHOLD của DEV | 83/110 | 94/110 | 90/110 |
| 50 nhóm test tiếng Việt đã có đủ phản hồi | 35/50 | 38/50 | 37/50 |

Trên 50 nhóm test mới, chưa thấy trường hợp reference đúng nhưng Attention chọn
model trả lời sai. Tuy nhiên, cận trên một phía 95% của regression vẫn là **5,82%**,
chưa đạt tối đa 3%. Chưa có kết quả cho 100 nhóm toán mới và còn thiếu 50 nhóm
tiếng Việt, tổng **150 nhóm test**. Chưa có cơ sở nói chất lượng toán đã được sửa.

Replay test hiện có cho tỷ lệ p50 provider + router CPU khoảng **1,19**, vượt trần
1,10. Đây không phải đo HTTP/DB/browser E2E. Bản ML không Attention cũng đúng nhiều
hơn Attention trên tập nhỏ này. Vì vậy, thêm dữ liệu chưa chứng minh Attention
là lựa chọn tốt hơn để go live.

**Không promote artifact, không tạo receipt PASS, không đổi `.env` và không
khởi động lại chat live.** Bộ `router qualify` đã từ chối bản kiểm định thiếu dữ
liệu. Các mã E2E trong report là thiếu bằng chứng, không phải một pilot E2E đã chạy.
Sau khi xem điểm test tạm này, giữ nguyên bản đã đóng băng; không chỉnh công thức
theo 50 câu đó rồi dùng lại chúng để chứng nhận.

## Quota, chi phí và trạng thái tiếp tục

Chi phí vòng này theo catalog: **0,015250925 USD**, không có khoản chưa rõ chi phí.
Trần gồm cả job cũ và job tiếp tục là **0,994953750 USD**, vẫn chịu ngân sách user
và project. Không tăng quota, nạp tiền hoặc đổi model để né giới hạn provider.

Job đầu `81a07410-527b-4caa-9631-23064820ebf9` dừng ở 151/300 câu. Job đã gom trùng
`1c95f2ce-a8f3-417f-8c23-36354dce0c9e` giữ cùng thư mục cache, dừng ở 2/262 câu.
Điểm kiểm tra được phục dựng từ các phản hồi đã hoàn thành ở cả hai job, chỉ khi
prompt/config/giá khớp. Phản hồi cache không được tính thành lượt gọi mới.

Công cụ đã biết chờ và resume quota phút bằng cùng job, nhưng dừng khi provider
xác nhận quota ngày. Hiện không có worker gọi API chạy nền. Không thể suy ra lúc
toàn bộ capacity hồi phục chỉ từ `Retry-After` ngắn của một request bị từ chối.

Khi provider có lại capacity, tiếp tục đúng job dưới đây; không tạo lại job để
reset trần chi phí. Lệnh này gọi API thật:

```powershell
python scripts/run_router_pilot.py --owner admin --manifest data/router-live-qualification-20261027/round2-v5/family-deduplicated/manifest.json --directory data/router-live-qualification-20261027/round2-v5/runs --live --resume 1c95f2ce-a8f3-417f-8c23-36354dce0c9e --phase collect --batches 11 --wait-for-quota
```

Sau khi đủ dữ liệu, kiểm tra toàn bộ bằng cùng artifact đã đóng băng, không train
lại theo kết quả 50 câu đã xem:

```powershell
python scripts/evaluate_router_round2.py --campaign data/router-live-qualification-20261027/round2-v5 --report output/project-audit/router-round2-full-replay-20261027.json
```

Lệnh full hiện từ chối xuất báo cáo vì thiếu 150 nhóm. Nếu đủ dữ liệu và đạt
quality/latency mới chạy pilot E2E có ngân sách, formal qualification và xem xét
phạm vi chat được kiểm định. Code, viết mở, RAG và memory chưa được chứng nhận
chỉ bằng dữ liệu toán/trắc nghiệm của lượt này.

## Bằng chứng và kiểm tra phần mềm

- `data/router-live-qualification-20261027/round2-v5/trained/`: artifact, baseline,
  ba công thức, DEV đã dùng, báo cáo chọn công thức và báo cáo test tạm.
- `output/project-audit/router-round2-status-20261027.json`: trạng thái, hash,
  job ID, số mẫu thiếu và chi phí để tiếp tục.
- `output/project-audit/router-round2-partial-qualification-20261027.json`: lý do
  qualification không đạt; serving artifact và receipt tương ứng không tồn tại.
- 34 ca offline về protocol, quota, tách nhóm và qualification đã qua. Ruff và
  kiểm tra kiểu của năm script thay đổi đã qua; kiểm thử không tiêu API.

Bộ duyệt tự động từ chối đề xuất sửa thuật toán `select_thresholds` trong
`backend/app/routing/ml/multi_training.py`, với lý do vượt phạm vi module/thuật
toán được phép thay đổi. Đề xuất đó không được áp dụng; vòng này dùng thuật toán
có sẵn với dữ liệu lớn hơn và các tham số train đã hỗ trợ.
