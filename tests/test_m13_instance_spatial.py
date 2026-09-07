"""M13 Production Instance spatial proofs (frozen R3 §30.4/§30.6)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m13_seed import make_entity, make_composition, mint, seed_base
from tests.test_m13_instance_state import _topology


async def _world(client, *, tag=b"m13-space"):
    base = await seed_base(client, tag=tag)
    cid = await make_composition(client, base["project_id"])
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    r = await client.post(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject",
        json={"kind": "production_instance"})
    assert r.status_code == 201, r.text
    loc = await make_entity(client, base["project_id"], kind="location",
                             name="Lobby Set")
    r = await client.post(
        f"/projects/{base['project_id']}/spatial-worlds",
        json={"key": "lobby", "name": "Lobby", "requirement": "required",
              "location_entity_id": loc})
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    return base, cid, oid, wid


async def _track(client, wid, oid, requirement="required"):
    r = await client.post(f"/spatial-worlds/{wid}/production-instance-tracks",
                          json={"occurrence_id": oid,
                                "requirement": requirement})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _transition(client, tid, anchor_type, anchor_id, boundary,
                      operation, transform=None):
    body = {"anchor_type": anchor_type, "anchor_id": anchor_id,
            "boundary": boundary, "operation": operation}
    if transform is not None:
        body["transform"] = transform
    r = await client.post(
        f"/production-instance-spatial-tracks/{tid}/transitions", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_m13_space_01(client):
    """M13-SPACE:01 — PI Track requires PI subject adoption."""
    base, cid, oid, wid = await _world(client)
    m2 = await mint(client, cid, base["production_revision_id"], 1, name="B")
    r = await client.post(f"/spatial-worlds/{wid}/production-instance-tracks",
                          json={"occurrence_id": m2["occurrence_id"],
                                "requirement": "required"})
    assert r.status_code == 422, r.text
    # creative_entity-adopted occurrence rejects too (SUBJECT:09 spatial)
    eid = await make_entity(client, base["project_id"])
    m3 = await mint(client, cid, base["production_revision_id"], 2, name="C")
    r = await client.post(
        f"/compositions/{cid}/occurrences/{m3['occurrence_id']}"
        "/authority-subject",
        json={"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201
    r = await client.post(f"/spatial-worlds/{wid}/production-instance-tracks",
                          json={"occurrence_id": m3["occurrence_id"],
                                "requirement": "required"})
    assert r.status_code == 422, r.text


async def test_m13_space_02(client):
    """M13-SPACE:02 — same-Project world required."""
    base, cid, oid, wid = await _world(client, tag=b"m13-space-02")
    other = await seed_base(client, tag=b"m13-space-other")
    loc2 = await make_entity(client, other["project_id"], kind="location",
                             name="Elsewhere Set")
    r = await client.post(
        f"/projects/{other['project_id']}/spatial-worlds",
        json={"key": "elsewhere", "name": "Elsewhere",
              "requirement": "required", "location_entity_id": loc2})
    assert r.status_code == 201, r.text
    other_wid = r.json()["id"]
    r = await client.post(
        f"/spatial-worlds/{other_wid}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "required"})
    assert r.status_code == 422, r.text


async def test_m13_space_03(client):
    """M13-SPACE:03 — one active track per (world, occurrence)."""
    base, cid, oid, wid = await _world(client)
    await _track(client, wid, oid)
    r = await client.post(f"/spatial-worlds/{wid}/production-instance-tracks",
                          json={"occurrence_id": oid,
                                "requirement": "optional"})
    assert r.status_code == 409, r.text
    # soft-deleting frees the coordinate
    r = await client.get(f"/spatial-worlds/{wid}/production-instance-tracks")
    tid = r.json()[0]["id"]
    r = await client.delete(
        f"/production-instance-spatial-tracks/{tid}")
    assert r.status_code == 200, r.text
    await _track(client, wid, oid, requirement="optional")


async def test_m13_space_04(client):
    """M13-SPACE:04 — set/clear grammar exact."""
    base, cid, oid, wid = await _world(client)
    tid = await _track(client, wid, oid)
    r = await client.post(
        f"/production-instance-spatial-tracks/{tid}/transitions",
        json={"anchor_type": "scene", "anchor_id": "x", "boundary": "start",
              "operation": "set",
              "transform": {"translation_mm": [1, 2, 3],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 422, r.text
    r = await client.post(
        f"/production-instance-spatial-tracks/{tid}/transitions",
        json={"anchor_type": "scene", "anchor_id": "x", "boundary": "start",
              "operation": "clear",
              "transform": {"translation_mm": [1, 2, 3],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 422, r.text


async def test_m13_space_05(client):
    """M13-SPACE:05 — no interpolation/default-origin authority."""
    base, cid, oid, wid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"],
                                           n_shots=2)
    tid = await _track(client, wid, oid, requirement="optional")
    # no transition at all: the track resolves absent, never origin
    from soloring.production_world.instance_spatial import resolve_pi_staging
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        out = await resolve_pi_staging(
            conn, shot_id=shot_ids[0], spatial_world_id=wid,
            subjects=[(cid, oid)])
    assert out["states"] == []
    assert out["absent"][0]["reason"] == "no_eligible_transition"
    assert out["absent"][0]["requirement"] == "optional"


async def test_m13_space_06(client):
    """M13-SPACE:06 — required means effective non-NULL transform at
    target Shot; optional resolves absent instead."""
    base, cid, oid, wid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"],
                                           n_shots=2)
    tid = await _track(client, wid, oid, requirement="required")
    await _transition(client, tid, "scene", scene, "start", "set",
                      {"translation_mm": [10, 0, 0],
                       "rotation_udeg": [0, 0, 0]})
    await _transition(client, tid, "shot", shot_ids[1], "start", "clear")
    from soloring.production_world.instance_spatial import resolve_pi_staging
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        out0 = await resolve_pi_staging(
            conn, shot_id=shot_ids[0], spatial_world_id=wid,
            subjects=[(cid, oid)])
        out1 = await resolve_pi_staging(
            conn, shot_id=shot_ids[1], spatial_world_id=wid,
            subjects=[(cid, oid)])
    assert [s["x_mm"] for s in out0["states"]] == [10]
    assert out1["states"] == []
    assert out1["absent"][0]["reason"] == "clear"
    assert out1["absent"][0]["requirement"] == "required"


async def test_m13_space_07(client):
    """M13-SPACE:07 — ambiguous/corrupt staging fails closed."""
    base, cid, oid, wid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"])
    tid = await _track(client, wid, oid)
    await _transition(client, tid, "shot", shot_ids[0], "start", "set",
                      {"translation_mm": [1, 1, 1],
                       "rotation_udeg": [0, 0, 0]})
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS uq_pistt_active_coordinate"))
        await conn.execute(text(
            "INSERT INTO production_instance_spatial_transitions "
            "(id, spatial_track_id, anchor_type, anchor_id, boundary, "
            "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
            "created_at, updated_at) VALUES "
            "(:id, :tid, 'shot', :aid, 'start', 'set', 2, 2, 2, 0, 0, 0, "
            "'2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z')"),
            {"id": "88888888-8888-8888-8888-888888888888", "tid": tid,
             "aid": shot_ids[0]})
        await conn.commit()
    from soloring.errors import SoloRingError
    from soloring.production_world.instance_spatial import resolve_pi_staging
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError) as ei:
            await resolve_pi_staging(
                conn, shot_id=shot_ids[0], spatial_world_id=wid,
                subjects=[(cid, oid)])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_space_08(client):
    """M13-SPACE:08 — EntityTrack-vs-PITrack shared-subset equivalence.

    Equivalent track/transition histories produce the same eligible
    winner, absence reason, required/optional handling, canonical
    transform, and source anchor semantics — only subject identity
    differs.
    """
    base, cid, oid, wid = await _world(client, tag=b"m13-space-08")
    pid = base["project_id"]
    seq, scene, shot_ids = await _topology(client, pid, n_shots=2)
    eid = await make_entity(client, pid)
    # entity twin: approved revision + dependency + EntityTrack + same
    # transition coordinates in the same world
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "twin"}})
    rev_id = r.json()["id"]
    r = await client.put(f"/entities/{eid}/approved-revision",
                         json={"revision_id": rev_id,
                               "expected_approved_revision_id": None})
    assert r.status_code == 200, r.text
    for sid in shot_ids:
        r = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert r.status_code in (200, 201), r.text
    r = await client.post(f"/spatial-worlds/{wid}/tracks",
                          json={"entity_id": eid, "requirement": "required"})
    assert r.status_code == 201, r.text
    etid = r.json()["id"]
    pi_tid = await _track(client, wid, oid, requirement="required")
    for tid, base_path in ((pi_tid, "production-instance-spatial-tracks"),
                           (etid, "spatial-tracks")):
        if base_path == "spatial-tracks":
            set_body = {"anchor_type": "scene", "anchor_id": scene,
                        "boundary": "start", "operation": "set",
                        "translation_mm": [10, 0, 0],
                        "rotation_udeg": [0, 0, 0]}
        else:
            set_body = {"anchor_type": "scene", "anchor_id": scene,
                        "boundary": "start", "operation": "set",
                        "transform": {"translation_mm": [10, 0, 0],
                                      "rotation_udeg": [0, 0, 0]}}
        r = await client.post(
            f"/{base_path}/{tid}/transitions", json=set_body)
        assert r.status_code == 201, (base_path, r.text)
        r = await client.post(
            f"/{base_path}/{tid}/transitions",
            json={"anchor_type": "shot", "anchor_id": shot_ids[1],
                  "boundary": "start", "operation": "clear"})
        assert r.status_code == 201, (base_path, r.text)
    from soloring.spatial.staging import resolve_effective_staging
    from soloring.production_world.instance_spatial import resolve_pi_staging
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        pi0 = await resolve_pi_staging(
            conn, shot_id=shot_ids[0], spatial_world_id=wid,
            subjects=[(cid, oid)])
        pi1 = await resolve_pi_staging(
            conn, shot_id=shot_ids[1], spatial_world_id=wid,
            subjects=[(cid, oid)])
        ent0 = await resolve_effective_staging(
            conn, shot_id=shot_ids[0], spatial_world_id=wid,
            resolved_entity_revisions={eid: rev_id})
        ent1 = await resolve_effective_staging(
            conn, shot_id=shot_ids[1], spatial_world_id=wid,
            resolved_entity_revisions={eid: rev_id})
    p0, e0 = pi0["states"][0], ent0.states[0]
    assert (p0["x_mm"], p0["yaw_udeg"], p0["requirement"],
            p0["source_anchor_type"], p0["source_boundary"]) == (
        e0.x_mm, e0.yaw_udeg, e0.requirement,
        e0.source_anchor_type, e0.source_boundary)
    p1a, e1a = pi1["absent"][0], ent1.absent[0]
    assert (p1a["requirement"], p1a["reason"]) == (
        e1a.requirement, e1a.reason) == ("required", "clear")


async def test_m13_impact_03(client):
    """M13-IMPACT:03 — active PI Track blocks termination."""
    base, cid, oid, wid = await _world(client, tag=b"m13-imp03")
    await _track(client, wid, oid)
    r = await client.post(
        f"/compositions/{cid}/identity-operations/preview",
        json={"scope": "composition_working_state",
              "request": {"kind": "remove",
                          "source_occurrence_ids": [oid],
                          "target_working_specs": []}})
    assert r.status_code == 200, r.text
    pv = r.json()
    assert pv["allowed"] is False
    assert [b["consumer"] for b in pv["live_blocking_references"]] == [
        "production_instance_spatial_track"]
    r = await client.post(
        f"/compositions/{cid}/identity-operations",
        json={"scope": "composition_working_state",
              "expected_working_version": 1,
              "expected_request_fingerprint":
                  pv["request_fingerprint"],
              "expected_impact_fingerprint":
                  pv["impact_fingerprint"],
              "request": {"kind": "remove",
                          "source_occurrence_ids": [oid],
                          "target_working_specs": []}})
    assert r.status_code == 409, r.text
    assert r.json()["details"]["reason"] == "live_references"
    # fork is NOT blocked by live state (frozen §22.4)
    r = await client.post(
        f"/compositions/{cid}/identity-operations/preview",
        json={"scope": "composition_working_state",
              "request": {"kind": "fork",
                          "source_occurrence_ids": [oid],
                          "target_working_specs": [{
                              "display_name": "Forked",
                              "source": {"kind": "production_revision",
                                         "revision_id":
                                             base["production_revision_id"]},
                              "visible": True,
                              "transform": {"translation_mm": [0, 0, 0],
                                            "rotation_udeg": [0, 0, 0]}}]}})
    assert r.status_code == 200 and r.json()["allowed"] is True
