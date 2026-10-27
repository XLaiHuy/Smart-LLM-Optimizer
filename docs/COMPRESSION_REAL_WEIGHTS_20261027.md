# Kiểm thử kiến trúc với LLMLingua thật — 27/10/2026

## Rà soát chất lượng câu trả lời sau vòng live

17/17 là **đúng trạng thái HTTP**, không phải 17 đáp án đúng. Đọc lại output thật:
`short_hard` trả **8899** cho câu “giảm 2% còn 8722”; đáp án đúng là
`8722 / 0.98 = 8900`. Hai vòng audit trước trả 8900, vòng mới sai: đây là biến động
chất lượng sinh nội dung cần đưa vào regression chất lượng, không quy thành lỗi API.
Không coi baseline 120B là bảo đảm toán đúng. 809 test phần mềm vẫn đạt, nhưng
không thay thế kiểm định câu trả lời thật.

`memory_unknown` dùng cùng tài khoản audit có ký ức từ phiên cũ; thực tế trả chưa
biết tên/ngành/trường nhưng nhớ đề tài SmartLLM Router. MemoryManager có chủ đích
đọc các phiên khác của cùng owner. Vì vậy ca này không chứng nhận tài khoản hoàn
toàn không dữ kiện; cần account cô lập sạch cho phép thử đó. Không xóa memory thật
để làm đẹp kết quả. Chi tiết lưu `quality_review` trong báo cáo JSON.

Key OpenAI hiện truy cập metadata `gpt-6-luna` được (GET model: 200); chưa gọi
completion hoặc đối soát billing trong lần rà soát này. Catalog đã đánh dấu Luna
được dùng fallback. Thứ tự phụ thuộc model khả dụng, ưu tiên catalog, giá dự toán,
quota, khả năng và ngân sách; không cam kết mọi lỗi đều chuyển được sang Luna.

Bảng đầy đủ prompt/response/model/token/USD/thời gian, gồm cả 3 input bị từ chối:
`output/project-audit/prompt-results-detailed-20261027.csv`.

Tiếp nối `SYSTEM_PROMPT_AUDIT_20261027.md`: đã tải phần weights còn thiếu,
không thay artifact ML + Attention được Huy chấp nhận dùng thử.

## Chuẩn bị tài nguyên

- Repository Microsoft: `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`.
- Revision: `5f0c82792b7ea14c6484e015b6a072009496b7f2`.
- 8 file, tổng 713.310.011 byte. Weights SHA256:
  `22b9ecde52fec5c97e8c54a293be768727df95a81c6c8dccb03f262a50c58324`.
- Cache bền vững: `/app/data/huggingface/hub`; Compose đặt `HF_HUB_CACHE` vào đây,
  `OMP_NUM_THREADS=2`, `MKL_NUM_THREADS=2`. Cache vẫn còn khi recreate container.
- Serving dùng `local_files_only=True`; tải là thao tác chuẩn bị riêng.
  Không gọi API LLM để tải model hoặc chạy audit nén local.

Chuẩn bị từ root project:

```powershell
Get-Content scripts/prepare_compression_resources.py -Raw | docker compose exec -T backend python - --download --output /app/data/system-audit/compression-assets.json
```

Bỏ `--download` để chỉ xác minh offline. Script kiểm tra snapshot đầy đủ và
checksum weights, lưu hash từng file; không đưa weights vào Git/image.

## Lỗi chỉ xuất hiện khi chạy model thật

1. Tải có chọn lọc file khiến Hugging Face từ chối local snapshot vì thiếu
   `.gitattributes`. Đã tải trọn snapshot đúng revision, xác minh offline.
2. Bộ nén đổi `BLUE-851` thành `BLUE - 851`, nhưng validator cũ chỉ giữ con số
   nên vẫn ghi preserved. Đã bảo vệ identifier/email/quoted literal và giữ nguyên
   đoạn chứa protected span, câu hỏi/yêu cầu nhận diện được, đoạn cuối cùng.
3. Giữ thực thể không chứng minh giữ ý nghĩa. Bản thay đổi cần thêm cosine >=0,85
   của từng đoạn với encoder ONNX cục bộ; thiếu score, nonfinite hoặc quá dài
   để encode đầy đủ thì giữ đoạn gốc. Không dùng vector bị truncate làm bằng chứng.
4. 16 đoạn lặp bị inference 16 lần: lượt đo Việt ban đầu ~29,15 giây, Anh ~21,22
   giây. Memo trong một request tái sử dụng kết quả cho đoạn giống hệt, vẫn giữ
   đủ số lần xuất hiện, thứ tự và separator. Không cache text người dùng qua phiên.
5. Warmup trước readiness chạy cả load và một inference. Vẫn có cold/kernel/CPU
   contention; giữ timeout 2 giây, một worker, không giải phóng slot trước khi
   worker thật kết thúc. Tổng unique work quá 512 model token thì bỏ qua sớm.

Cosine chỉ là bộ lọc từ chối, không chứng minh tương đương logic. Chưa chứng nhận
mọi paraphrase, tên người không được đánh dấu hoặc yêu cầu ngầm. Không nới gate
để buộc mọi request phải nén. Code/JSON vẫn theo nhánh bảo toàn rule-based.

## Ma trận local thật

`scripts/audit_compression_local.py` chạy weights LLMLingua + encoder ONNX thật,
không provider. Bằng chứng:
`data/system-audit/compression-real-warm-20261027.json`.

| Nhóm | Kết quả bộ tối ưu | Token trước → sau | Thời gian quan sát |
|---|---|---|---|
| Ngắn | Skip đúng ngưỡng | — | <1 ms |
| Việt dài | Nén | 1384 → 1024 | 1461 ms |
| Anh dài | Nén | 534 → 374 | 1486 ms |
| Điều kiện không ít hơn | Nén phần nền, giữ điều kiện | 717 → 537 | 1480 ms |
| Số âm Unicode | Nén phần nền, giữ số âm | 712 → 532 | 1250 ms |
| Mã/email/identifier/quoted name | Nén phần nền, giữ literal | 714 → 534 | 1335 ms |
| Code | Rule-based, không lợi ích nên skip | 703 → 703 | 5 ms |
| JSON | Rule-based, không lợi ích nên skip | 701 → 701 | 4 ms |
| Một đoạn vượt cửa sổ | Skip, không truncate | — | 16 ms |
| Nhiều đoạn unique vượt work budget | Skip sớm | — | 30 ms |

10/10 ca giữ các literal bắt buộc ở cả output raw và output được chấp nhận.
5/10 ca áp dụng nén. Số đo đơn lẻ trên máy đang chạy build/test, không phải SLO.
Audit đầu bị đo busy do gọi raw đồng bộ làm nghẽn event loop của chính harness;
đã sửa harness dùng `to_thread`, giữ kết quả cũ để đối chiếu, không bỏ semaphore
hay kéo dài deadline để che lỗi.

## Xác nhận hệ thống

Vòng live qua frontend/backend/provider đạt **17/17 trạng thái mong đợi**:
14 trả lời thành công, 3 đầu vào bị từ chối đúng; 14/14 response xác nhận ML và
Attention thực sự chạy, chat/trace thống nhất model. Cặp bật/tắt nén VI/EN đều
trả đúng `BLUE-851`. Trace của cả hai lượt bật nén ghi `applied / llmlingua2`.

| Cặp một lượt | Tắt nén | Bật nén | Token prompt được rewrite |
|---|---:|---:|---|
| Việt | 1542 ms | 4297 ms | 1384 → 1024 |
| Anh | 1754 ms | 4597 ms | 534 → 374 |

Nén giảm token nhưng tổng thời gian tăng ở hai cặp quan sát này. Không tuyên bố
LLMLingua làm chat nhanh hơn hoặc rẻ hơn chỉ từ tỷ lệ token; thời gian provider
và output có thể dao động. Các đoạn ngắn/code/JSON và quá work budget tiếp tục
skip đúng policy. Có cosine gate và literal checks không đồng nghĩa chứng nhận
chất lượng câu trả lời cho mọi prompt.

Chi phí catalog ước tính **0,002792532 USD**; p50 của 14 lượt thành công khoảng
**3707 ms**. Không có dispatch provider chưa xác định mới. Database và bản backup
`data/backups/after-compression-audit-20261027.sqlite3` đều integrity check `ok`;
hash artifact routing giữ nguyên. Bằng chứng máy đọc:
`output/project-audit/compression-final-20261027.json` và
`data/system-audit/live-compression-ready-20261027/`.

65 kiểm thử optimizer/biên/fault đạt; Ruff đạt và mypy 5 file production thay đổi
đạt. Hồi quy toàn backend và test cạnh source: **809 passed**, 396,39 giây,
không provider trả phí. XML: `output/project-audit/compression-backend-full-20261027.xml`.
Backend image đang chạy:
`sha256:92f1251b3255ecb1eb53f981d55cd4d55e8b040c1d475e7eea6a52a27c7e7ba2`.
Health backend và health qua frontend proxy đạt 200 sau vòng live.

Lượt live bổ sung giữ trần đã duyệt **0,13 USD/vòng**, 0,01 USD/request;
kiểm tra trước từng dispatch và dừng khi chi phí chưa xác định. Không nâng trần
lên 0,17 USD cho 17 ca. Phiên bản mới đã triển khai, nạp model trước readiness.

Kết quả trước trong báo cáo system audit vẫn có giá trị lịch sử; dòng “thiếu
weights” ở đó đã được xử lý bởi đợt này. Việc nén hoạt động không thay thế formal
qualification của router hoặc chất lượng downstream trên benchmark độc lập.
