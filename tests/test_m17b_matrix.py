"""M17B correction-round proof battery (correction plan R1 §14).

X1 true first-creation assessment race; X2 poisoned-session
discipline; X3 candidate-integrity corruption before adoption; X4
corrupt-winner replay; X5 adoption lifecycle ordering; X6 HTTP scalar
strictness; X7 frozen create-body grammar; X8 concurrent first
candidate Blob race; X9 recovery grammar corruptions; X10 F05 real
immutability surface; X11 A03 corrected structural ownership;
X12 adoption uses the running app's Settings (publication
review); X13 alignment provenance binds to the candidate's
project; X14-X17 PUB-R3 recovery/API regressions (operation
Blob root; 0019 predecessor semantics; cross-project
assessment law; bounded review keyset); X18-X20 second-Codex
regressions (adoption subject/project agreement; retarget
evidence resolution at adoption; minimal API provenance
defaults); X21-X23 third-Codex regressions (assessment
verdict recomputation; source-revision lineage; VP-speaker
alignment law).
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from sqlalchemy import text

from tests.m17b_seed import (SMILE, candidate_body, channel, kf,
                             seed_production_object,
                             seed_production_revision)


async def _subject(client, name="CR"):
    from tests.m17b_seed import make_entity, make_project
    pid = await make_project(client, name=name)
    eid = await make_entity(client, pid)
    return pid, eid


def _post(client, eid, body):
    return client.post(
        f"/creative-entities/{eid}/performance-candidates", json=body)


def _body(value=None, num=None):
    ch = channel(SMILE, [kf(0, 1, value if value is not None else 0)])
    if num is not None:
        ch["keyframes"][0]["time_ms"]["num"] = num
    return candidate_body([ch])


# --------------------------- X1/X2 ---------------------------------

async def _race_world(client, tag: bytes):
    from tests.m17b_seed import make_entity, make_project
    pid = await make_project(client, name=f"X1 {tag!r}")
    eid = await make_entity(client, pid)
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/"
                             "adopt",
                             json={"adopted_by": "d"})).json()
    obj = await seed_production_object(client, pid, "X1 obj", tag)
    pr1 = await seed_production_revision(client, obj, tag + b"1", 1)
    pr2 = await seed_production_revision(client, obj, tag + b"2", 2)
    return pid, eid, rev, pr1, pr2


@pytest.mark.asyncio
async def test_x1_retarget_true_first_creation_race_converges(client):
    """Two concurrent identical POSTs with ZERO preexisting rows:
    both succeed, one row, same id/scope/report/verdict, no
    PendingRollbackError escapes."""
    _, _, rev, pr1, pr2 = await _race_world(client, b"x1")
    url = f"/performance-revisions/{rev['id']}/retarget-assessments"
    payload = {"from_production_revision_id":
               pr1["production_revision_id"],
               "to_production_revision_id":
               pr2["production_revision_id"]}
    r1, r2 = await asyncio.gather(client.post(url, json=payload),
                                  client.post(url, json=payload))
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["scope_hash"] == r2.json()["scope_hash"]
    assert r1.json()["report_hash"] == r2.json()["report_hash"]
    assert r1.json()["overall_verdict"] == \
        r2.json()["overall_verdict"] == "REQUIRES_REVIEW"
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_retarget_assessments "
            "WHERE performance_revision_id = :r"),
            {"r": rev["id"]})).scalar()
    assert n == 1


@pytest.mark.asyncio
async def test_x1b_sequential_convergence_and_201_status_pinned(client):
    """Sequential identical requests converge; 201 is the pinned
    status on BOTH the newly-inserted and convergence paths."""
    _, _, rev, pr1, pr2 = await _race_world(client, b"x1b")
    url = f"/performance-revisions/{rev['id']}/retarget-assessments"
    payload = {"from_production_revision_id":
               pr1["production_revision_id"],
               "to_production_revision_id":
               pr2["production_revision_id"]}
    r1 = await client.post(url, json=payload)
    r2 = await client.post(url, json=payload)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_x2_poisoned_session_discipline(tmp_path):
    """A forced ORM-flush unique conflict (via the PRODUCT model)
    followed by any query on the same session raises
    PendingRollbackError — proving the production convergence must
    (and now does) happen at the route boundary. Core text() INSERT
    failures do NOT poison the session; only the ORM flush path
    does (independent-review empirical nuance)."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, PendingRollbackError
    from sqlalchemy.ext.asyncio import (async_sessionmaker,
                                        create_async_engine)
    from soloring.db.base import Base
    from soloring.db import models  # noqa: register tables
    from soloring.db.engine import create_soloring_engine
    from soloring.settings import Settings

    async def go():
        settings = Settings(data_dir=tmp_path / "d")
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        eng = create_soloring_engine(settings)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            now = "2026-01-01T00:00:00.000Z"
            await conn.execute(text(
                "INSERT INTO projects (id,name,created_at,updated_at)"
                " VALUES ('p','P','" + now + "','" + now + "')"))
            await conn.execute(text(
                "INSERT INTO blobs (hash, path, size_bytes, "
                "detected_media_type, created_at) VALUES ('"
                + "a" * 64 + "','sha256/aa/aa/" + "a" * 64
                + "',1,NULL,'" + now + "')"))
            await conn.execute(text(
                "INSERT INTO creative_entities (id, project_id, "
                "kind, name, created_at, updated_at) VALUES "
                "('p','p','character','S','" + now + "','" + now
                + "')"))
            await conn.execute(text(
                "INSERT INTO performance_candidates (id,project_id,"
                "subject_id,performance_kind,"
                "performance_profile_id,temporal_start_num,"
                "temporal_start_den,temporal_end_num,"
                "temporal_end_den,"
                "canonical_channel_payload_blob_hash,"
                "canonical_channel_payload_sha256,"
                "payload_schema_version,source_kind,"
                "provenance_schema_version,provenance_json,"
                "provenance_hash,created_at) VALUES "
                "('c','p','p','FACIAL',"
                "'performance-profile/1',0,1,4500,1,'"
                + "a" * 64 + "','" + "a" * 64
                + "',1,'authored',1,'{}','" + "b" * 64
                + "','" + now + "')"))
        from soloring.performance.models import (
            PerformanceCandidate)
        S = async_sessionmaker(bind=eng, expire_on_commit=False)
        async with S() as s:
            s.add(PerformanceCandidate(
                id="c", project_id="p", subject_id="p",
                performance_kind="FACIAL",
                performance_profile_id="performance-profile/1",
                temporal_start_num=0, temporal_start_den=1,
                temporal_end_num=4500, temporal_end_den=1,
                canonical_channel_payload_blob_hash="a" * 64,
                canonical_channel_payload_sha256="a" * 64,
                payload_schema_version=1, source_kind="authored",
                provenance_schema_version=1, provenance_json="{}",
                provenance_hash="b" * 64,
                created_at="2026-01-01T00:00:00.000Z"))
            try:
                await s.flush()
                raise AssertionError("conflict missing")
            except IntegrityError:
                pass
            with pytest.raises(PendingRollbackError):
                await s.execute(text("SELECT 1"))
        await eng.dispose()

    asyncio.run(go())


# --------------------------- X3/X4 ---------------------------------

async def _corrupt_payload_blob(client, c):
    settings = client._transport.app.state.settings
    p = (settings.blob_dir / "sha256" /
         c["canonical_channel_payload_blob_hash"][:2] /
         c["canonical_channel_payload_blob_hash"][2:4] /
         c["canonical_channel_payload_blob_hash"])
    p.write_bytes(b"corrupted-payload-bytes")


async def _corrupt_provenance(client, c, prov_doc):
    engine = client._transport.app.state.engine
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    j = canonical_json_str(prov_doc)
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_candidates SET provenance_json = :j, "
            "provenance_hash = :h WHERE id = :i"),
            {"j": j, "h": canonical_hash(prov_doc), "i": c["id"]})


@pytest.mark.asyncio
async def test_x3a_physical_blob_corruption_before_adoption_rejects(client):
    pid, eid = await _subject(client, "X3a")
    c = (await _post(client, eid, _body())).json()
    await _corrupt_payload_blob(client, c)
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions"),
            )).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_x3b_dual_hash_disagreement_rejects(client):
    pid, eid = await _subject(client, "X3b")
    c = (await _post(client, eid, _body())).json()
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_candidates SET "
            "canonical_channel_payload_sha256 = '" + "c" * 64 +
            "' WHERE id = :i"), {"i": c["id"]})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_x3c_noncanonical_payload_rejects(client):
    from tests.m17b_seed import JAW
    pid, eid = await _subject(client, "X3c")
    two = candidate_body([channel(SMILE, [kf(0, 1, 0)]),
                          channel(JAW, [kf(0, 1, 100)])])
    c = (await _post(client, eid, two)).json()
    settings = client._transport.app.state.settings
    h = c["canonical_channel_payload_blob_hash"]
    p = (settings.blob_dir / "sha256" / h[:2] / h[2:4] / h)
    doc = json.loads(p.read_bytes())
    assert len(doc["channels"]) == 2
    doc["channels"].reverse()  # 2-channel reversal is NONcanonical
    from soloring.domain.canonical import canonical_json_str
    noncanon = canonical_json_str(doc).encode("utf-8")
    p.write_bytes(noncanon)
    nh = hashlib.sha256(noncanon).hexdigest()
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, "
            "NULL, '2026-01-01T00:00:00.000Z')"),
            {"h": nh,
             "p": f"sha256/{nh[:2]}/{nh[2:4]}/{nh}", "s": len(noncanon)})
        await conn.execute(text(
            "UPDATE performance_candidates SET "
            "canonical_channel_payload_blob_hash = :h, "
            "canonical_channel_payload_sha256 = :h WHERE id = :i"),
            {"h": nh, "i": c["id"]})
    np_ = (settings.blob_dir / "sha256" / nh[:2] / nh[2:4] / nh)
    np_.parent.mkdir(parents=True, exist_ok=True)
    np_.write_bytes(noncanon)
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_x3d_provenance_hash_drift_rejects(client):
    pid, eid = await _subject(client, "X3d")
    c = (await _post(client, eid, _body())).json()
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_candidates SET provenance_hash = '"
            + "d" * 64 + "' WHERE id = :i"), {"i": c["id"]})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_x3e_selfconsistent_provenance_grammar_violation_rejects(client):
    pid, eid = await _subject(client, "X3e")
    c = (await _post(client, eid, _body())).json()
    await _corrupt_provenance(client, c, {
        "schema_version": 1, "source_kind": "authored",
        "producer_id": "p", "producer_version": "1",
        "source_identity": None, "parameters_sha256": None,
        "retarget": None, "extra_forbidden_key": True})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_x3f_source_identity_path_form_rejects(client):
    pid, eid = await _subject(client, "X3f")
    c = (await _post(client, eid, _body())).json()
    await _corrupt_provenance(client, c, {
        "schema_version": 1, "source_kind": "authored",
        "producer_id": "p", "producer_version": "1",
        "source_identity": "file://x/y", "parameters_sha256": None,
        "retarget": None})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_x4_corrupt_winner_replay_fails_closed(client):
    pid, eid = await _subject(client, "X4")
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/"
                             "adopt",
                             json={"adopted_by": "d"})).json()
    # tamper the WINNER closure before duplicate replay
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET performance_kind = "
            "'BODY' WHERE id = :i"), {"i": rev["id"]})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "other"})
    assert r.status_code == 500, r.text


# --------------------------- X5 ------------------------------------

@pytest.mark.asyncio
async def test_x5_adopt_delete_duplicate_adopt_returns_winner(client):
    pid, eid = await _subject(client, "X5")
    c = (await _post(client, eid, _body())).json()
    r1 = (await client.post(f"/performance-candidates/{c['id']}/"
                            "adopt",
                            json={"adopted_by": "director"})).json()
    r = await client.delete(f"/entities/{eid}")
    assert r.status_code in (200, 204)
    r2 = await client.post(f"/performance-candidates/{c['id']}/adopt",
                           json={"adopted_by": "producer"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["id"] == r1["id"]
    assert r2.json()["adoption_id"] == r1["adoption_id"]
    assert r2.json()["adopted_by"] == "director"


@pytest.mark.asyncio
async def test_x5b_first_adoption_after_delete_rejects(client):
    pid, eid = await _subject(client, "X5b")
    c = (await _post(client, eid, _body())).json()
    await client.delete(f"/entities/{eid}")
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code == 422
    assert r.json()["error_code"] == "PERFORMANCE_SUBJECT_DELETED"


# --------------------------- X6/X7 ---------------------------------

@pytest.mark.asyncio
async def test_x6_http_scalar_strictness(client):
    pid, eid = await _subject(client, "X6")
    for bad_body in (_body(value=True), _body(value="7"),
                     _body(value=7.0), _body(num=True),
                     _body(num="7"), _body(num=7.0)):
        r = await _post(client, eid, bad_body)
        assert r.status_code == 422, (r.status_code, r.text)
    ok = await _post(client, eid, _body(value=5, num=0))
    assert ok.status_code == 201, ok.text


@pytest.mark.asyncio
async def test_x7_frozen_create_body_grammar(client):
    pid, eid = await _subject(client, "X7")
    nested = _body()
    assert "temporal_domain" in nested
    r = await _post(client, eid, nested)
    assert r.status_code == 201, r.text
    flat = dict(nested)
    flat["temporal_start"] = flat.pop("temporal_domain")["start"]
    flat["temporal_end"] = {"num": 4500, "den": 1}
    r2 = await _post(client, eid, flat)
    assert r2.status_code == 422  # closed model rejects obsolete form


# --------------------------- X8 ------------------------------------

@pytest.mark.asyncio
async def test_x8_concurrent_first_identical_candidates_one_blob(client):
    pid, eid = await _subject(client, "X8")
    body = _body(value=42)
    r1, r2 = await asyncio.gather(_post(client, eid, body),
                                   _post(client, eid, body))
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    c1, c2 = r1.json(), r2.json()
    assert c1["canonical_channel_payload_blob_hash"] == \
        c2["canonical_channel_payload_blob_hash"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n_blob = (await conn.execute(text(
            "SELECT COUNT(*) FROM blobs WHERE hash = :h"),
            {"h": c1["canonical_channel_payload_blob_hash"]})).scalar()
        n_rev = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions"))).scalar()
    assert n_blob == 1
    assert n_rev == 0
    settings = client._transport.app.state.settings
    h = c1["canonical_channel_payload_blob_hash"]
    p = (settings.blob_dir / "sha256" / h[:2] / h[2:4] / h)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == h


# --------------------------- X9 ------------------------------------

async def _seeded_candidate(client, tag):
    pid, eid = await _subject(client, f"X9-{tag!r}")
    c = (await _post(client, eid, _body())).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await __import__("tests.m17b_seed", fromlist=["stamp_alembic"]) \
        .stamp_alembic(client)
    return pid, eid, c


def _verify(client):
    from soloring.recovery.m17b_verifier import (
        verify_m17b_performance_state)
    settings = client._transport.app.state.settings
    return verify_m17b_performance_state(
        settings.data_dir / "soloring.db", settings.blob_dir)


@pytest.mark.asyncio
async def test_x9_recovery_provenance_grammar_corruptions(client):
    pid, eid, c = await _seeded_candidate(client, b"prov")
    engine = client._transport.app.state.engine
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    bad_docs = [
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "p", "producer_version": "1",
         "source_identity": None, "parameters_sha256": None,
         "retarget": None, "extra": 1},
        {"schema_version": 2, "source_kind": "authored",
         "producer_id": "p", "producer_version": "1",
         "source_identity": None, "parameters_sha256": None,
         "retarget": None},
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "p" * 256, "producer_version": "1",
         "source_identity": None, "parameters_sha256": None,
         "retarget": None},
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "p", "producer_version": "1",
         "source_identity": "FILE://x", "parameters_sha256": None,
         "retarget": None},
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "p", "producer_version": "1",
         "source_identity": None, "parameters_sha256": "XYZ",
         "retarget": None},
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "p", "producer_version": "1",
         "source_identity": None, "parameters_sha256": None,
         "retarget": {"source_performance_revision_id": "x"}},
    ]
    for doc in bad_docs:
        j = canonical_json_str(doc)
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE performance_candidates SET provenance_json = "
                ":j, provenance_hash = :h WHERE id = :i"),
                {"j": j, "h": canonical_hash(doc), "i": c["id"]})
        with pytest.raises(Exception) as ei:
            _verify(client)
        assert "grammar" in str(ei.value), str(ei.value)
    # restore a lawful envelope passes again
    good = {"schema_version": 1, "source_kind": "authored",
            "producer_id": "p", "producer_version": "1",
            "source_identity": None, "parameters_sha256": None,
            "retarget": None}
    j = canonical_json_str(good)
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_candidates SET provenance_json = :j, "
            "provenance_hash = :h WHERE id = :i"),
            {"j": j, "h": canonical_hash(good), "i": c["id"]})
    _verify(client)


@pytest.mark.asyncio
async def test_x9_recovery_adoption_and_review_grammar(client):
    pid, eid, c = await _seeded_candidate(client, b"adp")
    rev = (await client.post(f"/performance-candidates/{c['id']}/"
                             "adopt",
                             json={"adopted_by": "d"})).json()
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET adoption_id = "
            "'not-a-uuid' WHERE id = :i"), {"i": rev["id"]})
    with pytest.raises(Exception) as ei:
        _verify(client)
    assert "adoption" in str(ei.value)
    from soloring.domain.ids import new_uuid
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET adoption_id = :a "
            "WHERE id = :i"),
            {"a": new_uuid(), "i": rev["id"]})
        await conn.execute(text(
            "UPDATE performance_revisions SET adopted_by = :b "
            "WHERE id = :i"),
            {"b": "x" * 256, "i": rev["id"]})
    with pytest.raises(Exception) as ei2:
        _verify(client)
    assert "adopted_by" in str(ei2.value) or "grammar" in \
        str(ei2.value)


# --------------------------- X10/X11 -------------------------------

@pytest.mark.asyncio
async def test_x10_f05_real_immutability_surface(client):
    pid, eid = await _subject(client, "X10")
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/"
                             "adopt",
                             json={"adopted_by": "d"})).json()
    from soloring.api.m17b_performance import router as m17b_router
    methods = {}
    for route in m17b_router.routes:
        path = getattr(route, "path", "")
        if path == "/performance-revisions/{revision_id}":
            methods.setdefault(path, set()).update(
                route.methods)
    assert "/performance-revisions/{revision_id}" in methods
    allowed = methods["/performance-revisions/{revision_id}"]
    assert "GET" in allowed
    assert not (allowed & {"PUT", "PATCH", "DELETE"})
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
    assert r.json()["performance_kind"] == "FACIAL"
    assert r.json()["canonical_channel_payload_sha256"] == \
        rev["canonical_channel_payload_sha256"]


@pytest.mark.asyncio
async def test_x11_a03_subject_owned_project_derivation(client):
    from fastapi.routing import APIRoute
    pid, eid = await _subject(client, "X11")
    from soloring.api.schemas.m17b_performance import (
        PerformanceCandidateCreate)
    schema_fields = set(PerformanceCandidateCreate.model_fields)
    assert "project_id" not in schema_fields, \
        "the create schema exposes no caller project override"
    c = (await _post(client, eid, _body())).json()
    assert c["project_id"] == pid
    p2 = (await client.post("/projects",
                            json={"name": "X11-B"})).json()["id"]
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_candidates WHERE "
            "project_id = :p AND subject_id = :s"),
            {"p": p2, "s": eid})).scalar()
    assert n == 0


# --------------------------- X12/X13 --------------------------------
# Publication-stage review regressions (PUB-R1): running-app Settings
# propagation and alignment provenance project binding.


@pytest.mark.asyncio
async def test_x12_adoption_uses_running_app_settings_not_the_process_singleton(client, tmp_path):
    """PUB-R1 regression: adoption integrity reads the retained Blob
    through the RUNNING APP's Settings (request.app.state.settings).
    With the process singleton poisoned toward a different (empty)
    data root, first adoption AND winner replay must both succeed and
    round-trip the payload hash from the app root."""
    from soloring import settings as settings_mod
    from soloring.settings import Settings
    pid, eid = await _subject(client, "X12")
    poisoned = Settings(data_dir=tmp_path / "poisoned-root")
    previous = settings_mod._settings
    settings_mod._settings = poisoned
    try:
        c = (await _post(client, eid, _body())).json()
        r1 = await client.post(
            f"/performance-candidates/{c['id']}/adopt",
            json={"adopted_by": "d"})
        assert r1.status_code == 200, r1.text
        r2 = await client.post(
            f"/performance-candidates/{c['id']}/adopt",
            json={"adopted_by": "d2"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["id"] == r1.json()["id"]  # winner replay
        assert r1.json()["canonical_channel_payload_sha256"] == \
            c["canonical_channel_payload_sha256"]
    finally:
        settings_mod._settings = previous


@pytest.mark.asyncio
async def test_x13_alignment_from_another_project_rejects_at_creation_and_adoption(client):
    """PUB-R1 regression: an alignment whose dialogue line lives in
    ANOTHER project - even with the speaker equal to the Performance
    subject - is rejected at candidate creation AND at adoption-time
    integrity (a DB-crafted candidate that bypassed creation gets the
    same refusal), matching the recovery verifier's project law."""
    pid, eid = await _subject(client, "X13")
    engine = client._transport.app.state.engine
    now = "2026-01-01T00:00:00.000Z"
    h64 = "c" * 64
    p2 = "00000000-0000-4000-8000-000000000b01"
    dl = "00000000-0000-4000-8000-000000000b02"
    dlr = "00000000-0000-4000-8000-000000000b03"
    vc = "00000000-0000-4000-8000-000000000b04"
    vpr = "00000000-0000-4000-8000-000000000b05"
    aid = "00000000-0000-4000-8000-000000000b06"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'X13-B', :n, :n)"), {"i": p2, "n": now})
        await conn.execute(text(
            "INSERT INTO dialogue_lines (id, project_id, created_at) "
            "VALUES (:i, :p, :n)"),
            {"i": dl, "p": p2, "n": now})
        await conn.execute(text(
            "INSERT INTO dialogue_line_revisions (id, dialogue_line_id,"
            " revision_number, speaker_subject_id, language, wording, "
            "schema_version, spec_json, spec_hash, created_at) VALUES "
            "(:i, :l, 1, :sp, 'en', 'x13 line', 1, '{}', :sh, :n)"),
            {"i": dlr, "l": dl, "sp": eid, "sh": h64, "n": now})
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :pa, 1, NULL, :n)"),
            {"h": h64, "pa": f"sha256/{h64[:2]}/{h64[2:4]}/{h64}",
             "n": now})
        await conn.execute(text(
            "INSERT INTO vocal_candidates (id, dialogue_line_revision_id,"
            " retained_audio_blob_hash, native_sample_rate_hz, "
            "retained_sample_count, trim_start_sample, "
            "trim_end_sample_exclusive, source_kind, "
            "provenance_schema_version, provenance_json, "
            "provenance_hash, created_at) VALUES "
            "(:i, :l, :h, 48000, 10, 0, 10, 'recorded', 1, '{}', "
            ":ph, :n)"),
            {"i": vc, "l": dlr, "h": h64, "ph": h64, "n": now})
        await conn.execute(text(
            "INSERT INTO vocal_performance_revisions (id, "
            "dialogue_line_revision_id, revision_number, "
            "speaker_subject_id, retained_audio_blob_hash, "
            "native_sample_rate_hz, retained_sample_count, "
            "trim_start_sample, trim_end_sample_exclusive, "
            "source_kind, provenance_schema_version, provenance_json, "
            "provenance_hash, adopted_candidate_id, adoption_id, "
            "adopted_by, adopted_at) VALUES "
            "(:i, :l, 1, :sp, :h, 48000, 10, 0, 10, 'recorded', 1, "
            "'{}', :ph, :vc, :ad, 'x13', :n)"),
            {"i": vpr, "l": dlr, "sp": eid, "h": h64, "ph": h64,
             "vc": vc, "ad": "00000000-0000-4000-8000-000000000b07",
             "n": now})
        await conn.execute(text(
            "INSERT INTO dialogue_alignments (id, "
            "vocal_performance_revision_id, analyzer_id, "
            "analyzer_version, model_identity, runtime_identity, "
            "parameters_sha256, alignment_schema_version, "
            "retained_blob_hash, retained_sha256, derivation_run_json, "
            "derivation_run_hash, derivation_run_identity, created_at)"
            " VALUES (:i, :v, 'x13-analyzer', '1', 'm', 'r', :ph, 1, "
            ":h, :h, '{}', :dh, :dh, :n)"),
            {"i": aid, "v": vpr, "ph": h64, "h": h64,
             "dh": "d" * 64, "n": now})

    # creation path: the cross-project alignment reference rejects
    from tests.m17b_seed import candidate_body
    body = candidate_body([channel(SMILE, [kf(0, 1, 0, kind="DERIVED",
                                               alignment=aid)])])
    r = await _post(client, eid, body)
    assert r.status_code in (403, 422), r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_ALIGNMENT_PROJECT_MISMATCH", r.text

    # adoption path: a DB-crafted candidate that bypassed creation
    # (fully lawful closure bytes, keyframes referencing the
    # cross-project alignment) gets the same refusal at integrity time
    from soloring.performance.profile import build_canonical_payload
    from soloring.performance.revision import build_provenance_envelope
    from soloring.domain.canonical import (canonical_hash,
                                           canonical_json_str)
    payload = {"schema_version": 1,
               "performance_profile_id": "performance-profile/1",
               "channels": body["channels"]}
    body_bytes, _norm = build_canonical_payload(
        payload, performance_kind="FACIAL",
        performance_profile_id="performance-profile/1",
        start_num=0, start_den=1, end_num=4500, end_den=1)
    bh = hashlib.sha256(body_bytes).hexdigest()
    envelope = build_provenance_envelope(
        {"schema_version": 1, "source_kind": "authored",
         "producer_id": "x13", "producer_version": "1",
         "source_identity": None, "parameters_sha256": None,
         "retarget": None})
    prov_json = canonical_json_str(envelope)
    settings = client._transport.app.state.settings
    bp = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_bytes(body_bytes)
    cid = "00000000-0000-4000-8000-000000000b08"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :p, :s, NULL, :n)"),
            {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
             "s": len(body_bytes), "n": now})
        await conn.execute(text(
            "INSERT INTO performance_candidates (id, project_id, "
            "subject_id, performance_kind, performance_profile_id, "
            "temporal_start_num, temporal_start_den, "
            "temporal_end_num, temporal_end_den, "
            "canonical_channel_payload_blob_hash, "
            "canonical_channel_payload_sha256, payload_schema_version,"
            " source_kind, provenance_schema_version, provenance_json, "
            "provenance_hash, created_at) VALUES "
            "(:i, :p, :s, 'FACIAL', 'performance-profile/1', 0, 1, "
            "4500, 1, :h, :h, 1, 'authored', 1, :j, :ph, :n)"),
            {"i": cid, "p": pid, "s": eid, "h": bh, "j": prov_json,
             "ph": canonical_hash(envelope), "n": now})
    r2 = await client.post(f"/performance-candidates/{cid}/adopt",
                           json={"adopted_by": "d"})
    assert r2.status_code in (403, 422), r2.text
    assert r2.json()["error_code"] == \
        "PERFORMANCE_ALIGNMENT_PROJECT_MISMATCH", r2.text
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions"))).scalar()
    assert n == 0


# --------------------------- X14-X17 --------------------------------
# PUB-R3 regressions (Codex independent-review findings).


async def _r37world(client, tag: bytes):
    from tests.m17b_seed import (make_entity, make_project,
                                 seed_production_object,
                                 seed_production_revision, stamp_alembic)
    pid = await make_project(client, name=f"R37 {tag!r}")
    eid = await make_entity(client, pid)
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/adopt",
                             json={"adopted_by": "d"})).json()
    obj = await seed_production_object(client, pid, "R37 obj", tag)
    pr1 = await seed_production_revision(client, obj, tag + b"1", 1)
    pr2 = await seed_production_revision(client, obj, tag + b"2", 2)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    return pid, eid, c, rev, obj, pr1, pr2, a


@pytest.mark.asyncio
async def test_x14_backup_and_restore_use_operation_blob_root_not_process_singleton(client, tmp_path):
    """PUB-R3/Codex-P1: with the process Settings singleton poisoned
    toward an EMPTY data root, backup() must verify M17B payloads
    under the operation's (app) Blob root and restore() under the
    restore-staged tree — never get_settings().blob_dir."""
    from soloring import settings as settings_mod
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings
    from tests.m17b_seed import stamp_alembic
    pid, eid = await _subject(client, "X14")
    c = (await _post(client, eid, _body())).json()
    await client.post(f"/performance-candidates/{c['id']}/adopt",
                      json={"adopted_by": "d"})
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    settings = client._transport.app.state.settings
    poisoned = Settings(data_dir=tmp_path / "poisoned-root")
    previous = settings_mod._settings
    settings_mod._settings = poisoned
    try:
        root = tmp_path / "bk"
        await backup(settings, root)
        dest = tmp_path / "rs"
        await restore(root, dest)
    finally:
        settings_mod._settings = previous
    import sqlite3
    con = sqlite3.connect(dest / "soloring.db")
    n, h = con.execute(
        "SELECT COUNT(*), MAX(canonical_channel_payload_blob_hash) "
        "FROM performance_candidates").fetchone()
    con.close()
    assert n == 1 and h == c["canonical_channel_payload_blob_hash"]


@pytest.mark.asyncio
async def test_x15_backup_at_0019_rejects_m14_and_m15_semantic_corruption(client, tmp_path):
    """PUB-R3/Codex-P1: at head 0019 the liveness wrapper now runs the
    M14 observation and M15 compatibility verifiers; representative
    corruption in either must refuse the BACKUP."""
    from soloring.recovery.backup import backup
    pid, eid, c, rev, obj, pr1, pr2, a = await _r37world(client, b"x15")
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    e64 = "e" * 64
    bad_m14 = ("INSERT INTO derived_observation_artifacts "
               "(id, project_id, observation_spec_hash, artifact_role, "
               "materializer_id, materializer_version, "
               "materializer_contract_hash, parameters_json, "
               "parameters_hash, provenance_json, provenance_hash, "
               "blob_hash, created_at) VALUES "
               "(:i, :p, :sh, 'observation.world_depth', 'm', 1, :mc, "
               "'{}', :ph, "
               "'{}', :pv, :bh, :n)")
    m14_params = {"i": "00000000-0000-4000-8000-00000000c401",
                  "p": pid, "sh": "z" * 64, "mc": e64,
                  "ph": e64, "pv": e64,
                  "bh": c["canonical_channel_payload_blob_hash"],
                  "n": "2026-01-01T00:00:00.000Z"}
    async with engine.begin() as conn:
        await conn.execute(text(bad_m14), m14_params)
    with pytest.raises(Exception) as exc_info:
        await backup(settings, tmp_path / "bk14")
    assert "observation_spec_hash" in str(exc_info.value)
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM derived_observation_artifacts WHERE id = :i"),
            {"i": m14_params["i"]})
    bad_m15 = ("INSERT INTO production_compatibility_assessments "
               "(id, project_id, production_object_id, from_revision_id, "
               "from_revision_hash, to_revision_id, to_revision_hash, "
               "schema_version, evaluator_id, evaluator_version, "
               "scope_json, scope_hash, report_json, report_hash, "
               "overall_verdict, created_at) VALUES "
               "(:i, :p, :o, :f, :sh, :t, :h, 1, "
               "'soloring.production_revision_compatibility', 1, '{}', "
               ":sc, "
               "'{}', :rh, 'COMPATIBLE_AS_IS', :n)")
    async with engine.begin() as conn:
        await conn.execute(text(bad_m15),
                           {"i": "00000000-0000-4000-8000-00000000c501",
                            "p": pid, "o": obj,
                            "f": pr1["production_revision_id"],
                            "sh": "z" * 64,
                            "t": pr2["production_revision_id"],
                            "h": "f" * 64, "sc": "a" * 64,
                            "rh": "b" * 64,
                            "n": "2026-01-01T00:00:00.000Z"})
    with pytest.raises(Exception) as exc_info:
        await backup(settings, tmp_path / "bk15")
    assert "revision hash invalid" in str(exc_info.value)


@pytest.mark.asyncio
async def test_x16_restore_at_0019_rejects_m14_and_m15_semantic_corruption(client, tmp_path):
    """PUB-R3/Codex-P1 (restore side): a backup tree whose DB carries
    representative M14/M15 semantic corruption — with the manifest
    database hash recomputed so the tree is self-consistent — must be
    REFUSED at restore by the newly-dispatched predecessor verifiers."""
    import hashlib
    import json as _json
    import sqlite3
    from soloring.recovery.backup import backup, restore
    pid, eid, c, rev, obj, pr1, pr2, a = await _r37world(client, b"x16")
    settings = client._transport.app.state.settings
    root = tmp_path / "bk"
    await backup(settings, root)

    def _tamper_and_reseal(sql: str, params) -> None:
        db = root / "soloring.db"
        con = sqlite3.connect(db)
        con.execute(sql, params)
        con.commit()
        con.close()
        mf = root / "backup-manifest.json"
        doc = _json.loads(mf.read_text(encoding="utf-8"))
        doc["database_sha256"] = hashlib.sha256(
            db.read_bytes()).hexdigest()
        from soloring.domain.canonical import canonical_json_bytes
        mf.write_bytes(canonical_json_bytes(doc))

    e64 = "e" * 64
    _tamper_and_reseal(
        "INSERT INTO derived_observation_artifacts "
        "(id, project_id, observation_spec_hash, artifact_role, "
        "materializer_id, materializer_version, "
        "materializer_contract_hash, parameters_json, parameters_hash, "
        "provenance_json, provenance_hash, blob_hash, created_at) "
        "VALUES (?, ?, ?, 'observation.world_depth', 'm', 1, ?, '{}', "
        "?, '{}', ?, ?, '2026-01-01T00:00:00.000Z')",
        ("00000000-0000-4000-8000-00000000c402", pid, "z" * 64,
         e64, e64, e64, c["canonical_channel_payload_blob_hash"]))
    with pytest.raises(Exception) as exc_info:
        await restore(root, tmp_path / "rs14")
    assert "observation_spec_hash" in str(exc_info.value)

    _tamper_and_reseal(
        "DELETE FROM derived_observation_artifacts WHERE id = ?",
        ("00000000-0000-4000-8000-00000000c402",))
    _tamper_and_reseal(
        "INSERT INTO production_compatibility_assessments "
        "(id, project_id, production_object_id, from_revision_id, "
        "from_revision_hash, to_revision_id, to_revision_hash, "
        "schema_version, evaluator_id, evaluator_version, scope_json, "
        "scope_hash, report_json, report_hash, overall_verdict, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, "
        "'soloring.production_revision_compatibility', "
        "1, '{}', ?, '{}', ?, 'COMPATIBLE_AS_IS', "
        "'2026-01-01T00:00:00.000Z')",
        ("00000000-0000-4000-8000-00000000c502", pid, obj,
         pr1["production_revision_id"], "z" * 64,
         pr2["production_revision_id"], "f" * 64,
         "a" * 64, "b" * 64))
    with pytest.raises(Exception) as exc_info:
        await restore(root, tmp_path / "rs15")
    assert "revision hash invalid" in str(exc_info.value)


@pytest.mark.asyncio
async def test_x17_recovery_rejects_self_consistent_cross_project_assessment(client, tmp_path):
    """PUB-R3/Codex-P1: an assessment whose referenced
    ProductionObject is moved to ANOTHER project — with scope/report
    still recomputing byte-identically (self-consistent) — is
    corruption under the live-service Project law, now enforced by
    recovery too."""
    pid, eid, c, rev, obj, pr1, pr2, a = await _r37world(client, b"x17")
    p2 = (await client.post("/projects",
                            json={"name": "X17-B"})).json()["id"]
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE production_objects SET project_id = :p "
            "WHERE id = :o"), {"p": p2, "o": obj})
    with pytest.raises(Exception) as exc_info:
        _verify(client)
    assert "another project" in str(exc_info.value)


# --------------------------- X18-X20 --------------------------------
# Second-Codex-review regressions (adoption integrity + API contract).


@pytest.mark.asyncio
async def test_x18_adoption_rejects_subject_project_disagreement(client):
    """Second-Codex P1: a schema-valid candidate whose project_id is
    NOT its subject's project (DB-crafted) must not be promotable —
    the live adoption now enforces the recovery verifier's
    subject/project agreement law."""
    pid, eid = await _subject(client, "X18")
    p2 = (await client.post("/projects",
                            json={"name": "X18-B"})).json()["id"]
    c = (await _post(client, eid, _body())).json()
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_candidates SET project_id = :p "
            "WHERE id = :i"), {"p": p2, "i": c["id"]})
    r = await client.post(f"/performance-candidates/{c['id']}/adopt",
                          json={"adopted_by": "d"})
    assert r.status_code in (403, 422), r.text
    assert r.json()["error_code"] == "PERFORMANCE_PROJECT_MISMATCH"
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions"))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_x19_adoption_rejects_unresolved_retarget_evidence(client):
    """Second-Codex P1: a retargeted candidate's provenance must
    actually RESOLVE at adoption — source revision, exact assessment
    coordinate, REQUIRES_REVIEW verdict, owned ACCEPT review. Forged
    ids, a stale coordinate, and a non-accepting review each refuse
    promotion (the recovery verifier's law, now enforced live)."""
    from tests.m17b_seed import (make_entity, make_project,
                                 seed_production_object,
                                 seed_production_revision)
    pid = await make_project(client, name="X19")
    eid = await make_entity(client, pid)
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/adopt",
                             json={"adopted_by": "d"})).json()
    obj = await seed_production_object(client, pid, "X19 obj", b"x19")
    pr1 = await seed_production_revision(client, obj, b"x19-1", 1)
    pr2 = await seed_production_revision(client, obj, b"x19-2", 2)
    pr3 = await seed_production_revision(client, obj, b"x19-3", 3)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    accept = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "rev", "rationale": None})).json()
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings

    def _craft(producer, retarget):
        from soloring.performance.revision import (
            build_provenance_envelope)
        from soloring.domain.canonical import (canonical_hash,
                                               canonical_json_str)
        envelope = build_provenance_envelope(
            {"schema_version": 1, "source_kind": "retargeted",
             "producer_id": producer, "producer_version": "1",
             "source_identity": None, "parameters_sha256": None,
             "retarget": retarget})
        return canonical_json_str(envelope), canonical_hash(envelope)

    def _retarget_candidate(prov_json, prov_hash, producer):
        from soloring.performance.profile import build_canonical_payload
        payload = {"schema_version": 1,
                   "performance_profile_id":
                       "performance-profile/1",
                   "channels": candidate_body(
                       [channel(SMILE, [kf(0, 1, 0)])])["channels"]}
        body_bytes, _ = build_canonical_payload(
            payload, performance_kind="FACIAL",
            performance_profile_id="performance-profile/1",
            start_num=0, start_den=1, end_num=4500, end_den=1)
        bh = hashlib.sha256(body_bytes).hexdigest()
        bp = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_bytes(body_bytes)
        cid = producer.replace("x19-", "00000000-0000-4000-8000-0000000")
        import sqlite3 as _s
        con = _s.connect(settings.data_dir / "soloring.db")
        con.execute(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (?, ?, ?, NULL, "
            "'2026-01-01T00:00:00.000Z')",
            (bh, f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", len(body_bytes)))
        con.execute(
            "INSERT INTO performance_candidates (id, project_id, "
            "subject_id, performance_kind, performance_profile_id, "
            "temporal_start_num, temporal_start_den, "
            "temporal_end_num, temporal_end_den, "
            "canonical_channel_payload_blob_hash, "
            "canonical_channel_payload_sha256, payload_schema_version,"
            " source_kind, provenance_schema_version, provenance_json, "
            "provenance_hash, created_at) VALUES (?, ?, ?, 'FACIAL', "
            "'performance-profile/1', 0, 1, 4500, 1, ?, ?, 1, "
            "'retargeted', 1, ?, ?, '2026-01-01T00:00:00.000Z')",
            (cid, pid, eid, bh, bh, prov_json, prov_hash))
        con.commit()
        con.close()
        return cid

    import asyncio as _a

    async def _try_adopt(cid):
        return await client.post(
            f"/performance-candidates/{cid}/adopt",
            json={"adopted_by": "d"})

    # 1. forged ids (nothing resolves)
    producer_label = "x19-forger"
    pj, ph = _craft(producer_label, {
        "source_performance_revision_id": rev["id"],
        "from_production_revision_id":
            pr1["production_revision_id"],
        "to_production_revision_id":
            pr2["production_revision_id"],
        "compatibility_assessment_id":
            "00000000-0000-4000-8000-00000000f001",
        "accepted_review_id":
            "00000000-0000-4000-8000-00000000f002"})
    cid = _retarget_candidate(pj, ph, producer_label)
    r = await _try_adopt(cid)
    assert r.status_code in (403, 422), r.text

    # 1b. FULLY VALID evidence chain but DIVERGENT semantic closure:
    # the crafted payload is lawful and internally canonical yet uses
    # SMILE value 1 while the source revision's payload uses 0 —
    # valid references + edited semantics is exactly the corruption
    # the retarget copy law forbids (final-diff review: the evidence
    # checks alone do not close this)
    from soloring.performance.profile import build_canonical_payload
    from soloring.domain.canonical import (canonical_hash as _ch,
                                           canonical_json_str as _cjs)
    from soloring.performance.revision import build_provenance_envelope \
        as _bpe
    divergent_body, _ = build_canonical_payload(
        {"schema_version": 1,
         "performance_profile_id": "performance-profile/1",
         "channels": candidate_body([channel(SMILE, [kf(0, 1, 1)])])[
             "channels"]},
        performance_kind="FACIAL",
        performance_profile_id="performance-profile/1",
        start_num=0, start_den=1, end_num=4500, end_den=1)
    dbh = hashlib.sha256(divergent_body).hexdigest()
    dbp = settings.blob_dir / "sha256" / dbh[:2] / dbh[2:4] / dbh
    dbp.parent.mkdir(parents=True, exist_ok=True)
    dbp.write_bytes(divergent_body)
    env1b = _bpe({"schema_version": 1, "source_kind": "retargeted",
                  "producer_id": "x19-divergent",
                  "producer_version": "1", "source_identity": None,
                  "parameters_sha256": None,
                  "retarget": {
                      "source_performance_revision_id": rev["id"],
                      "from_production_revision_id":
                          pr1["production_revision_id"],
                      "to_production_revision_id":
                          pr2["production_revision_id"],
                      "compatibility_assessment_id": a["id"],
                      "accepted_review_id": accept["id"]}})
    import sqlite3 as _s2
    con = _s2.connect(settings.data_dir / "soloring.db")
    con.execute(
        "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
        "detected_media_type, created_at) VALUES (?, ?, ?, NULL, "
        "'2026-01-01T00:00:00.000Z')",
        (dbh, f"sha256/{dbh[:2]}/{dbh[2:4]}/{dbh}",
         len(divergent_body)))
    con.execute(
        "INSERT INTO performance_candidates (id, project_id, "
        "subject_id, performance_kind, performance_profile_id, "
        "temporal_start_num, temporal_start_den, temporal_end_num, "
        "temporal_end_den, canonical_channel_payload_blob_hash, "
        "canonical_channel_payload_sha256, payload_schema_version, "
        "source_kind, provenance_schema_version, provenance_json, "
        "provenance_hash, created_at) VALUES "
        "('00000000-0000-4000-8000-0000000x19b', ?, ?, 'FACIAL', "
        "'performance-profile/1', 0, 1, 4500, 1, ?, ?, 1, "
        "'retargeted', 1, ?, ?, '2026-01-01T00:00:00.000Z')",
        (pid, eid, dbh, dbh, _cjs(env1b), _ch(env1b)))
    con.commit()
    con.close()
    r = await client.post(
        "/performance-candidates/"
        "00000000-0000-4000-8000-0000000x19b/adopt",
        json={"adopted_by": "d"})
    assert r.status_code in (403, 422), r.text
    assert "diverges from" in r.json()["message"], r.text

    # 2. real assessment id but stale coordinate (pr3, not pr2)
    producer_label = "x19-stale"
    pj, ph = _craft(producer_label, {
        "source_performance_revision_id": rev["id"],
        "from_production_revision_id":
            pr1["production_revision_id"],
        "to_production_revision_id":
            pr3["production_revision_id"],
        "compatibility_assessment_id": a["id"],
        "accepted_review_id": accept["id"]})
    cid = _retarget_candidate(pj, ph, producer_label)
    r = await _try_adopt(cid)
    assert r.status_code in (403, 422), r.text

    # 3. real coordinate but non-accepting review (REJECT exists on a
    #    second assessment)
    a2 = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr3["production_revision_id"]})).json()
    reject = (await client.post(
        f"/performance-retarget-assessments/{a2['id']}/reviews",
        json={"decision": "REJECT",
              "reviewed_by": "rev", "rationale": None})).json()
    producer_label = "x19-rej"
    pj, ph = _craft(producer_label, {
        "source_performance_revision_id": rev["id"],
        "from_production_revision_id":
            pr1["production_revision_id"],
        "to_production_revision_id":
            pr3["production_revision_id"],
        "compatibility_assessment_id": a2["id"],
        "accepted_review_id": reject["id"]})
    cid = _retarget_candidate(pj, ph, producer_label)
    r = await _try_adopt(cid)
    assert r.status_code in (403, 422), r.text
    engine2 = client._transport.app.state.engine
    async with engine2.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM performance_revisions WHERE "
            "adopted_candidate_id LIKE '%0000000%' AND "
            "adopted_candidate_id != :real", ),
            {"real": c["id"]})).scalar()
    assert n == 0  # none of the crafted candidates were promoted


@pytest.mark.asyncio
async def test_x20_minimal_api_provenance_defaults_materialize(client):
    """Second-Codex P3: a candidate create whose provenance supplies
    ONLY the required producer fields is VALID per the published
    schema and must succeed — the declared defaults (schema_version,
    source_kind, source_identity, parameters_sha256) materialize into
    the complete closed envelope. The route previously stripped them
    via exclude_unset and the service then demanded the exact key
    set, turning a schema-valid request into a 422."""
    from tests.m17b_seed import candidate_body, channel, kf, SMILE
    pid, eid = await _subject(client, "X20")
    body = candidate_body([channel(SMILE, [kf(0, 1, 0)])])
    body["source_provenance"] = {"producer_id": "minimal-client",
                                 "producer_version": "1"}
    r = await _post(client, eid, body)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["source_kind"] == "authored"
    rev = await client.post(f"/performance-candidates/{c['id']}/adopt",
                            json={"adopted_by": "d"})
    assert rev.status_code == 200, rev.text
    # the persisted envelope is the complete closed form
    import json as _json
    from soloring.domain.canonical import canonical_hash
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        pj = (await conn.execute(text(
            "SELECT provenance_json FROM performance_candidates WHERE "
            "id = :i"), {"i": c["id"]})).scalar()
    doc = _json.loads(pj)
    assert set(doc) == {"schema_version", "source_kind", "producer_id",
                        "producer_version", "source_identity",
                        "parameters_sha256", "retarget"}
    assert doc["schema_version"] == 1 and doc["source_kind"] == \
        "authored"
    assert doc["source_identity"] is None and \
        doc["parameters_sha256"] is None


# --------------------------- X21-X23 --------------------------------
# Third-Codex-review regressions (live/recovery authority parity).


@pytest.mark.asyncio
async def test_x21_adoption_rejects_tampered_assessment_verdict(client):
    """Third-Codex P1-1: a stored assessment verdict is never trusted —
    a REQUIRES_REVIEW row whose bytes were tampered from the
    evaluator's actual recomputation (e.g. INCOMPATIBLE overwritten to
    REQUIRES_REVIEW) must refuse retarget promotion, exactly as
    recovery would refuse the same database."""
    from tests.m17b_seed import (make_entity, make_project,
                                 seed_production_object,
                                 seed_production_revision)
    pid = await make_project(client, name="X21")
    eid = await make_entity(client, pid)
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/adopt",
                             json={"adopted_by": "d"})).json()
    obj = await seed_production_object(client, pid, "X21 obj", b"x21")
    # SAME_EXACT_PHYSICAL_REVISION (pr1 -> pr1) yields a
    # non-REQUIRES_REVIEW verdict lawfully; the tamper overwrites it
    pr1 = await seed_production_revision(client, obj, b"x21-1", 1)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr1["production_revision_id"]})).json()
    verdict = a["overall_verdict"]
    assert verdict != "REQUIRES_REVIEW", verdict
    accept = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "rev", "rationale": None})).json()
    engine = client._transport.app.state.engine
    # tamper the stored verdict (and report bytes) to REQUIRES_REVIEW
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_assessments SET "
            "overall_verdict = 'REQUIRES_REVIEW', report_json = "
            "replace(report_json, :old, 'REQUIRES_REVIEW') "
            "WHERE id = :i"),
            {"old": verdict, "i": a["id"]})
    rc = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": accept["id"],
              "producer_id": "x21", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    assert rc.status_code == 201, rc.text
    r = await client.post(
        f"/performance-candidates/{rc.json()['id']}/adopt",
        json={"adopted_by": "d"})
    assert r.status_code in (403, 422), r.text

    # ---- delta-review subcases: the four tamper shapes the
    # recomputation alone (or a stale-hash check alone) cannot catch

    async def _fresh_world(tag: bytes):
        pid_l = await make_project(client, name=f"X21-{tag!r}")
        eid_l = await make_entity(client, pid_l)
        c_l = (await _post(client, eid_l, _body())).json()
        rev_l = (await client.post(
            f"/performance-candidates/{c_l['id']}/adopt",
            json={"adopted_by": "d"})).json()
        obj_l = await seed_production_object(
            client, pid_l, f"X21 obj {tag!r}", tag)
        p1 = await seed_production_revision(client, obj_l, tag + b"1", 1)
        p2 = await seed_production_revision(client, obj_l, tag + b"2", 2)
        a_l = (await client.post(
            f"/performance-revisions/{rev_l['id']}/retarget-assessments",
            json={"from_production_revision_id":
                  p1["production_revision_id"],
                  "to_production_revision_id":
                  p2["production_revision_id"]})).json()
        acc = (await client.post(
            f"/performance-retarget-assessments/{a_l['id']}/reviews",
            json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
                  "reviewed_by": "rev", "rationale": None})).json()
        return pid_l, eid_l, rev_l, obj_l, p1, p2, a_l, acc

    async def _try_adopt_forge(rev_l, a_l, acc):
        rc = await client.post(
            f"/performance-revisions/{rev_l['id']}/retarget-candidates",
            json={"assessment_id": a_l["id"],
                  "accepted_review_id": acc["id"],
                  "producer_id": "x21b", "producer_version": "1",
                  "source_identity": None, "parameters_sha256": None})
        assert rc.status_code == 201, rc.text
        return await client.post(
            f"/performance-candidates/{rc.json()['id']}/adopt",
            json={"adopted_by": "d"})

    # (a) SELF-CONSISTENT forged report+hash: keep the stored
    # verdict REQUIRES_REVIEW (creation requires it) but forge the
    # report's reason_code to one the evaluator would never derive
    # here, and recompute the forged report_hash from the tampered
    # document — no stale-hash check can catch this; only the
    # evaluator's recomputation can
    pid_a, eid_a, rev_a, obj_a, p1a, p2a, a_a, acc_a = \
        await _fresh_world(b"sc")
    engine0 = client._transport.app.state.engine
    async with engine0.connect() as conn:
        stored = (await conn.execute(text(
            "SELECT report_json FROM "
            "performance_retarget_assessments WHERE id = :i"),
            {"i": a_a["id"]})).scalar()
    import json as _j21
    from soloring.domain.canonical import (canonical_hash as _ch21,
                                           canonical_json_str as _cj21)
    doc = _j21.loads(stored)
    assert doc["reason_code"] == \
        "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION"
    doc["reason_code"] = "SAME_EXACT_PHYSICAL_REVISION"
    forged_json = _cj21(doc)
    forged_hash = _ch21(doc)
    async with engine0.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_assessments SET report_json "
            "= :j, report_hash = :h WHERE id = :i"),
            {"j": forged_json, "h": forged_hash, "i": a_a["id"]})
    r = await _try_adopt_forge(rev_a, a_a, acc_a)
    assert r.status_code in (403, 422), r.text
    assert "recomputation" in r.json()["message"], r.text

    # (b) assessment.project_id tampered to another project
    pid_b, eid_b, rev_b, obj_b, p1b, p2b, a_b, acc_b = \
        await _fresh_world(b"pj")
    p_other = (await client.post(
        "/projects", json={"name": "X21-other"})).json()["id"]
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_assessments SET project_id = "
            ":p WHERE id = :i"), {"p": p_other, "i": a_b["id"]})
    r = await _try_adopt_forge(rev_b, a_b, acc_b)
    assert r.status_code in (403, 422), r.text
    assert "project" in r.json()["message"], r.text

    # (c) duplicated snapshot-hash column tampered
    pid_c, eid_c, rev_c, obj_c, p1c, p2c, a_c, acc_c = \
        await _fresh_world(b"sh")
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_retarget_assessments SET "
            "from_production_revision_hash = :h WHERE id = :i"),
            {"h": "b" * 64, "i": a_c["id"]})
    r = await _try_adopt_forge(rev_c, a_c, acc_c)
    assert r.status_code in (403, 422), r.text
    assert "snapshot-hash" in r.json()["message"], r.text

    # (d) referenced ProductionObject moved to another project —
    # scope/report/verdict all still recompute identically; only the
    # persisted ownership law catches it
    pid_d, eid_d, rev_d, obj_d, p1d, p2d, a_d, acc_d = \
        await _fresh_world(b"po")
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE production_objects SET project_id = :p WHERE id = "
            ":o"), {"p": p_other, "o": obj_d})
    r = await _try_adopt_forge(rev_d, a_d, acc_d)
    assert r.status_code in (403, 422), r.text
    assert "project" in r.json()["message"], r.text


@pytest.mark.asyncio
async def test_x22_retarget_rejects_tampered_source_revision_lineage(client):
    """Third-Codex P1-2: the source PerformanceRevision's own adoption
    lineage is revalidated before it may seed new authority — a
    tampered source (closure no longer reproducing its adopted
    candidate) must refuse retarget-seeding, exactly as recovery
    would refuse the same database."""
    from tests.m17b_seed import (make_entity, make_project,
                                 seed_production_object,
                                 seed_production_revision)
    pid = await make_project(client, name="X22")
    eid = await make_entity(client, pid)
    c = (await _post(client, eid, _body())).json()
    rev = (await client.post(f"/performance-candidates/{c['id']}/adopt",
                             json={"adopted_by": "d"})).json()
    obj = await seed_production_object(client, pid, "X22 obj", b"x22")
    pr1 = await seed_production_revision(client, obj, b"x22-1", 1)
    pr2 = await seed_production_revision(client, obj, b"x22-2", 2)
    a = (await client.post(
        f"/performance-revisions/{rev['id']}/retarget-assessments",
        json={"from_production_revision_id":
              pr1["production_revision_id"],
              "to_production_revision_id":
              pr2["production_revision_id"]})).json()
    accept = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "rev", "rationale": None})).json()
    engine = client._transport.app.state.engine
    # tamper the SOURCE revision's adoption lineage: its
    # adopted_candidate_id no longer resolves (kind drift is unusable
    # here — creation itself would refuse a BODY source with face
    # channels; the lineage tamper survives creation and only the
    # adoption-time lineage revalidation catches it)
    decoy = (await _post(client, eid, _body(5))).json()
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE performance_revisions SET adopted_candidate_id = "
            ":decoy WHERE id = :i"),
            {"decoy": decoy["id"], "i": rev["id"]})
    rc = await client.post(
        f"/performance-revisions/{rev['id']}/retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": accept["id"],
              "producer_id": "x22", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})
    r = await client.post(
        f"/performance-candidates/{rc.json()['id']}/adopt",
        json={"adopted_by": "d"})
    assert r.status_code in (403, 422), r.text
    assert "adopted candidate closure" in r.json()["message"], r.text


@pytest.mark.asyncio
async def test_x23_alignment_subject_law_uses_vp_speaker(client):
    """Third-Codex P1-3: the alignment speaker law is the ALIGNMENT'S
    OWN VP speaker (vocal_performance_revisions.speaker_subject_id —
    recovery parity), not the dialogue-line revision's speaker. A
    tampered VP whose speaker differs from the Performance subject
    must refuse candidate CREATION even when the line revision's
    speaker still matches."""
    pid, eid = await _subject(client, "X23")
    other = (await client.post("/projects",
                               json={"name": "X23-subj-home"})).json()
    from tests.m17b_seed import make_entity
    other_eid = await make_entity(client, other["id"])
    engine = client._transport.app.state.engine
    now = "2026-01-01T00:00:00.000Z"
    h64 = "c" * 64
    ids = {k: f"00000000-0000-4000-8000-000000000c{i:02d}"
           for i, k in enumerate(
               ["p2", "dl", "dlr", "vc", "vpr", "aid"], start=1)}
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:i, 'X23-B', :n, :n)"),
            {"i": ids["p2"], "n": now})
        await conn.execute(text(
            "INSERT INTO dialogue_lines (id, project_id, created_at) "
            "VALUES (:i, :p, :n)"),
            {"i": ids["dl"], "p": ids["p2"], "n": now})
        # the LINE revision's speaker still equals the subject; the VP
        # (the alignment's actual source) is tampered to another
        # speaker — the exact shape the old live check missed
        await conn.execute(text(
            "INSERT INTO dialogue_line_revisions (id, dialogue_line_id,"
            " revision_number, speaker_subject_id, language, wording, "
            "schema_version, spec_json, spec_hash, created_at) VALUES "
            "(:i, :l, 1, :sp, 'en', 'x23', 1, '{}', :sh, :n)"),
            {"i": ids["dlr"], "l": ids["dl"], "sp": eid,
             "sh": h64, "n": now})
        await conn.execute(text(
            "INSERT INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES "
            "(:h, :pa, 1, NULL, :n)"),
            {"h": h64, "pa": f"sha256/{h64[:2]}/{h64[2:4]}/{h64}",
             "n": now})
        await conn.execute(text(
            "INSERT INTO vocal_candidates (id, dialogue_line_revision_id,"
            " retained_audio_blob_hash, native_sample_rate_hz, "
            "retained_sample_count, trim_start_sample, "
            "trim_end_sample_exclusive, source_kind, "
            "provenance_schema_version, provenance_json, "
            "provenance_hash, created_at) VALUES "
            "(:i, :l, :h, 48000, 10, 0, 10, 'recorded', 1, '{}', "
            ":ph, :n)"),
            {"i": ids["vc"], "l": ids["dlr"], "h": h64, "ph": h64,
             "n": now})
        await conn.execute(text(
            "INSERT INTO vocal_performance_revisions (id, "
            "dialogue_line_revision_id, revision_number, "
            "speaker_subject_id, retained_audio_blob_hash, "
            "native_sample_rate_hz, retained_sample_count, "
            "trim_start_sample, trim_end_sample_exclusive, "
            "source_kind, provenance_schema_version, provenance_json, "
            "provenance_hash, adopted_candidate_id, adoption_id, "
            "adopted_by, adopted_at) VALUES "
            "(:i, :l, 1, :sp, :h, 48000, 10, 0, 10, 'recorded', 1, "
            "'{}', :ph, :vc, :ad, 'x23', :n)"),
            {"i": ids["vpr"], "l": ids["dlr"], "sp": other_eid,
             "h": h64, "ph": h64, "vc": ids["vc"],
             "ad": "00000000-0000-4000-8000-000000000c07", "n": now})
        await conn.execute(text(
            "INSERT INTO dialogue_alignments (id, "
            "vocal_performance_revision_id, analyzer_id, "
            "analyzer_version, model_identity, runtime_identity, "
            "parameters_sha256, alignment_schema_version, "
            "retained_blob_hash, retained_sha256, derivation_run_json, "
            "derivation_run_hash, derivation_run_identity, created_at)"
            " VALUES (:i, :v, 'x23-analyzer', '1', 'm', 'r', :ph, 1, "
            ":h, :h, '{}', :dh, :dh, :n)"),
            {"i": ids["aid"], "v": ids["vpr"], "ph": h64, "h": h64,
             "dh": "d" * 64, "n": now})
    from tests.m17b_seed import candidate_body
    body = candidate_body([channel(SMILE, [kf(0, 1, 0, kind="DERIVED",
                                               alignment=ids["aid"])])])
    r = await _post(client, eid, body)
    assert r.status_code in (403, 422), r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_ALIGNMENT_SUBJECT_MISMATCH", r.text
