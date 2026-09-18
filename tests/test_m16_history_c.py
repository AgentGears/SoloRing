"""M16:HIST — schema-7 historical isolation and reconstruction (frozen §22).

B-eligible-in-C cells: HIST 03/04/09/10/11 (isolation, rebuild,
convergence provenance, corruption) plus inspector acceptance.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from tests.m16_seed_b import (
    event,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture


async def _history(client, revision_id):
    r = await client.get(f"/shot-revisions/{revision_id}/continuity")
    assert r.status_code == 200, r.text
    return r.json()


async def _event_bearing_revision(client, factory, *, persistent=False):
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence=("require_handoff" if persistent
                           else "transient")))
    if persistent:
        await put_transition(
            client, fid, sid, operation="set", value="fresh")
    revision, _ = await _capture(client, sid)
    return base, sid, fid, revision


async def test_hist_03_rebuild_from_companions_only(client, factory):
    """Schema-7 history rebuilds solely from immutable companion rows plus
    the same-revision predecessor planes."""
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    engine = client._transport.app.state.engine

    # current M16 authority and current target state move on; history
    # is consumed from companions only
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE shot_id = :s"),
            {"s": sid})
        await conn.execute(text(
            "UPDATE continuity_features SET key = 'renamed' "
            "WHERE id = :f"), {"f": fid})
    hist = await _history(client, revision.id)
    block = hist["intra_shot"]
    assert block is not None
    assert block["events"][0]["target_identity"]["feature_key"] == "cut"
    assert block["events"][0]["after"] == state("fresh")


async def test_hist_04_parent_equals_children_and_outer(client, factory):
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    hist = await _history(client, revision.id)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        parent = (await conn.execute(text(
            "SELECT spec_json, spec_hash FROM "
            "shot_revision_intra_shot_specs WHERE shot_revision_id = :r"),
            {"r": revision.id})).one()
    from soloring.domain.canonical import canonical_hash

    assert json.loads(parent.spec_json) == hist["intra_shot"]
    assert parent.spec_hash == canonical_hash(hist["intra_shot"])
    snap = json.loads(
        (await _snapshot_json(engine, revision.id)))
    assert snap["intra_shot"] == hist["intra_shot"]


async def _snapshot_json(engine, revision_id):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision_id})).scalar_one()


async def test_hist_09_current_edits_never_change_history(client, factory):
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    before = await _history(client, revision.id)
    # current duration + current transition authority move
    await client.patch(f"/shots/{sid}", json={"duration_ms": 9000})
    await put_transition(client, fid, sid, operation="set", value="healing")
    after = await _history(client, revision.id)
    assert before == after


async def test_hist_10_semantic_convergence_keeps_provenance(client, factory):
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    first = (await _history(client, revision.id))["intra_shot"]["events"][0]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        first_source = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()

    # recreate identical semantics under a new working UUID and converge
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE shot_id = :s"),
            {"s": sid})
    await post_event(
        client, sid, event(fid, 1000, state(), state("fresh")))
    revision2, _ = await _capture(client, sid)
    assert revision2.id == revision.id
    async with engine.connect() as conn:
        second_source = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()
    assert second_source == first_source
    assert (await _history(client, revision.id))["intra_shot"]["events"][
        0] == first


async def test_hist_11_companion_corruption_fails_closed(client, factory):
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_intra_shot_events SET "
            "captured_after_state_json = :j WHERE shot_revision_id = :r"),
            {"j": '{"present": false}', "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "INTERNAL_INVARIANT_VIOLATION" in r.text


async def test_hist_outer_block_corruption_fails(client, factory):
    base, sid, fid, revision = await _event_bearing_revision(client, factory)
    engine = client._transport.app.state.engine
    snap = json.loads(await _snapshot_json(engine, revision.id))
    snap["intra_shot"]["events"][0]["time_ms"] = 4242
    from soloring.domain.canonical import canonical_json_str, canonical_hash

    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_revisions SET snapshot_json = :sj, "
            "snapshot_hash = :sh WHERE id = :r"),
            {"sj": canonical_json_str(snap),
             "sh": canonical_hash(snap), "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
