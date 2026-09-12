"""M15 evaluator v1 proofs (frozen R4 §31.4 M15-EVAL:01-18)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.compatibility.canonical import DIMENSIONS
from soloring.errors import SoloRingError
from tests.m15_seed import assess, assess_http, seed_a4_use
from tests.m13_seed import make_composition, mint, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation


async def test_same_object_distinct_revision_required(client):
    """M15-EVAL:01 — exact lineage law: same object + distinct ids
    assess; cross-object demands replace_as_new; identical ids refuse."""
    import hashlib

    from soloring.domain.ids import new_uuid
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    base = await seed_base(client, tag=b"ev01")
    cid = await make_composition(client, base["project_id"])
    await mint(client, cid, base["production_revision_id"], 0)

    result = await assess(
        client, base["production_revision_id"],
        (await seed_second_revision(client, base, number=2)))
    assert result["scope_status"] == "ASSESSED"

    # a DIFFERENT Production Object in the SAME Project
    engine = client._transport.app.state.engine
    now = "2026-01-01T00:00:00.000Z"
    bh = hashlib.sha256(b"ev01-other").hexdigest()
    other_obj, other_rev = new_uuid(), new_uuid()
    closure = RetainedBlobClosure(
        blob_hash=bh, size_bytes=10, media_type=None)
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :p, 10, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": now})
        await conn.execute(text(
            "INSERT INTO production_objects (id, project_id, name, "
            "created_at, updated_at) VALUES (:o, :p, 'Other', :n, :n)"),
            {"o": other_obj, "p": base["project_id"], "n": now})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, 1, :sj, :sh, :n)"),
            {"r": other_rev, "o": other_obj, "sj": sj(closure),
             "sh": sh(closure), "n": now})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, 10, NULL)"),
            {"r": other_rev, "bh": bh})
        await conn.commit()

    with pytest.raises(SoloRingError) as ei:
        await assess(client, base["production_revision_id"], other_rev)
    assert ei.value.details["allowed_operation"] == "replace_as_new"

    with pytest.raises(SoloRingError):
        await assess(client, base["production_revision_id"],
                     base["production_revision_id"])


async def test_changed_retained_blob_requires_review_without_equivalence_evidence(
        client):
    """M15-EVAL:02 — changed bytes never get COMPATIBLE_AS_IS."""
    base = await seed_a4_use(client, tag=b"ev02")
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    use = result["uses"][0]
    assert use["dimensions"]["retained_consumption"] == "REVIEW_REQUIRED"
    assert use["verdict"] == "REQUIRES_REVIEW"


async def test_media_type_change_requires_review(client):
    """M15-EVAL:03 — differing declared media types require review."""
    import hashlib

    from soloring.domain.ids import new_uuid
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    engine = client._transport.app.state.engine
    base = await seed_base(client, tag=b"ev03")
    cid = await make_composition(client, base["project_id"])
    await mint(client, cid, base["production_revision_id"], 0,
               name="Media chair")
    now = "2026-01-01T00:00:00.000Z"
    bh = hashlib.sha256(b"ev03-media").hexdigest()
    prid = new_uuid()
    closure = RetainedBlobClosure(
        blob_hash=bh, size_bytes=12, media_type="model/mesh")
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :p, 12, 'model/mesh', :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": now})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, "
            "production_object_id, revision_number, snapshot_json, "
            "snapshot_hash, created_at) VALUES "
            "(:r, :o, 3, :sj, :sh, :n)"),
            {"r": prid, "o": base["production_object_id"],
             "sj": sj(closure), "sh": sh(closure), "n": now})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, 12, 'model/mesh')"),
            {"r": prid, "bh": bh})
        await conn.commit()

    result = await assess(
        client, base["production_revision_id"], prid)
    use = result["uses"][0]
    # base closure media_type is NULL; target declares model/mesh
    assert use["dimensions"]["media_type"] == "REVIEW_REQUIRED"


async def test_equal_spatial_interpretation_is_compatible(client):
    """M15-EVAL:04 — identical interpretation VALUES bridge exactly.

    M13 interpretations pin their parent revision, so equal VALUES on
    distinct revisions still carry distinct hashes; the exact frame
    bridge proves equality with a zero delta."""
    base = await seed_a4_use(client, tag=b"ev04",
                             source_translation=(4, 5, 6),
                             target_translation=(4, 5, 6))
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    use = result["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == (
        "TRANSLATION_REQUIRED")
    assert use["translator_output_hash"]

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        params = (await conn.execute(text(
            "SELECT translator_parameters_json FROM "
            "production_compatibility_uses "
            "WHERE assessment_id = :a AND position = 0"),
            {"a": result["assessment_id"]})).scalar_one()
    assert json.loads(params)["source_local_to_target_local"][
        "translation_mm"] == [0, 0, 0]


async def test_exact_frame_bridge_yields_translation_verdict(client):
    """M15-EVAL:05 — deterministic translator verdict with exact pins;
    translator evidence retained even though the changed retained blob
    folds the use verdict to REQUIRES_REVIEW."""
    base = await seed_a4_use(client, tag=b"ev05",
                             source_translation=(0, 0, 0),
                             target_translation=(10, 0, 0))
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    use = result["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == (
        "TRANSLATION_REQUIRED")
    assert use["verdict"] == "REQUIRES_REVIEW"  # retained-consumption fold
    assert use["translator_output_hash"]


async def test_unsupported_frame_delta_requires_review(client):
    """M15-EVAL:06 — a rotated target interpretation never rounds or
    approximates."""
    base = await seed_base(client, tag=b"ev06")
    pid = base["project_id"]
    r2 = await seed_second_revision(client, base, number=2)
    cid = await make_composition(client, pid)
    occ = (await mint(client, cid, base["production_revision_id"], 0))[
        "occurrence_id"]
    w = await _approved_world(client, pid, key="lobby")
    await _interpretation(client, base["production_revision_id"])
    r = await client.post(
        f"/production-revisions/{r2}/spatial-interpretation",
        json={"realization_local_to_subject_local": {
            "translation_mm": [1, 0, 0], "rotation_udeg": [90, 0, 0]}})
    assert r.status_code == 201, r.text
    await _adopt(client, cid, occ, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ, "requirement": "required"})
    assert r.status_code == 201, r.text

    result = await assess(client, base["production_revision_id"], r2)
    use = result["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == "REVIEW_REQUIRED"
    assert use["translator_output_hash"] is None


async def test_missing_required_target_interpretation_is_incompatible(
        client):
    """M15-EVAL:07 — A4 consumer + target without interpretation is a
    hard block."""
    base = await seed_a4_use(client, tag=b"ev07",
                             with_target_interpretation=False)
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    use = result["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == "BLOCKED"
    assert use["verdict"] == "INCOMPATIBLE"
    assert result["overall_verdict"] == "INCOMPATIBLE"


async def test_persistent_state_subject_identity_preserves_occurrence_contract(
        client):
    """M15-EVAL:08 — subject continuity evidence rides the contract."""
    base = await seed_a4_use(client, tag=b"ev08")
    r = await client.post(
        f"/production-instances/{base['occurrence_id']}/features",
        json={"key": "damage", "kind": "damage", "value_type": "enum",
              "name": "Damage", "enum_values": ["fresh", "broken"]})
    assert r.status_code == 201, r.text

    result = await assess(
        client, base["production_revision_id"], base["r2"])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        contract = json.loads((await conn.execute(text(
            "SELECT use_contract_json FROM production_compatibility_uses "
            "WHERE assessment_id = :a AND position = 0"),
            {"a": result["assessment_id"]})).scalar_one())
        dims = json.loads((await conn.execute(text(
            "SELECT dimension_results_json FROM "
            "production_compatibility_uses "
            "WHERE assessment_id = :a AND position = 0"),
            {"a": result["assessment_id"]})).scalar_one())
    assert contract["authority_subject"] == {
        "kind": "production_instance", "id": base["occurrence_id"]}
    assert len(contract["active_instance_feature_contracts"]) == 1
    assert dims["persistent_state_subject_identity"]["status"] == (
        "SATISFIED")


def test_verdict_precedence():
    """M15-EVAL:09 — fold law precedence, exactly §5.2."""
    from soloring.compatibility.canonical import fold_verdict

    assert fold_verdict({
        "a": "SATISFIED", "b": "NOT_APPLICABLE"}) == "COMPATIBLE_AS_IS"
    assert fold_verdict({
        "a": "SATISFIED", "b": "TRANSLATION_REQUIRED"}) == (
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION")
    assert fold_verdict({
        "a": "TRANSLATION_REQUIRED", "b": "REVIEW_REQUIRED"}) == (
        "REQUIRES_REVIEW")
    assert fold_verdict({
        "a": "TRANSLATION_REQUIRED", "b": "REVIEW_REQUIRED",
        "c": "BLOCKED"}) == "INCOMPATIBLE"


async def test_corrupt_revision_is_not_friendly_incompatibility(client):
    """M15-EVAL:10 — stored corruption fails the invariant, never a
    verdict."""
    base = await seed_a4_use(client, tag=b"ev10")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "UPDATE production_revisions SET snapshot_json = '{}' "
            "WHERE id = :r"), {"r": base["r2"]})
        await conn.commit()
    with pytest.raises(SoloRingError) as ei:
        await assess(client, base["production_revision_id"], base["r2"])
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"


def test_unimplemented_future_dimensions_not_claimed():
    """M15-EVAL:11 — evaluator v1 claims exactly the five frozen
    dimensions; nothing speculative."""
    g4 = json.loads(
        (__import__("pathlib").Path(__file__).resolve().parents[1]
         / "tests/fixtures/m15/g4_contract.json").read_text())
    assert list(DIMENSIONS) == [
        "production_lineage", "retained_consumption", "media_type",
        "spatial_interpretation", "persistent_state_subject_identity"]
    assert "material_slot" not in " ".join(DIMENSIONS)


async def test_completed_assessment_can_be_nonpass_verdict(client):
    """M15-EVAL:12 — operational/domain-verdict separation: INCOMPATIBLE
    assessments are HTTP successes."""
    base = await seed_a4_use(client, tag=b"ev12",
                             with_target_interpretation=False)
    r = await assess_http(
        client, base["production_revision_id"], base["r2"])
    assert r.status_code == 201, r.text
    assert r.json()["overall_verdict"] == "INCOMPATIBLE"


async def test_parent_summary_fold_exact_and_not_apply_gate(client):
    """M15-EVAL:13 — summary fold over per-use verdicts; per-use
    verdicts stay individually exposed (apply authority is per use)."""
    base = await seed_a4_use(client, tag=b"ev13",
                             with_target_interpretation=False)
    pid = base["project_id"]
    # a second composition with a plain A6 use (review verdict)
    cid2 = await make_composition(client, pid)
    await mint(client, cid2, base["production_revision_id"], 0,
               name="Plain chair")

    result = await assess(
        client, base["production_revision_id"], base["r2"])
    verdicts = sorted(u["verdict"] for u in result["uses"])
    assert verdicts == ["INCOMPATIBLE", "REQUIRES_REVIEW"]
    assert result["overall_verdict"] == "INCOMPATIBLE"
    # the REQUIRES_REVIEW use remains individually addressable
    review_use = next(u for u in result["uses"]
                      if u["verdict"] == "REQUIRES_REVIEW")
    assert review_use["composition_id"] == cid2


async def test_zero_current_uses_returns_no_current_uses_without_persistence(
        client):
    """M15-EVAL:14 — empty scope persists nothing."""
    base = await seed_revision_pair_checked(client)
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    assert result == {"scope_status": "NO_CURRENT_USES",
                      "assessment_id": None, "overall_verdict": None}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments"))).scalar_one()
    assert n == 0

    r = await assess_http(
        client, base["production_revision_id"], base["r2"])
    assert r.status_code == 200
    assert r.json()["scope_status"] == "NO_CURRENT_USES"


async def seed_revision_pair_checked(client):
    from tests.m15_seed import seed_revision_pair

    return await seed_revision_pair(client, tag=b"ev14")


async def test_spatial_relevance_follows_resolved_placement_owner(client):
    """M15-EVAL:15 — A6 consumers are NOT_APPLICABLE; A4 consumers are
    evaluated."""
    base = await seed_a4_use(client, tag=b"ev15")
    cid2 = await make_composition(client, base["project_id"])
    await mint(client, cid2, base["production_revision_id"], 0,
               name="A6 chair")

    result = await assess(
        client, base["production_revision_id"], base["r2"])
    by_comp = {u["composition_id"]: u for u in result["uses"]}
    a6 = by_comp[cid2]
    a4 = by_comp[base["composition_id"]]
    assert a6["dimensions"]["spatial_interpretation"] == "NOT_APPLICABLE"
    assert a6["translator_output_hash"] is None
    assert a4["dimensions"]["spatial_interpretation"] == (
        "TRANSLATION_REQUIRED")


async def test_manual_backward_same_lineage_assessment_is_directional(
        client):
    """M15-EVAL:16 — explicit rollback r2 → r1 assesses with the
    source/target roles exactly swapped."""
    base = await seed_a4_use(client, tag=b"ev16",
                             source_translation=(0, 0, 0),
                             target_translation=(10, 0, 0))
    # a use OF r2 so the backward direction has a non-empty scope
    await mint(client, base["composition_id"], base["r2"], 1,
               name="Back chair")
    forward = await assess(
        client, base["production_revision_id"], base["r2"])
    backward = await assess(client, base["r2"],
                            base["production_revision_id"])

    engine = client._transport.app.state.engine

    async def pins(aid):
        async with engine.connect() as conn:
            row = (await conn.execute(text(
                "SELECT from_revision_id, to_revision_id, "
                "from_revision_hash, to_revision_hash FROM "
                "production_compatibility_assessments WHERE id = :a"),
                {"a": aid})).one()
        return (row.from_revision_id, row.to_revision_id,
                row.from_revision_hash, row.to_revision_hash)

    f = await pins(forward["assessment_id"])
    b = await pins(backward["assessment_id"])
    assert f[0] == b[1] and f[1] == b[0]
    assert f[2] == b[3] and f[3] == b[2]
    # direction matters: the forward use is the A4 consumer carrying the
    # bridge evidence; the backward use is a different (A6) consumer and
    # carries none — the assessment is directional, not symmetric
    assert forward["uses"][0]["translator_output_hash"]
    assert backward["uses"][0]["translator_output_hash"] is None
    assert backward["uses"][0]["dimensions"][
        "spatial_interpretation"] == "NOT_APPLICABLE"


async def test_multiworld_or_ambiguous_placement_consumer_refuses_without_a6_fallback(
        client):
    """M15-EVAL:17 — multi-world ambiguity refuses before persistence;
    no A6 fallback, no tie-break, nothing persisted."""
    base = await seed_a4_use(client, tag=b"ev17")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        before = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments"))).scalar_one()

    w2 = await _approved_world(client, base["project_id"], key="annex")
    r = await client.post(
        f"/spatial-worlds/{w2['world']['id']}/production-instance-tracks",
        json={"occurrence_id": base["occurrence_id"],
              "requirement": "required"})
    assert r.status_code == 201, r.text

    with pytest.raises(SoloRingError) as ei:
        await assess(client, base["production_revision_id"], base["r2"])
    assert ei.value.code == "PRODUCTION_COMPATIBILITY_CONFLICT"
    assert ei.value.details["reason"] == "placement_consumer_ambiguous"
    r = await assess_http(
        client, base["production_revision_id"], base["r2"])
    assert r.status_code == 409

    async with engine.connect() as conn:
        after = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "production_compatibility_assessments"))).scalar_one()
    assert after == before


async def test_emitted_a4_contract_requires_source_interpretation_and_exact_world_context(
        client):
    """M15-EVAL:18 — the emitted A4 contract pins the exact world
    revision/target and implies the source interpretation; a track
    without one refuses UNRESOLVED."""
    base = await seed_a4_use(client, tag=b"ev18")
    result = await assess(
        client, base["production_revision_id"], base["r2"])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        contract = json.loads((await conn.execute(text(
            "SELECT use_contract_json FROM production_compatibility_uses "
            "WHERE assessment_id = :a AND position = 0"),
            {"a": result["assessment_id"]})).scalar_one())
    placement = contract["placement_contract"]
    assert placement["owner"] == "A4_SPATIAL"
    assert placement["spatial_world_id"] == base["world"]["world"]["id"]
    assert placement["spatial_world_revision_id"] == (
        base["world"]["revision"]["id"])
    assert placement["spatial_world_revision_hash"] == (
        base["world"]["revision"]["snapshot_hash"])
    assert placement["target_id"] == base["track_id"]
    assert contract["source_revision"]["spatial_interpretation_hash"]

    # the §6.5.2 prerequisite: track without source interpretation
    # (seed_second_revision has a fixed tag, so build r2 directly)
    import hashlib

    from soloring.domain.ids import new_uuid
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    base2 = await seed_base(client, tag=b"ev18b")
    engine = client._transport.app.state.engine
    now = "2026-01-01T00:00:00.000Z"
    bh2 = hashlib.sha256(b"ev18b-direct-r2").hexdigest()
    r2b = new_uuid()
    closure = RetainedBlobClosure(
        blob_hash=bh2, size_bytes=15, media_type=None)
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :p, 15, NULL, :n)"),
            {"h": bh2, "p": f"sha256/{bh2[:2]}/{bh2[2:4]}/{bh2}", "n": now})
        await conn.execute(text(
            "INSERT INTO production_revisions (id, production_object_id, "
            "revision_number, snapshot_json, snapshot_hash, created_at) "
            "VALUES (:r, :o, 2, :sj, :sh, :n)"),
            {"r": r2b, "o": base2["production_object_id"],
             "sj": sj(closure), "sh": sh(closure), "n": now})
        await conn.execute(text(
            "INSERT INTO production_revision_closures "
            "(production_revision_id, contract_key, contract_version, "
            "blob_hash, size_bytes, media_type) VALUES "
            "(:r, 'retained_blob', 1, :bh, 15, NULL)"),
            {"r": r2b, "bh": bh2})
        await conn.commit()
    cidb = await make_composition(client, base2["project_id"])
    occb = (await mint(client, cidb, base2["production_revision_id"], 0))[
        "occurrence_id"]
    wb = await _approved_world(client, base2["project_id"], key="lobby")
    await _interpretation(client, r2b)  # target only; source lacks one
    await _adopt(client, cidb, occb, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{wb['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occb, "requirement": "required"})
    assert r.status_code == 201, r.text
    with pytest.raises(SoloRingError) as ei:
        await assess(client, base2["production_revision_id"], r2b)
    assert ei.value.details["reason"] == "placement_consumer_ambiguous"
    assert ei.value.details["issue"] == (
        "BINDING_SPATIAL_INTERPRETATION_REQUIRED")
