"""M16:TAKE — Take/approval independence from persistence (§22)."""

from __future__ import annotations

import json

from sqlalchemy import text

from tests.test_m16_proposals import _capture_revision
from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)
from tests.test_m16_adoption import _adopt_direct


async def _take_world(client, factory):
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    engine = client._transport.app.state.engine
    gen_id = "00000000-0000-4000-8000-0000000000a1"
    take_id = "00000000-0000-4000-8000-0000000000a2"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "status, operation, executor, workflow_id, workflow_version, "
            "workflow_template_hash, manifest_hash, compiled_prompt, "
            "prompt_compiler_version, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, attempt_id, "
            "generation_number, created_at, updated_at) VALUES ("
            ":g, :s, :r, 'succeeded', 'generate', 'comfy', 'wf', 1, "
            ":h, :h, 'p', 'v1', '{}', :sj, :sh, 1, 1, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"g": gen_id, "s": sid, "r": revision.id, "h": "0" * 64,
             "sj": json.dumps({"schema_version": 1}),
             "sh": __import__("hashlib").sha256(
                 json.dumps({"schema_version": 1}).encode()).hexdigest()})
        await conn.execute(text(
            "INSERT INTO takes (id, shot_id, generation_id, output_key) "
            "VALUES (:t, :s, :g, 'out')"),
            {"t": take_id, "s": sid, "g": gen_id})
    return base, sid, fid, revision, gen_id, take_id


async def test_take_01(client, factory):
    """TAKE:01 — Take approval mutates only approved_take_id (+ its
    review metadata), never creative/continuity state."""
    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    before = (await client.get(f"/shots/{sid}")).json()
    r = await client.post(f"/takes/{take_id}/approve")
    assert r.status_code == 200, r.text
    after = (await client.get(f"/shots/{sid}")).json()
    assert after["approved_take_id"] == take_id
    assert after["working_snapshot_hash"] == before[
        "working_snapshot_hash"]
    assert after["intra_shot_ready"] == before["intra_shot_ready"]
    assert after["subject"] == before["subject"]


async def test_take_02(client, factory):
    """TAKE:02 — Take approval cannot create event/proposal
    review/handoff."""
    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    await client.post(f"/takes/{take_id}/approve")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        ev = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_intra_shot_events"
        ))).scalar_one()
        rv = (await conn.execute(text(
            "SELECT COUNT(*) FROM persistent_consequence_reviews"
        ))).scalar_one()
        tr = (await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions"
        ))).scalar_one()
    assert ev == rv == tr == 0


async def test_take_03(client, factory):
    """TAKE:03 — rejecting a Take does not undo adopted persistence."""
    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r = await _adopt_direct(client, sid, ev)
    assert r.status_code == 200, r.text
    rr = await client.post(f"/takes/{take_id}/reject")
    assert rr.status_code == 200, rr.text
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True
    assert proj["handoffs"][0]["matched"] is True
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        pm = (await conn.execute(text(
            "SELECT persistence_mode FROM shot_intra_shot_events "
            "WHERE id = :e"), {"e": ev["id"]})).scalar_one()
    assert pm == "require_handoff"


async def test_take_04(client, factory):
    """TAKE:04 — persistence adoption does not approve a Take."""
    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r = await _adopt_direct(client, sid, ev)
    assert r.status_code == 200, r.text
    detail = (await client.get(f"/shots/{sid}")).json()
    assert detail.get("approved_take_id") in (None, "")
    tr = (await client.get(
        f"/shots/{sid}/takes")).json() if False else None


async def test_take_05(client, factory):
    """TAKE:05 — an already captured Take/Generation stays pinned to
    the old ShotRevision after M16 authority changes."""
    base, sid, fid, revision, gen_id, take_id = await _take_world(
        client, factory)
    await client.post(f"/takes/{take_id}/approve")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        pinned = (await conn.execute(text(
            "SELECT shot_revision_id FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar_one()
    assert pinned == revision.id
    # M16 authority changes afterwards
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    await _adopt_direct(client, sid, ev)
    async with engine.connect() as conn:
        still = (await conn.execute(text(
            "SELECT shot_revision_id FROM generations WHERE id = :g"),
            {"g": gen_id})).scalar_one()
    assert still == revision.id
