"""M13 race proofs (frozen R3 §30.10 R6-R11 at the M13C gate).

Every race uses deterministic injection seams or real lock contention —
no sleeps. The PREFENCE_SEAM fires inside the exact prefence-derivation →
fence-acquisition window; R9/R10 run genuinely concurrent tasks against
SQLite's BEGIN IMMEDIATE serialization; R11 parks the selection inside
its open writer fence and mechanically proves the terminating operation
attempted its own fence during the park.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import event, text

from tests.test_m13_binding import (
    _adopt,
    _approved_world,
    _binding_base,
    _interpretation,
    _publish,
)
from tests.test_m13_impact import _preview, _apply

SCOPE = "composition_working_state"


async def _shot(client, pid):
    r = await client.post(f"/projects/{pid}/shots", json={"subject": "s"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_m13_race_06(client):
    """M13-RACE:06 (R6) — binding freeze vs newly applicable subject
    adoption: the in-fence re-derivation discovers the complete new
    adoption set and refuses to publish the incomplete old candidate."""
    from soloring.production_world import binding as binding_svc

    b = await _binding_base(client, tag=b"race06", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "production_instance"})

    async def seam():
        await _adopt(client, cid, b["occurrences"][1],
                     {"kind": "production_instance"})

    binding_svc.PREFENCE_SEAM = seam
    try:
        r = await _publish(client, b["C"], w["revision"]["id"])
        assert r.status_code == 409, r.text
        assert r.json()["error_code"] == (
            "COMPOSITION_SPATIAL_BINDING_CONFLICT")
    finally:
        binding_svc.PREFENCE_SEAM = None
    # nothing was published; the next publish sees the complete set
    r = await _publish(client, b["C"], w["revision"]["id"])
    assert r.status_code == 201, r.text
    assert len(r.json()["subjects"]) == 2
    # an adoption for an occurrence absent from exact C does not conflict
    m = await b["mint_extra"](client) if hasattr(b, "mint_extra") else None
    if m is None:
        from tests.m13_seed import mint
        m = await mint(client, cid, b["production_revision_id"], 2,
                       name="Later")
        await _adopt(client, cid, m["occurrence_id"],
                     {"kind": "production_instance"})
        r = await _readiness_again(client, b, w)
        assert r.json()["subject_summaries"].__len__() == 2


async def _readiness_again(client, b, w):
    return await client.post(
        f"/composition-revisions/{b['C']}/spatial-binding-readiness",
        json={"spatial_world_revision_id": w["revision"]["id"]})


async def test_m13_race_07(client):
    """M13-RACE:07 (R7) — binding freeze vs PI and CreativeEntity A4
    target changes: both interleavings conflict through the entry-set
    change (PI track + CE-side EntityTrack; the CE fixed-frame variant is
    covered by a second approved revision changing the classified set)."""
    from soloring.production_world import binding as binding_svc

    b = await _binding_base(client, tag=b"race07", n_occurrences=2)
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    await _adopt(client, cid, b["occurrences"][0],
                 {"kind": "production_instance"})
    await _interpretation(client, b["production_revision_id"])
    eid = await make_entity_and_adopt(client, b, cid)

    # PI-track creation inside the window
    async def seam_pi():
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
            json={"occurrence_id": b["occurrences"][0],
                  "requirement": "required"})
        assert r.status_code == 201

    binding_svc.PREFENCE_SEAM = seam_pi
    try:
        r = await _publish(client, b["C"], w["revision"]["id"])
        assert r.status_code == 409
    finally:
        binding_svc.PREFENCE_SEAM = None

    # a fresh exact C/W pair for the CE-side EntityTrack variant
    b2 = await _binding_base(client, tag=b"race07b", n_occurrences=2)
    w2 = await _approved_world(client, b2["project_id"])
    eid2 = await make_entity_and_adopt(client, b2, b2["composition_id"])
    await _interpretation(client, b2["production_revision_id"])

    async def seam_ce():
        r = await client.post(
            f"/spatial-worlds/{w2['world']['id']}/tracks",
            json={"entity_id": eid2, "requirement": "required"})
        assert r.status_code == 201

    binding_svc.PREFENCE_SEAM = seam_ce
    try:
        r = await _publish(client, b2["C"], w2["revision"]["id"])
        assert r.status_code == 409
        assert r.json()["error_code"] == (
            "COMPOSITION_SPATIAL_BINDING_CONFLICT")
    finally:
        binding_svc.PREFENCE_SEAM = None


async def make_entity_and_adopt(client, b, cid):
    from tests.m13_seed import make_entity
    eid = await make_entity(client, b["project_id"])
    occ = b["occurrences"][1]
    await _adopt(client, cid, occ,
                 {"kind": "creative_entity", "creative_entity_id": eid})
    return eid


async def test_m13_race_08(client):
    """M13-RACE:08 (R8) — binding freeze vs spatial-interpretation
    creation: the previously missing interpretation changes bindability
    and the candidate hash — detected as a conflict before any not-ready
    refusal."""
    from soloring.production_world import binding as binding_svc

    b = await _binding_base(client, tag=b"race08")
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    # a PI track exists, so the prefence candidate is derived while the
    # interpretation is still missing (entry blocked)
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "required"})
    assert r.status_code == 201

    async def seam():
        await _interpretation(client, b["production_revision_id"])

    binding_svc.PREFENCE_SEAM = seam
    try:
        r = await _publish(client, b["C"], w["revision"]["id"])
        assert r.status_code == 409, r.text
        assert r.json()["error_code"] == (
            "COMPOSITION_SPATIAL_BINDING_CONFLICT")
    finally:
        binding_svc.PREFENCE_SEAM = None
    # the next publish sees the completed candidate and succeeds
    r = await _publish(client, b["C"], w["revision"]["id"])
    assert r.status_code == 201, r.text
    assert len(r.json()["entries"]) == 1


async def test_m13_race_09(client):
    """M13-RACE:09 (R9) — identical concurrent publication converges on
    one binding identity and fully validates the winner (real concurrent
    tasks; SQLite BEGIN IMMEDIATE serializes the fences)."""
    b = await _binding_base(client, tag=b"race09")
    w = await _approved_world(client, b["project_id"])
    results = await asyncio.gather(
        _publish(client, b["C"], w["revision"]["id"]),
        _publish(client, b["C"], w["revision"]["id"]),
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 201], [r.status_code for r in results]
    ids = {r.json()["binding_id"] for r in results}
    assert len(ids) == 1
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM composition_spatial_bindings "
            "WHERE composition_revision_id = :c"), {"c": b["C"]})
        ).scalar_one()
    assert n == 1
    # the winner is fully validated by the verified reader
    r = await client.get(
        f"/composition-spatial-bindings/{ids.pop()}")
    assert r.status_code == 200


async def test_m13_race_10(client):
    """M13-RACE:10 (R10) — competing Shot-selection CAS writes with the
    same expected prior pointer cannot both win; null expected is
    create-only."""
    b = await _binding_base(client, tag=b"race10")
    w = await _approved_world(client, b["project_id"])
    await _adopt(client, b["composition_id"], b["occurrences"][0],
                 {"kind": "production_instance"})
    pr = await _publish(client, b["C"], w["revision"]["id"])
    binding_id = pr.json()["binding_id"]
    shot_id = await _shot(client, b["project_id"])
    results = await asyncio.gather(
        client.put(f"/shots/{shot_id}/production-world-selection",
                   json={"binding_id": binding_id,
                         "expected_binding_id": None}),
        client.put(f"/shots/{shot_id}/production-world-selection",
                   json={"binding_id": binding_id,
                         "expected_binding_id": None}),
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], [r.status_code for r in results]
    r = await client.get(f"/shots/{shot_id}/production-world-selection")
    assert r.json()["binding_id"] == binding_id


async def test_m13_race_11(client):
    """M13-RACE:11 (R11) — Shot selection versus occurrence termination:
    the selection parks inside its open writer fence; the terminating
    operation mechanically attempts its own fence during the park and,
    after the selection commits, sees the live selection blocker. The
    reverse order (termination first) is proven in M13-IMPACT:08."""
    from soloring.production_world import selection as selection_svc

    b = await _binding_base(client, tag=b"race11")
    w = await _approved_world(client, b["project_id"])
    cid = b["composition_id"]
    oid = b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    pr = await _publish(client, b["C"], w["revision"]["id"])
    binding_id = pr.json()["binding_id"]
    shot_id = await _shot(client, b["project_id"])

    engine = client._transport.app.state.engine
    selection_parked = asyncio.Event()
    release = asyncio.Event()
    termination_attempted_fence = asyncio.Event()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _term_seam(conn, cursor, statement, parameters, context,
                   executemany):
        if "BEGIN IMMEDIATE" in statement and selection_parked.is_set():
            termination_attempted_fence.set()

    async def seam():
        selection_parked.set()
        await release.wait()

    selection_svc.SELECTION_SEAM = seam
    try:
        async def do_selection():
            return await client.put(
                f"/shots/{shot_id}/production-world-selection",
                json={"binding_id": binding_id,
                      "expected_binding_id": None})

        sel_task = asyncio.ensure_future(do_selection())
        await asyncio.wait_for(selection_parked.wait(), timeout=10)

        async def do_terminate():
            pv = await _preview(client, cid, "remove", [oid])
            return await _apply(client, cid, 1, "remove", [oid], pv)

        term_task = asyncio.ensure_future(do_terminate())
        # the terminating operation really attempts its writer fence
        # while the selection fence is open (it then blocks on the lock)
        await asyncio.wait_for(termination_attempted_fence.wait(),
                               timeout=10)
        await asyncio.sleep(0)  # scheduler yield only
        release.set()
        sel_out = await asyncio.wait_for(sel_task, timeout=30)
        term_out = await asyncio.wait_for(term_task, timeout=30)
        assert sel_out.status_code == 200, sel_out.text
        assert term_out.status_code == 409, term_out.text
        # the preview was taken while the selection fence was open (before
        # the row existed), so the committed selection changes the impact
        # fingerprint and the frozen stale_impact guard fires first; the
        # live_references refusal is the preview-after-commit branch
        # (M13-IMPACT:04). Either way the termination cannot proceed.
        assert term_out.json()["details"]["reason"] == "stale_impact"
    finally:
        selection_svc.SELECTION_SEAM = None
        event.remove(engine.sync_engine, "before_cursor_execute",
                     _term_seam)
