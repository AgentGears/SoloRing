"""API smoke tests (plan §99). M0 surface: /health + CORS."""

from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.asyncio
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from soloring.api.main import create_app
from soloring.settings import Settings


@pytest.fixture
def app(tmp_data_dir):
    return create_app(
        Settings(
            data_dir=tmp_data_dir,
            blob_dir=tmp_data_dir / "blobs",
            staging_dir=tmp_data_dir / "staging",
            tmp_dir=tmp_data_dir / "tmp",
            cors_origins=["http://test.local"],
        )
    )


@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_health(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ASGITransport does not run lifespan; /health needs no DB.
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["sqlite_version"] == sqlite3.sqlite_version


@pytest.mark.skipif(httpx is None, reason="httpx not installed")
async def test_cors_header_on_allowed_origin(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health", headers={"Origin": "http://test.local"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://test.local"
