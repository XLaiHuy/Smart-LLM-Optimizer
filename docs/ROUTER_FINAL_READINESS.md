# Router final candidate — 22/10/2026

Ready for local software integration and review. **Not qualified for real model
quality, cost savings, or production ML routing.** Mock/live gates stay in place.
`ML_ARTIFACT_READY` means the artifact can load, not that its quality is established.

## Fixed behavior

- Attention targets are joined by config ID, independent of observation order.
- Encoder initialization/inference failures become controlled fallback errors.
  An unavailable shared-state adapter falls back to standalone ONNX.
- Recipe `feature-view-v2-balanced-token-budget` reserves tokens for the final
  question/instructions and recent/evidence sections. It changes feature inputs,
  so V1 artifacts retain V1 behavior and the V3 candidate was retrained.
- Runtime keeps NumPy weights and predictor coefficients; SDPA keeps one module
  per device. The bounded LRU cache is synchronized, while independent NumPy/ORT
  cache misses can run concurrently. Routing computation runs outside the async
  event loop. Training uses batches of 64 instead of one full backward batch.
- Full VMLU options, including E, are retained without doubled A./B. prefixes.
- DEV units are grouped by template, question, or source document before splitting.
  Generated IDs are removed from inputs. Normalized content hashes additionally
  reject cross-split duplicates and HOLDOUT reuse disguised with a new ID.
- Encoder/Torch preflight precedes source collection and any paid distillation.
- Threshold selection uses DEV only. Quality/latency guardrails are checked first;
  eligible choices are ordered by USD, latency, then conservative thresholds.
  No USD + unitless penalty. HOLDOUT scripts no longer sweep/tune thresholds.
- Optional ML lock uses the base dependency lock as constraints. SQLite feedback
  needs migration `g106`; the local database was backed up before upgrade.

## Data and evidence

`prepare_final_router_dataset.py` produced **2,711 unique inputs**:
1,161 train, 431 calibration, 515 threshold, 604 HOLDOUT. It removed 4,289 copies
from the prior 7,000 rows. The four splits have no overlapping content or source
families under the implemented exact-normalization/source-group checks. This does
not prove the absence of all semantic near-duplicates. Coverage is uneven and
small for several domains; no perfect class balance or statistical power claim.

All correctness labels, token counts, prices and provider latencies remain
**simulation observations**. Public VMLU/ViQuAD inputs do not make those outcomes
real. Original licenses/graders need review; the public VMLU test used here has no
gold answer keys. SEA-IFEval is access restricted and has not been downloaded.

The new candidate has 15 attention epochs and two 100-tree predictors. Frozen
thresholds are 1.0/1.0; it selects reference throughout this HOLDOUT. Therefore
this run establishes **no cost saving**, and is not presented as improved quality.
Six attention features are learned pooling features, not seven verified domain
classifiers. CPU NumPy inference is the default; CUDA FlashAttention is unverified.

## Reproduce locally

Install the base environment as documented in README, then optional ML/data
dependencies from `backend/requirements-router-ml.lock`. Weights are not in Git:

```powershell
.venv\Scripts\python.exe scripts/prepare_flash_resources.py --encoder --datasets
.venv\Scripts\python.exe scripts/prepare_final_router_dataset.py
.venv\Scripts\python.exe -m app.cli router auto-train --dataset data/research/router-final-dev-v3.json --output config/router_final_candidate.json --flash-attention --encoder config/encoder.minilm-int8.json --allow-test-data --attention-epochs 15 --n-estimators 100
.venv\Scripts\python.exe scripts/eval_golden_holdout.py
.venv\Scripts\python.exe scripts/profile_router_cpu.py --samples 30 --concurrency 4
```

Training refuses to overwrite existing output unless `--overwrite` is explicitly
provided. Archive the old candidate or choose a fresh filename before reproducing.
The resource downloader makes public downloads only; tests never download assets
or call paid providers. Legacy dataset CLI entry points delegate to the V3 builder.

Local artifacts:

- `config/router_final_candidate.json`: software test candidate.
- `data/research/router-final-audit-v3.json`: split counts, hashes and limitations.
- `output/router-final/holdout.json`: frozen replay, with simulation labeling.
- `output/router-final/profile.json`: load, cache miss/hit and concurrent timings.
- `output/router-final/`: previous artifact copies for rollback.

Profiler measures actual policy selection, excluding HTTP/DB/provider time. It
reports cache misses, cache hits and concurrency separately; it does not infer
an LLM latency overhead percentage from cached scores.

Latest local sample (30 inputs, 4 concurrent workers, Windows/Python 3.11.9):
cache-miss P50/P95 **85.5/122.8 ms**, cache-hit **12.2/21.6 ms**; concurrent-miss
P50/P95 **124.4/149.9 ms**, about **34 requests/s**. Load took about 3.9 seconds.
These are local observations, not a capacity guarantee or a comparison on identical
data with the old artifact. The encoder remains the main cost on a cache miss.

Verification: full backend run **164 passed**; subsequent source-cache and CLI
regression checks also passed. Frontend **5 passed**, TypeScript, ESLint, Ruff,
mypy, generated contracts and documentation checks passed. No paid provider calls.
CLI now reports `learned_attention_ready`, `inference_backend`, per-candidate
feature counts and `cuda_flash_verified=false` instead of treating CPU attention
as proof of FlashAttention readiness.

## Remaining requirements for live qualification

Use reviewed source licenses, versioned deterministic graders and real provider
observations (or auditable real response caches); freeze DEV and independent
HOLDOUT before tuning. Account for router/storage overhead and paired uncertainty.
Configure the training manifest/server key/budget for paid distillation explicitly.
The admin pipeline can import a passing candidate into research; it does not
promote software tests into chat. Tân's adapter must match the encoder fingerprint,
token recipe and feature-view digest; the standalone fallback already works.
