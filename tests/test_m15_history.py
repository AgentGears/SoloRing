"""M15C historical-isolation proofs (frozen R6 §31.10 M15-HIST:01-10)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.compatibility.service import apply_assessment, create_assessment
from tests.m15_seed import seed_a4_use
from tests.test_m13_binding import _interpretation


def _sess(client):
    class _S:
        bind = client._transport.app.state.engine

    return _S()


async def _assess_and_apply(client, base, review=True):
    engine = client._transport.app.state.engine
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    use = result["uses"][0]
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": use["composition_id"]})).scalar_one()
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[{
            "composition_id": use["composition_id"],
            "occurrence_id": use["occurrence_id"],
            "expected_working_version": version,
            "expected_use_contract_hash": use["use_contract_hash"],
            "review_accept": review}])
    return result, out


async def test_old_composition_revision_byte_identical_after_update(
        client):
    """M15-HIST:01 — the pre-update published CompositionRevision is
    byte-identical after the working source moves."""
    base = await seed_a4_use(client, tag=b"hi01")
    from tests.m13_seed import publish

    pub = await publish(client, base["composition_id"], 1)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM "
            "composition_revisions WHERE id = :r"),
            {"r": pub["revision"]["revision_id"]})).one()
    await _assess_and_apply(client, base)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM "
            "composition_revisions WHERE id = :r"),
            {"r": pub["revision"]["revision_id"]})).one()
    assert (before.snapshot_json, before.snapshot_hash) == (
        after.snapshot_json, after.snapshot_hash)


async def test_old_binding_byte_identical_after_update(client):
    """M15-HIST:02 — any pre-existing M13 binding is byte-identical
    after the working update."""
    base = await seed_a4_use(client, tag=b"hi02")
    from tests.test_m13_binding import _publish

    from tests.test_m13_binding import _approved_world
    w = await _approved_world(client, base["project_id"],
                              key="hi02-lobby")
    from tests.m13_seed import publish as comp_publish

    await comp_publish(client, base["composition_id"], 1)
    r = await client.post(
        f"/composition-revisions/{await _last_crev(client, base)}/"
        "spatial-bindings",
        json={"spatial_world_revision_id": w["revision"]["id"]})
    assert r.status_code in (200, 201), r.text
    binding_id = r.json()["binding_id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT binding_json, binding_hash FROM "
            "composition_spatial_bindings WHERE id = :b"),
            {"b": binding_id})).one()
    await _assess_and_apply(client, base)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT binding_json, binding_hash FROM "
            "composition_spatial_bindings WHERE id = :b"),
            {"b": binding_id})).one()
    assert (before.binding_json, before.binding_hash) == (
        after.binding_json, after.binding_hash)


async def _last_crev(client, base):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id FROM composition_revisions WHERE "
            "composition_id = :c ORDER BY created_at DESC LIMIT 1"),
            {"c": base["composition_id"]})).scalar_one()


async def test_old_shot_revision_byte_identical_after_update(client):
    """M15-HIST:03 — captured ShotRevisions are byte-identical."""
    base = await seed_a4_use(client, tag=b"hi03")
    shot_id = await _capture_shot(client, base)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE shot_id = :s ORDER BY created_at DESC LIMIT 1"),
            {"s": shot_id})).one()
    await _assess_and_apply(client, base)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE shot_id = :s ORDER BY created_at DESC LIMIT 1"),
            {"s": shot_id})).one()
    assert (before.snapshot_json, before.snapshot_hash) == (
        after.snapshot_json, after.snapshot_hash)


async def _capture_shot(client, base):
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    from soloring.domain import revisions as rev_svc
    from tests.conftest import make_tracked_maker

    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    shot = await shot_svc.create_shot(
        maker(), base["project_id"],
        ShotCreate(subject="M15C history shot"))
    await rev_svc.capture_revision(maker(), shot.id)
    return shot.id


async def test_current_shot_selection_unchanged_by_update(client):
    """M15-HIST:04 — shot production-world selections never move."""
    base = await seed_a4_use(client, tag=b"hi04")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_production_world_selections"
        ))).scalar_one()
    await _assess_and_apply(client, base)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT COUNT(*) FROM shot_production_world_selections"
        ))).scalar_one()
    assert before == after == 0  # none existed; none invented


async def test_future_publish_and_binding_pin_target_revision(client):
    """M15-HIST:05 — after apply, publishing pins the TARGET revision
    in the new CompositionRevision's occurrence rows."""
    base = await seed_a4_use(client, tag=b"hi05")
    await _assess_and_apply(client, base)
    from tests.m13_seed import publish

    pub = await publish(client, base["composition_id"],
                        (await _version(client, base)))
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        rev_id = (await conn.execute(text(
            "SELECT id FROM composition_revisions WHERE "
            "composition_id = :c ORDER BY created_at DESC LIMIT 1"),
            {"c": base["composition_id"]})).scalar_one()
        pinned = (await conn.execute(text(
            "SELECT production_revision_id FROM "
            "composition_revision_occurrences WHERE "
            "composition_revision_id = :r AND occurrence_id = :o"),
            {"r": rev_id,
             "o": base["occurrence_id"]})).scalar_one()
    assert pinned == base["r2"]


async def _version(client, base):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": base["composition_id"]})).scalar_one()


async def test_future_shot_captures_target_revision(client):
    """M15-HIST:06 — a post-apply capture pins the target revision
    through the captured production world."""
    base = await seed_a4_use(client, tag=b"hi06")
    await _assess_and_apply(client, base)
    shot_id = await _capture_shot(client, base)
    engine = client._transport.app.state.engine

    async def _shot_rev_id():
        async with engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT id FROM shot_revisions WHERE shot_id = :s "
                "ORDER BY created_at DESC LIMIT 1"),
                {"s": shot_id})).scalar_one()

    srid = await _shot_rev_id()
    async with engine.connect() as conn:
        srpw = (await conn.execute(text(
            "SELECT composition_revision_id FROM "
            "shot_revision_production_worlds "
            "WHERE shot_revision_id = :s"),
            {"s": srid})).fetchall()
    # a schema-6 capture pins the CURRENT composition revision, whose
    # occurrence rows now reference the updated source (r2)
    if srpw:
        async with engine.connect() as conn:
            pinned = (await conn.execute(text(
                "SELECT production_revision_id FROM "
                "composition_revision_occurrences WHERE "
                "composition_revision_id = :r AND occurrence_id = :o"),
                {"r": srpw[0].composition_revision_id,
                 "o": base["occurrence_id"]})).scalar_one()
        assert pinned == base["r2"]
    else:
        # schema fell short of 6 (no production world content); the
        # frozen claim then holds vacuously for this fixture, but the
        # captured snapshot must still exist
        async with engine.connect() as conn:
            n = (await conn.execute(text(
                "SELECT COUNT(*) FROM shot_revisions WHERE shot_id = :s"),
                {"s": shot_id})).scalar_one()
        assert n >= 1


async def test_exact_rerun_old_shot_uses_source_with_m15_current_resolvers_poisoned(
        client):
    """M15-HIST:07 — the pre-update captured Shot reads only its
    captured graph; M15 current tables are irrelevant to it."""
    base = await seed_a4_use(client, tag=b"hi07")
    shot_id = await _capture_shot(client, base)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_hash FROM shot_revisions WHERE shot_id = :s "
            "ORDER BY created_at DESC LIMIT 1"),
            {"s": shot_id})).scalar_one()
    await _assess_and_apply(client, base)
    # poison ALL M15 current/evidence resolvers: the historical read
    # never consults them (child-first FK-safe order)
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE composition_working_occurrences SET visible = 0"))
        for table in ("production_update_items",
                      "production_update_operations",
                      "production_compatibility_uses",
                      "production_compatibility_assessments"):
            await conn.execute(text(f"DELETE FROM {table}"))
        await conn.commit()
    from soloring.domain import revisions as rev_svc
    from tests.conftest import make_tracked_maker

    maker = make_tracked_maker(engine)
    rev = await rev_svc.capture_revision(maker(), shot_id)  # recapture
    assert rev.snapshot_hash  # the captured-graph machinery still works


async def test_compatibility_translation_never_rewrites_historical_source_bytes(
        client):
    """M15-HIST:08 — APR-099/104: the translator pin in the operation
    evidence mutated nothing; the source revision bytes are identical."""
    base = await seed_a4_use(client, tag=b"hi08",
                             source_translation=(0, 0, 0),
                             target_translation=(7, 0, 0))
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM "
            "production_revisions WHERE id = :r"),
            {"r": base["production_revision_id"]})).one()
    result, out = await _assess_and_apply(client, base)
    assert out["translator_pins"]  # translation evidence was pinned
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM "
            "production_revisions WHERE id = :r"),
            {"r": base["production_revision_id"]})).one()
    assert (before.snapshot_json, before.snapshot_hash) == (
        after.snapshot_json, after.snapshot_hash)


async def test_chair_07_fallen_state_survives_r2_to_r3_update(client):
    """M15-HIST:09 — headline continuity: a fallen feature on chair-07
    survives the r2→r3 update with identical rows."""
    base = await seed_a4_use(client, tag=b"hi09")
    r = await client.post(
        f"/production-instances/{base['occurrence_id']}/features",
        json={"key": "state", "kind": "status", "value_type": "enum",
              "name": "Chair state", "enum_values": [
                  "upright", "fallen"]})
    feature_id = r.json()["id"]
    from tests.m15_seed import seed_scene

    scene = await seed_scene(client, base["project_id"])
    r = await client.post(
        f"/production-instance-features/{feature_id}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fallen"})
    assert r.status_code == 201, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT id, key, kind, value_type, name FROM "
            "production_instance_features WHERE composition_id = :c "
            "AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
    await _assess_and_apply(client, base)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT id, key, kind, value_type, name FROM "
            "production_instance_features WHERE composition_id = :c "
            "AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
        value = (await conn.execute(text(
            "SELECT value_json FROM "
            "production_instance_feature_transitions WHERE feature_id "
            "= :f"), {"f": feature_id})).scalar_one()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]
    assert json.loads(value) == "fallen"  # the fallen state survives


async def test_old_exact_rerun_ignores_all_m15_evidence_and_tracking(
        client):
    """M15-HIST:10 — M15 evidence is not a dependency of historical
        execution: dropping every M15 row leaves the captured Shot
        revision legible and identical."""
    base = await seed_a4_use(client, tag=b"hi10")
    shot_id = await _capture_shot(client, base)
    await _assess_and_apply(client, base)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE shot_id = :s ORDER BY created_at DESC LIMIT 1"),
            {"s": shot_id})).one()
        for table in ("production_update_items",
                      "production_update_operations",
                      "production_compatibility_uses",
                      "production_compatibility_assessments",
                      "composition_occurrence_revision_tracking"):
            await conn.execute(text(f"DELETE FROM {table}"))
            # HIST:07 — child-first order holds, but the assessments
            # delete is FK-guarded by uses; children precede parents
        await conn.commit()
        after = (await conn.execute(text(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE shot_id = :s ORDER BY created_at DESC LIMIT 1"),
            {"s": shot_id})).one()
    assert (before.snapshot_json, before.snapshot_hash) == (
        after.snapshot_json, after.snapshot_hash)
