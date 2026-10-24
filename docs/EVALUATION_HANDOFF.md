# Evaluation harness handoff

Cập nhật ngày 24/10/2026 trên nhánh `feat/Khoa/g2-sea-ifeval`.

## Trạng thái

Evaluation harness hiện đạt mức **engineering-ready functional harness**:

- Có canonical `EvalCase` tách serving input khỏi evaluator-only target.
- Có loader, manifest validation, source qualification record và frozen split validation.
- Có deterministic graders cho instruction following, extractive QA, memory probe và MCQ.
- Có candidate adapters cho SEA-IFEval, VMLU, UIT-ViQuAD và normalized Vi-Dialog probes.
- Có paired baseline/optimized comparison, aggregate quality, usage, cost và latency.
- Có deterministic JSONL/JSON exporting kèm SHA-256.
- Có live suite budget guard và DEV/qualified-source gates.
- Có `OrchestratorLiveExecutor` nối harness với orchestrator qua namespace `eval`.
- Có session isolation và purge sau mỗi execution arm.
- Có test ghép toàn tuyến executor → live suite → grading → export.
- Mock/synthetic execution luôn giữ `research_eligible=false`.

Trạng thái này chứng minh luồng kỹ thuật hoạt động. Nó chưa chứng minh chất lượng, savings, Pareto improvement hoặc kết quả nghiên cứu trên bốn benchmark thật.

## Thành phần chính

- `backend/app/evaluation/cases.py`: canonical evaluation DTOs.
- `backend/app/evaluation/loader.py`: JSONL loader và SHA-256 validation.
- `backend/app/evaluation/manifests.py`: case-set manifest validation.
- `backend/app/evaluation/sources.py`: source qualification gates.
- `backend/app/evaluation/splits.py`: frozen split validation.
- `backend/app/evaluation/graders.py`: deterministic graders.
- `backend/app/evaluation/dispatcher.py`: grader dispatch.
- `backend/app/evaluation/sea_ifeval.py`: pinned SEA-IFEval evaluator.
- `backend/app/evaluation/sea_ifeval_adapter.py`: SEA-IFEval row adapter.
- `backend/app/evaluation/vmlu_adapter.py`: candidate VMLU row adapter.
- `backend/app/evaluation/uit_viquad_adapter.py`: candidate UIT-ViQuAD row adapter.
- `backend/app/evaluation/vi_dialog_adapter.py`: candidate normalized conversation/probe adapter.
- `backend/app/evaluation/live_runner.py`: paired live execution.
- `backend/app/evaluation/live_harness.py`: suite aggregation and budget guards.
- `backend/app/evaluation/live_exporting.py`: deterministic live report export.
- `backend/app/evaluation/orchestrator_executor.py`: orchestrator adapter.
- `benchmark/fixtures/four_suite_smoke/`: synthetic four-family functional fixture.

## Verification hiện tại

Chạy từ repository root với virtual environment đã kích hoạt.

```bash
.venv/bin/python -m ruff check \
  backend/app/evaluation \
  backend/tests/evaluation

.venv/bin/python -m ruff format --check \
  backend/app/evaluation \
  backend/tests/evaluation

.venv/bin/python -m mypy \
  --config-file backend/pyproject.toml \
  backend/app/evaluation
```

Kết quả ghi nhận ngày 24/10/2026:

- Ruff check: pass.
- Ruff format: 52 files đã đúng format.
- Mypy: 27 source files, không có lỗi.

Chạy toàn bộ evaluation tests mà không cho phép API key:

```bash
env \
  PROVIDER_MODE=mock \
  RESEARCH_LIVE_ENABLED=false \
  OPENAI_API_KEY= \
  OPENROUTER_API_KEY= \
  GROQ_API_KEY= \
  GEMINI_API_KEY= \
  .venv/bin/python -m pytest \
  backend/tests/evaluation \
  -q
```

Kết quả: `276 passed`.

Kiểm tra toàn bộ backend với mock provider và catalog cục bộ bị vô hiệu hóa ghi nhận `420 passed, 2 failed`. Hai lỗi còn lại đều tái hiện trên `origin/develop` tại:

- `backend/tests/integration/test_documents_usage.py::test_document_lifecycle_dedupe_rag_fulltext_and_purge`;
- `backend/tests/integration/test_documents_usage.py::test_live_metering_fakes_settlement_failure_and_dedupe`.

Cả hai là sai khác expectation của `totals.usd` trong usage/ledger, nằm ngoài phạm vi evaluation và không phát sinh từ thay đổi của harness. File `config/models.json` cục bộ bị Git ignore có thể làm kết quả full-backend khác CI; evaluation tests phía trên luôn vô hiệu hóa live API và không phụ thuộc catalog này.

Chạy functional smoke:

```bash
env \
  PROVIDER_MODE=mock \
  RESEARCH_LIVE_ENABLED=false \
  OPENAI_API_KEY= \
  OPENROUTER_API_KEY= \
  GROQ_API_KEY= \
  GEMINI_API_KEY= \
  .venv/bin/python -m app.cli eval run \
  --purpose smoke \
  --manifest benchmark/manifests/smoke.json
```

Kết quả: 3 functional cases, mock execution, quality/savings unknown.

Chạy synthetic four-suite flow:

```bash
env \
  PROVIDER_MODE=mock \
  RESEARCH_LIVE_ENABLED=false \
  OPENAI_API_KEY= \
  OPENROUTER_API_KEY= \
  GROQ_API_KEY= \
  GEMINI_API_KEY= \
  .venv/bin/python \
  benchmark/fixtures/four_suite_smoke/run_demo.py
```

Kết quả fixture:

- Baseline: 1/4 functional cases passed.
- Optimized: 4/4 functional cases passed.
- Report SHA-256: `8688c3e32272b676408428ab4d6c5ea329146665de04256efe9ec258fee2ff9d`.
- `RESEARCH_ELIGIBLE: False`.

Các prediction trong fixture được dựng trước để kiểm tra wiring. Chênh lệch 1/4 và 4/4 không phải bằng chứng optimizer thật cải thiện chất lượng.

## Ranh giới leakage

- Provider chỉ nhận `serving_input`.
- Gold answer, instruction rules, evidence turn IDs và evaluator targets chỉ đi tới grader.
- Test export xác nhận `evaluator_target` không xuất hiện trong paired live result.
- Memory case chỉ được replay đến checkpoint; future turns không được đưa vào serving.
- VMLU duplicate-content groups và UIT-ViQuAD document groups không được trải qua cả DEV và HOLDOUT.
- Functional fixtures không được dùng để qualify nguồn nghiên cứu.

## Blocker trước live engineering pilot

1. Chưa có CLI/composition-root được owner review để dựng `OrchestratorLiveExecutor` với orchestrator, session store và principal thật.
2. Huy cần review:
   - namespace `eval`;
   - baseline/optimized flags;
   - session create/purge;
   - ledger category và budget enforcement;
   - model/catalog identity trong trace.
3. Memory live hiện chủ động từ chối history vì chưa có owner-reviewed session-history seeding port.
4. Live pilot chỉ được bật có chủ đích với reviewed catalog, server-side key và budget đã duyệt.
5. Tests và CI không được bật live hoặc thực hiện paid API calls.

## Blocker trước benchmark nghiên cứu chính thức

### SEA-IFEval

Qualification hiện là `candidate/BLOCKED`.

Candidate adapter đã có schema validation, answer-key isolation, duplicate-content grouping và adapter-to-grader tests. Adapter này không giải quyết các blocker về nguồn.

Còn thiếu:

- pin và review language detector package/model assets;
- independent review cho Vietnamese counting protocol;
- license, attribution và evaluator sign-off.

### VMLU

Qualification hiện là `candidate/BLOCKED`.

Còn thiếu:

- explicit dataset license hoặc redistribution permission;
- immutable official revision và checksums;
- authoritative split mapping;
- authoritative subject/category mapping;
- duplicate grouping/exclusion policy;
- pinned prompt/evaluator protocol.

### UIT-ViQuAD

Đã có candidate row adapter và synthetic adapter-to-grader tests. Chưa có qualification record, source audit, frozen split hoặc research manifest trên dữ liệu thật.

Phải giữ toàn bộ valid answers, answer spans, `is_impossible`, document/source IDs và không dùng `plausible_answers` làm gold.

### Vi-Dialog

Đã có adapter cho normalized conversation/probe rows, checkpoint isolation và synthetic adapter-to-grader tests. Chưa có qualification record, mapping từ raw source, frozen conversation split hoặc reviewed memory probes trên dữ liệu thật.

Các probe tự xây dựng chỉ là adapted protocol, không được gọi là official Vi-Dialog memory score.

## Research gate

`research_eligible` hiện được cố định `False`. Đây là safety gate có chủ đích, không phải lỗi cần đổi ngay.

Chỉ xem xét mở research mode sau khi:

1. nguồn được đánh dấu `QUALIFIED` với review evidence;
2. DEV/HOLDOUT được frozen theo source group;
3. adapters và evaluator versions được khóa;
4. manifest lưu data/code/catalog/policy/pricing hashes;
5. live composition được Huy review;
6. budget và call matrix được duyệt;
7. thresholds được khóa trước khi xem HOLDOUT;
8. report giữ cả failure, unknown usage và unknown cost.

## Ownership và bước tiếp theo

Khoa sở hữu evaluation cases, adapters, graders, source qualification, splits, runner và reports.

Huy sở hữu orchestrator composition, API/auth/storage/session, ledger/provider/router wiring và frontend.

Bước tiếp theo được đề xuất:

1. Huy review `orchestrator_executor.py` và quyết định composition/CLI entrypoint.
2. Khoa giữ harness ở trạng thái functional nếu chưa đủ thời gian qualification.
3. Qualification từng nguồn được thực hiện riêng, không đổi `candidate` thành `qualified` chỉ để chạy live.
4. Sau qualification mới tạo frozen research manifests và chạy DEV pilot có ngân sách.
5. HOLDOUT chỉ chạy sau khi policy và thresholds đã khóa.

Xem thêm:

- [Design specification](../SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md)
- [MVP handoff](MVP_HANDOFF.md)
- [SEA-IFEval scoring protocol](../benchmark/protocols/sea_ifeval_vi_v1_1.md)
