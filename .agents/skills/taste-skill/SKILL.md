---
name: taste-skill
description: Art direction and anti-slop frontend design skill from leonxlnx/taste-skill. Use when designing, building, or reviewing landing pages, UI layouts, typography, color palettes, and public web surfaces. Enforces strict no-slop design standards, curated typefaces, and distinctive aesthetics.
---

# Smart LLM Optimizer visual direction

Huy owns frontend/generated API types/integration. Read spec §04 for nullable metrics/effective flags and §14 for G0 acceptance. Do not redefine DTOs or assign frontend to Khoa. G0 includes a finished UI using real auth/history/trace and mock provider, not postponed polish.

## Visual system

Use a light OU blue/white theme: primary #034EA2, secondary #387EC1, white/very-light-gray surfaces and readable neutral text. This supersedes the earlier Slate/Emerald/Cyan direction by user decision. Keep deliberate typography/spacing, subtle borders and restrained shadows; no dark-theme toggle in G0.

Use local Roboto with Vietnamese glyphs, readable 400/500/700 body weights and mono for IDs/JSON. School lockup weights may use 900/300 following the linked OU brand book. Retain font license and original OU logo proportions/colors on a white background; do not redraw or apply effects. UI is VI/EN through next-intl, default vi; locale changes never translate saved messages or discard drafts.

Build a purposeful shell: owned-history sidebar, readable chat workspace, baseline/optimized control, trace inspector and dashboard. Use compact expandable technical details with accessible labels. Avoid arbitrary gradients, decorative fake charts, glass on every surface and dense repeated cards that obscure the task.

## Honest data

- Actual mock requests/history/timings are labeled mock. Unknown cost/quality/savings show “chưa có dữ liệu live” or explicit unknown status, never coerced zero.
- No invented savings badges/Pareto plots/research scores/preview measured data. Use informative empty dashboard until qualified live artifacts exist. Mock not_billable differs from measured free live usage.
- Flags show requested versus effective API config/availability. True no-op means not_implemented, not applied. Each trace keeps its request settings after next-request toggles change.
- Live charts later require real compatible artifacts with purpose/source/coverage. Quality, cost and latency retain distinct units.

## Completion

Finish login/logout, owned history/resume, chat, flags, trace and dashboard in G0. Include responsive/mobile, keyboard/focus, readable contrast/touch targets, reduced-motion and loading/submitting/disabled/empty/error/auth-expired states. Code/JSON scroll within narrow panels. Apply impeccable for behavior; validate actual UI flows/screenshots once code exists. Mock functionality is not scientific evidence.
