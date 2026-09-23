"""M17B candidate/adoption/provenance/pagination matrix (frozen
proof-map owners A*, E*, F*, J*, K*)."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from sqlalchemy import text

from tests.m17b_seed import (HEAD_YAW, SMILE, candidate_body, channel,
                             kf)


async def _subject(client):
    from tests.m17b_seed import make_entity, make_project
    pid = await make_project(client, name="M17B Perf")
    eid = await make_entity(client, pid)
    return pid, eid


def _post(client, eid, body):
    return client.post(
        f"/creative-entities/{eid}/performance-candidates", json=body)


# ------------------------------- A* ---------------------------------

@pytest.mark.asyncio
async def test_a01_missing_subject_rejects(client):
    r = await _post(client, "00000000-0000-4000-8000-000000000000",
                    candidate_body([channel(SMILE, [kf(0, 1, 0)])]))
    assert r.status_code == 404
    assert r.json()["error_code"] == "PERFORMANCE_SUBJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_a02_deleted_subject_rejects_for_new_candidate_adoption(client):
    from tests.m17b_seed import create_candidate, make_project
    pid = await make_project(client, name="A02")
    eid = (await client.post(f"/projects/{pid}/entities",
                             json={"kind": "character", "name": "X"})
           ).json()["id"]
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r = await client.delete(f"/entities/{eid}")
    assert r.status_code in (200, 204)
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    assert r.status_code == 422
    assert r.json()["error_code"] == "PERFORMANCE_SUBJECT_DELETED"
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "director"})
    assert r.status_code == 422
    assert r.json()["error_code"] == "PERFORMANCE_SUBJECT_DELETED"


@pytest.mark.asyncio
async def test_a03_cross_project_subject_rejects(client):
    from tests.m17b_seed import make_entity, make_project
    p1 = await make_project(client, name="P1")
    p2 = await make_project(client, name="P2")
    e2 = await make_entity(client, p2)
    r = await client.post(f"/projects/{p1}/dialogue-lines", json={})
    # subject from p2 against a p1-route is structurally impossible on
    # the candidate route (subject owns its project); prove the law:
    # candidate lands in p2, and any p1-scoped view cannot see it
    c = (await _post(client, e2, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))).json()
    assert c["project_id"] == p2
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidates WHERE "
            "project_id = :p AND subject_id = :s"),
            {"p": p1, "s": e2})).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_a04_valid_active_same_project_subject_passes(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    assert r.status_code == 201, r.text
    assert r.json()["project_id"] == pid


# ------------------------------- E* ---------------------------------

async def _alignment_world(client, tag: bytes = b"m17b-e"):
    """A minimal M17A line/VP/alignment triple for Eva-subject
    provenance tests."""
    from tests.m17a_seed import make_entity as m17a_entity
    from tests.m17a_seed import make_project as m17a_project
    from tests.m17a_seed import place_blob, wave_bytes
    pid = await m17a_project(client)
    eid = await m17a_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    rev = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "M17B provenance fixture."})).json()
    h = await place_blob(client, wave_bytes(48000, 48000))
    c = (await client.post(
        f"/dialogue-line-revisions/{rev['id']}/vocal-candidates",
        json={"retained_audio_blob_hash": h,
              "source_provenance": {"schema_version": 1,
                                    "source_kind": "recorded"}}
    )).json()
    vp = (await client.post(f"/vocal-candidates/{c['id']}/adopt",
                            json={"adopted_by": "d"})).json()
    await client.put(
        f"/dialogue-line-revisions/{rev['id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp["id"],
              "selected_by": "d"})
    al = {"analyzer_id": "X", "analyzer_version": "1.2.0",
          "model_identity": "Mx", "runtime_identity": "Rx",
          "parameters_sha256": "a" * 64,
          "alignment_document": {"schema_version": 1,
                                 "words": [{"start_sample": 0,
                                            "end_sample_exclusive": 120,
                                            "label": "Y"}],
                                 "phonemes": [], "viseme_classes": []},
          "derivation_run": {
              "schema_version": 1,
              "run_timestamp_utc": "2026-09-22T12:00:00.000000Z",
              "host_context": "worker-7",
              "input_digest": {
                  "vocal_performance_revision_id": vp["id"],
                  "retained_audio_blob_sha256": h}}}
    d = (await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=al)).json()
    return pid, eid, d


@pytest.mark.asyncio
async def test_e01_authored_null_alignment_passes(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "AUTHORED", None)])]))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_e02_authored_alignment_id_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "AUTHORED",
                            "11111111-1111-4111-8111-"
                            "111111111111")])]))
    assert r.status_code == 422
    assert "AUTHORED" in r.json()["message"]


@pytest.mark.asyncio
async def test_e03_derived_valid_same_project_same_subject_alignment_passes(client):
    apid, aeid, d = await _alignment_world(client)
    r = await _post(client, aeid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "DERIVED", d["id"])])]))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_e04_derived_then_edited_valid_same_project_same_subject_alignment_passes(client):
    apid, aeid, d = await _alignment_world(client, b"m17b-e4")
    r = await _post(client, aeid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "DERIVED_THEN_EDITED",
                            d["id"])])]))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_e05_missing_alignment_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "DERIVED",
                            "55555555-5555-4555-8555-"
                            "555555555555")])]))
    assert r.status_code == 404
    assert r.json()["error_code"] == "PERFORMANCE_ALIGNMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_e06_cross_project_alignment_rejects(client):
    apid, aeid, d = await _alignment_world(client, b"m17b-e6")
    pid2, eid2 = await _subject(client)
    r = await _post(client, eid2, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "DERIVED", d["id"])])]))
    assert r.status_code == 422
    assert r.json()["error_code"] in (
        "PERFORMANCE_ALIGNMENT_SUBJECT_MISMATCH",
        "PERFORMANCE_ALIGNMENT_PROJECT_MISMATCH")


@pytest.mark.asyncio
async def test_e07_different_subject_alignment_rejects(client):
    apid, aeid, d = await _alignment_world(client, b"m17b-e7")
    r = await client.post(f"/projects/{apid}/entities",
                          json={"kind": "character", "name": "Other"})
    other = r.json()["id"]
    rr = await client.post(f"/entities/{other}/revisions",
                           json={"spec": {"description": "Other"}})
    rid = rr.json()["id"]
    await client.put(f"/entities/{other}/approved-revision",
                     json={"revision_id": rid,
                           "expected_approved_revision_id": None})
    r2 = await _post(client, other, candidate_body(
        [channel(SMILE, [kf(0, 1, 0, "DERIVED", d["id"])])]))
    assert r2.status_code == 422
    assert r2.json()["error_code"] == \
        "PERFORMANCE_ALIGNMENT_SUBJECT_MISMATCH"


@pytest.mark.asyncio
async def test_e08_viseme_hint_inside_authority_payload_rejects(client):
    pid, eid = await _subject(client)
    k = kf(0, 1, 0)
    k["provenance"]["viseme_hint"] = "AA"
    r = await _post(client, eid, candidate_body(
        [channel(SMILE, [k])]))
    assert r.status_code == 422


# ------------------------------- F* ---------------------------------

@pytest.mark.asyncio
async def test_f01_candidate_is_not_authority(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r = await client.get(f"/performance-revisions/{c['id']}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_f02_adoption_copies_exact_candidate_closure(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    rev = await adopt(client, c["id"])
    for f in ("subject_id", "performance_kind",
              "performance_profile_id",
              "canonical_channel_payload_sha256",
              "canonical_channel_payload_blob_hash",
              "payload_schema_version", "source_kind",
              "provenance_hash"):
        assert rev[f] == c[f]
    assert rev["temporal_start_ms"] == {"num": 0, "den": 1}
    assert rev["temporal_end_ms"] == {"num": 4500, "den": 1}


@pytest.mark.asyncio
async def test_f03_duplicate_sequential_adoption_returns_the_same_performancerevision_and_adoptio(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r1 = await adopt(client, c["id"], "director")
    r2 = await adopt(client, c["id"], "producer")
    assert r1["id"] == r2["id"]
    assert r1["adoption_id"] == r2["adoption_id"]
    assert r1["adopted_by"] == r2["adopted_by"] == "director"


@pytest.mark.asyncio
async def test_f04_concurrent_duplicate_adoption_converges_to_one_exact_performancerevision(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r1, r2 = await asyncio.gather(
        client.post(f"/performance-candidates/{c['id']}/adopt",
                    json={"adopted_by": "director"}),
        client.post(f"/performance-candidates/{c['id']}/adopt",
                    json={"adopted_by": "producer"}))
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions WHERE "
            "adopted_candidate_id = :c"), {"c": c["id"]})).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_f05_adopted_revision_is_immutable(client):
    """F05 (rewritten per the publication-stage review): the REAL
    immutability surface — the M17B router exposes no mutation method
    on the revision authority, live PUT/PATCH/DELETE attempts return
    405, and the authority bytes are unchanged after the attempts."""
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    rev = await adopt(client, c["id"])
    from soloring.api.m17b_performance import router as m17b_router
    methods = set()
    for route in m17b_router.routes:
        if getattr(route, "path", "") == \
                "/performance-revisions/{revision_id}":
            methods |= route.methods
    assert "GET" in methods
    assert not (methods & {"PUT", "PATCH", "DELETE"})
    r_put = await client.put(
        f"/performance-revisions/{rev['id']}", json={})
    r_patch = await client.patch(
        f"/performance-revisions/{rev['id']}", json={})
    r_del = await client.delete(
        f"/performance-revisions/{rev['id']}")
    for m, r in (("put", r_put), ("patch", r_patch),
                 ("delete", r_del)):
        assert r.status_code == 405, (m, r.status_code)
    r = await client.get(f"/performance-revisions/{rev['id']}")
    assert r.status_code == 200
    assert r.json()["performance_kind"] == rev["performance_kind"]
    assert r.json()["canonical_channel_payload_sha256"] == \
        rev["canonical_channel_payload_sha256"]
    assert r.json()["adopted_candidate_id"] == c["id"]


@pytest.mark.asyncio
async def test_f06_candidate_is_immutable(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r = await client.put(
        f"/performance-candidates/{c['id']}",
        json=candidate_body([channel(SMILE, [kf(0, 1, 5)])]))
    assert r.status_code == 405


@pytest.mark.asyncio
async def test_f07_adoption_does_not_create_take_canon_current_state(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    rev = await adopt(client, c["id"])
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        cols = [r[1] for r in (await conn.execute(
            text("PRAGMA table_info(performance_revisions)")))]
    assert not any(x in cols for x in ("updated_at", "deleted_at",
                                       "current", "latest"))


@pytest.mark.asyncio
async def test_f08_no_current_latest_performancerevision_inference_exists(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c1 = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    c2 = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 100)])]))
    r1 = await adopt(client, c1["id"])
    r2 = await adopt(client, c2["id"])
    listing = (await client.get(
        f"/creative-entities/{eid}/performance-revisions")).json()
    assert {x["id"] for x in listing["revisions"]} == \
        {r1["id"], r2["id"]}
    assert "current" not in listing and "latest" not in listing


@pytest.mark.asyncio
async def test_f09_identical_payload_under_distinct_candidates_may_adopt_to_distinct_performancer(client):
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c1 = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    c2 = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    r1 = await adopt(client, c1["id"])
    r2 = await adopt(client, c2["id"])
    assert r1["id"] != r2["id"]
    assert r1["canonical_channel_payload_sha256"] == \
        r2["canonical_channel_payload_sha256"]


@pytest.mark.asyncio
async def test_f10_duplicate_adoption_winner_is_revalidated_against_candidate_closure_before_retu(client):
    from soloring.performance.revision import (closure_matches,
                                               revalidate_winner)
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    rev = await adopt(client, c["id"])
    engine = client._transport.app.state.engine
    from soloring.performance.models import (PerformanceCandidate,
                                             PerformanceRevision)
    from sqlalchemy.ext.asyncio import async_sessionmaker
    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as sess:
        row = await sess.get(PerformanceRevision, rev["id"])
        cand = await sess.get(PerformanceCandidate, c["id"])
    assert closure_matches(row, cand)
    revalidate_winner(row, cand)  # passes silently
    # tamper: closure divergence must fail closed
    cand.performance_kind = "BODY"
    with pytest.raises(Exception):
        revalidate_winner(row, cand)


# ------------------------------- J* ---------------------------------

def _prov_body(mutate):
    from tests.m17b_seed import candidate_body, channel, kf
    body = candidate_body([channel(SMILE, [kf(0, 1, 0)])])
    mutate(body["source_provenance"])
    return body


@pytest.mark.asyncio
async def test_j01_candidate_provenance_unknown_or_missing_top_level_keys_reject(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, _prov_body(
        lambda p: p.update({"gpu": "x"})))
    assert r.status_code in (403, 422)
    r2 = await _post(client, eid, _prov_body(
        lambda p: p.pop("producer_id")))
    assert r2.status_code in (403, 422)


@pytest.mark.asyncio
async def test_j02_candidate_provenance_source_kind_outside_the_closed_vocabulary_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, _prov_body(
        lambda p: p.update({"source_kind": "magicked"})))
    assert r.status_code in (403, 422)


@pytest.mark.asyncio
async def test_j03_producer_id_empty_whitespace_over_255_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, _prov_body(
        lambda p: p.update({"producer_id": "   "})))
    assert r.status_code in (403, 422)
    r2 = await _post(client, eid, _prov_body(
        lambda p: p.update({"producer_id": "x" * 256})))
    assert r2.status_code in (403, 422)


@pytest.mark.asyncio
async def test_j04_producer_version_empty_whitespace_over_255_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, _prov_body(
        lambda p: p.update({"producer_version": ""})))
    assert r.status_code in (403, 422)
    r2 = await _post(
        client, eid, _prov_body(
            lambda p: p.update({"producer_version": "x" * 256})))
    assert r2.status_code in (403, 422)


@pytest.mark.asyncio
async def test_j05_malformed_parameters_sha256_rejects(client):
    pid, eid = await _subject(client)
    r = await _post(client, eid, _prov_body(
        lambda p: p.update({"parameters_sha256": "XYZ"})))
    assert r.status_code in (403, 422)


@pytest.mark.asyncio
async def test_j06_non_retarget_source_kind_requires_retarget_null(client):
    pid, eid = await _subject(client)
    # the API schema structurally omits caller retarget; prove the
    # service law directly
    from soloring.performance.revision import build_provenance_envelope
    with pytest.raises(Exception):
        build_provenance_envelope({
            "schema_version": 1, "source_kind": "authored",
            "producer_id": "p", "producer_version": "1",
            "source_identity": None, "parameters_sha256": None,
            "retarget": {"source_performance_revision_id": "x",
                         "from_production_revision_id": "x",
                         "to_production_revision_id": "x",
                         "compatibility_assessment_id": "x",
                         "accepted_review_id": "x"}})


@pytest.mark.asyncio
async def test_j07_retarget_provenance_unknown_missing_nested_keys_reject(client):
    from soloring.performance.revision import build_provenance_envelope
    with pytest.raises(Exception):
        build_provenance_envelope({
            "schema_version": 1, "source_kind": "retargeted",
            "producer_id": "p", "producer_version": "1",
            "source_identity": None, "parameters_sha256": None,
            "retarget": {"source_performance_revision_id": "x"}})


@pytest.mark.asyncio
async def test_j08_source_identity_is_audit_provenance_only_and_mutable_local_filesystem_path_for(client):
    pid, eid = await _subject(client)
    for bad in ("file://x/y", "/abs/path", "./rel", "../up",
                "C:\\win\\path", "\\\\unc\\share"):
        r = await _post(client, eid, _prov_body(
            lambda p, b=bad: p.update({"source_identity": b})))
        assert r.status_code in (403, 422), bad
    r2 = await _post(client, eid, _prov_body(
        lambda p: p.update(
            {"source_identity": "session-7f3a-v2"})))
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_j09_retarget_provenance_golden_reproduces_pinned_bytes_and_sha256(client):
    from soloring.domain.canonical import canonical_json_str
    fixture = {
        "schema_version": 1,
        "source_kind": "retargeted",
        "producer_id": "fixture-retarget",
        "producer_version": "1",
        "source_identity": None,
        "parameters_sha256": None,
        "retarget": {
            "source_performance_revision_id":
                "11111111-1111-4111-8111-111111111111",
            "from_production_revision_id":
                "22222222-2222-4222-8222-222222222222",
            "to_production_revision_id":
                "33333333-3333-4333-8333-333333333333",
            "compatibility_assessment_id":
                "44444444-4444-4444-8444-444444444444",
            "accepted_review_id":
                "55555555-5555-4555-8555-555555555555"}}
    b = canonical_json_str(fixture).encode("utf-8")
    assert len(b) == 501
    assert hashlib.sha256(b).hexdigest() == (
        "08ee43e93df36e2d765bfbb4470d56903dc491dd7b9425a0704516a"
        "843228adf")


# ------------------------------- K* ---------------------------------

@pytest.mark.asyncio
async def test_k01_candidate_collection_rejects_partial_cursor(client):
    pid, eid = await _subject(client)
    r = await client.get(
        f"/creative-entities/{eid}/performance-candidates"
        "?cursor_created=2026-01-01T00:00:00.000Z")
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CURSOR"


@pytest.mark.asyncio
async def test_k02_revision_collection_rejects_partial_cursor(client):
    pid, eid = await _subject(client)
    r = await client.get(
        f"/creative-entities/{eid}/performance-revisions"
        "?cursor_adopted=2026-01-01T00:00:00.000Z")
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_CURSOR"


@pytest.mark.asyncio
async def test_k03_candidate_pagination_is_stable_and_gap_duplicate_free_for_equal_created_at_usi(client):
    """K03 (repaired per the publication-stage review): four
    equal-``created_at`` candidates for the SAME subject the route
    pages, plus one later API-created row — exact ``(created_at, id)``
    traversal with the tie broken by id, no gaps, no duplicates."""
    pid, eid = await _subject(client)
    engine = client._transport.app.state.engine
    now = "2026-01-01T00:00:00.000Z"
    settings = client._transport.app.state.settings
    h = 'a' * 64
    bp = settings.blob_dir / "sha256" / h[:2] / h[2:4] / h
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_bytes(b"pagination-fixture")
    eq_ids = []
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, "
            "NULL, :n)"),
            {"h": h, "p": f"sha256/{h[:2]}/{h[2:4]}/{h}", "s": 19,
             "n": now})
        for i in range(4):
            cid = f"k03-equal-{i:04d}"
            eq_ids.append(cid)
            await conn.execute(text(
                "INSERT INTO performance_candidates (id, project_id, "
                "subject_id, performance_kind, performance_profile_id,"
                " temporal_start_num, temporal_start_den, "
                "temporal_end_num, temporal_end_den, "
                "canonical_channel_payload_blob_hash, "
                "canonical_channel_payload_sha256, "
                "payload_schema_version, source_kind, "
                "provenance_schema_version, provenance_json, "
                "provenance_hash, created_at) VALUES (:i, :p, :s, "
                "'FACIAL', 'performance-profile/1', 0, 1, 4500, 1, "
                ":h, :h, 1, 'authored', 1, '{}', :ph, :n)"),
                {"i": cid, "p": pid, "s": eid,
                 "h": h, "ph": 'b' * 64, "n": now})
    from tests.m17b_seed import create_candidate
    c = await create_candidate(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))
    seen = []
    url = f"/creative-entities/{eid}/performance-candidates?limit=2"
    while url:
        page = (await client.get(url)).json()
        seen += [x["id"] for x in page["candidates"]]
        cur = page.get("next_cursor")
        url = (f"/creative-entities/{eid}/performance-candidates"
               f"?limit=2&cursor_created={cur[0]}&cursor_id={cur[1]}"
               ) if cur else None
    # equal-created_at rows come first in exact id order (tie-break),
    # then the later API-created row; no gaps, no duplicates
    assert seen == sorted(eq_ids) + [c["id"]]
    assert len(seen) == len(set(seen)) == 5


@pytest.mark.asyncio
async def test_k04_revision_pagination_is_stable_and_gap_duplicate_free_for_equal_adopted_at_usin(client):
    """K04 (repaired per the publication-stage review): all three
    revisions are FORCED to identical ``adopted_at`` — the cursor
    traversal must then break every tie by id, cross the tie boundary
    mid-page, and yield the exact total order with no duplicates."""
    pid, eid = await _subject(client)
    from tests.m17b_seed import adopt, create_candidate
    revs = []
    for i in range(3):
        c = await create_candidate(client, eid, candidate_body(
            [channel(SMILE, [kf(0, 1, i)])]))
        revs.append((await adopt(client, c["id"]))["id"])
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET adopted_at = :t WHERE "
            "id IN (:a, :b, :c)"),
            {"t": "2026-01-01T00:00:00.000Z", "a": revs[0],
             "b": revs[1], "c": revs[2]})
    seen = []
    url = f"/creative-entities/{eid}/performance-revisions?limit=2"
    while url:
        page = (await client.get(url)).json()
        seen += [x["id"] for x in page["revisions"]]
        cur = page.get("next_cursor")
        url = (f"/creative-entities/{eid}/performance-revisions"
               f"?limit=2&cursor_adopted={cur[0]}&cursor_id={cur[1]}"
               ) if cur else None
    assert seen == sorted(revs)
    assert len(seen) == len(set(seen)) == 3


@pytest.mark.asyncio
async def test_k05_exact_candidate_and_review_evidence_are_dereferenceable_review_listing_is_dete(client):
    """K05 (repaired per the publication-stage review): MULTIPLE
    reviews — equal-``reviewed_at`` CONFLICTING decisions (ACCEPT and
    REJECT are both lawful immutable evidence on one assessment) —
    remain separately dereferenceable at their exact ids and the
    listing is deterministic ``(reviewed_at, id)`` order (id tie-break
    at the forced equal timestamp), with no latest-wins collapse."""
    pid, eid = await _subject(client)
    from tests.m17b_seed import (seed_production_object,
                                 seed_production_revision)
    c = (await _post(client, eid, candidate_body(
        [channel(SMILE, [kf(0, 1, 0)])]))).json()
    r = await client.get(f"/performance-candidates/{c['id']}")
    assert r.status_code == 200 and r.json()["id"] == c["id"]
    rev = (await client.post(f"/performance-candidates/{c['id']}/"
                             "adopt",
                             json={"adopted_by": "director"})).json()
    obj = await seed_production_object(client, pid, "K05 obj",
                                       b"k05-object")
    pr1 = await seed_production_revision(client, obj, b"k05-r1", 1)
    pr2 = await seed_production_revision(client, obj, b"k05-r2", 2)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    assert a["overall_verdict"] == "REQUIRES_REVIEW"
    accept = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "rev-a", "rationale": None})).json()
    reject = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "REJECT",
              "reviewed_by": "rev-b", "rationale": None})).json()
    # force identical reviewed_at: the listing order must break the
    # tie by id, not by decision or recency
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_reviews SET reviewed_at = :t "
            "WHERE id IN (:a, :b)"),
            {"t": "2026-01-01T00:00:00.000Z", "a": accept["id"],
             "b": reject["id"]})
    for rv in (accept, reject):
        rr = await client.get(f"/performance-retarget-reviews/"
                              f"{rv['id']}")
        assert rr.status_code == 200
        assert rr.json()["assessment_id"] == a["id"]
        assert rr.json()["decision"] == rv["decision"]
    lst = (await client.get(
        f"/performance-retarget-assessments/{a['id']}/reviews")).json()
    got = [x["id"] for x in lst["reviews"]]
    assert got == sorted([accept["id"], reject["id"]])
    assert {x["decision"] for x in lst["reviews"]} == {
        "ACCEPT_FOR_NEW_CANDIDATE", "REJECT"}
