"""M10B re-gate corrections — P0-3 frame-PATCH integrity regressions."""
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.spatial import revisions as rev_svc
from soloring.spatial import worlds as svc

from tests.test_m10b_world_authority import (
    _make_world_with_state,
    factory_session,
)


async def _same_project_prop(factory, pid):
    beid, berid = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, "
                "name, created_at, updated_at) VALUES "
                "(:e, :p, 'prop', 'B', 't','t')"),
                {"e": beid, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": berid, "e": beid, "h": "cd" * 32})
    return beid, berid


async def _member(factory, state_id, frame_id, **kw):
    await svc.put_state_frame(
        factory_session(factory), state_id, frame_id,
        translation_mm=kw.get("t", [0, 0, -4000]),
        rotation_udeg=[0, 0, 0],
        half_extents_mm=kw.get("h"),
        bound_entity_revision_id=kw.get("r"))


async def test_parent_patch_requires_parent_in_every_member_state(factory):
    """S contains A + child C; PATCH C.parent -> B (same world, absent
    from S) is rejected; after adding B to S the same PATCH succeeds and
    the working/captured hash changes."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    a = await svc.create_frame(factory_session(factory), world["id"],
                               key="a", name="A", parent_spatial_frame_id=None,
                               bound_entity_id=None)
    b = await svc.create_frame(factory_session(factory), world["id"],
                               key="b", name="B", parent_spatial_frame_id=None,
                               bound_entity_id=None)
    c = await svc.create_frame(factory_session(factory), world["id"],
                               key="c", name="C",
                               parent_spatial_frame_id=a["id"],
                               bound_entity_id=None)
    await _member(factory, state["id"], a["id"])
    await _member(factory, state["id"], c["id"])
    with pytest.raises(SoloRingError, match="not the prospective parent"):
        await svc.patch_frame(
            factory_session(factory), c["id"],
            parent_spatial_frame_id=b["id"])
    # add B to the state -> the PATCH is now legal
    await _member(factory, state["id"], b["id"])
    before = await rev_svc.capture_revision(factory_session(factory),
                                            state["id"])
    await svc.patch_frame(
        factory_session(factory), c["id"],
        parent_spatial_frame_id=b["id"])
    after = await rev_svc.capture_revision(factory_session(factory),
                                           state["id"])
    assert after["snapshot_hash"] != before["snapshot_hash"]  # hash-bearing


async def test_bound_entity_patch_blocked_while_member(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    beid, berid = await _same_project_prop(factory, pid)
    beid2, berid2 = await _same_project_prop(factory, pid)
    f = await svc.create_frame(factory_session(factory), world["id"],
                               key="bound", name="X",
                               parent_spatial_frame_id=None,
                               bound_entity_id=beid)
    await _member(factory, state["id"], f["id"], r=berid)
    with pytest.raises(SoloRingError, match="memberships exist"):
        await svc.patch_frame(factory_session(factory), f["id"],
                              bound_entity_id=beid2)
    with pytest.raises(SoloRingError, match="memberships exist"):
        await svc.patch_frame(factory_session(factory), f["id"],
                              bound_entity_id=None)  # explicit unbind
    # legal sequence: remove membership -> rebind -> re-add
    await svc.delete_state_frame(factory_session(factory), state["id"],
                                 f["id"])
    await svc.patch_frame(factory_session(factory), f["id"],
                          bound_entity_id=beid2)
    await _member(factory, state["id"], f["id"], r=berid2)
    # stable-metadata mutation changes the captured hash when legal
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    await svc.delete_state_frame(factory_session(factory), state["id"],
                                 f["id"])
    await svc.patch_frame(factory_session(factory), f["id"],
                          bound_entity_id=beid)
    await _member(factory, state["id"], f["id"], r=berid)
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r2["snapshot_hash"] != r1["snapshot_hash"]


async def test_capture_cross_checks_stable_vs_membership_binding(factory):
    """A direct-DB authority split (membership says A, stable says B) is
    invariant corruption at capture, not a capturable state."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    be1, ber1 = await _same_project_prop(factory, pid)
    be2, ber2 = await _same_project_prop(factory, pid)
    f = await svc.create_frame(factory_session(factory), world["id"],
                               key="x", name="X",
                               parent_spatial_frame_id=None,
                               bound_entity_id=be1)
    await _member(factory, state["id"], f["id"], r=ber1)
    # stable frame re-bound to be2 AFTER the membership was written
    # (legal per policy only after removing membership; simulate the
    # authority split directly to prove the capture cross-check)
    async with factory() as session:
        await session.execute(text(
            "PRAGMA foreign_keys=OFF"))
        await session.execute(text(
            "UPDATE spatial_world_state_frames SET bound_entity_id = "
            ":other WHERE spatial_world_state_id = :s"),
            {"other": be2, "s": state["id"]})
        await session.execute(text(
            "PRAGMA foreign_keys=ON"))
        await session.commit()
    with pytest.raises(SoloRingError, match="authority split"):
        await rev_svc.capture_revision(factory_session(factory),
                                       state["id"])


async def test_patch_sentinels_omit_vs_null(factory):
    """Omitted fields unchanged; explicit null clears parent."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    a = await svc.create_frame(factory_session(factory), world["id"],
                               key="a", name="A",
                               parent_spatial_frame_id=None,
                               bound_entity_id=None)
    c = await svc.create_frame(factory_session(factory), world["id"],
                               key="c", name="C",
                               parent_spatial_frame_id=a["id"],
                               bound_entity_id=None)
    # omitted parent: unchanged
    await svc.patch_frame(factory_session(factory), c["id"], name="C2")
    async with factory() as session:
        parent = (await session.execute(text(
            "SELECT parent_spatial_frame_id, name FROM spatial_frames "
            "WHERE id = :f"), {"f": c["id"]})).first()
    assert parent[0] == a["id"] and parent[1] == "C2"
    # explicit null parent: cleared (no membership exists)
    await svc.patch_frame(factory_session(factory), c["id"],
                          parent_spatial_frame_id=None)
    async with factory() as session:
        parent = (await session.execute(text(
            "SELECT parent_spatial_frame_id FROM spatial_frames "
            "WHERE id = :f"), {"f": c["id"]})).first()
    assert parent[0] is None
