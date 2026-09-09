"""Shared pytest fixtures: isolated temp SQLite DB per test, fast timing."""

from __future__ import annotations

from pathlib import Path

import contextlib

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


@pytest.fixture(autouse=True)
def _settings_singleton_pinned(tmp_path: Path):
    """Pin the process Settings singleton to the TEST's storage root for
    the duration of each test (r2-gate B2).

    The pinned Settings names ``tmp_path / "data"`` — the exact root the
    ``settings`` fixture would use — WITHOUT creating anything, so tests
    that build their own directory tree keep working. Whenever a test
    also requests ``settings``/``engine``/``client``, the singleton and
    ``request.app.state.settings`` name the SAME authority, which is
    exactly what production guarantees when configured explicitly.
    Tests proving the app authority wins over a divergent singleton
    poison ``soloring.settings._settings`` locally.
    """
    import soloring.settings as settings_mod

    previous = settings_mod._settings
    settings_mod._settings = Settings(data_dir=tmp_path / "data")
    yield
    settings_mod._settings = previous


@pytest.fixture
async def engine(settings: Settings):
    """A real SoloRing engine (with PRAGMAs) over a fresh temp DB + schema."""
    eng = create_soloring_engine(settings)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await close_registered_sessions(eng)
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
    await close_registered_sessions(engine)
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
async def factory(engine):
    """AsyncSession factory bound to the test engine (service-level tests).

    Post-M13 hygiene (frozen R2 HYG-01): every session created through
    this fixture is tracked and closed at teardown — bare ``factory()``
    call sites previously leaked sessions whose pooled connections were
    later terminated by the garbage collector (the reproduced
    non-checked-in-connection warning family).
    """
    yield make_tracked_maker(engine)
    await close_registered_sessions(engine)


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



# --- Post-M13 hygiene: session registries (frozen R2 HYG-01) -----------
# File-local shorthand factories (tests/test_m13_*.py::_factory) create
# bare sessions against the SAME engine as these fixtures. Every session
# maker in the suite — fixture or helper — is created through
# make_tracked_maker so all sessions are closed BEFORE engine disposal
# (dispose alone does not close open sessions; GC afterwards terminated
# their connections — the residual reproduced warning family).

_SESSIONS_BY_ENGINE: dict[int, list] = {}


async def close_registered_sessions(engine) -> None:
    """Rollback + close every still-open session bound to `engine`."""
    import contextlib

    for session in _SESSIONS_BY_ENGINE.get(id(engine), []):
        with contextlib.suppress(Exception):
            if session.in_transaction():
                await session.rollback()
        with contextlib.suppress(Exception):
            await session.close()
    _SESSIONS_BY_ENGINE.pop(id(engine), None)


def make_tracked_maker(engine):
    """A real async_sessionmaker subclass registering created sessions."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    registry = _SESSIONS_BY_ENGINE.setdefault(id(engine), [])

    class _TrackedSessionMaker(async_sessionmaker):

        def __call__(self, *args, **kwargs) -> AsyncSession:
            session = super().__call__(*args, **kwargs)
            registry.append(session)
            return session

    return _TrackedSessionMaker(bind=engine, expire_on_commit=False,
                                class_=AsyncSession)


# --- Post-M13 hygiene warning gates (frozen R2 HYG-01/HYG-07) -------------

_HYG_SA_LEAK_MESSAGE = (
    "The garbage collector is trying to clean up non-checked-in connection")
_hyg_sa_leak_hits: list[tuple[str, str]] = []


def pytest_warning_recorded(warning_message, when, nodeid, location):
    """Record every SQLAlchemy connection-cleanup warning (HYG-01).

    These warnings fire inside __del__, where filterwarnings-as-error
    cannot propagate — the fatal gate therefore lives in
    pytest_sessionfinish below.
    """
    text = str(getattr(warning_message, "message", ""))
    # The leak surfaces two ways: as the SAWarning itself, or — as an
    # unraisable-exception wrapper carrying the same text — when the
    # warning fires inside __del__ (where errors cannot propagate, so
    # filterwarnings-as-error is ineffective for both families).
    if _HYG_SA_LEAK_MESSAGE in text or "was never awaited" in text:
        _hyg_sa_leak_hits.append((nodeid or str(when), text[:96]))


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if _hyg_sa_leak_hits:
        writer = session.config.get_terminal_writer()
        writer.line("")
        writer.sep("=", "HYGIENE VIOLATION: leaked connections / "
                           "unawaited coroutines", red=True)
        writer.line(f"{len(_hyg_sa_leak_hits)} hygiene warning(s):")
        for nodeid, text in _hyg_sa_leak_hits[:12]:
            writer.line(f"  {nodeid}: {text}")
        if len(_hyg_sa_leak_hits) > 12:
            writer.line(f"  … and {len(_hyg_sa_leak_hits) - 12} more")
        session.exitstatus = 1
