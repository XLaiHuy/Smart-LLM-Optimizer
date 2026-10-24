import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.cli import migrate
from app.composition import Container
from app.config import Settings
from app.main import create_app


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    settings = Settings(
        database_path=tmp_path / "test.db",
        app_env="test",
        provider_mode="mock",
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
