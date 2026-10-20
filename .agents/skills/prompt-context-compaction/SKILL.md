---
name: prompt-context-compaction
description: Rules and algorithms for Prompt Rewriting, Semantic Preservation Validation, and Context Compaction in LLM optimization pipelines. Use when developing prompt optimization modules, context window budget managers, token compression filters, or preservation validators.
---

# Prompt preservation and context compaction

Tân owns prompt/context/preservation; Khoa memory/evaluation; Huy contracts/storage/provider/ledger/wiring. Use spec §04 canonical DTOs/ports and §09 algorithms; do not shorten signatures into incompatible examples.

## G0

Prompt no-op keeps original mutable content. Context no-op assembles server instructions/full raw history/current turn once, retaining roles/order. Memory no-op returns unchanged snapshot, not empty history. True flag → not_implemented; false → disabled. No optimizer inference, fake usage/quality/savings. SessionStore persistence remains real and independent of flags.

## Preservation after G0

- Protect trusted roles/instructions, code/identifiers/quoted literals, entities, numbers/units/dates, language, exact schemas and logical/numeric constraints. Transform only allowed mutable content without new assumptions.
- Use semantic rules per constraint with versioned evaluators. Same negation token is only a heuristic: “không ít hơn 10” and “không nhiều hơn 10” reverse numeric direction. Output can violate “không nhắc tên A” while containing another “không”. A substring check cannot prove equivalence.
- Return preserved/violation/unknown with reasons/evidence. Incomplete extraction, unresolved relation/negation/time scope or ambiguity → unknown → skip original unchanged. Agreement on protected slots is not proof of all semantics; measure downstream final-answer quality separately.
- Counterexamples include reversed bounds, swapped entities with identical vocabulary, dates/units/corrections, code corruption and nested JSON keys. JSON parsing alone proves neither schema nor answer correctness.
- Trigger/length thresholds are DEV-tuned policy, not universal rules such as 50 words. Estimate downstream cost including optimizer calls/output; latency separate. Do not add tokens or milliseconds to USD.

## Context versus memory

ContextManager alone assembles immutable snapshot + budgets + features.current_turn. Orchestrator never appends again; rewritten current content returns to Context for final assembly. Bypass uses full raw, without overlapping summary. Token estimates retain source/status/model/tokenizer/version; len(text)//4 is not provider usage or exact guard. Unknown is allowed; live needs conservative configured bounds or mapped failure when feasibility cannot be established.

After G0 Context may select content/request summary_needed, but never writes DB or calls summarizer. Orchestrator approves/reserves; MemoryManager creates derived state/provenance via ports; Context reassembles within a bounded plan. Preserve trusted instructions/current turn/protected facts; no silent dropping to fit. Recover original baseline if feasible within remaining limits or error. Gold answers/evidence never drive serving selection.

Measure candidate-aware budgets including output reserve/role overhead, source maps and actual length tiers. UIT-ViQuAD is not automatically long-context; short Vi-Dialog does not establish long-term memory. Compare implemented variants with all calls counted and failures reported alongside compression ratios.
