---
name: backend-high-throughput-streaming
description: Quy chuẩn thiết kế Backend cho luồng streaming thời gian thực (SSE), Token Bucket rate limiter cho LLM APIs, chống nghẽn ghi đồng thời SQLite WAL và bảo vệ giao dịch kế toán tài chính.
---

# Backend High-Throughput Streaming & Rate Limiting

Kỹ năng chuyên sâu về kỹ thuật Backend trong hệ thống LLM: Server-Sent Events (SSE) streaming token thời gian thực, điều phối lưu lượng (Token/Leaky Bucket Rate Limiter) theo hạn ngạch API nhà cung cấp, và kiểm soát ghi đồng thời SQLite trong môi trường tải cao.

## 1. Nguyên tắc cốt lõi & An toàn Giao dịch (Safety & Architecture)

### 1.1. Streaming Response chuẩn SSE (Server-Sent Events)
- Định dạng gói tin SSE bắt buộc:
  ```text
  event: delta
  data: {"content": "text chunk", "finish_reason": null}

  event: progress
  data: {"stage": "reasoning", "percentage": 45}

  event: done
  data: {"usage": {"input_tokens": 120, "output_tokens": 85}, "cost_usd": 0.00015}
  ```
- **Phát hiện client ngắt kết nối (`disconnect handling`)**:
  Khi client đóng tab hoặc hủy request, generator streaming phải lắng nghe `await request.is_disconnected()`. Nếu client hủy:
  - Ngừng ngay lập tức các token generator tiếp theo để tiết kiệm token và chi phí API.
  - Sử dụng `asyncio.shield` để bảo vệ các thao tác ghi sổ cái (ledger debit/refund) và cập nhật session history vào database, tránh hỏng dữ liệu trạng thái.

### 1.2. Token Bucket Rate Limiter phân tán cho LLM Providers
- Nhà cung cấp (Gemini, OpenAI, Anthropic) giới hạn cả hai chiều:
  - **RPM (Requests Per Minute)**
  - **TPM (Tokens Per Minute)**
- Thuật toán Token Bucket phải hỗ trợ:
  1. **Đặt trước (Reservation)**: Trừ trước một lượng token ước lượng trước khi phát lệnh API call.
  2. **Điều chỉnh sau phản hồi (Reconciliation)**: Khi API trả về `actual_tokens`, cộng/trừ phần chênh lệch vào bucket.
  3. **Hoàn trả khi lỗi (Refund)**: Nếu call bị timeout/lỗi 5xx trước khi mô hình sinh từ, lập tức hoàn trả lượng token đã đặt trước vào bucket.

### 1.3. Chống tắc nghẽn đồng thời trên SQLite WAL (Concurrency Resilience)
SQLite ở chế độ WAL cho phép nhiều tiến trình đọc cùng lúc nhưng **chỉ duy nhất 1 tiến trình ghi tại một thời điểm**.
Để không bao giờ gặp lỗi `sqlite3.OperationalError: database is locked`:
- Luôn cấu hình kết nối:
  ```sql
  PRAGMA journal_mode = WAL;
  PRAGMA busy_timeout = 10000; -- Chờ tối đa 10s trước khi báo lỗi
  PRAGMA synchronous = NORMAL;
  ```
- Sử dụng **Async Write Queue / Lock** tại tầng Application để tuần tự hóa (serialize) các giao dịch ghi critical (như ghi sổ cái Ledger, ghi phiên đăng nhập).

---

## 2. Mã nguồn Mẫu Tái sử dụng (Reusable Python Implementations)

### 2.1. Bộ điều phối tốc độ bất đồng bộ (Async Token Bucket Rate Limiter)

```python
import asyncio
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitConfig:
    max_rpm: int = 60          # 60 requests / minute
    max_tpm: int = 100_000     # 100k tokens / minute


class AsyncTokenBucketLimiter:
    """Token Bucket bất đồng bộ quản lý chặt chẽ cả RPM và TPM."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._lock = asyncio.Lock()

        # Quản lý Request tokens
        self.request_capacity = float(config.max_rpm)
        self.request_tokens = float(config.max_rpm)
        self.request_refill_rate = config.max_rpm / 60.0

        # Quản lý Model tokens
        self.token_capacity = float(config.max_tpm)
        self.tokens = float(config.max_tpm)
        self.token_refill_rate = config.max_tpm / 60.0

        self.last_update = time.monotonic()

    def _refill(self, now: float) -> None:
        elapsed = now - self.last_update
        self.last_update = now

        self.request_tokens = min(
            self.request_capacity,
            self.request_tokens + elapsed * self.request_refill_rate
        )
        self.tokens = min(
            self.token_capacity,
            self.tokens + elapsed * self.token_refill_rate
        )

    async def acquire(self, estimated_tokens: int, timeout_sec: float = 30.0) -> bool:
        """Chờ và đặt trước quota. Trả về True nếu thành công, False nếu quá thời gian chờ."""
        deadline = time.monotonic() + timeout_sec

        while True:
            async with self._lock:
                now = time.monotonic()
                self._refill(now)

                if self.request_tokens >= 1.0 and self.tokens >= estimated_tokens:
                    self.request_tokens -= 1.0
                    self.tokens -= estimated_tokens
                    return True

                # Tính thời gian cần chờ để hồi phục đủ quota
                wait_req = (1.0 - self.request_tokens) / self.request_refill_rate if self.request_tokens < 1.0 else 0
                wait_tok = (estimated_tokens - self.tokens) / self.token_refill_rate if self.tokens < estimated_tokens else 0
                wait_time = max(wait_req, wait_tok, 0.05)

            if time.monotonic() + wait_time > deadline:
                return False

            await asyncio.sleep(min(wait_time, 1.0))

    async def release_unused(self, estimated_tokens: int, actual_tokens: int) -> None:
        """Hiệu chỉnh lại lượng token thực tế tiêu thụ."""
        async with self._lock:
            diff = estimated_tokens - actual_tokens
            if diff > 0:
                self.tokens = min(self.token_capacity, self.tokens + diff)
```

### 2.2. FastAPI SSE Streaming Generator với Disconnect Handling

```python
import asyncio
import json
from typing import AsyncGenerator
from fastapi import Request
from fastapi.responses import StreamingResponse


async def event_publisher(
    request: Request,
    token_generator: AsyncGenerator[str, None],
    on_complete_callback,
) -> AsyncGenerator[str, None]:
    """Phát luồng SSE an toàn, phát hiện client disconnect và bảo vệ callback hoàn tất."""
    accumulated_chunks = []
    is_client_aborted = False

    try:
        async for chunk in token_generator:
            if await request.is_disconnected():
                is_client_aborted = True
                break

            accumulated_chunks.append(chunk)
            payload = json.dumps({"delta": chunk})
            yield f"event: delta\ndata: {payload}\n\n"

        if not is_client_aborted:
            yield "event: done\ndata: {}\n\n"

    finally:
        # Sử dụng shield để đảm bảo ghi nhận kế toán & lịch sử ngay cả khi ngắt kết nối
        full_text = "".join(accumulated_chunks)
        await asyncio.shield(on_complete_callback(full_text, is_aborted=is_client_aborted))
```

---

## 3. Checklist Kiểm thử & Rà soát (QA Checklist)

- [ ] Rate Limiter được áp dụng trước mọi lệnh dispatch ra live provider API.
- [ ] Mọi cuộc gọi cơ sở dữ liệu critical khi streaming kết thúc đều được bọc trong `asyncio.shield`.
- [ ] SSE streams định dạng chuẩn `event: ...\ndata: ...\n\n` (2 dấu xuống dòng kết thúc mỗi event).
- [ ] Cấu hình `PRAGMA busy_timeout >= 5000` được kích hoạt trên mọi connection pooling SQLite.
- [ ] Không rò rỉ reservation quota khi nhà cung cấp trả mã 429 hoặc 500.
