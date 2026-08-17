"""Engine and session factory (plan §3, §15, §104).

Normal request handlers use a short ``AsyncSession`` per request with
``expire_on_commit=False``. Ownership-critical paths do NOT use sessions; they
use a raw ``engine.connect()`` with an explicit ``BEGIN IMMEDIATE`` (see
``soloring.worker.ownership``).
"""

from __future__ import annotations

import logging
import os
import sqlite3

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from soloring.db.sqlite import attach_sqlite_pragmas
from soloring.settings import Settings

log = logging.getLogger("soloring.db")


def _validate_same_filesystem(settings: Settings) -> None:
    """Atomic Blob placement depends on os.replace() (plan §21).

    tmp_dir and blob_dir must reside on the same filesystem/volume. Verified
    at startup — after storage dirs exist, before anything relies on rename —
    so a cross-device misconfiguration fails loudly instead of at upload time.
    """
    tmp_dev = os.stat(settings.tmp_dir).st_dev
    blob_dev = os.stat(settings.blob_dir).st_dev
    if tmp_dev != blob_dev:
        raise RuntimeError(
            "SoloRing storage configuration error: tmp_dir "
            f"({settings.tmp_dir}) and blob_dir ({settings.blob_dir}) are on "
            "different filesystems; atomic os.replace() cannot be guaranteed "
            "(plan §21). Configure SOLORING_TMP_DIR/SOLORING_BLOB_DIR on the "
            "same volume."
        )


def create_soloring_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine and apply SQLite PRAGMAs on every connection."""
    settings.ensure_storage_dirs()
    _validate_same_filesystem(settings)

    engine = create_async_engine(settings.resolved_database_url(), future=True)

    # PRAGMAs are connection-local (plan §15); apply on every new connection via
    # the shared hook (also used by Alembic) so app and migration engines agree.
    attach_sqlite_pragmas(engine.sync_engine)

    # Plan §15: log the sqlite version at startup.
    log.info("SQLite runtime version: %s", sqlite3.sqlite_version)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Short-lived session factory for API/SSE paths (plan §3, §104)."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
