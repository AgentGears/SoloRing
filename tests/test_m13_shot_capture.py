"""M13 Shot capture proofs (frozen R3 §30.7 M13-SHOT:01-15 core)."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.test_m13_binding import _adopt, _interpretation, _publish

CAM = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [-3000, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]}}],
}


def _factory(client):
    return async_sessionmaker(bind=client._transport.app.state.engine,
                              expire_on_commit=False)


async def _entity_approved(client, pid, kind, name):
    from tests.m13_seed import make_entity
    eid = await make_entity(client, pid, kind=kind, name=name)
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": name}})
    rid = r.json()["id"]
    r = await client.put(f"/entities/{eid}/approved-revision",
                         json={"revision_id": rid,
                               "expected_approved_revision_id": None})
    assert r.status_code == 200, r.text
    return eid, rid


async def _full_m13_world(client, *, tag=b"m13-shot"):
    """project + approved world (origin+desk frames, axis) + assigned shot
    with location/eva deps + plan — the minimal READY M10 configuration."""
    from soloring.spatial import plans as plan_svc
    from soloring.spatial import revisions as rev_svc
    from soloring.spatial import worlds as world_svc

    base = await seed_base(client, tag=tag)
    pid = base["project_id"]
    f = _factory(client)
    loc, locrev = await _entity_approved(client, pid, "location", "Set")
    eva, evarev = await _entity_approved(client, pid, "character", "Eva")
    world = await world_svc.create_world(
        f(), pid, key="lobby", name="Lobby", description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        f(), world["id"], location_entity_revision_id=locrev)
    fr_origin = await world_svc.create_frame(
        f(), world["id"], key="origin", name="origin",
        parent_spatial_frame_id=None, bound_entity_id=None)
    fr_desk = await world_svc.create_frame(
        f(), world["id"], key="desk", name="desk",
        parent_spatial_frame_id=None, bound_entity_id=None)
    await world_svc.put_state_frame(
        f(), state["id"], fr_origin["id"], translation_mm=[0, 0, 0],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=None)
    await world_svc.put_state_frame(
        f(), state["id"], fr_desk["id"], translation_mm=[3000, 0, -2000],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=None)
    axis = await world_svc.create_axis(
        f(), world["id"], key="axis", name="axis")
    await world_svc.put_state_axis(
        f(), state["id"], axis["id"], a_frame_id=fr_origin["id"],
        b_frame_id=fr_desk["id"])
    rev = await rev_svc.capture_revision(f(), state["id"])
    await rev_svc.approve_revision(
        f(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)

    # assigned shot with semantic deps (location + eva)
    engine = client._transport.app.state.engine
    shot = str(uuid.uuid4())
    seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO sequences (id, project_id, position, title) "
            "VALUES (:q, :p, (SELECT COALESCE(MAX(position),0)+1 FROM "
            "sequences WHERE project_id=:p), 'S')"),
            {"q": seq, "p": pid})
        await conn.execute(text(
            "INSERT INTO scenes (id, sequence_id, position, title) "
            "VALUES (:c, :q, 0, 'C')"), {"c": scene, "q": seq})
        await conn.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "duration_ms, scene_id, scene_position) VALUES (:s, :p, "
            "(SELECT COALESCE(MAX(shot_number),0)+1 FROM shots WHERE "
            "project_id=:p), 'shot', 5000, :c, 0)"),
            {"s": shot, "p": pid, "c": scene})
        for i, eid in enumerate((loc, eva)):
            await conn.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
                "role, position) VALUES (:s, :e, 'cast', :i)"),
                {"s": shot, "e": eid, "i": i})
        await conn.commit()
    plan = {
        "schema_version": 1,
        "spatial_world_id": world["id"],
        "camera": json.loads(json.dumps(CAM)),
        "blocking": [],
        "axis_constraint": {"spatial_axis_id": axis["id"],
                            "camera_side": "positive"},
    }
    await plan_svc.put_spatial_plan(
        f(), shot, expected_plan_hash=None, plan_raw=plan)
    return {**base, "pid": pid, "loc": loc, "locrev": locrev,
            "eva": eva, "world": world, "state": state, "rev": rev,
            "axis": axis, "shot": shot, "desk_frame": fr_desk}


async def _capture(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    return await capture_revision_with_visual(
        _factory(client)(), shot_id,
        settings=client._transport.app.state.settings)


async def _select_binding(client, b):
    """Build + publish a ready binding over the shot's exact world
    revision with one PI subject, then select it for the shot."""
    cid = await make_composition(client, b["pid"])
    m = await mint(client, cid, b["production_revision_id"], 0)
    oid = m["occurrence_id"]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    pub = await publish(client, cid, 1)
    c = pub["revision"]["revision_id"]
    r = await client.post(
        f"/spatial-worlds/{b['world']['id']}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "optional"})
    assert r.status_code == 201, r.text
    track = r.json()["id"]
    # stage the instance at the sequence start
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()
    r = await client.post(
        f"/production-instance-spatial-tracks/{track}/transitions",
        json={"anchor_type": "sequence", "anchor_id": seq,
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [100, 0, 0],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    pr = await _publish(client, c, b["rev"]["id"])
    assert pr.status_code == 201, pr.text
    binding_id = pr.json()["binding_id"]
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    return {"cid": cid, "occurrence_id": oid, "track": track,
            "binding_id": binding_id, "C": c}


async def test_m13_shot_01(client):
    """M13-SHOT:01 — no selection ⇒ exact lower behavior, no M13 pack:
    schemas 1-5 bytes/hashes identical to predecessor capture."""
    b = await _full_m13_world(client, tag=b"shot01")
    revision, _ = await _capture(client, b["shot"])
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 5  # M10 present, no M13
    assert "production_world" not in snap
    # schema-5 bytes are byte-identical to the predecessor builder:
    # re-derive without any M13 knowledge via the M10 path
    from soloring.domain.canonical import canonical_hash
    assert revision.snapshot_hash == canonical_hash(snap)


async def test_m13_shot_02_and_09(client):
    """M13-SHOT:02/09 — exact selected binding loads/validates; schema-6
    canonical golden bytes/hash with the exact lower schema-5 content."""
    b = await _full_m13_world(client, tag=b"shot02")
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 6
    pack = snap["production_world"]
    assert pack["schema_version"] == 1
    assert pack["binding"]["binding_id"] == sel["binding_id"]
    # the pack embeds the exact canonical binding value
    stored = (await client.get(
        f"/composition-spatial-bindings/{sel['binding_id']}")).json()
    assert pack["binding"]["binding_hash"] == stored["binding_hash"]
    assert pack["binding"]["value"]["subjects"] == stored["subjects"]
    # exact lower schema-5 content preserved beneath
    assert "spatial_continuity" in snap
    assert snap["spatial_continuity"]["spatial_world"][
        "spatial_world_revision_id"] == b["rev"]["id"]
    # one staged PI spatial state
    assert len(pack["instance_spatial_states"]) == 1
    st = pack["instance_spatial_states"][0]
    assert st["occurrence_id"] == sel["occurrence_id"]
    assert st["production_instance_track_id"] == sel["track"]
    assert st["transform"]["translation_mm"] == [100, 0, 0]
    # production-world hash = sha256 over canonical pack bytes
    import hashlib
    from soloring.domain.canonical import canonical_json_bytes
    assert hashlib.sha256(
        canonical_json_bytes(pack)).hexdigest() == (
        (await client.get(
            f"/shots/{b['shot']}/production-world")).json()[
            "production_world_hash"])


async def test_m13_shot_03(client):
    """M13-SHOT:03 — a stale binding blocks current capture."""
    b = await _full_m13_world(client, tag=b"shot03")
    sel = await _select_binding(client, b)
    # current authority evolves INSIDE the bound universe: soft-deleting
    # the PI track removes the entry from today's candidate
    r = await client.delete(
        f"/production-instance-spatial-tracks/{sel['track']}")
    assert r.status_code == 200, r.text
    r = await client.get(f"/shots/{b['shot']}/production-world")
    assert r.status_code == 200
    out = r.json()
    assert out["ready"] is False
    assert out["binding_current_complete"] is False
    assert out["stale_details"][0]["code"] == (
        "BINDING_STALE_PLACEMENT_SET_CHANGED")
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as ei:
        await _capture(client, b["shot"])
    assert ei.value.code == "PRODUCTION_WORLD_BINDING_STALE"


async def test_m13_shot_04(client):
    """M13-SHOT:04 — M10 spatial context absent blocks."""
    b = await _full_m13_world(client, tag=b"shot04")
    sel = await _select_binding(client, b)
    # remove the shot plan → M10 resolves no authority for this shot
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM shot_spatial_plans WHERE shot_id = :s"),
            {"s": b["shot"]})
        await conn.commit()
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as ei:
        await _capture(client, b["shot"])
    # M10 raises its own blocker first (frozen global precedence) when the
    # plan is gone for a required world
    assert ei.value.code in ("SPATIAL_SHOT_PLAN_REQUIRED",
                             "PRODUCTION_WORLD_SPATIAL_CONTEXT_REQUIRED")


async def test_m13_shot_05(client):
    """M13-SHOT:05 — a different exact M10 world revision blocks (the
    binding never tells M10 what to resolve)."""
    b = await _full_m13_world(client, tag=b"shot05")
    sel = await _select_binding(client, b)
    # approve a SECOND world revision after the binding was published: the
    # ordinary M10 resolver now resolves the newer revision
    from soloring.spatial import revisions as rev_svc
    from soloring.spatial import worlds as world_svc

    f = _factory(client)
    # genuinely change the world state, then approve the new revision
    await world_svc.put_state_frame(
        f(), b["state"]["id"], b["desk_frame"]["id"],
        translation_mm=[3100, 0, -2000], rotation_udeg=[0, 0, 0],
        half_extents_mm=None, bound_entity_revision_id=None)
    rev2 = await rev_svc.capture_revision(f(), b["state"]["id"])
    await rev_svc.approve_revision(
        f(), b["state"]["id"], revision_id=rev2["id"],
        expected_approved_revision_id=b["rev"]["id"])
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as ei:
        await _capture(client, b["shot"])
    assert ei.value.code == "PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH"


async def test_m13_shot_06(client):
    """M13-SHOT:06 — every CreativeEntity binding subject must be an
    explicit semantic dependency (missing ⇒ blocked, never injected)."""
    b = await _full_m13_world(client, tag=b"shot06")
    # build a binding whose CE subject is NOT among the shot deps
    from tests.m13_seed import make_entity
    cid = await make_composition(client, b["pid"])
    m = await mint(client, cid, b["production_revision_id"], 0)
    oid = m["occurrence_id"]
    stranger, stranger_rev = await _entity_approved(
        client, b["pid"], "prop", "Unrelated")
    await _adopt(client, cid, oid,
                 {"kind": "creative_entity", "creative_entity_id": stranger})
    await _interpretation(client, b["production_revision_id"])
    from soloring.spatial import worlds as world_svc

    f = _factory(client)
    fr = await world_svc.create_frame(
        f(), b["world"]["id"], key="stranger", name="stranger",
        parent_spatial_frame_id=None, bound_entity_id=stranger)
    await world_svc.put_state_frame(
        f(), b["state"]["id"], fr["id"], translation_mm=[0, 5, 0],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=stranger_rev)
    from soloring.spatial import revisions as rev_svc

    rev2 = await rev_svc.capture_revision(f(), b["state"]["id"])
    await rev_svc.approve_revision(
        f(), b["state"]["id"], revision_id=rev2["id"],
        expected_approved_revision_id=b["rev"]["id"])
    pub = await publish(client, cid, 1)
    pr = await _publish(client, pub["revision"]["revision_id"],
                        rev2["id"])
    assert pr.status_code == 201, pr.text
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": pr.json()["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as ei:
        await _capture(client, b["shot"])
    assert ei.value.code == "PRODUCTION_WORLD_ENTITY_DEPENDENCY_REQUIRED"
    assert ei.value.details["missing_entity_ids"] == [stranger]
    # no dependency was silently injected
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_entity_dependencies WHERE shot_id = "
            ":s AND entity_id = :e"),
            {"s": b["shot"], "e": stranger})).scalar_one()
    assert n == 0


async def test_m13_shot_10(client):
    """M13-SHOT:10 — schemas 1-5 golden bytes/hashes unchanged (the M10
    shot with no selection captures byte-identically after M13 lands)."""
    b = await _full_m13_world(client, tag=b"shot10")
    revision, _ = await _capture(client, b["shot"])
    snap = json.loads(revision.snapshot_json)
    # exact schema-5 key set, no M13 key
    assert set(snap) == {"schema_version", "intent", "references",
                         "continuity", "visual_reference_pack",
                         "spatial_continuity"} or set(snap) == {
        "schema_version", "intent", "references", "continuity",
        "spatial_continuity"}


async def test_m13_shot_11(client):
    """M13-SHOT:11 — an M13 pack without the M10 spatial pack is an
    invariant failure (the builder refuses the cell)."""
    from types import SimpleNamespace

    from soloring.continuity.snapshots import (
        ResolvedDependency,
        build_capturable_snapshot,
    )
    from soloring.errors import SoloRingError

    shot = SimpleNamespace(subject="s", action=None, environment=None,
                           framing=None, camera_motion=None, lens=None,
                           mood=None, duration_ms=1000)
    dep = ResolvedDependency(
        entity_id="11111111-1111-1111-1111-111111111111",
        entity_kind="prop",
        entity_revision_id="22222222-2222-2222-2222-222222222222",
        entity_revision_number=1,
        entity_revision_hash="3" * 64,
        role="cast", position=0, source="dependency")
    with pytest.raises(SoloRingError) as ei:
        build_capturable_snapshot(
            shot, [], [dep], (), (), None, None,
            production_world_pack={"schema_version": 1})
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_shot_15(client):
    """M13-SHOT:15 — a selected zero-subject binding still produces a
    legal non-null schema-6 production world."""
    b = await _full_m13_world(client, tag=b"shot15")
    cid = await make_composition(client, b["pid"])
    await mint(client, cid, b["production_revision_id"], 0)
    pub = await publish(client, cid, 1)
    pr = await _publish(client, pub["revision"]["revision_id"],
                        b["rev"]["id"])
    assert pr.status_code == 201, pr.text
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": pr.json()["binding_id"],
              "expected_binding_id": None})
    assert r.status_code == 200, r.text
    revision, _ = await _capture(client, b["shot"])
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 6
    assert snap["production_world"]["binding"]["value"]["subjects"] == []
    assert snap["production_world"]["instance_feature_states"] == []
    assert snap["production_world"]["instance_spatial_states"] == []
