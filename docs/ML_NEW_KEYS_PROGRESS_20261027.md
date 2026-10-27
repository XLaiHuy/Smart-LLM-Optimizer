# Tiếp tục ML + Attention bằng key mới — 27/10/2026

**Đã hoàn tất 500/500 câu, train và formal qualification. Chưa đạt live.**
Kết quả và chi phí cuối nằm trong [báo cáo nghiệm thu](ML_OPENROUTER_FINAL_20261027.md).
Các đoạn "đang chạy" bên dưới lưu snapshot tiến trình trước đó.

**Huy đã cho phép tiếp tục thu dữ liệu bằng key OpenAI/OpenRouter mới.** Quyết định
này thay trạng thái chờ đối soát ở báo cáo trước. Khoản cũ chưa rõ **0,0034292 USD**
vẫn được giữ; không gửi lại cuộc gọi mất kết nối đó. Key mới nằm trong `.env` phía
server đã bị Git ignore, không có key trong báo cáo hoặc mã nguồn.

## Đã kiểm tra tài khoản và gọi thực tế

| Provider | Kết quả |
|---|---|
| OpenAI | Đọc model HTTP 200; ba profile đã trả phản hồi thật trong campaign mới |
| OpenRouter | Key HTTP 200; trần 1 USD, chưa sử dụng tại preflight |
| Credits OpenRouter | Đã nạp 10 USD, đã dùng 3,037277413 USD; số dư lúc kiểm tra khoảng 6,9627 USD |
| Free quota OpenRouter | Metadata trả 1.000/ngày, còn 1.000 tại preflight; chiến dịch này dùng profile trả phí đã chốt |

Đã xác minh generation bằng call ID/response ID, không chỉ bằng model listing.
Các số tài khoản là snapshot; trần 1 USD của key vẫn áp dụng dù tài khoản còn nhiều
credits hơn. Không nạp tiền hoặc tăng trần tài khoản/người dùng/project.

## OpenAI: hoàn tất thu và huấn luyện, không đạt live

- Job: `dbb11e17-07b4-4aee-ad92-8344e9dac76b`.
- Đủ **417 nhóm**: 217 DEV, 200 HOLDOUT. Tập test gồm 100 toán và 100 tiếng Việt.
- 891 lần gọi mới; phần còn lại tái sử dụng cache đúng input/profile/giá.
- Chi phí theo token và catalog **0,0737791 USD**, không có cuộc gọi chưa rõ mới.
- Đã huấn luyện ML thường và Attention 5 epoch, chốt artifact trước khi đọc test.
- Hash Attention: `b4628809ad11e5e520ec8f2224fb7665c00de411356aeaa1c425508bd7208688`.

| Trên cùng 200 câu test | Reference | ML thường | ML + Attention |
|---|---:|---:|---:|
| Số câu đúng | 163 | 161 | 160 |
| Regression so với reference | — | 2 | 3 |
| Chi phí replay theo catalog, USD | 0,040964 | 0,0381663 | 0,037905 |

Attention có **0 regression/100 câu toán** và **3 regression/100 câu tiếng Việt**.
Cận trên một phía 95% tương ứng **2,95%** và **7,57%**, trong khi trần kiểm định là
3% cho mỗi nhóm. Vì vậy qualification từ chối bản này; không dùng việc toán đạt
để che kết quả tiếng Việt chưa đạt, không chỉnh threshold theo test đã xem.

Overhead Attention đo khoảng **23,4 ms p50**, provider + router p50/reference
khoảng **1,005**. Đây là replay, chưa phải pilot HTTP/DB thực tế. Không gọi thêm
pilot trả phí khi cổng chất lượng offline đã thất bại. Các mã E2E trong báo cáo
formal là thiếu bằng chứng, không phải một pilot E2E đã chạy và thất bại.

Chi phí trên là **ước tính từ usage thật và giá catalog**, không phải hóa đơn đã
đối soát của provider. Native usage được giữ riêng để kiểm tra chênh lệch.

## OpenRouter: đang thu tập mở rộng, sẽ tự train

- Job đang chạy: `81aa4e3a-e4c2-419e-9103-6d6396f2308e`.
- Manifest: `data/router-live-qualification-20261027/openrouter-expanded-full-v2-20261027/manifest.json`.
- Profile: OpenRouter GPT OSS 120B, OpenRouter GPT OSS 20B, OpenAI Luna. ID/profile
  và giá tách biệt với Groq; không gắn phản hồi provider khác thành kết quả Groq.
- **500 nhóm**: 300 DEV, 200 HOLDOUT. Bổ sung 83 nhóm DEV gốc chưa dùng, gồm
  42 toán và 41 tiếng Việt, bằng hash nguồn trước khi có kết quả OpenRouter.
  200 nhóm kiểm tra giữ nguyên kế hoạch đã chốt.
- Trần toàn chiến dịch **0,80 USD**, thấp hơn trần key **1 USD**. Ngân sách user và
  project vẫn được kiểm tra qua sổ cái chung.
- Lô xác minh 25 câu/75 lần gọi hoàn tất, không lỗi, không khoản chưa rõ, ước tính
  **0,002247848 USD**. Khi resume, phát hiện công cụ giữ batch size cũ và train sớm
  ở 50/500 câu. Job tạm `a1d07f08-1765-48e2-bcd0-7a25bf5a7193` đã finalized, chi
  **0,005037694 USD**; artifact được giữ riêng, không dùng điểm tạm để tune công thức.
- Đã sửa lỗi: full không train nếu corpus còn thiếu; runner tiếp tục cùng checkpoint
  cho đến đủ hoặc gặp lỗi/quota/ngân sách cần dừng. Cổng finalized vẫn được giữ.
  Protocol hoàn chỉnh v2 giữ nguyên 500 input, split, giá và recipe đã chốt; cache
  tái sử dụng 50 câu. Trần v2 giảm xuống **0,79 USD**; cộng đợt tạm thành tối đa
  **0,795037694 USD**, vẫn dưới tổng 0,80 USD. Không xóa hoặc sửa sổ chi phí cũ.
- Snapshot v2 tiếp theo: 58/500 câu, chi phí gọi mới ước tính 0,000695228 USD.
  Đây là tiến độ tại lúc ghi, không phải kết quả cuối. Trạng thái máy đọc cập nhật tại
  `output/project-audit/ml-new-keys-progress-20261027.json` và DB/job report.

Một bản ghi `unknown` khi worker còn chạy có thể chỉ là lần gọi đang xử lý; chỉ
kết luận lỗi chưa đối soát khi trạng thái terminal/call evidence xác nhận. Khi
đang chạy bình thường không tạo worker hoặc job trùng.

## Hoàn thiện routing trong đợt này

1. **Giới hạn phạm vi bằng chứng khi phục vụ.** Review toán/MCQ không tự cho phép
   chạy ML ở chat chung, lịch sử, memory, code hoặc RAG. Ngoài envelope single-turn
   đã đo thì dùng baseline, trace ghi `ML_UNREVIEWED_SCOPE_FALLBACK`. Giao diện
   có giải thích VI/EN. Đây là giới hạn dạng input đã đo, không phải bộ phân loại
   ngữ nghĩa toàn diện; câu thông thường như `1+1?` có thể vẫn dùng baseline.
2. **Nhịp gọi trả phí.** Giới hạn nội bộ OpenAI 24 RPM/model và OpenRouter 16 RPM/model,
   SQLite chia sẻ giữa alias/worker. Đây không phải hạn mức provider công bố.
   Collector có khoảng cách toàn cục 1,4 giây, một generation đang hoạt động;
   header chặt hơn và `Retry-After` vẫn có hiệu lực.
3. **Chặn giá endpoint OpenRouter.** Gửi `provider.max_price` theo input/output catalog,
   không chấp nhận phí mỗi request; yêu cầu hỗ trợ tham số đã cấu hình. Không âm
   thầm chuyển sang endpoint đắt hơn dự toán khi giá thấp không khả dụng.
4. **Mã đối chiếu native OpenAI.** Gửi `X-Client-Request-Id` tương ứng local call ID
   để hỗ trợ đối soát lỗi mạng. Đây là mã chẩn đoán, không phải cam kết idempotency
   hoặc quyền tự retry cuộc gọi chưa rõ kết quả.
5. **Cache Attention theo đúng artifact.** Giữ identity nguồn trong cache trọng số,
   tránh Python tái sử dụng object ID khiến artifact mới nhận nhầm trọng số cũ.
6. **Thu dữ liệu cân bằng và giữ đúng nhãn.** Xen kẽ domain trong từng split, luân
   phiên thứ tự gọi model bằng hash task; ghép kết quả theo config ID. Không đổi
   gold hoặc chia lại HOLDOUT sau khi đọc điểm.
7. **Pilot E2E chỉ sau khi offline đạt.** Yêu cầu đầy đủ HOLDOUT đã chốt, toàn bộ
   cổng offline qua; pilot xác nhận route thật sự chạy ML/Attention. Không tiêu API
   E2E để lấp thiếu hụt chất lượng đã biết.
8. **Sửa thông tin mô tả.** README không còn khẳng định router Attention <0,2 ms,
   ECE <0,04, sáu năng lực đã chứng nhận hoặc mức tiết kiệm chưa đo trong đợt này.
9. **Không train sớm ở mốc lô.** Phase full yêu cầu đủ corpus trước khi freeze DEV;
   runner tự resume các batch hoàn tất và trả trạng thái chưa hoàn chỉnh nếu dừng
   vì ngân sách. Có kiểm thử chặn `train_multi` khi mới đủ 25/32 mẫu fixture.
10. **Qualification tính cả runtime của router.** Phát hiện bước nghiệm thu trước
    đây dùng p50 provider để so sánh, trong khi pilot đã có số đo thêm overhead.
    Formal qualification nay dùng p50 provider + router để kiểm tra trần 1,10 và
    so sánh Attention với ML thường. Hai bản chọn model giống nhau nhưng Attention
    chậm hơn thì không bị coi là ngang nhau. Thiếu hoặc sai số đo runtime phải
    bị nhận diện; phép đo này vẫn không thay thế pilot HTTP/DB E2E.

**88 kiểm thử backend liên quan qua; frontend typecheck/lint qua; Ruff và mypy của
các module/script thay đổi qua.** Kiểm thử dùng provider giả lập, database tạm,
không tiêu API. Không đồng nhất kết quả này với toàn project đã hết lỗi: các lỗi
optimizer và kiểm thử cũ đã ghi ở báo cáo audit trước vẫn cần xử lý riêng.

## Timer và nghiệm thu tiếp theo

Theo yêu cầu cập nhật mới của Huy, lịch theo dõi trong chính chat chuyển sang
mỗi **10 phút**, ID
`ho-n-t-t-ki-m-nh-ml-attention`. Mỗi lượt báo ngắn tiến độ, giai đoạn, chi phí và
lỗi nếu có; chủ động xử lý lỗi trong phạm vi đã giao. Không tự tạo chiến dịch mới
hoặc tăng ngân sách. Khi có kết luận cuối thì dừng lịch để tránh thông báo lặp.

Khi OpenRouter thu và train xong: qualification trên đúng dev/holdout/artifact đã
đóng băng; nếu offline đạt mới đo pilot phục vụ, sau đó formal qualification đầy
đủ. Nếu không đạt thì giữ baseline và lưu nguyên nhân. **Hiện chưa bật ML live**;
đạt hai nhóm này cũng chưa chứng minh code, memory, RAG hay chat mở đã được kiểm định.

Bằng chứng: `output/project-audit/new-keys-preflight-20261027.json`,
`output/project-audit/router-native-v3-qualification-20261027.json`, và
`data/router-live-qualification-20261027/openrouter-expanded-20261027/access-preflight.json`.

Tài liệu giao thức: [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[OpenRouter limits](https://openrouter.ai/docs/api_reference/limits),
[OpenAI request IDs](https://developers.openai.com/api/reference/overview).
