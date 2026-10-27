"""Faults, long/hybrid prompts and optimizer work bounds; no external providers."""

import asyncio
import json
import sys
import threading
from statistics import median
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.config import ROOT
from app.contracts.dtos import FeatureFlags
from app.optimizers import llmlingua_compressor
from app.optimizers.preservation import check_preservation
from app.optimizers.prompt_optimizer import AdaptivePromptOptimizer


async def test_readiness_checks_storage_instead_of_static_platform(client, app, monkeypatch):
    assert (await client.get("/v1/health/ready")).status_code == 200

    class FailedSession:
        async def __aenter__(self):
            raise OperationalError("SELECT users", {}, Exception("private disk detail"))

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(app.state.container.db, "sessions", FailedSession)
    # Public readiness does not need a login or disclose exception details.
    client.cookies.clear()
    result = await client.get("/v1/health/ready")
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "private disk" not in result.text
    assert (await client.get("/v1/platform-info")).status_code == 200


async def test_timed_out_compressor_cannot_start_additional_cpu_workers():
    started = threading.Event()
    release = threading.Event()
    count = []

    class BlockingCompressor:
        def compress(self, prompt):
            count.append(1)
            started.set()
            release.wait(2)
            return {"compressed": prompt, "status": "skipped"}

    optimizer = AdaptivePromptOptimizer(
        BlockingCompressor(),
        min_compress_tokens=1,
        llm_threshold=1,
        compression_timeout_seconds=0.02,
    )
    prompt = "Long content to exercise bounded compression. " * 30
    request = SimpleNamespace(request=SimpleNamespace(message=prompt))
    try:
        first = await optimizer.optimize(request, None, FeatureFlags(rewrite=True))
        assert started.is_set()
        assert first.proposed == prompt and first.state.reason == "llmlingua_timeout"
        second = await optimizer.optimize(request, None, FeatureFlags(rewrite=True))
        assert second.proposed == prompt and second.state.reason == "llmlingua_busy"
        assert len(count) == 1
    finally:
        release.set()
        for _ in range(100):
            if not optimizer._compression_slot.locked():
                break
            await asyncio.sleep(0.01)
    assert not optimizer._compression_slot.locked()


async def test_storage_failure_always_has_safe_json_envelope(client, app):
    @app.get("/audit-storage-fault")
    async def fault():
        raise OperationalError("private query", {}, Exception("private path"))

    response = await client.get("/audit-storage-fault")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "private" not in response.text


def test_missing_local_weights_never_download_or_import_heavy_compressor(tmp_path, monkeypatch):
    observed = []

    def local_snapshot(repository, **kwargs):
        observed.append(kwargs)
        assert kwargs["local_files_only"] is True
        return str(tmp_path)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=local_snapshot)
    )

    def forbidden_import(name):
        raise AssertionError("Do not import heavy compressor before assets are ready")

    monkeypatch.setattr(llmlingua_compressor, "import_module", forbidden_import)
    compressor = llmlingua_compressor.LLMLinguaCompressor()
    with pytest.raises(FileNotFoundError, match="prepared before serving"):
        compressor._ensure_compressor()
    assert len(observed) == 1
    assert len(observed[0]["revision"]) == 40


@pytest.mark.parametrize(
    "before,after",
    [
        ("không ít hơn 10", "không nhiều hơn 10"),
        ("at least 10", "at most 10"),
        ("Giữ -75 trong đáp án", "Giữ 75 trong đáp án"),
        ("Kết quả −524", "Kết quả 524"),
    ],
)
def test_compression_never_certifies_reversed_bounds_or_removed_negative_sign(before, after):
    assert check_preservation(before, after) != "preserved"


@pytest.mark.parametrize(
    "prompt",
    [
        "1+1?",
        "".join("Dữ liệu nền.\n" for _ in range(1500)) + "Mã cuối OU-4729",
        "```python\ndef f(x): return x*x\n```\nGiải thích",
        "không ít hơn 10 và không nhiều hơn 20; giữ −75",
    ],
    ids=["short", "long", "code", "hybrid"],
)
async def test_short_long_code_and_hybrid_prompts_commit_one_pair(client, prompt):
    sid = (await client.post("/v1/sessions", json={"title": "audit"})).json()["id"]
    body = {
        "session_id": sid,
        "client_request_id": str(uuid4()),
        "message": prompt,
        "mode": "optimized",
        "flags": {"router": True, "rewrite": True, "context": True, "memory": True},
    }
    first = await client.post("/v1/chat", json=body)
    assert first.status_code == 200, first.text
    replay = await client.post("/v1/chat", json=body)
    assert replay.json()["request_id"] == first.json()["request_id"]
    messages = (await client.get(f"/v1/sessions/{sid}")).json()["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == prompt


async def test_concurrent_chat_writes_and_readiness_remain_responsive(client, app):
    original = app.state.container.orchestrator.provider.generate

    class DelayedProvider:
        async def generate(self, messages, opts):
            await asyncio.sleep(0.03)
            return await original(messages, opts)

    app.state.container.orchestrator.provider = DelayedProvider()
    session_ids = []
    for i in range(12):
        session_ids.append(
            (await client.post("/v1/sessions", json={"title": f"parallel-{i}"})).json()["id"]
        )

    async def submit(sid):
        started = perf_counter()
        result = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": str(uuid4()),
                "message": "Tính 1+1, trả lời ngắn.",
                "mode": "optimized",
            },
        )
        return result, (perf_counter() - started) * 1000

    results = await asyncio.wait_for(
        asyncio.gather(*(submit(sid) for sid in session_ids)), timeout=30
    )
    assert all(response.status_code == 200 for response, _ in results)
    for sid in session_ids:
        assert len((await client.get(f"/v1/sessions/{sid}")).json()["messages"]) == 2
    assert (await client.get("/v1/health/ready")).status_code == 200
    durations = sorted(ms for _, ms in results)
    path = ROOT / "output/project-audit/system-concurrency-mock-20261027.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "execution_source": "mock",
                "parallel_sessions": 12,
                "success": 12,
                "committed_message_pairs": 12,
                "p50_ms": median(durations),
                "p95_ms": durations[-1],
                "p95_method": "nearest rank, n=12; descriptive only",
                "no_provider_network": True,
            },
            indent=2,
        ),
        encoding="utf8",
    )
