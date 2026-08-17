"""Read SQLite-authoritative UTC time within a session (plan §6)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import DB_NOW_SQL


async def db_now(session: AsyncSession) -> str:
    """Return SQLite's current UTC timestamp (never Python wall-clock)."""
    return (await session.execute(text(f"SELECT {DB_NOW_SQL}"))).scalar()
