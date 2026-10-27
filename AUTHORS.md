# Authors & Contributors

## Dự án Smart LLM Optimizer

Dự án **Smart LLM Optimizer** được nghiên cứu, thiết kế kiến trúc và phát triển bởi nhóm sinh viên thuộc **Trường Đại học Mở Thành phố Hồ Chí Minh (Ho Chi Minh City Open University - OU)** nhằm phục vụ khối thi Phần mềm Nguồn mở (FOSS) và các công bố khoa học ứng dụng AI.

Toàn bộ mã nguồn cốt lõi của dự án được phát hành dưới giấy phép mã nguồn mở tự do **MIT License**.

---

## 👥 Nhóm Tác Giả & Phân Trách Nhiệm (Core Team)

| Thành viên | Vai trò & Trách nhiệm chính | Module sở hữu (Code Ownership) | Email liên hệ chính thức |
|---|---|---|---|
| **Lại Quốc Huy** | **Trưởng nhóm / Kiến trúc sư Hệ thống** (Team Lead & System Architect) | Kiến trúc tổng thể (Clean Architecture), API Contracts, Auth & Security, Storage & Concurrency Engine (SQLite WAL), Quota & Financial Ledger, Provider Adapter Engine, Routing Algorithms & Dynamic Pareto Frontier, Frontend UI/UX & Shared Tooling | `2351010075huy@ou.edu.vn` |
| **Lưu Tân** | **Kỹ sư Tối ưu hóa Mô hình** (Optimizer & Evaluator Engineer) | Phân hệ Nén ngữ cảnh thích ứng (`backend/app/optimizers/`), Kiểm định bảo toàn thực thể ngữ nghĩa (Semantic Entity Preservation), Token Window Budget Manager | `tan.optimizer@ou.edu.vn` |
| **Lâm Khoa** | **Kỹ sư Bộ nhớ & Đánh giá Khoa học** (Memory & Benchmark Engineer) | Phân hệ Bộ nhớ hội thoại phân tầng (`backend/app/memory/`), Bộ tải dữ liệu đánh giá khoa học (`evaluation/`, `benchmark/`), Deterministic Graders, Paired Ablation Testing | `khoa.benchmark@ou.edu.vn` |

---

## 🏫 Đơn Vị Chủ Quản & Bảo Trợ Học Thuật

- **Cơ sở đào tạo**: **Trường Đại học Mở Thành phố Hồ Chí Minh (Ho Chi Minh City Open University - OU)**
- **Khoa**: Công nghệ Thông tin (Faculty of Information Technology)
- **Địa chỉ liên hệ**: 35-37 Hồ Hảo Hớn, Phường Cô Giang, Quận 1, TP. Hồ Chí Minh, Việt Nam
- **Website chính thức**: [https://ou.edu.vn](https://ou.edu.vn)

---

## 📜 Giấy Phép & Tuyên Bố Bản Quyền (License & Copyright)

- **Mã nguồn dự án**: Phát hành theo giấy phép **MIT License**. Chi tiết xem tại [LICENSE](LICENSE).
- **Quyền tác giả**: Bản quyền thuộc về **Nhóm tác giả Smart LLM Optimizer - Trường Đại học Mở TP.HCM** (© 2026).
- **Thư viện bên thứ ba**: Danh mục bản quyền và giấy phép của tất cả các thư viện phụ thuộc (Python dependencies, Node.js packages) được kiểm kê minh bạch tại [docs/THIRD_PARTY_INVENTORY.json](docs/THIRD_PARTY_INVENTORY.json) và [docs/ASSETS.md](docs/ASSETS.md).
- **Dữ liệu đánh giá**: Các tập dữ liệu benchmark (VMLU, UIT-ViQuAD 2.0, Legal-QA) giữ nguyên bản quyền nghiên cứu gốc từ các đơn vị công bố khoa học.

---

## 🤝 Đóng Góp Cộng Đồng (Community Contributions)

Dự án hoan nghênh mọi đóng góp từ cộng đồng nghiên cứu và phát triển phần mềm nguồn mở. Vui lòng tham khảo tài liệu [CONTRIBUTING.md](CONTRIBUTING.md) để nắm rõ:
- Quy trình phân nhánh và tích hợp mã nguồn (`feature/* → develop → main`).
- Quy chuẩn viết code (Python Strict Type Hints, Pydantic V2 Frozen DTOs, ESLint & TypeScript Strict).
- Các kênh giao tiếp và thảo luận kỹ thuật công khai của dự án.
