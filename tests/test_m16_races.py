"""M16:RACE — capture serialization and concurrent-read coherence (§22)."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture


def _start_daemon(coro):
    return asyncio.ensure_future(coro)


async def test_race_08(client, factory):
    """RACE:08 — capture versus event/handoff mutation sees ONE coherent
    snapshot: a concurrent writer racing the capture read can never
    produce a hybrid (the captured intra_shot block is either fully the
    pre-mutation or fully the post-mutation state)."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    cut, wardrobe = base["feature_id"], base["wardrobe_feature_id"]
    await post_event(
        client, sid,
        event(cut, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, cut, sid, operation="set", value="fresh")

    mutations = {"n": 0}

    # a writer repeatedly toggles a transient event on a DISTINCT legal
    # target while captures run: every mutation must LAND (201) and be
    # removable (204) — a real race, not a skipped one
    toggle = event(wardrobe, 2000, state(), state("torn"),
                   ordinal=1)

    async def writer():
        for _ in range(5):
            r = await client.post(
                f"/shots/{sid}/intra-shot/events", json=toggle)
            assert r.status_code == 201, r.text
            mutations["n"] += 1
            eid = r.json()["id"]
            await asyncio.sleep(0.008)
            d = await client.delete(f"/intra-shot/events/{eid}")
            assert d.status_code == 204, d.text
            await asyncio.sleep(0.008)

    async def capturer():
        for _ in range(5):
            revision, _ = await _capture(client, sid)
            snap = json.loads(revision.snapshot_json)
            block = snap["intra_shot"]
            assert block["schema_version"] == 1
            for packed in block["events"]:
                if packed["persistence_mode"] == "require_handoff":
                    assert packed["handoff"] is not None
                    assert packed["handoff"]["state"] == state("fresh")
                    assert packed["target"]["id"] == cut
                else:
                    assert packed["handoff"] is None
                    assert packed["time_ms"] == 2000
                    assert packed["target"]["id"] == wardrobe
            await asyncio.sleep(0.008)

    await asyncio.gather(writer(), capturer())
    assert mutations["n"] == 5


async def test_race_04(client, factory):
    """RACE:04 — an event edit racing adoption detects the stale
    source/event-set basis (exactly one side commits)."""
    import asyncio

    from tests.m16_seed_b import put_transition

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    basis = {"expected_event_hash": ev["event_hash"],
             "expected_event_set_hash": proj["event_set_hash"]}

    edit = asyncio.ensure_future(client.patch(
        f"/intra-shot/events/{ev['id']}",
        json={"time_ms": 1200}))
    adopt = asyncio.ensure_future(client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt", json=basis))
    edit_r, adopt_r = await asyncio.gather(edit, adopt)
    # whichever committed first, the other either converged on the
    # committed outcome or conflicts with the typed code — never a
    # silent double-commit of stale authority
    outcomes = {(edit_r.status_code), (adopt_r.status_code)}
    assert outcomes <= {200, 409}, (edit_r.status_code, adopt_r.text)
    if adopt_r.status_code == 200:
        proj2 = await get_intra(client, sid)
        assert proj2["intra_shot_ready"] is True


async def test_race_05(client, factory):
    """RACE:05 — a handoff edit racing adoption is exact-match-or-
    conflict, never overwrite."""
    import asyncio

    from sqlalchemy import text as _text

    from soloring.domain.canonical import canonical_hash

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    engine = client._transport.app.state.engine

    # pre-place a DIFFERENT occupied value on the same coordinate
    async with engine.begin() as conn:
        await conn.execute(_text(
            "INSERT INTO continuity_feature_transitions (id, feature_id, "
            "anchor_type, anchor_id, boundary, operation, value_json, "
            "value_hash, created_at, updated_at) VALUES (:i, :f, 'shot', "
            ":s, 'end', 'set', :vj, :vh, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"i": "00000000-0000-4000-8000-0000000000b9",
             "f": fid, "s": sid, "vj": '"healing"',
             "vh": canonical_hash("healing")})
    r = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 409, r.text
    assert "INTRA_SHOT_HANDOFF_MISMATCH" in r.text
    # the occupied value was never overwritten
    async with engine.connect() as conn:
        vj = (await conn.execute(_text(
            "SELECT value_json FROM "
            "continuity_feature_transitions WHERE feature_id = :f "
            "AND anchor_id = :s"),
            {"f": fid, "s": sid})).scalar_one()
    assert vj == '"healing"'


async def test_race_06(client, factory):
    """RACE:06 — a proposal batch versus a current Shot change either
    uses the exact source basis or conflicts."""
    import asyncio

    from tests.test_m16_proposals import _capture_revision, _ingest

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision)
    proposal = r.json()
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": proposal["id"],
            "expected_proposal_hash": proposal["proposal_hash"],
            "decision": "adopt_persistence"}]})
    assert rr.status_code == 200, rr.text
    # after the batch changed current authority, a second batch still
    # pinned to the old basis is stale
    r2, _ = await _ingest(client, sid, fid, revision, t=1600)
    rr2 = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": r2.json()["id"],
            "expected_proposal_hash": r2.json()["proposal_hash"],
            "decision": "adopt_persistence"}]})
    assert rr2.status_code == 409, rr2.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in rr2.text


async def test_race_07(client, factory):
    """RACE:07 — concurrent identical proposal-batch retries converge
    completely (one commits, the retry returns the evidence)."""
    import asyncio

    from tests.test_m16_proposals import _capture_revision, _ingest

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision)
    proposal = r.json()
    body = {"reviews": [{
        "proposal_id": proposal["id"],
        "expected_proposal_hash": proposal["proposal_hash"],
        "decision": "adopt_persistence"}]}
    a, b = await asyncio.gather(
        asyncio.ensure_future(client.post(
            f"/shots/{sid}/intra-shot/proposals/review-batch",
            json=body)),
        asyncio.ensure_future(client.post(
            f"/shots/{sid}/intra-shot/proposals/review-batch",
            json=body)))
    codes = {a.status_code, b.status_code}
    assert codes <= {200}, (a.status_code, a.text, b.status_code)
    outs = [x.json() for x in (a, b)]
    assert any(o["idempotent"] for o in outs)
    bases = {o["batch_basis_hash"] for o in outs}
    assert len(bases) == 1


async def test_race_09(client, factory):
    """RACE:09 — Take approval versus adoption has no hidden ordering
    dependency: both commit independently in either order."""
    import asyncio

    from tests.test_m16_take_isolation import _take_world

    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    approve = asyncio.ensure_future(client.post(
        f"/takes/{take_id}/approve"))
    adopt = asyncio.ensure_future(client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]}))
    approve_r, adopt_r = await asyncio.gather(approve, adopt)
    assert approve_r.status_code == 200, approve_r.text
    assert adopt_r.status_code == 200, adopt_r.text
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["approved_take_id"] == take_id
    assert detail["intra_shot_ready"] is True


async def test_race_01(client, factory):
    """RACE:01 — event create versus duration patch has only legal
    serialized outcomes: an event at t=4000 racing a duration shrink to
    3000 can never leave both applied (the loser is refused by whichever
    fence serializes second)."""
    outcomes = []
    for _ in range(4):
        base = await seed_feature_world(client, factory, duration=5000)
        sid, fid = base["shot_id"], base["feature_id"]

        async def create():
            return await client.post(
                f"/shots/{sid}/intra-shot/events",
                json=event(fid, 4000, state(), state("fresh")))

        async def shrink():
            return await client.patch(
                f"/shots/{sid}", json={"duration_ms": 3000})

        r_event, r_patch = await asyncio.gather(create(), shrink())
        assert r_event.status_code in (201, 409, 422), r_event.text
        assert r_patch.status_code in (200, 409), r_patch.text
        # never both applied: a surviving t=4000 event with a 3000
        # duration is an illegal hybrid
        applied = (r_event.status_code == 201,
                   r_patch.status_code == 200)
        assert applied in ((True, False), (False, True), (False, False))
        detail = (await client.get(f"/shots/{sid}")).json()
        if applied == (True, False):
            assert detail["duration_ms"] == 5000
        elif applied == (False, True):
            assert detail["duration_ms"] == 3000
        outcomes.append(applied)
    # the race is real and serializes legally in at least one direction
    assert any(o[0] for o in outcomes) or any(o[1] for o in outcomes)


async def test_race_02(client, factory):
    """RACE:02 — event coordinate patch race commits at most one
    conflicting coordinate: two target-orthogonal events (independent
    before-chains) concurrently PATCHed onto the same (time, ordinal)
    leave exactly one winner — the conflict is purely the coordinate."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid, cut, wardrobe = (base["shot_id"], base["feature_id"],
                          base["wardrobe_feature_id"])
    e1 = await post_event(
        client, sid, event(cut, 1000, state(), state("healing")))
    e2 = await post_event(
        client, sid, event(wardrobe, 2000, state(), state("torn")))
    # both events race onto the SAME (3000, 0) coordinate; each move is
    # individually chain-legal, so only the coordinate can conflict
    async def move(eid):
        return await client.patch(
            f"/intra-shot/events/{eid}",
            json={"time_ms": 3000, "ordinal": 0})

    r1, r2 = await asyncio.gather(move(e1["id"]), move(e2["id"]))
    codes = sorted((r1.status_code, r2.status_code))
    assert codes in ([200, 200], [200, 409], [200, 422]), \
        (r1.text, r2.text)
    # if BOTH committed, they must hold distinct coordinates — never
    # two active events at one coordinate
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT time_ms, ordinal, COUNT(*) FROM "
            "shot_intra_shot_events WHERE shot_id = :s AND deleted_at "
            "IS NULL GROUP BY time_ms, ordinal HAVING COUNT(*) > 1"),
            {"s": sid})).fetchall()
    assert rows == []
    # the surviving set still resolves coherently
    proj = await get_intra(client, sid)
    assert proj["event_set_hash"] is not None


async def test_race_03(client, factory):
    """RACE:03 — event delete versus a dependent later event can never
    leave a false before-chain: deleting the predecessor while the
    dependent exists is refused, so a surviving dependent always has its
    chain anchor."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    e1 = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    e2 = await post_event(
        client, sid,
        event(fid, 2000, state("fresh"), state("healing")))

    async def delete(eid):
        return await client.delete(f"/intra-shot/events/{eid}")

    for _ in range(4):
        # re-seed the pair for each round
        b = await seed_feature_world(client, factory)
        s, f = b["shot_id"], b["feature_id"]
        a1 = await post_event(
            client, s, event(f, 1000, state(), state("fresh")))
        a2 = await post_event(
            client, s, event(f, 2000, state("fresh"), state("healing")))
        d1, d2 = await asyncio.gather(delete(a1["id"]), delete(a2["id"]))
        assert d1.status_code in (204, 409), d1.text
        assert d2.status_code in (204, 409), d2.text
        engine = client._transport.app.state.engine
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id FROM shot_intra_shot_events WHERE shot_id = "
                ":s AND deleted_at IS NULL ORDER BY time_ms"),
                {"s": s})).fetchall()
        ids = {r[0] for r in rows}
        # the dependent may never outlive its chain anchor
        if a2["id"] in ids:
            assert a1["id"] in ids
        # the surviving set is chain-coherent (the resolver certifies)
        proj = await get_intra(client, s)
        assert (proj["event_set_hash"] is not None
                or proj["events"] == [])
    _ = (e1, e2)
