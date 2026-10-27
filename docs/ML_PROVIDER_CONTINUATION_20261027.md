# Thu dữ liệu tiếp qua Groq và OpenAI — 27/10/2026

**Cập nhật mới:** Huy đã cung cấp key mới và yêu cầu tiếp tục. OpenAI đã hoàn tất
417 câu và kiểm định; OpenRouter đang thu 500 câu có timer theo dõi. Xem
[báo cáo tiếp tục mới](ML_NEW_KEYS_PROGRESS_20261027.md). Trạng thái chờ trong phần
dưới là snapshot của quyết định trước, không phải lệnh hiện tại.

**Đã thu thêm và huấn luyện; chưa bật ML live. Theo lựa chọn mới nhất của Huy,
chờ đối soát lần gọi mất kết nối trước mọi lần gọi trả phí tiếp theo.**

## Provider và tiền sử dụng

- Groq chính gọi lại được một phần. Key dự phòng cũng được thử trong cùng chiến
  dịch và cùng quota; cả hai sau đó nhận 429 `tokens_per_day`. Job đã gom trùng
  `1c95f2ce-a8f3-417f-8c23-36354dce0c9e` tăng từ 2 lên 103/262 câu. Chi phí lũy
  kế job là **0,003064825 USD**, không có cuộc gọi chưa rõ trạng thái.
- OpenRouter: `/api/v1/key` trả trần key 100 USD, còn 99,9709794 USD dưới trần.
  `/api/v1/credits` trả `total_credits=0`, `total_usage=0.0290206`; phép trừ là
  **−0,0290206 USD**, không phải số dư gần 100 USD. Free metadata báo 50 lượt/ngày,
  còn 50 tại thời điểm đọc. Không tự nạp tiền hoặc tăng ngân sách.
- OpenAI: chiến dịch đầu xác nhận Terra trả lời được, nhưng Sol bị từ chối 503
  hai lần, không có khoản chưa rõ; chi phí **0,000296 USD**. Không dùng model đang
  lỗi cho đợt thu hàng loạt tiếp theo.
- Chiến dịch thay thế dùng Terra, GPT-4.1 mini snapshot `2025-04-14` và Luna,
  tối đa 1 USD. GPT-4.1 mini dùng giá input/output **0,40/1,60 USD mỗi triệu token**
  và không truyền `reasoning_effort`. Các cấu hình mới giữ tách biệt với Groq;
  không chuyển nhãn Groq sang model/provider mới.

Trần key và credits là hai loại giới hạn khác nhau theo
[OpenRouter](https://openrouter.ai/docs/api_reference/limits). Giá/capabilities mini
được đối chiếu [OpenAI Docs](https://developers.openai.com/api/docs/models/gpt-4.1-mini).
Các số tài khoản trên là kết quả đọc bằng key server hiện có, không phải suy từ ảnh.

## Đã có dữ liệu và bản huấn luyện nào?

Đợt OpenAI thay thế `29149561-9a6c-4036-bf3b-401b6f66b674` chốt trước 400 nhóm,
gồm 200 DEV và 200 HOLDOUT mới, tách họ câu hỏi tiếng Việt để tránh trùng nguồn.
Thu được **120 bộ đủ ba phản hồi**, tương ứng 360 phản hồi có chấm bằng đáp án gốc.
Còn một phản hồi Terra hoàn thành ở câu kế tiếp, được ghi tiền và cache riêng.

- 362 bản ghi gọi: 361 hoàn thành, **1 mất kết nối chưa xác định kết quả**.
- Chi phí biết được: **0,0306310 USD**; khoản còn giữ dự phòng: **0,0034292 USD**.
  Không cộng khoản chưa rõ thành 0 USD hoặc tự ghi đã tiêu hết dự phòng.
- 102 mẫu DEV: 60 TRAIN, 24 CALIBRATION, 18 THRESHOLD.
- 18 HOLDOUT hiện có đều là tiếng Việt. Toàn bộ 120 mẫu gồm 116 tiếng Việt và
  4 toán; vì thứ tự thu chưa cân bằng domain, dữ liệu tạm này chưa kiểm định toán.
- Đã huấn luyện offline ML thường và ML + Attention, 5 epoch đã chốt trước điểm
  test. Artifact Attention có hash `a75a2df1116e2295918baeeb31af59464d93a4d12cc4b3c4add62e83342b7e42`.

Trên đúng 18 câu test đó, reference, ML thường và Attention đều đúng **15/18**.
Attention có 1 regression và 1 cải thiện nên tỷ lệ tổng bằng nhau; không thể dùng
tỷ lệ tổng để nói không làm giảm chất lượng từng câu. Cận trên regression một phía
95% là **23,77%**, cao hơn trần 3%. Replay Attention ghi p50 provider + router khoảng
0,91 lần reference; đây chưa phải đo đường HTTP/DB phục vụ thực tế.

`router qualify` **từ chối**: thiếu độ tin cậy tiếng Việt, thiếu kiểm định toán,
thiếu pilot E2E. Các mã lỗi E2E là thiếu bằng chứng, không phải kết quả một pilot
E2E đã chạy. Không tạo artifact/review được duyệt, không đổi `.env`, không restart
chat và không promote model nghiên cứu.

## Lần gọi cần đối soát

- Local call ID: `9e9c50cc-7e11-49c1-b506-95d3ecd6eabf`.
- Model: `gpt-4.1-mini-2025-04-14`; thuộc TRAIN toán, không phải HOLDOUT.
- Không nhận được provider response ID hoặc upstream HTTP status. 503 trong log
  là mã lỗi ứng dụng ánh xạ từ mất kết nối; không kết luận provider đã trả HTTP 503.
- API đọc usage tổ chức bị từ chối **403** với key hiện có. Chưa có bằng chứng đủ
  để tự đối soát cuộc gọi này; không xóa dispatch fence hoặc hoàn khoản dự phòng.
- Sau lỗi này chỉ huấn luyện/kiểm định offline và đọc metadata; **không có generation
  trả phí mới**. Huy đã chọn chờ đối soát rồi mới tiếp tục.

Theo [tài liệu request ID OpenAI](https://developers.openai.com/api/reference/overview),
ID request giúp đối chiếu lỗi mạng; local call ID hiện chưa phải ID do provider xác nhận.

## Bản sửa và kiểm tra

- Công cụ `router provider-limits` hiển thị riêng key cap và account balance;
  không suy số dư từ `limit_remaining`. Credits không đọc được giữ giá trị chưa rõ.
- Siết điều kiện import của pilot: thiếu mẫu hoặc còn cuộc gọi chưa đối soát thì
  không được gắn kết luận đủ điều kiện/import, dù các điểm replay đang đẹp.
- Report điểm cũ của đợt này đã đóng băng với `PASS_OBSERVED`; đây là điểm quan sát
  tạm, không phải chứng nhận live. Không sửa lại kết quả đã chốt hoặc vượt cổng
  `PILOT_FINALIZED`. Report formal qualification độc lập vẫn là **không đạt**.
- **41 kiểm thử offline qua**: metadata tài khoản, tập thiếu nhưng điểm cao, khoản
  chưa đối soát, cache/resume/fence, chia nguồn và cổng qualification. Ruff và kiểm
  tra kiểu script chuẩn bị dữ liệu qua. Không phát sinh API trong kiểm thử.

## Điểm tiếp tục đã chuẩn bị

Đã chuẩn bị, **chưa dispatch**, thư mục `data/router-live-qualification-20261027/native-v3-proposed/`:

- 417 câu: 217 DEV và 200 HOLDOUT; 18 câu test đã xem chuyển sang DEV, thay bằng
  18 họ câu hỏi tiếng Việt chưa xuất hiện ở các đợt trước.
- Loại nhóm TRAIN đang có cuộc gọi chưa rõ trước khi lập tập mới; không gọi lại
  cuộc gọi đó. Việc loại dựa trên sự cố vận hành, không dựa trên đúng/sai.
- Cache chỉ tái sử dụng khi prompt, profile và snapshot giá khớp; cùng catalog
  native-v2. Không làm mới ngân sách để bỏ qua chi phí đợt trước.
- Trần đề xuất đợt mới 0,90 USD. Cộng cả hai đợt OpenAI đã chạy và khoản dự phòng
  chưa rõ, tổng trần **0,9343562 USD**. Đây là phương án chuẩn bị, chưa được dispatch.
- Trạng thái theo quyết định của Huy: `WAIT_FOR_RECONCILIATION_USER_SELECTED`.
  Không chạy tiếp hoặc bật live chỉ vì quota Groq đã hồi phục.

Bằng chứng máy đọc: `output/project-audit/router-provider-continuation-20261027.json`
và `output/project-audit/router-native-v2-qualification-20261027.json`.
