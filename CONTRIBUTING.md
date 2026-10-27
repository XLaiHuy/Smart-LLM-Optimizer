# Hướng Dẫn Đóng Góp (Contributing Guidelines)

Dự án **Smart LLM Optimizer** là một dự án phần mềm nguồn mở được phát triển dựa trên các nguyên tắc minh bạch, cộng tác và chuẩn mực kỹ thuật cao. Chúng tôi hoan nghênh mọi đóng góp từ cộng đồng học thuật và các nhà phát triển.

---

## 1. Kênh Giao Tiếp Công Khai & Triết Lý Nguồn Mở (Community & Communication Channels)

Trong văn hóa phần mềm tự do nguồn mở (FOSS), kênh giao tiếp không chỉ đơn thuần là nơi gửi tin nhắn, mà là **nền tảng tri thức mở (Open Knowledge Commons)** đảm bảo tính minh bạch (*transparency*), khả năng truy xuất lịch sử vĩnh viễn (*permanent public archiving*), và sự hợp tác bình đẳng không rào cản (*inclusive collaboration*).

Dự án thiết lập 3 kênh giao tiếp chuẩn mực, phản ánh sự kế thừa triết lý FOSS cổ điển (mailing list, IRC, bug tracker) kết hợp hạ tầng nguồn mở hiện đại:

### 🐛 1.1. Hệ Thống Theo Dõi Lỗi (Bug Tracker): GitHub Issues
- **Địa chỉ**: [GitHub Issues](https://github.com/XLaiHuy/Smart-LLM-Optimizer/issues)
- **Mục đích**: Báo cáo lỗi kỹ thuật (bug reports), đề xuất cải tiến (enhancement requests), thảo luận nhiệm vụ cụ thể và theo dõi tiến độ giải quyết vấn đề.
- **Quy trình báo lỗi chuẩn**:
  1. Kiểm tra danh sách issue đang mở để tránh trùng lặp (duplicate).
  2. Sử dụng tiêu đề rõ ràng, súc tích (ví dụ: `[Bug] SQLite busy timeout error during high-concurrency batch evaluation`).
  3. Cung cấp các bước tái hiện (reproduction steps), hành vi thực tế (actual behavior), hành vi mong đợi (expected behavior), và thông tin môi trường (HĐH Windows/Linux, phiên bản Python 3.11, Node 24).
  4. Đính kèm logs hoặc stack trace (lưu ý **tuyệt đối không để lộ API keys hoặc thông tin bí mật**).
- **Hệ thống nhãn (Labels taxonomy)**:
  - `bug`: Lỗi phần mềm cần sửa chữa.
  - `enhancement`: Đề xuất tính năng mới hoặc nâng cấp thuật toán.
  - `documentation`: Cập nhật, bổ sung tài liệu kỹ thuật hoặc báo cáo học thuật.
  - `research`: Vấn đề liên quan đến thuật toán định tuyến, nén prompt, benchmark datasets.
  - `good first issue`: Tác vụ phù hợp cho người mới bắt đầu làm quen với codebase.
  - `wontfix` / `duplicate`: Vấn đề không thực hiện hoặc đã có thảo luận tương tự.

### 📬 1.2. Hộp Thư Liên Lạc Chính Thức & Học Thuật (Mailing List / Official Contact)
- **Địa chỉ**: `2351010075huy@ou.edu.vn` (Trưởng nhóm: Lại Quốc Huy)
- **Mục đích**: 
  - Kênh trao đổi học thuật chính thức giữa các nhóm nghiên cứu, giảng viên hướng dẫn và các trường đại học.
  - Báo cáo lỗ hổng bảo mật nhạy cảm (Security Vulnerability Disclosure) trước khi công bố công khai theo quy trình Responsible Disclosure.
  - Thư từ hành chính, phối hợp tổ chức thi đấu và xác minh quyền sở hữu trí tuệ.
- **Bản chất FOSS**: Đóng vai trò tương đương *Core Team Mailing List* trong các dự án FOSS kinh điển (như Linux Kernel Mailing List, Apache Software Foundation), bảo đảm kênh liên hệ trực tiếp, tin cậy tới kiến trúc sư trưởng của hệ thống.

### 💬 1.3. Diễn Đàn Kỹ Thuật & Thảo Luận Mở (Community Discussions / Modern IRC)
- **Địa chỉ**: [GitHub Discussions](https://github.com/XLaiHuy/Smart-LLM-Optimizer/discussions)
- **Mục đích**: Nơi thảo luận tự do, hỏi đáp kiến trúc và chia sẻ ý tưởng mới mà không làm loãng bug tracker.
- **Bản chất FOSS**: Thay thế và hiện đại hóa giao thức IRC (Internet Relay Chat) / Matrix truyền thống. GitHub Discussions cho phép lưu trữ vĩnh viễn (public archiving), đánh chỉ mục tìm kiếm và hỗ trợ công thức toán KaTeX/LaTeX, mã nguồn syntax highlighting – đặc biệt thích hợp cho dự án nghiên cứu khoa học AI.
- **Các phân mục thảo luận**:
  - `Q&A`: Hỏi đáp về cách thiết lập môi trường, chạy benchmark, sử dụng API.
  - `Ideas & RFCs`: Yêu cầu lấy ý kiến (Request for Comments) về các cải tiến thuật toán Pareto, Attention Router, Context Compaction.
  - `Show and Tell`: Chia sẻ kết quả thử nghiệm mô hình, các ca sử dụng tối ưu hóa thực tế.
  - `General`: Thảo luận chung về xu hướng công nghệ Multi-LLM Routing.

---

## 2. Quy Trình Phân Nhánh & Tích Hợp (Git Branching Flow)

- Luồng nhánh chuẩn mực: `feature/* → develop → main`.
- **Tạo nhánh**: Tạo nhánh tính năng `feature/<ten-tinh-nang>` xuất phát từ `develop`.
- **Đồng bộ hóa**: Luôn `git pull origin develop` và rebase/merge trước khi yêu cầu review.
- **Nhánh `develop`**: Nhánh tích hợp thường trực, kiểm thử tự động toàn diện trước khi phát hành.
- **Nhánh `main`**: Giữ bản phát hành ổn định tuyệt đối đã qua nghiệm thu để nộp sản phẩm / công bố release.
- **Yêu cầu đối với Pull Request (PR)**:
  - Nêu rõ vấn đề được giải quyết (Problem statement / Motivation).
  - Liệt kê các module/files bị thay đổi.
  - Nếu thay đổi Contract/Schema: Bắt buộc cập nhật cả Producer, Consumer, Unit Tests và generated TypeScript types trong cùng một PR (`npm run contracts:generate`).
  - Ghi nhận các lệnh kiểm thử đã chạy thực tế (`pytest`, `npm test`, `npm run lint`).
  - Giữ PR tập trung, không reformat hoặc thay đổi cấu trúc mã nguồn của module khác ngoài phạm vi.

---

## 3. Quy Chuẩn Lập Trình & Chất Lượng Mã Nguồn (Code Standards)

### Backend (Python):
- **Phiên bản**: Python 3.11+.
- **Type Safety**: Bắt buộc khai báo kiểu đầy đủ (strict type hints). Kiểm tra tĩnh nghiêm ngặt qua `mypy`.
- **Data Transfer Objects (DTOs)**: Định nghĩa immutable DTOs qua Pydantic V2 (`frozen=True`) hoặc Python `dataclasses(frozen=True)`.
- **Linter & Formatter**: Tuân thủ triệt để cấu hình `ruff format` và `ruff check`. Không để sót warning.
- **Clean Architecture**: Áp dụng triệt để kiến trúc Lục giác (Ports & Adapters). Logic nghiệp vụ độc lập hoàn toàn với framework và thư viện ngoài.

### Frontend (TypeScript / Next.js):
- **Phiên bản**: Next.js 15+ App Router, Node 24, npm 11.
- **Type Safety**: TypeScript Strict Mode (`noImplicitAny: true`, `strictNullChecks: true`). Sử dụng kiểu sinh tự động từ backend OpenAPI specs.
- **Style & UI**: Tuân thủ chuẩn nhận diện Trường Đại học Mở TP.HCM (OU Blue `#005696`, White crisp background). Tuyệt đối không dùng icon trang trí bừa bãi (anti-slop).
- **Đa ngôn ngữ**: Toàn bộ chuỗi hiển thị qua bộ dịch Song ngữ Tiếng Việt / Tiếng Anh (`src/lib/i18n.ts`).

---

## 4. Kiểm Thử & An Toàn Dữ Liệu (Testing & Security Invariants)

- **Nguyên tắc Ngoại Tuyến (Offline-by-Default)**:
  - Mọi Unit Test, Integration Test và CI pipeline mặc định chạy ở chế độ **Mock / Offline**.
  - **Tuyệt đối không gọi Paid API** (OpenAI, Anthropic, v.v.) trong các bộ kiểm thử tự động hoặc môi trường CI.
- **Bảo mật Bí mật (Secrets Zero-Leakage)**:
  - Không bao giờ commit file `.env`, API keys, tokens, file cơ sở dữ liệu (`*.db`), hoặc dữ liệu riêng tư của người dùng vào Git.
  - Sử dụng `.env.example` làm mẫu cấu hình chuẩn.
- **Kiểm thử Hành vi Rủi ro Cao**:
  - Tập trung kiểm thử các điểm trọng yếu: Race conditions, cô lập giao dịch SQLite WAL, cơ chế bọc Ledger `asyncio.shield`, tính toàn vẹn của Quota tài chính, và các luồng kiểm thử giao diện Playwright Chromium.

---

## 5. Phân Trách Nhiệm Module (Code Ownership)

- **Lại Quốc Huy**: Sở hữu Contracts, API Core, Auth & Session, Storage/Migrations, Concurrency Engine, Financial Ledger, Provider Adapters, Routing Policies, Router Lab UI/API, Shared Tooling.
- **Lưu Tân**: Sở hữu Phân hệ Nén ngữ cảnh thích ứng (`backend/app/optimizers/`), Token Window Budgeting, và Semantic Entity Preservation.
- **Lâm Khoa**: Sở hữu Phân hệ Bộ nhớ dài hạn (`backend/app/memory/`), Scientific Benchmark Loaders (`evaluation/`, `benchmark/`), Deterministic Graders và Báo cáo kiểm định thống kê.
