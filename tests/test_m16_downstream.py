"""M16-D downstream adoption obligations: ENTITY:04, RELATION:04 downstream
half, INSTANCE:05 — adopted consequences feed later Shot state."""

from __future__ import annotations

from tests.m16_seed_b import (
    assign_shot,
    event,
    get_intra,
    post_event,
    put_relation_transition,
    seed_feature_world,
    seed_relation_world,
    state,
)
from tests.test_m16_adoption import _adopt_direct


async def _later_shot(factory, pid, eid):
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    sid2 = (await shot_svc.create_shot(
        factory(), pid, ShotCreate(subject="later",
                                   duration_ms=4000))).id
    await assign_shot(factory, pid, sid2, name="later scene")
    d = None
    return sid2


def _rel(active):
    return {"active": active}


async def test_entity_04(client, factory):
    """ENTITY:04 — an adopted entity-feature Shot/end transition feeds a
    later Shot's start state."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.domain import projects as project_svc

    base = await seed_feature_world(client, factory)
    sid, fid, pid = (base["shot_id"], base["feature_id"],
                     base["project_id"])
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r = await _adopt_direct(client, sid, ev)
    assert r.status_code == 200, r.text

    sid2 = await _later_shot(factory, pid, base["entity_id"])
    d = None
    engine = client._transport.app.state.engine
    from soloring.domain.shots import read_shot_detail

    detail = await read_shot_detail(engine, sid2)
    # the later Shot resolves the adopted fresh state at its start via
    # the ordinary M7 resolver (this is the downstream-feed proof)
    r2 = await client.put(
        f"/shots/{sid2}/semantic-dependencies",
        json={"dependencies": [{"entity_id": base["entity_id"],
                                "role": "subject"}]})
    assert r2.status_code == 200, r2.text
    # a later event chaining FROM fresh proves the start state
    ev2 = await post_event(
        client, sid2,
        event(fid, 500, state("fresh"), state("healing")))
    proj2 = await get_intra(client, sid2)
    assert proj2["intra_shot_ready"] is True


async def test_relation_04(client, factory):
    """RELATION:04 — an adopted persistent relation handoff's exact
    active/inactive state survives downstream (later Shot resolves the
    adopted terminal relation state)."""
    base = await seed_relation_world(client, factory)
    sid, rid = base["shot_id"], base["relation_id"]
    ev = await post_event(
        client, sid,
        event(rid, 1000, _rel(False), _rel(True),
              kind="entity_relation", persistence="require_handoff"))
    await put_relation_transition(client, rid, sid, st="active")
    proj = await get_intra(client, sid)
    r = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 200, r.text
    # a later Shot chaining from the ADOPTED active relation proves the
    # downstream feed
    sid2 = await _later_shot(factory, base["project_id"],
                              base["subject_id"])
    d = await client.put(
        f"/shots/{sid2}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": base["subject_id"], "role": "subject"},
            {"entity_id": base["object_id"], "role": "object"}]})
    assert d.status_code == 200, d.text
    ev2 = await post_event(
        client, sid2,
        event(rid, 500, _rel(True), _rel(False),
              kind="entity_relation"))
    proj2 = await get_intra(client, sid2)
    assert proj2["intra_shot_ready"] is True
    assert proj2["terminal_targets"][0]["terminal_state"] == _rel(False)


async def test_instance_05(client, factory):
    """INSTANCE:05 — an adopted PI-feature Shot/end transition feeds the
    SAME occurrence downstream (via the real M13 world fixtures)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from tests.test_m13_shot_capture import _full_m13_world, _select_binding
    from tests.test_m16_instance import _pi_event, _pi_world

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
    # the same occurrence still resolves with the adopted fallen state
    # (the current world resolver picks up the A2 transition)
    proj2 = await get_intra(client, b["shot"])
    assert proj2["intra_shot_ready"] is True
    assert proj2["handoffs"][0]["matched"] is True
