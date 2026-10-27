# Router activation and provider stability

This workflow separates software readiness, measured quality and operator activation.
Huy subsequently accepted the measured 177/200 result for development trial chat.
The separate [operator acceptance record](ML_OPERATOR_ACCEPTED_TRIAL_20261027.md)
preserves the failed scientific qualification and the research artifact label.
The 500-case OpenRouter study is complete and failed qualification; no live
promotion was performed. See [final results](ML_OPENROUTER_FINAL_20261027.md).
Latest continuation with the new OpenAI/OpenRouter keys, a 500-case campaign,
routing scope guards and its five-minute monitor:
[ML_NEW_KEYS_PROGRESS_20261027.md](ML_NEW_KEYS_PROGRESS_20261027.md).
The expanded second training round is recorded in
[ML_ROUND2_TRAINING_20261027.md](ML_ROUND2_TRAINING_20261027.md): 543 measured DEV rows,
source-family deduplication, frozen recipe comparison and daily-quota blockers.
The subsequent real-data run and its failed activation decision are recorded in
[ML_LIVE_QUALIFICATION_20261027.md](ML_LIVE_QUALIFICATION_20261027.md). The current
catalog is `smartllm-routing-v5`; the v4 notes below describe the preceding audit.
Loading an artifact, a `qualified_dev` string, or a moving Galaxy does not prove that
ML or Attention executed for a request. Simulation is never live quality evidence.

## Current deployment audit (2026-10-27)

`router readiness` inspected the selected artifact without making a provider call
(before the catalog profile migration):

- ML loads, but the selected artifact has no Attention and remains a research candidate.
- Runtime configuration hashes, reference and cost/catalog snapshot differ from its training snapshot.
- The other Attention artifact loads on CPU, but its grader is
  `synthetic-labels-v3-not-a-grader`; it cannot be promoted as measured evidence.
- The local training cache is empty. The artifact from a 96-sample live pilot is
  present, but its underlying measured DEV/HOLDOUT response cache is not available here.
  Compose bind-mounts this same `data` directory at `/app/data`; it defines no separate
  data volume. The Docker engine is stopped, so older containers could not be inspected.
- Existing Groq output reserves of 8192 exceed the default local 6400 TPM admission
  profile before input is added. A new generation profile is required.

The active catalog is now `smartllm-routing-v4`, with canonical 2048-output-token
profiles and no duplicate generation aliases. Its original file was backed up under
`data/backups/models.before-routing-v4-20261027-*.json`. Read-only model-list checks
confirmed access for the configured Groq/OpenAI models. The three native OpenAI
profiles are operationally approved for paid failover under the user's explicit
choice and existing pricing/budget constraints; this is not measured ML quality
evidence. No `.env`, server key, existing ML artifact, history or unresolved
reservation was rewritten. The ML remains blocked pending measured qualification.

## 1. Freeze a reviewed generation profile

Use the repository `.venv` Python (with `backend` on PYTHONPATH):

```powershell
python -m app.cli router prepare-catalog --source config/models.json --output config/models.routing-next.json --version smartllm-routing-next-1 --max-output-tokens 2048
```

The command writes a new file, removes duplicate endpoint/credential/model aliases,
uses IDs containing the output reserve and refuses to overwrite the source. Review
endpoint, key profile, access, pricing, tool capability and output needs before
selecting this catalog. Longer tasks may need a separately measured 4096 profile.
Do not silently truncate prompts or retrofit old observations to changed settings.

Only model profiles explicitly reviewed for failover should receive
`fallback_approved: true` in this new versioned catalog. Access/pricing verification
alone does not establish quality. Paid failover remains subject to existing
request, user and project USD limits. No automatic top-up or budget increase occurs.

Apply the additive `h107` migration before using persistent quotas. Back up the
database first. Do not reset accounts, history or unresolved reservations.

## 2. Obtain measured data and compare ML with ML + Attention

Restore the original pilot cache/manifest if available. Reuse a response only if its
exact generation configuration and price snapshot match. Otherwise collect new
responses through the existing reviewed, metered Router Lab pipeline with an explicit
run budget. `RESEARCH_LIVE_ENABLED` controls research collection, not ordinary chat;
never enable it from tests or CI.

Keep source/conversation groups independent across TRAIN, CALIBRATION, THRESHOLD and
HOLDOUT. Freeze thresholds before HOLDOUT. Label provenance must include reviewed
gold/human verification, grader version and response hash. Synthetic outcome/latency
fixtures remain `software_test`, even when prompts originate from public datasets.

Train two artifacts on the same DEV snapshot:

```powershell
python -m app.cli router auto-train --dataset data/reviewed/dev.json --output config/router_candidate_ml.json --hybrid
python -m app.cli router auto-train --dataset data/reviewed/dev.json --output config/router_candidate_attention.json --hybrid --flash-attention --encoder config/encoder.minilm-int8.json
```

`--flash-attention` is the existing CLI name for training the attention head. It does
not claim GPU Flash Attention is active. Serving defaults to the NumPy CPU path over
the pinned local INT8 ONNX encoder. Loader hash checks never download model weights.

Training produces candidates, never serving approval. Import in Router Lab changes
research experiments only. Run a bounded paired **evaluation pilot**, with the same
generation settings and input cases, to measure router/storage overhead and E2E
latency; do not activate the unreviewed candidate for ordinary chat to run this pilot.

The E2E JSON report must include `execution_source: "live"`, `configuration_hashes`,
actual ledger `provider_call_ids`, `attention_artifact_hash`, `ml_artifact_hash`,
`p50_latency_ratio` (Attention route versus fixed reference), and
`critical_regressions`. Preserve its source evidence for operator review.

## 3. Qualify, promote and activate

```powershell
python -m app.cli router qualify --dataset data/reviewed/dev.json --holdout data/reviewed/holdout.json --model config/router_candidate_attention.json --compare-model config/router_candidate_ml.json --e2e-report data/reviewed/e2e.json --reviewed-by Huy --report output/router-live-qualification.json --output config/router_live_qualified.json --review-output config/router_live_qualified.review.json
```

This command never calls providers or overwrites artifacts. FAIL writes reasons and
does not create a serving artifact. PASS requires exact snapshot matching, reviewed
measured labels, independent HOLDOUT, no critical pilot regressions and E2E median
latency ratio at most 1.10. Per-domain source-group regression rates must have an
exact one-sided 95% upper bound no greater than 3%. This conservative promotion guard
is distinct from a universal scientific non-inferiority conclusion; small samples
are explicitly insufficient. The report includes the ML-only ablation for review.

Only after reviewing a PASS and the corresponding catalog, set:

```dotenv
AUTO_ROUTING_STRATEGY=ml_multi_model
ML_ROUTER_ARTIFACT_PATH=config/router_live_qualified.json
ML_ROUTER_QUALIFICATION_PATH=config/router_live_qualified.review.json
ML_ROUTER_LIVE_APPROVED=true
ML_ROUTER_ALLOW_RESEARCH_CANDIDATE=false
```

Restart the backend; then run `python -m app.cli router readiness`. Trace separately
records ML/Attention loaded/executed and the actual per-request attention features.
These six learned features are not labelled as measured difficulty or correctness.
Galaxy uses identities from the request's calls, with illustrative coordinates;
it does not draw obsolete default models or invented attention values. Old traces
remain readable with unknown runtime metadata.

Rollback: set `AUTO_ROUTING_STRATEGY=rule_guarded`, restore the prior reviewed catalog
and restart. Keep the baseline if routing/Attention provides no demonstrated benefit.

## Quota and financial behavior

Published defaults checked on 2026-10-26:

- Groq GPT OSS 20B/120B and Qwen 3.8: 30 RPM, 1000 RPD, 8000 TPM, 200000 TPD.
  Exact organization limits may differ: https://console.groq.com/docs/rate-limits
- OpenRouter free: 20 RPM and 50 RPD; a qualifying credit purchase raises the daily
  ceiling. Failed attempts can consume quota. Check the actual account:
  `python -m app.cli router provider-limits` (metadata GET only, no inference).
  https://openrouter.ai/docs/api_reference/limits

Local defaults are 80%: Groq 24/800/6400/160000; OpenRouter free 16 RPM/40 RPD.
Set `OPENROUTER_FREE_RPD=800` only after the account reports a 1000/day ceiling.
Configure one `PROVIDER_QUOTA_ACCOUNT` per real organization/account; rotating keys
does not create new capacity. OpenRouter free variants share a daily pool. Groq
model aliases share an endpoint/account/model bucket. SQLite atomic claims survive
workers and restarts; its database must be shared by all server workers.

Every generation path, including research collection, reserves before SDK dispatch.
Known token usage reconciles the reservation; unknown usage remains conservative.
Response headers can reduce available capacity; Retry-After is honored. OpenRouter
daily counters reset at UTC midnight; absent authoritative Groq resets, rolling
24-hour local accounting is conservative. These local controls cannot account for
other applications sharing keys until provider headers/account data reveal usage.

At most two model failovers are allowed per chat request. Ambiguous timeout/connection
or server failure stops automatic paid failover and retains unresolved USD accounting.
Upstream auth errors are provider configuration errors, never user-login expiry.
Successful calls may be streamed over SSE **after one metered execution completes**;
this transport does not claim provider-token streaming or measured TTFT.

`GET /v1/traces/{request_id}/calls` returns owned diagnostics even when the chat failed:
model/config, provider host, safe error code, upstream status, retry delay and dispatch
state. It excludes keys, private provider messages and prompt text; other users get 404.
# Cập nhật 27/10: tiếp tục provider và chờ đối soát

[Báo cáo Groq/OpenAI mới nhất](ML_PROVIDER_CONTINUATION_20261027.md): đã huấn luyện
bản Attention mới bằng dữ liệu OpenAI thật, chưa đạt qualification; Huy yêu cầu
đối soát xong lần gọi mất kết nối trước mọi generation trả phí tiếp theo. Trần key
OpenRouter 100 USD không phải số dư credits. Không bật live hoặc chạy lại cuộc gọi
chưa xác định để vượt tình trạng này.
