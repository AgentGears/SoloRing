"""M10C-2 tests — SpatialTransition authority (M10C plan §7; matrix 14-30).

All six anchor-boundary set classes, clear, aggregate set|clear contract,
numeric normalization, anchor validation through the canonical M7
authority (cross-Project/tombstoned/unassigned rejected), coordinate
conflicts, prospective PATCH semantics (omitted/explicit-null), and
tombstone/recreate identity.
"""
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import transitions as svc
from soloring.spatial import tracks as track_svc
from soloring.spatial import worlds as world_svc

T = [100, 200, -300]
R = [40000000, -5000000, 600000]


def fs(factory):
    return factory()


async def _seed_narrative(factory, *, shots_in_scene=2):
    """Project + location Entity/rev + movable Entity + Sequence/Scene/
    assigned Shots. Returns ids dict."""
    pid, loc, rid, mov, seq, scene = (str(uuid.uuid4()) for _ in range(6))
    shot_ids = [str(uuid.uuid4()) for _ in range(shots_in_scene)]
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
            await session.execute(text(
                "INSERT INTO scenes (id, sequence_id, position, title) "
                "VALUES (:c, :s, 0, 'C')"), {"c": scene, "s": seq})
            for i, sh in enumerate(shot_ids):
                await session.execute(text(
                    "INSERT INTO shots (id, project_id, shot_number, "
                    "subject, scene_id, scene_position) VALUES "
                    "(:i, :p, :n, 'shot', :c, :pos)"),
                    {"i": sh, "p": pid, "n": i + 1, "c": scene, "pos": i})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="optional", location_entity_id=loc)
    track = await track_svc.create_track(
        fs(factory), world["id"], entity_id=mov, requirement="optional")
    return {"pid": pid, "loc": loc, "mov": mov, "seq": seq, "scene": scene,
            "shots": shot_ids, "world": world, "track": track}


async def _mk_transition(factory, seed, *, anchor_type, anchor_id, boundary,
                         operation="set", t=None, r=None, track_id=None):
    tm = t if t is not None else (T if operation == "set" else None)
    rm = r if r is not None else (R if operation == "set" else None)
    return await svc.create_transition(
        fs(factory), track_id or seed["track"]["id"],
        anchor_type=anchor_type, anchor_id=anchor_id, boundary=boundary,
        operation=operation, translation_mm=tm, rotation_udeg=rm)


# ------------------------------------------------------------ creation

async def test_transition_set_all_six_anchor_boundary_classes(factory):
    # matrix 14-19
    seed = await _seed_narrative(factory)
    cases = [
        ("sequence", seed["seq"], "start"),
        ("sequence", seed["seq"], "end"),
        ("scene", seed["scene"], "start"),
        ("scene", seed["scene"], "end"),
        ("shot", seed["shots"][0], "start"),
        ("shot", seed["shots"][0], "end"),
    ]
    for at, aid, b in cases:
        tr = await _mk_transition(factory, seed, anchor_type=at,
                                  anchor_id=aid, boundary=b)
        got = await svc.get_transition(fs(factory), tr["id"])
        assert got["operation"] == "set"
        assert (got["x_mm"], got["y_mm"], got["z_mm"]) == tuple(T)
        assert (got["yaw_udeg"], got["pitch_udeg"], got["roll_udeg"]) == \
            tuple(R)
    listed = await svc.list_transitions(fs(factory),
                                        seed["track"]["id"])
    assert len(listed) == 6


async def test_transition_clear_on_legal_boundary(factory):
    # matrix 20
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="sequence",
                              anchor_id=seed["seq"], boundary="start",
                              operation="clear")
    got = await svc.get_transition(fs(factory), tr["id"])
    assert got["operation"] == "clear"
    assert all(got[k] is None for k in
               ("x_mm", "y_mm", "z_mm", "yaw_udeg", "pitch_udeg",
                "roll_udeg"))


async def test_transition_numeric_contract_normalizes(factory):
    seed = await _seed_narrative(factory)
    # +180° canonicalizes to -180°; values normalize into the half-open
    # domain independently
    tr = await _mk_transition(factory, seed, anchor_type="scene",
                              anchor_id=seed["scene"], boundary="start",
                              t=[0, 0, 0], r=[180000000, 360000000, -0])
    got = await svc.get_transition(fs(factory), tr["id"])
    assert got["yaw_udeg"] == -180000000
    assert got["pitch_udeg"] == 0  # 360° → 0 inside [-180°, +180°)
    assert got["roll_udeg"] == 0
    # floats rejected
    with pytest.raises(SoloRingError, match="int"):
        await _mk_transition(factory, seed, anchor_type="scene",
                             anchor_id=seed["scene"], boundary="end",
                             t=[0.5, 0, 0])
    # JS-safe bounds rejected
    with pytest.raises(SoloRingError, match="JavaScript-safe"):
        await _mk_transition(factory, seed, anchor_type="scene",
                             anchor_id=seed["scene"], boundary="end",
                             t=[2 ** 53, 0, 0])


async def test_transition_incomplete_set_and_clear_with_transform(factory):
    # matrix 24, 25
    seed = await _seed_narrative(factory)
    with pytest.raises(SoloRingError, match="complete transform"):
        await svc.create_transition(
            fs(factory), seed["track"]["id"], anchor_type="sequence",
            anchor_id=seed["seq"], boundary="start", operation="set",
            translation_mm=None, rotation_udeg=R)
    with pytest.raises(SoloRingError, match="no transform"):
        await _mk_transition(factory, seed, anchor_type="sequence",
                             anchor_id=seed["seq"], boundary="start",
                             operation="clear", t=T)
    # bad vector arity
    with pytest.raises(SoloRingError, match="3-vector"):
        await svc.create_transition(
            fs(factory), seed["track"]["id"], anchor_type="sequence",
            anchor_id=seed["seq"], boundary="start", operation="set",
            translation_mm=[1, 2], rotation_udeg=R)


async def test_transition_cross_project_and_bad_anchors_rejected(factory):
    # matrix 21, 22
    seed = await _seed_narrative(factory)
    other_pid, other_seq, unassigned = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'Q', 't', 't')"), {"p": other_pid})
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'X')"),
                {"s": other_seq, "p": other_pid})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:u, :p, 99, 'unassigned')"),
                {"u": unassigned, "p": seed["pid"]})
    # cross-project anchor
    with pytest.raises(SoloRingError) as ei:
        await _mk_transition(factory, seed, anchor_type="sequence",
                             anchor_id=other_seq, boundary="start")
    assert ei.value.code == ErrorCode.SPATIAL_TRANSITION_INVALID
    assert "another Project" in ei.value.message
    # unassigned shot anchor has no narrative boundary
    with pytest.raises(SoloRingError, match="unassigned"):
        await _mk_transition(factory, seed, anchor_type="shot",
                             anchor_id=unassigned, boundary="start")
    # missing anchor
    with pytest.raises(SoloRingError, match="missing or tombstoned"):
        await _mk_transition(factory, seed, anchor_type="scene",
                             anchor_id=str(uuid.uuid4()), boundary="start")
    # tombstoned anchor
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE scenes SET deleted_at = 't' WHERE id = :c"),
                {"c": seed["scene"]})
    with pytest.raises(SoloRingError, match="tombstoned"):
        await _mk_transition(factory, seed, anchor_type="scene",
                             anchor_id=seed["scene"], boundary="start")


async def test_transition_coordinate_conflict_and_concurrent(factory):
    # matrix 23 + concurrent mutation conflict
    import asyncio
    seed = await _seed_narrative(factory)
    await _mk_transition(factory, seed, anchor_type="shot",
                         anchor_id=seed["shots"][0], boundary="start")
    with pytest.raises(SoloRingError) as ei:
        await _mk_transition(factory, seed, anchor_type="shot",
                             anchor_id=seed["shots"][0], boundary="start")
    assert ei.value.status_code == 409
    # same anchor/boundary on a DIFFERENT boundary is a free coordinate
    await _mk_transition(factory, seed, anchor_type="shot",
                         anchor_id=seed["shots"][0], boundary="end")
    # concurrent create: one winner, one conflict
    results = await asyncio.gather(
        _mk_transition(factory, seed, anchor_type="shot",
                       anchor_id=seed["shots"][1], boundary="start"),
        _mk_transition(factory, seed, anchor_type="shot",
                       anchor_id=seed["shots"][1], boundary="start"),
        return_exceptions=True)
    wins = [r for r in results if not isinstance(r, Exception)]
    losses = [r for r in results if isinstance(r, Exception)]
    assert len(wins) == 1 and len(losses) == 1
    assert losses[0].status_code == 409


async def test_transition_on_deleted_track_rejected(factory):
    seed = await _seed_narrative(factory)
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_tracks SET deleted_at = 't' WHERE id = :t"),
                {"t": seed["track"]["id"]})
    with pytest.raises(SoloRingError, match="deleted"):
        await _mk_transition(factory, seed, anchor_type="sequence",
                             anchor_id=seed["seq"], boundary="start")


# ----------------------------------------------------------------- PATCH

async def test_transition_patch_set_to_clear_and_clear_to_set(factory):
    # matrix 26, 27
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="shot",
                              anchor_id=seed["shots"][0], boundary="start")
    # set → clear (atomically all six NULL)
    await svc.patch_transition(fs(factory), tr["id"], operation="clear")
    got = await svc.get_transition(fs(factory), tr["id"])
    assert got["operation"] == "clear"
    assert all(got[k] is None for k in
               ("x_mm", "y_mm", "z_mm", "yaw_udeg", "pitch_udeg", "roll_udeg"))
    # clear → set with complete transform
    await svc.patch_transition(fs(factory), tr["id"], operation="set",
                               translation_mm=[1, 2, 3],
                               rotation_udeg=[4, 5, 6])
    got = await svc.get_transition(fs(factory), tr["id"])
    assert got["operation"] == "set" and got["x_mm"] == 1
    # clear → set WITHOUT transform rejected
    tr2 = await _mk_transition(factory, seed, anchor_type="shot",
                               anchor_id=seed["shots"][0], boundary="end",
                               operation="clear")
    with pytest.raises(SoloRingError, match="complete transform"):
        await svc.patch_transition(fs(factory), tr2["id"], operation="set")


async def test_transition_patch_partial_transform_preserves(factory):
    # matrix 28: omitted fields retain; one-vector PATCH keeps the other
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="shot",
                              anchor_id=seed["shots"][0], boundary="start")
    await svc.patch_transition(fs(factory), tr["id"],
                               translation_mm=[900, 0, 0])
    got = await svc.get_transition(fs(factory), tr["id"])
    assert (got["x_mm"], got["y_mm"], got["z_mm"]) == (900, 0, 0)
    assert (got["yaw_udeg"], got["pitch_udeg"], got["roll_udeg"]) == \
        tuple(R)  # rotation preserved
    # no-op PATCH (nothing provided) commits cleanly
    await svc.patch_transition(fs(factory), tr["id"])


async def test_transition_patch_explicit_null_unambiguous(factory):
    # matrix 29: explicit nulls are only legal where the aggregate permits
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="shot",
                              anchor_id=seed["shots"][0], boundary="start")
    # explicit null translation on a set without operation=clear →
    # prospective aggregate is illegal
    with pytest.raises(SoloRingError):
        await svc.patch_transition(fs(factory), tr["id"],
                                   translation_mm=None)
    # explicit null transform with operation=clear is exactly set→clear
    await svc.patch_transition(fs(factory), tr["id"], operation="clear",
                               translation_mm=None, rotation_udeg=None)
    got = await svc.get_transition(fs(factory), tr["id"])
    assert got["operation"] == "clear"
    # explicit null anchor fields rejected (non-nullable identity)
    with pytest.raises(SoloRingError, match="anchor_type"):
        await svc.patch_transition(fs(factory), tr["id"], anchor_type=None)


async def test_transition_patch_anchor_revalidates_coordinate(factory):
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="shot",
                              anchor_id=seed["shots"][0], boundary="start")
    other = await _mk_transition(factory, seed, anchor_type="shot",
                                 anchor_id=seed["shots"][1], boundary="start")
    # moving onto an occupied coordinate → conflict
    with pytest.raises(SoloRingError) as ei:
        await svc.patch_transition(fs(factory), tr["id"],
                                   anchor_id=seed["shots"][1])
    assert ei.value.status_code == 409
    # moving to a free legal coordinate revalidates the anchor fully
    await svc.patch_transition(fs(factory), tr["id"],
                               anchor_type="sequence",
                               anchor_id=seed["seq"], boundary="end")
    got = await svc.get_transition(fs(factory), tr["id"])
    assert (got["anchor_type"], got["boundary"]) == ("sequence", "end")
    # cross-project anchor move rejected
    other_pid, other_scene_owner = str(uuid.uuid4()), str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'Q', 't', 't')"), {"p": other_pid})
            await session.execute(text(
                "INSERT INTO sequences (id, project_id, position, title) "
                "VALUES (:s, :p, 0, 'X')"),
                {"s": other_scene_owner, "p": other_pid})
    with pytest.raises(SoloRingError, match="another Project"):
        await svc.patch_transition(fs(factory), other["id"],
                                   anchor_type="sequence",
                                   anchor_id=other_scene_owner)
    # patched onto deleted transition rejected
    await svc.delete_transition(fs(factory), other["id"])
    with pytest.raises(SoloRingError, match="deleted"):
        await svc.patch_transition(fs(factory), other["id"],
                                   operation="clear")


async def test_transition_delete_recreate_new_identity(factory):
    # matrix 30
    seed = await _seed_narrative(factory)
    tr = await _mk_transition(factory, seed, anchor_type="shot",
                              anchor_id=seed["shots"][0], boundary="start")
    await svc.delete_transition(fs(factory), tr["id"])
    fresh = await _mk_transition(factory, seed, anchor_type="shot",
                                 anchor_id=seed["shots"][0],
                                 boundary="start", t=[7, 8, 9])
    assert fresh["id"] != tr["id"]
    # old identity remains as a tombstone row, never recycled
    old = await svc.get_transition(fs(factory), tr["id"])
    assert old["deleted_at"] is not None
    # idempotent delete
    await svc.delete_transition(fs(factory), tr["id"])


async def test_transition_api_transport_and_workspace(client):
    r = await client.post("/projects", json={"name": "P"})
    pid = r.json()["id"]
    er = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "location", "name": "L"})
    mr = await client.post(f"/projects/{pid}/entities",
                           json={"kind": "character", "name": "Eva"})
    wr = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "lobby", "name": "Lobby", "requirement": "optional",
        "location_entity_id": er.json()["id"]})
    world_id = wr.json()["id"]
    tr = await client.post(f"/spatial-worlds/{world_id}/tracks", json={
        "entity_id": mr.json()["id"], "requirement": "optional"})
    track_id = tr.json()["id"]
    # narrative anchor via public API
    sr = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq_id = sr.json()["id"]
    cr = await client.post(
        f"/sequences/{seq_id}/scenes", json={"title": "C"})
    scene_id = cr.json()["id"]
    shr = await client.post(f"/projects/{pid}/shots",
                            json={"subject": "shot"})
    assert shr.status_code == 201, shr.text
    shot_id = shr.json()["id"]
    ar = await client.put(f"/scenes/{scene_id}/shots",
                          json={"shot_ids": [shot_id]})
    assert ar.status_code == 200, ar.text
    # undeclared field rejected
    bad = await client.post(f"/spatial-tracks/{track_id}/transitions",
                            json={"anchor_type": "sequence",
                                  "anchor_id": seq_id, "boundary": "start",
                                  "operation": "set",
                                  "translation_mm": [0, 0, 0],
                                  "rotation_udeg": [0, 0, 0], "x": 1})
    assert bad.status_code == 422
    # valid set
    ok = await client.post(f"/spatial-tracks/{track_id}/transitions",
                           json={"anchor_type": "sequence",
                                 "anchor_id": seq_id, "boundary": "start",
                                 "operation": "set",
                                 "translation_mm": [0, 1650, 4200],
                                 "rotation_udeg": [0, 0, 0]})
    assert ok.status_code == 201, ok.text
    tid = ok.json()["id"]
    # conflict through API
    dup = await client.post(f"/spatial-tracks/{track_id}/transitions",
                            json={"anchor_type": "sequence",
                                  "anchor_id": seq_id, "boundary": "start",
                                  "operation": "clear"})
    assert dup.status_code == 409
    assert dup.json()["error_code"] == "SPATIAL_TRANSITION_INVALID"
    # PATCH clear via API
    pr = await client.patch(f"/spatial-transitions/{tid}",
                            json={"operation": "clear"})
    assert pr.status_code == 204
    # DELETE via API
    dr = await client.delete(f"/spatial-transitions/{tid}")
    assert dr.status_code == 204
    # workspace carries per-track transitions
    ok2 = await client.post(f"/spatial-tracks/{track_id}/transitions",
                            json={"anchor_type": "shot",
                                  "anchor_id": shot_id, "boundary": "start",
                                  "operation": "set",
                                  "translation_mm": [1, 2, 3],
                                  "rotation_udeg": [4, 5, 6]})
    ws = await client.get(f"/spatial-worlds/{world_id}/workspace")
    body = ws.json()
    assert body["tracks"][0]["transitions"][0]["id"] == ok2.json()["id"]
    assert body["tracks"][0]["transitions"][0]["anchor_type"] == "shot"
