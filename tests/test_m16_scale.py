"""M16:SCALE — resolver query/count bounds and paging (frozen R6 §5.4)."""

from __future__ import annotations

import json

from sqlalchemy import text

from soloring.continuity.intra_shot_canonical import (
    event_storage,
    state_storage,
)
from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)


async def _feature_meta(engine, fid):
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT f.id, f.entity_id, f.key, f.kind, f.value_type, "
            "f.unit, f.enum_values_json, e.project_id FROM "
            "continuity_features f JOIN creative_entities e "
            "ON e.id = f.entity_id WHERE f.id = :i"), {"i": fid})).one()
    return {"id": row.id, "entity_id": row.entity_id, "key": row.key,
            "kind": row.kind, "value_type": row.value_type,
            "unit": row.unit, "enum_values_json": row.enum_values_json,
            "project_id": row.project_id}


async def _insert_events(engine, shot_id, fid, meta, count, *,
                         start_time=1, id_base=0):
    """Bulk-insert minimal legal canonical events via one executemany."""
    rows = []
    prev = None
    for n in range(count):
        t = start_time + n
        after_value = "fresh" if n % 2 == 0 else "healing"
        before, bj, bh = state_storage(
            "entity_feature", state(prev), meta)
        after, aj, ah = state_storage(
            "entity_feature", state(after_value), meta)
        prev = after_value
        ev, ej, eh = event_storage(
            time_ms=t, ordinal=0,
            target={"kind": "entity_feature", "id": fid},
            before=before, after=after, persistence_mode="transient")
        rows.append({
            "id": f"00000000-0000-4000-8000-{id_base + n:012d}",
            "shot": shot_id,
            "t": t, "o": 0, "tk": "entity_feature", "ef": fid,
            "er": None, "pf": None, "bj": bj, "bh": bh, "aj": aj,
            "ah": ah, "pm": "transient", "ej": ej, "eh": eh})
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO shot_intra_shot_events "
            "(id, shot_id, time_ms, ordinal, target_kind, entity_feature_id, "
            "entity_relation_id, production_instance_feature_id, "
            "before_state_json, before_state_hash, after_state_json, "
            "after_state_hash, persistence_mode, source_kind, "
            "source_proposal_id, event_json, event_hash, created_at, "
            "updated_at) VALUES "
            "(:id,:shot,:t,:o,:tk,:ef,:er,:pf,:bj,:bh,:aj,:ah,:pm,"
            "'authored',NULL,:ej,:eh,"
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"), rows)


async def _count_resolver_statements(engine, session_maker, shot_id):
    from soloring.continuity.intra_shot_resolver import (
        resolve_intra_shot_read,
    )

    count = 0

    def bump(*args, **kwargs):
        nonlocal count
        count += 1

    from sqlalchemy import event as sa_event

    sa_event.listen(engine.sync_engine, "before_cursor_execute", bump)
    try:
        session = session_maker()
        try:
            await resolve_intra_shot_read(session, shot_id)
        finally:
            await session.close()
    finally:
        sa_event.remove(engine.sync_engine, "before_cursor_execute", bump)
    return count


async def test_scale_01(client, factory):
    """A write above 10,000 active events is rejected with the stable code."""
    base = await seed_feature_world(
        client, factory, duration=20_001)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    meta = await _feature_meta(engine, fid)
    await _insert_events(engine, sid, fid, meta, 10_000)
    r = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 20_000, state("fresh"), state("healing")))
    assert r.status_code == 409, r.text
    assert "INTRA_SHOT_EVENT_LIMIT_EXCEEDED" in r.text


async def test_scale_02(client, factory):
    """The resolver uses <=20 SQL statements, independent of N (1..10,000)."""
    from tests.conftest import make_tracked_maker

    base = await seed_feature_world(client, factory, duration=20_001)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    meta = await _feature_meta(engine, fid)

    counts = {}
    for n in (1, 100, 1_000, 10_000):
        async with engine.begin() as conn:
            await conn.execute(text(
                "DELETE FROM shot_intra_shot_events WHERE shot_id = :s"),
                {"s": sid})
        await _insert_events(engine, sid, fid, meta, n)
        counts[n] = await _count_resolver_statements(engine, maker, sid)
    assert max(counts.values()) <= 20, counts
    assert len(set(counts.values())) == 1, (
        f"resolver statement count is not N-independent: {counts}")
    # the projection stays correct at the ceiling
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"][:3]
    assert proj["event_set_hash"] is not None


async def test_scale_03(client, factory):
    """10,000 minimal legal events resolve with no per-event query growth.

    The N+1 guard: statement counts at N=10,000 equal those at N=100 for
    the same target shape (set-oriented loads only)."""
    from tests.conftest import make_tracked_maker

    base = await seed_feature_world(
        client, factory, duration=20_001,
        extra_feature_keys=("wardrobe",))
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    meta = await _feature_meta(engine, fid)

    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM shot_intra_shot_events WHERE shot_id = :s"),
            {"s": sid})
    await _insert_events(engine, sid, fid, meta, 100)
    small = await _count_resolver_statements(engine, maker, sid)

    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM shot_intra_shot_events WHERE shot_id = :s"),
            {"s": sid})
    await _insert_events(engine, sid, fid, meta, 10_000)
    big = await _count_resolver_statements(engine, maker, sid)
    assert big == small, (small, big)

    proj = await get_intra(client, sid)
    assert len(proj["events"]) == 100  # default page
    assert proj["next_cursor"] == 100
    rest = await get_intra(client, sid, cursor=9_900)
    assert len(rest["events"]) == 100
    assert rest["next_cursor"] is None


async def test_scale_04(client, factory):
    """Event list paging: default 100, maximum 500, cursor advances."""
    base = await seed_feature_world(client, factory, duration=1200)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    meta = await _feature_meta(engine, fid)
    await _insert_events(engine, sid, fid, meta, 700)

    default = await get_intra(client, sid)
    assert len(default["events"]) == 100
    assert default["next_cursor"] == 100

    big = await get_intra(client, sid, limit=500)
    assert len(big["events"]) == 500
    assert big["next_cursor"] == 500

    over = await client.get(
        f"/shots/{sid}/intra-shot", params={"limit": 501})
    assert over.status_code == 422, over.text

    last = await get_intra(client, sid, limit=500, cursor=500)
    assert len(last["events"]) == 200
    assert last["next_cursor"] is None


def test_scale_fixture_canonical_columns_only():
    """The bulk fixture itself never bypasses canonical storage laws."""
    meta = {"value_type": "enum", "enum_values_json":
            json.dumps(["fresh", "healing", "scarred"])}
    before, bj, bh = state_storage("entity_feature", state(), meta)
    after, aj, ah = state_storage("entity_feature", state("fresh"), meta)
    ev, ej, eh = event_storage(
        time_ms=1, ordinal=0,
        target={"kind": "entity_feature", "id":
                "00000000-0000-4000-8000-000000000000"},
        before=before, after=after, persistence_mode="transient")
    assert bh != ah and eh is not None and len(eh) == 64


async def test_scale_resolver_overflow_fails_closed(client, factory):
    """A >10,000-active-event database (only reachable through corrupt
    direct storage) is detected, never folded or hashed as valid."""
    base = await seed_feature_world(client, factory, duration=30_000)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    meta = await _feature_meta(engine, fid)
    await _insert_events(engine, sid, fid, meta, 10_000)
    # one more active row beyond the ceiling, directly (the writer
    # refuses this state; storage-level corruption must fail closed)
    await _insert_events(engine, sid, fid, meta, 1, start_time=29_999,
                      id_base=10_000)

    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is False
    codes = [i["code"] for i in proj["intra_shot_issues"]]
    assert codes == ["INTRA_SHOT_EVENT_LIMIT_EXCEEDED"]
    assert proj["event_set_hash"] is None
    assert proj["terminal_targets"] == []
    assert proj["handoffs"] == []
    assert len(proj["events"]) == 100  # bounded, paged stored identities

    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["intra_shot_ready"] is False
    assert detail["working_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None
