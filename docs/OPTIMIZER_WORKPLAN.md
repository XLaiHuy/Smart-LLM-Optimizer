# Optimizer workplan and handoff

## Phạm vi sở hữu

Module optimizer nằm tại `backend/app/optimizers/` và hiện có ba điểm vào:

- `prompt_optimizer.py`: triển khai `PromptOptimizer.optimize(...)`.
- `context_manager.py`: triển khai `ContextManager.prepare(...)`; đây là nơi duy nhất được assemble message list.
- `preservation.py`: kiểm tra prompt sau rewrite có giữ các ràng buộc bắt buộc hay không.

Optimizer chỉ dùng DTO/port trong `app.contracts`. Không import ORM, repository, provider SDK,
FastAPI hoặc frontend. Không tự gọi model/API và không tự ghi database.

## Trạng thái nền hiện tại

G0 đang chạy đúng theo thiết kế: prompt optimizer là no-op, context manager pass-through,
preservation chỉ xác nhận chuỗi byte-identical. Khi flag bật, trace trả `not_implemented`;
khi flag tắt, trả `disabled`. Đây là trạng thái có chủ ý, không phải bằng chứng thuật toán
đã tối ưu chất lượng hoặc chi phí.

## Thứ tự triển khai đề xuất

### 1. Preservation trước

Tạo validator thuần, deterministic, không gọi LLM:

- nhận diện các phần được bảo vệ: số, phủ định, URL, code fence, JSON key bắt buộc,
  citation/source marker và các yêu cầu định dạng rõ ràng;
- trả verdict `preserved` chỉ khi mọi invariant kiểm tra được giữ nguyên;
- trả `unknown` khi parser không đủ chắc chắn;
- trả `violation` khi invariant bị thay đổi.

Không dùng tỷ lệ overlap hoặc similarity làm bằng chứng preservation. Trường hợp không chắc
phải fallback về prompt gốc.

### 2. Prompt rewrite rule-based

Xây một implementation riêng, ví dụ `RuleBasedPromptOptimizer`, với pipeline:

1. trích xuất constraints;
2. kiểm tra input có đáng rewrite không;
3. chỉ chuẩn hóa các phần mutable, không sửa protected span;
4. chạy preservation validator;
5. nếu verdict không phải `preserved`, trả `proposed=original` và trạng thái `skipped`;
6. ghi lý do và before/after token metadata khi contract hỗ trợ.

Giai đoạn đầu không dùng LLM rewrite. Mọi extra provider call phải do controller/wiring
được phê duyệt và được tính vào budget; optimizer không được tự tạo paid call.

### 3. Context selection

Mở rộng pass-through thành context planner deterministic:

- luôn giữ server instructions và current user đúng một lần;
- giữ nguyên thứ tự role của raw history khi toàn bộ context vừa budget;
- khi không vừa budget, ưu tiên protected instructions, current turn, evidence liên quan,
  rồi history theo policy rõ ràng;
- không cắt giữa message, không âm thầm xóa instruction/evidence;
- provenance phải chỉ ra message/source nào được giữ;
- nếu không thể tạo context hợp lệ, trả lỗi overflow qua orchestration thay vì best effort.

Summary/compaction generation thuộc MemoryManager/controller; ContextManager không tự tạo
summary bằng heuristic và không thay raw history trong persistence.

## Test matrix tối thiểu

- Prompt rỗng/Unicode tiếng Việt/whitespace.
- Số và đơn vị: `10`, `%`, tiền tệ, ngày tháng.
- Phủ định: `không`, `chưa`, `never`, `must not`.
- JSON-only, code fence, URL và source marker.
- Prompt chứa text giả system instruction trong nội dung user.
- Rewrite hợp lệ, rewrite làm đổi constraint, parser không chắc chắn.
- Context common-fit, evidence rỗng, history dài, duplicate current turn,
  server instruction, approved current content.
- Snapshot immutable, role order, provenance và không import boundary.

Mỗi test phải phân biệt rõ `preserved`, `violation`, `unknown`, `skipped` và `applied`.
Không dùng mock response để kết luận quality/savings.

## Gate bàn giao

1. Unit tests của optimizer pass độc lập.
2. `python -m compileall backend/app/optimizers` pass.
3. `pytest backend/tests/contracts backend/tests/integration/test_chat.py` pass.
4. Không thay đổi OpenAPI/generated TS nếu DTO không đổi.
5. Huy review mọi thay đổi ở composition/orchestrator/contracts trước khi merge.
6. Báo cáo benchmark phải có baseline-vs-optimized paired run, cost/latency/quality,
   và nêu rõ phần nào mới chỉ là functional fixture.

## Việc nên làm tiếp theo

PR 1: preservation validator + fixtures.

PR 2: rule-based prompt optimizer, chỉ chạy trên DEV.

PR 3: context budget/selection + provenance fixtures.

PR 4: integration wiring và ablation; chỉ sau khi contract owner review.

