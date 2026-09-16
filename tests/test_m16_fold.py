"""M16:FOLD — deterministic fold, ordering, and event-set hash (frozen §22)."""

from __future__ import annotations

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)


async def test_fold_01(client, factory):
    """Semantic order is exactly (time_ms, ordinal)."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    await post_event(
        client, sid, event(fid, 1500, state("fresh"), state("healing")))
    await post_event(
        client, sid, event(fid, 2000, state("healing"), state("scarred")))
    proj = await get_intra(client, sid)
    times = [(e["time_ms"], e["ordinal"]) for e in proj["events"]]
    assert times == [(1000, 0), (1500, 0), (2000, 0)]
    assert proj["terminal_targets"][0]["terminal_state"] == state("scarred")


async def test_fold_02(client, factory):
    """Same-time independent targets fold deterministically."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    cut, wardrobe = base["feature_id"], base["wardrobe_feature_id"]
    await post_event(
        client, sid,
        event(wardrobe, 1000, state(), state("torn"), kind="entity_feature",
              ordinal=1))
    await post_event(
        client, sid, event(cut, 1000, state(), state("fresh"), ordinal=0))
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    coords = [(e["time_ms"], e["ordinal"]) for e in proj["events"]]
    assert coords == [(1000, 0), (1000, 1)]
    terminals = {t["target"]["id"]: t["terminal_state"]
                 for t in proj["terminal_targets"]}
    assert terminals[cut] == state("fresh")
    assert terminals[wardrobe] == state("torn")


async def test_fold_03(client, factory):
    """Same-time same-target chains follow the explicit ordinal."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh"), ordinal=0))
    await post_event(
        client, sid,
        event(fid, 1000, state("fresh"), state("healing"), ordinal=1))
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert [(e["time_ms"], e["ordinal"]) for e in proj["events"]] == [
        (1000, 0), (1000, 1)]
    assert proj["terminal_targets"][0]["terminal_state"] == state("healing")


async def test_fold_04(client, factory):
    """A drifted before-state identifies the exact event and expectation."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import projects as project_svc
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="M16 fold4"))).id
    from tests.m16_seed_b import seed_ordered_pair

    first, second = await seed_ordered_pair(factory, pid, name="M16 fold4")
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "E"})
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    for sid in (first, second):
        d = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing", "scarred"]})
    fid = f.json()["id"]

    from tests.m16_seed_b import put_transition

    await put_transition(client, fid, first, operation="set", value="healing")
    # authored against the CURRENT inherited start (healing)
    ev = await post_event(
        client, second, event(fid, 1000, state("healing"), state("fresh")))

    # upstream truth moves (first Shot's end changes to scarred)
    from soloring.domain.canonical import canonical_hash

    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE continuity_feature_transitions SET value_json=:vj, "
            "value_hash=:vh WHERE feature_id=:f AND anchor_id=:s"),
            {"vj": '"scarred"', "vh": canonical_hash("scarred"),
             "f": fid, "s": first})

    proj = await get_intra(client, second)
    assert proj["intra_shot_ready"] is False
    mismatch = [i for i in proj["intra_shot_issues"] if i["code"] ==
                "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH"]
    assert mismatch, proj["intra_shot_issues"]
    assert mismatch[0]["details"]["event_id"] == ev["id"]
    assert mismatch[0]["details"]["expected"] == state("scarred")
    assert mismatch[0]["details"]["actual"] == state("healing")


async def test_fold_05(client, factory):
    """Insertion/UUID order never alters fold order or the event-set hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    a = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    b = await post_event(
        client, sid, event(fid, 1500, state("fresh"), state("healing")))
    c = await post_event(
        client, sid, event(fid, 2000, state("healing"), state("scarred")))
    proj1 = await get_intra(client, sid)

    # storage-layer permutation: re-insert the SAME rows in reverse
    # physical order; the fold order and hash must not move
    from sqlalchemy import text as _text

    engine = client._transport.app.state.engine
    rows = None
    async with engine.connect() as conn:
        rows = (await conn.execute(_text(
            "SELECT * FROM shot_intra_shot_events WHERE shot_id = :s "
            "AND deleted_at IS NULL"), {"s": sid})).mappings().all()
    async with engine.begin() as conn:
        await conn.execute(_text(
            "DELETE FROM shot_intra_shot_events WHERE shot_id = :s"),
            {"s": sid})
        for row in reversed(rows):
            await conn.execute(_text(
                "INSERT INTO shot_intra_shot_events "
                "(id, shot_id, time_ms, ordinal, target_kind, "
                "entity_feature_id, entity_relation_id, "
                "production_instance_feature_id, before_state_json, "
                "before_state_hash, after_state_json, after_state_hash, "
                "persistence_mode, source_kind, source_proposal_id, "
                "event_json, event_hash, created_at, updated_at, "
                "deleted_at) VALUES (:id, :shot_id, :time_ms, :ordinal, "
                ":target_kind, :entity_feature_id, :entity_relation_id, "
                ":production_instance_feature_id, :before_state_json, "
                ":before_state_hash, :after_state_json, :after_state_hash, "
                ":persistence_mode, :source_kind, :source_proposal_id, "
                ":event_json, :event_hash, :created_at, :updated_at, "
                ":deleted_at)"), dict(row))
    proj2 = await get_intra(client, sid)
    assert proj1["event_set_hash"] == proj2["event_set_hash"]
    assert [(e["time_ms"], e["ordinal"]) for e in proj2["events"]] == [
        (1000, 0), (1500, 0), (2000, 0)]
    assert [e["id"] for e in proj2["events"]] == [
        a["id"], b["id"], c["id"]]


async def test_fold_06(client, factory):
    """Terminal state equals the exact final folded state."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    await post_event(
        client, sid, event(fid, 2000, state("fresh"), state("healing")))
    proj = await get_intra(client, sid)
    assert len(proj["terminal_targets"]) == 1
    t = proj["terminal_targets"][0]
    assert t["target"] == {"kind": "entity_feature", "id": fid}
    assert t["terminal_state"] == state("healing")
    assert t["terminal_event_id"] == proj["events"][-1]["id"]


async def test_fold_07(client, factory):
    """A nonterminal require_handoff marker invalidates the prospective set."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    later = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 2000, state("fresh"), state("healing")))
    assert later.status_code == 409, later.text
    assert "INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL" in later.text


async def test_fold_08(client, factory):
    """The event-set hash changes iff semantic meaning or duration changes."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    h1 = (await get_intra(client, sid))["event_set_hash"]
    # duration PATCH (lawful: still above every event time) → new hash
    p = await client.patch(
        f"/shots/{sid}", json={"duration_ms": 6000})
    assert p.status_code == 200, p.text
    h2 = (await get_intra(client, sid))["event_set_hash"]
    assert h2 is not None and h2 != h1
    # idempotent re-read → same hash
    h3 = (await get_intra(client, sid))["event_set_hash"]
    assert h3 == h2
    # semantic PATCH (time change) → new hash again
    evs = (await get_intra(client, sid))["events"]
    q = await client.patch(
        f"/intra-shot/events/{evs[0]['id']}", json={"time_ms": 1200})
    assert q.status_code == 200, q.text
    h4 = (await get_intra(client, sid))["event_set_hash"]
    assert h4 != h2
