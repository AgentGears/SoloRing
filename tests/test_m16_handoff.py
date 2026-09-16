"""M16:HANDOFF — owning-domain Shot/end comparison only (frozen §22).

M16-B never creates, adopts, or overwrites a transition; every handoff
fact here is an exact comparison against transitions authored through
the ordinary predecessor API.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    put_relation_transition,
    put_transition,
    seed_feature_world,
    seed_relation_world,
    state,
)


def _codes(proj):
    return [i["code"] for i in proj["intra_shot_issues"]]


async def _transition_count(client, table, target_id):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            f"SELECT COUNT(*) FROM {table} WHERE feature_id = :t"),
            {"t": target_id})).scalar_one()


async def test_handoff_01(client, factory):
    """A transient event needs no handoff."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["handoffs"] == []


async def test_handoff_02(client, factory):
    """A persistent terminal entity-feature event accepts an exact
    set handoff and an exact clear handoff."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    before = await get_intra(client, sid)
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in _codes(before)

    await put_transition(client, fid, sid, operation="set", value="fresh")
    after = await get_intra(client, sid)
    assert after["intra_shot_ready"] is True, after["intra_shot_issues"]
    assert after["handoffs"][0]["matched"] is True
    assert after["handoffs"][0]["reason"] == "exact"

    # terminal ABSENCE maps to the predecessor clear operation
    base2 = await seed_feature_world(client, factory)
    sid2, fid2 = base2["shot_id"], base2["feature_id"]
    from tests.m16_seed_b import put_transition as put_t

    await post_event(
        client, sid2, event(fid2, 1000, state(), state("fresh")))
    await post_event(
        client, sid2,
        event(fid2, 2000, state("fresh"), state(),
              persistence="require_handoff"))
    await put_t(client, fid2, sid2, operation="clear")
    proj2 = await get_intra(client, sid2)
    assert proj2["intra_shot_ready"] is True, proj2["intra_shot_issues"]
    assert proj2["handoffs"][0]["matched"] is True


async def test_handoff_03(client, factory):
    """A persistent relation event accepts exact active/inactive — the
    predecessor vocabulary has no set/clear alias for relations."""
    base = await seed_relation_world(client, factory)
    sid, rid = base["shot_id"], base["relation_id"]
    rel_state = lambda active: {"active": active}  # noqa: E731

    await post_event(
        client, sid,
        event(rid, 1000, rel_state(False), rel_state(True),
              kind="entity_relation", persistence="require_handoff"))
    await put_relation_transition(client, rid, sid, st="active")
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["handoffs"][0]["matched"] is True

    base2 = await seed_relation_world(client, factory)
    sid2, rid2 = base2["shot_id"], base2["relation_id"]
    await post_event(
        client, sid2,
        event(rid2, 1000, rel_state(False), rel_state(True),
              kind="entity_relation"))
    await post_event(
        client, sid2,
        event(rid2, 2000, rel_state(True), rel_state(False),
              kind="entity_relation", persistence="require_handoff"))
    await put_relation_transition(client, rid2, sid2, st="inactive")
    proj2 = await get_intra(client, sid2)
    assert proj2["intra_shot_ready"] is True, proj2["intra_shot_issues"]
    assert proj2["handoffs"][0]["matched"] is True


async def test_handoff_04(client, factory):
    """A persistent PI-feature event accepts an exact set/clear handoff."""
    from tests.test_m16_instance import _pi_event, _pi_world

    b, sel, fid = await _pi_world(client, tag=b"m16-handoff04")
    created = await client.post(
        f"/shots/{b['shot']}/intra-shot/events",
        json=_pi_event(fid, 1000, state(), state("fallen"),
                       persistence="require_handoff"))
    assert created.status_code == 201, created.text
    missing = await get_intra(client, b["shot"])
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in _codes(missing)

    t = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "shot", "anchor_id": b["shot"],
              "boundary": "end", "operation": "set", "value": "fallen"})
    assert t.status_code == 201, t.text
    proj = await get_intra(client, b["shot"])
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["handoffs"][0]["matched"] is True
    assert proj["handoffs"][0]["reason"] == "exact"


async def test_handoff_05(client, factory):
    """A missing handoff blocks readiness but never rejected authoring."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    created = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 1000, state(), state("fresh"),
                   persistence="require_handoff"))
    assert created.status_code == 201, created.text
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in _codes(proj)
    assert proj["handoffs"][0]["reason"] == "missing"
    assert proj["handoffs"][0]["existing"] is None
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["intra_shot_ready"] is False


async def test_handoff_06(client, factory):
    """A transition for a different target never satisfies this target."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("other",))
    sid = base["shot_id"]
    fid, other = base["feature_id"], base["other_feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(
        client, other, sid, operation="set", value="irrelevant")
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    assert "INTRA_SHOT_HANDOFF_REQUIRED" in _codes(proj)


async def test_handoff_07(client, factory):
    """A semantically different active handoff blocks readiness."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="healing")
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    assert "INTRA_SHOT_HANDOFF_MISMATCH" in _codes(proj)
    assert proj["handoffs"][0]["reason"] == "mismatch"


async def test_handoff_08(client, factory):
    """An exact preexisting handoff converges without any duplicate."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    n0 = await _transition_count(client, "continuity_feature_transitions",
                                 fid)
    for _ in range(3):
        proj = await get_intra(client, sid)
        assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    n1 = await _transition_count(client, "continuity_feature_transitions",
                                 fid)
    assert n0 == n1 == 1


async def test_handoff_09(client, factory):
    """A conflicting active handoff is never overwritten by a read."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    tr = await put_transition(
        client, fid, sid, operation="set", value="healing")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row_before = (await conn.execute(text(
            "SELECT id, operation, value_json, value_hash, updated_at "
            "FROM continuity_feature_transitions WHERE id = :i"),
            {"i": tr["id"]})).one()
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    async with engine.connect() as conn:
        row_after = (await conn.execute(text(
            "SELECT id, operation, value_json, value_hash, updated_at "
            "FROM continuity_feature_transitions WHERE id = :i"),
            {"i": tr["id"]})).one()
    assert tuple(row_before) == tuple(row_after)
