"""Shared pytest fixtures: isolated temp SQLite DB per test, fast timing."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from soloring.db.engine import create_soloring_engine
from soloring.db.base import Base
from soloring.db import models  # noqa: F401  (register tables on Base.metadata)
from soloring.db.timeutil import db_now_minus_sql
from soloring.settings import BASE_DIR, Settings


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    for sub in ("blobs", "staging", "tmp"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def settings(tmp_data_dir: Path) -> Settings:
    # Only data_dir is set; blob/staging/tmp must derive from it (plan §4, #6).
    return Settings(data_dir=tmp_data_dir)


@pytest.fixture
async def engine(settings: Settings):
    """A real SoloRing engine (with PRAGMAs) over a fresh temp DB + schema."""
    eng = create_soloring_engine(settings)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def age_heartbeat():  # noqa: F811 - defined below
    """Force the lease heartbeat into the past (simulates a stalled worker)."""

    async def _age(engine, seconds: int = 9999) -> None:
        frag = db_now_minus_sql(seconds)
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(
                text(
                    "UPDATE worker_leases SET heartbeat_at = "
                    + frag
                    + " WHERE name = 'generation-worker'"
                )
            )
            await conn.exec_driver_sql("COMMIT")

    return _age


# Re-export for convenience in tests that need the repo root.
REPO_ROOT = BASE_DIR


@pytest.fixture
async def client(settings: Settings):
    """An httpx client against a real SoloRing app over a fresh temp DB."""
    import httpx

    from soloring.api.main import create_app
    from soloring.db.engine import create_session_factory

    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


async def create_project(client, **fields) -> dict:
    """Helper: create a project, returning the JSON body."""
    r = await client.post("/projects", json=fields)
    assert r.status_code == 201, r.text
    return r.json()


async def create_shot(client, project_id: str, **fields) -> dict:
    r = await client.post(f"/projects/{project_id}/shots", json=fields)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def factory(engine):
    """AsyncSession factory bound to the test engine (service-level tests)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def seed_reference_asset(engine, project_id: str) -> tuple[str, str]:
    """Create a Blob + reference Asset directly (upload is M1D; plan §48 M1C).

    Returns (asset_id, blob_hash).
    """
    import hashlib

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    bh = hashlib.sha256(aid.encode()).hexdigest()
    f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", size_bytes=10))
        await s.flush()  # ensure blob row exists before the FK on the asset
        s.add(Asset(id=aid, project_id=project_id, blob_hash=bh, kind="reference"))
        await s.commit()
    return aid, bh

