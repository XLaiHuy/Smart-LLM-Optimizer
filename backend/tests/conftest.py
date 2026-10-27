import asyncio
import socket
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.cli import migrate
from app.composition import Container
from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Tests may use loopback/ASGI, never a paid provider or remote download."""
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def guarded(sock, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError("External network is disabled in tests")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)

    def guarded_connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError("External network is disabled in tests")
        return connect_ex(sock, address)

    def guarded_dns(host, *args, **kwargs):
        if host not in (None, "127.0.0.1", "::1", "localhost", b"localhost", b"127.0.0.1", b"::1"):
            raise AssertionError("External network is disabled in tests")
        return getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_dns)


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = Settings(
        database_path=tmp_path / "test.db",
        app_env="test",
        provider_mode="mock",
        mock_config_id="mock-baseline",
        model_catalog_path=tmp_path / "models.json",
        ml_router_artifact_path=tmp_path / "no-live-artifact.json",
        ml_router_allow_research_candidate=False,
        ml_router_live_approved=False,
        adaptive_prompt_enabled=False,
        hybrid_context_enabled=False,
        memory_retrieval_enabled=False,
        allowed_origins=("http://testserver",),
        router_training_directory=tmp_path / "router-training",
        router_training_manifest_path=tmp_path / "router-training" / "manifest.json",
        upload_directory=tmp_path / "uploads",
    )
    await asyncio.to_thread(migrate, settings.database_path)
    instance = create_app(settings)
    c: Container = instance.state.container
    await c.auth.create_user("alice", "password-alice")
    await c.auth.create_user("bob", "password-bob")
    async with instance.router.lifespan_context(instance):
        yield instance


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as connection:
        assert (
            await connection.post(
                "/v1/auth/login", json={"username": "alice", "password": "password-alice"}
            )
        ).status_code == 200
        yield connection
