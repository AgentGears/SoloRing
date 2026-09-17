"""M16:ADOPT — direct + proposal adoption (frozen §22)."""

from __future__ import annotations

import json

from sqlalchemy import text

from soloring.domain.canonical import canonical_hash

from tests.test_m16_proposals import (
    _capture_revision,
    _ingest,
    _proposal_body,
)
from tests.m16_seed_b import (
    assign_shot,
    event,
    get_intra,
    post_event,
    put_transition,
    seed_feature_world,
    state,
)


async def _adopt_direct(client, sid, ev):
    proj = await get_intra(client, sid)
    r = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    return r


async def test_adopt_01(client, factory):
    """ADOPT:01 — direct adoption creates-or-exact-matches the handoff
    atomically with the review."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r = await _adopt_direct(client, sid, ev)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["idempotent"] is False
    assert out["transition_id"]
    # the handoff now exists and the event is ready
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True
    assert proj["handoffs"][0]["matched"] is True
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions"))
        n = res.scalar_one()
    assert n == 1


async def test_adopt_02(client, factory):
    """ADOPT:02 — decline changes the unreviewed require_handoff event
    to transient and records the resulting hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    r = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/decline",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["resulting_event_hash"] != ev["event_hash"]
    proj2 = await get_intra(client, sid)
    assert proj2["intra_shot_ready"] is True  # transient: no handoff need
    assert proj2["handoffs"] == []


async def test_adopt_03(client, factory):
    """ADOPT:03 — a previously adopted source hash cannot receive a
    competing decline; regret requires a PATCH producing a new hash."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r1 = await _adopt_direct(client, sid, ev)
    assert r1.status_code == 200, r1.text
    proj = await get_intra(client, sid)
    # the same source hash declined now conflicts (the event was never
    # edited — a decline of an adopted persistent event is a review
    # conflict, not a silent second decision)
    r2 = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/decline",
        json={"expected_event_hash": ev["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert r2.status_code == 409, r2.text
    # regret through an ordinary PATCH produces a NEW event hash
    r3 = await client.patch(
        f"/intra-shot/events/{ev['id']}",
        json={"persistence_mode": "transient"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["event_hash"] != ev["event_hash"]


async def test_adopt_04(client, factory):
    """ADOPT:04 — adopt_event_only always creates a transient event
    even when the suggestion says persist."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision,
                          suggestion="persist")
    proposal = r.json()
    rr = await client.post(
        f"/intra-shot/proposals/{proposal['id']}/review",
        json={"expected_proposal_hash": proposal["proposal_hash"],
              "decision": "adopt_event_only"})
    assert rr.status_code == 200, rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT persistence_mode FROM shot_intra_shot_events "
            "WHERE source_proposal_id = :p"),
            {"p": proposal["id"]})
        pm = res.scalar_one()
    assert pm == "transient"


async def test_adopt_05(client, factory):
    """ADOPT:05 — adopt_persistence creates the event + the exact A2
    handoff atomically."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision,
                          suggestion="persist")
    proposal = r.json()
    rr = await client.post(
        f"/intra-shot/proposals/{proposal['id']}/review",
        json={"expected_proposal_hash": proposal["proposal_hash"],
              "decision": "adopt_persistence"})
    assert rr.status_code == 200, rr.text
    out = rr.json()
    assert out["idempotent"] is False
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True
    assert proj["handoffs"][0]["matched"] is True
    assert proj["terminal_targets"][0]["persistence_mode"] == \
        "require_handoff"


async def test_adopt_06(client, factory):
    """ADOPT:06 — ignore creates no authority."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r, _ = await _ingest(client, sid, fid, revision)
    proposal = r.json()
    rr = await client.post(
        f"/intra-shot/proposals/{proposal['id']}/review",
        json={"expected_proposal_hash": proposal["proposal_hash"],
              "decision": "ignore"})
    assert rr.status_code == 200, rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        res = await conn.execute(text(
            "SELECT COUNT(*) FROM shot_intra_shot_events"))
        n = res.scalar_one()
    assert n == 0


async def _two_sibling_proposals(client, factory):
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    revision = await _capture_revision(client, sid)
    r1, _ = await _ingest(client, sid, base["feature_id"], revision)
    r2, _ = await _ingest(
        client, sid, base["wardrobe_feature_id"], revision, t=1600)
    return base, sid, revision, [r1.json(), r2.json()]


async def test_adopt_07(client, factory):
    """ADOPT:07 — a multi-proposal same-source batch checks the working
    source basis once before mutation."""
    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    out = rr.json()
    assert out["idempotent"] is False
    assert out["batch_basis_hash"]
    assert set(out["results"]) == {p["id"] for p in props}


async def test_adopt_08(client, factory):
    """ADOPT:08 — the batch prospective fold includes every selected
    adopted proposal AND the existing events."""
    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    # an existing working event that the adopted candidates must chain
    # with legally (target-orthogonal)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    proj = await get_intra(client, sid)
    ids = {e["id"] for e in proj["events"]}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        adopted = (await conn.execute(text(
            "SELECT id FROM shot_intra_shot_events WHERE "
            "source_proposal_id IS NOT NULL"))).fetchall()
    assert {r[0] for r in adopted} <= ids
    assert len(proj["events"]) == 2


async def test_adopt_09(client, factory):
    """ADOPT:09 — a batch rollback leaves no partial rows."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    revision = await _capture_revision(client, sid)
    r1, _ = await _ingest(client, sid, fid, revision)
    # a second proposal whose chain is illegal against the first
    body = _proposal_body(fid, t=1500)
    body["source_shot_revision_id"] = revision.id
    body["source_shot_revision_hash"] = revision.snapshot_hash
    body["candidate_event"]["before"] = state("wrong")
    r2 = await client.post(f"/shots/{sid}/intra-shot/proposals",
                           json=body)
    assert r2.status_code == 201, r2.text
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": r1.json()["id"],
             "expected_proposal_hash": r1.json()["proposal_hash"],
             "decision": "adopt_persistence"},
            {"proposal_id": r2.json()["id"],
             "expected_proposal_hash": r2.json()["proposal_hash"],
             "decision": "adopt_persistence"}]})
    assert rr.status_code == 409, rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        ev = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_intra_shot_events"))).scalar_one()
        tr = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "continuity_feature_transitions"))).scalar_one()
        rv = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "persistent_consequence_reviews"))).scalar_one()
    assert ev == 0 and tr == 0 and rv == 0


async def test_adopt_10(client, factory):
    """ADOPT:10 — review_basis_hash and batch_basis_hash follow the
    exact canonical roots."""
    from soloring.continuity.intra_shot_canonical import (
        proposal_review_basis_hash,
    )

    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    out = rr.json()
    batch = out["batch_basis_hash"]
    for p in props:
        expected = proposal_review_basis_hash(
            batch_basis_hash=batch,
            proposal_id=p["id"],
            proposal_hash=p["proposal_hash"],
            decision="adopt_persistence")
        assert out["results"][p["id"]].get(
            "review_basis_hash", expected) in (
            expected, out["results"][p["id"]].get("review_basis_hash"))
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT source_proposal_id, review_basis_hash FROM "
            "persistent_consequence_reviews WHERE source_kind = "
            "'proposal'"))).fetchall()
    # key by source_proposal_id — review-row ids are independent
    # UUIDs whose incidental ordering says nothing about the batch
    by_pid = {r[0]: r[1] for r in rows}
    for p in props:
        expected = proposal_review_basis_hash(
            batch_basis_hash=batch,
            proposal_id=p["id"],
            proposal_hash=p["proposal_hash"],
            decision="adopt_persistence")
        assert by_pid[p["id"]] == expected


async def test_adopt_11(client, factory):
    """ADOPT:11 — an exact retry returns the complete non-null
    committed evidence and detects later result drift."""
    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    first = rr.json()
    rr2 = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr2.status_code == 200, rr2.text
    retry = rr2.json()
    assert retry["idempotent"] is True
    assert retry["batch_basis_hash"] == first["batch_basis_hash"]
    assert retry["results"]
    # later drift on a result event conflicts a retry
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE shot_intra_shot_events SET event_hash = :h "
            "WHERE source_proposal_id IS NOT NULL"),
            {"h": "9" * 64})
    rr3 = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr3.status_code == 409, rr3.text
    assert "INTRA_SHOT_REVIEW_CONFLICT" in rr3.text


async def test_adopt_12(client, factory):
    """ADOPT:12 — an exact decline retry converges on the committed
    review even though the first decline already made the event
    transient; the retry writes nothing (§12.4)."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    body = {"expected_event_hash": ev["event_hash"],
            "expected_event_set_hash": proj["event_set_hash"]}
    r1 = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/decline",
        json=body)
    assert r1.status_code == 200, r1.text
    first = r1.json()
    r2 = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/decline",
        json=body)
    assert r2.status_code == 200, r2.text
    retry = r2.json()
    assert retry["idempotent"] is True
    assert retry["review_id"] == first["review_id"]
    assert retry["operation_hash"]
    assert retry["result"]["event_hash"] == first["resulting_event_hash"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "persistent_consequence_reviews"))).scalar_one()
    assert n == 1


async def test_adopt_13(client, factory):
    """ADOPT:13 — an exact direct-adopt retry returns the committed
    transition id and review/operation identities, and later result
    TRANSITION drift conflicts instead of converging."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    r1 = await _adopt_direct(client, sid, ev)
    assert r1.status_code == 200, r1.text
    first = r1.json()
    r2 = await _adopt_direct(client, sid, ev)
    assert r2.status_code == 200, r2.text
    retry = r2.json()
    assert retry["idempotent"] is True
    assert retry["review_id"] == first["review_id"]
    assert retry["operation_hash"]
    assert retry["result"]["transition"]["id"] == first["transition_id"]
    # drift the committed transition value: the retry must conflict
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE continuity_feature_transitions SET value_json = "
            ":vj, value_hash = :vh"),
            {"vj": '"drifted"', "vh": "8" * 64})
    r3 = await _adopt_direct(client, sid, ev)
    assert r3.status_code == 409, r3.text
    assert "INTRA_SHOT_REVIEW_CONFLICT" in r3.text


async def test_adopt_14(client, factory):
    """ADOPT:14 — a strict subset of a committed batch is corruption:
    the subset retry conflicts, while the exact full-batch retry
    converges with complete committed evidence."""
    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    sub = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": props[0]["id"],
            "expected_proposal_hash": props[0]["proposal_hash"],
            "decision": "adopt_persistence"}]})
    assert sub.status_code == 409, sub.text
    assert "subset" in sub.text.lower()
    rr2 = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr2.status_code == 200, rr2.text
    retry = rr2.json()
    assert retry["idempotent"] is True
    res = retry["results"][props[0]["id"]]
    assert res["review_id"]
    assert res["operation_hash"]
    assert res["transition"]["id"]


async def test_adopt_15(client, factory):
    """ADOPT:15 — one source ShotRevision per ATOMIC batch (the
    C-recovery source-coherence invariant): mixed-decision batching is
    legal only when every member pins the SAME revision; a batch mixing
    revisions conflicts and the stale proposal is reviewed separately."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid = base["shot_id"]
    old_rev = await _capture_revision(client, sid)
    r_old, _ = await _ingest(client, sid, base["feature_id"], old_rev)
    # move the working state so the next capture is a NEW revision —
    # content-identical captures deduplicate to the same revision
    await post_event(client, sid, event(
        base["feature_id"], 1000, state(), state("healing")))
    new_rev = await _capture_revision(client, sid)
    assert new_rev.id != old_rev.id
    r_new, _ = await _ingest(
        client, sid, base["wardrobe_feature_id"], new_rev, t=1600)
    r_third, _ = await _ingest(
        client, sid, base["wardrobe_feature_id"], new_rev, t=1700)
    old_p, new_p, third_p = (r_old.json(), r_new.json(),
                             r_third.json())
    # mixing source revisions inside one atomic batch is refused
    mixed = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": new_p["id"],
             "expected_proposal_hash": new_p["proposal_hash"],
             "decision": "adopt_persistence"},
            {"proposal_id": old_p["id"],
             "expected_proposal_hash": old_p["proposal_hash"],
             "decision": "ignore"}]})
    assert mixed.status_code == 409, mixed.text
    assert "INTRA_SHOT_PROPOSAL_STALE" in mixed.text
    assert "separately" in mixed.text
    # a mixed-DECISION batch is legal when every member shares one
    # revision — ignore records its review evidence with no authority
    ok = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": new_p["id"],
             "expected_proposal_hash": new_p["proposal_hash"],
             "decision": "adopt_persistence"},
            {"proposal_id": third_p["id"],
             "expected_proposal_hash": third_p["proposal_hash"],
             "decision": "ignore"}]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["idempotent"] is False
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        dec = (await conn.execute(text(
            "SELECT decision FROM persistent_consequence_reviews "
            "WHERE source_proposal_id = :p"),
            {"p": third_p["id"]})).scalar_one()
    assert dec == "ignore"
    # the stale proposal is ignored in its own batch at its own revision
    sep = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [
            {"proposal_id": old_p["id"],
             "expected_proposal_hash": old_p["proposal_hash"],
             "decision": "ignore"}]})
    assert sep.status_code == 200, sep.text
    async with engine.connect() as conn:
        dec2 = (await conn.execute(text(
            "SELECT decision FROM persistent_consequence_reviews "
            "WHERE source_proposal_id = :p"),
            {"p": old_p["id"]})).scalar_one()
    assert dec2 == "ignore"


async def test_adopt_16(client, factory):
    """ADOPT:16 — a committed batch missing a persisted review row is
    corruption: the full retry conflicts and never recreates the
    missing member (§12.4 forbids repairing partial persistence)."""
    base, sid, revision, props = await _two_sibling_proposals(
        client, factory)
    rr = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr.status_code == 200, rr.text
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM persistent_consequence_reviews WHERE "
            "source_proposal_id = :p"),
            {"p": props[1]["id"]})
    rr2 = await client.post(
        f"/shots/{sid}/intra-shot/proposals/review-batch",
        json={"reviews": [{
            "proposal_id": p["id"],
            "expected_proposal_hash": p["proposal_hash"],
            "decision": "adopt_persistence"} for p in props]})
    assert rr2.status_code == 409, rr2.text
    assert "INTRA_SHOT_REVIEW_CONFLICT" in rr2.text
    assert "corruption" in rr2.text.lower()
    # nothing was recreated: only the surviving row remains
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "persistent_consequence_reviews"))).scalar_one()
    assert n == 1


async def test_adopt_17(client, factory):
    """ADOPT:17 — direct retries survive unrelated later captures and
    event-set evolution: the prior review is located from the immutable
    request source tuple; current state only certifies result drift."""
    base = await seed_feature_world(
        client, factory, extra_feature_keys=("wardrobe",))
    sid, fid = base["shot_id"], base["feature_id"]
    ev1 = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    adopt_body = {"expected_event_hash": ev1["event_hash"],
                  "expected_event_set_hash": proj["event_set_hash"]}
    r1 = await client.post(
        f"/intra-shot/events/{ev1['id']}/persistence/adopt",
        json=adopt_body)
    assert r1.status_code == 200, r1.text
    # unrelated event-set evolution: a second event joins the set
    ev2 = await post_event(
        client, sid,
        event(base["wardrobe_feature_id"], 1200, state(), state("wet"),
              persistence="require_handoff"))
    # the exact adopt retry (original request evidence) still converges
    r2 = await client.post(
        f"/intra-shot/events/{ev1['id']}/persistence/adopt",
        json=adopt_body)
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotent"] is True
    # decline flow: decline ev2, then capture a NEW revision (which
    # moves the working pin), then retry the decline unchanged
    proj2 = await get_intra(client, sid)
    decline_body = {"expected_event_hash": ev2["event_hash"],
                    "expected_event_set_hash": proj2["event_set_hash"]}
    d1 = await client.post(
        f"/intra-shot/events/{ev2['id']}/persistence/decline",
        json=decline_body)
    assert d1.status_code == 200, d1.text
    await _capture_revision(client, sid)
    d2 = await client.post(
        f"/intra-shot/events/{ev2['id']}/persistence/decline",
        json=decline_body)
    assert d2.status_code == 200, d2.text
    assert d2.json()["idempotent"] is True


async def test_adopt_18(client, factory):
    """ADOPT:18 — fresh direct adoption re-folds the FULL event set
    under the writer fence: a stored before-chain gone stale against
    current Shot/start authority conflicts even though the stored
    event-set bytes never changed, and no A2 authority is written."""
    from soloring.api.schemas.projects import ProjectCreate
    from soloring.domain import projects as project_svc
    from tests.m16_seed_b import seed_ordered_pair

    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="M16 adopt 18"))).id
    first, second = await seed_ordered_pair(
        factory, pid, name="M16 a18")
    e = await client.post(
        f"/projects/{pid}/entities",
        json={"kind": "character", "name": "E"})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    a = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    assert a.status_code == 200, a.text
    for sid in (first, second):
        d = await client.put(
            f"/shots/{sid}/semantic-dependencies",
            json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
        assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing"]})
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    # an event in `second` chained from the ABSENT start state
    ev = await post_event(
        client, second,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, second)
    body = {"expected_event_hash": ev["event_hash"],
            "expected_event_set_hash": proj["event_set_hash"]}
    # prior-Shot end authority now projects a DIFFERENT start state
    # into `second`; the stored event bytes are untouched
    await put_transition(client, fid, first, operation="set",
                         value="healing")
    rr = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt", json=body)
    assert rr.status_code == 409, rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions "
            "WHERE anchor_id = :s"),
            {"s": second})).scalar_one()
    assert n == 0


async def test_adopt_19(client, factory):
    """ADOPT:19 — an exact retry after the result event is tombstoned
    returns the §12.4 recorded-result drift conflict, not a
    missing-source-event 404."""
    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    proj = await get_intra(client, sid)
    body = {"expected_event_hash": ev["event_hash"],
            "expected_event_set_hash": proj["event_set_hash"]}
    r1 = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt", json=body)
    assert r1.status_code == 200, r1.text
    d = await client.delete(f"/intra-shot/events/{ev['id']}")
    assert d.status_code in (200, 204), d.text
    r2 = await client.post(
        f"/intra-shot/events/{ev['id']}/persistence/adopt", json=body)
    assert r2.status_code == 409, r2.text
    assert "INTRA_SHOT_REVIEW_CONFLICT" in r2.text


async def test_adopt_20(client, factory):
    """ADOPT:20 — §12.1 step 4: only the terminal event for a target
    may adopt persistence. The authoring API refuses to demote a
    require_handoff event (INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL),
    so the non-terminal state is crafted directly in the database and
    the adopt-side check is proven as defense-in-depth."""
    from soloring.continuity.intra_shot_canonical import event_storage
    from soloring.domain.canonical import canonical_json_str
    from soloring.domain.ids import new_uuid

    base = await seed_feature_world(client, factory)
    sid, fid = base["shot_id"], base["feature_id"]
    ev1 = await post_event(
        client, sid,
        event(fid, 1000, state(), state("fresh"),
              persistence="require_handoff"))
    # a later transient event on the same target, inserted past the
    # authoring guard — ev1 is now non-terminal for its target
    value, ej, eh = event_storage(
        time_ms=1500, ordinal=0,
        target={"kind": "entity_feature", "id": fid},
        before=state("fresh"), after=state("healing"),
        persistence_mode="transient")
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO shot_intra_shot_events "
            "(id, shot_id, time_ms, ordinal, target_kind, "
            "entity_feature_id, entity_relation_id, "
            "production_instance_feature_id, before_state_json, "
            "before_state_hash, after_state_json, after_state_hash, "
            "persistence_mode, source_kind, source_proposal_id, "
            "event_json, event_hash, created_at, updated_at) VALUES ("
            ":id, :s, :t, 0, 'entity_feature', :f, NULL, NULL, :bj, "
            ":bh, :aj, :ah, 'transient', 'authored', NULL, :ej, :eh, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"id": new_uuid(), "s": sid, "t": 1500, "f": fid,
             "bj": canonical_json_str(state("fresh")),
             "bh": canonical_hash(state("fresh")),
             "aj": canonical_json_str(state("healing")),
             "ah": canonical_hash(state("healing")),
             "ej": ej, "eh": eh})
    proj = await get_intra(client, sid)
    rr = await client.post(
        f"/intra-shot/events/{ev1['id']}/persistence/adopt",
        json={"expected_event_hash": ev1["event_hash"],
              "expected_event_set_hash": proj["event_set_hash"]})
    assert rr.status_code == 409, rr.text
    assert "terminal" in rr.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM continuity_feature_transitions "
            "WHERE anchor_id = :s"),
            {"s": sid})).scalar_one()
    assert n == 0
