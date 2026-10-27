# Task-family calibration — 27 October 2026

## LATEST DEPLOYMENT: explicit global operator thresholds

Huy explicitly requested global 20B=0.690085 and Luna=0.71 and Docker browser testing, superseding the math-only proposal. Implemented as a new research_candidate artifact/receipt with false qualification evidence; previous engine files retained. Both Docker images built and deployed, backend healthy and http://localhost:3000 verified in browser. Full details and rollback: docs/OPERATOR_GLOBAL_THRESHOLDS_DOCKER_20261027.md. No paid provider smoke calls were made, no budgets/quota/reserves changed, and the stopped collection was not resumed. Do not revert these user-selected global settings merely because older sections below recommend keeping prior thresholds; those are historical research findings, not the latest operator instruction.

## LATEST: Huy requested actual threshold calculation from 450

Performed user-authorized exploratory partial-DEV fit, keeping the strict full qualification path unchanged. New research-only modules `family_threshold_preview.py`, scripts `preview_task_family_thresholds.py` and `check_task_family_preview.py`. Classifier trained on 234 TRAIN groups; raw-score thresholds selected only on 114 threshold groups; then frozen and checked once on 102 calibration groups not used to choose these thresholds. Existing ML+Attention weights unchanged. All computations offline, no paid calls. Research format is deliberately rejected by the serving loader. Eleven functional tests passed; Ruff passed.

Results and provenance: `data/router-task-family-v1-20261027/threshold-preview-450/RESULTS.md`, immutable candidate.json and unused-calibration-check.json. Math candidate 20B=.6900851096993991, Luna=1; check28/30 prior and candidate,0regressions,cost .001977954 -> .001636296 (~17.3% lower), classifier recognition7/30. Extraction candidate20B=.9202585257992495,Luna=.6880396510055419; check16/33->15/33,1regression, reject. Vietnamese candidate20B=.8543685871377994,Luna=.4775590934674324; check11/39->9/39,5regressions/3gains,reject. These are DEV diagnostics, not general accuracy/certification; exact-match grader/source ambiguity warnings above remain. Do not promote even the math candidate without full evidence and serving pilot; do not retune these frozen thresholds to hide the check failures. All three models can be selected by the candidate, but two task groups lose quality. No production threshold or config change was made.

## CURRENT RESULT: authorized ten OTHER questions complete, stopped at 450

After the 440 stop, Huy explicitly approved via request_user_input_async: retain USD 0.00173715, do not retry the unresolved call, collect ten OTHER questions. This supersedes the prohibition on new paid calls ONLY for that bounded exception. Authorization is persisted in `bounded-continuation-approval.json`, binding the same job/source, original call ID, initial 1,323 calls, maximum 30 additional calls, and stop at 450. Any new unknown ID still blocks continuation. The sample with the old dispatch marker was deferred without removing/replaying it; its two known cached answers remain unchanged. Frozen source membership and split assignments did not change.

Result: completed EXACTLY 450, `interrupted / USER_REQUESTED_PAUSE`; API call records 1,353 (1,352 known-cost and one old unknown), known cost USD 0.052305136, old unresolved reserve USD 0.00173715 retained. Added exactly 30 calls / ten complete independent DEV questions; no new unknown calls. Worker lock is free. Automation stays deleted; no further collection, pilot or deployment is scheduled.

Next offline step completed: `stopped-analysis-after-ten/report.json`, `README.md`, `RESULTS.md`, and UTF-8 `prompt-response-model.csv` with 1,350 actual cached response rows (450 x three models). Response SHA256 matches observations. CSV clearly labels paired provider measurements, not auto-route or full-chat E2E; records input/output tokens, USD, provider latency and preparation time. Spreadsheet-formula escaping changes export display only; cached responses are intact. Original 440 report is preserved separately.

Remaining DEV deficits: TRAIN66, calibration48, threshold36 = 150 missing DEV. Independent HOLDOUT remains 300 uncollected. No classifier/calibration fitting or engine retraining has been performed on the partial dataset, and no new thresholds were enabled. The next qualified fit needs all 600 DEV under the approved protocol, then independent HOLDOUT/pilot. Do not relax this gate or collect more without new authorization.

Preliminary DEV counts (NOT live certification): math120B138/142, 20B131/142, Luna78/142; extraction120B80/149,20B80/149,Luna61/149; Vietnamese120B48/159,20B51/159,Luna48/159. Error spot-checks found genuine task/semantic mistakes, exact-match span-boundary disagreements (e.g. 'Thermographic cameras' versus source answer 'Thermographic'), and a math source item requiring gold/ambiguity review (Juan 4,000-page example: response500 vs supplied gold250). These are diagnostic flags only: no source gold, grading formula or qualified label was edited to improve results. Daifuku error retained the term 'đại phúc' in both original and prepared prompt (401 chars, rewrite skipped); that inspected error cannot be attributed to compression loss. Do not generalize these few examples to every failure or certify open Vietnamese QA from these scores.

Bounded-exception + parallel/source tests: 18 passed; Ruff and targeted mypy passed. Reports and approval are persisted; financial uncertainty remains visibly separate from known cost.

## FINAL STOP: 440 complete questions, new unresolved provider call

Before the requested 450 boundary, the worker halted at 440 complete questions on `DEPENDENCY_UNAVAILABLE` for OpenRouter OSS120B, call `ee5c9467-6f10-44dc-b08b-dde858e32942`. Ledger: 1,323 total records, 1,322 known-cost calls, USD 0.051306478 known cost; one unresolved reservation USD 0.00173715 retained. The log's provider_status=503 is the AppError classification; actual upstream_status and Retry-After are absent, so do not claim a verified provider HTTP503 response or quota rejection. The two other generations of the incomplete next question are cached/settled and preserved. No retry or new campaign is authorized while this NEW dispatch remains uncertain.

The collector and offline watcher have both stopped. The stop-monitor automation `theo-d-i-hi-u-ch-nh-routing-ba-model` was DELETED to prevent further automatic work or repeated notifications. Source control still requests 450; do NOT resume it automatically. No training, pilot, promotion or serving threshold update occurred.

Read-only failed-stop diagnostics were completed explicitly using `finalize_task_family_stop.py --allow-failed-stop`, which neither writes the ledger nor releases unknown reserves. Report: `data/router-task-family-v1-20261027/stopped-analysis/report.json` and README. Both bind the DEV/source hashes and honestly report 440 complete DEV groups, calibration_ready=false, all_costs_resolved=false, trained=false, live_qualified=false. No HOLDOUT was read. Required DEV split counts are incomplete: math TRAIN72/CAL27/THRESHOLD37; extraction 78/33/37; Vietnamese 79/39/38. There are 160 missing DEV groups and 300 uncollected independent HOLDOUT groups under the frozen protocol.

Next-step tools and latest source were staged separately in `/tmp/task-family-next-code` (calibrate/evaluate/package); they are not running. The paid pilot remains draft, requires more integration review and all prior gates, and was not staged for automatic execution. New user direction plus safe reconciliation are needed before any collection continuation; do not infer permission from requests for status or setup. Older financial reserves are unchanged.

## LATEST USER DECISION: stop at 50 percent

Huy additionally asked to set up the steps after saving. A separate OFFLINE-only postcollection process is now scheduled inside the container: `/tmp/task-family-code/finalize_task_family_stop.py --wait`, exclusive `postcollection.lock`, log `postcollection.log`. It imports no provider/container, makes no API calls and cannot train or promote. It waits for exactly 450 with `USER_REQUESTED_PAUSE`, then for the collector's lock to be released. It verifies known billing and no pending/unresolved reservations for THIS job, validates DEV pairing/independence, computes split deficits and per-model DEV failure task IDs, and writes `stopped-analysis/report.json` plus README once. It never reads HOLDOUT. Six mocked/pure tests passed including architecture boundaries; targeted mypy and Ruff passed. Do not launch another copy: the process is already waiting. Check its report/log when the stop occurs, then notify Huy and delete the stop-monitor automation. This is preparation and diagnosis, not training or live certification.

Huy now requests collection stop at exactly 450/900 questions. This supersedes the automatic continuation to 600 DEV, 900 total, training/pilot/promotion instructions below. `collection-control.json` persists `stop_after_completed=450`. Collector checks BEFORE preparing/admitting the next question, records `interrupted / USER_REQUESTED_PAUSE`, keeps checkpoint/caches/ledger and exits. It must not claim succeeded/complete. Do not remove the control file or auto-resume after the boundary without new user direction. Monitor automation has been changed to stop-only and must be deleted after confirmation at 450 (or a blocking error).

To load this control safely into the existing process, a second pre-dispatch maintenance pause was applied (journal `stop-target-maintenance.json`). The first marker raced a lane that had already admitted its call; that call completed normally and remained cached. A repeated pre-dispatch check then stopped the worker at 371 complete questions / 1,115 known-cost calls, USD 0.043310568. Cleanup held the exclusive lock and verified every call cost known, removing only the maintenance markers it owned. One restart with the new runner/module failed to acquire the already-held lock and made no API calls. After verified cleanup, the same job was resumed once with the new `app.routing.ml.family_campaign` module and the persistent 450 stop control. No running provider request was killed. Seven source/stop-boundary tests passed. The running module now IS the new source path; the earlier note below about the old loaded path is historical.

Huy asked whether these data will train the router: explain accurately that the campaign is intended to learn the task classifier/calibration/thresholds first, preserving the ML+Attention engine; engine retraining only if DEV error analysis warrants it. At 450 there is insufficient complete DEV (600) and independent HOLDOUT for the approved qualification workflow. Do not silently shorten splits, fit partial data as a certified artifact, or interpret the question as permission to override the 50-percent stop.

Full mocked backend run ended: 812 passed, one import-boundary failure that was repaired during the run; the 19-test follow-up (including boundary tests) passed. XML `output/project-audit/task-family-backend-20261027.xml` retains the original failure for audit; follow-up XML records the fix. Do not describe the original XML as all-green.

## Active collection

- Single job: `743d174d-b46b-4a86-8e21-c13acbac75f0`.
- Directory: `data/router-task-family-v1-20261027`; read `status.json` and tail `worker.log` for current progress.
- At this checkpoint: 129/900 questions, 390 API calls, known cost USD 0.015075808, running, no reported error. Counts can include the next in-flight question.
- Frozen corpus SHA256: `8c2c40d829f2840722df700f9c1564fb24cff636f39cd209ad94f81a1067cbad`.
- Three families, 300 independent source groups each: GSM8K arithmetic, SQuAD extraction, MLQA Vietnamese grounded QA. Each family: 100 TRAIN / 50 calibration / 50 threshold / 100 HOLDOUT.
- Three models measured on the same prepared input: OSS20B and OSS120B through OpenRouter, Luna through OpenAI. One worker, up to TWO concurrent calls, persistent checkpoints, exclusive lock. Do not launch a second worker or regenerate the frozen protocol.

## Safe acceleration at 22:00 local

Huy requested maximum safe speed. The collector was upgraded from sequential to at most two calls concurrently. It preserves the global 1.4-second admission interval, provider limiter, exact input/config/grader cache keys and frozen source/splits. Per-call lanes use the existing atomic ledger reservations and settlements; only the coordinator writes job status, reconciled from actual ledger records rather than summing stale job copies. Any failed lane closes admission; already dispatched peers finish and are accounted without cancellation. New unknown costs block same-job resume.

The old worker was paused using an explicit maintenance marker at the existing PRE-dispatch fence, never killed. At the boundary it had 199 complete questions and 599 known-cost calls. Cleanup acquired the exclusive worker lock and verified all 599 ledger records had known costs before removing ONLY its own maintenance marker. The same job resumed using existing caches (including the partially completed question). `DISPATCH_REVIEW_REQUIRED` in the log at this boundary is the deliberate maintenance pause, not a provider failure. Other dispatch markers/reservations were not touched. The journal is `parallel-switch-maintenance.json`; do not reuse this one-time cleanup command.

Actual read-only ledger sampling after resume observed TWO simultaneous pending calls, with six calls admitted during a roughly 10-second sample; evidence is `parallel-observation.json`. This confirms overlap, not a promised 2x end-to-end speedup. Progress at 22:01 local: 209/900, 627 calls, USD 0.024168718, running with no reported error. Warmup/restart was limited to the research worker; chat/backend container stayed running. Serving thresholds and the USD 2 campaign cap remain unchanged.

Verification: 46 targeted tests passed, including real temporary SQLite/ledger with fake providers for concurrent success, draining peers after an unknown timeout, retained unresolved reservations, cache reuse without dispatch, and gate rejection after a failure. Ruff and a targeted mypy check passed. Evidence: `output/project-audit/task-family-parallel-20261027.xml`.

## Budget and uncertainty

## Follow-up at 22:09 local

Huy requested all work within ten minutes. At 238/900, roughly 1,986 calls remained; the frozen global admission spacing of 1.4 seconds alone implies approximately 46 minutes before qualification/pilot. Do not promise ten-minute quality certification, reduce sample counts, loosen gates or change concurrency/quotas merely to meet that deadline. Continue useful independent software checks while collecting.

Full backend tests were started with mocked providers. They exposed an import-boundary violation in the new collector: research accounting imported storage inside the pure routing directory. Source collector was moved to `backend/app/routing/ml/family_campaign.py`; runner/tests imports updated. The RUNNING container worker still uses its already-loaded `/tmp/task-family-code/app/routing/family_campaign.py` frozen copy, so do not change/restart it. Future staging must use the new source path. Follow-up boundary/concurrency/checkpoint tests: 19 passed (`output/project-audit/task-family-fix-followup-20261027.xml`). The original full test run still needs its final report and a follow-up for affected failures; do not claim a fully green suite prematurely.

Pilot draft hardened: `app.routing.family_pilot.checkpoint_spend` scans every prior marker before a new paid call, binds results to frozen candidate and verifies known per-call billing equals recorded cost. Eight fake-checkpoint tests passed. Resume accounting includes ALL prior result costs before dispatch and does not double-count replay files. Pilot refuses successful qualification without real ML+Attention execution and at least one matching family profile application. Packaging refuses an empty approved bundle. These changes do NOT mean the entire draft pilot is live-tested/approved; full fake-provider integration review is still needed before any paid pilot.

At 22:09: 287/900, 861 calls, USD 0.032869948, running with no reported error. `backend/app/routing/family_pilot.py` and pilot/packaging scripts have not been staged to serving or executed live.

At 22:11: 309/900, 927 calls, USD 0.035420954, running. Full mocked backend suite remains in unified exec session `7756`, report destination `output/project-audit/task-family-backend-20261027.xml` (not yet written). Initial failure was the collector import-boundary issue fixed above; the follow-up boundary tests passed, but inspect the full final XML and repair any other failures before claiming the suite is green. Targeted mypy for `routing/ml/family_campaign.py` and `routing/family_pilot.py` passed; pilot/packaging scripts compile. Never call the draft pilot live on the strength of these limited checks alone.

## Financial fences

New campaign ceiling USD 2: collection <=1.50, pilot <=0.50. Preserve existing user/project/key limits and all older reservations. The authorized old VAE exception retains USD 0.00230895 without retrying that call. Other old reserves remain unresolved. Any NEW completed dispatch with uncertain outcome stops further paid calls; preserve its marker and reservation. A currently running call is not a failed dispatch. Never resume solely because the status counter says zero unknown calls; inspect the job ledger and markers.

## Serving state and next gates

Serving engine and thresholds remain unchanged. No family-specific threshold is certified or activated yet.

1. Finish DEV collection (600 rows); run `scripts/calibrate_task_families.py` using only `dev-observations.json`. Freeze candidate before reading HOLDOUT. Do not change the serving engine or tune on HOLDOUT.
2. Finish all 900 rows. Run `scripts/evaluate_task_family_holdout.py` once on the frozen candidate. At least 100 independent HOLDOUT groups/family, no correctness loss or critical regression, one-sided regression upper95 <=3%, lower all-in cost.
3. The paired serving pilot script is a DRAFT and must pass mocked-provider tests and review before live execution. Only offline-passing groups may enter it: >=20 pairs/family, median latency <=1.10 baseline, cheaper all-in cost, verify actual ML/Attention/profile execution. Keep the combined budget and unknown-dispatch fences.
4. `scripts/package_task_family_profiles.py` is a DRAFT packaging tool. Package only passing groups; never deploy an empty bundle or claim unreviewed pilot results. Preserve code/open reasoning/hybrid/memory/RAG/multi-turn policies. These source sets certify only single-turn empty-memory envelopes if all gates pass.
5. Before deployment, back up the native Docker SQLite database using SQLite backup; do not use the corrupt host `data/smartllm.db`. Do not restart the backend while collection is running. Retain the prior serving configuration for rollback.

## Verification

42 targeted functional tests passed at the earlier checkpoint; these are software tests, not live-quality certification. Additional malformed-evidence tests now cover zero latency, nonfinite/negative cost, and nonboolean quality/accounting fields. All automated tests use mocked providers and consume no paid API.

Collection code runs from `/tmp/task-family-code` in `smartllm-backend`; serving modules loaded by the existing server have not been replaced. Do not overwrite the running collector or restart the container during collection. New offline calibration/pilot scripts need staging and verification before use.
