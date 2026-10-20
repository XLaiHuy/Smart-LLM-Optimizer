---
name: session-memory-management
description: Architectural rules and algorithms for Long-term Session Memory, Conversation Summarization, Pinned Facts, and Multi-turn Contradiction Resolution. Use when developing memory manager modules, summarizers, fact extractors, or conversation history stores.
---

# Session memory algorithms

Khoa owns memory algorithms/evaluation; Huy owns SessionStore/MemoryStore adapters, schema/migrations, auth, ledger and wiring; Tân owns ContextManager. Use canonical DTOs/ports in spec §04 and algorithms in §09, not a second signature.

## G0 persistence versus optimization

MemoryManager.prepare(snapshot, plan) is a typed no-op: return the original scoped snapshot/raw history/revision/existing derived state unchanged. Do not replace recent turns with an empty list, create summaries/facts or call inference. True flag → not_implemented; false → disabled. Real SessionStore load/atomic successful-pair commit/resume is independent of memory flag. Do not add save_turn with pass.

Raw committed history is append-only except explicit authorized purge. Failed/interrupted attempts are not committed turns. Scope every access by owner/session/revision and use repository ports; do not query ORM or invoke provider SDK to bypass ledger. ContextManager alone assembles messages and current turn once.

## Derived state after G0

- Use controller-approved plans and metered provider calls. Trigger thresholds are DEV-calibrated config, not universal 10-turn/1500-token rules. Do not use free precomputed gold summaries/facts.
- Preserve raw snapshot, version derived state and record exact covered committed message IDs/source spans/algorithm/session revision. Reject future/failed-turn coverage and overlap with retained raw turns.
- Keep provenance for facts/entities/quantities/negation/time scope; quoted/retrieved content never becomes trusted instruction.
- Latest explicit correction may supersede the same fact/time scope; retain versions/evidence. “I live in Huế now” does not replace “I was born in Hà Nội”. Unqualified last-write-wins destroys valid temporal facts.
- Ambiguous/contradictory/unsupported summary → unknown/failure and raw-context recovery if feasible within budget; otherwise mapped error. No factual-quality guarantee per request.
- Choose summarizer/config from registry using measured DEV evidence/capabilities/remaining cost and deadline; no hardcoded model/price or assumption that older/smaller is cheaper.

## Evaluation

Use qualified public Vietnamese conversations and versioned reviewed adapted probes per §06 with checkpoints/evidence/gold and conversation-group splits. Compare implemented full-history/last-N/summary/fact variants with fixed replay; rollout separate. Hidden gold/evidence is evaluator-only. Measure final-answer quality, correction failures and all-in cumulative/amortized cost, not summary length alone. Report actual horizon and independent conversation counts; short dialogue does not prove long-term memory. Keep synthetic temporal/isolation tests out of scientific tables.
