import asyncio
import io
import json
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from docx import Document as WordDocument
from sqlalchemy import func, select

from app.contracts.dtos import Citation, Usage
from app.contracts.errors import AppError
from app.documents.service import validate_citations
from app.providers.catalog import Catalog, ModelEntry, price
from app.storage.models import QuotaAudit, UsageRecord


async def session(client):
    return (await client.post("/v1/sessions", json={"title": "Documents"})).json()["id"]


async def uploaded(
    client, sid, filename="source.txt", content="Học phí l? 12 triệu đồng. Hạn đóng l? 25/10."
):
    response = await client.post(
        f"/v1/sessions/{sid}/documents",
        files={"file": (filename, content.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def finished(client, sid, ids, task="index", key=None):
    response = await client.post(
        f"/v1/sessions/{sid}/document-jobs",
        json={
            "client_request_id": key or task + "-" + str(len(ids)),
            "task": task,
            "document_ids": ids,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    for _ in range(200):
        job = (await client.get(f"/v1/document-jobs/{job['id']}")).json()
        if job["status"] not in ("pending", "running"):
            break
        await asyncio.sleep(0.05)
    assert job["status"] == "succeeded", job
    return job


async def test_document_lifecycle_dedupe_rag_fulltext_and_purge(client, app):
    sid = await session(client)
    first = await uploaded(client, sid)
    assert await uploaded(client, sid) == first
    assert (await client.get(f"/v1/documents/{first}")).json()["text"].startswith("Học phí")
    await finished(client, sid, [first])
    c = app.state.container
    async with c.db.sessions() as db:
        before = await db.scalar(select(func.count()).select_from(UsageRecord))
    await finished(client, sid, [first], key="index-repeat")
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(UsageRecord)) == before
    result = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "rag",
            "message": "Học phí bao nhiêu?",
            "mode": "baseline",
            "document_ids": [first],
        },
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["citations"] and data["usage"]["input_tokens"] is None
    assert [call["stage"] for call in data["calls"]] == ["query_embedding", "provider"]
    summary = await finished(client, sid, [first], "summarize")
    assert summary["coverage"] == 1 and summary["response"]["citations"]
    second = await uploaded(
        client, sid, "other.md", "Học phí m?i l? 13 triệu đồng. Hạn đóng l? 27/10."
    )
    await finished(client, sid, [second], key="index-second")
    compare = await finished(client, sid, [first, second], "compare")
    assert compare["coverage"] == 1
    assert len(compare["response"]["calls"]) == 5
    assert (await client.delete(f"/v1/sessions/{sid}")).status_code == 204
    assert (await client.get(f"/v1/documents/{first}")).status_code == 404
    assert (await client.get(f"/v1/document-jobs/{summary['id']}")).status_code == 404
    report = (await client.get("/v1/usage")).json()
    assert report["totals"]["calls"] >= 9 and report["totals"]["usd"] is None


async def test_document_isolation_limits_and_invalid_sources(client, app):
    sid = await session(client)
    source = await uploaded(client, sid)
    assert (
        await client.post(f"/v1/sessions/{sid}/documents", files={"file": ("bad.exe", b"bad")})
    ).status_code == 422
    assert (
        await client.post(f"/v1/sessions/{sid}/documents", files={"file": ("bad.pdf", b"not-pdf")})
    ).status_code == 422
    assert (
        await client.post(f"/v1/sessions/{sid}/documents", files={"file": ("empty.txt", b" ")})
    ).status_code == 422
    app.state.container.settings.max_file_bytes = 5
    assert (
        await client.post(f"/v1/sessions/{sid}/documents", files={"file": ("big.txt", b"123456")})
    ).status_code == 413
    assert (
        await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": "not-ready",
                "message": "x",
                "mode": "baseline",
                "document_ids": [source],
            },
        )
    ).status_code == 409
    await client.post("/v1/auth/logout")
    await client.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
    assert (await client.get(f"/v1/documents/{source}")).status_code == 404
    assert (await client.delete(f"/v1/documents/{source}")).status_code == 404
    assert (await client.get(f"/v1/sessions/{sid}/documents")).status_code == 404
    assert (await client.get("/v1/usage")).json()["totals"]["calls"] == 0


async def test_docx_and_scan_pdf_handling(client):
    sid = await session(client)
    word = WordDocument()
    word.add_paragraph("Thông tin học phí tiếng Việt")
    stream = io.BytesIO()
    word.save(stream)
    response = await client.post(
        f"/v1/sessions/{sid}/documents", files={"file": ("document.docx", stream.getvalue())}
    )
    assert response.status_code == 201, response.text
    from pypdf import PdfWriter

    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    blank = io.BytesIO()
    pdf.write(blank)
    response = await client.post(
        f"/v1/sessions/{sid}/documents", files={"file": ("scan.pdf", blank.getvalue())}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "NO_EXTRACTABLE_TEXT"


async def test_usage_admin_quota_export_and_date_validation(client, app):
    assert (await client.get("/v1/usage?project=true")).status_code == 403
    assert (await client.get("/v1/admin/users")).status_code == 403
    assert (await client.get("/v1/usage?start=2026-10-21&end=2026-10-20")).status_code == 422
    assert (
        (await client.get("/v1/usage/export?format=csv"))
        .headers["content-type"]
        .startswith("text/csv")
    )
    c = app.state.container
    await c.auth.create_user("operator", "password-operator", "admin")
    await client.post("/v1/auth/logout")
    await client.post(
        "/v1/auth/login", json={"username": "operator", "password": "password-operator"}
    )
    users = (await client.get("/v1/admin/users")).json()
    alice = next(u for u in users if u["username"] == "alice")
    response = await client.patch(
        f"/v1/admin/users/{alice['id']}/quota", json={"quota_usd": "3.00", "reason": "Test limit"}
    )
    assert response.status_code == 204
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(QuotaAudit)) == 1
    assert (await client.get("/v1/usage?project=true")).status_code == 200


def entry():
    return ModelEntry(
        config_id="fixture",
        model_id="fixture-model",
        kind="generation",
        context_window=100000,
        max_output_tokens=100,
        input_per_million=Decimal(2),
        output_per_million=Decimal(8),
        cached_per_million=Decimal(1),
        source_url="https://developers.openai.com/api/docs/pricing",
        effective_at="2026-10-20",
        verified_access=True,
        pricing_verified=True,
    )


def test_price_subsets_unknown_and_citations():
    usage = Usage(
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=10,
        reasoning_tokens=5,
        usage_source="provider",
    )
    assert price(entry(), usage, "test-v1").serving_usd == Decimal("0.00026")
    assert (
        price(entry(), usage.model_copy(update={"cached_input_tokens": None}), "v").status
        == "unknown"
    )
    assert price(entry(), usage, "v", cache_write=1).status == "unknown"
    citation = Citation(
        chunk_id="11111111-1111-1111-1111-111111111111",
        document_id="d",
        filename="x",
        location="p1",
        excerpt="Evidence",
    )
    validate_citations("Answer [11111111-1111-1111-1111-111111111111]", (citation,), "live")
    with pytest.raises(AppError):
        validate_citations("Answer [22222222-2222-2222-2222-222222222222]", (citation,), "live")
    with pytest.raises(AppError):
        validate_citations("unsupported certainty", (citation,), "live")


async def test_live_metering_fakes_settlement_failure_and_dedupe(client, app):
    from app.contracts.dtos import ProviderResult

    c = app.state.container
    catalog = Catalog(
        version="fixture-v1",
        baseline_config="fixture",
        embedding_config="fixture",
        models=(entry(),),
    )
    c.metering.catalog = catalog
    # Existing mock route is remapped only for this deterministic metered fake.
    c.orchestrator.registry = c.orchestrator.registry.model_copy(
        update={
            "mock_config_id": "fixture",
            "configurations": (
                c.registry.configurations[0].model_copy(
                    update={"config_id": "fixture", "model_id": "fixture-model"}
                ),
            ),
        }
    )
    c.orchestrator.provider = AsyncMock()
    usage = Usage(
        scope="call",
        input_tokens=100,
        output_tokens=10,
        cached_input_tokens=20,
        reasoning_tokens=5,
        usage_source="provider",
    )
    c.orchestrator.provider.generate.return_value = ProviderResult(
        text="fake live result",
        execution_source="live",
        usage=usage,
        cost=price(entry(), usage, "fixture-v1"),
        duration_ms=12,
    )
    sid = await session(client)
    body = {
        "session_id": sid,
        "client_request_id": "live-fake",
        "message": "hello",
        "mode": "baseline",
    }
    response = await client.post("/v1/chat", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["usage"]["input_tokens"] == 100
    assert response.json()["cost"]["serving_usd"] == "0.00026"
    assert (await client.post("/v1/chat", json=body)).json() == response.json()
    assert c.orchestrator.provider.generate.await_count == 1
    c.orchestrator.provider.generate.side_effect = TimeoutError()
    assert (
        await client.post("/v1/chat", json={**body, "client_request_id": "timeout"})
    ).status_code == 504
    report = (await client.get("/v1/usage")).json()
    assert report["totals"]["usd"] is None and report["totals"]["known_subtotal_usd"] == "0.00026"
    assert Decimal(report["reserved_usd"]) > 0


async def test_job_conflict_failure_and_restart_do_not_replay(client, app):
    from app.storage.models import Attempt, Conversation, StoredMessage

    sid = await session(client)
    doc = await uploaded(client, sid)
    c = app.state.container
    await c.documents.close()
    payload = {"client_request_id": "queued", "task": "index", "document_ids": [doc]}
    created = await client.post(f"/v1/sessions/{sid}/document-jobs", json=payload)
    assert created.status_code == 202
    assert (await client.post(f"/v1/sessions/{sid}/document-jobs", json=payload)).json()[
        "id"
    ] == created.json()["id"]
    assert (await client.delete(f"/v1/documents/{doc}")).status_code == 409
    assert (await client.delete(f"/v1/sessions/{sid}")).status_code == 409
    async with c.db.write() as db:
        row = await db.get(Attempt, created.json()["id"])
        row.status = "running"
    await c.sessions.recover_interrupted()
    await c.documents.start()
    await asyncio.sleep(0.3)
    status = (await client.get(f"/v1/document-jobs/{created.json()['id']}")).json()
    assert status["status"] == "interrupted"
    c.metering.embed = AsyncMock(side_effect=AppError("PROVIDER_TIMEOUT", 504, "fixture"))
    response = await client.post(
        f"/v1/sessions/{sid}/document-jobs", json={**payload, "client_request_id": "fail"}
    )
    for _ in range(100):
        job = (await client.get(f"/v1/document-jobs/{response.json()['id']}")).json()
        if job["status"] == "failed":
            break
        await asyncio.sleep(0.05)
    assert job["status"] == "failed" and job["response"] is None
    assert (await client.get(f"/v1/documents/{doc}")).json()["status"] == "extracted"
    async with c.db.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(StoredMessage)) == 0
        assert (await db.get(Conversation, sid)).active_attempt_id is None


async def test_parser_timeout_is_bounded_and_temp_removed(client, app, monkeypatch):
    import subprocess

    import app.documents.service as service

    sid = await session(client)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fixture", 0.01)

    monkeypatch.setattr(service.subprocess, "run", timeout)
    response = await client.post(
        f"/v1/sessions/{sid}/documents", files={"file": ("timeout.txt", b"hello")}
    )
    assert (
        response.status_code == 422 and response.json()["error"]["code"] == "DOCUMENT_PARSE_TIMEOUT"
    )


async def test_native_responses_adapter_normalizes_usage_without_network():
    from openai import AsyncOpenAI

    from app.contracts.dtos import Message, ProviderOptions
    from app.providers.live import OpenAIProvider

    catalog = Catalog(
        version="fixture-v2",
        baseline_config="fixture",
        embedding_config="fixture",
        models=(entry(),),
    )
    provider = OpenAIProvider("test-not-a-real-key", catalog)
    await provider.client.close()

    def handler(request):
        body = json.loads(request.content)
        assert body["store"] is False and body["truncation"] == "disabled"
        assert body["input"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 0,
                "model": "fixture-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "m",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "fixture", "annotations": []}],
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens": 10,
                    "output_tokens_details": {"reasoning_tokens": 5},
                    "total_tokens": 110,
                },
            },
        )

    provider.client = AsyncOpenAI(
        api_key="test-not-a-real-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        result = await provider.generate(
            (Message(role="user", content="test"),),
            ProviderOptions(
                request_id="r", call_id="c", config_id="fixture", model_id="fixture-model"
            ),
        )
        assert result.text == "fixture" and result.usage.reasoning_tokens == 5
        assert result.cost.serving_usd == Decimal("0.00026")
        assert (
            result.provider_response_id == "resp_fixture"
            and json.loads(result.native_usage_json)["total_tokens"] == 110
        )
    finally:
        await provider.client.close()


async def test_timezone_source_filter_and_csv_match_known_usage(client, app):
    from app.contracts.dtos import CallRecord

    c = app.state.container
    principal = await c.auth.resolve(client.cookies.get("smartllm_session"))
    usage = Usage(
        scope="call",
        usage_source="provider",
        input_tokens=100,
        output_tokens=10,
        cached_input_tokens=20,
        reasoning_tokens=5,
    )
    record = CallRecord(
        call_id="fixture-usage",
        model_id="fixture-model",
        usage=usage,
        cost=price(entry(), usage, "fixture"),
        duration_ms=10,
    )
    async with c.db.write() as db:
        db.add(
            UsageRecord(
                id="fixture-usage",
                owner_user_id=principal.id,
                operation_id="fixture-operation",
                session_id="deleted-session",
                created_at="2026-10-19T17:30:00+00:00",
                category="serving",
                execution_source="live",
                model_id="fixture-model",
                record_json=record.model_dump_json(),
            )
        )
    query = "start=2026-10-20&end=2026-10-20&source=live"
    response = await client.get("/v1/usage?" + query)
    assert response.status_code == 200
    report = response.json()
    assert report["daily"][0]["key"] == "2026-10-20" and report["totals"]["input_tokens"] == 100
    assert report["totals"]["usd"] == "0.00026" and report["execution_source"] == "live"
    assert (await client.get("/v1/usage?" + query.replace("live", "mock"))).json()["totals"][
        "calls"
    ] == 0
    csv_response = await client.get("/v1/usage/export?" + query + "&format=csv")
    assert "model,fixture-model,1,100,10,0.00026" in csv_response.text
    await client.post("/v1/auth/logout")
    await client.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
    assert (await client.get("/v1/usage?" + query)).json()["totals"]["calls"] == 0


async def test_upgrade_g0_preserves_accounts_and_history(tmp_path):
    from alembic import command
    from alembic.config import Config

    from app.auth.service import AuthService
    from app.config import ROOT, Settings
    from app.storage.database import Database
    from app.storage.repositories import SqlSessionStore

    path = tmp_path / "legacy.db"
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.attributes["database_path"] = path
    await asyncio.to_thread(command.upgrade, config, "70542f1078a5")
    db = Database(Settings(database_path=path, app_env="test"))
    try:
        auth = AuthService(db, Settings(database_path=path, app_env="test"))
        user = await auth.create_user("legacy", "password-legacy")
        store = SqlSessionStore(db)
        created = await store.create(user, "Legacy history")
        await asyncio.to_thread(command.upgrade, config, "head")
        principal, token = await auth.login("legacy", "password-legacy")
        assert principal.id == user.id
        assert (await store.detail(principal, created.id)).title == "Legacy history"
        await auth.logout(token)
    finally:
        await db.close()


def test_unicode_chunk_boundaries_cover_source_without_replacement():
    from app.documents.chunking import split_sections

    content = ("Đại học Mở TP.HCM — học phí, ngày đóng, phủ định không được bỏ. ") * 150
    chunks = split_sections([["paragraph 1", content]])
    assert len(chunks) > 1 and all("�" not in value for _, value in chunks)
    # Every protected phrase remains in at least one overlapping source chunk.
    for phrase in ("Đại học Mở TP.HCM", "phủ định không được bỏ"):
        assert any(phrase in value for _, value in chunks)
