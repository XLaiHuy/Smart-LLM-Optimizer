# Smart LLM Optimizer

Read the root spec, README and relevant `.agents/skills/` before changes. User decisions override stale skill styling: light OU blue/white, local Roboto, VI/EN; mock by default; live requires reviewed catalog and server key. See spec §15 and docs/MVP_HANDOFF.md. No paid API calls in tests or CI.

Huy owns contracts/API/auth/storage/migrations/ledger/provider/router/wiring/frontend and shared tooling. Tân owns optimizers after G0 handoff; Khoa memory/evaluation/benchmark. Use ports and generated TS; affected owners review contract changes. Do not edit another module or dependency lock incidentally.

<!-- CODEGRAPH_START -->
## CodeGraph

If `.codegraph/` exists, reach for CodeGraph before grep/find or reading files to understand or locate code. Use `codegraph_explore` or `codegraph explore`. If absent, skip CodeGraph; indexing is the user's decision.
<!-- CODEGRAPH_END -->
