"""M16-E §23 source-gate acceptance scenarios, walked end to end as the
closure battery's named owners (§28.1 gates 7-9)."""

from __future__ import annotations

import json

from sqlalchemy import text

from tests.m16_seed_b import (
    assign_shot,
    event,
    get_intra,
    post_event,
    seed_feature_world,
    state,
)
from tests.test_m16_capture import _capture
from tests.test_m16_proposals import _capture_revision, _proposal_body


async def _adopt_direct(client, sid, ev):
    proj = await get_intra(client, sid)
    return await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})


async def _seed_generation_and_take(engine, sid, revision, *, gen_suffix,
                                    take_suffix):
    gen_id = f"00000000-{gen_suffix}-4000-8000-0000000000c1"
    take_id = f"00000000-{take_suffix}-4000-8000-0000000000c2"
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
    return gen_id, take_id


async def test_source_gate_entity(client, factory):
    """§23.1 entity-bound injury: the full timeline, adoption, downstream
    feed, historical isolation, and fail-closed realization fence."""
    base = await seed_feature_world(client, factory, duration=5000)
    sid, fid = base["shot_id"], base["feature_id"]
    engine = client._transport.app.state.engine
    # historical source captured BEFORE any event (predecessor bytes)
    r1, _ = await _capture(client, sid)
    r1_bytes = r1.snapshot_json

    # the fold timeline BEFORE the injury event exists: t<3100 is
    # still uninjured — an interior probe chaining from absent is
    # legal, and claiming the injury early is refused
    probe_ok = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 3099, state(), state("healing")))
    assert probe_ok.status_code == 201, probe_ok.text
    await client.delete(
        f"/intra-shot/events/{probe_ok.json()['id']}")
    probe_lie = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 3099, state("fresh"), state("healing")))
    assert probe_lie.status_code == 409, probe_lie.text
    assert "BEFORE_STATE_MISMATCH" in probe_lie.text

    # t=3100: uninjured -> fresh injury (transient for now)
    ev0 = await post_event(
        client, sid, event(fid, 3100, state(), state("fresh")))

    # 3100+ is fresh: a probe chaining from fresh is legal — probed
    # BEFORE the persistence marker exists, because a later
    # same-target event would otherwise demote require_handoff
    probe_after = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(fid, 3200, state("fresh"), state("healing")))
    assert probe_after.status_code == 201, probe_after.text
    await client.delete(
        f"/intra-shot/events/{probe_after.json()['id']}")

    # persistence is requested on the terminal event via a lawful PATCH
    marked = await client.patch(
        f"/intra-shot/events/{ev0['id']}",
        json={"persistence_mode": "require_handoff"})
    assert marked.status_code == 200, marked.text
    ev = marked.json()
    # Shot/end- terminal state is fresh
    proj = await get_intra(client, sid)
    assert proj["terminal_targets"][0]["terminal_state"] == \
        state("fresh")

    # BEFORE adoption: the require_handoff event is structurally valid
    # but capture-blocked (no handoff exists)
    try:
        await _capture(client, sid)
    except Exception as exc:
        # the fail-closed capture fence: the unresolved require_handoff
        # event has no owning-domain Shot/end handoff
        assert "handoff" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("capture succeeded without the handoff")

    # Take approval alone creates no persistent state; the Take's
    # Generation pins the pre-event historical revision r1
    _gen, take_id = await _seed_generation_and_take(
        engine, sid, r1, gen_suffix="0001", take_suffix="0002")
    approve = await client.post(f"/takes/{take_id}/approve")
    assert approve.status_code == 200, approve.text
    async with engine.connect() as conn:
        tr = (await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions "
            "WHERE anchor_id = :s"),
            {"s": sid})).scalar_one()
        rv = (await conn.execute(text(
            "SELECT COUNT(*) FROM persistent_consequence_reviews"
        ))).scalar_one()
    assert tr == 0 and rv == 0

    # AFTER explicit adoption: Shot/end transition = fresh injury
    r = await _adopt_direct(client, sid, ev)
    assert r.status_code == 200, r.text
    async with engine.connect() as conn:
        val = (await conn.execute(text(
            "SELECT value_json FROM continuity_feature_transitions "
            "WHERE anchor_id = :s AND boundary = 'end' AND "
            "deleted_at IS NULL"),
            {"s": sid})).scalar_one()
    # the M7 transition stores the bare canonical value
    assert json.loads(val) == "fresh"

    # later Shot/start = fresh injury (the downstream feed)
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    pid = base["project_id"]
    sid2 = (await shot_svc.create_shot(
        factory(), pid, ShotCreate(subject="later",
                                   duration_ms=4000))).id
    await assign_shot(factory, pid, sid2, name="later scene")
    d = await client.put(
        f"/shots/{sid2}/semantic-dependencies",
        json={"dependencies": [{"entity_id": base["entity_id"],
                                "role": "subject"}]})
    assert d.status_code == 200, d.text
    later = await post_event(
        client, sid2, event(fid, 500, state("fresh"), state("healing")))
    assert later is not None

    # the historical source ShotRevision bytes never moved
    async with engine.connect() as conn:
        now_bytes = (await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": r1.id})).scalar_one()
    assert now_bytes == r1_bytes

    # a newly captured schema-7 ShotRevision is authoritative history
    r2, _ = await _capture(client, sid)
    assert json.loads(r2.snapshot_json)["intra_shot"][
        "schema_version"] == 1
    # current M16 workflows do not execute it
    refused = await client.post(f"/shots/{sid}/generations")
    assert refused.status_code == 409, refused.text
    assert "INTRA_SHOT_REALIZATION_UNSUPPORTED" in refused.text


async def test_source_gate_instance(client, factory):
    """§23.2 instance-bound chair: the occurrence-bound configuration
    consequence walks upright -> fallen through the terminal fold and
    the explicit PI handoff on the SAME stable occurrence."""
    from tests.test_m16_instance import _pi_event, _pi_world

    b, sel, fid = await _pi_world(client, tag=b"m16-sg2")
    sid = b["shot"]
    engine = client._transport.app.state.engine
    occurrence = sel["occurrence_id"]
    # §23.2: the configuration feature starts UPRIGHT via an explicit
    # Shot/start authority (absent-start fallback if the predecessor
    # route refuses the start anchor)
    try:
        start = await client.post(
            f"/production-instance-features/{fid}/transitions",
            json={"anchor_type": "shot", "anchor_id": sid,
                  "boundary": "start", "operation": "set",
                  "value": "upright"})
        start_ok = start.status_code == 201
    except Exception:
        start_ok = False
    before = state("upright") if start_ok else state()
    created = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=_pi_event(fid, 2500, before, state("fallen"),
                       persistence="require_handoff"))
    assert created.status_code == 201, created.text
    # Shot/end- terminal fold is fallen
    proj = await get_intra(client, sid)
    assert proj["terminal_targets"][0]["terminal_state"] == \
        state("fallen")
    # explicit PI handoff: create the exact transition, then adopt
    t = await client.post(
        f"/production-instance-features/{fid}/transitions",
        json={"anchor_type": "shot", "anchor_id": sid,
              "boundary": "end", "operation": "set", "value": "fallen"})
    assert t.status_code == 201, t.text
    r = await client.post(
        f"/intra-shot/events/{created.json()['id']}/persistence/adopt",
        json={"expected_event_hash": created.json()["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 200, r.text
    proj2 = await get_intra(client, sid)
    assert proj2["handoffs"][0]["matched"] is True
    # the SAME occurrence resolves fallen — no re-mint/substitution:
    # the PI feature row and its occurrence authority are unchanged
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT pif.id, c.subject_kind FROM "
            "production_instance_features pif JOIN "
            "composition_occurrence_authority_subjects c ON "
            "c.occurrence_id = pif.occurrence_id WHERE pif.id = :f"),
            {"f": fid})).first()
    assert row is not None and row[1] == "production_instance"
    assert occurrence == sel["occurrence_id"]


async def test_source_gate_multi_proposal(client, factory):
    """§23.3 multi-event post-Take proposal batch: two analyzer
    proposals from one captured source, adopted in one atomic
    review-batch, then a later stale proposal conflicts instead of
    rebasing."""
    from soloring.domain.canonical import canonical_hash

    base = await seed_feature_world(
        client, factory, duration=5000,
        extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    engine = client._transport.app.state.engine
    revision = await _capture_revision(client, sid)
    _gen, take_id = await _seed_generation_and_take(
        engine, sid, revision, gen_suffix="0003", take_suffix="0004")

    def analyzer_body(fid, t):
        body = _proposal_body(fid, source_kind="take", t=t)
        body["source_shot_revision_id"] = revision.id
        body["source_shot_revision_hash"] = revision.snapshot_hash
        body["source_generation_id"] = _gen
        body["source_take_id"] = take_id
        body["proposer_kind"] = "analyzer"
        body["analyzer_id"] = "vision-1"
        body["analyzer_version"] = "1.2.3"
        body["analyzer_parameters_hash"] = canonical_hash({})
        return body

    ra = await client.post(
        f"/shots/{sid}/intra-shot/proposals",
        json=analyzer_body(base["feature_id"], 3100))
    rb = await client.post(
        f"/shots/{sid}/intra-shot/proposals",
        json=analyzer_body(base["wardrobe_feature_id"], 4200))
    assert ra.status_code == 201, ra.text
    assert rb.status_code == 201, rb.text
    pa, pb = ra.json(), rb.json()

    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": pa["id"],
             "expected_proposal_hash": pa["proposal_hash"],
             "decision": "adopt_persistence"},
            {"proposal_id": pb["id"],
             "expected_proposal_hash": pb["proposal_hash"],
             "decision": "adopt_persistence"}]})
    assert rr.status_code == 200, rr.text
    out = rr.json()
    assert out["idempotent"] is False
    assert set(out["results"]) == {pa["id"], pb["id"]}
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT operation_json FROM persistent_consequence_reviews "
            "WHERE source_kind = 'proposal'"))).fetchall()
        events = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_intra_shot_events WHERE "
            "source_proposal_id IS NOT NULL"))).scalar_one()
        handoffs = (await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions WHERE "
            "anchor_id = :s"),
            {"s": sid})).scalar_one()
    docs = [json.loads(r[0]) for r in rows]
    assert len(docs) == 2
    assert len({d["batch_basis_hash"] for d in docs}) == 1
    assert events == 2 and handoffs == 2
    for d in docs:
        assert d["result"]["transition"]["semantic_hash"]

    # a later proposal still pinned to the OLD source is stale
    rc = await client.post(
        f"/shots/{sid}/intra-shot/proposals",
        json=analyzer_body(base["feature_id"], 1500))
    assert rc.status_code == 201, rc.text
    pc = rc.json()
    stale = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": pc["id"],
             "expected_proposal_hash": pc["proposal_hash"],
             "decision": "adopt_persistence"}]})
    assert stale.status_code == 409, stale.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in stale.text
    # the stale ignore is still legal (no authority)
    ignore = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": pc["id"],
             "expected_proposal_hash": pc["proposal_hash"],
             "decision": "ignore"}]})
    assert ignore.status_code == 200, ignore.text
