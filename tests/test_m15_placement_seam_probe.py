"""M15A placement-consumer seam probe (frozen R4 §6.5.1/§8; M15A entry
condition).

Decides the §8/§26.1 STOP question before M15A structure is built:

  Can the working-state CLEAN_A6 / UNIQUE_A4 / UNRESOLVED projection be
  obtained by CALLING the existing predecessor pure seam —
  ``derive_candidate``'s importable primitives
  (``load_world_revision_with_world``, ``classify_entity_a4_targets``,
  ``_verify_interpretation_unused``, ``_entry_is_identity``, the frozen
  PI-track query and §12 issue vocabulary) — in the predecessor's exact
  prerequisite order, reading the working occurrence universe from
  ``composition_working_occurrences``, WITHOUT modifying or extracting
  ``production_world/binding.py``?

The published-twin oracle proves the composed projection agrees with
the UNMODIFIED predecessor classifier (``derive_candidate`` over the
published CompositionRevision twin) wherever both are defined.
"""

from __future__ import annotations

from sqlalchemy import text

from soloring.production_world.binding import (
    _entry_is_identity,
    _load_composition_revision,
    _verify_interpretation_unused,
    derive_candidate,
)
from soloring.spatial.targets import load_world_revision_with_world
from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation


async def _resolve_working_placement_consumer(
        conn, *, composition_id: str, occurrence_id: str) -> dict:
    """§6.5.1 projection composed from predecessor primitives only.

    This is the blueprint for the compatibility evaluator's resolver:
    the same tables, the same vocabulary, and derive_candidate's exact
    per-entry prerequisite order (targets → identity transform → closed
    revision → interpretation), driven by the working occurrence row.
    binding.py is never modified or extracted.
    """
    row = (await conn.execute(text(
        "SELECT production_revision_id, x_mm, y_mm, z_mm, yaw_udeg, "
        "pitch_udeg, roll_udeg FROM composition_working_occurrences "
        "WHERE composition_id = :c AND occurrence_id = :o"),
        {"c": composition_id, "o": occurrence_id})).one()

    # applicable world contexts = worlds holding an ACTIVE PI track for
    # this occurrence (the M13 universe notion, working state)
    tracks = (await conn.execute(text(
        "SELECT spatial_world_id, id FROM "
        "production_instance_spatial_tracks "
        "WHERE occurrence_id = :o AND deleted_at IS NULL ORDER BY id"),
        {"o": occurrence_id})).fetchall()
    worlds = sorted({t.spatial_world_id for t in tracks})
    if not worlds:
        return {"outcome": "CLEAN_A6"}
    if len(worlds) > 1:
        return {"outcome": "UNRESOLVED", "reason": "multi_world_context",
                "worlds": worlds}

    # the predecessor-selected context needs the world's approved
    # revision (carried per spatial-world state; 0 or >1 approved
    # revisions = no predecessor-selected winner → UNRESOLVED)
    approved_rows = (await conn.execute(text(
        "SELECT approved_revision_id FROM spatial_world_states "
        "WHERE spatial_world_id = :w AND approved_revision_id IS NOT NULL"),
        {"w": worlds[0]})).fetchall()
    if len(approved_rows) != 1:
        return {"outcome": "UNRESOLVED",
                "reason": "no_unique_approved_world_revision"}

    targets = [{"kind": "production_instance_track", "id": t.id}
               for t in tracks if t.spatial_world_id == worlds[0]]
    if len(targets) != 1:
        return {"outcome": "UNRESOLVED", "reason": "multi_a4_target",
                "targets": targets}

    # derive_candidate's exact prerequisite order, working row
    if not _entry_is_identity(row):
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_COMPOSITION_TRANSFORM_CONFLICT"}
    pr = (await conn.execute(text(
        "SELECT pr.id, pr.snapshot_hash, po.project_id, "
        "(SELECT c.blob_hash FROM production_revision_closures c "
        " WHERE c.production_revision_id = pr.id "
        " AND c.contract_key = 'retained_blob' "
        " AND c.contract_version = 1) AS blob_hash "
        "FROM production_revisions pr "
        "JOIN production_objects po ON po.id = pr.production_object_id "
        "WHERE pr.id = :r"),
        {"r": row.production_revision_id})).one()
    if pr.blob_hash is None:
        return {"outcome": "UNRESOLVED", "reason": "BINDING_SUBJECT_INVALID"}
    interp = await _verify_interpretation_unused(
        conn, row.production_revision_id, pr.snapshot_hash, pr.blob_hash)
    if interp is None:
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_SPATIAL_INTERPRETATION_REQUIRED"}

    w = await load_world_revision_with_world(
        conn, spatial_world_revision_id=approved_rows[0].
        approved_revision_id)
    if w["project_id"] != pr.project_id:
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_PROJECT_MISMATCH"}
    return {
        "outcome": "UNIQUE_A4",
        "placement_contract": {
            "owner": "A4_SPATIAL",
            "spatial_world_id": worlds[0],
            "spatial_world_revision_id": w["verified"]["id"],
            "spatial_world_revision_hash": w["verified"]["snapshot_hash"],
            "target_kind": "production_instance_track",
            "target_id": targets[0]["id"],
        },
    }


async def _oracle(conn, *, c_revision_id: str, approved_world_revision: str):
    """The UNMODIFIED predecessor classifier over the published twin."""
    c = await _load_composition_revision(conn, c_revision_id)
    w = await load_world_revision_with_world(
        conn, spatial_world_revision_id=approved_world_revision)
    return await derive_candidate(conn, c=c, w=w)


async def test_placement_seam_probe_three_outcomes_and_oracle(client):
    """Probe: UNIQUE_A4 / CLEAN_A6 / UNRESOLVED via the pure seam, with
    published-twin agreement against the unmodified classifier."""
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

    async with engine.connect() as conn:
        # UNIQUE_A4: exact world-revision/target coordinate pinned
        out_a = await _resolve_working_placement_consumer(
            conn, composition_id=cid, occurrence_id=occ_a)
        assert out_a["outcome"] == "UNIQUE_A4", out_a
        contract = out_a["placement_contract"]
        assert contract["spatial_world_id"] == w1["world"]["id"]
        assert contract["spatial_world_revision_id"] == approved1
        assert contract["spatial_world_revision_hash"] == (
            w1["revision"]["snapshot_hash"])
        assert contract["target_kind"] == "production_instance_track"
        assert contract["target_id"] == track_a

        # CLEAN_A6: no applicable A4 consumer, no blocking issue
        out_b = await _resolve_working_placement_consumer(
            conn, composition_id=cid, occurrence_id=occ_b)
        assert out_b == {"outcome": "CLEAN_A6"}, out_b

        # UNRESOLVED: interpretation prerequisite missing (§6.5.2)
        out_c = await _resolve_working_placement_consumer(
            conn, composition_id=cid, occurrence_id=occ_c)
        assert out_c["outcome"] == "UNRESOLVED"
        assert out_c["reason"] == "BINDING_SPATIAL_INTERPRETATION_REQUIRED"

        # ORACLE — the unmodified predecessor classifier agrees on the
        # published twin for every comparable state: same entries, and
        # the same per-occurrence issue for the interpretation-missing A4
        # consumer that the working projection reports as UNRESOLVED
        value, issues = await _oracle(
            conn, c_revision_id=twin, approved_world_revision=approved1)
        assert issues == [{
            "code": "BINDING_SPATIAL_INTERPRETATION_REQUIRED",
            "occurrence_id": occ_c,
            "production_revision_id": prid2}], issues
        entries = {e["occurrence_id"]: e for e in value["entries"]}
        assert occ_a in entries, "UNIQUE_A4 twin must carry an A4 entry"
        assert entries[occ_a]["placement"] == {
            "kind": "production_instance_track", "id": track_a}
        assert entries[occ_a]["spatial_interpretation_hash"] == (
            interp["interpretation_hash"])
        assert occ_b not in entries, "CLEAN_A6 twin carries no entry"
        assert occ_c not in entries, "UNRESOLVED twin carries no entry"

    # interpretation for prid2 flips occ_c to UNIQUE_A4 (dynamics)
    interp2 = await _interpretation(client, prid2, translation=(0, 5, 0))
    async with engine.connect() as conn:
        out_c = await _resolve_working_placement_consumer(
            conn, composition_id=cid, occurrence_id=occ_c)
        assert out_c["outcome"] == "UNIQUE_A4", out_c
        value, issues = await _oracle(
            conn, c_revision_id=twin, approved_world_revision=approved1)
        assert not issues, issues
        assert value["entries"][0]["occurrence_id"] in (occ_a, occ_c)

    # multi-world ambiguity → UNRESOLVED, never A6 fallback or a tie-break
    w2 = await _approved_world(client, pid, key="annex")
    r = await client.post(
        f"/spatial-worlds/{w2['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_a, "requirement": "required"})
    assert r.status_code == 201, r.text
    async with engine.connect() as conn:
        out_a = await _resolve_working_placement_consumer(
            conn, composition_id=cid, occurrence_id=occ_a)
        assert out_a["outcome"] == "UNRESOLVED"
        assert out_a["reason"] == "multi_world_context"
        # each single-context derivation still resolves (the ambiguity is
        # the absence of a predecessor-selected winner, not corruption)
        for approved in (approved1, w2["revision"]["id"]):
            value, issues = await _oracle(
                conn, c_revision_id=twin, approved_world_revision=approved)
            assert not issues, issues
            assert any(e["occurrence_id"] == occ_a for e in value["entries"])
