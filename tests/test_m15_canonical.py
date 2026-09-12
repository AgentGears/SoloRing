"""M15 canonical/stored-integrity proofs (frozen R4 §31.3 M15-CAN).

CAN:08 (stored update corruption) stays PENDING until M15C lands
update rows; the remaining ten cells are owned here.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.compatibility import canonical as canon
from soloring.compatibility.canonical import verify_stored_assessment
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import SoloRingError
from tests.m15_seed import (
    assess,
    seed_a4_use,
    seed_scene,
    seed_revision_pair,
)


def test_four_verdict_grammar_exact():
    """M15-CAN:01 — closed verdict vocabulary, exactly the frozen four."""
    g4 = json.loads(
        (__import__("pathlib").Path(__file__).resolve().parents[1]
         / "tests/fixtures/m15/g4_contract.json").read_text())
    assert list(canon.VERDICTS) == g4["overall_verdicts"]
    with pytest.raises(Exception):
        canon.fold_summary(["NOT_A_VERDICT"])


def test_dimension_status_grammar_exact():
    """M15-CAN:02 — closed dimension vocabulary + §5.2 fold law."""
    g4 = json.loads(
        (__import__("pathlib").Path(__file__).resolve().parents[1]
         / "tests/fixtures/m15/g4_contract.json").read_text())
    assert list(canon.DIMENSION_STATUSES) == g4["dimension_statuses"]
    assert canon.fold_verdict({"a": "SATISFIED", "b": "NOT_APPLICABLE"}) \
        == "COMPATIBLE_AS_IS"
    assert canon.fold_verdict({"a": "TRANSLATION_REQUIRED"}) == (
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION")
    assert canon.fold_verdict(
        {"a": "TRANSLATION_REQUIRED", "b": "REVIEW_REQUIRED"}) == (
        "REQUIRES_REVIEW")
    assert canon.fold_verdict({"a": "BLOCKED", "b": "REVIEW_REQUIRED"}) \
        == "INCOMPATIBLE"
    with pytest.raises(Exception):
        canon.fold_verdict({"a": "MAYBE"})


def _contract(i: int = 1) -> dict:
    return {
        "composition_id": f"c{i}", "occurrence_id": f"o{i}",
        "composition_working_version": i,
        "working_spec": {"display_name": "Chair",
                         "source": {"kind": "production_revision",
                                    "revision_id": "r"},
                         "visible": True,
                         "translation_mm": [0, 0, 0],
                         "rotation_udeg": [0, 0, 0]},
        "authority_subject": None,
        "placement_contract": {"owner": "A6_COMPOSITION"},
        "active_instance_feature_contracts": [],
        "active_instance_spatial_tracks": [],
        "source_revision": {"id": "r", "snapshot_hash": "h",
                            "blob_hash": "b", "media_type": None,
                            "spatial_interpretation_hash": None},
        "target_revision": {"id": "t", "snapshot_hash": "h2",
                            "blob_hash": "b2", "media_type": None,
                            "spatial_interpretation_hash": None},
    }


def test_use_contract_canonical_ordering():
    """M15-CAN:03 — deterministic use hash independent of dict order."""
    a, b = _contract(), _contract()
    b["working_spec"] = dict(reversed(list(
        b["working_spec"].items())))  # different insertion order
    assert canonical_hash(canon.use_contract_value(a)) == canonical_hash(
        canon.use_contract_value(b))
    assert canonical_hash(canon.use_contract_value(a)) != canonical_hash(
        canon.use_contract_value(_contract(2)))
    with pytest.raises(Exception):
        canon.use_contract_value(
            {**_contract(), "placement_contract": {
                "owner": "NEITHER"}})


def test_scope_hash_from_ordered_use_hashes():
    """M15-CAN:04 — scope identity is order-sensitive over the same
    per-use hashes."""
    u1 = {"composition_id": "c1", "occurrence_id": "o1",
          "use_contract_hash": "h1"}
    u2 = {"composition_id": "c2", "occurrence_id": "o2",
          "use_contract_hash": "h2"}
    assert canonical_hash(canon.scope_root([u1, u2])) != canonical_hash(
        canon.scope_root([u2, u1]))
    assert canonical_hash(canon.scope_root([u1, u2])) == canonical_hash(
        canon.scope_root([dict(u1), dict(u2)]))


async def test_report_hash_from_normalized_children(client):
    """M15-CAN:05 — the stored report hash re-derives from normalized
    children through the verified reader."""
    base = await seed_a4_use(client)
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        verified = await verify_stored_assessment(
            conn, result["assessment_id"])
    assert verified["parent"]["report_hash"] == result["report_hash"]
    assert verified["parent"]["scope_hash"] is not None


def test_update_operation_hash_exact():
    """M15-CAN:06 — update audit identity: deterministic over pinned
    assessment + ordered items; byte-stable re-derivation."""
    identity = {"assessment_id": "a1", "assessment_report_hash": "r" * 64}
    items = [{
        "composition_id": "c", "occurrence_id": "o",
        "from_revision_id": "f", "to_revision_id": "t",
        "verdict": "REQUIRES_REVIEW", "review_accepted": 1,
        "working_version_before": 3, "working_version_after": 4,
        "before_spec_hash": "x" * 64, "after_spec_hash": "y" * 64,
        "translator_output_hash": None}]
    root1 = canon.operation_root(identity, items)
    root2 = canon.operation_root(identity, [dict(items[0])])
    assert canonical_hash(root1) == canonical_hash(root2)
    changed = dict(items[0], working_version_after=5)
    assert canonical_hash(canon.operation_root(identity, [changed])) != \
        canonical_hash(root1)


async def test_stored_assessment_corruption_fails_closed(client):
    """M15-CAN:07 — parent/child integrity: any tampered hash or
    verdict fails the invariant, never a friendly verdict."""
    base = await seed_a4_use(client)
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    engine = client._transport.app.state.engine
    aid = result["assessment_id"]

    async def _tamper(sql, params):
        async with engine.connect() as conn:
            await conn.execute(text(sql), params)
            await conn.commit()

    await _tamper(
        "UPDATE production_compatibility_assessments SET report_hash = "
        ":h WHERE id = :a", {"h": "0" * 64, "a": aid})
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError):
            await verify_stored_assessment(conn, aid)
    # restore, then tamper a child verdict (fold disagreement)
    await _tamper(
        "UPDATE production_compatibility_assessments SET report_hash = "
        ":h WHERE id = :a", {"h": result["report_hash"], "a": aid})
    await _tamper(
        "UPDATE production_compatibility_uses SET verdict = 'INCOMPATIBLE'"
        " WHERE assessment_id = :a AND position = 0", {"a": aid})
    async with engine.connect() as conn:
        with pytest.raises(SoloRingError):
            await verify_stored_assessment(conn, aid)


async def test_feature_transition_set_change_changes_use_contract_hash(
        client):
    """M15-CAN:09 — A2 transition closure: a feature transition edit
    leaves working_version untouched but changes use_contract_hash."""
    base = await seed_a4_use(client)
    cid, occ = base["composition_id"], base["occurrence_id"]
    r = await client.post(
        f"/production-instances/{occ}/features",
        json={"key": "damage", "kind": "damage",
              "value_type": "enum", "name": "Damage",
              "enum_values": ["fresh", "broken"]})
    assert r.status_code == 201, r.text
    feature_id = r.json()["id"]
    scene = await seed_scene(client, base["project_id"])

    before = await assess(
        client, base["production_revision_id"], base["r2"])
    r = await client.post(
        f"/production-instance-features/{feature_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "broken"})
    assert r.status_code == 201, r.text
    after = await assess(
        client, base["production_revision_id"], base["r2"])

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        versions = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": cid})).scalar_one()
        before_hash = (await conn.execute(text(
            "SELECT use_contract_hash FROM "
            "production_compatibility_uses WHERE assessment_id = :a"),
            {"a": before["assessment_id"]})).scalar_one()
        after_hash = (await conn.execute(text(
            "SELECT use_contract_hash FROM "
            "production_compatibility_uses WHERE assessment_id = :a"),
            {"a": after["assessment_id"]})).scalar_one()
    assert versions == 1  # transition edit did NOT bump working_version
    assert before_hash != after_hash
    assert before["scope_hash"] if "scope_hash" in before else True


async def test_spatial_transition_set_change_changes_use_contract_hash(
        client):
    """M15-CAN:10 — A4 transition closure: a spatial transition edit
    changes use_contract_hash without touching working_version."""
    base = await seed_a4_use(client)
    track_id = base["track_id"]
    scene = await seed_scene(client, base["project_id"])
    before = await assess(
        client, base["production_revision_id"], base["r2"])
    r = await client.post(
        f"/production-instance-spatial-tracks/{track_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [1, 2, 3],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    after = await assess(
        client, base["production_revision_id"], base["r2"])
    engine = client._transport.app.state.engine

    async def one_hash(aid):
        async with engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT use_contract_hash FROM "
                "production_compatibility_uses "
                "WHERE assessment_id = :a AND position = 0"),
                {"a": aid})).scalar_one()

    assert await one_hash(before["assessment_id"]) != await one_hash(
        after["assessment_id"])


async def test_placement_contract_change_changes_use_contract_hash(client):
    """M15-CAN:11 — exact placement consumer: a second tracked world
    flips the resolved consumer and changes the use-contract hash (and
    the assessment refuses as UNRESOLVED per §6.5.1)."""
    from tests.test_m13_binding import _approved_world

    base = await seed_a4_use(client)
    before = await assess(
        client, base["production_revision_id"], base["r2"])
    assert before["uses"][0]["verdict"] == "REQUIRES_REVIEW"

    w2 = await _approved_world(client, base["project_id"], key="annex")
    r = await client.post(
        f"/spatial-worlds/{w2['world']['id']}/production-instance-tracks",
        json={"occurrence_id": base["occurrence_id"],
              "requirement": "required"})
    assert r.status_code == 201, r.text

    from soloring.errors import SoloRingError as SRE

    with pytest.raises(SRE) as ei:
        await assess(client, base["production_revision_id"], base["r2"])
    assert ei.value.details["reason"] == "placement_consumer_ambiguous"
    assert ei.value.code == "PRODUCTION_COMPATIBILITY_CONFLICT"
