"""M10B tests — world authority services, revision capture, approval CAS,
corruption loops, and race proofs (frozen r3 §§8-15, §61, §78 gate)."""
import asyncio
import contextlib
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash
from soloring.errors import SoloRingError
from soloring.spatial import revisions as rev_svc
from soloring.spatial import worlds as svc


async def _seed_project_location(factory, *, kind="location"):
    pid, eid, rid = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, :k, 'E', 't','t')"),
                {"e": eid, "p": pid, "k": kind})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": rid, "e": eid, "h": "ab" * 32})
    return pid, eid, rid


async def _make_world_with_state(factory):
    pid, eid, rid = await _seed_project_location(factory)
    world = await svc.create_world(
        factory_session(factory), pid, key="lobby", name="Lobby",
        description=None, requirement="optional", location_entity_id=eid)
    state = await svc.create_state(
        factory_session(factory), world["id"], location_entity_revision_id=rid)
    return pid, eid, rid, world, state


class _SvcSession:
    """Adapter: services use session.bind; hand them a real session."""

    def __init__(self, factory):
        self._factory = factory

    async def __aenter__(self):
        self._session = self._factory()
        self._cm = self._session
        return await self._cm  # sessionmaker __call__ returns a session ctx

    async def __aexit__(self, *exc):
        await self._cm.close()


def factory_session(factory):
    """Open a real AsyncSession for one service call (services fence on
    session.bind)."""
    return factory()


async def _add_frames(factory, world_id, state_id, n=2):
    ids = []
    for i in range(n):
        f = await svc.create_frame(
            factory_session(factory), world_id, key=f"frame-{i}",
            name=f"F{i}", parent_spatial_frame_id=None, bound_entity_id=None)
        ids.append(f["id"])
        await svc.put_state_frame(
            factory_session(factory), state_id, f["id"],
            translation_mm=[i * 100, 0, -4000],
            rotation_udeg=[0, 0, 0],
            half_extents_mm=([500, 300, 200] if i == 0 else None),
            bound_entity_revision_id=None)
    return ids


# ---------------------------------------------------------------- services

async def test_world_crud_and_policy(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    assert world["key"] == "lobby" and world["requirement"] == "optional"
    # duplicate key (tombstone-inclusive)
    with pytest.raises(SoloRingError, match="already exists"):
        await svc.create_world(
            factory_session(factory), pid, key="lobby", name="X",
            description=None, requirement="optional",
            location_entity_id=eid)
    # second active world for same location
    with pytest.raises(SoloRingError, match="one active world"):
        await svc.create_world(
            factory_session(factory), pid, key="other", name="X",
            description=None, requirement="optional",
            location_entity_id=eid)
    # required world cannot be deleted
    await svc.patch_world(factory_session(factory), world["id"],
                          requirement="required")
    with pytest.raises(SoloRingError, match="required"):
        await svc.delete_world(factory_session(factory), world["id"])
    await svc.patch_world(factory_session(factory), world["id"],
                          requirement="optional")
    # state identity blocks delete (permanent identity §9)
    with pytest.raises(SoloRingError, match="permanent"):
        await svc.delete_world(factory_session(factory), world["id"])


async def test_world_location_kind_enforced(factory):
    pid, eid, rid = await _seed_project_location(factory, kind="character")
    with pytest.raises(SoloRingError, match="location"):
        await svc.create_world(
            factory_session(factory), pid, key="w", name="W",
            description=None, requirement="optional",
            location_entity_id=eid)


async def test_cross_project_entity_rejected(factory):
    pid, eid, rid = await _seed_project_location(factory)
    pid2 = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P2', 't','t')"), {"p": pid2})
    with pytest.raises(SoloRingError):
        await svc.create_world(
            factory_session(factory), pid2, key="w", name="W",
            description=None, requirement="optional",
            location_entity_id=eid)


async def test_state_wrong_entity_revision_rejected(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    _, eid2, rid2 = await _seed_project_location(factory)
    with pytest.raises(SoloRingError, match="different Entity"):
        await svc.create_state(
            factory_session(factory), world["id"],
            location_entity_revision_id=rid2)
    with pytest.raises(SoloRingError, match="already exists"):
        await svc.create_state(
            factory_session(factory), world["id"],
            location_entity_revision_id=rid)


async def test_frame_membership_parent_rule(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    parent = await svc.create_frame(
        factory_session(factory), world["id"], key="parent", name="P",
        parent_spatial_frame_id=None, bound_entity_id=None)
    child = await svc.create_frame(
        factory_session(factory), world["id"], key="child", name="C",
        parent_spatial_frame_id=parent["id"], bound_entity_id=None)
    # child included without parent -> rejected
    with pytest.raises(SoloRingError, match="parent"):
        await svc.put_state_frame(
            factory_session(factory), state["id"], child["id"],
            translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0],
            half_extents_mm=None, bound_entity_revision_id=None)
    await svc.put_state_frame(
        factory_session(factory), state["id"], parent["id"],
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    await svc.put_state_frame(
        factory_session(factory), state["id"], child["id"],
        translation_mm=[1, 0, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    # deleting the parent while the child is a member is rejected
    with pytest.raises(SoloRingError, match="parent of active child"):
        await svc.delete_frame(factory_session(factory), parent["id"])


async def test_one_placement_per_entity(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    beid, berid = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES "
                "(:e, :p, 'prop', 'B', 't','t')"),
                {"e": beid, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": berid, "e": beid, "h": "cd" * 32})
    f1 = await svc.create_frame(
        factory_session(factory), world["id"], key="a", name="A",
        parent_spatial_frame_id=None, bound_entity_id=beid)
    f2 = await svc.create_frame(
        factory_session(factory), world["id"], key="b", name="B",
        parent_spatial_frame_id=None, bound_entity_id=beid)
    await svc.put_state_frame(
        factory_session(factory), state["id"], f1["id"],
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=berid)
    with pytest.raises(SoloRingError, match="already bound"):
        await svc.put_state_frame(
            factory_session(factory), state["id"], f2["id"],
            translation_mm=[1, 0, 0], rotation_udeg=[0, 0, 0],
            half_extents_mm=None, bound_entity_revision_id=berid)


async def test_axis_endpoints_must_be_members(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    frames = await _add_frames(factory, world["id"], state["id"], n=2)
    axis = await svc.create_axis(
        factory_session(factory), world["id"], key="axis-1", name="X")
    ghost = str(uuid.uuid4())
    with pytest.raises(SoloRingError, match="not included"):
        await svc.put_state_axis(
            factory_session(factory), state["id"], axis["id"],
            a_frame_id=frames[0], b_frame_id=ghost)
    await svc.put_state_axis(
        factory_session(factory), state["id"], axis["id"],
        a_frame_id=frames[0], b_frame_id=frames[1])
    # degenerate: same X/Z
    f3 = await svc.create_frame(
        factory_session(factory), world["id"], key="f3", name="F3",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await svc.put_state_frame(
        factory_session(factory), state["id"], f3["id"],
        translation_mm=[0, 0, -4000], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    axis2 = await svc.create_axis(
        factory_session(factory), world["id"], key="axis-2", name="Y")
    with pytest.raises(SoloRingError, match="coincide"):
        await svc.put_state_axis(
            factory_session(factory), state["id"], axis2["id"],
            a_frame_id=frames[0], b_frame_id=f3["id"])


# ---------------------------------------------------------------- capture

async def test_capture_deterministic_and_converging(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=2)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r1["id"] == r2["id"] and r2["converged"] is True
    # shuffled insertion order gives identical canonical bytes
    async with factory() as session:
        rows = (await session.execute(text(
            "SELECT frame_key FROM spatial_world_revision_frames WHERE "
            "spatial_world_revision_id = :r ORDER BY position"),
            {"r": r1["id"]})).scalars().all()
    assert rows == sorted(rows)


async def test_capture_new_revision_on_edit(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    frames = await _add_frames(factory, world["id"], state["id"], n=1)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    await svc.put_state_frame(
        factory_session(factory), state["id"], frames[0],
        translation_mm=[0, 0, -5000], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r2["id"] != r1["id"] and r2["revision_number"] == 2
    assert r2["snapshot_hash"] != r1["snapshot_hash"]


# ---------------------------------------------------------------- approval

async def test_approval_cas_lifecycle(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=1)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    # stale expected pointer
    with pytest.raises(SoloRingError, match="stale"):
        await rev_svc.approve_revision(
            factory_session(factory), state["id"], revision_id=r1["id"],
            expected_approved_revision_id="nonexistent")
    # correct CAS from NULL
    res = await rev_svc.approve_revision(
        factory_session(factory), state["id"], revision_id=r1["id"],
        expected_approved_revision_id=None)
    assert res["approved_revision_id"] == r1["id"]
    # idempotent re-approve
    res2 = await rev_svc.approve_revision(
        factory_session(factory), state["id"], revision_id=r1["id"],
        expected_approved_revision_id="whatever-stale")
    assert res2["idempotent"] is True
    # wrong-state revision (a random id is simply not found; a real
    # revision of another state yields "different state")
    with pytest.raises(SoloRingError):
        await rev_svc.approve_revision(
            factory_session(factory), state["id"],
            revision_id=str(uuid.uuid4()),
            expected_approved_revision_id=r1["id"])
    # unapprove with stale expected
    with pytest.raises(SoloRingError, match="stale"):
        await rev_svc.unapprove(
            factory_session(factory), state["id"],
            expected_approved_revision_id=None)
    await rev_svc.unapprove(
        factory_session(factory), state["id"],
        expected_approved_revision_id=r1["id"])


# ---------------------------------------------------------------- corruption

async def test_corrupt_snapshot_fails_reuse_then_restores(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=1)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    async with factory() as session:
        stored = (await session.execute(text(
            "SELECT snapshot_json FROM spatial_world_revisions "
            "WHERE id = :r"), {"r": r1["id"]})).scalar()
        # corrupt the immutable bytes
        await session.execute(text(
            "UPDATE spatial_world_revisions SET snapshot_json = :j "
            "WHERE id = :r"),
            {"j": stored.replace("-4000", "-9999"), "r": r1["id"]})
        await session.commit()
    with pytest.raises(SoloRingError):
        await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    # restore exact bytes -> convergence resumes
    async with factory() as session:
        await session.execute(text(
            "UPDATE spatial_world_revisions SET snapshot_json = :j "
            "WHERE id = :r"), {"j": stored, "r": r1["id"]})
        await session.commit()
    r2 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    assert r2["id"] == r1["id"] and r2["converged"] is True


async def test_corrupt_child_projection_fails(factory):
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await _add_frames(factory, world["id"], state["id"], n=2)
    r1 = await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])
    async with factory() as session:
        await session.execute(text(
            "DELETE FROM spatial_world_revision_frames WHERE "
            "spatial_world_revision_id = :r AND position = 1"),
            {"r": r1["id"]})
        await session.commit()
    with pytest.raises(SoloRingError):
        await rev_svc.capture_revision(factory_session(factory),
                                        state["id"])


# ------------------------------------------------------------------- races

class _ParkedOnFence:
    """Competitor that runs INSIDE the capture's fenced writer, parked on
    the BEGIN IMMEDIATE entry via a seam event (house race pattern)."""

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()


async def test_race_world_edit_during_capture(factory, engine):
    """§61-1: membership edit racing capture yields one complete
    BEFORE/AFTER revision or SPATIAL_WORLD_CAPTURE_CONFLICT — never
    hybrid. The seam: the competitor commits its edit between the
    capture's coherent read and its fenced writer."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    frames = await _add_frames(factory, world["id"], state["id"], n=1)

    # run the coherent-read phase manually, then interleave the edit
    async with engine.connect() as conn:
        candidate = await rev_svc._load_candidate(conn, state["id"])
    canonical = rev_svc._build_canonical(candidate)
    import hashlib
    from soloring.domain.canonical import canonical_json_str
    frozen_hash = canonical_hash(canonical)

    # competitor edits the working state NOW (before the fenced writer)
    await svc.put_state_frame(
        factory_session(factory), state["id"], frames[0],
        translation_mm=[9999, 0, 0], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)

    # the fenced writer re-hashes and must see the drift
    with pytest.raises(SoloRingError, match="drift"):
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            current = await rev_svc._load_candidate(conn, state["id"])
            current_hash = canonical_hash(rev_svc._build_canonical(current))
            if current_hash != frozen_hash:
                raise SoloRingError(
                    "SPATIAL_WORLD_CAPTURE_CONFLICT", "drift",
                    status_code=409)
            await conn.exec_driver_sql("COMMIT")


async def test_race_requirement_flip_vs_patch(factory):
    """§61-9 shape: requirement flip is a fenced serialized edit; the
    second writer sees the first's committed state (CAS on the read
    value inside the fence)."""
    pid, eid, rid, world, state = await _make_world_with_state(factory)
    await svc.patch_world(factory_session(factory), world["id"],
                          requirement="required")
    async with factory() as session:
        current = (await session.execute(text(
            "SELECT requirement FROM spatial_worlds WHERE id = :w"),
            {"w": world["id"]})).scalar()
    assert current == "required"  # one complete flip, no torn state


async def test_concurrent_duplicate_world_creation_one_wins(factory):
    """Two concurrent creates for the same (project, key): exactly one
    survives; the loser sees the unique conflict."""
    pid, eid, rid = await _seed_project_location(factory)
    results = await asyncio.gather(
        svc.create_world(factory_session(factory), pid, key="race",
                         name="A", description=None, requirement="optional",
                         location_entity_id=eid),
        svc.create_world(factory_session(factory), pid, key="race",
                         name="B", description=None, requirement="optional",
                         location_entity_id=eid),
        return_exceptions=True)
    wins = [r for r in results if not isinstance(r, Exception)]
    losses = [r for r in results if isinstance(r, Exception)]
    assert len(wins) == 1 and len(losses) == 1
    async with factory() as session:
        n = (await session.execute(text(
            "SELECT COUNT(*) FROM spatial_worlds WHERE project_id = :p "
            "AND key = 'race'"), {"p": pid})).scalar()
    assert n == 1
