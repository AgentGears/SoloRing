"""M16:PROPOSAL — immutable proposal ingestion/read (frozen §22)."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.m16_seed_b import (
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture


async def _capture_revision(client, sid):
    revision, _ = await _capture(client, sid)
    return revision


def _proposal_body(fid, *, source_kind="imported", suggestion="persist",
                    t=1500):
    return {
        "schema_version": 1,
        "source_kind": source_kind,
        "source_shot_revision_id": "PENDING",
        "source_shot_revision_hash": "PENDING",
        "proposer_kind": "human",
        "candidate_event": {
            "time_ms": t, "ordinal": 0,
            "target": {"kind": "entity_feature", "id": fid},
            "before": state(), "after": state("fresh"),
        },
        "persistence_suggestion": suggestion,
    }


async def _ingest(client, sid, fid, revision, **kw):
    body = _proposal_body(fid, **kw)
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = revision.snapshot_hash
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    return r, body


async def test_proposal_01(client, factory):
    """PROPOSAL:01 — Grammar v1 accepts exactly one candidate event plus
    a non-authoritative persistence suggestion."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, body = await _ingest(client, sid, fid, revision)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["source_shot_revision_id"] == revision.id
    detail = (await client.get(
        f"/shots/{sid}/intra-shot/proposals")).json()["proposals"][0]
    assert detail["persistence_suggestion"] == "persist"
    assert detail["candidate_event"]["target"]["id"] == fid
    assert detail["review_decision"] is None


async def test_proposal_02(client, factory):
    """PROPOSAL:02 — canonical bytes above 65,536 are rejected."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    await _capture_revision(client, sid)
    big = "x" * 70_000
    body = _proposal_body(fid)
    body["candidate_event"]["after"] = {
        "present": True, "value": big,
        "value_hash": __import__("hashlib").sha256(
            json.dumps(big).encode()).hexdigest()}
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    assert r.status_code == 422, r.text


async def test_proposal_03(client, factory):
    """PROPOSAL:03 — proposal time validates against the SOURCE
    ShotRevision's captured duration."""
    base = await seed_feature_world(client, factory, duration=5000)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    # interior boundary value is accepted; out-of-range is refused
    r, _ = await _ingest(client, sid, fid, revision, t=4999)
    assert r.status_code == 201, r.text
    r2, _ = await _ingest(client, sid, fid, revision, t=6000)
    assert r2.status_code in (409, 422), r2.text
    assert "duration" in r2.text or "interior" in r2.text


async def test_proposal_04(client, factory):
    """PROPOSAL:04 — a Generation-backed proposal pins the exact
    Generation ShotRevision id/hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    engine = client._transport.app.state.engine
    gen_id = "00000000-0000-4000-800-0000000000g1".replace(
        "8000-", "8000-")
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
    body = _proposal_body(fid, source_kind="generation")
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = revision.snapshot_hash
    body["source_generation_id"] = gen_id
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    assert r.status_code == 201, r.text
    # a wrong generation lineage is stale
    body2 = dict(body)
    body2["source_generation_id"] = "00000000-0000-4000-8000-fg"
    r2 = await client.post(f"/shots/{sid}/intra-shot/proposals",
                           json=body2)
    assert r2.status_code == 409, r2.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in r2.text


async def test_proposal_05(client, factory):
    """PROPOSAL:05 — a Take-backed proposal pins the coherent
    Take/Generation/Shot/ShotRevision lineage."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    engine = client._transport.app.state.engine
    gen_id = "00000000-0000-4000-8000-0000000000h1"
    take_id = "00000000-0000-4000-8000-0000000000h2"
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
            "INSERT INTO takes (id, shot_id, generation_id, "
            "output_key) VALUES (:t, :s, :g, 'out')"),
            {"t": take_id, "s": sid, "g": gen_id})
    body = _proposal_body(fid, source_kind="take")
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = revision.snapshot_hash
    body["source_generation_id"] = gen_id
    body["source_take_id"] = take_id
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    assert r.status_code == 201, r.text
    # a take pinned to a DIFFERENT generation is stale
    body2 = dict(body)
    body2["source_generation_id"] = "00000000-0000-4000-8000-fg"
    r2 = await client.post(f"/shots/{sid}/intra-shot/proposals",
                           json=body2)
    assert r2.status_code == 409, r2.text


async def test_proposal_06(client, factory):
    """PROPOSAL:06 — an imported proposal has no Generation/Take ids
    but still pins the exact source ShotRevision."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    body = _proposal_body(fid)
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = "0" * 64  # wrong hash
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    assert r.status_code == 409, r.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in r.text
    body["source_shot_revision_hash"] = revision.snapshot_hash
    body["source_generation_id"] = "00000000-0000-4000-8000-nope"
    r2 = await client.post(f"/shots/{sid}/intra-shot/proposals",
                           json=body)
    assert r2.status_code == 422, r2.text


async def test_proposal_07(client, factory):
    """PROPOSAL:07 — analyzer proposals always pin id/version/parameter
    hash, including the canonical empty parameters."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    body = _proposal_body(fid)
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = revision.snapshot_hash
    body["proposer_kind"] = "analyzer"
    r = await client.post(f"/shots/{sid}/intra-shot/proposals",
                          json=body)
    assert r.status_code == 422, r.text
    from soloring.domain.canonical import canonical_hash

    body["analyzer_id"] = "vision-1"
    body["analyzer_version"] = "1.2.3"
    body["analyzer_parameters_hash"] = canonical_hash({})
    r2 = await client.post(f"/shots/{sid}/intra-shot/proposals",
                           json=body)
    assert r2.status_code == 201, r2.text


async def test_proposal_08(client, factory):
    """PROPOSAL:08 — proposal existence does not alter the working hash,
    readiness, or create a transition."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    before = (await client.get(f"/shots/{sid}")).json()
    r, _ = await _ingest(client, sid, fid, revision)
    assert r.status_code == 201, r.text
    after = (await client.get(f"/shots/{sid}")).json()
    assert after["working_snapshot_hash"] == before[
        "working_snapshot_hash"]
    assert after["intra_shot_ready"] == before["intra_shot_ready"]
    proj = await get_intra(client, sid)
    assert proj["events"] == []
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions"))
        n = res.scalar_one()
    assert n == 0


async def test_proposal_09(client, factory):
    """PROPOSAL:09 — stale proposal adoption never silently rebases onto
    current truth."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision)
    assert r.status_code == 201, r.text
    proposal = r.json()
    # current authority moves past the pinned basis
    await post_event(client, sid, event(fid, 1000, state(), state("heal"
                                                                              "ing")))
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": proposal["id"],
            "expected_proposal_hash": proposal["proposal_hash"],
            "decision": "adopt_persistence"}]})
    assert rr.status_code == 409, rr.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in rr.text


async def test_proposal_10(client, factory):
    """PROPOSAL:10 — a stale proposal ignore remains legal because it
    creates no authority."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision)
    proposal = r.json()
    await post_event(client, sid, event(fid, 1000, state(), state("healing")))
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": proposal["id"],
            "expected_proposal_hash": proposal["proposal_hash"],
            "decision": "ignore"}]})
    assert rr.status_code == 200, rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_intra_shot_events "
            "WHERE source_proposal_id = :p"),
            {"p": proposal["id"]})).scalar_one()
    assert n == 0
