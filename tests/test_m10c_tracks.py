"""M10C-1 tests — SpatialTrack authority (M10C plan §6; matrix items 1-13).

Track lifecycle, same-Project ownership, active (world, Entity)
uniqueness with race-safe duplicate translation, requirement policy,
delete guards (downgrade-first, active transitions, current-plan
blocking references via the read-only schema-1 reader), tombstone
behavior, transport strictness, and the workspace projection.
"""
import asyncio
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import tracks as svc
from soloring.spatial import worlds as world_svc
from soloring.spatial.plan_reference import plan_blocking_references_track


def fs(factory):
    """One real AsyncSession for one service call (services fence on
    session.bind)."""
    return factory()


async def _seed(factory, *, movable_kind="character"):
    """Project + location Entity/revision + a movable dependent Entity."""
    pid, loc_eid, rid, mov_eid = (str(uuid.uuid4()) for _ in range(4))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't', 't')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', 'L',"
                " 't','t')"), {"e": loc_eid, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": rid, "e": loc_eid, "h": "ab" * 32})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, :k, 'M', 't','t')"),
                {"e": mov_eid, "p": pid, "k": movable_kind})
    return pid, loc_eid, rid, mov_eid


async def _make_world_with_track(factory):
    pid, loc_eid, rid, mov_eid = await _seed(factory)
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc_eid)
    track = await svc.create_track(
        fs(factory), world["id"], entity_id=mov_eid, requirement="optional")
    return pid, loc_eid, rid, mov_eid, world, track


async def _insert_active_transition(factory, track_id, *, anchor_id,
                                    anchor_type="shot", boundary="start"):
    tid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO spatial_transitions (id, spatial_track_id, "
                "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, "
                "z_mm, yaw_udeg, pitch_udeg, roll_udeg, created_at, "
                "updated_at) VALUES (:i,:t,:at,:a,:b,'set',1,2,3,4,5,6,"
                "'t','t')"),
                {"i": tid, "t": track_id, "at": anchor_type,
                 "a": anchor_id, "b": boundary})
    return tid


async def _insert_plan(factory, project_id, world_id, *, plan_doc,
                       shot_suffix="s1"):
    shot_id = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            next_no = (await session.execute(text(
                "SELECT COALESCE(MAX(shot_number), 0) + 1 FROM shots "
                "WHERE project_id = :p"), {"p": project_id})).scalar()
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:s, :p, :n, 'shot')"),
                {"s": shot_id, "p": project_id, "n": next_no})
            await session.execute(text(
                "INSERT INTO shot_spatial_plans (shot_id, spatial_world_id, "
                "plan_json, plan_hash, created_at, updated_at) VALUES "
                "(:s,:w,:j,:h,'t','t')"),
                {"s": shot_id, "w": world_id, "j": plan_doc,
                 "h": "0" * 64})
    return shot_id


def _plan_doc(world_id, track_ids):
    return json.dumps({
        "schema_version": 1,
        "spatial_world_id": world_id,
        "camera": {"projection": "perspective", "focal_length_um": 50000,
                   "sensor_width_um": 36000, "sensor_height_um": 20250,
                   "keyframes": []},
        "blocking": [{"spatial_track_id": t, "screen_direction": None,
                      "keyframes": []} for t in track_ids],
    })


# ------------------------------------------------------------- authority

async def test_track_create_valid_and_duplicate_translated(factory):
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    assert track["requirement"] == "optional"
    got = await svc.get_track(fs(factory), track["id"])
    assert got["entity_id"] == mov_eid
    assert got["spatial_world_id"] == world["id"]
    # matrix 6: duplicate active (world, Entity)
    with pytest.raises(SoloRingError) as ei:
        await svc.create_track(fs(factory), world["id"], entity_id=mov_eid,
                               requirement="required")
    assert ei.value.code == ErrorCode.SPATIAL_ENTITY_INSTANCING_UNSUPPORTED
    assert ei.value.status_code == 409


async def test_track_cross_project_entity_rejected(factory):
    # matrix 2
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    other_entity = str(uuid.uuid4())
    other_pid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'Q', 't', 't')"), {"p": other_pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'prop', 'X', "
                "'t','t')"),
                {"e": other_entity, "p": other_pid})
    with pytest.raises(SoloRingError, match="another Project"):
        await svc.create_track(fs(factory), world["id"],
                               entity_id=other_entity,
                               requirement="optional")


async def test_track_deleted_world_and_entity_rejected(factory):
    # matrix 3, 4
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    # soft-delete the entity directly, then try a second track for it
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE creative_entities SET deleted_at = 't' "
                "WHERE id = :e"), {"e": mov_eid})
    with pytest.raises(SoloRingError, match="not found or inactive"):
        await svc.create_track(fs(factory), world["id"], entity_id=mov_eid,
                               requirement="optional")
    # deleted world
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_worlds SET deleted_at = 't' "
                "WHERE id = :w"), {"w": world["id"]})
    other = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'prop', 'O', "
                "'t','t')"), {"e": other, "p": pid})
    with pytest.raises(SoloRingError, match="not found or deleted"):
        await svc.create_track(fs(factory), world["id"], entity_id=other,
                               requirement="optional")


async def test_track_invalid_requirement_rejected(factory):
    # matrix 5
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    with pytest.raises(SoloRingError, match="requirement"):
        await svc.create_track(fs(factory), world["id"], entity_id=mov_eid,
                               requirement="sometimes")


async def test_concurrent_duplicate_track_creation_one_active_winner(
        factory):
    # matrix 7: two real concurrent fenced creates for the same active
    # (world, Entity) — BEGIN IMMEDIATE serializes them; exactly one
    # commits, the loser receives the instancing error.
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    other_eid = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'vehicle', 'V', "
                "'t','t')"), {"e": other_eid, "p": pid})
    results = await asyncio.gather(
        svc.create_track(fs(factory), world["id"], entity_id=other_eid,
                         requirement="required"),
        svc.create_track(fs(factory), world["id"], entity_id=other_eid,
                         requirement="optional"),
        return_exceptions=True)
    wins = [r for r in results if not isinstance(r, Exception)]
    losses = [r for r in results if isinstance(r, Exception)]
    assert len(wins) == 1 and len(losses) == 1
    assert losses[0].code == ErrorCode.SPATIAL_ENTITY_INSTANCING_UNSUPPORTED
    async with factory() as session:
        n = (await session.execute(text(
            "SELECT COUNT(*) FROM spatial_tracks WHERE "
            "spatial_world_id = :w AND entity_id = :e AND deleted_at IS "
            "NULL"), {"w": world["id"], "e": other_eid})).scalar()
    assert n == 1


async def test_track_identity_cannot_be_retargeted(client):
    # matrix 8: the transport has no identity fields at all (schema
    # extra=forbid); the service exposes no retarget parameters.
    r = await client.post("/projects", json={"name": "P"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    async def _mk_entity(kind):
        import uuid as _u
        # entities API is story-world scoped in M6; direct DB is simpler
        return str(_u.uuid4()), kind

    # seed via service-level DB would need the app engine; use the
    # public entities route if present, else fall back to factory-style
    # direct insert through the app's engine is unavailable — so drive
    # the world+track through the API with a location entity created by
    # the story-world entity route.
    er = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "location", "name": "L"})
    assert er.status_code == 201, er.text
    loc = er.json()["id"]
    mr = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "character", "name": "M"})
    assert mr.status_code == 201, mr.text
    mov = mr.json()["id"]
    wr = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "lobby", "name": "Lobby", "requirement": "optional",
        "location_entity_id": loc})
    assert wr.status_code == 201, r.text
    world_id = wr.json()["id"]
    tr = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mov, "requirement": "optional"})
    assert tr.status_code == 201, tr.text
    track_id = tr.json()["id"]
    # retarget attempts are undeclared fields → 422 (matrix 62)
    pr = await client.patch(f"/spatial-tracks/{track_id}", json={
        "requirement": "required", "spatial_world_id": str(uuid.uuid4())})
    assert pr.status_code == 422
    pr2 = await client.patch(f"/spatial-tracks/{track_id}", json={
        "requirement": "required", "entity_id": str(uuid.uuid4())})
    assert pr2.status_code == 422


async def test_track_required_delete_rejected_then_downgrade(factory):
    # matrix 9 + requirement mutation path
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    await svc.patch_track(fs(factory), track["id"],
                          requirement="required")
    got = await svc.get_track(fs(factory), track["id"])
    assert got["requirement"] == "required"
    with pytest.raises(SoloRingError) as ei:
        await svc.delete_track(fs(factory), track["id"])
    assert ei.value.status_code == 409
    await svc.patch_track(fs(factory), track["id"], requirement="optional")


async def test_track_patch_deleted_rejected_and_fenced_updated_at(factory):
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    # force a stale updated_at so the DB-owned advance is deterministic
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_tracks SET updated_at = "
                "'2020-01-01T00:00:00.000Z' WHERE id = :t"),
                {"t": track["id"]})
    await svc.patch_track(fs(factory), track["id"], requirement="required")
    async with factory() as session:
        after = (await session.execute(text(
            "SELECT updated_at, requirement FROM spatial_tracks "
            "WHERE id = :t"), {"t": track["id"]})).first()
    assert after[0] > "2020-01-01T00:00:00.000Z" and after[1] == "required"
    # tombstoned track: patch rejected
    await svc.patch_track(fs(factory), track["id"], requirement="optional")
    await svc.delete_track(fs(factory), track["id"])
    with pytest.raises(SoloRingError, match="deleted"):
        await svc.patch_track(fs(factory), track["id"],
                              requirement="required")


async def test_track_active_transition_blocks_delete(factory):
    # matrix 10
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    anchor = str(uuid.uuid4())  # anchor validity is M10C-2's concern;
    # the delete guard only checks existence of an active row.
    await _insert_active_transition(factory, track["id"], anchor_id=anchor)
    with pytest.raises(SoloRingError, match="active SpatialTransitions"):
        await svc.delete_track(fs(factory), track["id"])


async def test_track_plan_blocking_reference_blocks_delete(factory):
    # matrix 11
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    await _insert_plan(factory, pid, world["id"],
                       plan_doc=_plan_doc(world["id"], [track["id"]]))
    with pytest.raises(SoloRingError, match="blocking entry"):
        await svc.delete_track(fs(factory), track["id"])
    # a plan that references a DIFFERENT track does not block: remove the
    # referencing plan, keep an other-track plan in the same world
    other_track = str(uuid.uuid4())
    await _insert_plan(factory, pid, world["id"],
                       plan_doc=_plan_doc(world["id"], [other_track]),
                       shot_suffix="s2")
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "DELETE FROM shot_spatial_plans WHERE plan_json LIKE :frag"),
                {"frag": f"%{track['id']}%"})
    await svc.delete_track(fs(factory), track["id"])  # matrix 13 path


async def test_track_malformed_plan_fails_delete_closed(factory):
    # matrix 12
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    for bad in (
        "not json at all",
        json.dumps([1, 2, 3]),
        json.dumps({"schema_version": 2, "spatial_world_id": world["id"],
                    "blocking": []}),
        json.dumps({"schema_version": 1, "blocking": []}),
        json.dumps({"schema_version": 1,
                    "spatial_world_id": "other-world", "blocking": []}),
        json.dumps({"schema_version": 1,
                    "spatial_world_id": world["id"]}),
        json.dumps({"schema_version": 1,
                    "spatial_world_id": world["id"],
                    "blocking": [{"no_track": True}]}),
    ):
        await _insert_plan(factory, pid, world["id"], plan_doc=bad)
        with pytest.raises(SoloRingError) as ei:
            await svc.delete_track(fs(factory), track["id"])
        assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


async def test_plan_reference_reader_string_search_boundary():
    # the reader decides on parsed structure only
    doc = _plan_doc("w1", ["t1"])
    assert plan_blocking_references_track(
        doc, row_spatial_world_id="w1", spatial_track_id="t1") is True
    assert plan_blocking_references_track(
        doc, row_spatial_world_id="w1", spatial_track_id="t2") is False
    # substring-carrying ids must not match without exact equality
    doc2 = _plan_doc("w1", ["track-1-full"])
    assert plan_blocking_references_track(
        doc2, row_spatial_world_id="w1", spatial_track_id="track-1") is False


async def test_track_legal_delete_and_tombstone_frees_coordinate(factory):
    # matrix 13 + deterministic tombstone behavior
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    await svc.delete_track(fs(factory), track["id"])
    async with factory() as session:
        row = (await session.execute(text(
            "SELECT deleted_at, requirement FROM spatial_tracks "
            "WHERE id = :t"), {"t": track["id"]})).first()
    assert row[0] is not None and row[1] == "optional"
    # tombstoned track no longer owns the active coordinate
    fresh = await svc.create_track(
        fs(factory), world["id"], entity_id=mov_eid, requirement="required")
    assert fresh["id"] != track["id"]
    # idempotent delete
    await svc.delete_track(fs(factory), track["id"])


async def test_track_list_canonical_order(factory):
    pid, loc_eid, rid, mov_eid, world, track = \
        await _make_world_with_track(factory)
    more = [str(uuid.uuid4()) for _ in range(3)]
    async with factory() as session:
        async with session.begin():
            for e in more:
                await session.execute(text(
                    "INSERT INTO creative_entities (id, project_id, kind,"
                    " name, created_at, updated_at) VALUES (:e, :p, 'prop',"
                    " 'X', 't','t')"), {"e": e, "p": pid})
    for e in more:
        await svc.create_track(fs(factory), world["id"], entity_id=e,
                               requirement="optional")
    listed = await svc.list_tracks(fs(factory), world["id"])
    assert [t["entity_id"] for t in listed] == \
        sorted([mov_eid] + more)


async def test_track_api_transport_and_workspace_projection(client):
    r = await client.post("/projects", json={"name": "P"})
    pid = r.json()["id"]
    er = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "location", "name": "L"})
    loc = er.json()["id"]
    mr = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "character", "name": "Eva"})
    mov = mr.json()["id"]
    wr = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "lobby", "name": "Lobby", "requirement": "optional",
        "location_entity_id": loc})
    world_id = wr.json()["id"]
    # undeclared field rejected (matrix 62, transport strictness)
    bad = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mov, "requirement": "optional", "note": "x"})
    assert bad.status_code == 422
    # valid create
    tr = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mov, "requirement": "required"})
    assert tr.status_code == 201, tr.text
    track_id = tr.json()["id"]
    # duplicate through the API surface
    dup = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mov, "requirement": "optional"})
    assert dup.status_code == 409
    assert dup.json()["error_code"] == \
        "SPATIAL_ENTITY_INSTANCING_UNSUPPORTED"
    # requirement PATCH
    pr = await client.patch(f"/spatial-tracks/{track_id}",
                            json={"requirement": "optional"})
    assert pr.status_code == 204
    # required-delete policy through API
    pr2 = await client.patch(f"/spatial-tracks/{track_id}",
                             json={"requirement": "required"})
    dr = await client.delete(f"/spatial-tracks/{track_id}")
    assert dr.status_code == 409
    await client.patch(f"/spatial-tracks/{track_id}",
                       json={"requirement": "optional"})
    dr2 = await client.delete(f"/spatial-tracks/{track_id}")
    assert dr2.status_code == 204
    # workspace exposes the track list (active only, entity order)
    tr2 = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mov, "requirement": "optional"})
    ws = await client.get(f"/spatial-worlds/{world_id}/workspace")
    assert ws.status_code == 200
    body = ws.json()
    assert [t["entity_id"] for t in body["tracks"]] == [mov]
    assert body["tracks"][0]["requirement"] == "optional"
