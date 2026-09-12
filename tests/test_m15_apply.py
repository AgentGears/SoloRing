"""M15C apply proofs (frozen R6 §31.8 M15-APPLY:01-16)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.compatibility.service import apply_assessment, create_assessment
from soloring.errors import SoloRingError
from tests.m15_seed import seed_a4_use
from tests.m13_seed import make_composition, mint, publish, seed_base


class _S:
    def __init__(self, engine):
        self.bind = engine


def _sess(client):
    return _S(client._transport.app.state.engine)


async def _assess(client, base, review=False):
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    use = result["uses"][0]
    return result, {
        "composition_id": use["composition_id"],
        "occurrence_id": use["occurrence_id"],
        "expected_working_version": _working_version(client, use),
        "expected_use_contract_hash": use["use_contract_hash"],
        "review_accept": review}


def _working_version(client, use):
    engine = client._transport.app.state.engine
    import asyncio

    async def _get():
        async with engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT working_version FROM compositions WHERE id = :c"),
                {"c": use["composition_id"]})).scalar_one()
    return asyncio.get_event_loop().run_until_complete(_get()) \
        if False else None  # replaced below


async def _selection(client, result, review=False):
    use = result["uses"][0]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": use["composition_id"]})).scalar_one()
    return {
        "composition_id": use["composition_id"],
        "occurrence_id": use["occurrence_id"],
        "expected_working_version": version,
        "expected_use_contract_hash": use["use_contract_hash"],
        "review_accept": review}


async def _working_version_async(client, cid):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": cid})).scalar_one()


async def test_review_accepted_use_updates_selected_working_source_only(
        client):
    """M15-APPLY:01 — a review-accepted legal v1 use updates ONLY the
    selected working source; nothing else in the row moves."""
    base = await seed_a4_use(client, tag=b"ap01")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    assert out["idempotent"] is False
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT production_revision_id, display_name, visible, "
            "x_mm, y_mm, z_mm FROM composition_working_occurrences "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": sel["composition_id"],
             "o": sel["occurrence_id"]})).one()
    assert row.production_revision_id == base["r2"]
    assert row.display_name == "Chair 7" and row.visible == 1
    assert (row.x_mm, row.y_mm, row.z_mm) == (0, 0, 0)


async def test_review_accepted_translation_dimension_pins_exact_translator(
        client):
    """M15-APPLY:02 — the selected use carried TRANSLATION_REQUIRED
    spatial; the operation item retains the exact translator pins
    under the legal v1 review fold."""
    base = await seed_a4_use(client, tag=b"ap02",
                             source_translation=(0, 0, 0),
                             target_translation=(10, 0, 0))
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    use = result["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == (
        "TRANSLATION_REQUIRED")
    assert use["translator_output_hash"]
    sel = await _selection(client, result, review=True)
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    pin = [p for p in out["translator_pins"]
           if p["occurrence_id"] == sel["occurrence_id"]]
    assert pin and pin[0]["translator_output_hash"] == (
        use["translator_output_hash"])


async def test_review_requires_explicit_acceptance(client):
    """M15-APPLY:03 — a REQUIRES_REVIEW use without review_accept is a
    typed PRODUCTION_UPDATE_BLOCKED refusal with zero mutation."""
    base = await seed_a4_use(client, tag=b"ap03")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=False)
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(client), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.code == "PRODUCTION_UPDATE_BLOCKED"
    assert ei.value.details["reason"] == (
        "review_required_without_acceptance")
    engine = client._transport.app.state.engine
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


async def test_incompatible_cannot_be_forced(client):
    """M15-APPLY:04 — INCOMPATIBLE refuses even with review_accept."""
    base = await seed_a4_use(client, tag=b"ap04",
                             with_target_interpretation=False)
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    assert result["overall_verdict"] == "INCOMPATIBLE"
    sel = await _selection(client, result, review=True)
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(client), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.code == "PRODUCTION_UPDATE_BLOCKED"
    assert ei.value.details["reason"] == "per_use_incompatible"


async def test_each_composition_working_version_increments_once(client):
    """M15-APPLY:05 — two selected uses in ONE composition bump the
    composition working_version exactly once."""
    base = await seed_a4_use(client, tag=b"ap05")
    cid2 = await make_composition(client, base["project_id"])
    await mint(client, base["composition_id"],
               base["production_revision_id"], 1, name="Second")
    await mint(client, cid2, base["production_revision_id"], 0,
               name="Other comp")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    cid = base["composition_id"]
    same_comp_uses = [u for u in result["uses"]
                      if u["composition_id"] == cid]
    assert len(same_comp_uses) == 2
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": cid})).scalar_one()
    sel = [{
        "composition_id": u["composition_id"],
        "occurrence_id": u["occurrence_id"],
        "expected_working_version": version,
        "expected_use_contract_hash": u["use_contract_hash"],
        "review_accept": True}
        for u in same_comp_uses]
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=sel)
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": cid})).scalar_one()
        items = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_update_items io "
            "JOIN production_update_operations o "
            "ON o.id = io.operation_id "
            "WHERE o.id = :op"),
            {"op": out["operation_id"]})).scalar_one()
    assert after == version + 1  # exactly once regardless of 2 items
    assert items == 2


async def test_occurrence_identity_unchanged(client):
    """M15-APPLY:06 — APR-103: the occurrence UUID is never reminted."""
    base = await seed_a4_use(client, tag=b"ap06")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM composition_occurrences "
            "WHERE id = :o"),
            {"o": sel["occurrence_id"]})).scalar_one()
        working = (await conn.execute(text(
            "SELECT COUNT(*) FROM composition_working_occurrences "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": sel["composition_id"],
             "o": sel["occurrence_id"]})).scalar_one()
    assert n == 1
    assert working == 1  # same id, still present, not reminted


async def test_instance_feature_and_subject_rows_unchanged(client):
    """M15-APPLY:07 — persistent state: feature rows and the authority
    subject row are byte-identical after apply."""
    base = await seed_a4_use(client, tag=b"ap07")
    r = await client.post(
        f"/production-instances/{base['occurrence_id']}/features",
        json={"key": "damage", "kind": "damage", "value_type": "enum",
              "name": "Damage", "enum_values": ["fresh", "broken"]})
    assert r.status_code == 201, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        feats_before = (await conn.execute(text(
            "SELECT id, key, kind, value_type, name, enum_values_json, "
            "unit FROM production_instance_features WHERE "
            "composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
        subj_before = (await conn.execute(text(
            "SELECT subject_kind FROM "
            "composition_occurrence_authority_subjects "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    async with engine.connect() as conn:
        feats_after = (await conn.execute(text(
            "SELECT id, key, kind, value_type, name, enum_values_json, "
            "unit FROM production_instance_features WHERE "
            "composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
        subj_after = (await conn.execute(text(
            "SELECT subject_kind FROM "
            "composition_occurrence_authority_subjects "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
    assert [tuple(r) for r in feats_before] == [tuple(r)
                                                for r in feats_after]
    assert subj_before == subj_after


async def test_instance_spatial_rows_unchanged(client):
    """M15-APPLY:08 — spatial subject: the track row is identical."""
    base = await seed_a4_use(client, tag=b"ap08")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT id, spatial_world_id, requirement, deleted_at "
            "FROM production_instance_spatial_tracks WHERE "
            "composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT id, spatial_world_id, requirement, deleted_at "
            "FROM production_instance_spatial_tracks WHERE "
            "composition_id = :c AND occurrence_id = :o"),
            {"c": base["composition_id"],
             "o": base["occurrence_id"]})).fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


async def test_stale_use_contract_rolls_back_all(client):
    """M15-APPLY:09 — a stale use contract refuses atomically: zero
    operation rows, zero source mutation, even for the fresh item."""
    base = await seed_a4_use(client, tag=b"ap09")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    # drift the contract: a working edit bumps the version and changes
    # the use contract hash
    from soloring.composition.service import patch_working_occurrence
    from tests.conftest import make_tracked_maker

    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    await patch_working_occurrence(
        maker(), sel["composition_id"], sel["occurrence_id"],
        scope="composition_working_state",
        expected_working_version=sel["expected_working_version"],
        display_name="Drifted")
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(client), assessment_id=result["assessment_id"],
            selected_uses=[sel])
    assert ei.value.code == "PRODUCTION_COMPATIBILITY_CONFLICT"
    assert ei.value.details["reason"] in (
        "stale_working_version", "stale_use_contract")
    engine = client._transport.app.state.engine
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


async def test_exact_retry_is_idempotent(client):
    """M15-APPLY:10 — a duplicate apply returns the committed
    operation (idempotent=True, same id/hash), never a second bump."""
    base = await seed_a4_use(client, tag=b"ap10")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    first = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": sel["composition_id"]})).scalar_one()
    # the retry presents the POST-apply contract facts: same stored
    # hash, the new working version
    retry_sel = dict(sel, expected_working_version=version)
    second = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[retry_sel])
    assert second["idempotent"] is True
    assert second["operation_id"] == first["operation_id"]
    assert second["operation_hash"] == first["operation_hash"]
    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": sel["composition_id"]})).scalar_one()
        ops = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_update_operations"
        ))).scalar_one()
    assert after == version  # no double increment
    assert ops == 1


async def test_partial_apply_stales_remaining_same_composition_uses(
        client):
    """M15-APPLY:11 — applying one of two same-composition uses makes
    the other stale (reassessment required before it can apply)."""
    base = await seed_a4_use(client, tag=b"ap11")
    await mint(client, base["composition_id"],
               base["production_revision_id"], 1, name="Second")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    target = result["uses"][0]
    other = result["uses"][1]
    assert target["composition_id"] == other["composition_id"]
    sel = await _selection(client, result, review=True)
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    assert out["reassessment_required"] is True
    stale_ids = {(u["composition_id"], u["occurrence_id"])
                 for u in out["stale_remaining_uses"]}
    assert (other["composition_id"], other["occurrence_id"]) in stale_ids
    # the stale use cannot apply against the old assessment
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": other["composition_id"]})).scalar_one()
    with pytest.raises(SoloRingError) as ei:
        await apply_assessment(
            _sess(client), assessment_id=result["assessment_id"],
            selected_uses=[{
                "composition_id": other["composition_id"],
                "occurrence_id": other["occurrence_id"],
                "expected_working_version": version,
                "expected_use_contract_hash": (
                    other["use_contract_hash"]),
                "review_accept": True}])
    assert ei.value.code == "PRODUCTION_COMPATIBILITY_CONFLICT"


async def test_direct_patch_source_swap_cannot_bypass_compatibility(
        client):
    """M15-APPLY:12 — the ordinary PATCH refuses the same-object
    source swap with the typed compatibility pointer (§15)."""
    from soloring.composition.service import patch_working_occurrence
    from tests.conftest import make_tracked_maker

    base = await seed_a4_use(client, tag=b"ap12")
    engine = client._transport.app.state.engine
    maker = make_tracked_maker(engine)
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": base["composition_id"]})).scalar_one()
    with pytest.raises(SoloRingError) as ei:
        await patch_working_occurrence(
            maker(), base["composition_id"], base["occurrence_id"],
            scope="composition_working_state",
            expected_working_version=version,
            source={"kind": "production_revision",
                    "revision_id": base["r2"]})
    assert ei.value.code == (
        "PRODUCTION_REVISION_UPDATE_REQUIRES_COMPATIBILITY")
    assert ei.value.details["required_action"] == (
        "compatibility_assessment")
    r = await client.patch(
        f"/compositions/{base['composition_id']}/occurrences/"
        f"{base['occurrence_id']}",
        json={"scope": "composition_working_state",
              "expected_working_version": version,
              "source": {"kind": "production_revision",
                         "revision_id": base["r2"]}})
    assert r.status_code == 409
    assert r.json()["error_code"] == (
        "PRODUCTION_REVISION_UPDATE_REQUIRES_COMPATIBILITY")


async def test_parent_incompatible_summary_does_not_block_selected_review_accepted_use(
        client):
    """M15-APPLY:13 — per-use authority: a parent INCOMPATIBLE summary
    does not block applying an independently reviewable selected use."""
    base = await seed_a4_use(client, tag=b"ap13",
                             with_target_interpretation=False)
    pid = base["project_id"]
    # a reviewable use in a second composition (target has no
    # interpretation, so the A4 use is INCOMPATIBLE; the plain A6 use
    # in another composition is REQUIRES_REVIEW)
    cid2 = await make_composition(client, pid)
    occ2 = (await mint(client, cid2, base["production_revision_id"], 0,
                       name="Plain"))["occurrence_id"]
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    assert result["overall_verdict"] == "INCOMPATIBLE"
    review_use = next(u for u in result["uses"]
                      if u["occurrence_id"] == occ2)
    assert review_use["verdict"] == "REQUIRES_REVIEW"
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": cid2})).scalar_one()
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[{
            "composition_id": cid2,
            "occurrence_id": occ2,
            "expected_working_version": version,
            "expected_use_contract_hash": (
                review_use["use_contract_hash"]),
            "review_accept": True}])
    assert out["updated_occurrences"][0]["occurrence_id"] == occ2


async def test_update_operation_fk_pins_exact_assessment_report_hash(
        client):
    """M15-APPLY:14 — the composite FK mechanically rejects a report
    hash that does not match the stored assessment."""
    base = await seed_a4_use(client, tag=b"ap14")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        with pytest.raises(Exception):
            await conn.execute(text(
                "INSERT INTO production_update_operations "
                "(id, project_id, assessment_id, "
                "assessment_report_hash, schema_version, operation_json, "
                "operation_hash, created_at) VALUES "
                "(:i, :p, :a, :rh, 1, '{}', :oh, :n)"),
                {"i": "forged-000000000001", "p": base["project_id"],
                 "a": result["assessment_id"], "rh": "0" * 64,
                 "oh": "f" * 64, "n": "2026-01-01T00:00:00.000Z"})
        await conn.rollback()
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM production_update_operations "
            "WHERE operation_hash = :h"), {"h": "f" * 64})).scalar_one()
    assert n == 0


async def test_partial_apply_response_lists_stale_remaining_uses(client):
    """M15-APPLY:16 — the response carries explicit stale coordinates
    with reassessment_required=true (frozen §14.3)."""
    base = await seed_a4_use(client, tag=b"ap16")
    await mint(client, base["composition_id"],
               base["production_revision_id"], 1, name="Second")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    sel = await _selection(client, result, review=True)
    out = await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[sel])
    other = [u for u in result["uses"]
             if u["occurrence_id"] != sel["occurrence_id"]][0]
    assert out["reassessment_required"] is True
    assert out["stale_remaining_uses"] == [{
        "composition_id": other["composition_id"],
        "occurrence_id": other["occurrence_id"],
        "reason": "working_version_changed"}]
    assert out["post_apply_next_actions"]
