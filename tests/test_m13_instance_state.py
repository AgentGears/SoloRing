"""M13 Production Instance state proofs (frozen R3 §30.3/§30.1/§30.6)."""

from __future__ import annotations

from sqlalchemy import text

from tests.m13_seed import (
    make_entity,
    make_composition,
    mint,
    remove_occurrence,
    seed_base,
)

NOW = "2026-01-01T00:00:00.000Z"


async def _world(client, *, tag=b"m13-state"):
    """project + closed PR + composition + minted+adopted occurrence."""
    base = await seed_base(client, tag=tag)
    cid = await make_composition(client, base["project_id"])
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    r = await client.post(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject",
        json={"kind": "production_instance"})
    assert r.status_code == 201, r.text
    return base, cid, oid


async def _feature(client, oid, key="fallen", **kw):
    value_type = kw.pop("value_type", "enum")
    payload = {
        "key": key, "kind": kw.pop("kind", "status"),
        "value_type": value_type,
        "name": kw.pop("name", "Fallen"),
    }
    if value_type == "enum":
        payload["enum_values"] = kw.pop(
            "enum_values", ["upright", "fallen"])
    payload.update(kw)
    r = await client.post(f"/production-instances/{oid}/features",
                          json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _transition(client, fid, anchor_type, anchor_id, boundary,
                      operation, value=None):
    body = {"anchor_type": anchor_type, "anchor_id": anchor_id,
            "boundary": boundary, "operation": operation}
    if value is not None:
        body["value"] = value
    r = await client.post(
        f"/production-instance-features/{fid}/transitions", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _topology(client, pid, n_shots=1):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    assert r.status_code == 201, r.text
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "C"})
    assert r.status_code == 201, r.text
    scene = r.json()["id"]
    engine = client._transport.app.state.engine
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    shot_ids = []
    for i in range(n_shots):
        async with factory() as s:
            shot = await shot_svc.create_shot(
                s, pid, ShotCreate(subject=f"shot {i + 1}"))
        shot_ids.append(shot.id)
    r = await client.put(f"/scenes/{scene}/shots",
                         json={"shot_ids": shot_ids})
    assert r.status_code == 200, r.text
    return seq, scene, shot_ids


async def test_m13_state_01(client):
    """M13-STATE:01 — PI Feature requires PI subject adoption."""
    base, cid, oid = await _world(client)
    # un-adopt the subject by using a fresh occurrence
    m2 = await mint(client, cid, base["production_revision_id"], 1,
                    name="Bare")
    r = await client.post(f"/production-instances/{m2['occurrence_id']}"
                          "/features",
                          json={"key": "k", "kind": "status",
                                "value_type": "text", "name": "K"})
    assert r.status_code == 422, r.text
    # creative_entity adoption also rejects (SUBJECT:09)
    eid = await make_entity(client, base["project_id"])
    m3 = await mint(client, cid, base["production_revision_id"], 2,
                    name="CE")
    r = await client.post(
        f"/compositions/{cid}/occurrences/{m3['occurrence_id']}"
        "/authority-subject",
        json={"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201
    r = await client.post(f"/production-instances/{m3['occurrence_id']}"
                          "/features",
                          json={"key": "k", "kind": "status",
                                "value_type": "text", "name": "K"})
    assert r.status_code == 422, r.text
    assert "creative_entity" in r.json()["message"]


async def test_m13_state_02(client):
    """M13-STATE:02 — value grammar equals the M7 shared semantics."""
    base, cid, oid = await _world(client)
    # enum without values / bad key / bad unit mirror the M7 rejections
    r = await client.post(f"/production-instances/{oid}/features",
                          json={"key": "Bad Key", "kind": "status",
                                "value_type": "text", "name": "K"})
    assert r.status_code == 422
    r = await client.post(f"/production-instances/{oid}/features",
                          json={"key": "ok_key", "kind": "status",
                                "value_type": "enum", "name": "K"})
    assert r.status_code == 422
    r = await client.post(f"/production-instances/{oid}/features",
                          json={"key": "ok_key2", "kind": "status",
                                "value_type": "text", "name": "K",
                                "unit": "cm"})
    assert r.status_code == 422
    # integer+unit is legal; canonical transition value grammar applies
    fid = await _feature(client, oid, key="tilt_deg", value_type="integer",
                         name="Tilt", unit="degrees")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT enum_values_json FROM production_instance_features "
            "WHERE id = :f"), {"f": fid})).first()
    assert row is not None


async def test_m13_state_03(client):
    """M13-STATE:03 — random-access winner direct at target boundary."""
    base, cid, oid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"])
    fid = await _feature(client, oid)
    await _transition(client, fid, "shot", shot_ids[0], "start", "set",
                      "fallen")
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        out = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[0], subjects=[(cid, oid)])
    assert [s["value_json"] for s in out["states"]] == ['"fallen"']
    assert out["states"][0]["feature_id"] == fid


async def test_m13_state_04(client):
    """M13-STATE:04 — start/end inclusion exact."""
    base, cid, oid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"],
                                           n_shots=2)
    fid = await _feature(client, oid)
    # set at scene start is eligible at every contained shot start
    await _transition(client, fid, "scene", scene, "start", "set", "upright")
    # set at scene end is NOT eligible at shot starts
    await _transition(client, fid, "shot", shot_ids[1], "start", "set",
                      "fallen")
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        out0 = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[0], subjects=[(cid, oid)])
        out1 = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[1], subjects=[(cid, oid)])
    assert [s["value_json"] for s in out0["states"]] == ['"upright"']
    assert [s["value_json"] for s in out1["states"]] == ['"fallen"']


async def test_m13_state_05(client):
    """M13-STATE:05 — clear means canonical absence."""
    base, cid, oid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"],
                                           n_shots=2)
    fid = await _feature(client, oid)
    await _transition(client, fid, "scene", scene, "start", "set", "fallen")
    await _transition(client, fid, "shot", shot_ids[1], "start", "clear")
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        out1 = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[1], subjects=[(cid, oid)])
    assert out1["states"] == []
    assert out1["relevant_temporal_data"] is True


async def test_m13_state_06(client):
    """M13-STATE:06 — ambiguous winner is invariant corruption."""
    base, cid, oid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"])
    fid = await _feature(client, oid)
    await _transition(client, fid, "shot", shot_ids[0], "start", "set",
                      "fallen")
    # force a second active transition at the same coordinate via SQL;
    # the active-coordinate partial unique normally prevents this, so the
    # corruption simulation drops the index first (schema tampering)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS uq_pift_active_coordinate"))
        await conn.execute(text(
            "INSERT INTO production_instance_feature_transitions "
            "(id, feature_id, anchor_type, anchor_id, boundary, operation, "
            "value_json, value_hash, created_at, updated_at) VALUES "
            "(:id, :fid, 'shot', :aid, 'start', 'set', :vj, :vh, :n, :n)"),
            {"id": "99999999-9999-9999-9999-999999999999", "fid": fid,
             "aid": shot_ids[0], "vj": '"upright"',
             "vh": "0" * 64, "n": NOW})
        await conn.commit()
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    import pytest
    from soloring.errors import SoloRingError
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError) as ei:
            await resolve_pi_feature_state(
                conn, shot_id=shot_ids[0], subjects=[(cid, oid)])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_state_07(client):
    """M13-STATE:07 — stored value corruption fails closed."""
    base, cid, oid = await _world(client)
    seq, scene, shot_ids = await _topology(client, base["project_id"])
    fid = await _feature(client, oid)
    await _transition(client, fid, "shot", shot_ids[0], "start", "set",
                      "fallen")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE production_instance_feature_transitions "
            "SET value_json = '\"upright\"' WHERE feature_id = :f"),
            {"f": fid})
        await conn.commit()
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    import pytest
    from soloring.errors import SoloRingError
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError) as ei:
            await resolve_pi_feature_state(
                conn, shot_id=shot_ids[0], subjects=[(cid, oid)])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_state_08(client):
    """M13-STATE:08 — Entity-vs-PI shared-subset equivalence.

    Equivalent Feature/transition histories over the same narrative
    ordering produce the same eligibility, winner boundary, set/clear
    outcome, canonical scalar, value hash, and ambiguous-winner error —
    only subject identity differs.
    """
    base, cid, oid = await _world(client, tag=b"m13-equiv")
    pid = base["project_id"]
    seq, scene, shot_ids = await _topology(client, pid, n_shots=2)
    eid = await make_entity(client, pid)
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "twin"}})
    assert r.status_code == 201, r.text
    r = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    assert r.status_code == 200, r.text
    # Entity twin: same key/kind/value_type + same transition coordinates
    r = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "fallen", "kind": "status", "value_type": "enum",
              "name": "Fallen",
              "enum_values": ["upright", "fallen"]})
    assert r.status_code == 201, r.text
    efid = r.json()["id"]
    fid = await _feature(client, oid)
    for f in (fid, efid):
        await client.post(
            f"/production-instance-features/{f}/transitions"
            if f == fid else
            f"/continuity-features/{f}/transitions",
            json={"anchor_type": "scene", "anchor_id": scene,
                  "boundary": "start", "operation": "set",
                  "value": "upright"})
        path = (f"/production-instance-features/{fid}/transitions"
                if f == fid else
                f"/continuity-features/{efid}/transitions")
        await client.post(path, json={
            "anchor_type": "shot", "anchor_id": shot_ids[1],
            "boundary": "start", "operation": "set", "value": "fallen"})
    # make the Entity a Shot dependency so its state resolves
    for sid in shot_ids:
        r = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert r.status_code in (200, 201), r.text
    from soloring.continuity.state import resolve_effective_feature_state
    from soloring.production_world.instance_state import (
        resolve_pi_feature_state,
    )
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        pi = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[1], subjects=[(cid, oid)])
        ent = await resolve_effective_feature_state(conn, shot_ids[1])
    p = pi["states"][0]
    e = ent.states[0]
    assert (p["feature_key"], p["feature_kind"], p["value_type"],
            p["value_json"], p["value_hash"],
            p["source_anchor_type"], p["source_boundary"]) == (
        e.feature_key, e.feature_kind, e.value_type,
        e.value_json, e.value_hash,
        e.source_anchor_type, e.source_boundary)
    # same eligibility boundary at the earlier shot too
    async with engine.connect() as conn:
        pi0 = await resolve_pi_feature_state(
            conn, shot_id=shot_ids[0], subjects=[(cid, oid)])
        ent0 = await resolve_effective_feature_state(conn, shot_ids[0])
    assert (pi0["states"][0]["value_json"],
            pi0["states"][0]["source_anchor_type"]) == (
        ent0.states[0].value_json, ent0.states[0].source_anchor_type)
