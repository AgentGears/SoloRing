"""M13 binding proofs (frozen R3 §30.5 M13-BIND:01-17)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.m13_seed import (
    make_composition,
    make_entity,
    mint,
    mint_nested,
    publish,
    seed_base,
)


def _factory(client):
    return async_sessionmaker(bind=client._transport.app.state.engine,
                              expire_on_commit=False)


async def _approved_world(client, pid, *, frames=(("origin", (0, 0, 0),
                                                   None),),
                           key="lobby"):
    """World + state + frames + captured + APPROVED revision."""
    from soloring.spatial import revisions as rev_svc
    from soloring.spatial import worlds as world_svc

    f = _factory(client)
    loc = await make_entity(client, pid, kind="location",
                            name=f"{key} set")
    r = await client.post(f"/entities/{loc}/revisions",
                          json={"spec": {"description": key}})
    locrev = r.json()["id"]
    world = await world_svc.create_world(
        f(), pid, key=key, name=key, description=None,
        requirement="required", location_entity_id=loc)
    state = await world_svc.create_state(
        f(), world["id"], location_entity_revision_id=locrev)
    fids = {}
    for fkey, t, bound in frames:
        fr = await world_svc.create_frame(
            f(), world["id"], key=fkey, name=fkey,
            parent_spatial_frame_id=None,
            bound_entity_id=bound[0] if bound else None)
        fids[fkey] = fr["id"]
        await world_svc.put_state_frame(
            f(), state["id"], fr["id"], translation_mm=list(t),
            rotation_udeg=[0, 0, 0], half_extents_mm=None,
            bound_entity_revision_id=bound[1] if bound else None)
    rev = await rev_svc.capture_revision(f(), state["id"])
    await rev_svc.approve_revision(
        f(), state["id"], revision_id=rev["id"],
        expected_approved_revision_id=None)
    return {"world": world, "state": state, "revision": rev, "fids": fids}


async def _binding_base(client, *, tag=b"m13-bind", n_occurrences=1,
                        transform=(0, 0, 0)):
    """project + closed PR + published C with direct occurrences."""
    base = await seed_base(client, tag=tag)
    pid = base["project_id"]
    cid = await make_composition(client, pid)
    occs = []
    for i in range(n_occurrences):
        m = await mint(
            client, cid, base["production_revision_id"], i,
            name=f"Chair {i}", transform=transform)
        occs.append(m["occurrence_id"])
    pub = await publish(client, cid, len(occs))
    return {**base, "composition_id": cid, "occurrences": occs,
            "C": pub["revision"]["revision_id"]}


async def _readiness(client, c, w):
    return await client.post(
        f"/composition-revisions/{c}/spatial-binding-readiness",
        json={"spatial_world_revision_id": w})


async def _publish(client, c, w):
    return await client.post(
        f"/composition-revisions/{c}/spatial-bindings",
        json={"spatial_world_revision_id": w})


async def _interpretation(client, prid, translation=(0, 0, 0)):
    r = await client.post(
        f"/production-revisions/{prid}/spatial-interpretation",
        json={"realization_local_to_subject_local": {
            "translation_mm": list(translation),
            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    return r.json()


async def _adopt(client, cid, oid, body):
    r = await client.post(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject",
        json=body)
    assert r.status_code == 201, r.text


async def test_m13_bind_01(client):
    """M13-BIND:01 — exact C/W verified and same Project."""
    b = await _binding_base(client, tag=b"bind01")
    w = await _approved_world(client, b["project_id"])
    r = await _readiness(client, b["C"], w["revision"]["id"])
    assert r.status_code == 200, r.text
    assert r.json()["ready"] is True
    # cross-Project W → deterministic mismatch issue
    other = await seed_base(client, tag=b"bind01-other")
    ow = await _approved_world(client, other["project_id"], key="other")
    cid2 = await make_composition(client, other["project_id"])
    await mint(client, cid2, other["production_revision_id"], 0)
    pub2 = await publish(client, cid2, 1)
    r = await _readiness(client, pub2["revision"]["revision_id"],
                         w["revision"]["id"])
    assert r.json()["ready"] is False
    assert r.json()["issues"][0]["code"] == "BINDING_PROJECT_MISMATCH"
    # unknown revisions are 404s, not readiness issues
    r = await _readiness(client, "ffffffff-ffff-ffff-ffff-ffffffffffff",
                         w["revision"]["id"])
    assert r.status_code == 404


async def test_m13_bind_02(client):
    """M13-BIND:02 — subject list is the complete server-derived set;
    adoptions outside exact C are excluded (BIND:15) and a nested-source
    occurrence present in C is excluded at the derivation level (the
    frozen §7.2/§10.1 rule, proven structurally)."""
    b = await _binding_base(client, tag=b"bind02", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    eid = await make_entity(client, b["project_id"])
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    await _adopt(client, cid, b["occurrences"][1],
                 {"kind": "production_instance"})
    # an adoption for an occurrence NOT present in exact C (minted after
    # publication) is excluded
    m = await mint(client, cid, b["production_revision_id"], 2,
                   name="Later")
    await _adopt(client, cid, m["occurrence_id"],
                 {"kind": "production_instance"})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is True
    assert sorted(s["occurrence_id"] for s in out["subject_summaries"]) == \
        sorted(b["occurrences"])

    # structural proof: an adoption row on a nested-source occurrence
    # present in exact C contributes no subject and is not a readiness
    # error (the frozen exclusion rule; unreachable via M12 authoring)
    cid2 = await make_composition(client, b["project_id"], name="Sub")
    await mint(client, cid2, b["production_revision_id"], 0)
    pub2 = await publish(client, cid2, 1)
    cid3 = await make_composition(client, b["project_id"], name="Host")
    nm = await mint_nested(client, cid3, pub2["revision"]["revision_id"], 0)
    pub3 = await publish(client, cid3, 1)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO composition_occurrence_authority_subjects "
            "(composition_id, occurrence_id, subject_kind, "
            "creative_entity_id, created_at) VALUES "
            "(:c, :o, 'production_instance', NULL, '2026-01-01T00:00:00')"
            ".000Z'.replace('000Z','000Z')"),
            {"c": cid3, "o": nm["occurrence_id"]}) \
            if False else await conn.execute(text(
            "INSERT INTO composition_occurrence_authority_subjects "
            "(composition_id, occurrence_id, subject_kind, "
            "creative_entity_id, created_at) VALUES "
            "(:c, :o, 'production_instance', NULL, "
            "'2026-01-01T00:00:00.000Z')"),
            {"c": cid3, "o": nm["occurrence_id"]})
        await conn.commit()
    r = await _readiness(client, pub3["revision"]["revision_id"],
                         w["revision"]["id"])
    assert r.status_code == 200, r.text
    assert r.json()["ready"] is True
    assert r.json()["subject_summaries"] == []


async def test_m13_bind_03(client):
    """M13-BIND:03 — entry list is the complete server-derived A4 subset
    (one CE frame entry, one PI track entry, one composition-owned)."""
    b = await _binding_base(client, tag=b"bind03", n_occurrences=3)
    eid = await make_entity(client, b["project_id"])
    w = await _approved_world(
        client, b["project_id"],
        frames=(("chair_frame", (1, 2, 3), None),))
    # add a bound frame in a NEW approved revision
    from soloring.spatial import revisions as rev_svc
    from soloring.spatial import worlds as world_svc

    f = _factory(client)
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "d"}})
    erid = r.json()["id"]
    await client.put(f"/entities/{eid}/approved-revision",
                     json={"revision_id": erid,
                           "expected_approved_revision_id": None})
    fr2 = await world_svc.create_frame(
        f(), w["world"]["id"], key="chair_bound", name="chair_bound",
        parent_spatial_frame_id=None, bound_entity_id=eid)
    await world_svc.put_state_frame(
        f(), w["state"]["id"], fr2["id"], translation_mm=[5, 0, 0],
        rotation_udeg=[0, 0, 0], half_extents_mm=None,
        bound_entity_revision_id=erid)
    # drop the unbound frame from the state to keep one frame set
    rev2 = await rev_svc.capture_revision(f(), w["state"]["id"])
    await rev_svc.approve_revision(
        f(), w["state"]["id"], revision_id=rev2["id"],
        expected_approved_revision_id=w["revision"]["id"])

    cid = b["composition_id"]
    occ_ce, occ_pi, occ_free = b["occurrences"]
    await _adopt(client, cid, occ_ce,
                 {"kind": "creative_entity", "creative_entity_id": eid})
    await _adopt(client, cid, occ_pi, {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    # PI track for occ_pi in the world
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_pi, "requirement": "required"})
    assert r.status_code == 201, r.text
    pi_track = r.json()["id"]

    r = await _readiness(client, b["C"], rev2["id"])
    out = r.json()
    assert out["ready"] is True, out
    assert len(out["subject_summaries"]) == 2
    assert len(out["entry_summaries"]) == 2
    kinds = {e["occurrence_id"]: e["placement"]["kind"]
             for e in out["entry_summaries"]}
    assert kinds[occ_ce] == "entity_fixed_frame"
    assert kinds[occ_pi] == "production_instance_track"
    assert occ_free not in kinds  # composition-owned: no entry

    pr = await _publish(client, b["C"], rev2["id"])
    assert pr.status_code == 201, pr.text
    stored = pr.json()
    assert {e["placement"]["kind"] for e in stored["entries"]} == {
        "entity_fixed_frame", "production_instance_track"}
    by_occ = {e["occurrence_id"]: e["placement"]["id"]
              for e in stored["entries"]}
    assert by_occ[occ_ce] == fr2["id"]
    assert by_occ[occ_pi] == pi_track


async def test_m13_bind_04(client):
    """M13-BIND:04 — zero A4 targets ⇒ composition-owned / no entry."""
    b = await _binding_base(client, tag=b"bind04")
    w = await _approved_world(client, b["project_id"])
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "production_instance"})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is True
    assert len(out["subject_summaries"]) == 1
    assert out["entry_summaries"] == []


async def test_m13_bind_06(client):
    """M13-BIND:06 — duplicate A4 targets ⇒ conflict (frame + entity
    track)."""
    b = await _binding_base(client, tag=b"bind06")
    eid = await make_entity(client, b["project_id"])
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "d"}})
    erid = r.json()["id"]
    await client.put(f"/entities/{eid}/approved-revision",
                     json={"revision_id": erid,
                           "expected_approved_revision_id": None})
    w = await _approved_world(
        client, b["project_id"],
        frames=(("f_bound", (0, 0, 0), (eid, erid)),))
    # add a competing EntityTrack in the same world
    r = await client.post(f"/spatial-worlds/{w['world']['id']}/tracks",
                          json={"entity_id": eid, "requirement": "required"})
    assert r.status_code == 201, r.text
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is False
    assert out["issues"][0]["code"] == "BINDING_SPATIAL_TARGET_CONFLICT"
    r = await _publish(client, b["C"], w["revision"]["id"])
    assert r.status_code == 409
    assert r.json()["error_code"] == "COMPOSITION_SPATIAL_BINDING_NOT_READY"


async def test_m13_bind_07(client):
    """M13-BIND:07 — non-identity Composition transform blocks the
    authority-bound entry."""
    b = await _binding_base(client, tag=b"bind07", transform=(10, 0, 0))
    eid = await make_entity(client, b["project_id"])
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "d"}})
    erid = r.json()["id"]
    w = await _approved_world(
        client, b["project_id"],
        frames=(("f", (0, 0, 0), (eid, erid)),))
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is False
    assert out["issues"][0]["code"] == (
        "BINDING_COMPOSITION_TRANSFORM_CONFLICT")
    # a composition-owned subject with the same non-identity transform is
    # unaffected (no entry required) — same Project, its own world
    b2 = await _binding_base(client, tag=b"bind07b", transform=(10, 0, 0))
    w2 = await _approved_world(client, b2["project_id"], key="lobby7b")
    await _adopt(client, b2["composition_id"], b2["occurrences"][0],
                 {"kind": "production_instance"})
    r = await _readiness(client, b2["C"], w2["revision"]["id"])
    assert r.json()["ready"] is True, r.text


async def test_m13_bind_08(client):
    """M13-BIND:08 — missing interpretation blocks the authority-bound
    entry (and creating it unblocks)."""
    b = await _binding_base(client, tag=b"bind08")
    eid = await make_entity(client, b["project_id"])
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "d"}})
    erid = r.json()["id"]
    w = await _approved_world(
        client, b["project_id"],
        frames=(("f", (0, 0, 0), (eid, erid)),))
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "creative_entity", "creative_entity_id": eid})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    assert r.json()["issues"][0]["code"] == (
        "BINDING_SPATIAL_INTERPRETATION_REQUIRED")
    await _interpretation(client, b["production_revision_id"])
    r = await _readiness(client, b["C"], w["revision"]["id"])
    assert r.json()["ready"] is True, r.text


async def test_m13_bind_09(client):
    """M13-BIND:09 — canonical binding golden bytes/hash/order."""
    b = await _binding_base(client, tag=b"bind09", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "production_instance"})
    r = await _publish(client, b["C"], w["revision"]["id"])
    assert r.status_code == 201, r.text
    stored = r.json()
    # canonical ordering: subjects ascending by occurrence_id
    occs = [s["occurrence_id"] for s in stored["subjects"]]
    assert occs == sorted(occs)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT binding_json, binding_hash, "
            "composition_revision_hash, spatial_world_revision_hash FROM "
            "composition_spatial_bindings WHERE id = :b"),
            {"b": stored["binding_id"]})).first()
    parsed = json.loads(row.binding_json)
    from soloring.domain.canonical import canonical_json_str
    assert row.binding_json == canonical_json_str(parsed)
    import hashlib
    assert row.binding_hash == hashlib.sha256(
        row.binding_json.encode("utf-8")).hexdigest()
    assert row.composition_revision_hash == parsed[
        "composition_revision"]["snapshot_hash"]
    # subject entries embed the exact PR hash
    from soloring.production_world.binding import (
        binding_hash as bh,
        binding_value as bv,
    )
    rebuilt = bv(
        composition_revision_id=parsed["composition_revision"]["revision_id"],
        composition_revision_hash=parsed[
            "composition_revision"]["snapshot_hash"],
        spatial_world_revision_id=parsed[
            "spatial_world_revision"]["revision_id"],
        spatial_world_revision_hash=parsed[
            "spatial_world_revision"]["snapshot_hash"],
        subjects=parsed["subjects"], entries=parsed["entries"])
    assert bh(rebuilt) == row.binding_hash


async def test_m13_bind_10(client):
    """M13-BIND:10 — the caller cannot author binding membership: the
    request is exactly the world revision id (extra fields forbidden)."""
    b = await _binding_base(client, tag=b"bind10")
    w = await _approved_world(client, b["project_id"])
    r = await client.post(
        f"/composition-revisions/{b['C']}/spatial-bindings",
        json={"spatial_world_revision_id": w["revision"]["id"],
              "subjects": [{"occurrence_id": "0" * 36,
                            "production_revision_id": "0" * 36,
                            "production_revision_hash": "0" * 64,
                            "authority_subject": {"kind": "production_instance",
                                                  "id": "0" * 36}}],
              "entries": []})
    assert r.status_code == 422, r.text
    assert "Extra inputs" in r.text


async def test_m13_bind_11(client):
    """M13-BIND:11 — existing winner full parent/child validation; child
    corruption fails closed."""
    b = await _binding_base(client, tag=b"bind11")
    w = await _approved_world(client, b["project_id"])
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "production_instance"})
    r1 = await _publish(client, b["C"], w["revision"]["id"])
    assert r1.status_code == 201
    r2 = await _publish(client, b["C"], w["revision"]["id"])
    assert r2.status_code == 200
    assert r2.json()["binding_id"] == r1.json()["binding_id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM composition_spatial_binding_subjects WHERE "
            "binding_id = :b AND position = 0"), {"b": r1.json()["binding_id"]})
        await conn.commit()
    r = await client.get(
        f"/composition-spatial-bindings/{r1.json()['binding_id']}")
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_m13_bind_13(client):
    """M13-BIND:13 — freeze-versus-authority-change conflict, forced
    deterministically at the in-fence seam for both a PI target and a
    CreativeEntity A4 target change (concurrent proofs in RACE:06/07)."""
    from soloring.production_world import binding as binding_svc

    b = await _binding_base(client, tag=b"bind13", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    eid = await make_entity(client, b["project_id"])
    await _adopt(client, cid, b["occurrences"][1],
                 {"kind": "creative_entity", "creative_entity_id": eid})

    # PI A4 target appears after the prefence derivation: the entry set
    # changes (composition-owned -> authority-bound) => hash conflict
    async def seam():
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
            json={"occurrence_id": b["occurrences"][0],
                  "requirement": "required"})
        assert r.status_code == 201

    binding_svc.PREFENCE_SEAM = seam
    try:
        r = await _publish(client, b["C"], w["revision"]["id"])
        assert r.status_code == 409, r.text
        assert r.json()["error_code"] == (
            "COMPOSITION_SPATIAL_BINDING_CONFLICT")
    finally:
        binding_svc.PREFENCE_SEAM = None

    # CreativeEntity-side change: a new applicable EntityTrack for an
    # adopted CE subject (frozen R7's CE-side eligibility change) — the
    # CE entry set changes from empty to entity_track
    async def seam2():
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/tracks",
            json={"entity_id": eid, "requirement": "required"})
        assert r.status_code == 201

    binding_svc.PREFENCE_SEAM = seam2
    try:
        r = await _publish(client, b["C"], w["revision"]["id"])
        assert r.status_code == 409, r.text
        assert r.json()["error_code"] == (
            "COMPOSITION_SPATIAL_BINDING_CONFLICT")
    finally:
        binding_svc.PREFENCE_SEAM = None


async def test_m13_bind_14(client):
    """M13-BIND:14 — the historical binding reader ignores current
    mapping changes after publication."""
    b = await _binding_base(client, tag=b"bind14", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "production_instance"})
    r = await _publish(client, b["C"], w["revision"]["id"])
    binding_id = r.json()["binding_id"]
    # current authority evolves: a new adoption changes today's candidate
    await _adopt(client, cid, b["occurrences"][1],
                 {"kind": "production_instance"})
    r = await client.get(f"/composition-spatial-bindings/{binding_id}")
    assert r.status_code == 200, r.text
    assert len(r.json()["subjects"]) == 1  # exact captured value
    # but current readiness sees the changed candidate
    from soloring.production_world.binding import (
        binding_current_status, read_binding,
    )
    engine = client._transport.app.state.engine
    stored = await read_binding(
        _session_of(client), binding_id)
    async with engine.connect() as conn:
        complete, stale = await binding_current_status(
            conn, composition_revision_id=b["C"],
            spatial_world_revision_id=w["revision"]["id"],
            stored_value=stored_value_of(stored))
    assert complete is False
    assert stale[0]["code"] == "BINDING_STALE_SUBJECT_SET_CHANGED"


def stored_value_of(stored: dict) -> dict:
    return {
        "schema_version": 1,
        "composition_revision": {
            "revision_id": stored["composition_revision_id"],
            "snapshot_hash": stored["composition_revision_hash"]},
        "spatial_world_revision": {
            "revision_id": stored["spatial_world_revision_id"],
            "snapshot_hash": stored["spatial_world_revision_hash"]},
        "subjects": stored["subjects"], "entries": stored["entries"],
    }


def _session_of(client):
    from sqlalchemy.ext.asyncio import AsyncSession

    class _S:
        bind = client._transport.app.state.engine

    return _S()  # read_binding only uses session.bind


async def test_m13_bind_16(client):
    """M13-BIND:16 — zero-subject binding is legal and canonical."""
    b = await _binding_base(client, tag=b"bind16")
    w = await _approved_world(client, b["project_id"])
    r = await _readiness(client, b["C"], w["revision"]["id"])
    assert r.json()["ready"] is True
    assert r.json()["subject_summaries"] == []
    r = await _publish(client, b["C"], w["revision"]["id"])
    assert r.status_code == 201, r.text
    assert r.json()["subjects"] == [] and r.json()["entries"] == []


async def test_m13_bind_17(client):
    """M13-BIND:17 — CE A4 classification reuses/proves exact M10
    semantics: fixed frames come from the verified revision snapshot and
    track authority from applicable active tracks (resolver P0-1)."""
    b = await _binding_base(client, tag=b"bind17")
    eid = await make_entity(client, b["project_id"])
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": "d"}})
    erid = r.json()["id"]
    w = await _approved_world(
        client, b["project_id"],
        frames=(("f", (0, 0, 0), (eid, erid)),))
    r = await client.post(f"/spatial-worlds/{w['world']['id']}/tracks",
                          json={"entity_id": eid, "requirement": "optional"})
    assert r.status_code == 201
    track_id = r.json()["id"]
    engine = client._transport.app.state.engine
    from soloring.spatial.targets import (
        classify_entity_a4_targets,
        load_world_revision_with_world,
    )
    async with engine.connect() as conn:
        world = await load_world_revision_with_world(
            conn, spatial_world_revision_id=w["revision"]["id"])
        out = await classify_entity_a4_targets(
            conn, world=world, entity_ids=[eid])
    # exactly the resolver's authority: one snapshot frame + one active
    # track, ordered by (kind, id)
    assert out[eid] == [
        {"kind": "entity_fixed_frame", "id": w["fids"]["f"]},
        {"kind": "entity_track", "id": track_id}]


async def test_m13_bind_05(client):
    """M13-BIND:05 — exactly one A4 target ⇒ exactly one entry."""
    b = await _binding_base(client, tag=b"bind05")
    w = await _approved_world(client, b["project_id"])
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": b["occurrences"][0],
              "requirement": "required"})
    assert r.status_code == 201
    track_id = r.json()["id"]
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is True
    assert len(out["entry_summaries"]) == 1
    assert out["entry_summaries"][0]["placement"] == {
        "kind": "production_instance_track", "id": track_id}


async def test_m13_bind_12(client):
    """M13-BIND:12 — identical publication converges on one identity
    (the forced-concurrent interleaving is RACE:09)."""
    b = await _binding_base(client, tag=b"bind12")
    w = await _approved_world(client, b["project_id"])
    r1 = await _publish(client, b["C"], w["revision"]["id"])
    assert r1.status_code == 201
    r2 = await _publish(client, b["C"], w["revision"]["id"])
    assert r2.status_code == 200
    assert r1.json()["binding_id"] == r2.json()["binding_id"]
    assert r1.json()["binding_hash"] == r2.json()["binding_hash"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM composition_spatial_bindings "
            "WHERE composition_revision_id = :c"),
            {"c": b["C"]})).scalar_one()
    assert n == 1


async def test_m13_bind_15(client):
    """M13-BIND:15 — an adoption for an occurrence absent from the exact
    bound revision is excluded from the candidate."""
    b = await _binding_base(client, tag=b"bind15")
    w = await _approved_world(client, b["project_id"])
    # adopt an occurrence minted AFTER the bound revision was published
    m = await mint(client, b["composition_id"],
                   b["production_revision_id"], 1, name="Later")
    await _adopt(client, b["composition_id"], m["occurrence_id"],
                 {"kind": "production_instance"})
    r = await _readiness(client, b["C"], w["revision"]["id"])
    out = r.json()
    assert out["ready"] is True
    assert out["subject_summaries"] == []
