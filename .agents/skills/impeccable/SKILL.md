---
name: impeccable
description: UI/UX design craft and frontend polish skill from pbakaus/impeccable. Use when building, auditing, polishing, or optimizing frontend components, dashboards, chat interfaces, settings, and forms. Focuses on micro-interactions, responsive states, layout alignment, typography, and premium user experience.
---

# Interface behavior and polish

Huy owns frontend/API integration. Use generated OpenAPI types per spec §04 and G0 acceptance §14 with taste-skill visual direction. Complete login/logout, owned history/chat, flags, trace inspector and dashboard during G0.

## Interactions

- Provide labels, error associations, visible keyboard focus, contrast/touch targets, responsive layouts and reduced-motion alternatives. Transitions must not delay use or cause layout jumps.
- Distinguish initial load, empty history, request in progress, busy session, transport error and auth expiry. Preserve draft where appropriate; retry follows dedupe/error semantics, never automatically creates a new paid ID after uncertain dispatch.
- Clear owned caches on logout/account change; 401 returns to login. No stale session/history/trace from another account remains visible.
- Flags read effective policy/availability from API, not checkbox state alone. Baseline sends allowed defaults/all-false flags, not conflicting true flags. Show next-request changes clearly and keep running request config stable.
- True G0 no-op → not_implemented; false → disabled. Skipped/applied/failed require matching API reason/result. Changing next flags never rewrites prior trace settings.

## Metrics

Handle null/unknown explicitly. Mock not_billable/null means no live measurement, not a measured zero-cost policy. Do not format null as $0.0000 or 0% quality/savings; use “chưa có dữ liệu live” or reason/status. Known tiny costs need enough significant digits or tooltip rather than rounding to false zero. Show known/estimated/unknown provenance.

Actual local mock timings need a mock label. Nonstreaming TTFT stays null/absent. E2E is not a sum of overlapping spans; USD/tokens/ms remain distinct. Charts and green saving badges require compatible qualified live data; G0 dashboard uses informative empty state, never fabricated graphs.

## Verification after implementation

Exercise login/logout/expiry, two-user isolation, history/resume, modes/flags/effective config, trace snapshots, double submit and network/error/empty/mobile/keyboard states. Require actual backend tests, frontend typecheck/build and UI-flow evidence before handoff. These instructions are not proof that checks already passed.
