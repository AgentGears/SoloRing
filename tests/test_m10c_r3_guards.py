"""M10C-r3 corrections — transition mutation parent fence (source-gate
round 2 residual P0-1).

One shared fence in transitions.py — active parent SpatialTrack AND
active owning SpatialWorld — runs BEFORE any evaluation, mutation, or
no-op return in every PATCH/DELETE path. Regressions cover the three
reviewer manifestations: empty `PATCH {}` beneath a tombstoned world
(service AND public HTTP shape), changed PATCH beneath a tombstoned
Track, DELETE beneath tombstoned world and tombstoned Track, plus the
positive active-parent DELETE control.
"""
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc


def fs(factory):
    return factory()


async def _seed(factory):
    pid, loc, rid, mov = str(uuid.uuid4()), str(uuid.uuid4()), \
        str(uuid.uuid4()), str(uuid.uuid4())
    seq = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', 'L',"
                " 't','t')"), {"e": loc, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": rid, "e": loc, "h": "ab" * 32})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'character', 'M',"
                " 't','t')"), {"e": mov, "p": pid})
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'S')"), {"s": seq, "p": pid})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc)
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    tr = await trans_svc.create_transition(
        fs(factory), track["id"], anchor_type="sequence",
        anchor_id=seq, boundary="start", operation="set",
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0])
    return {"pid": pid, "seq": seq, "world": world, "track": track,
            "tr": tr}


async def _tombstone(factory, table: str, row_id: str) -> None:
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                f"UPDATE {table} SET deleted_at = 't' WHERE id = :i"),
                {"i": row_id})


async def test_empty_patch_noop_fails_closed_beneath_tombstoned_world(
        factory, client):
    """The publicly reachable `PATCH {}` (every transport field
    optional) must still fail closed beneath a tombstoned world — the
    fence runs BEFORE the no-op early return."""
    seed = await _seed(factory)
    await _tombstone(factory, "spatial_worlds", seed["world"]["id"])
    # service level: no fields at all
    with pytest.raises(SoloRingError) as ei:
        await trans_svc.patch_transition(fs(factory), seed["tr"]["id"])
    assert ei.value.code == ErrorCode.SPATIAL_TRANSITION_INVALID
    assert ei.value.status_code == 409
    # public HTTP shape: empty object body
    r = await client.patch(f"/spatial-transitions/{seed['tr']['id']}",
                           json={})
    assert r.status_code == 409
    assert r.json()["error_code"] == "SPATIAL_TRANSITION_INVALID"
    # the transition is untouched
    got = await trans_svc.get_transition(fs(factory), seed["tr"]["id"])
    assert got["deleted_at"] is None and got["operation"] == "set"


async def test_changed_patch_beneath_tombstoned_track_rejected(factory):
    seed = await _seed(factory)
    await _tombstone(factory, "spatial_tracks", seed["track"]["id"])
    with pytest.raises(SoloRingError) as ei:
        await trans_svc.patch_transition(
            fs(factory), seed["tr"]["id"], translation_mm=[9, 9, 9])
    assert ei.value.status_code == 409
    assert "deleted SpatialTrack" in ei.value.message
    # empty PATCH beneath the tombstoned TRACK fails closed too
    with pytest.raises(SoloRingError, match="deleted SpatialTrack"):
        await trans_svc.patch_transition(fs(factory), seed["tr"]["id"])


async def test_delete_transition_beneath_tombstoned_world_rejected(
        factory):
    seed = await _seed(factory)
    await _tombstone(factory, "spatial_worlds", seed["world"]["id"])
    with pytest.raises(SoloRingError) as ei:
        await trans_svc.delete_transition(fs(factory), seed["tr"]["id"])
    assert ei.value.status_code == 409
    assert "deleted SpatialWorld" in ei.value.message
    got = await trans_svc.get_transition(fs(factory), seed["tr"]["id"])
    assert got["deleted_at"] is None  # untouched


async def test_delete_transition_beneath_tombstoned_track_rejected(
        factory):
    seed = await _seed(factory)
    await _tombstone(factory, "spatial_tracks", seed["track"]["id"])
    with pytest.raises(SoloRingError) as ei:
        await trans_svc.delete_transition(fs(factory), seed["tr"]["id"])
    assert ei.value.status_code == 409
    assert "deleted SpatialTrack" in ei.value.message


async def test_delete_transition_with_active_parents_succeeds(factory):
    seed = await _seed(factory)
    await trans_svc.delete_transition(fs(factory), seed["tr"]["id"])
    got = await trans_svc.get_transition(fs(factory), seed["tr"]["id"])
    assert got["deleted_at"] is not None
    # idempotent second delete beneath ACTIVE parents stays a clean no-op
    await trans_svc.delete_transition(fs(factory), seed["tr"]["id"])
