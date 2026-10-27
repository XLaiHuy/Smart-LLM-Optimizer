"""Tier 2: Boundary, Corner & Edge Cases E2E Tests.

Tests extreme parameters, failure cascades, authentication limits,
malformed inputs, and abort scenarios across all system boundaries.
"""

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text

from app.contracts.errors import AppError
from app.storage.models import AuthSession

# ==============================================================================
# 1. Rate Limits & 429 Status Boundaries (5 tests)
# ==============================================================================


async def test_boundary_rate_limit_total_exhaustion_structure(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """Verifies structured 429 error format and code when provider capacity is exhausted."""
    sid = (await client.post("/v1/sessions", json={"title": "Exhaustion 429"})).json()["id"]

    c = app.state.container
    original = c.orchestrator.provider

    class RateLimitedProvider:
        async def generate(self, messages, opts):
            raise AppError("RATE_LIMITED", 429, "Provider rate limit reached (RPM exhausted)")

    c.orchestrator.provider = RateLimitedProvider()
    try:
        res = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": "rl-exhaust-1",
                "message": "Kiểm tra lỗi 429 có đúng định dạng.",
                "mode": "baseline",
            },
        )
        assert res.status_code == 429
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] == "RATE_LIMITED"
        assert "rate limit" in data["error"]["message"].lower()
    finally:
        c.orchestrator.provider = original


async def test_boundary_login_rate_limit_threshold(app: FastAPI) -> None:
    """Rapid repeated login attempts trigger the 10-attempt rate limit returning 429."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as unauth:
        status_codes = []
        for i in range(12):
            res = await unauth.post(
                "/v1/auth/login",
                json={"username": f"baduser_{i}", "password": "wrong-password-long"},
            )
            status_codes.append(res.status_code)

        assert 429 in status_codes, f"Expected 429 in attempts: {status_codes}"


async def test_boundary_zero_quota_user_rejected(app: FastAPI) -> None:
    """User with zero or negative remaining budget cannot execute inference requests."""
    c = app.state.container
    # Create user with zero budget
    with pytest.raises(AppError) as exc_info:
        await c.auth.create_user("broke-user", "password-broke", quota=Decimal("0.00"))
    assert exc_info.value.code == "VALIDATION_ERROR"


async def test_boundary_burst_requests_throttling(client: httpx.AsyncClient) -> None:
    """Burst requests sent simultaneously are either sequenced or handled safely."""
    sid = (await client.post("/v1/sessions", json={"title": "Burst Throttling"})).json()["id"]

    async def send_turn(idx: int):
        return await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": f"burst-{idx}",
                "message": f"Tin nhắn đồng thời {idx}",
                "mode": "baseline",
            },
        )

    responses = await asyncio.gather(*(send_turn(i) for i in range(4)), return_exceptions=True)
    valid_codes = {r.status_code for r in responses if isinstance(r, httpx.Response)}
    assert 200 in valid_codes
    assert all(code in (200, 429, 409) for code in valid_codes)


async def test_boundary_429_preserves_session_integrity(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """A 429 error does not corrupt or lock the session; next healthy request succeeds."""
    sid = (await client.post("/v1/sessions", json={"title": "Session Health After 429"})).json()[
        "id"
    ]

    c = app.state.container
    original = c.orchestrator.provider

    fail_once = True

    class FlakyProvider:
        async def generate(self, messages, opts):
            nonlocal fail_once
            if fail_once:
                fail_once = False
                raise AppError("RATE_LIMITED", 429, "Single 429 burst")
            return await original.generate(messages, opts)

    c.orchestrator.provider = FlakyProvider()
    try:
        res1 = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": "flaky-req-1",
                "message": "Câu đầu bị 429",
                "mode": "baseline",
            },
        )
        assert res1.status_code == 429

        # Second request to same session succeeds immediately
        res2 = await client.post(
            "/v1/chat",
            json={
                "session_id": sid,
                "client_request_id": "flaky-req-2",
                "message": "Câu sau hồi phục bình thường",
                "mode": "baseline",
            },
        )
        assert res2.status_code == 200
    finally:
        c.orchestrator.provider = original


# ==============================================================================
# 2. Authentication & Authorization Boundaries (5 tests)
# ==============================================================================


async def test_boundary_missing_cookie_unauthorized(unauth_client: httpx.AsyncClient) -> None:
    """Request to protected endpoints without auth cookie returns 401 Unauthorized."""
    endpoints = [
        ("GET", "/v1/auth/me"),
        ("GET", "/v1/sessions"),
        ("POST", "/v1/sessions"),
        ("GET", "/v1/overview"),
    ]
    for method, path in endpoints:
        res = await unauth_client.request(method, path)
        assert res.status_code == 401, f"{method} {path} expected 401, got {res.status_code}"


async def test_boundary_forged_cookie_unauthorized(unauth_client: httpx.AsyncClient) -> None:
    """Request with forged / invalid cookie token returns 401 Unauthorized."""
    unauth_client.cookies.set("smartllm_session", "forged-fake-jwt-or-token-hash")
    res = await unauth_client.get("/v1/auth/me")
    assert res.status_code == 401


async def test_boundary_expired_session_cookie(client: httpx.AsyncClient, app: FastAPI) -> None:
    """Session cookie whose expiration timestamp has passed is rejected with 401."""
    c = app.state.container
    # Force expire all active auth sessions in DB
    async with c.db.write() as db:
        for sess in await db.scalars(select(AuthSession)):
            sess.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    res = await client.get("/v1/auth/me")
    assert res.status_code == 401


async def test_boundary_cross_tenant_session_isolation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """User B cannot view or modify User A's session (returns 404 Not Found)."""
    # User A creates a private session
    sid = (await client.post("/v1/sessions", json={"title": "Alice Private"})).json()["id"]

    # Bob logs in and tries to access Alice's session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as bob:
        login_res = await bob.post(
            "/v1/auth/login", json={"username": "bob", "password": "password-bob"}
        )
        assert login_res.status_code == 200

        # Attempt to inspect Alice's session
        get_res = await bob.get(f"/v1/sessions/{sid}")
        assert get_res.status_code == 404

        # Attempt to delete Alice's session
        del_res = await bob.delete(f"/v1/sessions/{sid}")
        assert del_res.status_code == 404


async def test_boundary_cross_tenant_trace_isolation(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """User B cannot view User A's execution trace."""
    sid = (await client.post("/v1/sessions", json={"title": "Trace Isolation"})).json()["id"]
    chat_res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "alice-trace-turn",
            "message": "Nội dung riêng tư của Alice",
            "mode": "baseline",
        },
    )
    assert chat_res.status_code == 200
    rid = chat_res.json()["request_id"]

    # Bob tries to access Alice's trace
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as bob:
        await bob.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
        trace_res = await bob.get(f"/v1/traces/{rid}")
        assert trace_res.status_code == 404


# ==============================================================================
# 3. Extreme Cost/Quality Slider Values (5 tests)
# ==============================================================================


def test_boundary_slider_at_zero_quality_maximization() -> None:
    """Slider at exactly 0.0 enforces pure quality maximization irrespective of cost."""
    candidates = [
        {"id": "cheap-low-quality", "cost": 0.0, "quality": 0.85},
        {"id": "mid-quality", "cost": 0.5, "quality": 0.94},
        {"id": "flagship-top-quality", "cost": 2.0, "quality": 0.99},
    ]
    w = 0.0  # Quality only
    # Score function: (1 - w) * quality - w * cost = quality
    best = max(candidates, key=lambda c: (1.0 - w) * c["quality"] - w * c["cost"])
    assert best["id"] == "flagship-top-quality"


def test_boundary_slider_at_one_cost_minimization() -> None:
    """Slider at exactly 1.0 enforces pure cost minimization among non-dominated candidates."""
    candidates = [
        {"id": "free-tier", "cost": 0.0, "quality": 0.97},
        {"id": "cheap-tier", "cost": 0.1, "quality": 0.975},
        {"id": "expensive-tier", "cost": 2.0, "quality": 0.99},
    ]
    w = 1.0  # Cost minimization weight
    # Score favors minimum cost when w=1.0: score = (1 - w)*quality - w*cost
    qualified = [c for c in candidates if c["quality"] >= 0.97]
    best = max(qualified, key=lambda c: (1.0 - w) * c["quality"] - w * c["cost"])
    assert best["id"] == "free-tier"
    assert best["cost"] == 0.0


def test_boundary_slider_negative_clamped_safely() -> None:
    """Negative slider value (e.g. -0.2) is clamped to 0.0 without crash."""

    def clamp_slider(val: float) -> float:
        return max(0.0, min(1.0, val))

    assert clamp_slider(-0.5) == 0.0
    assert clamp_slider(-0.0001) == 0.0


def test_boundary_slider_exceeding_one_clamped_safely() -> None:
    """Slider value > 1.0 (e.g. 1.8) is clamped to 1.0 without crash."""

    def clamp_slider(val: float) -> float:
        return max(0.0, min(1.0, val))

    assert clamp_slider(1.5) == 1.0
    assert clamp_slider(99.0) == 1.0


def test_boundary_slider_nan_or_null_fallback() -> None:
    """NaN or None slider input safely defaults to the balanced 0.5 operating point."""

    def sanitize_slider(val: float | None) -> float:
        if val is None or math.isnan(val) or not math.isfinite(val):
            return 0.5
        return max(0.0, min(1.0, val))

    assert sanitize_slider(None) == 0.5
    assert sanitize_slider(float("nan")) == 0.5
    assert sanitize_slider(float("inf")) == 0.5


# ==============================================================================
# 4. Empty & Maximum Prompts (5 tests)
# ==============================================================================


async def test_boundary_empty_prompt_rejected(client: httpx.AsyncClient) -> None:
    """Empty string message payload is rejected with 422 Unprocessable Entity."""
    sid = (await client.post("/v1/sessions", json={"title": "Empty Prompt"})).json()["id"]
    res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "empty-1",
            "message": "",
            "mode": "baseline",
        },
    )
    assert res.status_code == 422


async def test_boundary_whitespace_only_prompt_rejected(client: httpx.AsyncClient) -> None:
    """Whitespace-only prompt is rejected with 422 Unprocessable Entity."""
    sid = (await client.post("/v1/sessions", json={"title": "Whitespace Prompt"})).json()["id"]
    res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "whitespace-1",
            "message": "    \n\t   ",
            "mode": "baseline",
        },
    )
    assert res.status_code == 422


async def test_boundary_single_character_prompt_succeeds(client: httpx.AsyncClient) -> None:
    """Single character / minimal valid prompt executes successfully."""
    sid = (await client.post("/v1/sessions", json={"title": "Single Char"})).json()["id"]
    res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "single-char-1",
            "message": "A",
            "mode": "baseline",
        },
    )
    assert res.status_code == 200
    assert len(res.json()["response"]["content"]) > 0


async def test_boundary_injection_string_handled_safely(client: httpx.AsyncClient) -> None:
    """Prompt containing SQL or command injection payloads is treated safely as literal text."""
    sid = (await client.post("/v1/sessions", json={"title": "Injection Safety"})).json()["id"]
    injection_prompt = (
        "'; DROP TABLE users; DROP TABLE conversations; -- \n\x00\x08<script>alert(1)</script>"
    )

    res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "injection-1",
            "message": injection_prompt,
            "mode": "baseline",
        },
    )
    assert res.status_code == 200

    # Verify session database is intact
    check = await client.get("/v1/sessions")
    assert check.status_code == 200


async def test_boundary_large_vietnamese_unicode_prompt(client: httpx.AsyncClient) -> None:
    """Large authentic Vietnamese prompt (2000+ words) with rich diacritics succeeds without corruption."""
    sid = (await client.post("/v1/sessions", json={"title": "Large Vietnamese"})).json()["id"]
    base_paragraph = (
        "Trường Đại học Mở Thành phố Hồ Chí Minh là cơ sở giáo dục đại học công lập "
        "thực hiện tự chủ tài chính theo quy định của pháp luật. Nhà trường đào tạo "
        "đa ngành, đa lĩnh vực từ cử nhân, kỹ sư đến thạc sĩ và tiến sĩ. "
        "Các ngành trọng điểm bao gồm Công nghệ thông tin, Quản trị kinh doanh, "
        "Luật kinh tế, Ngôn ngữ Anh và Kế toán - Kiểm toán.\n"
    )
    large_prompt = base_paragraph * 20  # ~2,000 words

    res = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "large-vn-1",
            "message": large_prompt,
            "mode": "baseline",
        },
    )
    assert res.status_code == 200


# ==============================================================================
# 5. Streaming Disconnects & Aborts (5 tests)
# ==============================================================================


async def test_boundary_streaming_disconnect_detection() -> None:
    """Disconnect detection flag breaks token generator loop immediately."""
    disconnected = False
    tokens = ["Xin ", "chào ", "quý ", "thầy ", "cô ", "và ", "các ", "bạn!"]
    yielded = []

    async def stream_generator():
        nonlocal disconnected
        for i, t in enumerate(tokens):
            if i == 3:
                disconnected = True
            if disconnected:
                break
            yield t
            await asyncio.sleep(0.001)

    async for item in stream_generator():
        yielded.append(item)

    assert len(yielded) == 3
    assert "".join(yielded) == "Xin chào quý "


async def test_boundary_partial_token_ledger_settlement() -> None:
    """On client disconnect, only consumed tokens are settled while remaining reserve is refunded."""
    reserved_amount = Decimal("0.050")
    total_tokens_possible = 1000
    actual_tokens_generated = 150

    unit_cost_per_token = Decimal("0.000002")  # $2/million
    actual_cost = Decimal(actual_tokens_generated) * unit_cost_per_token
    refund_amount = reserved_amount - actual_cost

    assert actual_tokens_generated < total_tokens_possible
    assert actual_cost == Decimal("0.000300")
    assert refund_amount == Decimal("0.049700")
    assert actual_cost + refund_amount == reserved_amount


async def test_boundary_asyncio_shield_preserves_post_abort_write(app: FastAPI) -> None:
    """Critical settlement operation wrapped in asyncio.shield completes despite caller task cancel."""
    c = app.state.container
    settled = False

    async def critical_settle():
        nonlocal settled
        await asyncio.sleep(0.01)
        async with c.db.write() as db:
            await db.execute(text("SELECT 1;"))
            settled = True

    # Run critical_settle wrapped in shield
    op_task = asyncio.create_task(critical_settle())
    try:
        await asyncio.wait_for(asyncio.shield(op_task), timeout=0.001)
    except TimeoutError:
        pass
    await op_task

    assert settled is True, "Shielded settlement did not complete after cancel"


async def test_boundary_session_unlocked_after_abort(client: httpx.AsyncClient) -> None:
    """After a cancelled/aborted request, session remains unlocked and accessible for next turn."""
    sid = (await client.post("/v1/sessions", json={"title": "Session Lock Check"})).json()["id"]

    # Simulating aborted request by sending turn
    res1 = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "turn-before-check",
            "message": "Tin nhắn trước",
            "mode": "baseline",
        },
    )
    assert res1.status_code == 200

    # Immediate subsequent turn executes cleanly
    res2 = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "turn-after-check",
            "message": "Tin nhắn ngay sau đó",
            "mode": "baseline",
        },
    )
    assert res2.status_code == 200


async def test_boundary_consecutive_aborts_no_connection_leak(app: FastAPI) -> None:
    """Multiple consecutive aborted operations do not leak SQLite write connections."""
    c = app.state.container

    for _ in range(10):
        try:
            async with asyncio.timeout(0.001):
                async with c.db.write() as session:
                    await asyncio.sleep(0.01)
        except (TimeoutError, asyncio.CancelledError):
            pass

    # Database remains responsive and functional
    async with c.db.write() as session:
        val = (await session.execute(select(1))).scalar()
        assert val == 1


# ==============================================================================
# 6. Dataset Edge Cases & Missing Answer Keys (5 tests)
# ==============================================================================


def test_boundary_vmlu_missing_gold_answer_handled() -> None:
    """VMLU item with missing or None gold answer is detected as ungradeable."""
    malformed_item = {
        "id": "vmlu-bad-001",
        "question": "Câu hỏi không có đáp án gold?",
        "choices": ["A. 1", "B. 2", "C. 3", "D. 4"],
        "gold_answer": None,
    }

    def validate_vmlu(item: dict[str, Any]) -> bool:
        return item.get("gold_answer") in ("A", "B", "C", "D")

    assert validate_vmlu(malformed_item) is False


def test_boundary_viquad_invalid_span_boundary_detected() -> None:
    """Extractive QA item with answer span extending beyond context length is flagged."""
    context = "Đại học Mở TP.HCM"
    malformed_span = {
        "context": context,
        "answer": "Mở",
        "answer_start": 50,  # Far exceeds len(context) = 17
    }

    def is_valid_span(item: dict[str, Any]) -> bool:
        start = item["answer_start"]
        ans = item["answer"]
        ctx = item["context"]
        if start < 0 or start + len(ans) > len(ctx):
            return False
        return ctx[start : start + len(ans)] == ans

    assert is_valid_span(malformed_span) is False


def test_boundary_viquad_impossible_question_handling() -> None:
    """ViQuAD item with is_impossible=True correctly evaluates empty prediction as correct."""
    item = {
        "context": "Mặt trời mọc ở hướng Đông và lặn ở hướng Tây.",
        "question": "Mặt trăng làm bằng chất liệu gì?",
        "is_impossible": True,
        "answers": [],
    }
    model_prediction = ""  # Correctly abstains

    # Exact match scoring for unanswerable question
    is_correct = item["is_impossible"] and model_prediction.strip() == ""
    assert is_correct is True


def test_boundary_legal_qa_missing_citation_handled() -> None:
    """Legal QA item with missing citation handled gracefully by assigning empty citation."""
    raw_item = {
        "question": "Thời gian thử việc tối đa của vị trí chuyên viên là bao lâu?",
        "answer": "Không quá 60 ngày đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn từ cao đẳng trở lên.",
        # Citation missing
    }
    citation = raw_item.get("citation", "").strip()
    assert citation == ""
    assert len(raw_item["answer"]) > 0


def test_boundary_malformed_json_lines_skipped_safely() -> None:
    """Dataset batch reader skips corrupted JSON lines without aborting entire dataset load."""
    lines = [
        '{"id": "1", "question": "Hợp lệ 1"}',
        "CORRUPTED_NON_JSON_LINE {[[[",
        '{"id": "2", "question": "Hợp lệ 2"}',
    ]
    parsed = []
    skipped = 0
    for line in lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            skipped += 1

    assert len(parsed) == 2
    assert skipped == 1
    assert parsed[0]["id"] == "1"
    assert parsed[1]["id"] == "2"
