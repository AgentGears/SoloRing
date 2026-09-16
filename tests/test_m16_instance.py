"""M16:INSTANCE — Production Instance fold against the selected M13 world.

B-eligible cells only: cell 04 (captured schema-6 plane) is M16-C and
cell 05 (adopted transition feeding downstream) is M16-D.
"""

from __future__ import annotations

from soloring.domain.canonical import canonical_hash

from tests.m16_seed_b import get_intra
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
