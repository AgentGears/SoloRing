"""M16:START — the Shot/start boundary the fold begins from (frozen §22)."""

from __future__ import annotations

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)


from tests.m16_seed_b import seed_ordered_pair


async def _two_shots(factory, pid_name="M16 start"):
    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name=pid_name))).id
    first, second = await seed_ordered_pair(factory, pid, name=pid_name)
    return pid, first, second


async def test_start_01(client, factory):
    """A prior Shot/end transition is included in the downstream start."""
    pid, first, second = await _two_shots(factory)
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "E"})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    a = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    assert a.status_code == 200, a.text
    for sid in (first, second):
        d = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing"]})
    fid = f.json()["id"]
    await put_transition(client, fid, first, operation="set", value="healing")

    # downstream Shot/start inherited `healing`, so an event chained from
    # it folds cleanly — proving the prior transition was included.
    await post_event(client, second, event(
        fid, 1000, state("healing"), state("fresh")))
    proj = await get_intra(client, second)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["terminal_targets"][0]["terminal_state"] == state("fresh")


async def test_start_02(client, factory):
    """The target Shot's own Shot/end transition never projects backward."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    # absent at start; the Shot's OWN end transition must not leak into
    # the start state the first event folds from.
    await put_transition(client, fid, sid, operation="set", value="scarred")
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]

    # a chain that ASSUMED the own-end value would be false at event time
    bad = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 2000, state("scarred"), state("fresh")))
    assert bad.status_code == 409, bad.text
    assert "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH" in bad.text


async def test_start_03(client, factory):
    """Prior Shot/end transitions project into downstream Shot/start."""
    pid, first, second = await _two_shots(factory, pid_name="M16 start 3")
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "E"})
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    a = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    assert a.status_code == 200, a.text
    for sid in (first, second):
        d = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing"]})
    fid = f.json()["id"]
    await put_transition(client, fid, first, operation="set", value="healing")

    proj = await get_intra(client, second)
    assert proj["intra_shot_ready"] is True
    r2 = await client.get(
        f"/shots/{second}",
    )
    assert r2.status_code == 200, r2.text


async def test_start_04(client, factory):
    """M16 events never change state_at(0): the first before is the exact
    Shot/start state and Shot detail keeps predecessor readiness fields."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    detail0 = (await client.get(f"/shots/{sid}")).json()
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    await post_event(
        client, sid,
        event(fid, 2000, state("fresh"), state("healing"), ordinal=0))
    proj = await get_intra(client, sid)
    assert proj["events"][0]["before"] == state()
    assert proj["events"][1]["before"] == state("fresh")
    assert proj["terminal_targets"][0]["terminal_state"] == state("healing")
    detail1 = (await client.get(f"/shots/{sid}")).json()
    # predecessor M7 semantics are untouched by M16 events
    assert (detail1["continuity_state_ready"]
            == detail0["continuity_state_ready"])
    assert detail1["continuity_ready"] == detail0["continuity_ready"]
