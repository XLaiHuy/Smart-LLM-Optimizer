from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.composition import Container
from app.storage.models import AuthSession


async def test_two_users_isolation_logout_expiry_and_purge(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    body = {
        "session_id": sid,
        "client_request_id": "one",
        "message": "private text",
        "mode": "baseline",
    }
    response = (await client.post("/v1/chat", json=body)).json()
    rid = response["request_id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as bob:
        await bob.post("/v1/auth/login", json={"username": "bob", "password": "password-bob"})
        assert (await bob.get("/v1/sessions")).json() == []
        assert (await bob.get("/v1/overview")).json()["total_requests"] == 0
        for method, path in (
            ("GET", f"/v1/sessions/{sid}"),
            ("DELETE", f"/v1/sessions/{sid}"),
            ("GET", f"/v1/traces/{rid}"),
        ):
            assert (await bob.request(method, path)).status_code == 404
        assert (await bob.post("/v1/chat", json=body)).status_code == 404
    assert (await client.delete(f"/v1/sessions/{sid}")).status_code == 204
    assert (await client.get(f"/v1/traces/{rid}")).status_code == 404
    # A purged request cannot be replayed to restore deleted content.
    assert (await client.post("/v1/chat", json=body)).status_code == 409
    token = client.cookies.get("smartllm_session")
    assert (await client.post("/v1/auth/logout")).status_code == 204
    assert (await client.get("/v1/auth/me")).status_code == 401
    client.cookies.set("smartllm_session", token)
    assert (await client.get("/v1/auth/me")).status_code == 401
    await client.post("/v1/auth/login", json={"username": "alice", "password": "password-alice"})
    c: Container = app.state.container
    async with c.db.write() as db:
        for session in await db.scalars(select(AuthSession)):
            session.expires_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert (await client.get("/v1/auth/me")).status_code == 401


async def test_origin_and_cookie_flags(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/auth/login", json={"username": "alice", "password": "password-alice"}
    )
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=lax" in response.headers["set-cookie"]
    )
    forbidden = await client.post(
        "/v1/sessions", json={}, headers={"Origin": "https://evil.invalid"}
    )
    assert forbidden.status_code == 403


async def test_chunked_body_limit_before_validation(client: httpx.AsyncClient) -> None:
    async def chunks():
        yield b'{"message":"'
        yield b"x" * 512001
        yield b'"}'

    response = await client.post(
        "/v1/chat", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
