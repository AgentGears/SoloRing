"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Short AsyncSession per request (plan §104)."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_engine(request: Request) -> AsyncEngine:
    """The app engine (for explicit read units / non-session work)."""
    return request.app.state.engine
