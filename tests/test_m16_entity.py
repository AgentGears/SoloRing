"""M16:ENTITY — entity-feature fold eligibility and start fidelity (§22).

B-eligible cells only: cells 03/04 (captured history, adopted downstream
transition) are owned by the M16-C/M16-D slices.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)


async def test_entity_01(client, factory):
    """An entity-feature target must be an explicit Shot dependency."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import projects as project_svc
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="M16 entity1"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="x", duration_ms=5000))).id
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "X"})
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing"]})
    fid = f.json()["id"]
    # NO semantic dependency wiring: the target is not a Shot dependency

    rejected = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 1000, state(), state("fresh")))
    assert rejected.status_code == 409, rejected.text
    assert "INTRA_SHOT_TARGET_INVALID" in rejected.text


async def test_entity_02(client, factory):
    """The fold preserves Shot/start then changes state at event time."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    await post_event(
        client, sid, event(fid, 2000, state("fresh"), state("healing")))
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["events"][0]["before"] == state()  # exact Shot/start
    assert proj["events"][0]["after"] == state("fresh")
    assert proj["events"][1]["before"] == state("fresh")
    assert proj["terminal_targets"][0]["terminal_state"] == state("healing")


async def test_entity_05(client, factory):
    """The current terminal state never projects back to Shot/start."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import projects as project_svc
    from soloring.domain import shots as shot_svc

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    pid = base["project_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))

    # a downstream Shot in the same project: its start must NOT see the
    # first Shot's M16 terminal state (no handoff exists).
    async with factory() as s:
        second = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="b", duration_ms=5000))).id
    d = await client.put(
        f"/shots/{second}/semantic-dependencies",
        json={"dependencies": [{"entity_id": base["entity_id"],
                                "role": "subject"}]})
    assert d.status_code == 200, d.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        dep = (await conn.execute(text(
            "SELECT scene_id FROM shots WHERE id = :s"), {"s": second})
        ).scalar_one_or_none()
    assert dep is None  # unassigned downstream Shot
    proj = await get_intra(client, second)
    assert proj["intra_shot_ready"] is True  # event-free: no M16 claim
    # the first Shot's terminal state is its own current authority only
    first = await get_intra(client, sid)
    assert first["terminal_targets"][0]["terminal_state"] == state("fresh")


async def test_entity_03_captured_type_unit_is_historical(client, factory):
    """ENTITY:03 — the captured feature type/unit is historical: a
    current schema edit never alters the captured target identity."""
    import json

    from sqlalchemy import text as _text

    from tests.test_m16_capture import _capture, _snap_json

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    engine = client._transport.app.state.engine
    snap = json.loads(await _snap_json(engine, revision.id))
    identity = snap["intra_shot"]["events"][0]["target_identity"]
    assert identity["value_type"] == "enum"
    assert identity["unit"] is None

    # current definition moves; the captured identity does not
    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE continuity_features SET value_type = 'integer', "
            "unit = 'mm', enum_values_json = NULL WHERE id = :f"),
            {"f": fid})
    snap2 = json.loads(await _snap_json(engine, revision.id))
    identity2 = snap2["intra_shot"]["events"][0]["target_identity"]
    assert identity2 == identity

    # and the historical read still verifies against the frozen fields
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["intra_shot"]["events"][0]["target_identity"] == identity
