"""M16 working-event identity/provenance proofs (R6 M16:IDENTITY)."""

from __future__ import annotations

from sqlalchemy import text

from soloring.api.schemas.shots import ShotCreate
from soloring.continuity.intra_shot_canonical import event_storage, proposal_storage
from soloring.domain import shots as shot_svc
from soloring.domain.canonical import canonical_hash


async def _seed(client, factory, *, duration=5000):
    async with factory() as s:
        from soloring.api.schemas.projects import ProjectCreate
        from soloring.domain import projects as project_svc
        pid = (await project_svc.create_project(s, ProjectCreate(name="M16"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="subject", duration_ms=duration))).id
    er = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "Eva"})
    assert er.status_code == 201, er.text
    eid = er.json()["id"]
    rr = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    assert rr.status_code == 201, rr.text
    ar = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": rr.json()["id"], "expected_approved_revision_id": None})
    assert ar.status_code == 200, ar.text
    dr = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
    assert dr.status_code == 200, dr.text
    fr = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "forehead_cut", "kind": "injury", "value_type": "enum",
              "name": "Forehead cut", "enum_values": ["fresh", "healing"]})
    assert fr.status_code == 201, fr.text
    return pid, sid, fr.json()["id"]


def _body(fid, *, time=1000, ordinal=0, persistence="transient"):
    return {
        "time_ms": time,
        "ordinal": ordinal,
        "target": {"kind": "entity_feature", "id": fid},
        "before": {"present": False},
        "after": {"present": True, "value": "fresh",
                  "value_hash": canonical_hash("fresh")},
        "persistence_mode": persistence,
    }


async def test_identity_01(client, factory):
    """PATCH preserves event UUID while semantic changes replace event_hash."""
    _, sid, fid = await _seed(client, factory)
    created = await client.post(f"/shots/{sid}/intra-shot/events", json=_body(fid))
    assert created.status_code == 201, created.text
    before = created.json()
    patched = await client.patch(
        f"/intra-shot/events/{before['id']}", json={"ordinal": 1})
    assert patched.status_code == 200, patched.text
    after = patched.json()
    assert after["id"] == before["id"]
    assert after["event_hash"] != before["event_hash"]


def test_identity_02():
    """event_hash covers only the frozen semantic event root, never audit provenance."""
    fid = "11111111-1111-4111-8111-111111111111"
    doc, raw, digest = event_storage(
        time_ms=1000, ordinal=0,
        target={"kind": "entity_feature", "id": fid},
        before={"present": False},
        after={"present": True, "value": "fresh",
               "value_hash": canonical_hash("fresh")},
        persistence_mode="transient")
    assert digest == canonical_hash(doc)
    assert "source_kind" not in raw
    assert "source_proposal_id" not in raw
    assert "event_id" not in raw
    assert "shot_id" not in raw


async def test_identity_03(client, factory):
    """Semantic PATCH of proposal-adopted current authority becomes authored/null."""
    _, sid, fid = await _seed(client, factory)
    from soloring.domain import revisions as revision_svc
    async with factory() as session:
        source_revision = await revision_svc.capture_revision(session, sid)

    candidate = _body(fid)
    proposal_doc, proposal_json, proposal_hash = proposal_storage(
        candidate_event={k: candidate[k] for k in
                         ("time_ms", "ordinal", "target", "before", "after")},
        persistence_suggestion="transient")
    engine = client._transport.app.state.engine
    proposal_id = "22222222-2222-4222-8222-222222222222"
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO shot_intra_shot_event_proposals "
            "(id,shot_id,source_kind,source_shot_revision_id,"
            "source_shot_revision_hash,source_generation_id,source_take_id,"
            "proposer_kind,analyzer_id,analyzer_version,analyzer_parameters_hash,"
            "proposal_json,proposal_hash,created_at) VALUES "
            "(:id,:s,'imported',:r,:rh,NULL,NULL,'human',NULL,NULL,NULL,:pj,:ph,"
            "'2026-01-01T00:00:00.000Z')"),
            {"id": proposal_id, "s": sid, "r": source_revision.id,
             "rh": source_revision.snapshot_hash, "pj": proposal_json,
             "ph": proposal_hash})

    from soloring.api.schemas.intra_shot import IntraShotEventCreate
    from soloring.continuity import intra_shot_service
    async with factory() as session:
        created = await intra_shot_service.create_event(
            session, sid, IntraShotEventCreate(**candidate),
            source_kind="proposal_adoption", source_proposal_id=proposal_id)
    assert created["source_kind"] == "proposal_adoption"
    assert created["source_proposal_id"] == proposal_id

    patched = await client.patch(
        f"/intra-shot/events/{created['id']}", json={"ordinal": 1})
    assert patched.status_code == 200, patched.text
    assert patched.json()["source_kind"] == "authored"
    assert patched.json()["source_proposal_id"] is None

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT source_kind,source_proposal_id FROM shot_intra_shot_events "
            "WHERE id=:e"), {"e": created["id"]})).one()
    assert tuple(row) == ("authored", None)
    assert proposal_doc["schema_version"] == 1
