"""M16-A authoritative event lifecycle/prospective-set proofs."""

from __future__ import annotations

from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.domain.canonical import canonical_hash


async def _seed(client, factory):
    async with factory() as s:
        pid = (await project_svc.create_project(s, ProjectCreate(name="M16 events"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="x", duration_ms=5000))).id
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "Eva"})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    assert r.status_code == 201, r.text
    a = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"], "expected_approved_revision_id": None})
    assert a.status_code == 200, a.text
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
    assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing", "scarred"]})
    assert f.status_code == 201, f.text
    return pid, sid, eid, f.json()["id"]


def _state(value=None):
    if value is None:
        return {"present": False}
    return {"present": True, "value": value, "value_hash": canonical_hash(value)}


def _event(fid, t, before, after, *, ordinal=0, persistence="transient"):
    return {
        "time_ms": t, "ordinal": ordinal,
        "target": {"kind": "entity_feature", "id": fid},
        "before": _state(before), "after": _state(after),
        "persistence_mode": persistence,
    }


async def test_event_crud_soft_delete(client, factory):
    """POST/PATCH/DELETE preserve UUID and DELETE tombstones current authority."""
    _, sid, _, fid = await _seed(client, factory)
    c = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000, None, "fresh"))
    assert c.status_code == 201, c.text
    event = c.json()
    p = await client.patch(
        f"/intra-shot/events/{event['id']}", json={"time_ms": 1100})
    assert p.status_code == 200, p.text
    assert p.json()["id"] == event["id"]
    d = await client.delete(f"/intra-shot/events/{event['id']}")
    assert d.status_code == 204, d.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT deleted_at FROM shot_intra_shot_events WHERE id=:e"),
            {"e": event["id"]})).one()
    assert row.deleted_at is not None


async def test_whole_set_patch_rejects_later_before_drift(client, factory):
    """Editing an earlier event cannot silently falsify a later before-state."""
    _, sid, _, fid = await _seed(client, factory)
    first = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000, None, "fresh"))
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 2000, "fresh", "healing"))
    assert second.status_code == 201, second.text
    bad = await client.patch(
        f"/intra-shot/events/{first.json()['id']}",
        json={"after": _state("scarred")})
    assert bad.status_code == 409, bad.text
    assert "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH" in bad.text


async def test_whole_set_delete_rejects_orphaned_before(client, factory):
    """Deleting an earlier event rejects if the remaining chain becomes false."""
    _, sid, _, fid = await _seed(client, factory)
    first = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000, None, "fresh"))
    second = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 2000, "fresh", "healing"))
    assert first.status_code == second.status_code == 201
    bad = await client.delete(f"/intra-shot/events/{first.json()['id']}")
    assert bad.status_code == 409, bad.text
    assert "INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH" in bad.text


async def test_require_handoff_must_remain_terminal(client, factory):
    """A later same-target event cannot strand an earlier persistent marker."""
    _, sid, _, fid = await _seed(client, factory)
    first = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=_event(fid, 1000, None, "fresh", persistence="require_handoff"))
    assert first.status_code == 201, first.text
    later = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 2000, "fresh", "healing"))
    assert later.status_code == 409, later.text
    assert "INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL" in later.text


async def test_active_coordinate_conflict_is_domain_conflict(client, factory):
    _, sid, _, fid = await _seed(client, factory)
    first = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000, None, "fresh"))
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000, "fresh", "healing"))
    assert second.status_code == 409, second.text
    assert "INTRA_SHOT_EVENT_COORDINATE_CONFLICT" in second.text


async def test_target_must_be_explicit_shot_dependency(client, factory):
    pid, sid, _, _ = await _seed(client, factory)
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": "character", "name": "Other"})
    assert e.status_code == 201
    eid = e.json()["id"]
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "other", "kind": "injury", "value_type": "enum",
              "name": "Other", "enum_values": ["fresh"]})
    assert f.status_code == 201, f.text
    bad = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=_event(f.json()["id"], 1000, None, "fresh"))
    assert bad.status_code == 409, bad.text
    assert "INTRA_SHOT_TARGET_INVALID" in bad.text


async def test_strict_event_request_rejects_extra_and_coerced_integer(client, factory):
    _, sid, _, fid = await _seed(client, factory)
    body = _event(fid, 1000, None, "fresh")
    body["time_ms"] = "1000"
    r = await client.post(f"/shots/{sid}/intra-shot/events", json=body)
    assert r.status_code == 422, r.text
    body = _event(fid, 1000, None, "fresh")
    body["unexpected"] = True
    r = await client.post(f"/shots/{sid}/intra-shot/events", json=body)
    assert r.status_code == 422, r.text
