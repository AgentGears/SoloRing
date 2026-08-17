"""RevisionService tests (plan §14, §50.7): capture/reuse, two-conflict handling."""

from __future__ import annotations

import asyncio

import pytest

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.domain import projects, references, revisions, shots
from soloring.errors import ErrorCode, SoloRingError
from tests.conftest import seed_reference_asset


async def _proj(factory) -> str:
    async with factory() as s:
        return (await projects.create_project(s, ProjectCreate(name="P"))).id


async def _shot(factory, pid: str, subject: str = "x") -> str:
    async with factory() as s:
        return (await shots.create_shot(s, pid, ShotCreate(subject=subject))).id


async def _asset(engine, pid: str) -> str:
    return (await seed_reference_asset(engine, pid))[0]


async def _set_refs(factory, shot_id: str, pairs: list[tuple[str, str]]) -> None:
    items = [ReferenceInput(asset_id=a, role=r) for a, r in pairs]
    async with factory() as s:
        await references.replace_references(s, shot_id, items)


async def _patch_subject(factory, shot_id: str, subject: str) -> None:
    async with factory() as s:
        await shots.patch_shot(s, shot_id, ShotPatch(subject=subject))


async def _capture(factory, shot_id: str):
    async with factory() as s:
        return await revisions.capture_revision(s, shot_id)


async def test_same_state_captured_twice_reuses(factory) -> None:
    sid = await _shot(factory, await _proj(factory), "a")
    r1 = await _capture(factory, sid)
    r2 = await _capture(factory, sid)
    assert r1.id == r2.id


async def test_subject_change_creates_new_revision(factory) -> None:
    sid = await _shot(factory, await _proj(factory), "a")
    r1 = await _capture(factory, sid)
    await _patch_subject(factory, sid, "b")
    r2 = await _capture(factory, sid)
    assert r1.id != r2.id
    assert r1.snapshot_hash != r2.snapshot_hash
    assert r2.revision_number == r1.revision_number + 1


async def test_reference_replacement_creates_new_revision(factory, engine) -> None:
    pid = await _proj(factory)
    sid = await _shot(factory, pid, "a")
    r1 = await _capture(factory, sid)
    a1 = await _asset(engine, pid)
    await _set_refs(factory, sid, [(a1, "reference")])
    r2 = await _capture(factory, sid)
    assert r1.id != r2.id


async def test_role_change_and_reorder_and_removal_create_new_revisions(factory, engine) -> None:
    pid = await _proj(factory)
    sid = await _shot(factory, pid, "a")
    a1, a2 = await _asset(engine, pid), await _asset(engine, pid)

    await _set_refs(factory, sid, [(a1, "reference"), (a2, "character")])
    base = await _capture(factory, sid)

    # role change on a1
    await _set_refs(factory, sid, [(a1, "style"), (a2, "character")])
    assert (await _capture(factory, sid)).snapshot_hash != base.snapshot_hash

    # reorder within a role (two refs under same role, swapped) — add a3
    a3 = await _asset(engine, pid)
    await _set_refs(factory, sid, [(a1, "reference"), (a2, "reference")])
    after_order1 = (await _capture(factory, sid)).snapshot_hash
    await _set_refs(factory, sid, [(a2, "reference"), (a1, "reference")])
    after_order2 = (await _capture(factory, sid)).snapshot_hash
    # Position reflects request order, which is part of snapshot identity, so
    # reordering produces a new revision (plan §50.7: reorder -> new revision).
    assert after_order1 != after_order2

    # removal
    await _set_refs(factory, sid, [(a1, "reference")])
    removed = await _capture(factory, sid)
    assert removed.snapshot_hash != after_order2
    _ = a3  # keep fixture usage explicit


async def test_snapshot_includes_asset_and_blob_identity(factory, engine) -> None:
    pid = await _proj(factory)
    sid = await _shot(factory, pid, "a")
    aid, bh = await seed_reference_asset(engine, pid)
    await _set_refs(factory, sid, [(aid, "reference")])
    rev = await _capture(factory, sid)
    assert aid in rev.snapshot_json
    assert bh in rev.snapshot_json


async def test_concurrent_identical_snapshots_converge(factory) -> None:
    sid = await _shot(factory, await _proj(factory), "a")
    r1, r2 = await asyncio.gather(_capture(factory, sid), _capture(factory, sid))
    assert r1.id == r2.id  # exactly one revision row


async def test_revision_number_collision_survives(factory, engine, monkeypatch) -> None:
    """A different snapshot whose revision_number collides is re-allocated (§14.3)."""
    pid = await _proj(factory)
    sid = await _shot(factory, pid, "a")
    rev_a = await _capture(factory, sid)  # revision 1
    await _patch_subject(factory, sid, "b")  # different snapshot

    real = revisions._allocate_number
    state = {"first": True}

    async def fake(conn, shot_id):
        if state["first"]:
            state["first"] = False
            return rev_a.revision_number  # force (shot_id, revision_number) collision
        return await real(conn, shot_id)

    monkeypatch.setattr(revisions, "_allocate_number", fake)
    rev_b = await _capture(factory, sid)
    assert rev_b.id != rev_a.id
    assert rev_b.snapshot_hash != rev_a.snapshot_hash  # not convergence
    assert rev_b.revision_number != rev_a.revision_number  # re-allocated


async def test_revision_exhaustion_raises_internal_error(factory, monkeypatch) -> None:
    """Persistent revision_number collisions exhaust the budget -> invariant."""
    pid = await _proj(factory)
    sid = await _shot(factory, pid, "a")
    rev_a = await _capture(factory, sid)  # revision 1
    await _patch_subject(factory, sid, "b")  # different snapshot

    async def always_collide(conn, shot_id):
        return rev_a.revision_number  # always collides

    monkeypatch.setattr(revisions, "_allocate_number", always_collide)
    with pytest.raises(SoloRingError) as ei:
        await _capture(factory, sid)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
    assert ei.value.status_code == 500


# --- API: summary list excludes snapshot_json (plan §16) -------------------


async def test_revision_list_is_summary_only(client, factory) -> None:
    from tests.conftest import create_project, create_shot

    p = await create_project(client, name="P")
    s = await create_shot(client, p["id"], subject="a")
    # No public capture endpoint in M1; create revisions directly via the service.
    async with factory() as sess:
        await revisions.capture_revision(sess, s["id"])
        await shots.patch_shot(sess, s["id"], ShotPatch(subject="b"))
        await revisions.capture_revision(sess, s["id"])

    items = (await client.get(f"/shots/{s['id']}/revisions")).json()
    assert len(items) == 2
    for it in items:
        assert set(it.keys()) == {"id", "shot_id", "revision_number", "snapshot_hash", "created_at"}
        assert "snapshot_json" not in it
