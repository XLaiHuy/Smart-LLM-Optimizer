---
name: eval-benchmark-graders
description: Guidelines and scripts for Vietnamese Multi-task Benchmark loaders (SEA-IFEval, UIT-ViQuAD, VMLU), Deterministic Graders (Exact Match, Token F1, Regex Rules), and Paired Ablation Testing. Use when developing evaluation runners, graders, benchmark dataset adapters, or metrics calculators.
---

# Vietnamese benchmark and graders

Khoa owns evaluation/adapters/graders/runner/reports and memory. Huy owns serving/storage/contracts. Read spec §04 and §06–§07; do not copy a reduced EvalCase schema that loses source metadata or multi-turn state. Keep serving inputs and evaluator-only targets separate.

## Four target suites: candidates until qualified

- SEA-IFEval: aisingapore/Instruction-Following-IFEval, config vi, split eval. Retain instruction IDs/kwargs and evaluator version; audit Vietnamese word/sentence rules. Ad hoc regex is not automatically official scoring.
- UIT-ViQuAD 2.0: proposed taidng/UIT-ViQuAD2.0 mirror. Preserve all valid answers/spans, is_impossible, document/source IDs and context. Score multiple golds by pinned source rules; evaluate no-answer cases separately. plausible_answers are distractors, never gold or a reason to turn the case answerable.
- Vi-Dialog: preserve public original conversations. Group annotations use adapted protocol vi-dialog-memory-probes-v1, not official Vi-Dialog memory scoring. Each probe needs source/conversation ID, checkpoint, evidence turns no later than checkpoint, question, gold/variants, protocol version and annotator/reviewer/status. Original dialogue-rubric evaluation is different; see VMLU paper in spec.
- VMLU multidisciplinary MCQ: proposed tridm/VMLU mirror; retain options/keys/topics and deterministic option mapping. Verify original release/license; mirror availability alone does not qualify data.

Record revision/hash/access/license/schema/duplicates/splits/grader fixtures before QUALIFIED. Target 140–170 TOTAL sampling units across DEV + HOLDOUT. Count questions, independent conversations, raw turns, checkpoints and probes separately. Split by source/document/conversation before tuning; variants stay together. Many probes do not increase independent conversation N. Do not invent dialogue to fill long-horizon gaps; report coverage limitations.

## Grading and leakage

- Prefer source-compatible deterministic graders: EM/F1, MCQ accuracy, numeric bounds/tolerance, exact literal requirements/prohibitions, schema assertions. Version evaluator and normalization; test positive/negative/boundary fixtures.
- Presence of the substring “không” is not a semantic-preservation test. For “không nhắc tên A”, check the prohibited entity; for “không ít hơn 10”, check the lower bound. “Không ít hơn” and “không nhiều hơn” reverse meaning despite sharing negation. Unknown constraints do not pass.
- JSON parsing proves syntax only; test required keys/types and answer content separately. Preserve Unicode, diacritics, numbers/units and negation; disclose versioned departures from source normalization, including Vietnamese orthography changes.
- Open-ended dimensions use blind judge: anonymized outputs, randomized A/B order, frozen rubric/config and human-calibration subset. Report disagreements/limitations. Judge cost separate from serving, included in spending envelope.
- Hidden gold/reference/evidence goes only to evaluators. Serving can see original user-visible constraints, never answer keys, oracle selected context or gold pinned facts.

## Runs and reporting

G0 deterministic synthetic smoke proves flow, not model quality. Preserve purpose/source, reject mock/unqualified/incomplete manifest in live research. Freeze source/group splits, code/policy/registry/pricing/evaluator versions/settings/exclusions. Memory replay sees only prefix at checkpoint, separate rollout, count all summary calls once with provenance and amortized totals.

Pilot determines cases × configs × repeats × optimizer/judge calls within roughly 20 USD including development/reruns; do not guarantee fixed API cost or statistical power. Report paired deltas, group regressions/failures, independent N and uncertainty (cluster by conversation when appropriate). Lock thresholds before holdout; point estimates do not prove a 3 pp non-inferiority margin. Unknown cost is not zero; mock/no-op has no research quality/savings. Use PASS_OBSERVED/INSUFFICIENT_EVIDENCE/FAIL per spec and retain negative results.
