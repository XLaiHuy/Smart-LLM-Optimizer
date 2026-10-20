---
name: fastapi-sqlite-clean-arch
description: Architectural guidelines and best practices for Python FastAPI, SQLite concurrency (WAL mode), Pydantic V2, and Clean Hexagonal Architecture (Ports & Adapters). Use when developing backend API endpoints, database models, session management, or core orchestration.
---

# FastAPI / SQLite foundation

Read root spec §04 for canonical DTOs/ports/errors and §14 for G0 acceptance. Huy owns contracts, API/auth, schema/migrations, repositories, ledger, providers/router, wiring and frontend. Tân owns prompt/context; Khoa owns memory/evaluation after full G0 handoff. This skill is not a second contract definition.

## Boundaries

- Put Pydantic V2 request/result types in contracts/dtos.py; Protocols import DTOs in contracts/protocols.py. Define LLMProvider once. Generate frontend TypeScript from OpenAPI; never hand-edit generated types.
- Use frozen DTOs with immutable nested values or defensive copies; frozen Pydantic alone does not freeze list/dict contents. Reject public identity/trusted roles/full history; auth principal and stored history are authoritative.
- Keep routes under API modules, lifecycle/router mounting in main, concrete dependencies in composition root. Algorithms use ports, not private ORM/API/provider SDK internals.
- SessionStore performs real load/atomic successful-pair commit/resume regardless of memory flag. Memory no-op preserves the entire snapshot. ContextManager alone assembles messages/current turn once. Follow §04 signatures, not simplified substitutes.

## SQLite and transactions

Use local one-worker SQLite WAL, foreign keys, configured busy timeout, SQLAlchemy async and Alembic. WAL improves reader/writer overlap; it is not a multi-writer high-concurrency service. Never share AsyncSession across concurrent tasks or hold DB transactions while awaiting inference. Apply appropriate connection settings; use short atomic DB claims/constraints for dedupe, session lease and request/user/project reservations.

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

Busy timeout is configurable; journal setup and migrations must work from an empty DB. Commit original user/assistant pair together; failed/interrupted attempts remain separate. Uncertain dispatch retains unresolved usage, no automatic paid replay. Huy integrates migrations; each clone/test uses an isolated DB.

## Auth and accounting

Follow §04 account CLI/Argon2/opaque-token hash/expiry/revocation and same-origin cookie design. Scope reads/writes/trace by owner; foreign IDs return 404. Logout/expiry invalidates access and frontend owned caches. Do not expose secrets or raw private content in logs.

CostCatalog pricing is separate from BudgetLedger reserve/settle/reconcile at request/user/project. Preserve unknown usage/cost; never fill missing usage with zero or release uncertain reservations as free calls. G0 mock is not_billable/null with no quality/savings; statuses distinguish disabled/not_implemented/skipped/applied/failed.

## Verification after implementation

Require clean migrations/account CLI, two-user isolation/logout/expiry, history with memory off, dedupe/concurrent requests, quota races/reconcile, all flags, unknown metrics, generated-contract consistency and mapped API errors. Use metered fake/fault fixtures, not live API calls. G0 checklist is a future gate, not evidence already passed.
