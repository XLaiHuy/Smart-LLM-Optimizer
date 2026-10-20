# HƯỚNG DẪN SỬ DỤNG BỘ AI AGENT SKILLS TRONG DỰ ÁN

Thư mục `.agents/skills/` chứa các gói hướng dẫn chuyên môn hóa (Agent Skills) dành cho các trợ lý AI (như Antigravity, Cursor, Claude Code, Cline, Windsurf...) khi làm việc trong dự án Smart LLM Platform.

---

## 1. Danh sách 8 Skills và Người sử dụng chính

| Tên Skill | Vị trí thư mục | Thành viên phụ trách | Khi nào nên áp dụng? |
|---|---|---|---|
| **`taste-skill`** | `.agents/skills/taste-skill/` | **Huy** (Web UI) | Khi thiết kế giao diện, chọn font, phối màu, căn chỉnh layout web để tránh AI-slop. |
| **`impeccable`** | `.agents/skills/impeccable/` | **Huy** (Web UI) | Khi làm Dashboard, biểu đồ Pareto, tinh chỉnh micro-interactions và responsive. |
| **`fastapi-sqlite-clean-arch`** | `.agents/skills/fastapi-sqlite-clean-arch/` | **Huy** (Backend Core) | Khi viết API FastAPI, xử lý concurrency SQLite WAL, viết DTOs Pydantic V2. |
| **`prompt-context-compaction`** | `.agents/skills/prompt-context-compaction/` | **Tân** (Prompt & Context) | Khi viết thuật toán bảo toàn ngữ nghĩa (từ "không", JSON), đo đạc token và cắt tỉa context. |
| **`llm-optimizer-router`** | `.agents/skills/llm-optimizer-router/` | **Huy** (Model Router) | Khi viết bộ phân loại tác vụ (Task Analyzer), thuật toán định tuyến model rẻ/mạnh. |
| **`eval-benchmark-graders`** | `.agents/skills/eval-benchmark-graders/` | **Khoa** (Eval & Graders) | Khi tải dataset tiếng Việt (IFEval, ViQuAD, VMLU), viết bộ chấm điểm tự động. |
| **`session-memory-management`** | `.agents/skills/session-memory-management/` | **Khoa** (Session Memory) | Khi viết thuật toán tóm tắt hội thoại nhiều lượt, ghim sự thật và giải quyết đính chính. |
| **`codegraph-navigation`** | `.agents/skills/codegraph-navigation/` | **Cả 3 bạn** | Khi tra cứu nhanh đồ thị hàm, tìm vị trí gọi code giữa các module mà không cần tìm thủ công. |

---

## 2. Cách AI Agent nhận diện và áp dụng Skills

* **Nhận diện phụ thuộc agent/IDE:** Không mặc định mọi công cụ đều tự quét `.agents/skills/`. Kiểm tra cấu hình của công cụ hoặc chỉ định rõ file skill cần đọc. Các quyết định hiện hành là UI trắng–xanh OU/Roboto, Việt–Anh và mock-only G0; xem [README](../README.md) và [handoff](G0_HANDOFF.md).
* **Chủ động nhắc AI (Explicit Prompting):**
  * Trong khung chat, bạn có thể gõ: `"Hãy áp dụng skill prompt-context-compaction để viết hàm optimize()"` hoặc `"Dùng skill taste-skill để chỉnh lại CSS trang Dashboard"`.
