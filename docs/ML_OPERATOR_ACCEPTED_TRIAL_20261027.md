# ML + Attention: quyết định dùng thử của Huy

Huy chấp nhận kết quả **177/200** và yêu cầu đưa ML + Attention vào chat ngày
27/10/2026. Đây là quyết định sử dụng bản nghiên cứu trong môi trường development;
không phải thay đổi kết quả formal qualification hoặc chứng nhận production.

## Cấu hình đã nạp

- Artifact: `config/router_attention_operator_accepted.json`, giữ nguyên
  `purpose=research_candidate`, có Attention thật.
- Hash artifact: `5d7e83ef8127183ea3d3c3a4650d72c0e71699a66df8e871bdb167d1e39308fc`.
- Catalog: `config/models.json`, khớp ba profile đã đo: OpenRouter GPT OSS 120B,
  OpenRouter GPT OSS 20B và OpenAI Luna. Không dùng nhầm kết quả này cho Groq.
- `AUTO_ROUTING_STRATEGY=ml_multi_model`.
- `ML_ROUTER_ALLOW_RESEARCH_CANDIDATE=true`, chỉ có hiệu lực ở development.
- `ML_ROUTER_LIVE_APPROVED=false`: không giả là đã được phê duyệt khoa học.
- Receipt quyết định: `config/router_research_acceptance.json`, gắn với đúng hash
  artifact, dataset, cấu hình và giá.
- Bằng chứng kiểm định chưa đạt: `config/router_research_evidence.json`, giữ
  `passed=false`, 177/200 của Attention so với 180/200 reference, 4 regression.
- Cấu hình cũ được lưu ở `data/backups/before-operator-research-20261027/`, không
  bao gồm bản sao API key.

Không cần train lại để bật dùng thử artifact đã có. Bản mới chỉ được xét lại sau
khi đo thật; không thay trọng số hoặc threshold của artifact này để sửa điểm test
đã xem. Code, chat mở, memory và RAG chưa có chứng nhận chất lượng từ bộ 500 câu.

## Cách phân biệt trong hệ thống

Development chat cần cả công tắc và receipt hợp lệ. Công tắc đơn lẻ không tự mở
review; artifact giả lập, thiếu Attention, khác hash/catalog/giá vẫn bị chặn.
Production qualification tiếp tục yêu cầu bằng chứng cũ, không coi receipt dùng
thử là receipt PASS.

Trace ghi `ROUTE_ML_RESEARCH_REFERENCE` hoặc `ROUTE_ML_RESEARCH_CANDIDATE`, cùng
`ml_executed`, `attention_executed` và sáu đặc trưng đo thực. Quy tắc
`operator_accepted_research` được giữ cả khi provider failover. Giao diện gắn nhãn
**ML + Attention · thử nghiệm**. Research không bỏ qua ngân sách, quota, context
window, capability hoặc deadline.

Một câu đơn giản vẫn có thể được ML chọn model tham chiếu nếu các ứng viên không
đạt threshold đã học. Điều này khác với việc không chạy ML rồi fallback do thiếu
review. Bằng chứng offline cho câu `1 + 1 = mấy?` đã xác nhận ML và Attention thực
sự chạy, kể cả khi kết quả chọn GPT OSS 120B.

## Nạp vào Docker

Backend image trước đó lặp khởi động vì thiếu migration h107 đã có trong database.
Build lại image mang migration hiện tại; không lùi hoặc xóa dữ liệu. Runtime Docker
cần `SMARTLLM_ROOT=/app` để resolve đúng config và encoder assets đã mount, cùng
hai dependency ONNX được pin cho CPU serving. Giữ nguyên lockfile ứng dụng.

Backend và frontend đã được nạp lại thành công. Hai đường HTTP trực tiếp backend
và proxy frontend đều trả 200. Image chạy là `smartllmplatform-backend:operator-research`
và `smartllmplatform-frontend:operator-research`, cũng đã gắn tag `latest` cho Compose.
Các Dockerfile `runtime-update` dùng lại dependency từ image của chính project đã
pin tag `pre-operator-20261027`; cài dependency serving có hash rồi `pip check`, build
frontend production từ source hiện tại. Dockerfile thông thường vẫn phục vụ clean
build. Compose tăng thời gian chờ khởi động CPU lên 180 giây cho lần tạo container
tiếp theo. Backend hiện tại đã healthy, không cần khởi động lại thêm.

Lượt chat thật qua orchestration, ledger và provider của ứng dụng:

- Request ID: `539dfc79-f214-4a40-ab59-a7b9b6ee1b16`.
- Prompt: `1 + 1 = mấy? Trả lời một từ duy nhất.`; phản hồi: **hai**.
- `ml_executed=true`, `attention_executed=true`, sáu đặc trưng thực, backend `numpy`.
- Model thực và trace cùng là `openai/gpt-oss-120b` qua OpenRouter; provider dispatch
  `completed`. Lý do `ROUTE_ML_RESEARCH_REFERENCE`, có `operator_accepted_research`.
- GPT OSS 20B được chấm `0.91232192824723`, dưới threshold `0.9228998323717365`;
  chọn reference sau khi chấm điểm là hành vi đúng của artifact hiện tại.
- Chi phí catalog ước tính **0,000067950 USD**, dưới trần lượt thử 0,01 USD.
- Bằng chứng: `data/operator-research-verification/response.json`, `trace.json` và
  `output/project-audit/operator-research-activation-20261027.json`.

Lượt xác minh dùng ASGI trong ứng dụng thật cùng database hiện tại và provider live;
không kiểm tra đăng nhập hoặc thao tác click trong browser. Không phát sinh paid API
trong kiểm thử tự động. Bộ kiểm thử liên quan: 95 passed; frontend typecheck/lint và
production build thành công. Không coi một lượt chat là kiểm định chất lượng bổ sung.

## Có nên train thêm?

- **Để dùng thử ngay:** không cần; đã có artifact hợp lệ để chạy.
- **Để cải thiện:** nên dựa trên các lỗi lựa chọn model quan sát được và chẩn đoán
  DEV. Hiện 4/6 đặc trưng Attention gần 0/1 trên ít nhất 99% mẫu DEV, nên chỉ tăng
  số mẫu chưa chắc sửa được chất lượng biểu diễn hoặc calibration.
- Khóa công thức mới bằng DEV, kiểm tra lại bằng HOLDOUT mới. Không tái dùng 200
  câu test đã xem như bằng chứng độc lập sau khi chỉnh model.

Báo cáo nền: [kết quả kiểm định 500 câu](ML_OPENROUTER_FINAL_20261027.md).

Đợt bổ sung sau quyết định dùng thử đã thu đủ dữ liệu và train lại. Attention mới
đạt 95/110 trên test mới, bản hiện tại đạt 99/110 trên cùng test; giữ nguyên artifact
đang phục vụ. Xem [phân tích lỗi và bổ sung có mục tiêu](ML_TARGETED_ERROR_ANALYSIS_20261027.md).
