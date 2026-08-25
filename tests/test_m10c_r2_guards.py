"""M10C-r2 corrections — source-gate P0-1 and P0-2 regressions.

P0-1: the SpatialWorld delete guard rejects deletion while any active
SpatialTrack exists (the M10C child authority the M10B guard predated),
and Track/Transition mutations fail closed beneath a tombstoned world —
covering both the normal lifecycle (now unreachable through the guard)
and direct-DB corruption of that invariant.

P0-2: the strict staging resolver RAISES the frozen
NARRATIVE_CONTEXT_REQUIRED at the production semantic seam for
unassigned + relevant temporal data; the preview wrapper catches that
exact condition and projects it structurally; corruption conditions
still propagate.
"""
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import staging
from soloring.spatial import tracks as track_svc
from soloring.spatial import transitions as trans_svc
from soloring.spatial import worlds as world_svc


def fs(factory):
    return factory()


async def _seed(factory):
    pid, loc, rid, mov, movrev = (str(uuid.uuid4()) for _ in range(5))
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
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": movrev, "e": mov, "h": "cd" * 32})
            await session.execute(text(
                "INSERT INTO entity_approved_revisions (entity_id, "
                "revision_id, approved_at) VALUES (:e, :r, 't')"),
                {"e": mov, "r": movrev})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc)
    return pid, loc, rid, mov, world


# ------------------------------------------------------ P0-1: lifecycle

async def test_world_delete_blocked_while_active_track_exists(factory):
    pid, loc, rid, mov, world = await _seed(factory)
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    with pytest.raises(SoloRingError) as ei:
        await world_svc.delete_world(fs(factory), world["id"])
    assert ei.value.code == ErrorCode.SPATIAL_WORLD_INVALID
    assert ei.value.status_code == 409
    assert "active SpatialTracks" in ei.value.message
    # the world is still there, undamaged
    async with factory() as session:
        state = (await session.execute(text(
            "SELECT deleted_at FROM spatial_worlds WHERE id = :w"),
            {"w": world["id"]})).scalar()
    assert state is None
    # removing the track releases the guard (tombstoned track does not
    # dangle)
    await track_svc.delete_track(fs(factory), track["id"])
    await world_svc.delete_world(fs(factory), world["id"])


async def test_world_delete_trackless_optional_world_still_deletes(factory):
    pid, loc, rid, mov, world = await _seed(factory)
    await world_svc.delete_world(fs(factory), world["id"])  # no track → OK


async def test_mutations_fail_closed_beneath_tombstoned_world(factory):
    """Direct-DB corruption of the world→track invariant (the service
    guard makes this unreachable normally): every Track/Transition
    mutation beneath the tombstoned world is rejected."""
    pid, loc, rid, mov, world = await _seed(factory)
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    seq = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'S')"), {"s": seq, "p": pid})
            # corrupt: tombstone the world beneath the ACTIVE track
            await session.execute(text(
                "UPDATE spatial_worlds SET deleted_at = 't' "
                "WHERE id = :w"), {"w": world["id"]})
    with pytest.raises(SoloRingError, match="deleted SpatialWorld") as e1:
        await track_svc.patch_track(fs(factory), track["id"],
                                    requirement="required")
    assert e1.value.status_code == 409
    with pytest.raises(SoloRingError, match="deleted SpatialWorld") as e2:
        await track_svc.delete_track(fs(factory), track["id"])
    assert e2.value.status_code == 409
    with pytest.raises(SoloRingError, match="deleted SpatialWorld") as e3:
        await trans_svc.create_transition(
            fs(factory), track["id"], anchor_type="sequence",
            anchor_id=seq, boundary="start", operation="set",
            translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0])
    assert e3.value.status_code == 409
    # PATCH of an existing transition also fails closed beneath the
    # tombstoned world
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_worlds SET deleted_at = NULL "
                "WHERE id = :w"), {"w": world["id"]})
    tr = await trans_svc.create_transition(
        fs(factory), track["id"], anchor_type="sequence",
        anchor_id=seq, boundary="start", operation="set",
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0])
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_worlds SET deleted_at = 't' "
                "WHERE id = :w"), {"w": world["id"]})
    with pytest.raises(SoloRingError, match="deleted SpatialWorld") as e4:
        await trans_svc.patch_transition(fs(factory), tr["id"],
                                         operation="clear")
    assert e4.value.status_code == 409
    # create_track beneath a tombstoned world was already fail-closed
    # (positive control)
    with pytest.raises(SoloRingError, match="not found or deleted"):
        await track_svc.create_track(
            fs(factory), world["id"], entity_id=mov,
            requirement="optional")


# ------------------------------------------- P0-2: strict enforcement

async def test_resolver_raises_narrative_context_required(factory, engine):
    """The production seam itself enforces the frozen condition: the
    strict resolver raises NARRATIVE_CONTEXT_REQUIRED (409) for
    unassigned + relevant temporal data — not a projection, not a
    manually constructed error object."""
    pid, loc, rid, mov, world = await _seed(factory)
    seq, scene, shot, unassigned = (str(uuid.uuid4()) for _ in range(4))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'S')"), {"s": seq, "p": pid})
            await session.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :s, 0, 'C')"), {"c": scene, "s": seq})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "scene_id, scene_position) VALUES (:i, :p, 1, 'x', :c, 0)"),
                {"i": shot, "p": pid, "c": scene})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:u, :p, 99, 'unassigned')"),
                {"u": unassigned, "p": pid})
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    # BEFORE any transition: unassigned + no relevant data resolves
    # normally (no blocker invented)
    async with engine.connect() as conn:
        out = await staging.resolve_effective_staging(
            conn, shot_id=unassigned, spatial_world_id=world["id"],
            resolved_entity_revisions={mov: rid})
    assert out.assigned is False and out.relevant_transition_data is False
    # AFTER a relevant transition exists: the resolver RAISES
    await trans_svc.create_transition(
        fs(factory), track["id"], anchor_type="sequence",
        anchor_id=seq, boundary="start", operation="set",
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0])
    with pytest.raises(SoloRingError) as ei:
        async with engine.connect() as conn:
            await staging.resolve_effective_staging(
                conn, shot_id=unassigned, spatial_world_id=world["id"],
                resolved_entity_revisions={mov: rid})
    assert ei.value.code == ErrorCode.NARRATIVE_CONTEXT_REQUIRED
    assert ei.value.status_code == 409
    # an ASSIGNED shot with the same data resolves normally
    async with engine.connect() as conn:
        ok = await staging.resolve_effective_staging(
            conn, shot_id=shot, spatial_world_id=world["id"],
            resolved_entity_revisions={mov: rid})
    assert ok.assigned is True and len(ok.states) == 1


async def test_preview_catches_and_projects_the_strict_condition(factory):
    """The inspection wrapper catches EXACTLY NARRATIVE_CONTEXT_REQUIRED
    from the strict resolver and projects it structurally (§10.4); any
    other failure (e.g. corruption) still propagates."""
    pid, loc, rid, mov, world = await _seed(factory)
    seq, unassigned = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'S')"), {"s": seq, "p": pid})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:u, :p, 99, 'unassigned')"),
                {"u": unassigned, "p": pid})
            await session.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id,"
                " role, position) VALUES (:s, :e, 'cast', 0)"),
                {"s": unassigned, "e": mov})
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    await trans_svc.create_transition(
        fs(factory), track["id"], anchor_type="sequence",
        anchor_id=seq, boundary="start", operation="set",
        translation_mm=[0, 0, 0], rotation_udeg=[0, 0, 0])
    body = await staging.preview_staging(
        fs(factory), spatial_world_id=world["id"], shot_id=unassigned)
    assert body["narrative_context_required"] is True
    assert body["assigned"] is False
    assert body["relevant_transition_data"] is True
    assert body["states"] == [] and body["absent"] == []
    # corruption beneath the same wrapper still propagates (nothing else
    # is caught): corrupt the winning transition's operation domain and
    # read through an ASSIGNED target so the resolver reaches winner
    # validation rather than the narrative condition
    seq2_scene, shot2 = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :s, 1, 'C2')"),
                {"c": seq2_scene, "s": seq})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "scene_id, scene_position) VALUES (:u, :p, 98, 'x', :c, 0)"),
                {"u": shot2, "p": pid, "c": seq2_scene})
            await session.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id,"
                " role, position) VALUES (:s, :e, 'cast', 0)"),
                {"s": shot2, "e": mov})
            conn = await session.connection()
            await conn.exec_driver_sql(
                "PRAGMA ignore_check_constraints=ON")
            await conn.execute(text(
                "UPDATE spatial_transitions SET operation = 'blink'"))
            await conn.exec_driver_sql(
                "PRAGMA ignore_check_constraints=OFF")
    with pytest.raises(SoloRingError) as ei:
        await staging.preview_staging(
            fs(factory), spatial_world_id=world["id"], shot_id=shot2)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION
