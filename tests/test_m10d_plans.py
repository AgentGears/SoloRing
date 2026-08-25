"""M10D-1 tests — ShotSpatialPlan authority, CAS, ownership, and the
in-place parser evolution (matrix 1-36, 118-119, 138-140).

Covers: exact PUT/DELETE CAS table; write-time ownership (active
same-Project world with Location dependency; active in-world blocking
Tracks of current dependencies; in-world axis); recursive transport
strictness; camera optics/keyframe rules; canonical byte identity under
key-order/whitespace/blocking-order differences; wrap-equivalent
rotation convergence (+180° == -180°) in returned plan bytes AND pack
bytes; explicit-null axis canonical absence; plan-specific durable
error identity with SchemaInvalid catch compatibility.
"""
import json
import uuid

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from soloring.spatial import plans as svc
from soloring.spatial import worlds as world_svc
from soloring.spatial.schemas import (
    _COORDINATE_SYSTEM,
    SchemaInvalid,
    parse_continuity_pack,
    parse_shot_plan,
    parse_world_revision,
    plan_hash,
    world_revision_hash,
)


def fs(factory):
    return factory()


CAM = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [0, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]},
    }],
}


def plan_doc(world_id, *, cam=None, blocking=(), axis=None):
    return {
        "schema_version": 1,
        "spatial_world_id": world_id,
        "camera": cam or json.loads(json.dumps(CAM)),
        "blocking": [json.loads(json.dumps(b)) for b in blocking],
        "axis_constraint": axis,
    }


async def _seed(factory, *, with_character_dep=True, duration_ms=5000):
    pid, loc, locrev, eva, evarev = (str(uuid.uuid4()) for _ in range(5))
    shot = str(uuid.uuid4())
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
                {"r": locrev, "e": loc, "h": "ab" * 32})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'character', 'E',"
                " 't','t')"), {"e": eva, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:r, :e, 1, 1, :h, 't')"),
                {"r": evarev, "e": eva, "h": "cd" * 32})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject, "
                "duration_ms) VALUES (:s, :p, 1, 'shot', :d)"),
                {"s": shot, "p": pid, "d": duration_ms})
            await session.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
                "role, position) VALUES (:s, :e, 'location', 0)"),
                {"s": shot, "e": loc})
            if with_character_dep:
                await session.execute(text(
                    "INSERT INTO shot_entity_dependencies (shot_id, "
                    "entity_id, role, position) VALUES (:s, :e, 'cast', 1)"),
                    {"s": shot, "e": eva})
    world = await world_svc.create_world(
        fs(factory), pid, key="lobby", name="Lobby", description=None,
        requirement="required", location_entity_id=loc)
    return {"pid": pid, "loc": loc, "locrev": locrev, "eva": eva,
            "evarev": evarev, "shot": shot, "world": world}


# ------------------------------------------------------------------ CAS

async def test_plan_cas_lifecycle_full_table(factory):
    # matrix 1-11
    seed = await _seed(factory)
    wid = seed["world"]["id"]
    shot = seed["shot"]

    # 1: create with null expectation
    r1 = await svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=None,
        plan_raw=plan_doc(wid))
    assert r1["created"] is True and len(r1["plan_hash"]) == 64
    h1 = r1["plan_hash"]

    # 2: create over existing conflicts
    with pytest.raises(SoloRingError) as e2:
        await svc.put_spatial_plan(fs(factory), shot, expected_plan_hash=None,
                                   plan_raw=plan_doc(wid))
    assert e2.value.status_code == 409

    # 6: canonically identical candidate no-ops
    same = json.loads(json.dumps(plan_doc(wid)))
    same["camera"]["keyframes"][0]["transform"]["rotation_udeg"] = \
        [360000000, 0, 0]  # wraps to 0 — same canonical value
    r6 = await svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=h1, plan_raw=same)
    assert r6["created"] is False and r6["plan_hash"] == h1

    # 3: exact-hash update succeeds
    changed = plan_doc(wid)
    changed["camera"]["focal_length_um"] = 60000
    r3 = await svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=h1, plan_raw=changed)
    h2 = r3["plan_hash"]
    assert h2 != h1 and r3["created"] is True

    # 4: stale hash conflicts
    with pytest.raises(SoloRingError) as e4:
        await svc.put_spatial_plan(fs(factory), shot, expected_plan_hash=h1,
                                   plan_raw=changed)
    assert e4.value.status_code == 409
    # 5: null expectation on existing conflicts
    with pytest.raises(SoloRingError):
        await svc.put_spatial_plan(fs(factory), shot, expected_plan_hash=None,
                                   plan_raw=changed)

    # 8/9: DELETE CAS
    with pytest.raises(SoloRingError):
        await svc.delete_spatial_plan(fs(factory), shot,
                                      expected_plan_hash=None)
    with pytest.raises(SoloRingError):
        await svc.delete_spatial_plan(fs(factory), shot,
                                      expected_plan_hash=h1)  # stale
    await svc.delete_spatial_plan(fs(factory), shot, expected_plan_hash=h2)

    # 10/11: nonexistent row
    await svc.delete_spatial_plan(fs(factory), shot, expected_plan_hash=None)
    with pytest.raises(SoloRingError) as e11:
        await svc.delete_spatial_plan(fs(factory), shot,
                                      expected_plan_hash="x" * 64)
    assert e11.value.status_code == 409


# ----------------------------------------------------------- ownership

async def test_plan_ownership_validation(factory):
    # matrix 16-21
    from soloring.spatial import tracks as track_svc

    seed = await _seed(factory)
    wid = seed["world"]["id"]
    shot = seed["shot"]

    # 16: cross-Project world
    other = await _seed(factory)
    with pytest.raises(SoloRingError, match="another Project"):
        await svc.put_spatial_plan(
            fs(factory), shot, expected_plan_hash=None,
            plan_raw=plan_doc(other["world"]["id"]))

    # 17: Location not a current dependency (same Project, different
    # Location Entity that the Shot does not depend on)
    loc2 = str(uuid.uuid4())
    shot2 = str(uuid.uuid4())
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e, :p, 'location', 'L2',"
                " 't','t')"), {"e": loc2, "p": seed["pid"]})
            await session.execute(text(
                "INSERT INTO shots (id, project_id, shot_number, subject) "
                "VALUES (:s, :p, 2, 'x')"),
                {"s": shot2, "p": seed["pid"]})
            await session.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
                "role, position) VALUES (:s, :e, 'cast', 0)"),
                {"s": shot2, "e": seed["eva"]})
    w2 = await world_svc.create_world(
        fs(factory), seed["pid"], key="other", name="O", description=None,
        requirement="optional", location_entity_id=loc2)
    # w2's Location (loc2) is not a dependency of `shot`
    with pytest.raises(SoloRingError, match="not a current semantic"):
        await svc.put_spatial_plan(
            fs(factory), shot, expected_plan_hash=None,
            plan_raw=plan_doc(w2["id"]))

    # 18-20: blocking track tombstoned / wrong world / entity not dep
    track = await track_svc.create_track(
        fs(factory), wid, entity_id=seed["eva"], requirement="optional")
    blocking = [{
        "spatial_track_id": track["id"],
        "screen_direction": "left_to_right",
        "keyframes": [{
            "time_ms": 0,
            "transform": {"translation_mm": [0, 0, 0],
                          "rotation_udeg": [0, 0, 0]}}],
    }]
    # wrong-world track (belongs to w2)
    track_w2 = await track_svc.create_track(
        fs(factory), w2["id"], entity_id=seed["eva"],
        requirement="optional")
    with pytest.raises(SoloRingError, match="different SpatialWorld"):
        await svc.put_spatial_plan(
            fs(factory), shot, expected_plan_hash=None,
            plan_raw=plan_doc(wid, blocking=[{
                "spatial_track_id": track_w2["id"],
                "screen_direction": "unspecified",
                "keyframes": blocking[0]["keyframes"]}]))
    # entity not a dependency (no character dep variant)
    seed2 = await _seed(factory, with_character_dep=False)
    track2 = await track_svc.create_track(
        fs(factory), seed2["world"]["id"], entity_id=seed2["eva"],
        requirement="optional")
    with pytest.raises(SoloRingError, match="not a current semantic"):
        await svc.put_spatial_plan(
            fs(factory), seed2["shot"], expected_plan_hash=None,
            plan_raw=plan_doc(seed2["world"]["id"], blocking=[{
                "spatial_track_id": track2["id"],
                "screen_direction": "unspecified",
                "keyframes": blocking[0]["keyframes"]}]))
    # tombstoned track
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "UPDATE spatial_tracks SET deleted_at = 't' "
                "WHERE id = :t"), {"t": track2["id"]})
    with pytest.raises(SoloRingError, match="missing or deleted"):
        await svc.put_spatial_plan(
            fs(factory), seed2["shot"], expected_plan_hash=None,
            plan_raw=plan_doc(seed2["world"]["id"], blocking=[{
                "spatial_track_id": track2["id"],
                "screen_direction": "unspecified",
                "keyframes": blocking[0]["keyframes"]}]))

    # 21: axis wrong world
    axis_w2 = await world_svc.create_axis(
        fs(factory), w2["id"], key="a2", name="A2")
    with pytest.raises(SoloRingError, match="different SpatialWorld"):
        await svc.put_spatial_plan(
            fs(factory), shot, expected_plan_hash=None,
            plan_raw=plan_doc(wid, axis={
                "spatial_axis_id": axis_w2["id"],
                "camera_side": "positive"}))
    # active in-world axis + valid blocking passes
    axis_ok = await world_svc.create_axis(
        fs(factory), wid, key="a1", name="A1")
    ok = await svc.put_spatial_plan(
        fs(factory), shot, expected_plan_hash=None,
        plan_raw=plan_doc(wid, blocking=[{
            "spatial_track_id": track["id"],
            "screen_direction": "stationary",
            "keyframes": blocking[0]["keyframes"]}],
            axis={"spatial_axis_id": axis_ok["id"],
                  "camera_side": "positive"}))
    assert ok["created"] is True


async def test_plan_api_transport_strictness(client, factory):
    # matrix 12-15 at the transport layer
    seed = await _seed(factory)
    wid = seed["world"]["id"]
    base = plan_doc(wid)

    bad_top = {"expected_plan_hash": None, "plan": base, "note": "x"}
    r = await client.put(f"/shots/{seed['shot']}/spatial-plan",
                         json=bad_top)
    assert r.status_code == 422
    bad_cam = json.loads(json.dumps(base))
    bad_cam["camera"]["focus_distance_um"] = 100
    r2 = await client.put(
        f"/shots/{seed['shot']}/spatial-plan",
        json={"expected_plan_hash": None, "plan": bad_cam})
    assert r2.status_code == 422
    bad_blk = json.loads(json.dumps(base))
    bad_blk["blocking"] = [{
        "spatial_track_id": "t", "screen_direction": "unspecified",
        "keyframes": [{"time_ms": 0, "transform": {
            "translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]}}],
        "easing": "linear"}]
    r3 = await client.put(
        f"/shots/{seed['shot']}/spatial-plan",
        json={"expected_plan_hash": None, "plan": bad_blk})
    assert r3.status_code == 422
    bad_ver = json.loads(json.dumps(base))
    bad_ver["schema_version"] = 2
    r4 = await client.put(
        f"/shots/{seed['shot']}/spatial-plan",
        json={"expected_plan_hash": None, "plan": bad_ver})
    assert r4.status_code == 422
    assert r4.json()["error_code"] == "SPATIAL_SHOT_PLAN_INVALID"

    # valid PUT through the API + GET projection
    ok = await client.put(f"/shots/{seed['shot']}/spatial-plan",
                          json={"expected_plan_hash": None, "plan": base})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["plan"]["axis_constraint"] is None
    got = await client.get(f"/shots/{seed['shot']}/spatial-plan")
    assert got.json()["plan_hash"] == body["plan_hash"]
    dr = await client.request(
        "DELETE", f"/shots/{seed['shot']}/spatial-plan",
        json={"expected_plan_hash": body["plan_hash"]})
    assert dr.status_code == 204


# ------------------------------------------------- pure parser authority

def _plan(**overrides):
    doc = plan_doc("w-parser")
    doc.update(overrides)
    return doc


def test_parser_camera_rules_and_normalization():
    # matrix 23-34
    assert parse_shot_plan(_plan(), duration_ms=1000)["camera"][
        "projection"] == "perspective"
    with pytest.raises(SchemaInvalid, match="perspective"):
        parse_shot_plan(_plan(camera={**CAM, "projection": "ortho"}),
                        duration_ms=1000)
    with pytest.raises(SchemaInvalid, match="optics"):
        parse_shot_plan(_plan(camera={**CAM, "focal_length_um": 0}),
                        duration_ms=1000)
    with pytest.raises(SchemaInvalid, match="optics"):
        parse_shot_plan(_plan(camera={**CAM, "sensor_width_um": -1}),
                        duration_ms=1000)
    kf_late = {"time_ms": 500, "transform": CAM["keyframes"][0]
               ["transform"]}
    with pytest.raises(SchemaInvalid, match="first keyframe"):
        parse_shot_plan(_plan(camera={**CAM, "keyframes": [kf_late]}),
                        duration_ms=1000)
    kf_dup = {"time_ms": 0, "transform": CAM["keyframes"][0]
              ["transform"]}
    with pytest.raises(SchemaInvalid, match="strictly increasing"):
        parse_shot_plan(_plan(camera={**CAM,
                                     "keyframes": [kf_dup,
                                                   dict(kf_dup)]}),
                        duration_ms=1000)
    kf_over = {"time_ms": 2000, "transform": CAM["keyframes"][0]
               ["transform"]}
    with pytest.raises(SchemaInvalid, match="duration"):
        parse_shot_plan(_plan(camera={**CAM, "keyframes": [
            CAM["keyframes"][0], kf_over]}), duration_ms=1000)
    # NULL duration: only t=0
    with pytest.raises(SchemaInvalid, match="NULL"):
        parse_shot_plan(_plan(camera={**CAM, "keyframes": [
            CAM["keyframes"][0], kf_over]}), duration_ms=None)
    # JS-safe bounds
    big = {"time_ms": 0, "transform": {
        "translation_mm": [2 ** 53, 0, 0], "rotation_udeg": [0, 0, 0]}}
    with pytest.raises(SchemaInvalid, match="JavaScript-safe"):
        parse_shot_plan(_plan(camera={**CAM, "keyframes": [big]}),
                        duration_ms=1000)
    # 34 + 138: normalization is RETURNED (+180 -> -180, byte convergence)
    wrapped = {"time_ms": 0, "transform": {
        "translation_mm": [0, 0, 0], "rotation_udeg": [180000000, 0, 0]}}
    canonical_wrapped = {"time_ms": 0, "transform": {
        "translation_mm": [0, 0, 0], "rotation_udeg": [-180000000, 0, 0]}}
    a = parse_shot_plan(_plan(camera={**CAM, "keyframes": [wrapped]}),
                        duration_ms=1000)
    b = parse_shot_plan(_plan(camera={**CAM,
                                     "keyframes": [canonical_wrapped]}),
                        duration_ms=1000)
    assert a["camera"]["keyframes"][0]["transform"]["rotation_udeg"][0] \
        == -180000000
    assert plan_hash(a) == plan_hash(b)  # identical canonical bytes


def test_parser_canonical_byte_identity():
    # matrix 35, 36, 118, 119, 15-det-17
    t0 = {"time_ms": 0, "transform": {"translation_mm": [1, 2, 3],
                                      "rotation_udeg": [0, 0, 0]}}
    t1 = {"time_ms": 100, "transform": {"translation_mm": [4, 5, 6],
                                        "rotation_udeg": [7000000, 0, 0]}}
    cam = {"projection": "perspective", "focal_length_um": 50000,
           "sensor_width_um": 36000, "sensor_height_um": 20250,
           "keyframes": [t0, t1]}
    entry = {"spatial_track_id": "track-b",
             "screen_direction": "left_to_right",
             "keyframes": [dict(t0)]}
    entry2 = {"spatial_track_id": "track-a",
              "screen_direction": "unspecified",
              "keyframes": [dict(t0)]}
    base = parse_shot_plan(plan_doc("w1", cam=cam,
                                    blocking=[entry2, entry]),
                           duration_ms=1000)
    # different key order + whitespace + blocking order → identical bytes
    shuffled = json.loads(json.dumps({
        "axis_constraint": None,
        "blocking": [entry, entry2],
        "camera": cam,
        "schema_version": 1,
        "spatial_world_id": "w1"}))
    other = parse_shot_plan(shuffled, duration_ms=1000)
    assert plan_hash(base) == plan_hash(other)
    # canonical blocking order is track-id ascending
    assert [b["spatial_track_id"] for b in other["blocking"]] == \
        ["track-a", "track-b"]
    # 118: explicit-null axis stays present-null; omission rejected
    assert "axis_constraint" in other and \
        other["axis_constraint"] is None
    omitted = {k: v for k, v in shuffled.items()
               if k != "axis_constraint"}
    with pytest.raises(SchemaInvalid, match="missing required fields"):
        parse_shot_plan(omitted, duration_ms=1000)
    # 119: empty blocking is canonical []; missing screen_direction fails
    empty_blk = parse_shot_plan(plan_doc("w1", cam=cam, blocking=[]),
                                duration_ms=1000)
    assert empty_blk["blocking"] == []
    no_dir = {"spatial_track_id": "t", "keyframes": [dict(t0)]}
    with pytest.raises(SchemaInvalid, match="screen_direction"):
        parse_shot_plan(plan_doc("w1", cam=cam, blocking=[no_dir]),
                        duration_ms=1000)


def test_parser_error_identity_and_catch_compatibility():
    # matrix 140
    from soloring.errors import ErrorCode
    with pytest.raises(SchemaInvalid) as ei:
        parse_shot_plan(plan_doc("w1", cam={**CAM, "projection": "x"}),
                        duration_ms=1000)
    assert isinstance(ei.value, SchemaInvalid)  # catch-compat holds
    assert ei.value.code == ErrorCode.SPATIAL_SHOT_PLAN_INVALID
    # world grammar identity unchanged
    with pytest.raises(SchemaInvalid) as ew:
        parse_world_revision({"schema_version": 2})
    assert ew.value.code == ErrorCode.SPATIAL_WORLD_INVALID


def _pack_raw(plan_raw):
    snap = parse_world_revision({
        "schema_version": 1,
        "spatial_world_id": "w1",
        "location_entity_id": "l1",
        "location_entity_revision_id": "r1",
        "coordinate_system": dict(_COORDINATE_SYSTEM),
        "frames": [], "axes": []})
    return {
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": "w1", "requirement": "required",
            "spatial_world_state_id": "st1",
            "spatial_world_revision_id": "rev1",
            "spatial_world_revision_hash": world_revision_hash(snap),
            "location_entity_id": "l1",
            "location_entity_revision_id": "r1",
            "world_snapshot": snap,
        },
        "staging": [],
        "shot_plan": plan_raw,
    }


def test_pack_parser_embeds_normalized_plan():
    # matrix 139: unnormalized caller rotations cannot survive the pack
    wrapped = json.loads(json.dumps(CAM))
    wrapped["keyframes"][0]["transform"]["rotation_udeg"] = \
        [180000000, 0, 0]
    raw = _pack_raw(plan_doc("w1", cam=wrapped))
    out = parse_continuity_pack(raw)
    assert out["shot_plan"]["camera"]["keyframes"][0]["transform"][
        "rotation_udeg"][0] == -180000000
    # and hash identity with the pre-normalized equivalent
    pre = _pack_raw(parse_shot_plan(plan_doc("w1", cam=wrapped),
                                    duration_ms=1000))
    assert parse_continuity_pack(pre)["shot_plan"] == out["shot_plan"]
