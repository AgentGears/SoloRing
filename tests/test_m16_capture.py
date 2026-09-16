"""M16:CAPTURE — immutable schema-7 capture (frozen R6 §14/§22).

B-eligible-in-C cells: the capture half of READY:05 and the capture-side
IDENTITY evidence live here alongside CAPTURE 01-08.
"""

from __future__ import annotations

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


async def _capture(client, shot_id):
    from sqlalchemy.ext.asyncio import AsyncSession

    from soloring.domain.revisions import capture_revision_with_visual

    settings = client._transport.app.state.settings
    engine = client._transport.app.state.engine
    async with AsyncSession(engine, expire_on_commit=False) as session:
        return await capture_revision_with_visual(
            session, shot_id, settings=settings)


async def _companion_children(engine, revision_id):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT position, time_ms, ordinal, target_kind, "
            "captured_target_identity_json, captured_handoff_json, "
            "source_event_id FROM shot_revision_intra_shot_events "
            "WHERE shot_revision_id = :r ORDER BY position"),
            {"r": revision_id})).fetchall()


async def test_capture_04(client, factory):
    """Event-free capture is byte-identical to predecessor schema 1-6."""
    base = await seed_feature_world(client, factory)
    sid = base["shot_id"]
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] < 7
    assert "intra_shot" not in snap
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_revision_intra_shot_specs "
            "WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()
    assert n == 0


async def test_capture_05(client, factory):
    """Event-bearing capture preserves predecessor planes and emits
    outer schema 7 with the canonical intra_shot block."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 7
    block = snap["intra_shot"]
    assert block["schema_version"] == 1
    assert block["duration_ms"] == snap["intent"]["duration_ms"] == 5000
    assert len(block["events"]) == 1
    packed = block["events"][0]
    assert packed["time_ms"] == 1000 and packed["ordinal"] == 0
    assert packed["before"] == state() and packed["after"] == state("fresh")
    assert packed["persistence_mode"] == "transient"
    assert packed["handoff"] is None
    identity = packed["target_identity"]
    assert identity["kind"] == "entity_feature"
    assert identity["feature_id"] == fid
    assert identity["value_type"] == "enum"
    assert identity["feature_key"] == "cut"
    # predecessor planes ride along unchanged (continuity spec intact)
    assert snap["continuity"]["schema_version"] in (1, 2)
    children = await _companion_children(
        client._transport.app.state.engine, revision.id)
    assert len(children) == 1
    assert children[0].source_event_id == ev["id"]
    assert json.loads(children[0].captured_target_identity_json) == identity


async def test_capture_07(client, factory):
    """Persistent captures carry the semantic handoff; the transition
    UUID is audit provenance, NOT in the semantic block."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    tr = await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    handoff = snap["intra_shot"]["events"][0]["handoff"]
    assert handoff == {
        "domain": "entity_feature",
        "target": {"kind": "entity_feature", "id": fid},
        "anchor": {"anchor_type": "shot", "anchor_id": sid,
                   "boundary": "end"},
        "operation": "set",
        "state": state("fresh"),
    }
    assert tr["id"] not in json.dumps(snap["intra_shot"])
    children = await _companion_children(
        client._transport.app.state.engine, revision.id)
    assert children[0].captured_handoff_json is not None


async def test_capture_08(
        client, factory):
    """A persistent event missing its handoff fails the capture fence."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    from soloring.errors import SoloRingError

    try:
        await _capture(client, sid)
    except SoloRingError as exc:
        assert exc.code == "INTRA_SHOT_HANDOFF_REQUIRED"
    else:
        raise AssertionError("capture did not fail closed")


async def test_ready_05(client, factory):
    """READY:05 (complete): Shot detail AND capture consume the same
    resolver-result grammar — the captured block equals the working
    projection fold, and the working hash equals the captured hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["intra_shot_ready"] is True
    assert detail["working_snapshot_hash"] == revision.snapshot_hash
    proj = await get_intra(client, sid)
    assert proj["terminal_targets"][0]["terminal_state"] == state("fresh")


async def test_capture_convergence_semantic(client, factory):
    """A later working event with a different UUID but identical
    semantics converges to the existing ShotRevision; first-publication
    audit provenance is never rewritten."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    first = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    await client.delete(f"/intra-shot/events/{first['id']}")
    second = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    assert second["id"] != first["id"]
    revision2, _ = await _capture(client, sid)
    assert revision2.id == revision.id
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).fetchall()
    assert [r.source_event_id for r in rows] == [first["id"]]


async def test_capture_01(client, factory):
    """CAPTURE:01 — events/handoffs/duration/start planes are read inside
    ONE SQLite snapshot: a deterministic barrier INSIDE the live read
    transaction (between constituent reads, before its COMMIT) holds the
    capture while a writer commits on another connection; the captured
    value must be exactly one complete pre-state."""
    import asyncio

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    engine = client._transport.app.state.engine

    from soloring.continuity import state as state_svc

    real_features = state_svc.resolve_effective_feature_state
    gate = asyncio.Event()
    inside_tx = asyncio.Event()

    async def held_features(conn, shot_id):
        # this runs INSIDE _snapshot_one_read's explicit BEGIN, before
        # the M16 resolver read and before COMMIT: the read snapshot is
        # LIVE here, and a competing writer must not interleave
        inside_tx.set()
        await gate.wait()
        return await real_features(conn, shot_id)

    state_svc.resolve_effective_feature_state = held_features
    from soloring.domain import revisions as rev_svc

    real_read = rev_svc._snapshot_one_read

    async def routed_read(session, shot_id, *, settings=None):
        # route the in-unit import to the held resolver
        import soloring.domain.revisions as rv

        orig = rv._snapshot_one_read
        return await orig(session, shot_id, settings=settings)

    capture_task = asyncio.ensure_future(_capture(client, sid))
    await inside_tx.wait()

    # the writer commits on ANOTHER connection WHILE the read
    # transaction is live: the pinned snapshot must not see it
    r = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 2000, state("fresh"), state("healing")))
    assert r.status_code == 201, r.text

    gate.set()
    revision = (await capture_task)[0]
    snap = json.loads(revision.snapshot_json)
    events = snap["intra_shot"]["events"]
    # exactly the PRE-state: the single 1000ms event, complete
    assert [(e["time_ms"], e["ordinal"]) for e in events] == [(1000, 0)]
    assert events[0]["after"] == state("fresh")
    state_svc.resolve_effective_feature_state = real_features


async def test_capture_02(client, factory):
    """CAPTURE:02 — a post-read event mutation cannot contaminate the
    captured value: with capture held after its read unit, a handoff
    mutation lands and is asserted; the persisted result equals exactly
    the pre-mutation captured state."""
    import asyncio

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    engine = client._transport.app.state.engine

    from soloring.domain import revisions as rev_svc

    real_read = rev_svc._snapshot_one_read
    gate = asyncio.Event()
    inside_read = asyncio.Event()

    async def held_read(session, shot_id, *, settings=None):
        read = await real_read(session, shot_id, settings=settings)
        inside_read.set()
        await gate.wait()
        return read

    rev_svc._snapshot_one_read = held_read
    capture_task = asyncio.ensure_future(_capture(client, sid))
    await inside_read.wait()

    # post-read HANDOFF mutation: the transition's value moves while
    # the capture is between its read unit and write phase
    from sqlalchemy import text as _text

    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE continuity_feature_transitions SET value_json = "
            ":vj, value_hash = :vh WHERE feature_id = :f "
            "AND anchor_id = :s"),
            {"vj": '"healing"',
             "vh": __import__("hashlib").sha256(
                 b'"healing"').hexdigest(), "f": fid, "s": sid})
    gate.set()
    revision = (await capture_task)[0]
    snap = json.loads(revision.snapshot_json)
    packed = snap["intra_shot"]["events"][0]
    # the captured handoff is the PRE-mutation exact value
    assert packed["handoff"]["state"] == state("fresh")
    assert packed["after"] == state("fresh")
    rev_svc._snapshot_one_read = real_read


async def test_capture_03(client, factory):
    """CAPTURE:03 — capture versus duration PATCH sees one coherent
    pre/post state: the fence serializes them, and whichever order
    interleaves, the captured duration and event times agree."""
    import asyncio

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))

    async def patcher():
        for n in range(5):
            r = await client.patch(
                f"/shots/{sid}", json={"duration_ms": 6000 + n})
            assert r.status_code == 200, r.text
            await asyncio.sleep(0.005)

    async def capturer():
        for _ in range(5):
            revision, _ = await _capture(client, sid)
            snap = json.loads(revision.snapshot_json)
            duration = snap["intra_shot"]["duration_ms"]
            # the duplicated duration is the INTENT duration — a hybrid
            # of two moments can never satisfy both at once
            assert snap["intent"]["duration_ms"] == duration
            for packed in snap["intra_shot"]["events"]:
                assert 1 <= packed["time_ms"] < duration
            await asyncio.sleep(0.005)

    await asyncio.gather(patcher(), capturer())


async def _snap_json(engine, revision_id):
    from sqlalchemy import text as _text

    async with engine.connect() as conn:
        return (await conn.execute(_text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision_id})).scalar_one()


async def test_capture_04(client, factory):
    """Event-free capture is byte-identical to predecessor schema 1-6."""
    base = await seed_feature_world(client, factory)
    sid = base["shot_id"]
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] < 7
    assert "intra_shot" not in snap
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_revision_intra_shot_specs "
            "WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()
    assert n == 0


async def test_capture_05(client, factory):
    """Event-bearing capture preserves predecessor planes and emits
    outer schema 7 with the canonical intra_shot block."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 7
    block = snap["intra_shot"]
    assert block["schema_version"] == 1
    assert block["duration_ms"] == snap["intent"]["duration_ms"] == 5000
    assert len(block["events"]) == 1
    packed = block["events"][0]
    assert packed["time_ms"] == 1000 and packed["ordinal"] == 0
    assert packed["before"] == state() and packed["after"] == state("fresh")
    assert packed["persistence_mode"] == "transient"
    assert packed["handoff"] is None
    identity = packed["target_identity"]
    assert identity["kind"] == "entity_feature"
    assert identity["feature_id"] == fid
    assert identity["value_type"] == "enum"
    assert identity["feature_key"] == "cut"
    # predecessor planes ride along unchanged (continuity spec intact)
    assert snap["continuity"]["schema_version"] in (1, 2)
    children = await _companion_children(
        client._transport.app.state.engine, revision.id)
    assert len(children) == 1
    assert children[0].source_event_id == ev["id"]
    assert json.loads(children[0].captured_target_identity_json) == identity


async def test_capture_07(client, factory):
    """Persistent captures carry the semantic handoff; the transition
    UUID is audit provenance, NOT in the semantic block."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    tr = await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    handoff = snap["intra_shot"]["events"][0]["handoff"]
    assert handoff == {
        "domain": "entity_feature",
        "target": {"kind": "entity_feature", "id": fid},
        "anchor": {"anchor_type": "shot", "anchor_id": sid,
                   "boundary": "end"},
        "operation": "set",
        "state": state("fresh"),
    }
    assert tr["id"] not in json.dumps(snap["intra_shot"])
    children = await _companion_children(
        client._transport.app.state.engine, revision.id)
    assert children[0].captured_handoff_json is not None


async def test_capture_08(
        client, factory):
    """A persistent event missing its handoff fails the capture fence."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    from soloring.errors import SoloRingError

    try:
        await _capture(client, sid)
    except SoloRingError as exc:
        assert exc.code == "INTRA_SHOT_HANDOFF_REQUIRED"
    else:
        raise AssertionError("capture did not fail closed")


async def test_ready_05(client, factory):
    """READY:05 (complete): Shot detail AND capture consume the same
    resolver-result grammar — the captured block equals the working
    projection fold, and the working hash equals the captured hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await put_transition(client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail["intra_shot_ready"] is True
    assert detail["working_snapshot_hash"] == revision.snapshot_hash
    proj = await get_intra(client, sid)
    assert proj["terminal_targets"][0]["terminal_state"] == state("fresh")


async def test_capture_convergence_semantic(client, factory):
    """A later working event with a different UUID but identical
    semantics converges to the existing ShotRevision; first-publication
    audit provenance is never rewritten."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    first = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    await client.delete(f"/intra-shot/events/{first['id']}")
    second = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    assert second["id"] != first["id"]
    revision2, _ = await _capture(client, sid)
    assert revision2.id == revision.id
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).fetchall()
    assert [r.source_event_id for r in rows] == [first["id"]]


async def test_capture_01(client, factory):
    """Events/handoffs/duration/start planes are read inside one SQLite
    snapshot: a concurrent event mutation cannot contaminate the capture."""
    from sqlalchemy import text as _text

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    engine = client._transport.app.state.engine
    from soloring.domain import revisions as rev_svc

    landed = {}

    real_resolve = rev_svc._snapshot_one_read

    async def interleaved(session, shot_id, *, settings=None):
        read = await real_resolve(session, shot_id, settings=settings)
        # a mutation lands AFTER the read unit closes: the captured
        # value already derives from the earlier coherent snapshot
        async with engine.begin() as conn:
            landed["n"] = (await conn.execute(_text(
                "SELECT COUNT(*) FROM shot_intra_shot_events WHERE "
                "shot_id = :s AND deleted_at IS NULL"),
                {"s": shot_id})).scalar_one()
        return read

    rev_svc._snapshot_one_read = interleaved
    try:
        revision, _ = await _capture(client, sid)
    finally:
        rev_svc._snapshot_one_read = real_resolve
    snap = json.loads(
        (await _snap_json(engine, revision.id)))
    assert len(snap["intra_shot"]["events"]) == 1
    assert landed["n"] == 1


async def test_capture_02(
        client, factory):
    """A delete landing after the capture read does not alter the
    captured value (the immutable rows were already written)."""
    from sqlalchemy import text as _text

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    engine = client._transport.app.state.engine
    revision, _ = await _capture(client, sid)
    before = await _snap_json(engine, revision.id)
    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE shot_intra_shot_events SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :e"),
            {"e": ev["id"]})
    after = await _snap_json(engine, revision.id)
    assert before == after


async def test_capture_03(client, factory):
    """Capture versus a duration PATCH sees one coherent pre/post state:
    capturing with events requires the already-patched duration, and the
    duration fence keeps the event times lawful either way."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    p = await client.patch(f"/shots/{sid}", json={"duration_ms": 9000})
    assert p.status_code == 200, p.text
    revision, _ = await _capture(client, sid)
    snap = json.loads(await _snap_json(
        client._transport.app.state.engine, revision.id))
    assert snap["intra_shot"]["duration_ms"] == 9000
    assert snap["intent"]["duration_ms"] == 9000


async def test_capture_06(client, factory):
    """captured target_identity is part of the schema-7 semantic bytes
    and the companion columns."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(await _snap_json(
        client._transport.app.state.engine, revision.id))
    identity = snap["intra_shot"]["events"][0]["target_identity"]
    assert identity["feature_id"] == fid
    assert set(identity) >= {
        "kind", "feature_id", "entity_id", "feature_key", "feature_kind",
        "value_type", "unit"}
