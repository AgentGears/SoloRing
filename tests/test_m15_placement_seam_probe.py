"""M15A placement seam probe — working/published twin oracle (frozen
R5 §31.1 M15-BASE:10).

Wiring/load-congruence proof: the M15 working-state classification
(outcomes produced through the SINGLE shared pure classifier loaded by
the M15 I/O adapter) agrees with the published M13 derive_candidate
path (the same shared classifier, published loading) wherever both are
defined. Neither oracle authorizes a second classifier; the
pinned-M14 baseline behavior oracle is M15-BASE:09.
"""

from __future__ import annotations

from sqlalchemy import text

from soloring.compatibility.evaluator import (
    resolve_placement_consumer,
)
from soloring.compatibility.canonical import DIMENSIONS
from soloring.production_world.binding import (
    _load_composition_revision,
    derive_candidate,
)
from soloring.spatial.targets import load_world_revision_with_world
from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation


async def _working_outcome(conn, *, cid, occ, revision):
    row = (await conn.execute(text(
        "SELECT composition_id, occurrence_id, production_revision_id, "
        "x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg FROM "
        "composition_working_occurrences "
        "WHERE composition_id = :c AND occurrence_id = :o"),
        {"c": cid, "o": occ})).one()
    subject_row = (await conn.execute(text(
        "SELECT subject_kind FROM "
        "composition_occurrence_authority_subjects "
        "WHERE composition_id = :c AND occurrence_id = :o"),
        {"c": cid, "o": occ})).one_or_none()
    subject = None
    if subject_row is not None:
        subject = {"kind": subject_row.subject_kind, "id": occ,
                   "valid": True}
    interp_row = (await conn.execute(text(
        "SELECT interpretation_hash FROM "
        "production_revision_spatial_interpretations "
        "WHERE production_revision_id = :r"),
        {"r": row.production_revision_id})).scalar_one_or_none()
    return await resolve_placement_consumer(
        conn, working_row=row, subject=subject, revision=revision,
        source_interpretation_hash=interp_row)


async def test_working_state_twin_oracle_matches_published_shared_classifier(
        client):
    """M15-BASE:10 — the working/published twin oracle through the one
    shared classifier: UNIQUE_A6/A4/UNRESOLVED outcomes agree with the
    published derive_candidate classification of the published twin."""
    engine = client._transport.app.state.engine
    base = await seed_base(client, tag=b"m15-probe-a")
    pid = base["project_id"]
    prid1 = base["production_revision_id"]
    prid2 = await seed_second_revision(client, base, number=2)
    cid = await make_composition(client, pid)

    occ_a = (await mint(client, cid, prid1, 0, name="Chair A"))[
        "occurrence_id"]  # → UNIQUE_A4
    occ_b = (await mint(client, cid, prid1, 1, name="Chair B"))[
        "occurrence_id"]  # → CLEAN_A6
    occ_c = (await mint(client, cid, prid2, 2, name="Chair C"))[
        "occurrence_id"]  # → UNRESOLVED (interpretation missing)
    pub = await publish(client, cid, 3)
    twin = pub["revision"]["revision_id"]

    w1 = await _approved_world(client, pid, key="lobby")
    interp = await _interpretation(client, prid1, translation=(10, 0, 0))
    await _adopt(client, cid, occ_a, {"kind": "production_instance"})
    await _adopt(client, cid, occ_c, {"kind": "production_instance"})
    approved1 = w1["revision"]["id"]

    r = await client.post(
        f"/spatial-worlds/{w1['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_a, "requirement": "required"})
    assert r.status_code == 201, r.text
    track_a = r.json()["id"]
    r = await client.post(
        f"/spatial-worlds/{w1['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_c, "requirement": "required"})
    assert r.status_code == 201, r.text

    revision = {"project_id": pid, "blob_hash": "verified"}
    async with engine.connect() as conn:
        out_a = await _working_outcome(
            conn, cid=cid, occ=occ_a, revision=revision)
        assert out_a["outcome"] == "UNIQUE_A4", out_a
        contract = out_a["placement_contract"]
        assert contract["spatial_world_id"] == w1["world"]["id"]
        assert contract["spatial_world_revision_id"] == approved1
        assert contract["spatial_world_revision_hash"] == (
            w1["revision"]["snapshot_hash"])
        assert contract["target_kind"] == "production_instance_track"
        assert contract["target_id"] == track_a

        out_b = await _working_outcome(
            conn, cid=cid, occ=occ_b, revision=revision)
        assert out_b == {"outcome": "CLEAN_A6"}, out_b

        out_c = await _working_outcome(
            conn, cid=cid, occ=occ_c, revision=revision)
        assert out_c["outcome"] == "UNRESOLVED"
        assert out_c["reason"] == "BINDING_SPATIAL_INTERPRETATION_REQUIRED"

        # published twin through the SAME shared classifier
        c = await _load_composition_revision(conn, twin)
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=approved1)
        value, issues = await derive_candidate(conn, c=c, w=w)
        assert issues == [{
            "code": "BINDING_SPATIAL_INTERPRETATION_REQUIRED",
            "occurrence_id": occ_c,
            "production_revision_id": prid2}], issues
        entries = {e["occurrence_id"]: e for e in value["entries"]}
        assert occ_a in entries
        assert entries[occ_a]["placement"] == {
            "kind": "production_instance_track", "id": track_a}
        assert entries[occ_a]["spatial_interpretation_hash"] == (
            interp["interpretation_hash"])
        assert occ_b not in entries
        assert occ_c not in entries

    # interpretation for prid2 flips occ_c to UNIQUE_A4 (dynamics)
    await _interpretation(client, prid2, translation=(0, 5, 0))
    async with engine.connect() as conn:
        out_c = await _working_outcome(
            conn, cid=cid, occ=occ_c, revision=revision)
        assert out_c["outcome"] == "UNIQUE_A4", out_c
        c = await _load_composition_revision(conn, twin)
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=approved1)
        value, issues = await derive_candidate(conn, c=c, w=w)
        assert not issues, issues
        assert any(e["occurrence_id"] == occ_c for e in value["entries"])

    # multi-world ambiguity → UNRESOLVED, never A6 fallback
    w2 = await _approved_world(client, pid, key="annex")
    r = await client.post(
        f"/spatial-worlds/{w2['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_a, "requirement": "required"})
    assert r.status_code == 201, r.text
    async with engine.connect() as conn:
        out_a = await _working_outcome(
            conn, cid=cid, occ=occ_a, revision=revision)
        assert out_a["outcome"] == "UNRESOLVED"
        assert out_a["reason"] == "multi_world_context"
        # each single-context published derivation still resolves
        for approved in (approved1, w2["revision"]["id"]):
            c = await _load_composition_revision(conn, twin)
            w = await load_world_revision_with_world(
                conn, spatial_world_revision_id=approved)
            value, issues = await derive_candidate(conn, c=c, w=w)
            assert not issues, issues
            assert any(e["occurrence_id"] == occ_a for e in value["entries"])
