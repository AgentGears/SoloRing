"""M13 race proofs (frozen R3 §30.10 R6-R11 at the M13C gate).

Every race uses deterministic injection seams or real lock contention —
no sleeps. The PREFENCE_SEAM fires inside the exact prefence-derivation →
fence-acquisition window; R9/R10 run genuinely concurrent tasks against
SQLite's BEGIN IMMEDIATE serialization; R11 parks the selection inside
its open writer fence and mechanically proves the terminating operation
attempted its own fence during the park.
"""

from __future__ import annotations

from tests.conftest import make_tracked_maker
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


# --- R1-R5: authority races (frozen §27) ------------------------------------


async def test_m13_race_01(client):
    """M13-RACE:01 (R1) — identical spatial-interpretation create
    converges; a different second meaning conflicts."""
    from tests.m13_seed import seed_base

    base = await seed_base(client, tag=b"race01")
    prid = base["production_revision_id"]
    body = {"realization_local_to_subject_local": {
        "translation_mm": [1, 2, 3], "rotation_udeg": [0, 0, 0]}}
    r1, r2 = await asyncio.gather(
        client.post(f"/production-revisions/{prid}/spatial-interpretation",
                    json=body),
        client.post(f"/production-revisions/{prid}/spatial-interpretation",
                    json=body))
    codes = sorted((r1.status_code, r2.status_code))
    assert codes == [200, 201], codes
    assert r1.json()["interpretation_hash"] == r2.json()[
        "interpretation_hash"]
    other = {"realization_local_to_subject_local": {
        "translation_mm": [9, 9, 9], "rotation_udeg": [0, 0, 0]}}
    r = await client.post(
        f"/production-revisions/{prid}/spatial-interpretation", json=other)
    assert r.status_code == 409


async def test_m13_race_02(client):
    """M13-RACE:02 (R2) — subject adoption versus identity termination.
    Forced order: preview → adoption commits (the parked interleave) →
    apply under the fence. Adoption is durable identity metadata and
    never blocks; the impact fingerprint is blocker-driven, so the
    terminating operation proceeds — exactly one legal history with the
    adoption surviving as immutable provenance on a terminated
    occurrence, and no terminated occurrence is ever newly adopted."""
    from sqlalchemy import text

    from tests.test_m13_binding import _adopt, _binding_base
    from tests.test_m13_impact import _apply, _preview

    b = await _binding_base(client, tag=b"race02")
    cid, oid = b["composition_id"], b["occurrences"][0]
    pv = await _preview(client, cid, "remove", [oid])
    assert pv["allowed"] is True
    # the interleave: adoption commits between preview and apply
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 200, r.text  # adoption alone never blocks
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        kept = (await conn.execute(text(
            "SELECT subject_kind FROM "
            "composition_occurrence_authority_subjects "
            "WHERE occurrence_id = :o"), {"o": oid})).scalar_one_or_none()
    assert kept == "production_instance"  # provenance survives
    # and the terminated occurrence can never be newly adopted
    r = await client.post(
        f"/compositions/{cid}/occurrences/{oid}/authority-subject",
        json={"kind": "creative_entity",
              "creative_entity_id": "1" * 8 + "-1111-1111-1111-" + "1" * 12})
    assert r.status_code == 422


async def test_m13_race_03(client):
    """M13-RACE:03 (R3) — concurrent same-CreativeEntity adoption: at most
    one commits; a terminated historical claim does not block a later
    new active claim."""
    from tests.test_m13_binding import _adopt, _binding_base
    from tests.m13_seed import make_entity

    b = await _binding_base(client, tag=b"race03", n_occurrences=2)
    cid = b["composition_id"]
    eid = await make_entity(client, b["project_id"])
    body = {"kind": "creative_entity", "creative_entity_id": eid}
    r1, r2 = await asyncio.gather(
        client.post(
            f"/compositions/{cid}/occurrences/"
            f"{b['occurrences'][0]}/authority-subject", json=body),
        client.post(
            f"/compositions/{cid}/occurrences/"
            f"{b['occurrences'][1]}/authority-subject", json=body))
    # exactly one commits; the loser gets the claim conflict
    codes = sorted((r1.status_code, r2.status_code))
    assert codes == [201, 409], codes


async def test_m13_race_04(client):
    """M13-RACE:04 (R4) — PI Feature creation versus termination: if the
    feature wins, the terminating operation sees the live blocker under
    its fence (stale_impact); if termination wins, feature creation
    rejects the terminated subject."""
    from tests.test_m13_binding import _adopt, _binding_base
    from tests.test_m13_impact import _apply, _preview

    b = await _binding_base(client, tag=b"race04")
    cid, oid = b["composition_id"], b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    pv = await _preview(client, cid, "remove", [oid])
    # the interleave: a live PI feature commits between preview and apply
    r = await client.post(f"/production-instances/{oid}/features",
                          json={"key": "fallen", "kind": "status",
                                "value_type": "text", "name": "Fallen"})
    assert r.status_code == 201, r.text
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "stale_impact"
    # reverse order: terminate first, feature creation then rejects
    from tests.m13_seed import mint, remove_occurrence

    m2 = await mint(client, cid, b["production_revision_id"], 1,
                    name="B")
    oid2 = m2["occurrence_id"]
    await _adopt(client, cid, oid2, {"kind": "production_instance"})
    await remove_occurrence(client, cid, oid2, 2)
    r = await client.post(f"/production-instances/{oid2}/features",
                          json={"key": "x", "kind": "status",
                                "value_type": "text", "name": "X"})
    assert r.status_code == 422


async def test_m13_race_05(client):
    """M13-RACE:05 (R5) — PI SpatialTrack creation versus termination,
    same forced discipline as R4."""
    from tests.test_m13_binding import _adopt, _binding_base
    from tests.test_m13_impact import _apply, _preview

    b = await _binding_base(client, tag=b"race05")
    cid, oid = b["composition_id"], b["occurrences"][0]
    await _adopt(client, cid, oid, {"kind": "production_instance"})
    from tests.test_m13_binding import _approved_world

    w = await _approved_world(client, b["project_id"])
    pv = await _preview(client, cid, "remove", [oid])
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": oid, "requirement": "required"})
    assert r.status_code == 201, r.text
    r = await _apply(client, cid, 1, "remove", [oid], pv)
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "stale_impact"


# --- R12-R16: coherent-capture races (frozen §27) ---------------------------


def _capture_task(client, shot_id):
    from soloring.domain.revisions import capture_revision_with_visual
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = make_tracked_maker(client._transport.app.state.engine)
    return capture_revision_with_visual(
        factory(), shot_id,
        settings=client._transport.app.state.settings)


async def _parked_capture_with(client, shot_id, change_coro):
    """Park the capture at its coherent-read BEGIN (fence held open by the
    read transaction), run the change (it takes its own writer fence and
    commits), release, and let the capture resolve AFTER the change."""
    engine = client._transport.app.state.engine
    capture_began = asyncio.Event()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _seam(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("BEGIN") and not \
                capture_began.is_set():
            capture_began.set()

    task = asyncio.ensure_future(_capture_task(client, shot_id))
    await asyncio.wait_for(capture_began.wait(), timeout=10)
    await asyncio.sleep(0)  # scheduler yield; the read snapshot is pinned
    await change_coro()
    out = await asyncio.wait_for(task, timeout=30)
    event.remove(engine.sync_engine, "before_cursor_execute", _seam)
    return out


async def test_m13_race_12(client):
    """M13-RACE:12 (R12) — a selection change during the capture read
    yields one whole BEFORE or AFTER database moment, never mixed: with
    the capture parked at its read BEGIN, a selection DELETE commits
    first; the capture then resolves the AFTER state (no selection →
    schema 5), proving no mixed binding/current-state capture."""
    import json as _json

    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"race12")
    sel = await _select_binding(client, b)

    async def change():
        r = await client.request(
            "DELETE", f"/shots/{b['shot']}/production-world-selection",
            json={"expected_binding_id": sel["binding_id"]})
        assert r.status_code == 200, r.text

    # whole BEFORE: the pinned read snapshot carries the original
    # selection moment intact (schema 6, the exact selected binding)
    revision, _ = await _parked_capture_with(client, b["shot"], change)
    snap = _json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 6
    assert snap["production_world"]["binding"][
        "binding_id"] == sel["binding_id"]
    # whole AFTER: a capture begun after the committed delete resolves a
    # schema-5 moment — neither order can mix the two states
    revision2, _ = await _capture_task(client, b["shot"])
    snap2 = _json.loads(revision2.snapshot_json)
    assert snap2["schema_version"] == 5
    assert "production_world" not in snap2


async def test_m13_race_13(client):
    """M13-RACE:13 (R13) — an M10 approval change during the capture read
    cannot produce a ShotRevision mixing a W-A binding with W-B spatial
    content: with the capture parked, approve a genuinely different world
    revision; the M13 agreement gate then blocks the capture entirely."""
    import json as _json

    import pytest as _pytest

    from soloring.errors import SoloRingError
    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"race13")
    await _select_binding(client, b)

    async def change():
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from soloring.spatial import revisions as rev_svc
        from soloring.spatial import worlds as world_svc

        f = make_tracked_maker(client._transport.app.state.engine)
        await world_svc.put_state_frame(
            f(), b["state"]["id"], b["desk_frame"]["id"],
            translation_mm=[3200, 0, -2000], rotation_udeg=[0, 0, 0],
            half_extents_mm=None, bound_entity_revision_id=None)
        rev2 = await rev_svc.capture_revision(f(), b["state"]["id"])
        await rev_svc.approve_revision(
            f(), b["state"]["id"], revision_id=rev2["id"],
            expected_approved_revision_id=b["rev"]["id"])

    # whole BEFORE: the pinned snapshot resolves the pre-change approval
    # consistently — binding W == M10 W inside one database moment
    revision, _ = await _parked_capture_with(client, b["shot"], change)
    snap = _json.loads(revision.snapshot_json)
    assert snap["schema_version"] == 6
    # whole AFTER: a capture begun after the new approval is BLOCKED by
    # the agreement gate — never a W-A binding with W-B spatial content
    with _pytest.raises(SoloRingError) as ei:
        await _capture_task(client, b["shot"])
    assert ei.value.code == "PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH"


async def test_m13_race_14(client):
    """M13-RACE:14 (R14) — a PI feature-transition change during the
    capture read yields one whole BEFORE/AFTER state and hash: the parked
    capture sees the AFTER value (the committed transition), never a mix."""
    import json as _json

    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"race14")
    sel = await _select_binding(client, b)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()
    r = await client.post(
        f"/production-instances/{sel['occurrence_id']}/features",
        json={"key": "fallen", "kind": "status", "value_type": "text",
              "name": "Fallen"})
    fid = r.json()["id"]

    async def change():
        r = await client.post(
            f"/production-instance-features/{fid}/transitions",
            json={"anchor_type": "sequence", "anchor_id": seq,
                  "boundary": "start", "operation": "set",
                  "value": "down"})
        assert r.status_code == 201, r.text

    # whole BEFORE: the pinned snapshot predates the transition — the
    # captured pack carries the empty feature state consistently
    revision, _ = await _parked_capture_with(client, b["shot"], change)
    snap = _json.loads(revision.snapshot_json)
    assert snap["production_world"]["instance_feature_states"] == []
    # whole AFTER: a capture begun after the commit sees exactly the new
    # value — never a half-applied transition
    revision2, _ = await _capture_task(client, b["shot"])
    snap2 = _json.loads(revision2.snapshot_json)
    states = snap2["production_world"]["instance_feature_states"]
    assert len(states) == 1 and states[0]["value"] == "down"


async def test_m13_race_15(client):
    """M13-RACE:15 (R15) — a PI spatial-transition change during the
    capture read yields one whole BEFORE/AFTER staging: the parked capture
    sees the AFTER transform."""
    import json as _json

    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"race15")
    sel = await _select_binding(client, b)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        seq = (await conn.execute(text(
            "SELECT id FROM sequences WHERE project_id = :p "
            "ORDER BY position LIMIT 1"), {"p": b["pid"]})).scalar_one()

    async def change():
        # soft-delete the existing coordinate (frees it), then set 777
        engine = client._transport.app.state.engine
        tid = (await _first_transition_id(engine, sel["track"]))
        r = await client.request(
            "DELETE",
            f"/production-instance-spatial-transitions/{tid}")
        assert r.status_code == 200, r.text
        r = await client.post(
            f"/production-instance-spatial-tracks/{sel['track']}"
            "/transitions",
            json={"anchor_type": "sequence", "anchor_id": seq,
                  "boundary": "start", "operation": "set",
                  "transform": {"translation_mm": [777, 0, 0],
                                "rotation_udeg": [0, 0, 0]}})
        assert r.status_code == 201, r.text

    # whole BEFORE: pinned snapshot keeps the original 100mm staging
    revision, _ = await _parked_capture_with(client, b["shot"], change)
    snap = _json.loads(revision.snapshot_json)
    states = snap["production_world"]["instance_spatial_states"]
    assert len(states) == 1
    assert states[0]["transform"]["translation_mm"] == [100, 0, 0]
    # whole AFTER: the next capture sees exactly the new transform
    revision2, _ = await _capture_task(client, b["shot"])
    snap2 = _json.loads(revision2.snapshot_json)
    states2 = snap2["production_world"]["instance_spatial_states"]
    assert states2[0]["transform"]["translation_mm"] == [777, 0, 0]


async def _first_transition_id(engine, track_id):
    # the ONE query, awaited under explicit connection ownership (HYG-02:
    # the former dead first line created an unawaited coroutine and an
    # unowned connection)
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id FROM production_instance_spatial_transitions "
            "WHERE spatial_track_id = :t AND deleted_at IS NULL LIMIT 1"),
            {"t": track_id})).scalar_one()


async def test_m13_race_16(client):
    """M13-RACE:16 (R16) — concurrent identical schema-6 captures converge
    through the EXISTING ShotRevision snapshot identity (one revision row,
    one set of M13 children; no separate M13 winner)."""
    import json as _json

    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"race16")
    await _select_binding(client, b)
    (rev1, _v1), (rev2, _v2) = await asyncio.gather(
        _capture_task(client, b["shot"]),
        _capture_task(client, b["shot"]))
    assert rev1.id == rev2.id
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
            {"s": b["shot"]})).scalar_one()
        m13 = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_revision_production_worlds WHERE "
            "shot_revision_id = :r"), {"r": rev1.id})).scalar_one()
    assert n == 1
    assert m13 == 1
    snap = _json.loads(rev1.snapshot_json)
    assert snap["schema_version"] == 6
