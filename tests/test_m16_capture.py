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


async def test_capture_04_event_free_bytes_identical(client, factory):
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


async def test_capture_05_event_bearing_schema_7(client, factory):
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


async def test_capture_07_handoff_semantics_excluding_uuid(client, factory):
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


async def test_capture_08_persistent_without_handoff_cannot_capture(
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


async def test_ready_05_capture_half(client, factory):
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


async def test_capture_convergence_semantic_not_audit(client, factory):
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
