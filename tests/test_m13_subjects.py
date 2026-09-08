"""M13 subject-adoption proofs (frozen R3 §30.1 M13-SUBJECT:01-08,10,11)."""

from __future__ import annotations

from tests.m13_seed import (
    SCOPE,
    fork_occurrence,
    make_composition,
    make_entity,
    mint,
    mint_nested,
    patch_source,
    publish,
    remove_occurrence,
    seed_base,
    seed_second_revision,
)


async def _adopt(client, cid, oid, body):
    return await client.post(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject",
        json=body)


async def _get(client, cid, oid):
    return await client.get(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject")


async def _world(client, tag=b"m13-subjects"):
    base = await seed_base(client, tag=tag)
    cid = await make_composition(client, base["project_id"])
    return base, cid


async def test_m13_subject_01(client):
    """M13-SUBJECT:01 — existing occurrence UUID is the PI subject id."""
    base, cid = await _world(client)
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    r = await _adopt(client, cid, oid, {"kind": "production_instance"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["subject_kind"] == "production_instance"
    assert out["subject_id"] == oid  # no second id is minted
    r = await _get(client, cid, oid)
    assert r.json()["subject_id"] == oid


async def test_m13_subject_02(client):
    """M13-SUBJECT:02 — CreativeEntity subject creates no duplicate PI."""
    base, cid = await _world(client)
    eid = await make_entity(client, base["project_id"])
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    r = await _adopt(client, cid, oid,
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["subject_kind"] == "creative_entity"
    assert out["subject_id"] == eid and out["creative_entity_id"] == eid


async def test_m13_subject_03(client):
    """M13-SUBJECT:03 — direct ProductionRevision promotion succeeds."""
    base, cid = await _world(client)
    m = await mint(client, cid, base["production_revision_id"], 0)
    r = await _adopt(client, cid, m["occurrence_id"],
                     {"kind": "production_instance"})
    assert r.status_code == 201, r.text


async def test_m13_subject_04(client):
    """M13-SUBJECT:04 — nested CompositionRevision promotion rejects."""
    base, cid = await _world(client)
    # build a second composition with one published revision
    cid2 = await make_composition(client, base["project_id"], name="Sub")
    await mint(client, cid2, base["production_revision_id"], 0)
    pub = await publish(client, cid2, 1)
    nested_rev = pub["revision"]["revision_id"]
    m = await mint_nested(client, cid, nested_rev, 0)
    r = await _adopt(client, cid, m["occurrence_id"],
                     {"kind": "production_instance"})
    assert r.status_code == 422, r.text


async def test_m13_subject_05(client):
    """M13-SUBJECT:05 — cross-Project CreativeEntity rejects."""
    base, cid = await _world(client)
    other_base = await seed_base(client, tag=b"m13-subjects-other")
    eid = await make_entity(client, other_base["project_id"])
    m = await mint(client, cid, base["production_revision_id"], 0)
    r = await _adopt(client, cid, m["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 422, r.text


async def test_m13_subject_06(client):
    """M13-SUBJECT:06 — active duplicate claim rejects; terminated claim
    releases the slot."""
    base, cid = await _world(client)
    eid = await make_entity(client, base["project_id"])
    m1 = await mint(client, cid, base["production_revision_id"], 0,
                    name="Chair A")
    m2 = await mint(client, cid, base["production_revision_id"], 1,
                    name="Chair B")
    r = await _adopt(client, cid, m1["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201, r.text
    # identical retry on the same occurrence is idempotent
    r = await _adopt(client, cid, m1["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 200, r.text
    # another ACTIVE occurrence cannot claim it
    r = await _adopt(client, cid, m2["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 409, r.text
    assert r.json()["details"]["reason"] == "creative_entity_claim_conflict"
    # terminating the holder releases the slot (adoption alone never blocks)
    await remove_occurrence(client, cid, m1["occurrence_id"], 2)
    r = await _adopt(client, cid, m2["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201, r.text
    # the terminated holder's row survives as immutable provenance
    r = await _get(client, cid, m1["occurrence_id"])
    assert r.json()["subject_kind"] == "creative_entity"
    assert r.json()["creative_entity_id"] == eid


async def test_m13_subject_07(client):
    """M13-SUBJECT:07 — rebinding/reclassification rejects."""
    base, cid = await _world(client)
    eid = await make_entity(client, base["project_id"])
    eid2 = await make_entity(client, base["project_id"], name="Other")
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    # reclassify PI -> CE
    r = await _adopt(client, cid, oid,
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 409, r.text
    assert r.json()["details"]["reason"] == "subject_adoption_conflict"
    # CE -> different CE
    r = await _adopt(client, cid, oid,
                     {"kind": "creative_entity", "creative_entity_id": eid2})
    assert r.status_code == 409, r.text
    # invalid kinds / shapes
    r = await _adopt(client, cid, oid, {"kind": "ghost"})
    assert r.status_code == 422
    r = await _adopt(client, cid, oid,
                     {"kind": "production_instance", "creative_entity_id": eid})
    assert r.status_code == 422
    r = await _adopt(client, cid, oid, {"kind": "creative_entity"})
    assert r.status_code == 422


async def test_m13_subject_08(client):
    """M13-SUBJECT:08 — terminated occurrence cannot be newly adopted."""
    base, cid = await _world(client)
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    await remove_occurrence(client, cid, oid, 1)
    r = await _adopt(client, cid, oid, {"kind": "production_instance"})
    assert r.status_code == 422, r.text


async def test_m13_subject_10(client):
    """M13-SUBJECT:10 — adoption survives same-occurrence source
    substitution; a nested-source exact-C occurrence stays excluded from
    the binding universe while the active CE claim persists."""
    base, cid = await _world(client)
    prid2 = await seed_second_revision(client, base)
    eid = await make_entity(client, base["project_id"])
    m1 = await mint(client, cid, base["production_revision_id"], 0,
                    name="Chair A")
    m2 = await mint(client, cid, base["production_revision_id"], 1,
                    name="Chair B")
    oid = m1["occurrence_id"]
    r = await _adopt(client, cid, oid,
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 201
    adopted_at = r.json()["created_at"]

    # production_revision -> production_revision: adoption survives
    await patch_source(client, cid, oid, 2, kind="production_revision",
                       revision_id=prid2)
    r = await _get(client, cid, oid)
    assert r.json()["subject_kind"] == "creative_entity"
    assert r.json()["created_at"] == adopted_at

    # production_revision -> composition_revision on a SURVIVING occurrence
    # is structurally refused by M12 itself (a source-kind switch changes
    # identity and must use replace_as_new, which mints a fresh target) —
    # the frozen §7.2 exclusion rule is therefore unreachable through the
    # predecessor surface, and the adoption row trivially persists.
    cid2 = await make_composition(client, base["project_id"], name="Sub")
    await mint(client, cid2, base["production_revision_id"], 0)
    pub = await publish(client, cid2, 1)
    r = await client.patch(
        f"/compositions/{cid}/occurrences/{oid}",
        json={"scope": SCOPE, "expected_working_version": 3,
              "source": {"kind": "composition_revision",
                         "revision_id": pub["revision"]["revision_id"]}})
    assert r.status_code == 422, r.text
    assert r.json()["details"]["identity_change_required"] is True
    # the adoption row survives the refused substitution attempt untouched
    r = await _get(client, cid, oid)
    assert r.json()["subject_kind"] == "creative_entity"
    assert r.json()["created_at"] == adopted_at
    # the active claim still blocks the other occurrence
    r = await _adopt(client, cid, m2["occurrence_id"],
                     {"kind": "creative_entity", "creative_entity_id": eid})
    assert r.status_code == 409, r.text


async def test_m13_subject_11(client):
    """M13-SUBJECT:11 — mint/fork targets begin COMPOSITION-LOCAL with no
    implicit M13 copy."""
    base, cid = await _world(client)
    eid = await make_entity(client, base["project_id"])
    m = await mint(client, cid, base["production_revision_id"], 0)
    oid = m["occurrence_id"]
    r = await _get(client, cid, oid)
    assert r.status_code == 200
    assert r.json()["subject_kind"] == "composition_local"

    # fork the adopted occurrence: the target receives no copied adoption
    await _adopt(client, cid, oid,
                 {"kind": "creative_entity", "creative_entity_id": eid})
    out = await fork_occurrence(
        client, cid, oid, base["production_revision_id"], 1)
    target = out["target_occurrence_ids"][0]
    r = await _get(client, cid, target)
    assert r.json()["subject_kind"] == "composition_local"
    # the source keeps its adoption
    r = await _get(client, cid, oid)
    assert r.json()["subject_kind"] == "creative_entity"
