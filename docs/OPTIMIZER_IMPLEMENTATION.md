# Optimizer Implementation

## Phạm vi

Tài liệu này ghi lại các phần đã triển khai trong nhóm optimizer:

- Phân tích prompt và token.
- Rule-based compression.
- Model-based compression qua LLMLingua-2.
- Strategy selection và fallback.
- Preservation validation.
- Hybrid context selection.
- Context summarization abstraction.
- Context optimizer orchestration.

## Các module đã hoàn thiện

### Prompt Analyzer

File: `backend/app/optimizers/prompt_analyzer.py`

Analyzer thực hiện:

- Đếm token bằng `tiktoken` với encoding `cl100k_base`.
- Phát hiện code block.
- Phát hiện URL, bao gồm Markdown URL.
- Phát hiện JSON key.
- Phát hiện phủ định tiếng Anh và tiếng Việt.
- Phát hiện số, phần trăm và đơn vị như `USD`, `VND`, `kg`, `km`.
- Tạo các protected spans kèm vị trí trong prompt.
- Loại bỏ protected span trùng nhau.

### Rule-based Compressor

File: `backend/app/optimizers/compressor.py`

Compressor hiện tại chỉ chuẩn hóa whitespace ngoài code block:

- Xóa trailing whitespace.
- Gộp từ ba dòng trống trở lên thành hai dòng.
- Không thay đổi nội dung code block.
- Không áp dụng nếu prompt dưới ngưỡng token.
- Không áp dụng nếu mất protected span.
- Không áp dụng nếu không tiết kiệm token.

Kết quả trả về gồm:

- Prompt gốc và prompt sau nén.
- Token trước/sau.
- Số token tiết kiệm.
- Compression ratio.
- Status và reason.

### Strategy Selector

File: `backend/app/optimizers/strategy_selector.py`

Chiến lược được chọn theo thứ tự:

1. `skip` nếu prompt ngắn hơn ngưỡng.
2. `rule_based` nếu có code hoặc JSON.
3. `rule_based` nếu model không khả dụng.
4. `llmlingua2` nếu prompt dài hơn ngưỡng LLMLingua.
5. `rule_based` cho các trường hợp còn lại.

Các threshold không hợp lệ sẽ bị từ chối bằng `ValueError`.

### Preservation Validator

File: `backend/app/optimizers/preservation.py`

Validator kiểm tra:

- Prompt nén không được rỗng.
- Protected spans không bị mất.
- Rule-based output phải tương ứng với whitespace normalization.
- Summary hoặc compression không được tự đánh dấu hợp lệ nếu provenance không đúng.

Hàm `check_preservation()` vẫn được giữ để tương thích với các caller cũ.

### Adaptive Prompt Optimizer

File: `backend/app/optimizers/prompt_optimizer.py`

`AdaptivePromptOptimizer` điều phối:

```text
Prompt Analyzer
        ↓
Strategy Selector
        ↓
Skip / Rule-based / LLMLingua-2
        ↓
Preservation + token validation
        ↓
Applied hoặc fallback về prompt gốc
```

Các trường hợp LLMLingua sau đều fallback an toàn:

- Model bị lỗi hoặc không khả dụng.
- Kết quả không có preservation hợp lệ.
- Prompt sau nén không tiết kiệm token.
- Kết quả không đúng kiểu dữ liệu mong đợi.

### LLMLingua-2 Compressor

File: `backend/app/optimizers/llmlingua_compressor.py`

Wrapper cung cấp:

- CPU inference qua LLMLingua-2.
- Token count trước/sau bằng `tiktoken`.
- Savings và ratio.
- `status`.
- `preservation`.

LLMLingua được import động trong constructor để CI vẫn chạy được khi package model chưa được cài. Model chỉ được load khi tính năng được bật.

### Hybrid Context Selection

Các file liên quan:

- `backend/app/optimizers/context_selection.py`
- `backend/app/optimizers/context_manager.py`

Context pipeline hiện có:

- Giữ system instructions.
- Giữ current user message.
- Ưu tiên các turn gần nhất.
- Chọn các turn cũ theo relevance và recency.
- Kiểm tra tổng token sau khi chọn.
- Loại bỏ history cũ nếu context vẫn vượt budget.
- Fallback rõ ràng khi mandatory context vượt budget.

`PassThroughContext` giữ nguyên raw history khi hybrid context bị tắt.

### Context Summarizer

File: `backend/app/optimizers/context_summarizer.py`

Module mới cung cấp:

- `SummaryGenerator` async dependency injection.
- `SummaryValidator`.
- `ContextSummarizer`.

Validator yêu cầu summary:

- Có nội dung.
- Đúng session revision.
- Có ít nhất một source message.
- Tất cả source message ID phải thuộc snapshot hiện tại.
- Không có duplicate covered message ID.

Summary không hợp lệ sẽ trả về `None` để caller fallback.

### Context Optimizer

File: `backend/app/optimizers/context_optimizer.py`

Module mới điều phối:

1. Chọn history bằng `HybridContextManager`.
2. Xác định các message bị loại khỏi context.
3. Gửi phần bị loại cho `ContextSummarizer` nếu có.
4. Validate summary.
5. Chèn summary trước current user message.
6. Kiểm tra lại token budget.
7. Fallback về context đã chọn nếu summary không hợp lệ hoặc vượt budget.

Summary được đưa vào provenance theo dạng:

```text
summary:<revision>:<covered_message_ids>
```

## Kiểm thử

Các test đã bổ sung hoặc cập nhật cho:

- Rule-based compression.
- Prompt analyzer.
- Preservation.
- Strategy selector.
- Adaptive prompt optimizer.
- Hybrid context manager.
- Context summarizer.
- Context optimizer.
- Context benchmark cho 4 cấu hình.

Kết quả kiểm tra optimizer hiện tại:

```text
38 passed
ruff check: pass
mypy optimizer: pass
```

## Benchmark context

File `backend/app/optimizers/context_benchmark.py` cung cấp benchmark không gọi
provider thật, dùng để so sánh công bằng bốn cấu hình:

1. `full_history`: gửi toàn bộ history.
2. `hybrid_only`: chọn history bằng relevance + recency.
3. `summary_only`: thay history bằng một summary đã validate.
4. `hybrid_summary`: chọn history trước, rồi tóm tắt phần bị loại.

Mỗi kết quả ghi nhận:

- token của context cuối;
- token input/output của lần sinh summary;
- tổng token gồm cả chi phí summary;
- latency sinh summary;
- estimated cost theo input/output price per million;
- factual consistency dựa trên `SessionSnapshot.facts`.

`factual_consistency` là deterministic smoke metric: fact chỉ được tính là
preserved khi value xuất hiện trong summary. Kết quả này không thay thế
entailment judge hoặc đánh giá chất lượng ngữ nghĩa bằng người.

Chạy test benchmark:

```powershell
cd D:\optimizer\Smart-LLM-Optimizer
$env:TIKTOKEN_CACHE_DIR="D:\optimizer\tiktoken-cache"
.\.venv\Scripts\python.exe -X utf8 -m pytest backend\app\optimizers\test_context_benchmark.py -q
```

Chi phí summary được tính vào `total_tokens` và `estimated_cost_usd`; không
chỉ đo request cuối. Khi nối generator thật vào production, cần mở rộng
metering `CallRecord` với stage summary và ghi usage/provider cost của call đó.

Lệnh chạy từ thư mục repository:

```powershell
cd D:\optimizer\Smart-LLM-Optimizer

$env:TIKTOKEN_CACHE_DIR="D:\optimizer\tiktoken-cache"

.\.venv\Scripts\python.exe -X utf8 -m pytest backend\app\optimizers -q
```

## Cấu hình tích hợp

Các config liên quan:

```env
ADAPTIVE_PROMPT_ENABLED=false
HYBRID_CONTEXT_ENABLED=false
CONTEXT_TOKEN_BUDGET=8000
```

Mặc định các tính năng tối ưu vẫn tắt để không thay đổi behavior G0. Có thể bật Adaptive Prompt Optimizer bằng:

```env
ADAPTIVE_PROMPT_ENABLED=true
```

## Phần chưa hoàn tất

`ContextOptimizer` và `ContextSummarizer` đã có implementation độc lập cùng unit tests, nhưng chưa được nối trực tiếp vào orchestrator production.

Lý do: `ContextManager.prepare()` hiện là synchronous, trong khi summarization có thể gọi dependency async. Muốn bật summary trong request pipeline cần thống nhất tiếp contract async của context orchestration với owner phần core/orchestrator.

Raw history vẫn là source of truth. Summary không thay thế raw history và không tự ghi database.

