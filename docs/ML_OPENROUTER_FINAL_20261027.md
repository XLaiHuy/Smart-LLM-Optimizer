# Kết quả OpenRouter: đủ 500 câu, đã train, chưa đạt live

Chiến dịch `81aa4e3a-e4c2-419e-9103-6d6396f2308e` đã hoàn tất thu dữ liệu,
huấn luyện và kiểm định. **Không bật ML + Attention live vì chất lượng chưa đạt
và Attention chưa mang lại lợi ích so với ML thường.** Giữ nguyên baseline.

## Dữ liệu và chi phí

- 500 nhóm nguồn, gồm 300 DEV và 200 HOLDOUT; nhóm giữa hai tập không trùng.
- DEV: 180 TRAIN, 60 CALIBRATION, 60 THRESHOLD. HOLDOUT: 100 toán, 100 MCQ tiếng Việt.
- Đúng 1.500 lần gọi hoàn thành qua ba cấu hình: OpenRouter GPT OSS 120B,
  OpenRouter GPT OSS 20B và native OpenAI Luna. 150 lần thuộc lô cũ, 1.350 lần
  thuộc đợt hoàn chỉnh; cache giữ đúng input/profile/giá, không gọi trùng 50 câu.
- Tổng chi phí ước tính theo usage/catalog **0,044239630 USD**, dưới trần 0,80 USD.
  Con số này bao gồm cả native OpenAI Luna, không phải toàn bộ đều trừ key OpenRouter.
- Riêng 1.000 lần OpenRouter, trường cost trong phản hồi provider cộng lại là
  **0,016251048 USD**; đây là subtotal provider báo, giữ riêng với ước tính catalog
  và không giả là hóa đơn cuối đã đối soát.
- Không có cuộc gọi chưa xác định mới. Khoản OpenAI cũ **0,0034292 USD** vẫn giữ
  dự phòng, không bị xóa hoặc coi là 0 USD.

## Huấn luyện và kết quả độc lập

Đã train cặp ML thường và ML + Attention 5 epoch theo công thức khóa trước test.
Không điều chỉnh threshold/recipe theo kết quả HOLDOUT, không nới ngưỡng nghiệm thu.

| Trên cùng 200 câu kiểm tra | Reference GPT OSS 120B | ML thường | ML + Attention |
|---|---:|---:|---:|
| Đúng | 180/200 (90%) | 177/200 (88,5%) | 177/200 (88,5%) |
| Reference đúng nhưng lựa chọn router sai | — | 6 | 4 |
| Chi phí replay theo catalog (USD) | 0,0137382 | 0,007249662 | 0,012611496 |
| p50 provider + router / reference | 1,00 | 0,877 | 1,012 |

Tỷ lệ đúng tổng không cho biết mọi câu đều giữ nguyên chất lượng: cải thiện một
câu có thể bù một câu làm sai. Cổng formal đếm regression theo từng nhóm độc lập.

| Nhóm kiểm tra của Attention | Regression | Cận trên một phía 95% | Trần |
|---|---:|---:|---:|
| Toán | 1/100 | 4,66% | 3% |
| Tiếng Việt | 3/100 | 7,57% | 3% |

Cả hai nhóm chưa đạt bằng chứng yêu cầu. ML thường có cùng accuracy tổng nhưng
rẻ và nhanh hơn Attention trên replay này; **ML thường cũng chưa được duyệt live**,
vì có regression và chưa hoàn tất các cổng riêng. Không tự đổi sang ML thường chỉ
vì nó tốt hơn Attention ở hai chỉ số khác.

Attention overhead khoảng **49,9 ms p50**, ML thường khoảng **9,94 ms** trong lần
qualification offline này. Đây là số đo CPU/replay trên máy hiện tại, chưa phải
pilot HTTP/DB/browser. Không tiêu thêm tiền chạy E2E khi cổng offline đã fail.
Các mã E2E trong report formal là thiếu bằng chứng, không phải một pilot E2E đã
được gọi và thất bại.

## ML và Attention thực sự chạy chưa?

**Có, trong luồng huấn luyện và replay offline.** Đã nạp artifact, chạy encoder và
pooling NumPy CPU, thu sáu giá trị đặc trưng thật và lưu bằng chứng. Điều này không
có nghĩa model đã đủ chuẩn được phục vụ trong chat.

- Hash phục vụ của artifact Attention:
  `5d7e83ef8127183ea3d3c3a4650d72c0e71699a66df8e871bdb167d1e39308fc`.
- File artifact/baseline/dev/holdout và manifest đã đóng băng trong thư mục job.
- `.env` không được đổi sang artifact nghiên cứu mới; không tạo receipt PASS,
  không restart server để bật live, không bật research-candidate override.
- Sáu giá trị Attention là đặc trưng học được, chưa phải sáu năng lực có nhãn
  toán/code/lập luận/... được kiểm chứng riêng.

## Điều đã xác định và hướng xử lý tiếp

1. **API không phải điểm chặn của đợt này.** Các key đã gọi đủ số mẫu, không có
   cuộc gọi terminal unknown hoặc quota error mới. Kết quả không đạt nằm ở lựa
   chọn model/chất lượng thực nghiệm và lợi ích của Attention.
2. **Attention chưa cải thiện quyết định.** Trên 60 câu DEV dùng chọn threshold,
   Attention chỉ chuyển 7 câu sang ứng viên, giữ reference cho 53 câu; ML thường
   chuyển 25 câu và giữ reference 35 câu. Trên HOLDOUT, Attention giữ reference
   181/200 câu nhưng vẫn có 4 regression ở phần được chuyển model. Đây là kết quả
   đo, không phải bằng chứng một nguyên nhân duy nhất như learning rate hay số epoch.
3. **Mục tiêu hiệu chỉnh và nghiệm thu cần được đối chiếu.** Selector DEV hiện dùng
   quality delta tổng theo domain; nghiệm thu còn yêu cầu cận trên regression từng
   nhóm. Điểm tổng tốt không bảo đảm đạt cổng regression. Chưa sửa selector theo
   điểm test đã xem; cần thiết kế và khóa protocol tiếp theo trên DEV trước.
4. **Thêm số lượng mẫu không tự bảo đảm PASS.** Đợt tiếp theo cần chẩn đoán chất
   lượng đặc trưng, calibration và những quyết định chuyển model trên DEV, so với
   ablation ML thường. Chọn công thức bằng DEV; kiểm định lại trên nguồn/test mới
   độc lập. Không quay lại dùng 200 câu test này như một tập mới sau khi đã xem điểm.
   Chẩn đoán trên 300 mẫu DEV cho thấy **4/6 đặc trưng Attention nằm gần 0 hoặc 1
   ở ít nhất 99% mẫu** (ngưỡng 0,01/0,99). Đây là dấu hiệu biểu diễn bị bão hòa cần
   kiểm tra bằng thí nghiệm DEV (độ đa dạng đặc trưng, scale/normalization, mục tiêu
   học và calibration), chưa chứng minh một nguyên nhân duy nhất cho regression.
   Không đổi trọng số hoặc recipe của bản vừa kiểm định để làm đẹp kết quả.
5. **Phạm vi vẫn chỉ toán và MCQ.** Code, hội thoại mở, memory và RAG cần nguồn dữ
   liệu, grader và protocol riêng trước khi có thể nói ML đủ chuẩn toàn hệ thống.

Các lỗi phần mềm đã sửa trong quá trình thực hiện (scope guard, quota trả phí,
trần giá OpenRouter, request ID, cache trọng số, thứ tự collector, train sớm theo
lô và đo overhead khi qualification) giữ nguyên. Bằng chứng kiểm thử nằm trong
[báo cáo tiến trình](ML_NEW_KEYS_PROGRESS_20261027.md): 88 kiểm thử liên quan qua,
frontend typecheck/lint qua; không đồng nghĩa toàn project đã hết lỗi cũ.

## Kết luận vận hành

Đợt 500 câu đã kết thúc với kết quả **không đạt qualification**. Không tạo thêm
chiến dịch trả phí hoặc chỉnh công thức trên HOLDOUT đã xem. Lịch theo dõi định kỳ
được dừng sau khi báo kết quả cuối, tránh thông báo lặp cho một job đã xong.

Bằng chứng chính:

- `output/project-audit/router-openrouter-full-v2-qualification-20261027.json`
- `data/router-live-qualification-20261027/openrouter-expanded-20261027/runs/81aa4e3a-e4c2-419e-9103-6d6396f2308e/report.json`
- Cùng thư mục: `frozen.json`, `dev.json`, `holdout.json`, `artifact.json`,
  `baseline.json`, `attention-execution-proof.json`, `attention-dev-diagnostics.json`.
