"""SQLite configuration tests (plan §15)."""

from __future__ import annotations

import logging
import sqlite3

import pytest
from sqlalchemy import text

from soloring.db.engine import create_soloring_engine


async def test_pragmas_applied_per_connection(engine) -> None:
    async with engine.connect() as conn:
        fk = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
        bt = (await conn.execute(text("PRAGMA busy_timeout"))).scalar()
        sm = (await conn.execute(text("PRAGMA synchronous"))).scalar()
        jm = (await conn.execute(text("PRAGMA journal_mode"))).scalar()
    assert fk == 1, "PRAGMA foreign_keys=ON must be set per connection"
    assert bt == 5000, "PRAGMA busy_timeout=5000"
    assert int(sm) == 1, f"PRAGMA synchronous=NORMAL(1), got {sm!r}"
    assert str(jm).lower() == "wal", f"PRAGMA journal_mode=WAL, got {jm!r}"


def test_sqlite_version_is_logged(caplog, settings) -> None:
    caplog.set_level(logging.INFO, logger="soloring.db")
    import asyncio

    eng = create_soloring_engine(settings)

    async def _dispose():
        await eng.dispose()

    asyncio.run(_dispose())
    assert "SQLite runtime version" in caplog.text
    assert sqlite3.sqlite_version in caplog.text


def test_sqlite_version_supports_returning() -> None:
    """RETURNING is available on SQLite >= 3.35 (plan §61)."""
    major, minor, *_ = (int(x) for x in sqlite3.sqlite_version.split("."))
    assert (major, minor) >= (3, 35), sqlite3.sqlite_version


async def test_session_factory_expire_on_commit_disabled(settings) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from soloring.db.engine import create_session_factory

    eng = create_soloring_engine(settings)
    try:
        factory = create_session_factory(eng)
        async with factory() as session:
            assert isinstance(session, AsyncSession)
        # expire_on_commit=False is the configured default (plan §3)
        assert factory.kw["expire_on_commit"] is False
    finally:
        await eng.dispose()
