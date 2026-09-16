"""M16:HIST — the frozen owner file for schema-7 historical proofs.

This module carries the C-owned HIST cells under their frozen exact
owners. The supplementary regression file ``test_m16_history_c.py``
remains as additional development evidence; the frozen-owner cells live
here.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.m16_seed_b import (
    event,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture, _snap_json


async def _event_revision(client, factory, *, persistent=False):
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


async def _history(client, revision_id):
    r = await client.get(f"/shot-revisions/{revision_id}/continuity")
    assert r.status_code == 200, r.text
    return r.json()


async def test_hist_01(client, factory):
    """HIST:01 — continuity-spec schemas 1/2 historical behavior remains
    exact: event-free and event-bearing revisions carry the same
    predecessor spec bytes for the same dependency state."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision_free, _ = await _capture(client, sid)
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision_ev, _ = await _capture(client, sid)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT continuity_spec_json FROM shot_revisions "
            "WHERE id IN (:a, :b)"), {"a": revision_free.id,
                                       "b": revision_ev.id})).fetchall()
    assert rows[0][0] == rows[1][0]


async def test_hist_02(client, factory):
    """HIST:02 — published outer schema 6 remains inspectable without
    current state (the P0-B correction holds under schema 7)."""
    from tests.test_m13_shot_capture import _full_m13_world, _select_binding

    b = await _full_m13_world(client, tag=b"m16-hist02")
    sel = await _select_binding(client, b)
    engine = client._transport.app.state.engine
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from soloring.domain.revisions import capture_revision

        revision = await capture_revision(
            session, b["shot"], settings=client._transport.app.state
            .settings)
    snap = json.loads(await _snap_json(engine, revision.id))
    assert snap["schema_version"] == 6
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    assert r.json()["snapshot_schema_version"] == 6
    assert r.json()["intra_shot"] is None


async def test_hist_03(client, factory):
    """HIST:03 — schema-7 block rebuilt solely from immutable rows."""
    base, sid, fid, revision = await _event_revision(client, factory)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE shot_id = :s"),
            {"s": sid})
        await conn.execute(text(
            "UPDATE continuity_features SET key = 'renamed' "
            "WHERE id = :f"), {"f": fid})
    hist = await _history(client, revision.id)
    assert hist["intra_shot"]["events"][0]["target_identity"][
        "feature_key"] == "cut"


async def test_hist_04(client, factory):
    """HIST:04 — parent spec bytes/hash equal the rebuilt children and
    the outer snapshot block."""
    from soloring.domain.canonical import canonical_hash

    base, sid, fid, revision = await _event_revision(client, factory)
    hist = await _history(client, revision.id)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        parent = (await conn.execute(text(
            "SELECT spec_json, spec_hash FROM "
            "shot_revision_intra_shot_specs WHERE shot_revision_id = :r"),
            {"r": revision.id})).one()
    assert json.loads(parent.spec_json) == hist["intra_shot"]
    assert parent.spec_hash == canonical_hash(hist["intra_shot"])
    snap = json.loads(await _snap_json(engine, revision.id))
    assert snap["intra_shot"] == hist["intra_shot"]


async def test_hist_05(client, factory):
    """HIST:05 — captured target identity canonical bytes verified."""
    base, sid, fid, revision = await _event_revision(client, factory)
    hist = await _history(client, revision.id)
    identity = hist["intra_shot"]["events"][0]["target_identity"]
    from soloring.domain.canonical import canonical_json_str

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT captured_target_identity_json, "
            "captured_target_identity_hash FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).one()
    assert canonical_json_str(identity) == row[0]
    from soloring.domain.canonical import canonical_hash

    assert canonical_hash(identity) == row[1]


async def test_hist_06(client, factory):
    """HIST:06 — the re-fold starts from captured Shot/start states."""
    base, sid, fid, revision = await _event_revision(client, factory)
    hist = await _history(client, revision.id)
    first = hist["intra_shot"]["events"][0]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        captured_start = (await conn.execute(text(
            "SELECT value_json FROM shot_revision_feature_states "
            "WHERE shot_revision_id = :r AND feature_id = :f"),
            {"r": revision.id, "f": fid})).fetchall()
    if captured_start:
        assert first["before"] == {
            "present": True,
            "value": json.loads(captured_start[0][0]),
            "value_hash": None} | {"value_hash": first["before"].get(
                "value_hash")}
    else:
        assert first["before"] == {"present": False}


async def test_hist_07(client, factory):
    """HIST:07 — the re-fold verifies every before chain and terminal."""
    base, sid, fid, revision = await _event_revision(client, factory)
    await post_event(
        client, sid, event(fid, 2000, state("fresh"), state("healing")))
    revision2, _ = await _capture(client, sid)
    hist = await _history(client, revision2.id)
    events = hist["intra_shot"]["events"]
    assert events[0]["after"] == events[1]["before"] == state("fresh")
    assert hist["intra_shot"]["events"][-1]["after"] == state("healing")


async def test_hist_08(client, factory):
    """HIST:08 — captured persistent handoff equals the re-folded
    terminal state."""
    base, sid, fid, revision = await _event_revision(
        client, factory, persistent=True)
    hist = await _history(client, revision.id)
    entry = hist["intra_shot"]["events"][0]
    assert entry["persistence_mode"] == "require_handoff"
    assert entry["handoff"]["state"] == entry["after"] == state("fresh")
    assert entry["handoff"]["anchor"] == {
        "anchor_type": "shot", "anchor_id": sid, "boundary": "end"}


async def test_hist_09(client, factory):
    """HIST:09 — current edits never change the historical read."""
    base, sid, fid, revision = await _event_revision(client, factory)
    before = await _history(client, revision.id)
    await client.patch(f"/shots/{sid}", json={"duration_ms": 9000})
    await put_transition(client, fid, sid, operation="set", value="healing")
    after = await _history(client, revision.id)
    assert before == after


async def test_hist_10(client, factory):
    """HIST:10 — semantic convergence keeps first-publication ids."""
    base, sid, fid, revision = await _event_revision(client, factory)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        first_source = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE shot_id = :s"),
            {"s": sid})
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision2, _ = await _capture(client, sid)
    assert revision2.id == revision.id
    async with engine.connect() as conn:
        second_source = (await conn.execute(text(
            "SELECT source_event_id FROM "
            "shot_revision_intra_shot_events WHERE shot_revision_id = :r"),
            {"r": revision.id})).scalar_one()
    assert second_source == first_source


async def test_hist_11(client, factory):
    """HIST:11 — corrupt companion rows fail the invariant."""
    base, sid, fid, revision = await _event_revision(client, factory)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_intra_shot_events SET "
            "captured_after_state_json = :j "
            "WHERE shot_revision_id = :r"),
            {"j": '{"present": false}', "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "INTERNAL_INVARIANT_VIOLATION" in r.text


async def test_hist_missing_parent_corrupt(client, factory):
    """A schema-7 snapshot with NO companion parent is corruption."""
    base, sid, fid, revision = await _event_revision(client, factory)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM shot_revision_intra_shot_events "
            "WHERE shot_revision_id = :r"), {"r": revision.id})
        await conn.execute(text(
            "DELETE FROM shot_revision_intra_shot_specs "
            "WHERE shot_revision_id = :r"), {"r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "INTERNAL_INVARIANT_VIOLATION" in r.text


async def test_hist_foreign_handoff_corrupt(client, factory):
    """A coherently re-hashed handoff anchoring another Shot fails."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import projects as project_svc
    from soloring.domain import shots as shot_svc
    from soloring.domain.canonical import (
        canonical_hash as _ch,
        canonical_json_str as _cjs,
    )

    base, sid, fid, revision = await _event_revision(
        client, factory, persistent=True)
    async with factory() as s:
        pid2 = (await project_svc.create_project(
            s, ProjectCreate(name="other"))).id
        other = (await shot_svc.create_shot(
            s, pid2, ShotCreate(subject="o", duration_ms=3000))).id
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT captured_handoff_json FROM "
            "shot_revision_intra_shot_events "
            "WHERE shot_revision_id = :r"), {"r": revision.id})).one()
    handoff = json.loads(row[0])
    handoff["anchor"]["anchor_id"] = other
    tampered = _cjs(handoff)
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_revision_intra_shot_events SET "
            "captured_handoff_json = :j, captured_handoff_hash = :h "
            "WHERE shot_revision_id = :r"),
            {"j": tampered, "h": _ch(handoff), "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text


async def test_hist_identity_value_grammar_adversarial(client, factory):
    """A coherently re-hashed identity with an out-of-vocabulary
    feature_kind fails even at an absent-at-start target (pure §4.7
    grammar, no predecessor row needed)."""
    import hashlib

    from sqlalchemy import text as _text

    from soloring.domain.canonical import (
        canonical_hash as _ch,
        canonical_json_str as _cjs,
    )

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    # absent-at-start target: the feature has no current value
    await post_event(client, sid, event(fid, 1000, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(_text(
            "SELECT captured_target_identity_json FROM "
            "shot_revision_intra_shot_events "
            "WHERE shot_revision_id = :r"), {"r": revision.id})).one()
    identity = json.loads(row[0])
    identity["feature_kind"] = "not-a-real-kind"
    tampered = _cjs(identity)
    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE shot_revision_intra_shot_events SET "
            "captured_target_identity_json = :j, "
            "captured_target_identity_hash = :h "
            "WHERE shot_revision_id = :r"),
            {"j": tampered, "h": _ch(identity), "r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "vocabulary" in r.text or "grammar" in r.text
