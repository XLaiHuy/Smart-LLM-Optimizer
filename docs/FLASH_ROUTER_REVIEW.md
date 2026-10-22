# Đối chiếu FLASH-ROUTER — 22/10/2026

**Cập nhật sau kiểm tra cuối:** [ROUTER_FINAL_READINESS.md](ROUTER_FINAL_READINESS.md) mô tả bản sửa hiện tại, dữ liệu đã loại trùng và giới hạn bằng chứng. Các phát hiện ban đầu bên dưới được giữ làm lịch sử review.

Kết luận: implementation trước lượt sửa này **chưa đúng toàn bộ plan**. Các tests shape/khởi tạo không chứng minh các module đã được tích hợp, đã học trọng số hoặc đạt các mốc latency/quality nêu trong bản kế hoạch.

| Hạng mục | Phát hiện ban đầu | Xử lý / trạng thái hiện tại |
|---|---|---|
| `auto-train` | `flash_attention` chỉ được echo; `allow_test_data` không kiểm tra; output mở `w`, ghi đè model; không có `--distill-cache` | Cờ chưa tích hợp bị từ chối rõ ràng; test data cần opt-in; output dùng exclusive create; pipeline web riêng thực hiện distill thực |
| Linear compatibility | Validator nhận coefficient width 11 nhưng runtime dựng 14 features, khiến inference lỗi/fallback | Chọn đúng numeric schema 7/11/14 theo artifact; regression tests |
| 14 structural features | `numeric_view` đã có 14, nhưng linear train vẫn gọi `legacy_7=True` | Linear train/calibration dùng 14; giữ load model cũ |
| Pruning | Chưa có chọn features trong trainer | Chọn importance ≥1% trên train, refit GBDT và remap schema; calibration/runtime dùng cùng feature order. Chưa có bước Pearson correlation như plan |
| Pooler fallback | PyTorch tính multi-head; NumPy dùng full-vector dot product nên không tương đương | CPU NumPy tính đúng từng head, có kiểm tra parity toán học; không quảng cáo đây là CUDA FlashAttention |
| Pooler reproducibility | Python `hash(word)` khác giữa process; text features không tái lập | SHA-256 ổn định, có test hai process với PYTHONHASHSEED khác nhau |
| Semantic encoder | Text embedding là random projection; weights/query chỉ random init; không có ONNX weights hoặc optimizer học task queries | Đã triển khai `OnnxTokenEncoder` chuẩn hóa hash SHA-256, offline tokenizer, không download ngầm; đi kèm `attention.py` dùng PyTorch SDPA và NumPy CPU path có parity toán học |
| Shared tensor / “0 ms” | Có hàm nhận tensor nhưng chưa có port nối module Tân; attention pooling vẫn tốn thời gian | Đã thiết kế giao diện mở `SharedRepresentationPort` và `SharedRepresentation` theo kiến trúc Ports & Adapters; fallback độc lập về ONNX khi chưa ghép adapter của Tân |
| Drift | Class có buffer/threshold shift nhưng không có caller từ retry/tool/dislike hoặc quyết định route | Đã nối `RoutingDrift` và `RouterFeedbackService` vào DB và `PolicyRouter.select`; tự động dịch chuyển ngưỡng động (tối đa 15%) khi có tín hiệu lỗi/retry/dislike |
| Gemini limiter | Không khóa thread dù doc nói process-safe; retry mọi exception; write cache trực tiếp và nuốt lỗi | Shared-instance lock, atomic write, chỉ retry explicit 429 trong helper sync. Async pipeline paid không tự retry uncertain dispatch. Không hứa process-safe hay quota cố định |
| Nút một lần | Không có job API/UI; CLI chỉ train labeled dataset | Đã thêm collect/cache/live distill/train/HOLDOUT/import, tiến độ VI/EN, dedupe/owner/ledger; xem [hướng dẫn](ROUTER_TRAINING.md) |

Các vấn đề nghiên cứu còn phải xử lý trước khi công bố kết quả:

- `scripts/prepare_large_multidomain_dataset.py` tạo câu từ templates và gán labels theo giả định; tên miền/benchmark trong docstring không biến chúng thành dữ liệu thật của các benchmark đó. Model sinh từ đây chỉ dùng kiểm thử `software_test`, không nâng thành qualified.
- Downloader cũ chỉ xử lý VMLU và ViQuAD, không thực hiện 32 adapters của plan. Cắt `choices[:4]` có thể bỏ lựa chọn E có thật trong [VMLU JSONL](https://huggingface.co/datasets/tridm/VMLU/blob/main/train.jsonl); prefix choices cũng đã chứa A./B. Nguồn mirror/license/revision và các tập 50/200/600 lồng nhau không đủ để gọi 600 là HOLDOUT độc lập. Pipeline mới giữ toàn bộ options và split group; script cũ chưa được coi là nguồn qualified.
- `scripts/evaluate_real_benchmark.py` dùng F1≥0,5 **hoặc substring** làm pass ViQuAD, bắt cụm từ “không có thông tin” để pass unanswerable, và có bảng giá/fallback gán cứng cùng defaults usage=0. Đây không phải official ViQuAD scorer hoặc accounting đáng tin. Pipeline mới không dùng script này; chưa thay grader của Khoa. Cần qualification/deterministic graders trước báo cáo khoa học.
- Bản plan liệt kê tên/count của 32 datasets nhưng chưa kèm đủ original release/license/hash/schema. Không thể xác nhận từng bộ tồn tại/đủ quyền sử dụng chỉ từ danh sách đó.
- Không có bằng chứng cho ONNX 42MB, encoder 1,8–2,5ms, pooling <1,2ms, all-in router gần 0ms, hay savings/quality Gemini. Các mốc này là giả thuyết cần đo trên phần cứng và workload đóng băng.
- Teacher self-judging có bias; điểm calibrated router không phải xác suất một câu trả lời sẽ đúng. HOLDOUT pass quan sát được chưa chứng minh non-inferiority thống kê. Không tự promote candidate lên production.

Nguồn quota/API đối chiếu: [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai). Model IDs, access và giá phải review theo tài khoản tại thời điểm chạy; không lấy thứ tự “Lite/Flash/Pro” làm bảo đảm chất lượng.
