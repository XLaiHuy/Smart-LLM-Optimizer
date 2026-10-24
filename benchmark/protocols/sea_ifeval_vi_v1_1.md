# SEA-IFEval Vietnamese Evaluation Protocol v1

## Status

CANDIDATE — NOT RESEARCH ELIGIBLE.

This protocol may be used for local engineering validation.
It must not be used to claim model quality or savings until
the source qualification record is marked qualified.

## Pinned source

- Suite: SEA-IFEval Vietnamese
- Source ID: sea-ifeval-vi-v1-1
- Dataset revision: 1b7947549d2871c44b21956e9f23e90ce830cc37
- Dataset file SHA-256: 576a68a9c2ea0f05a122bcacffbd36f19aec96a7014afcba3cfbe4b754476889
- Evaluator: sea-ifeval-v1.1+sea-helm-v1.3.0@9be3986d
- Dataset license: CC-BY-4.0
- Evaluator code license: MIT

Raw dataset rows must not be committed until attribution and
redistribution handling have been independently reviewed.

## Population and frozen split

The source contains 105 unique Vietnamese cases covering
21 instruction IDs.

Frozen assignment:

- DEV: 21 cases
- HOLDOUT: 21 cases
- RESERVE: 63 cases

Each instruction ID occurs once in DEV and once in HOLDOUT.

DEV may be used for engineering pilots and debugging.

HOLDOUT is frozen and must not be inspected or used while
tuning. Because the upstream dataset is public, HOLDOUT is
not considered a blind private test set.

RESERVE cases are excluded from the primary result unless a
new versioned protocol explicitly includes them.

## Serving and evaluator boundary

The model receives only serving_input.

The following remain evaluator-only:

- instruction ID
- checker arguments
- expected language
- evaluator target
- grading result

Evaluator-only fields must never be copied into provider
messages, prompts, metadata, or optimizer context.

## Per-case scoring

SEA-HELM v1.3.0 performs one instruction-checker evaluation
per case.

For each case:

- constraint_passed is the result of the pinned instruction checker.
- correct_language is the result of the pinned language detector.
- passed is constraint_passed AND correct_language.

This project does not calculate or report separate strict and
loose IFEval scores.

The primary metric is:

overall_lang_normalized_accuracy =
100 * passed_case_count / evaluated_case_count

Reports must also preserve constraint and language failures
separately.

## Paired comparison

Baseline and optimized configurations must evaluate the same
case IDs using the same evaluator version.

For every case, report exactly one paired outcome:

- improvement: baseline fails and optimized passes
- regression: baseline passes and optimized fails
- both_pass
- both_fail

Also report tokens, estimated serving cost, latency, model ID,
configuration ID, catalog version, run ID and repeat index.

Mock and fixture runs are never research eligible.

## Vietnamese counting semantics

The pinned evaluator defines words using Unicode regular
expression matches for `\w+`. This is not Vietnamese lexical
word segmentation. Hyphenated text may be counted as multiple
units.

Sentences are non-empty blocks separated by the exact `***`
marker. Natural punctuation is not used for sentence
segmentation.

Paragraphs are non-empty blocks separated by the `***`
marker.

These are benchmark-specific operational definitions, not
general linguistic definitions.

## Qualification requirements

Before changing the source status to qualified:

1. Pin the language detector package, version and model assets.
2. Add detector adapter and parity/failure tests.
3. Obtain independent review of Vietnamese counting semantics.
4. Obtain independent license, attribution and evaluator review.
5. Record reviewer identity, date and decision.
6. Keep live execution behind explicit operator approval and budget limits.
