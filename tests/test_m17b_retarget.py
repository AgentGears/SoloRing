"""M17B retarget/review/assessment matrix (frozen proof-map owners
G01–G20)."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from tests.m17b_seed import (SMILE, candidate_body, channel, kf,
                             seed_production_object,
                             seed_production_revision)


async def _world(client, tag: bytes = b"g-world"):
    from tests.m17b_seed import make_entity, make_project
    pid = await make_project(client, name=f"G {tag!r}")
    eid = await make_entity(client, pid)
    r = await client.post(
        f"/creative-entities/{eid}/performance-candidates",
        json=candidate_body([channel(SMILE, [kf(0, 1, 0)])]))
    assert r.status_code == 201, r.text
    rev = (await client.post(
        f"/performance-candidates/{r.json()['id']}/adopt",
        json={"adopted_by": "director"})).json()
    obj = await seed_production_object(client, pid, "G obj", tag)
    pr1 = await seed_production_revision(
        client, obj, tag + b"-r1", 1)
    pr2 = await seed_production_revision(
        client, obj, tag + b"-r2", 2)
    objx = await seed_production_object(client, pid, "G objX",
                                        tag + b"-x")
    prx = await seed_production_revision(
        client, objx, tag + b"-rx", 1)
    return pid, eid, rev, pr1, pr2, prx


def _assess(client, rev_id, from_id, to_id):
    return client.post(
        f"/performance-revisions/{rev_id}/retarget-assessments",
        json={"from_production_revision_id": from_id,
              "to_production_revision_id": to_id})


@pytest.mark.asyncio
async def test_g01_same_exact_physical_revision_to_compatible_as_is(client):
    _, _, rev, pr1, _, _ = await _world(client)
    r = await _assess(client, rev["id"], pr1["production_revision_id"],
                      pr1["production_revision_id"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["overall_verdict"] == "COMPATIBLE_AS_IS"
    assert a["physical_revision_compatibility_only"] is True
    assert a["subject_binding_assessed"] is False
    assert a["executor_qualification_assessed"] is False


@pytest.mark.asyncio
async def test_g02_same_productionobject_different_revision_to_requires_review(client):
    _, _, rev, pr1, pr2, _ = await _world(client)
    r = await _assess(client, rev["id"], pr1["production_revision_id"],
                      pr2["production_revision_id"])
    assert r.status_code == 201, r.text
    assert r.json()["overall_verdict"] == "REQUIRES_REVIEW"


@pytest.mark.asyncio
async def test_g03_different_productionobject_to_incompatible(client):
    _, _, rev, pr1, _, prx = await _world(client)
    r = await _assess(client, rev["id"], pr1["production_revision_id"],
                      prx["production_revision_id"])
    assert r.status_code == 201, r.text
    assert r.json()["overall_verdict"] == "INCOMPATIBLE"


@pytest.mark.asyncio
async def test_g04_evaluator_v1_never_emits_compatible_via_deterministic_translation(client):
    _, _, rev, pr1, pr2, prx = await _world(client)
    for f, t in ((pr1, pr1), (pr1, pr2), (pr1, prx), (pr2, prx)):
        r = await _assess(client, rev["id"],
                          f["production_revision_id"],
                          t["production_revision_id"])
        assert r.json()["overall_verdict"] != \
            "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION"
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "performance_retarget_assessments WHERE overall_verdict = "
            "'COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION'"))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_g05_requires_review_without_explicit_accepted_review_cannot_create_retarget_candid(client):
    _, _, rev, pr1, pr2, _ = await _world(client, b"g05")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    r = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id":
                  "55555555-5555-4555-8555-555555555555",
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 404
    assert r.json()["error_code"] == "RETARGET_REVIEW_NOT_FOUND"


async def _reviewed_assessment(client, tag: bytes = b"g-rev"):
    _, _, rev, pr1, pr2, _ = await _world(client, tag)
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    review = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "rev", "rationale": None})).json()
    return rev, pr1, pr2, a, review


@pytest.mark.asyncio
async def test_g06_exact_accept_for_new_candidate_review_for_the_same_assessment_permits_retarget(client):
    rev, pr1, pr2, a, review = await _reviewed_assessment(client,
                                                          b"g06")
    r = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": review["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_g07_reject_review_does_not_permit_retarget_candidate(client):
    _, _, rev, pr1, pr2, _ = await _world(client, b"g07")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    review = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "REJECT",
              "reviewed_by": "rev"})).json()
    r = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": review["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 422
    assert r.json()["error_code"] == "RETARGET_REVIEW_REJECTED"


@pytest.mark.asyncio
async def test_g08_incompatible_assessment_blocks_retarget_candidate(client):
    _, _, rev, pr1, _, prx = await _world(client, b"g08")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       prx["production_revision_id"])).json()
    assert a["overall_verdict"] == "INCOMPATIBLE"
    r = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id":
                  "55555555-5555-4555-8555-555555555555",
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 422
    assert r.json()["error_code"] == "RETARGET_INCOMPATIBLE"


@pytest.mark.asyncio
async def test_g09_retarget_assessment_provenance_coordinate_mismatch_rejects(client):
    rev, pr1, pr2, a, review = await _reviewed_assessment(client,
                                                          b"g09")
    _, _, rev2, q1, q2, _ = await _world(client, b"g09b")
    a2 = (await _assess(client, rev2["id"],
                        q1["production_revision_id"],
                        q2["production_revision_id"])).json()
    r = await client.post(
        f"/performance-revisions/{rev2['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": review["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 422
    assert r.json()["error_code"] in (
        "RETARGET_ASSESSMENT_COORDINATE_MISMATCH",
        "RETARGET_REVIEW_ASSESSMENT_MISMATCH")


@pytest.mark.asyncio
async def test_g10_retarget_candidate_adoption_leaves_source_performancerevision_unchanged(client):
    rev, pr1, pr2, a, review = await _reviewed_assessment(client,
                                                          b"g10")
    before = (await client.get(
        f"/performance-revisions/{rev['id']}")).json()
    c = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": review["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
        ).json()
    f2 = (await client.post(f"/performance-candidates/{c['id']}/"
                            "adopt",
                            json={"adopted_by": "d"})).json()
    after = (await client.get(
        f"/performance-revisions/{rev['id']}")).json()
    assert after == before
    assert f2["canonical_channel_payload_sha256"] == \
        before["canonical_channel_payload_sha256"]
    assert f2["id"] != before["id"]


@pytest.mark.asyncio
async def test_g11_assessment_stores_exact_from_to_productionrevision_snapshot_hashes(client):
    _, _, rev, pr1, pr2, _ = await _world(client, b"g11")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    assert a["from_production_revision_hash"] == \
        pr1["snapshot_hash"]
    assert a["to_production_revision_hash"] == pr2["snapshot_hash"]


@pytest.mark.asyncio
async def test_g12_retarget_verdict_does_not_claim_subject_binding_rig_support_or_executor_qualif(client):
    _, _, rev, pr1, pr1b, _ = await _world(client, b"g12")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr1["production_revision_id"])).json()
    assert a["physical_revision_compatibility_only"] is True
    assert a["subject_binding_assessed"] is False
    assert a["executor_qualification_assessed"] is False


@pytest.mark.asyncio
async def test_g13_scope_json_exact_key_grammar_enforced(client):
    from soloring.performance.retarget import _SCOPE_KEYS
    _, _, rev, pr1, pr2, _ = await _world(client, b"g13")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        scope = (await conn.execute(text(
            "SELECT scope_json FROM "
            "performance_retarget_assessments WHERE id = :i"),
            {"i": a["id"]})).scalar()
    assert tuple(sorted(json.loads(scope))) == tuple(
        sorted(_SCOPE_KEYS))


@pytest.mark.asyncio
async def test_g14_report_json_exact_key_grammar_enforced(client):
    from soloring.performance.retarget import _REPORT_KEYS
    _, _, rev, pr1, pr2, _ = await _world(client, b"g14")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        report = (await conn.execute(text(
            "SELECT report_json FROM "
            "performance_retarget_assessments WHERE id = :i"),
            {"i": a["id"]})).scalar()
    assert tuple(sorted(json.loads(report))) == tuple(
        sorted(_REPORT_KEYS))


@pytest.mark.asyncio
async def test_g15_scope_report_hashes_recompute_byte_exact_from_immutable_referenced_rows(client):
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    _, _, rev, pr1, pr2, _ = await _world(client, b"g15")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT scope_json, scope_hash, report_json, report_hash "
            "FROM performance_retarget_assessments WHERE id = :i"),
            {"i": a["id"]})).one()
    assert canonical_hash(json.loads(row[0])) == row[1]
    assert canonical_json_str(
        json.loads(row[0])) == row[0]
    assert canonical_hash(json.loads(row[2])) == row[3]
    report = json.loads(row[2])
    assert report["scope_hash"] == row[1]


@pytest.mark.asyncio
async def test_g16_accepted_review_belonging_to_another_assessment_rejects(client):
    rev1, _, _, a1, review1 = await _reviewed_assessment(client,
                                                          b"g16a")
    _, _, rev2, q1, q2, _ = await _world(client, b"g16b")
    a2 = (await _assess(client, rev2["id"],
                        q1["production_revision_id"],
                        q2["production_revision_id"])).json()
    r = await client.post(
        f"/performance-revisions/{rev2['id']}/retarget-candidates",
        json={"assessment_id": a2["id"],
              "accepted_review_id": review1["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 422
    assert r.json()["error_code"] == \
        "RETARGET_REVIEW_ASSESSMENT_MISMATCH"


@pytest.mark.asyncio
async def test_g17_compatible_as_is_assessment_is_valid_evidence_but_retarget_candidate_creation(client):
    _, _, rev, pr1, _, _ = await _world(client, b"g17")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr1["production_revision_id"])).json()
    assert a["overall_verdict"] == "COMPATIBLE_AS_IS"
    r = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id":
                  "55555555-5555-4555-8555-555555555555",
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert r.status_code == 422
    assert r.json()["error_code"] == "RETARGET_NOT_REQUIRED"


@pytest.mark.asyncio
async def test_g18_retarget_candidate_inherits_source_project_subject_kind_profile_domain_channel(client):
    rev, pr1, pr2, a, review = await _reviewed_assessment(client,
                                                          b"g18")
    c = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": review["id"],
              "producer_id": "p", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
        ).json()
    for f in ("project_id", "subject_id", "performance_kind",
              "performance_profile_id",
              "canonical_channel_payload_sha256",
              "canonical_channel_payload_blob_hash",
              "payload_schema_version"):
        assert c[f] == rev[f], f
    assert c["temporal_start_ms"] == rev["temporal_start_ms"]
    assert c["temporal_end_ms"] == rev["temporal_end_ms"]
    assert c["source_kind"] == "retargeted"
    assert c["provenance_hash"] != rev["provenance_hash"]


@pytest.mark.asyncio
async def test_g19_identical_retarget_assessment_creation_converges_sequentially_and_concurrently(client):
    _, _, rev, pr1, pr2, _ = await _world(client, b"g19")
    args = (rev["id"], pr1["production_revision_id"],
            pr2["production_revision_id"])
    r1 = await _assess(client, *args)
    r2 = await _assess(client, *args)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["report_hash"] == r2.json()["report_hash"]
    ra, rb = await asyncio.gather(_assess(client, *args),
                                  _assess(client, *args))
    ids = {ra.json().get("id"), rb.json().get("id")}
    assert ids == {r1.json()["id"]}
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "performance_retarget_assessments WHERE "
            "performance_revision_id = :r"),
            {"r": rev["id"]})).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_g20_report_scope_hash_binding_rejects_cross_scope_report_mixing_or_same_coordinate(client):
    from soloring.performance.retarget import _assert_deterministic
    from soloring.errors import SoloRingError
    from soloring.performance.models import (
        PerformanceRetargetAssessment)
    from sqlalchemy.ext.asyncio import async_sessionmaker
    _, _, rev, pr1, pr2, _ = await _world(client, b"g20")
    a = (await _assess(client, rev["id"],
                       pr1["production_revision_id"],
                       pr2["production_revision_id"])).json()
    engine = client._transport.app.state.engine
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as sess:
        row = await sess.get(PerformanceRetargetAssessment, a["id"])
        tampered_report = row.report_json.replace(
            "REQUIRES_REVIEW", "INCOMPATIBLE")
        with pytest.raises(SoloRingError):
            _assert_deterministic(row, tampered_report,
                                  row.report_hash, "INCOMPATIBLE")
        # same coordinate, different verdict -> invariant failure
        with pytest.raises(SoloRingError):
            _assert_deterministic(row, row.report_json,
                                  row.report_hash, "INCOMPATIBLE")
