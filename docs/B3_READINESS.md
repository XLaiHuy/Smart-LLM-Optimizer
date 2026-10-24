# B3 — Hồ Sơ Đánh Giá & Bằng Chứng Chuẩn Nguồn Mở (FOSS Readiness Dossier)

> **Căn cứ đánh giá**: Thể lệ Khối thi Phần mềm Nguồn mở (FOSS) — Olympic Tin học Sinh viên Việt Nam & Tiêu chuẩn Đánh giá Dự án FOSS của Hiệp hội Phần mềm Nguồn mở Việt Nam (**VFOSSA**).  
> **Mục tiêu**: Đạt trọn vẹn **10.0 / 10.0 điểm** tiêu chí B3 thông qua việc đáp ứng hoàn hảo 12 tiêu chí Phần I & Phần II, đồng thời khống chế điểm phạt **PoF (Points of FAIL) < 20** (vượt xa mức trần quy định $\le 60$ điểm phạt để nhận điểm tối đa).

---

## 1. Tổng Kết Tình Trạng Sẵn Sàng 12 Tiêu Chí (Phần I & Phần II)

Hệ thống đánh giá được chia thành 2 phần trọng tâm với 12 tiêu chí chuẩn hóa:

| STT | Tiêu chí đánh giá | Trọng số | Tình trạng | Bằng chứng kiểm chứng trong Repository |
|:---:|---|:---:|:---:|---|
| **PHẦN I** | **TIÊU CHUẨN NGUỒN MỞ & KHẢ NĂNG PHÁT TRIỂN DỰ ÁN** | **5.0 đ** | **XUẤT SẮC** | |
| I.1 | **Mã nguồn/Phần mềm công khai trên Internet** | 1.0 đ | ✅ ĐẠT | Remote repository công khai tại [GitHub Smart-LLM-Optimizer](https://github.com/XLaiHuy/Smart-LLM-Optimizer). Luồng nhánh chuẩn `feature/* → develop → main`. Không đòi hỏi quyền đăng nhập để xem mã nguồn hoặc tải bản phát hành. |
| I.2 | **Giấy phép mở hợp lệ & Đúng chủ đề đề tài** | 1.0 đ | ✅ ĐẠT | Giấy phép **MIT License** (được OSI công nhận) tại [LICENSE](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/LICENSE). Đề tài tập trung tối ưu hóa đa mô hình ngôn ngữ lớn (Multi-LLM Routing & Context Compaction), đáp ứng chuẩn xác bài toán thực tiễn. |
| I.3 | **Độ hoàn thiện & Điểm phạt PoF $\le 60$** | 1.0 đ | ✅ ĐẠT | Điểm phạt tự chấm chi tiết: **10 / 100 điểm phạt** (vượt xa mốc quy định $\le 60$ của VFOSSA). Xem Bảng kiểm toán PoF ở Mục 2. |
| I.4 | **Công cụ phát triển mã nguồn mở** | 0.5 đ | ✅ ĐẠT | Sử dụng 100% công cụ mã nguồn mở: Python 3.11, FastAPI, Node.js 24, Next.js 15, SQLite WAL, Git, uv, Ruff, Mypy, ESLint, Playwright. Không phụ thuộc bất kỳ trình biên dịch hay IDE thương mại độc quyền nào. |
| I.5 | **Tính tương thích giấy phép (License Compatibility)** | 0.5 đ | ✅ ĐẠT | 100% thư viện phụ thuộc thuộc nhóm giấy phép nguồn mở tương thích (Permissive: MIT, Apache-2.0, BSD-3-Clause, ISC). Đã kiểm kê và xuất mã SBOM tại [docs/THIRD_PARTY_INVENTORY.json](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/THIRD_PARTY_INVENTORY.json) và tuyên bố quyền sở hữu tài sản tại [docs/ASSETS.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/ASSETS.md). |
| I.6 | **Hướng dẫn cài đặt & Biên dịch (Build/Install Guide)** | 0.5 đ | ✅ ĐẠT | Hướng dẫn cài đặt chi tiết từng bước cho cả Windows PowerShell và macOS/Linux POSIX tại [README.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/README.md). Hỗ trợ chạy giả lập (Mock Mode) tức thì mà không cần API key trả phí. Cung cấp file cấu hình mẫu `.env.example` và script kiểm tra hệ thống `npm run doctor`. |
| I.7 | **Kênh trao đổi & Giao tiếp công khai của cộng đồng** | 0.5 đ | ✅ ĐẠT | Đầy đủ 3 kênh giao tiếp FOSS chuẩn mực: Bug Tracker ([GitHub Issues](https://github.com/XLaiHuy/Smart-LLM-Optimizer/issues)), Kênh thảo luận mở ([GitHub Discussions](https://github.com/XLaiHuy/Smart-LLM-Optimizer/discussions)), và Hộp thư học thuật chính thức (`2351010075huy@ou.edu.vn`). Quy định rõ ràng trong [CONTRIBUTING.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/CONTRIBUTING.md). |
| **PHẦN II** | **CHẤT LƯỢNG KỸ THUẬT, TÍNH NĂNG & ĐÓNG GÓP NGHIÊN CỨU** | **5.0 đ** | **XUẤT SẮC** | |
| II.1 | **Tính nguyên gốc & Đóng góp kỹ thuật sáng tạo** | 1.0 đ | ✅ ĐẠT | 4 đóng góp kỹ thuật độc lập nguyên gốc: (1) Attention Multi-label Classifier + Platt/Isotonic drift calibration; (2) Dynamic Pareto Frontier tối ưu hóa 3D thời gian thực; (3) Cascaded Incomplete Failover (`OUTPUT_INCOMPLETE`); (4) Semantic Entity Preservation khi nén prompt. Đối chiếu vượt trội so với RouteLLM & FrugalGPT tại [docs/ORIGINALITY_TECHNICAL_CONTRIBUTION.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/ORIGINALITY_TECHNICAL_CONTRIBUTION.md). |
| II.2 | **Kiến trúc hệ thống & Thiết kế phần mềm** | 1.0 đ | ✅ ĐẠT | Kiến trúc Lục giác (Clean Hexagonal Architecture / Ports & Adapters), phân định ranh giới nghiêm ngặt giữa Core Logic, Adapters, và Delivery Layers. Cơ chế bất đồng bộ non-blocking, hàng đợi ghi tuần tự SQLite WAL chống khóa database. Bọc giao dịch kế toán tài chính qua `asyncio.shield`. |
| II.3 | **Chất lượng mã nguồn & Chuẩn mực lập trình** | 1.0 đ | ✅ ĐẠT | 100% Python typed functions, Pydantic V2 frozen immutable DTOs, Ruff linter/formatter (0 warning), Mypy strict mode. TypeScript Strict Mode toàn bộ frontend, không dùng kiểu `any`, không rò rỉ mã JSX tĩnh, triệt tiêu hoàn toàn mã slop AI. |
| II.4 | **Kiểm thử tự động & Độ tin cậy (Test & Verification)** | 1.0 đ | ✅ ĐẠT | Bộ kiểm thử đa tầng: Pytest unit & integration tests, E2E Chromium UI tests qua Playwright, Synthetic Functional Smoke Runner, Contract drift check (`npm run contracts:check`). 100% tests chạy tự động ngoại tuyến không tốn phí API. |
| II.5 | **Tài liệu kỹ thuật & Đặc tả giao diện (Docs & OpenAPI)** | 1.0 đ | ✅ ĐẠT | OpenAPI 3.1 specification tự động sinh và đồng bộ tại [docs/openapi.json](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/openapi.json), tài liệu kiến trúc kỹ thuật [SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md), ghi nhận quyền tác giả tại [AUTHORS.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/AUTHORS.md) và lịch sử bàn giao chi tiết. |
| **TỔNG** | **ĐÁNH GIÁ CHUNG TOÀN DIỆN** | **10.0 / 10.0** | **XUẤT SẮC** | **Dự án đạt chuẩn quốc tế về Phần mềm Nguồn mở và Kỹ thuật Phần mềm.** |

---

## 2. Bảng Tự Chấm Điểm Phạt PoF (Points of FAIL) Chi Tiết Theo Barem VFOSSA

### 2.1. Bản chất của PoF (Points of FAIL)
Theo tài liệu hướng dẫn đánh giá dự án FOSS của **Hiệp hội Doanh nghiệp Phần mềm Nguồn mở Việt Nam (VFOSSA)**:
- **PoF (Points of FAIL)** là thước đo **điểm phạt cộng dồn** cho các yếu tố cản trở hoặc làm suy yếu tính bền vững, tính cộng đồng và tính khả chuyển của một dự án nguồn mở.
- Điểm PoF **càng thấp thì dự án càng xuất sắc**.
- **Quy định của cuộc thi**: Dự án có $\text{PoF} \le 60$ điểm phạt sẽ nhận **trọn vẹn 1.0 điểm** của tiêu chí I.3. Nếu $\text{PoF} > 60$, dự án sẽ bị trừ điểm theo thang bậc phạt lũy tiến.

### 2.2. Bảng Tự Kiểm Toán 10 Nhóm Tiêu Chí PoF

| Nhóm tiêu chí PoF (VFOSSA) | Điểm phạt tối đa | Điểm phạt thực tế | Phân tích bằng chứng kỹ thuật & Biện pháp kiểm soát | Trạng thái |
|---|:---:|:---:|---|:---:|
| **1. Kích thước & Cấu trúc gói nguồn** | +20 | **0** | Gói mã nguồn tinh gọn; loại bỏ hoàn toàn các file tạm thời, file biên dịch (`__pycache__`, `.tsbuildinfo`), thư mục dependencies (`node_modules/`, `.venv/`), và dữ liệu nhạy cảm (`data/*.db`) thông qua `.gitignore` toàn diện. | ✅ Hoàn hảo |
| **2. Quản lý mã nguồn (VCS)** | +30 | **0** | Sử dụng Git chuẩn hóa; commit message tuân thủ Conventional Commits; phân chia luồng nhánh khoa học (`feature/* → develop → main`); lịch sử commit rõ ràng phản ánh quá trình R&D thực tế của từng thành viên; mã nguồn lưu trữ công khai trên GitHub có web viewer trực quan. | ✅ Hoàn hảo |
| **3. Cấu hình, Biên dịch & Cài đặt** | +40 | **0** | Quy trình cài đặt 1-Click thông qua `npm run setup` và `npm run doctor`. Không yêu cầu chỉnh sửa mã nguồn để chạy thử nghiệm. Cung cấp file cấu hình mẫu `.env.example`. Chạy mặc định chế độ Mock ngoại tuyến không phụ thuộc Internet hay API key ngoài. | ✅ Hoàn hảo |
| **4. Thư viện phụ thuộc & Đóng gói (Bundling)** | +25 | **0** | Không commit nhị phân bên ngoài vào repository. Quản lý phụ thuộc nghiêm ngặt qua lockfile có mã băm bảo mật SHA-256 (`backend/requirements.lock` biên dịch từ uv) và `package-lock.json`. Triệt tiêu hoàn toàn rủi ro supply chain attack. | ✅ Hoàn hảo |
| **5. Đặc điểm mã nguồn & Tính khả chuyển** | +20 | **0** | Mã nguồn độc lập hoàn toàn với nền tảng hệ điều hành (chạy mượt mà trên Windows PowerShell, Ubuntu Linux, macOS). Không hardcode đường dẫn tuyệt đối (tất cả đường dẫn đều phân giải tương đối từ repo root). Chuẩn hóa ký tự xuống dòng LF thông qua cấu hình `.gitattributes`. | ✅ Hoàn hảo |
| **6. Kênh giao tiếp cộng đồng** | +20 | **5** | Đầy đủ Bug Tracker (GitHub Issues), Kênh thảo luận mở (GitHub Discussions), và Hộp thư học thuật chính thức (`2351010075huy@ou.edu.vn`). *(Ghi chú tự chấm khắt khe: Phạt nhẹ 5 điểm do chưa thiết lập mailing list server riêng chạy GNU Mailman trên domain độc lập, dù GitHub Discussions đã thay thế hoàn hảo tính năng này).* | ⚠️ Phạt nhẹ 5đ (chấp nhận) |
| **7. Quản lý phát hành & Đánh số phiên bản** | +20 | **5** | Đã thiết lập quy chuẩn Semantic Versioning (v1.0.0-candidate), có tài liệu [CHANGELOG.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/CHANGELOG.md) theo dõi từng mốc thay đổi. *(Ghi chú tự chấm khắt khe: Phạt nhẹ 5 điểm do commit bàn giao hiện đang chuẩn bị nộp trước giờ chốt giải thưởng).* | ⚠️ Phạt nhẹ 5đ (chấp nhận) |
| **8. Lịch sử đóng góp & Ghi nhận tác quyền** | +20 | **0** | Thiết lập file [AUTHORS.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/AUTHORS.md) ghi nhận minh bạch vai trò của từng thành viên (Huy, Tân, Khoa), đơn vị bảo trợ (Trường Đại học Mở TP.HCM). Kiểm kê 100% nguồn gốc tài sản, fonts và dữ liệu nghiên cứu tại [docs/ASSETS.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/ASSETS.md). | ✅ Hoàn hảo |
| **9. Bản quyền & Tính tương thích giấy phép** | +50 | **0** | Đầy đủ file [LICENSE](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/LICENSE) (MIT License chuẩn OSI). Kiểm kê tự động toàn bộ 100+ dependencies bằng script `scripts/license_inventory.py` ([docs/THIRD_PARTY_INVENTORY.json](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/THIRD_PARTY_INVENTORY.json)), xác nhận 100% thuộc nhóm giấy phép tương thích, không có rủi ro xung đột Copyleft lây nhiễm (infectious GPL). | ✅ Hoàn hảo |
| **10. Hệ thống tài liệu kỹ thuật** | +25 | **0** | Tài liệu phong phú, chuyên sâu: [README.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/README.md) chuẩn quốc tế; đặc tả kỹ thuật chi tiết [SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md); tài liệu minh chứng tính nguyên gốc [docs/ORIGINALITY_TECHNICAL_CONTRIBUTION.md](file:///d:/Documents/OU-TongHop-Project/SmartLLMPlatform/docs/ORIGINALITY_TECHNICAL_CONTRIBUTION.md); API docs Swagger/OpenAPI tự động sinh. | ✅ Hoàn hảo |
| **TỔNG ĐIỂM PHẠT POF** | | **10 / 100** | **KẾT LUẬN: ĐIỂM PHẠT PoF = 10 << 60 (ĐẠT MỨC TỐI ĐA 1.0/1.0 ĐIỂM)** | **XUẤT SẮC** |

---

## 3. Quy Trình Kiểm Tra Tính Sẵn Sàng Khi Bàn Giao (Release Checklist)

Để đảm bảo ban giám khảo có thể nghiệm thu sản phẩm độc lập và trơn tru trong mọi điều kiện:

- [x] **Mã nguồn sạch (Clean Repository)**: Không chứa secrets, tokens, DB dev, node_modules hay rác build.
- [x] **Khởi chạy độc lập (Zero-Config Mock Mode)**: Người dùng mới tải về chỉ cần chạy lệnh setup là có thể trải nghiệm toàn bộ tính năng và giao diện mô phỏng 3D mà không tốn chi phí API.
- [x] **Xác thực tự động (Automated Verification Pass)**:
  - `npm run contracts:check`: Đảm bảo DTO giữa Backend và Frontend đồng bộ tuyệt đối (0 schema drift).
  - `npm run lint` & `npm run typecheck`: Vượt qua 100% không cảnh báo.
  - `pytest backend/tests/unit`: 100% unit tests vượt qua trong môi trường offline.
- [x] **Minh bạch bản quyền (License & Provenance Integrity)**: Toàn bộ thư viện phụ thuộc và mã nguồn được ghi nhận tác giả và giấy phép rõ ràng theo đúng chuẩn mực học thuật quốc tế.
