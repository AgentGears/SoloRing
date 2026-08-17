"""Shot numbering service tests (plan §10): RETURNING + fenced fallback.

The fenced path is exercised by forcing the capability flag off, proving the
single-connection BEGIN IMMEDIATE fallback (verify -> MAX -> INSERT) also
allocates non-reused numbers and rejects a deleted parent atomically. The
collision-retry policy is fault-tested deterministically (plan §10.1, §50.4).
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects
from soloring.domain import shots as shots_mod
from soloring.errors import ErrorCode, SoloRingError


async def _make_project(factory) -> str:
    async with factory() as s:
        p = await projects.create_project(s, ProjectCreate(name="P"))
        return p.id


async def _create_shot(factory, pid: str, subject: str) -> int:
    async with factory() as s:
        shot = await shots_mod.create_shot(s, pid, ShotCreate(subject=subject))
        return shot.shot_number


def _unique_violation() -> IntegrityError:
    return IntegrityError(
        "INSERT INTO shots",
        {},
        sqlite3.IntegrityError(
            "UNIQUE constraint failed: shots.project_id, shots.shot_number"
        ),
    )


async def test_returning_path_numbering(factory) -> None:
    pid = await _make_project(factory)
    assert await _create_shot(factory, pid, "a") == 1
    assert await _create_shot(factory, pid, "b") == 2


async def test_fenced_fallback_numbering(factory, monkeypatch) -> None:
    monkeypatch.setattr("soloring.domain.shots.sqlite_supports_returning", lambda: False)
    pid = await _make_project(factory)
    assert await _create_shot(factory, pid, "a") == 1
    assert await _create_shot(factory, pid, "b") == 2


async def test_fenced_fallback_rejects_deleted_project(factory, monkeypatch) -> None:
    monkeypatch.setattr("soloring.domain.shots.sqlite_supports_returning", lambda: False)
    pid = await _make_project(factory)
    async with factory() as s:
        await projects.delete_project(s, pid)
    with pytest.raises(SoloRingError) as ei:
        await _create_shot(factory, pid, "a")
    assert ei.value.code == ErrorCode.PROJECT_NOT_FOUND


# --- collision-retry policy (fault injection) -------------------------------


async def test_collision_retry_then_success(factory, monkeypatch) -> None:
    """First attempt collides (numbering uniqueness), retry succeeds."""
    real = shots_mod._execute_shot_insert
    state = {"n": 0}

    async def fake(session, params):
        state["n"] += 1
        if state["n"] == 1:
            raise _unique_violation()
        return await real(session, params)

    monkeypatch.setattr(shots_mod, "_execute_shot_insert", fake)
    pid = await _make_project(factory)
    assert await _create_shot(factory, pid, "a") == 1
    assert state["n"] == 2  # one collision + one success


async def test_collision_exhaustion_raises_internal_error(factory, monkeypatch) -> None:
    """Both attempts collide -> INTERNAL_INVARIANT_VIOLATION, never raw."""
    async def always(session, params):
        raise _unique_violation()

    monkeypatch.setattr(shots_mod, "_execute_shot_insert", always)
    pid = await _make_project(factory)
    with pytest.raises(SoloRingError) as ei:
        await _create_shot(factory, pid, "a")
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert ei.value.status_code == 500


async def test_unrelated_integrity_not_treated_as_collision(factory, monkeypatch) -> None:
    """A non-numbering integrity failure is not retried; it is an invariant."""
    state = {"n": 0}

    async def fake(session, params):
        state["n"] += 1
        raise IntegrityError(
            "INSERT INTO shots",
            {},
            sqlite3.IntegrityError("CHECK constraint failed: ck_shots_subject_nonempty"),
        )

    monkeypatch.setattr(shots_mod, "_execute_shot_insert", fake)
    pid = await _make_project(factory)
    with pytest.raises(SoloRingError) as ei:
        await _create_shot(factory, pid, "a")
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert state["n"] == 1  # not retried as a numbering collision
