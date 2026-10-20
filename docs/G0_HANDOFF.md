# G0 foundation handoff

Mốc bàn giao: commit `feat: initialize G0 optimizer foundation`. Tra cứu bằng `git log --oneline`; các feature branches của Tân/Khoa bắt đầu từ foundation commit đã kiểm tra này. Chưa tạo remote hoặc push.

## Trạng thái và bằng chứng

G0 có code chạy thật cho auth, SQLite migrations/repositories, owned history/trace/overview, dedupe/session lease, budget ledger, deterministic mock và frontend OU Việt/Anh. Router/rewrite/context optimization/memory optimization vẫn no-op; Context assembly và raw persistence hoạt động thật. Chưa có live adapter hoặc research results.

Các kiểm tra thực hiện trên **Windows, Python 3.11.9, Node 24.18.0/npm 11**. Exact dependency resolutions ở lockfiles. CI Windows/Linux đã được cấu hình; chưa có remote CI run, không gọi đó là kết quả đã pass trên Linux/macOS.

| Gate | Command / evidence |
|---|---|
| Clean setup | Venv sạch từ requirements hashes + no-build-isolation editable install; npm ci; doctor |
| Backend | `npm run test:backend`: **32 tests** gồm 16 flag combinations, auth/ownership, rollback, concurrent claims/quota, interruption, chunked limits và timeout/cancel |
| Frontend unit | `npm run test:frontend`: **3 tests** cho unknown metrics, flags và VI/EN parity |
| Contracts | `npm run contracts:check`: OpenAPI/generated TS không drift |
| Code checks | Ruff lint/format, mypy strict, ESLint, Prettier, TypeScript |
| Root launcher | npm run dev: backend health/proxy trả mock; UI HTTP 200; Ctrl+C dừng cả hai ports |
| Build | `npm run build`: production Next build |
| Browser | `npm run test:ui`: **3 Chromium flows**, gồm VI/EN/draft/history/trace/dashboard/logout; second-user isolation; mobile/network retry/expiry |
| Smoke | `npm run eval:smoke`: **3 synthetic cases**, DB riêng, deterministic predictions, mock labels/null quality/savings |

Browser screenshots/traces ở `output/playwright/`; không commit private runtime artifacts. Tests dùng temp DB/account; không có dev account/password mặc định. Xem [README](../README.md) để setup và tự tạo account.

## Ownership / integration

| Owner | Module sau G0 | Cần phối hợp |
|---|---|---|
| Huy | contracts/API/auth/core/storage/migrations/ledger/provider/routing/wiring/frontend/tooling | Affected-owner review khi đổi contract; tích hợp migrations/locks/generated types |
| Tân | optimizers: prompt/context/preservation và module tests | Repository/provider DTO mới qua Huy; evaluator rules với Khoa |
| Khoa | memory algorithms + evaluation/adapters/graders/runner/benchmark/reports/tests | Schema/store changes qua Huy; memory/context provenance với Tân |

Mỗi người clone/worktree, branch và DB riêng. Không cùng sửa shared global fixtures hoặc root locks trong PR thuật toán. Consumer dùng ports từ `contracts/protocols.py`; actual DTO shapes ở `contracts/dtos.py`, public API snapshot tại `docs/openapi.json`. Modules algorithm không import ORM/private API/provider SDK. Small PR + contract checks + sequential merge giảm conflict; không bảo đảm tuyệt đối không conflict.

## Hành vi và giới hạn cần giữ

- SessionStore commit original user/assistant pair và success/trace trong một transaction. Memory false vẫn lưu history; derived state lưu qua MemoryStore, evidence phải từ committed messages.
- Same succeeded request/payload trả stored response. Failed/interrupted không tự dispatch lại; session đang chạy trả 409. Restart chuyển running thành interrupted và giữ unresolved reservations nếu có dispatch.
- Ledger dùng Decimal strings dưới SQLite write transaction, không SQL floating-point SUM. Reservation/dispatched/unresolved/settled/released có transition checks; G0 mock không giả tiền.
- Request config/trace immutable theo từng request; UI locale không đổi content. API key chỉ server `.env`, G0 live mode bị reject.
- Dashboard scope current-user/all-time; purged traces không phục hồi qua replay. Failed/interrupted attempts có status/error metadata trong DB và overview; GET trace hiện trả successful response traces, không có error-trace inspector riêng.
- G0 stored timing scope `server_through_history_flush`, dừng trước final trace commit; HTTP `Server-Timing` gồm transaction commit. Không dùng mock median để nhận policy hoặc kết luận scientific latency.
- Local single-worker only; auth TTL 8 giờ, login throttle local/in-memory, không public deployment/SSO/signup. Linux/macOS và real API access chưa được kiểm tra trong phiên này.

## Tickets tiếp theo

1. **Khoa / G1:** qualified source registry, DEV/HOLDOUT grouped split, official-compatible graders; giữ multi-gold/no-answer và reviewed adapted memory probes. Không dùng smoke làm research score.
2. **Huy / G2:** native API adapter, verified IDs/access/usage/pricing, live token guard, pilot/call matrix trong budget. Không bật bằng cách chỉ đổi `.env` trên G0.
3. **Tân / G4–G5:** preservation constraints/unknown→skip và context source maps qua ports; fake-backed tests trước, live ablation sau G2.
4. **Khoa / G6:** provenance/versioned summaries/facts/corrections, không đổi raw history hoặc bypass ledger; research claims bị chặn nếu horizon/qualification chưa đủ.
5. **Huy / G3/G7/G8:** measured router/controller và live reports integration sau prerequisite gates.
