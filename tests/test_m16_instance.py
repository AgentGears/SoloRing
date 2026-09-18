"""M16:INSTANCE — Production Instance fold against the selected M13 world."""

from __future__ import annotations

import json

from soloring.domain.canonical import canonical_hash

from tests.m16_seed_b import state, get_intra
from tests.test_m13_shot_capture import _full_m13_world, _select_binding


def _state(value=None):
    if value is None:
        return {"present": False}
    return {"present": True, "value": value,
            "value_hash": canonical_hash(value)}


def _pi_event(fid, t, before, after, *, persistence="transient"):
    return {
        "time_ms": t, "ordinal": 0,
        "target": {"kind": "production_instance_feature", "id": fid},
        "before": before, "after": after,
        "persistence_mode": persistence,
    }


async def _pi_world(client, *, tag=b"m16-inst"):
    b = await _full_m13_world(client, tag=tag)
    sel = await _select_binding(client, b)
    f = await client.post(
        f"/production-instances/{sel['occurrence_id']}/features",
        json={"key": "condition", "kind": "damage", "value_type": "enum",
              "name": "Condition", "enum_values": ["upright", "fallen"]})
    assert f.status_code == 201, f.text
    return b, sel, f.json()["id"]


async def test_instance_01(client):
    """A PI event resolves the exact occurrence's production_instance
    authority subject and folds over the selected world state."""
    b, sel, fid = await _pi_world(client, tag=b"m16-inst1")
    r = await client.post(
        f"/shots/{b['shot']}/intra-shot/events",
        json=_pi_event(fid, 1000, _state(), _state("fallen")))
    assert r.status_code == 201, r.text
    proj = await get_intra(client, b["shot"])
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["terminal_targets"][0]["target"] == {
        "kind": "production_instance_feature", "id": fid}
    assert proj["terminal_targets"][0]["terminal_state"] == _state("fallen")


async def test_instance_02(client):
    """A PI event requires the occurrence inside the selected binding."""
    b, sel, fid = await _pi_world(client, tag=b"m16-inst2")
    # unselect the binding: the current Production World plane is gone
    u = await client.request(
        "DELETE", f"/shots/{b['shot']}/production-world-selection",
        json={"expected_binding_id": sel["binding_id"]})
    assert u.status_code == 200, u.text
    rejected = await client.post(
        f"/shots/{b['shot']}/intra-shot/events",
        json=_pi_event(fid, 1000, _state(), _state("fallen")))
    assert rejected.status_code == 409, rejected.text
    assert "INTRA_SHOT_TARGET_INVALID" in rejected.text


async def test_instance_03(client):
    """A PI before-state is revalidated when the binding selection moves."""
    b, sel, fid = await _pi_world(client, tag=b"m16-inst3")
    r = await client.post(
        f"/shots/{b['shot']}/intra-shot/events",
        json=_pi_event(fid, 1000, _state(), _state("fallen")))
    assert r.status_code == 201, r.text
    proj = await get_intra(client, b["shot"])
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]

    # the current selection disappears: the PI target fails closed
    u = await client.request(
        "DELETE", f"/shots/{b['shot']}/production-world-selection",
        json={"expected_binding_id": sel["binding_id"]})
    assert u.status_code == 200, u.text
    proj2 = await get_intra(client, b["shot"])
    assert proj2["intra_shot_ready"] is False
    codes = [i["code"] for i in proj2["intra_shot_issues"]]
    assert "INTRA_SHOT_TARGET_INVALID" in codes
    # the authoritative event stays visible with its stored canonical
    # identity even though its target no longer resolves
    assert [e["id"] for e in proj2["events"]] == [r.json()["id"]]
    assert proj2["events"][0]["event_hash"] == r.json()["event_hash"]
    assert proj2["event_set_hash"] is None
    assert proj2["terminal_targets"] == []
    # an M16 blocker makes the authoritative working hash unavailable
    detail = (await client.get(f"/shots/{b['shot']}")).json()
    assert detail["intra_shot_ready"] is False
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None

    # storage self-consistency precedes target-context resolution: a
    # tampered duplicated stored field on an unresolved-target event is
    # typed internal corruption, never fabricated output.
    from sqlalchemy import text as _text

    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE shot_intra_shot_events SET event_json = :j "
            "WHERE id = :e"),
            {"j": '{"schema_version":1,"tampered":true}',
             "e": r.json()["id"]})
    tampered = await client.get(f"/shots/{b['shot']}/intra-shot")
    assert tampered.status_code == 500, tampered.text
    assert "INTERNAL_INVARIANT_VIOLATION" in tampered.text


async def test_instance_06(client):
    """No CreativeEntity fallback: a creative_entity-authority occurrence
    is never a legal Production Instance event target."""
    from tests.test_m13_binding import _adopt

    b = await _full_m13_world(client, tag=b"m16-inst6")
    sel = await _select_binding(client, b)
    # an occurrence adopted as a creative_entity subject inside a second
    # composition is out of bounds for PI events
    from tests.m13_seed import make_composition, mint

    cid = await make_composition(client, b["pid"])
    m = await mint(client, cid, b["production_revision_id"], 0,
                   name="Desk clone")
    await _adopt(client, cid, m["occurrence_id"], {"kind": "creative_entity", "creative_entity_id": b["eva"]})
    f = await client.post(
        f"/production-instances/{m['occurrence_id']}/features",
        json={"key": "condition", "kind": "damage", "value_type": "enum",
              "name": "Condition", "enum_values": ["upright", "fallen"]})
    # M13 refuses shadow Production Instance state for a creative_entity
    # occurrence, and M16-B adds no fallback: no PI feature id exists, so
    # no Production-Instance event target can ever be minted for it.
    assert f.status_code == 422, f.text
    assert "creative_entity" in f.text


async def test_instance_05(client, factory):
    """INSTANCE:05 — an adopted PI-feature Shot/end transition feeds the
    SAME occurrence downstream: a later Shot selecting the same binding
    resolves the adopted fallen state at its start (no re-mint, no
    Production Revision replacement, no CreativeEntity substitution)."""
    b, sel, fid = await _pi_world(client, tag=b"m16-inst5")
    created = await client.post(
        f"/shots/{b['shot']}/intra-shot/events",
        json=_pi_event(fid, 1000, state(), state("fallen"),
                       persistence="require_handoff"))
    assert created.status_code == 201, created.text
    t = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "shot", "anchor_id": b["shot"],
              "boundary": "end", "operation": "set", "value": "fallen"})
    assert t.status_code == 201, t.text
    proj = await get_intra(client, b["shot"])
    r = await client.post(
        f"/intra-shot/events/{created.json()['id']}/persistence/adopt",
        json={"expected_event_hash": created.json()["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 200, r.text
    # the adoption matched on the originating Shot
    proj2 = await get_intra(client, b["shot"])
    assert proj2["handoffs"][0]["matched"] is True

    # the downstream proof: a LATER Shot selects the SAME binding — the
    # same occurrence — and resolves the adopted fallen state at its
    # start (an event chaining FROM fallen is legal there)
    sid2 = await _later_pi_shot(client, factory, b, sel,
                                subject="later pi")
    later = await client.post(
        f"/shots/{sid2}/intra-shot/events",
        json=_pi_event(fid, 500, state("fallen"), state("upright")))
    assert later.status_code == 201, later.text


async def test_instance_04(client, factory):
    """INSTANCE:04 — a PI event captures the schema-6 production-world
    plane as its required lower authority: the captured target identity
    embeds composition/occurrence/production_instance subject identity
    and the predecessor continuity planes ride along unchanged."""
    from tests.test_m16_capture import _capture
    from tests.test_m16_instance import _pi_event, _pi_world
    from tests.test_m16_capture import _companion_children

    b, sel, fid = await _pi_world(client, tag=b"m16-inst4")
    sid = b["shot"]
    ev = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=_pi_event(fid, 1000, state(), state("fallen")))
    assert ev.status_code == 201, ev.text
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 7
    block = snap["intra_shot"]
    packed = block["events"][0]
    identity = packed["target_identity"]
    assert identity["kind"] == "production_instance_feature"
    assert identity["feature_id"] == fid
    assert identity["occurrence_id"] == sel["occurrence_id"]
    from sqlalchemy import text as _text

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        comp = (await conn.execute(_text(
            "SELECT composition_id FROM "
            "production_instance_features WHERE id = :f"),
            {"f": fid})).scalar_one()
    assert identity["composition_id"] == comp
    assert identity["authority_subject_kind"] == "production_instance"
    # the schema-6 production-world plane is the required lower
    # authority and rides along unchanged beneath schema 7
    assert snap["production_world"]["schema_version"] == 1
    assert snap["production_world"]["binding"][
        "binding_id"] == sel["binding_id"]
    # the immutable companion carries the same identity bytes
    children = await _companion_children(
        client._transport.app.state.engine, revision.id)
    assert len(children) == 1
    assert json.loads(children[0].captured_target_identity_json) == \
        identity


async def _later_pi_shot(client, factory, b, sel, *, subject):
    """A LATER Shot over the same M13 world: semantic deps + a spatial
    plan bound to the same world/axis + the SAME binding selection, so
    the same Production Instance occurrence resolves for it."""
    import json as _json

    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    from soloring.spatial import plans as plan_svc
    from tests.m16_seed_b import assign_shot
    from tests.test_m13_shot_capture import CAM

    sid = (await shot_svc.create_shot(
        factory(), b["pid"], ShotCreate(subject=subject,
                                        duration_ms=4000))).id
    await assign_shot(factory, b["pid"], sid, name=f"{subject} scene")
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": b["loc"], "role": "cast"},
            {"entity_id": b["eva"], "role": "cast"}]})
    assert d.status_code == 200, d.text
    plan = {
        "schema_version": 1,
        "spatial_world_id": b["world"]["id"],
        "camera": _json.loads(_json.dumps(CAM)),
        "blocking": [],
        "axis_constraint": {"spatial_axis_id": b["axis"]["id"],
                            "camera_side": "positive"},
    }
    await plan_svc.put_spatial_plan(
        factory(), sid, expected_plan_hash=None, plan_raw=plan)
    select = await client.put(
        f"/shots/{sid}/production-world-selection",
        json={"binding_id": sel["binding_id"],
              "expected_binding_id": None})
    assert select.status_code == 200, select.text
    return sid
