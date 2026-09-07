"""M13 M12-impact integration proofs (frozen R3 §30.6 M13-IMPACT:01-08)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m13_seed import (
    make_composition,
    make_entity,
    mint,
    remove_occurrence,
    fork_occurrence,
    seed_base,
)
from tests.test_m13_binding import (
    _adopt,
    _approved_world,
    _binding_base,
    _publish,
)

SCOPE = "composition_working_state"


async def _preview(client, cid, kind, sources, specs=()):
    r = await client.post(
        f"/compositions/{cid}/identity-operations/preview",
        json={"scope": SCOPE,
              "request": {"kind": kind, "source_occurrence_ids": sources,
                          "target_working_specs": list(specs)}})
    assert r.status_code == 200, r.text
    return r.json()


async def _apply(client, cid, version, kind, sources, pv, specs=()):
    r = await client.post(
        f"/compositions/{cid}/identity-operations",
        json={"scope": SCOPE, "expected_working_version": version,
              "expected_request_fingerprint": pv["request_fingerprint"],
              "expected_impact_fingerprint": pv["impact_fingerprint"],
              "request": {"kind": kind, "source_occurrence_ids": sources,
                          "target_working_specs": list(specs)}})
    return r


async def _pi_feature(client, oid, key="fallen"):
    r = await client.post(
        f"/production-instances/{oid}/features",
        json={"key": key, "kind": "status", "value_type": "text",
              "name": "Fallen"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_m13_impact_01():
    """M13-IMPACT:01 — FK inventory includes the exact M13 occurrence
    consumers (structurally re-derived by M12-BOUNDARY:05)."""
    from soloring.composition.impacts import FK_CONSUMERS

    families = {
        "composition_occurrence_authority_subjects",
        "production_instance_features",
        "production_instance_spatial_tracks",
        "shot_revision_production_instance_feature_states",
        "shot_revision_production_instance_spatial_states",
    }
    tables = {t for (t, _) in FK_CONSUMERS}
    assert families <= tables
    assert FK_CONSUMERS[
        ("composition_occurrence_authority_subjects", "occurrence_id")] == (
        "adoption/non-blocking")
    assert FK_CONSUMERS[
        ("shot_revision_production_instance_feature_states",
         "occurrence_id")] == "historical/non-blocking"


async def test_m13_impact_02(client):
    """M13-IMPACT:02 — active PI Feature blocks termination."""
    b = await _binding_base(client, tag=b"imp02")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    fid = await _pi_feature(client, oid)
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is False
    assert pv["live_blocking_references"] == [
        {"consumer": "production_instance_feature", "id": fid,
         "occurrence_id": oid}]
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409, r.text
    assert r.json()["details"]["reason"] == "live_references"
    # clearing the blocker (soft delete) unblocks termination
    r = await client.delete(f"/production-instance-features/{fid}")
    assert r.status_code == 200
    await remove_occurrence(client, cid, oid, 1)


async def test_m13_impact_03(client):
    """M13-IMPACT:03 — active PI Track blocks termination; fork is not
    blocked by live state."""
    b = await _binding_base(client, tag=b"imp03")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    w = await _approved_world(client, b["project_id"])
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "required"})
    assert r.status_code == 201
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is False
    assert [x["consumer"] for x in pv["live_blocking_references"]] == [
        "production_instance_spatial_track"]
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409
    # fork does not terminate and is never blocked by live state
    pv = await _preview(
        client, cid, "fork", [oid],
        specs=[{"display_name": "Forked",
                "source": {"kind": "production_revision",
                           "revision_id": b["production_revision_id"]},
                "visible": True,
                "transform": {"translation_mm": [0, 0, 0],
                              "rotation_udeg": [0, 0, 0]}}])
    assert pv["allowed"] is True


async def test_m13_impact_04(client):
    """M13-IMPACT:04 — a current Shot selection through the binding
    blocks termination of every promoted authority-subject occurrence."""
    b = await _binding_base(client, tag=b"imp04")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    w = await _approved_world(client, b["project_id"])
    pr = await _publish(client, b["C"], w["revision"]["id"])
    assert pr.status_code == 201
    binding_id = pr.json()["binding_id"]
    # a Shot selects the exact binding
    r = await client.post(f"/projects/{b['project_id']}/shots",
                          json={"subject": "s"})
    shot_id = r.json()["id"]
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is False
    assert [x["consumer"] for x in pv["live_blocking_references"]] == [
        "shot_production_world_selection"]
    assert pv["live_blocking_references"][0]["shot_id"] == shot_id
    assert pv["live_blocking_references"][0]["binding_id"] == binding_id
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409


async def test_m13_impact_05(client):
    """M13-IMPACT:05 — historical binding/Shot rows do not block current
    identity evolution."""
    b = await _binding_base(client, tag=b"imp05")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    w = await _approved_world(client, b["project_id"])
    pr = await _publish(client, b["C"], w["revision"]["id"])
    assert pr.status_code == 201  # immutable binding exists, never selected
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is True
    assert pv["live_blocking_references"] == []
    out = await remove_occurrence(client, cid, oid, 1)
    assert out["kind"] == "remove"


async def test_m13_impact_06(client):
    """M13-IMPACT:06 — any blocker addition changes the impact
    fingerprint and forces a fresh preview (stale_impact under fence)."""
    b = await _binding_base(client, tag=b"imp06")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is True
    # a live blocker appears after the preview
    await _pi_feature(client, oid)
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409, r.text
    assert r.json()["details"]["reason"] == "stale_impact"


async def test_m13_impact_07(client):
    """M13-IMPACT:07 — fork remains legal with live state and the target
    receives no copied M13 authority."""
    b = await _binding_base(client, tag=b"imp07")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    fid = await _pi_feature(client, oid)
    out = await fork_occurrence(
        client, cid, oid, b["production_revision_id"], 1)
    target = out["target_occurrence_ids"][0]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        copied = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_instance_features "
            "WHERE occurrence_id = :o"), {"o": target})).scalar_one()
        adopted = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "composition_occurrence_authority_subjects "
            "WHERE occurrence_id = :o"), {"o": target})).scalar_one()
        src_feature = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_instance_features "
            "WHERE occurrence_id = :o"), {"o": oid})).scalar_one()
    assert copied == 0 and adopted == 0
    assert src_feature == 1  # the source keeps its live authority


async def test_m13_impact_08(client):
    """M13-IMPACT:08 — no new selection can be established against a
    terminated bound subject (§22.5 symmetry, order-determined branch)."""
    b = await _binding_base(client, tag=b"imp08")
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    w = await _approved_world(client, b["project_id"])
    pr = await _publish(client, b["C"], w["revision"]["id"])
    binding_id = pr.json()["binding_id"]
    r = await client.post(f"/projects/{b['project_id']}/shots",
                          json={"subject": "s"})
    shot_id = r.json()["id"]
    # selection established, then removed; termination succeeds
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 200
    r = await client.request(
        "DELETE", f"/shots/{shot_id}/production-world-selection",
        json={"expected_binding_id": binding_id})
    assert r.status_code == 200, r.text
    await remove_occurrence(client, cid, oid, 1)
    # a NEW selection on the same binding is rejected: a bound subject is
    # terminated (the concurrent interleaving is RACE:11)
    r = await client.put(
        f"/shots/{shot_id}/production-world-selection",
        json={"binding_id": binding_id, "expected_binding_id": None})
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "PRODUCTION_WORLD_BINDING_STALE"
    assert r.json()["details"]["terminated_occurrences"] == [oid]
