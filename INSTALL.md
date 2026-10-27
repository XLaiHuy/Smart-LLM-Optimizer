# Hướng Dẫn Cài Đặt và Triển Khai Hệ Thống Smart LLM Optimizer

Tài liệu hướng dẫn chi tiết, độc lập và toàn diện các phương thức cài đặt, khởi chạy và kiểm tra hệ thống **Smart LLM Optimizer** (Đại học Mở TP.HCM - OU).

---

## 1. Yêu Cầu Tiên Quyết (Prerequisites)

Hệ thống hỗ trợ 3 phương thức triển khai chính:

| Phương thức | Docker / Engine | Python Runtime | Node.js Runtime | Khuyến nghị |
|:---|:---:|:---:|:---:|:---:|
| **Cách 1: Docker Compose** | Docker 24+ & Compose v2+ | Đã đóng gói trong image | Đã đóng gói trong image | ⭐⭐⭐⭐⭐ (Khuyên dùng) |
| **Cách 2: Windows PowerShell** | Không bắt buộc | Python 3.11.x (64-bit) | Node.js 24.x & npm 11.x | ⭐⭐⭐⭐ (Phát triển native) |
| **Cách 3: Linux / macOS** | Không bắt buộc | Python 3.11.x (64-bit) | Node.js 24.x & npm 11.x | ⭐⭐⭐⭐ (Server / Unix dev) |

> [!NOTE]
> Ứng dụng chạy mặc định ở chế độ **Mock Provider** (`PROVIDER_MODE=mock`), không yêu cầu GPU, không phát sinh chi phí và không gọi API bên ngoài khi phát triển hoặc chạy kiểm thử.

---

## 2. Kiến Trúc Triển Khai Container

```mermaid
graph TD
    Client["Trình duyệt (Browser / Client)"] -->|Port 3000| Frontend["frontend (Next.js 16 Alpine)<br/>Node 24"]
    Client -.->|Port 8000 (Direct/Docs)| Backend["backend (FastAPI Bookworm)<br/>Python 3.11"]
    Frontend -->|Internal Proxy http://backend:8000| Backend
    Backend -->|Bind Mount Volume| SQLite[("./data/smartllm.db<br/>(Persisted SQLite WAL)")]
    
    subgraph DockerBridge ["Mạng nội bộ: smartllm-network (bridge)"]
        Frontend
        Backend
    end
```

---

## 3. Cách 1: Triển Khai Bằng Docker Compose (Khuyến Nghị)

Phương thức nhanh nhất, nhất quán trên mọi hệ điều hành (Windows, macOS, Linux) chỉ với **1 lệnh duy nhất**.

### Bước 1: Chuẩn bị mã nguồn và biến môi trường

Mở terminal tại thư mục gốc của repository:

```bash
# 1. Đảm bảo file cấu hình môi trường tồn tại từ template
# (Trên Windows PowerShell)
if (!(Test-Path .env)) { Copy-Item .env.example .env }

# (Trên Linux / macOS)
cp -n .env.example .env || true
```

### Bước 2: Khởi chạy toàn bộ hệ thống bằng Docker Compose

```bash
docker compose up --build
```

Docker Compose sẽ:
1. Tự động build **backend** từ base `python:3.11-slim-bookworm`, cài đặt toàn bộ dependencies từ lockfile chuẩn hash SHA-256.
2. Tự động chạy migration cơ sở dữ liệu SQLite (`alembic upgrade head`) thông qua entrypoint.
3. Tự động build **frontend** từ base `node:24-alpine` với multi-stage build tối ưu Next.js 16.
4. Thiết lập bridge network nội bộ và ánh xạ cổng ra máy chủ:
   - **Frontend UI:** [http://localhost:3000](http://localhost:3000)
   - **Backend API & Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Healthcheck & Platform Info:** [http://localhost:8000/v1/platform-info](http://localhost:8000/v1/platform-info)

> [!TIP]
> Để chạy ở chế độ nền (detached mode), thêm cờ `-d`:
> ```bash
> docker compose up --build -d
> ```

### Bước 3: Tạo tài khoản quản trị (Admin Account)

Sau khi container khởi động, mở một terminal mới để tạo tài khoản người dùng đầu tiên:

```bash
docker compose exec backend python -m app.cli create-user --username admin --role admin
```
*Hệ thống sẽ yêu cầu nhập và xác nhận mật khẩu an toàn (từ 8 đến 256 ký tự).*

### Các lệnh quản lý Docker hữu ích:

```bash
# Xem log thời gian thực của cả 2 services
docker compose logs -f

# Xem log riêng backend hoặc frontend
docker compose logs -f backend
docker compose logs -f frontend

# Chạy test suite bên trong backend container
docker compose exec backend pytest backend/tests -q

# Dừng hệ thống container (dữ liệu trong ./data vẫn được giữ nguyên)
docker compose down

# Dừng và xóa toàn bộ volumes/containers nếu muốn làm sạch hoàn toàn
docker compose down -v
```

---

## 4. Cách 2: Triển Khai Native Trên Windows PowerShell

Dành cho nhà phát triển làm việc trực tiếp với mã nguồn trên môi trường Windows.

### Bước 1: Khởi tạo môi trường ảo Python 3.11

Mở PowerShell tại thư mục gốc repository:

```powershell
# Tạo virtual environment
python -m venv .venv

# Kích hoạt virtual environment
.\.venv\Scripts\Activate.ps1
```

> [!IMPORTANT]
> Nếu gặp thông báo lỗi thực thi script của PowerShell (`ExecutionPolicy`), bạn có thể mở quyền tạm thời cho session hiện tại mà không cần can thiệp hệ thống:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\.venv\Scripts\Activate.ps1
> ```

### Bước 2: Cài đặt thư viện Python (Locked Dependencies)

```powershell
# Cài đặt chính xác các thư viện theo hash SHA-256 đã kiểm định
python -m pip install --require-hashes -r backend/requirements.lock

# Cài đặt gói ứng dụng nội bộ backend ở chế độ editable
python -m pip install --no-deps --no-build-isolation -e 'backend[dev]'
```

### Bước 3: Cài đặt thư viện Node.js & Frontend

```powershell
# Cài đặt sạch các gói npm
npm ci

# Khởi tạo file .env từ template (nếu chưa có)
npm run setup
```

### Bước 4: Kiểm tra tính sẵn sàng của hệ thống (Doctor Check)

```powershell
npm run doctor
```
*Kết quả đạt yêu cầu:*
```text
OK Node 24
OK .env configured
OK frontend dependencies
OK Python 3.11 / backend dependencies
```

### Bước 5: Nâng cấp Cơ sở dữ liệu và Tạo tài khoản

```powershell
# Áp dụng các migration của Alembic lên SQLite
npm run db:migrate

# Tạo tài khoản quản trị viên
npm run account:create -- --username admin --role admin
```

### Bước 6: Khởi chạy môi trường phát triển

```powershell
# Chạy đồng thời cả Backend (port 8000) và Frontend (port 3000)
npm run dev
```

---

## 5. Cách 3: Triển Khai Native Trên Linux / macOS

Thích hợp cho máy trạm macOS hoặc máy chủ Ubuntu/Debian Linux.

### Bước 1: Khởi tạo và kích hoạt virtual environment

```bash
# Đảm bảo bạn đang ở thư mục gốc repository
python3.11 -m venv .venv
source .venv/bin/activate
```

### Bước 2: Cài đặt thư viện phụ thuộc

```bash
# Cài đặt Python packages với mã băm an toàn
python -m pip install --require-hashes -r backend/requirements.lock
python -m pip install --no-deps --no-build-isolation -e 'backend[dev]'

# Cài đặt Node.js packages
npm ci
npm run setup
```

### Bước 3: Kiểm tra cấu hình và chuẩn bị cơ sở dữ liệu

```bash
# Kiểm tra tổng thể
npm run doctor

# Chạy migration
npm run db:migrate

# Tạo tài khoản admin
npm run account:create -- --username admin --role admin
```

### Bước 4: Khởi chạy hệ thống

```bash
npm run dev
```

---

## 6. Kiểm Tra và Xác Thực Hệ Thống (Verification & Testing)

Sau khi cài đặt xong, bạn có thể thực thi các lệnh kiểm tra sau để đảm bảo hệ thống đạt độ tin cậy tuyệt đối:

### 1. Kiểm tra sức khỏe môi trường (System Doctor)
```bash
npm run doctor
```

### 2. Chạy bộ kiểm thử tự động Backend (Pytest Suite)
```bash
# Đảm bảo virtual environment đang được kích hoạt
npm run test:backend
```
*Kết quả chuẩn: Toàn bộ 86 test cases đều passed.*

### 3. Kiểm tra tính toàn vẹn hợp đồng OpenAPI & TypeScript
```bash
npm run contracts:check
```

### 4. Kiểm tra tĩnh & Định dạng mã nguồn
```bash
npm run lint
npm run typecheck
```

---

## 7. Bảng Cấu Hình Biến Môi Trường Quan Trọng

Các biến được cấu hình tại file `.env` ở root repository:

| Biến môi trường | Mặc định | Ý nghĩa & Hướng dẫn |
|:---|:---:|:---|
| `APP_ENV` | `development` | Chế độ môi trường (`development`, `production`, `test`). |
| `DATABASE_PATH` | `data/smartllm.db` | Đường dẫn file cơ sở dữ liệu SQLite cục bộ. |
| `PROVIDER_MODE` | `mock` | `mock` (không tốn chi phí, tự cung cấp dữ liệu mô phỏng) hoặc `live` (kết nối LLM thương mại sau khi duyệt catalog). |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Địa chỉ Backend mà Frontend proxy Next.js sẽ chuyển tiếp các request `/api/*`. |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | Cấu hình CORS cho phép trình duyệt truy cập. |
| `AUTH_SESSION_HOURS` | `8` | Thời hạn phiên đăng nhập hợp lệ của Cookie. |
| `PROJECT_BUDGET_USD` | `20.00` | Ngân sách giới hạn tối đa của toàn dự án. |
| `DEFAULT_USER_BUDGET_USD` | `5.00` | Hạn mức chi tiêu ban đầu cho người dùng mới. |

---

## 8. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

### 1. Trùng cổng mạng (Port Conflict: 3000 hoặc 8000)
- **Hiện tượng:** Không thể bind cổng do có tiến trình khác đang chiếm giữ `3000` hoặc `8000`.
- **Khắc phục trên Windows:**
  ```powershell
  Get-NetTCPConnection -LocalPort 8000, 3000 -ErrorAction SilentlyContinue | Select-Object OwningProcess, LocalPort
  Stop-Process -Id <PID> -Force
  ```
- **Khắc phục trên Linux / macOS:**
  ```bash
  lsof -i :8000 -i :3000
  kill -9 <PID>
  ```

### 2. Lỗi "Database not migrated" khi khởi động
- **Hiện tượng:** Backend ném lỗi `RuntimeError: Database not migrated`.
- **Khắc phục:**
  - Nếu chạy Docker: Entrypoint đã tự xử lý, hoặc gõ: `docker compose exec backend alembic upgrade head`.
  - Nếu chạy Native: Chạy lệnh `npm run db:migrate`.

### 3. Quyền ghi thư mục dữ liệu trên Linux (`data/smartllm.db: Permission denied`)
- **Khắc phục:** Đảm bảo thư mục `./data` có quyền đọc/ghi phù hợp cho Docker user:
  ```bash
  chmod -R 777 ./data
  ```

---

*Hệ thống được phát triển và chuẩn hóa theo tiêu chuẩn đồ án tốt nghiệp Trường Đại học Mở TP.HCM.*
