"""SQLite connection initialization (plan §15).

One shared hook applies the required connection-local PRAGMAs on every new
SQLite connection. It is used by BOTH the application async engine
(``create_soloring_engine``) and Alembic's synchronous migration engine
(``server/alembic/env.py``), so a freshly-migrated SoloRing database already
satisfies the runtime contract — including the persistent ``journal_mode=WAL``.

PRAGMAs:
    journal_mode=WAL     DB-persistent; WAL survives across connections
    foreign_keys=ON      connection-local; required for FK enforcement
    busy_timeout=5000    connection-local; retry on lock contention
    synchronous=NORMAL   connection-local; WAL-safe reduced fsync
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Single source of truth for the required PRAGMAs (plan §15).
SQLITE_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("foreign_keys", "ON"),
    ("busy_timeout", "5000"),
    ("synchronous", "NORMAL"),
)


def sqlite_supports_returning() -> bool:
    """SQLite >= 3.35 supports RETURNING (plan §61)."""
    parts = sqlite3.sqlite_version.split(".")
    return tuple(int(x) for x in parts[:2]) >= (3, 35)


def attach_sqlite_pragmas(engine: Engine) -> None:
    """Attach the required PRAGMA initialization to every new connection."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            for pragma, value in SQLITE_PRAGMAS:
                cursor.execute(f"PRAGMA {pragma}={value}")
        finally:
            cursor.close()
