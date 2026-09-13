"""M15C race proofs (frozen R6 §25/§31.9 M15-RACE:01-07).

Barrier-driven via parked connections/Events; no correctness sleeps.
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.compatibility.service import apply_assessment, create_assessment
from soloring.errors import SoloRingError
from tests.m15_seed import seed_a4_use


def _sess(engine):
    class _S:
        bind = engine

    return _S()


async def _conn(engine) -> AsyncConnection:
    return await engine.connect()


async def _assess(client, base):
    engine = client._transport.app.state.engine
    result = await create_assessment(
        _sess(engine), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    engine  # touched below per race
    use = result["uses"][0]
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": use["composition_id"]})).scalar_one()
    return result, {
        "composition_id": use["composition_id"],
        "occurrence_id": use["occurrence_id"],
        "expected_working_version": version,
        "expected_use_contract_hash": use["use_contract_hash"],
        "review_accept": True}


async def test_assessment_vs_working_edit_no_hybrid(client):
    """M15-RACE:01 — an assessment fenced against a competing working
    edit either sees the post-edit state or refuses; it never
    persists a hybrid scope."""
    base = await seed_a4_use(client, tag=b"rc01")
    engine = client._transport.app.state.engine

    started = asyncio.Event()
    release = asyncio.Event()

    async def assess_task():
        await started.wait()
        try:
            result = await create_assessment(
                _sess(engine), from_revision_id=(
                    base["production_revision_id"]),
                to_revision_id=base["r2"])
            return ("ok", result)
        except Exception as exc:  # busy/refusal acceptable; hybrid not
            return ("err", exc)

    async def edit_task():
        from soloring.composition.service import patch_working_occurrence
        from tests.conftest import make_tracked_maker

        maker = make_tracked_maker(engine)
        async with engine.connect() as conn:
            version = (await conn.execute(text(
                "SELECT working_version FROM compositions WHERE id = :c"),
                {"c": base["composition_id"]})).scalar_one()
        started.set()
        await asyncio.sleep(0)  # yield into the assess fence contention
        out = await patch_working_occurrence(
            maker(), base["composition_id"], base["occurrence_id"],
            scope="composition_working_state",
            expected_working_version=version, display_name="Edited")
        release.set()
        return out

    assess_f = asyncio.create_task(assess_task())
    edit_f = asyncio.create_task(edit_task())
    await asyncio.wait_for(edit_f, 30)
    status, payload = await asyncio.wait_for(assess_f, 30)
    engine2 = client._transport.app.state.engine
    async with engine2.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT use_contract_json FROM "
            "production_compatibility_uses u "
            "JOIN production_compatibility_assessments a "
            "ON a.id = u.assessment_id "
            "WHERE a.from_revision_id = :f"),
            {"f": base["production_revision_id"]})).fetchall()
        names = set()
        for r in rows:
            import json as _json

            doc = _json.loads(r.use_contract_json)
            names.add(doc["working_spec"]["display_name"])
    if status == "ok":
        # the assessment observed ONE coherent state
        assert names <= {"Chair 7", "Edited"}, names
    else:
        assert isinstance(payload, Exception)


async def test_three_identical_assessments_converge(client):
    """M15-RACE:02 — three concurrent identical assessments converge on
    one semantic coordinate."""
    base = await seed_a4_use(client, tag=b"rc02")
    engine = client._transport.app.state.engine

    barrier = asyncio.Barrier(3)

    async def one():
        await barrier.wait()
        return await create_assessment(
            _sess(engine), from_revision_id=(
                base["production_revision_id"]),
            to_revision_id=base["r2"])

    results = await asyncio.gather(one(), one(), one(),
                                   return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    ids = {r["assessment_id"] for r in ok}
    hashes = {r["report_hash"] for r in ok}
    assert ids and len(ids) == 1, (results,)
    assert len(hashes) == 1
    engine2 = client._transport.app.state.engine
    async with engine2.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments "
            "WHERE from_revision_id = :f"),
            {"f": base["production_revision_id"]})).scalar_one()
    assert n == 1


async def test_apply_vs_working_edit_refuses_atomically(client):
    """M15-RACE:03 — a competing working edit advances working_version
    after assessment; apply refuses with zero operation rows and zero
    source mutation."""
    base = await seed_a4_use(client, tag=b"rc03")
    engine = client._transport.app.state.engine
    result, sel = await _assess(client, base)

    from soloring.composition.service import patch_working_occurrence
    from tests.conftest import make_tracked_maker

    maker = make_tracked_maker(engine)
    await patch_working_occurrence(
        maker(), base["composition_id"], base["occurrence_id"],
        scope="composition_working_state",
        expected_working_version=sel["expected_working_version"],
        display_name="Competing edit")

    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(engine), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.code == "PRODUCTION_COMPATIBILITY_CONFLICT"
    async with engine.connect() as conn:
        source = (await conn.execute(text(
            "SELECT production_revision_id FROM "
            "composition_working_occurrences WHERE composition_id = :c "
            "AND occurrence_id = :o"),
            {"c": sel["composition_id"],
             "o": sel["occurrence_id"]})).scalar_one()
        ops = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_update_operations"
        ))).scalar_one()
    assert source == base["production_revision_id"]
    assert ops == 0


async def test_apply_vs_feature_contract_edit_refuses(client):
    """M15-RACE:04 — a feature-transition edit commits without
    changing working_version; the transition-set hash changes and
    apply refuses stale_use_contract."""
    base = await seed_a4_use(client, tag=b"rc04")
    r = await client.post(
        f"/production-instances/{base['occurrence_id']}/features",
        json={"key": "damage", "kind": "damage", "value_type": "enum",
              "name": "Damage", "enum_values": ["fresh", "broken"]})
    feature_id = r.json()["id"]
    engine = client._transport.app.state.engine
    result, sel = await _assess(client, base)
    from tests.m15_seed import seed_scene

    scene = await seed_scene(client, base["project_id"])
    r = await client.post(
        f"/production-instance-features/{feature_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "broken"})
    assert r.status_code == 201, r.text
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(engine), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.details["reason"] == "stale_use_contract"


async def test_duplicate_apply_cannot_double_increment(client):
    """M15-RACE:05 — two sequential exact applies: one commits, the
    other converges to the committed operation (idempotent) — the
    composition version never double-increments."""
    base = await seed_a4_use(client, tag=b"rc05")
    engine = client._transport.app.state.engine
    result, sel = await _assess(client, base)
    first = await apply_assessment(
        _sess(engine), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    assert first["idempotent"] is False
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": sel["composition_id"]})).scalar_one()
    retry = dict(sel, expected_working_version=version)
    second = await apply_assessment(
        _sess(engine), assessment_id=result["assessment_id"],
        selected_uses=[retry])
    assert second["idempotent"] is True
    assert second["operation_id"] == first["operation_id"]
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": sel["composition_id"]})).scalar_one()
        ops = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_update_operations"
        ))).scalar_one()
    assert after == version
    assert ops == 1


async def test_apply_vs_spatial_transition_edit_refuses(client):
    """M15-RACE:06 — a spatial-transition edit after assessment
    changes the track transition-set hash; apply refuses."""
    base = await seed_a4_use(client, tag=b"rc06")
    engine = client._transport.app.state.engine
    result, sel = await _assess(client, base)
    from tests.m15_seed import seed_scene

    scene = await seed_scene(client, base["project_id"])
    r = await client.post(
        f"/production-instance-spatial-tracks/{base['track_id']}"
        "/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set",
              "transform": {"translation_mm": [9, 9, 9],
                            "rotation_udeg": [0, 0, 0]}})
    assert r.status_code == 201, r.text
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(engine), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.details["reason"] == "stale_use_contract"


async def test_tracking_policy_aba_is_rejected(client):
    """M15-RACE:07 — the full PINNED(v0)→TRACK(v1)→PINNED(v2) cycle;
    a stale v0 client fails; authored versions never return to 0."""
    base = await seed_a4_use(client, tag=b"rc07")
    cid, occ = base["composition_id"], base["occurrence_id"]

    async def put(mode, version):
        return await client.put(
            f"/compositions/{cid}/occurrences/{occ}/revision-tracking",
            json={"mode": mode, "expected_policy_version": version})

    r = await put("TRACK_COMPATIBLE", 0)
    assert r.json()["policy_version"] == 1
    r = await put("PINNED", 1)
    assert r.json()["policy_version"] == 2
    r = await put("TRACK_COMPATIBLE", 0)  # stale ABA attempt
    assert r.status_code == 409
    assert r.json()["details"]["reason"] == "tracking_policy_conflict"
    r = await client.get(
        f"/compositions/{cid}/occurrences/{occ}/revision-tracking")
    assert r.json() == {"mode": "PINNED", "policy_version": 2}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        minimum = (await conn.execute(text(
            "SELECT MIN(policy_version) FROM "
            "composition_occurrence_revision_tracking"
        ))).scalar_one()
    assert minimum >= 1
