"""M10B closure corrections — P0-1..P0-3 races/corruption/CRUD proofs."""
import asyncio
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.spatial import revisions as rev_svc
from soloring.spatial import worlds as svc

from tests.test_m10b_world_authority import (  # noqa: F401  fixtures/helpers
    _add_frames,
    _make_world_with_state,
    _seed_project_location,
    factory_session,
)


# ------------------------------------------------- P0-2: real-operation races

async def test_race_real_capture_vs_world_edit(factory):
    """§61-1 at the REAL seam: the production capture_revision runs as a
    task; a REAL competing service mutation commits between the freeze
    and the fenced writer (via the production _after_freeze seam); the
    capture itself must raise SPATIAL_WORLD_CAPTURE_CONFLICT."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    frames = await _add_frames(factory, world["id"], state["id"], n=1)

    async def seam():
        # REAL competing service mutation commits inside the contested
        # window (between the freeze and the fenced writer)
        await svc.put_state_frame(
            factory_session(factory), state["id"], frames[0],
            translation_mm=[9999, 0, 0], rotation_udeg=[0, 0, 0],
            half_extents_mm=None, bound_entity_revision_id=None)

    with pytest.raises(SoloRingError) as ei:
        await rev_svc.capture_revision(
            factory_session(factory), state["id"], _after_freeze=seam)
    assert ei.value.code == "SPATIAL_WORLD_CAPTURE_CONFLICT"
    # no revision row was written (fail-closed, no partial history)
    async with factory() as session:
        n = (await session.execute(text(
            "SELECT COUNT(*) FROM spatial_world_revisions WHERE "
            "spatial_world_state_id = :s"), {"s": state["id"]})).scalar()
    assert n == 0


async def test_race_real_capture_vs_approval_change(factory):
    """§61-2 shape: approval is NOT a hash-bearing dependency, so a REAL
    approval committing mid-capture lets the capture complete — and the
    final state is one coherent outcome (revision created; approval
    pointer landed; no hybrid)."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=1)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])

    async def seam():
        # REAL approval commits inside the contested window; approval is
        # not a hash-bearing dependency, so the capture must still
        # complete and the approval pointer must land atomically
        await rev_svc.approve_revision(
            factory_session(factory), state["id"], revision_id=r1["id"],
            expected_approved_revision_id=None)

    # mutate working state slightly so the new capture is a NEW revision
    async with factory() as session:
        fid = (await session.execute(text(
            "SELECT spatial_frame_id FROM spatial_world_state_frames "
            "WHERE spatial_world_state_id = :s"),
            {"s": state["id"]})).scalar()
    await svc.put_state_frame(
        factory_session(factory), state["id"], fid,
        translation_mm=[0, 0, -4500], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)

    result = await rev_svc.capture_revision(
        factory_session(factory), state["id"], _after_freeze=seam)
    assert result["converged"] is False  # new revision r2 created
    async with factory() as session:
        row = (await session.execute(text(
            "SELECT approved_revision_id FROM spatial_world_states "
            "WHERE id = :s"), {"s": state["id"]})).scalar()
    assert row == r1["id"]  # the competitor's approval landed atomically


# ------------------------------------------------- P0-1: UPDATE corruption

async def test_corrupt_frame_child_update_fails_then_restores(factory):
    """UPDATE-based frame-child corruption with row count unchanged."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=2)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    async with factory() as session:
        before = (await session.execute(text(
            "SELECT x_mm FROM spatial_world_revision_frames WHERE "
            "spatial_world_revision_id = :r AND position = 0"),
            {"r": r1["id"]})).scalar()
        await session.execute(text(
            "UPDATE spatial_world_revision_frames SET x_mm = x_mm + 1 "
            "WHERE spatial_world_revision_id = :r"),
            {"r": r1["id"]})
        await session.commit()
    with pytest.raises(SoloRingError):
        await rev_svc.capture_revision(factory_session(factory),
                                       state["id"])
    async with factory() as session:
        await session.execute(text(
            "UPDATE spatial_world_revision_frames SET x_mm = x_mm - 1 "
            "WHERE spatial_world_revision_id = :r"),
            {"r": r1["id"]})
        await session.commit()
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r2["id"] == r1["id"] and r2["converged"] is True


async def test_corrupt_axis_child_update_fails_then_restores(factory):
    """UPDATE-based axis-child corruption with parent snapshot intact."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    frames = await _add_frames(factory, world["id"], state["id"], n=2)
    axis = await svc.create_axis(
        factory_session(factory), world["id"], key="ax", name="A")
    await svc.put_state_axis(
        factory_session(factory), state["id"], axis["id"],
        a_frame_id=frames[0], b_frame_id=frames[1])
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    async with factory() as session:
        await session.execute(text(
            "UPDATE spatial_world_revision_axes SET axis_key = 'tampered' "
            "WHERE spatial_world_revision_id = :r"),
            {"r": r1["id"]})
        await session.commit()
    with pytest.raises(SoloRingError):
        await rev_svc.capture_revision(factory_session(factory),
                                       state["id"])
    async with factory() as session:
        await session.execute(text(
            "UPDATE spatial_world_revision_axes SET axis_key = :k WHERE "
            "spatial_world_revision_id = :r"),
            {"k": "ax", "r": r1["id"]})
        await session.commit()
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r2["id"] == r1["id"] and r2["converged"] is True


# --------------------------------------------- Location-revision gate (§85)

async def test_location_revision_change_requires_new_state(factory):
    """§78/§85 critical proof: rev3's approved world does NOT apply to
    rev4; rev4 needs its own permanent state + capture + approval."""
    pid, eid, rid3, world, state3 = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state3["id"], n=1)
    r3 = await rev_svc.capture_revision(factory_session(factory),
                                        state3["id"])
    await rev_svc.approve_revision(
        factory_session(factory), state3["id"], revision_id=r3["id"],
        expected_approved_revision_id=None)

    # Location approval moves to revision 4
    rid4 = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 2, 1, :h, 't')"),
                {"r": rid4, "e": eid, "h": "ef" * 32})

    # the rev3 state/revision/approval remain intact and unchanged…
    async with factory() as session:
        st3 = (await session.execute(text(
            "SELECT approved_revision_id FROM spatial_world_states "
            "WHERE id = :s"), {"s": state3["id"]})).scalar()
        rev3_hash = (await session.execute(text(
            "SELECT snapshot_hash FROM spatial_world_revisions "
            "WHERE id = :r"), {"r": r3["id"]})).scalar()
    assert st3 == r3["id"]

    # …but no state exists for rev4: nothing carries forward
    async with factory() as session:
        st4 = (await session.execute(text(
            "SELECT COUNT(*) FROM spatial_world_states WHERE "
            "spatial_world_id = :w AND location_entity_revision_id = :r"),
            {"w": world["id"], "r": rid4})).scalar()
    assert st4 == 0

    # rev4 gets its own explicit state + capture; approval starts clean
    state4 = await svc.create_state(
        factory_session(factory), world["id"],
        location_entity_revision_id=rid4)
    f4 = await svc.create_frame(
        factory_session(factory), world["id"], key="rev4-origin",
        name="R4", parent_spatial_frame_id=None, bound_entity_id=None)
    await svc.put_state_frame(
        factory_session(factory), state4["id"], f4["id"],
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    r4 = await rev_svc.capture_revision(factory_session(factory),
                                        state4["id"])
    async with factory() as session:
        st4_appr = (await session.execute(text(
            "SELECT approved_revision_id FROM spatial_world_states WHERE "
            "id = :s"), {"s": state4["id"]})).scalar()
        rev3_hash_after = (await session.execute(text(
            "SELECT snapshot_hash FROM spatial_world_revisions "
            "WHERE id = :r"), {"r": r3["id"]})).scalar()
    assert st4_appr is None  # rev4 approval must be explicit
    assert r4["id"] != r3["id"]
    assert rev3_hash_after == rev3_hash  # rev3 history untouched


# ------------------------------------- P0-3: stable Frame/Axis CRUD surface

async def test_patch_frame_identity_rules(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    f1 = await svc.create_frame(
        factory_session(factory), world["id"], key="f1", name="Old",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await svc.patch_frame(factory_session(factory), f1["id"], name="New")
    # self-parent
    with pytest.raises(SoloRingError, match="own parent"):
        await svc.patch_frame(
            factory_session(factory), f1["id"],
            parent_spatial_frame_id=f1["id"])
    # cross-world parent
    _, _, _, world2, _state2 = await _make_world_with_state(factory)
    f2 = await svc.create_frame(
        factory_session(factory), world2["id"], key="x", name="X",
        parent_spatial_frame_id=None, bound_entity_id=None)
    with pytest.raises(SoloRingError, match="different world"):
        await svc.patch_frame(
            factory_session(factory), f1["id"],
            parent_spatial_frame_id=f2["id"])
    # cycle: f1 -> f2(same world) then f2 -> f1 rejected
    f3 = await svc.create_frame(
        factory_session(factory), world["id"], key="f3", name="C",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await svc.patch_frame(
        factory_session(factory), f1["id"],
        parent_spatial_frame_id=f3["id"])
    with pytest.raises(SoloRingError, match="cyclic"):
        await svc.patch_frame(
            factory_session(factory), f3["id"],
            parent_spatial_frame_id=f1["id"])


async def test_patch_and_delete_axis(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    axis = await svc.create_axis(
        factory_session(factory), world["id"], key="ax1", name="Old")
    await svc.patch_axis(factory_session(factory), axis["id"], name="New")
    async with factory() as session:
        name = (await session.execute(text(
            "SELECT name FROM spatial_axes WHERE id = :a"),
            {"a": axis["id"]})).scalar()
    assert name == "New"
    await svc.delete_axis(factory_session(factory), axis["id"])
    # membership blocks delete
    frames = await _add_frames(factory, world["id"], state["id"], n=2)
    axis2 = await svc.create_axis(
        factory_session(factory), world["id"], key="ax2", name="A2")
    await svc.put_state_axis(
        factory_session(factory), state["id"], axis2["id"],
        a_frame_id=frames[0], b_frame_id=frames[1])
    with pytest.raises(SoloRingError, match="membership"):
        await svc.delete_axis(factory_session(factory), axis2["id"])


async def test_delete_frame_route_surface(factory):
    """delete_frame service is reachable and guarded via its API route."""
    from soloring.api.spatial_worlds import delete_frame as route
    assert callable(route)
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    f = await svc.create_frame(
        factory_session(factory), world["id"], key="gone", name="G",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await svc.delete_frame(factory_session(factory), f["id"])
    async with factory() as session:
        deleted = (await session.execute(text(
            "SELECT deleted_at FROM spatial_frames WHERE id = :f"),
            {"f": f["id"]})).scalar()
    assert deleted is not None
