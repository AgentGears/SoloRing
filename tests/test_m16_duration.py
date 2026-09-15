"""M16 conditional-duration proofs (frozen R6 M16:DURATION:01-05)."""

from __future__ import annotations

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.domain.canonical import canonical_hash


async def _shot(factory, duration):
    async with factory() as s:
        pid = (await project_svc.create_project(s, ProjectCreate(name="M16 duration"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="x", duration_ms=duration))).id
    return pid, sid


async def _target(client, factory, duration):
    pid, sid = await _shot(factory, duration)
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
              "name": "Cut", "enum_values": ["fresh", "healing"]})
    assert f.status_code == 201, f.text
    return sid, f.json()["id"]


def _event(fid, t=1000):
    return {
        "time_ms": t, "ordinal": 0,
        "target": {"kind": "entity_feature", "id": fid},
        "before": {"present": False},
        "after": {"present": True, "value": "fresh",
                  "value_hash": canonical_hash("fresh")},
        "persistence_mode": "transient",
    }


async def _empty_result(client, sid):
    from soloring.continuity import intra_shot_service
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        shot = await intra_shot_service._load_shot(conn, sid)
        return await intra_shot_service.validate_prospective_event_set(conn, shot, [])


async def test_duration_01(client, factory):
    """Event-free Shot with NULL duration remains legal and has no M16 event block."""
    _, sid = await _shot(factory, None)
    out = await _empty_result(client, sid)
    assert out == {"events": [], "terminal_states": {}, "event_set_hash": None}


async def test_duration_02(client, factory):
    """Event-free Shot with zero duration remains legal and has no M16 event block."""
    _, sid = await _shot(factory, 0)
    out = await _empty_result(client, sid)
    assert out["events"] == [] and out["event_set_hash"] is None


async def test_duration_03(client, factory):
    """Event creation against NULL/zero duration is rejected before storage."""
    for duration in (None, 0):
        sid, fid = await _target(client, factory, duration)
        r = await client.post(f"/shots/{sid}/intra-shot/events", json=_event(fid, 1))
        assert r.status_code == 409, r.text
        assert "INTRA_SHOT_DURATION_REQUIRED" in r.text
        engine = client._transport.app.state.engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            n = (await conn.execute(text(
                "SELECT COUNT(*) FROM shot_intra_shot_events WHERE shot_id=:s"),
                {"s": sid})).scalar_one()
        assert n == 0


async def test_duration_04(client, factory):
    """Duration PATCH cannot become NULL/zero or <= max active event time."""
    sid, fid = await _target(client, factory, 5000)
    c = await client.post(f"/shots/{sid}/intra-shot/events", json=_event(fid, 1000))
    assert c.status_code == 201, c.text
    for bad in (None, 0, 1000, 999):
        r = await client.patch(f"/shots/{sid}", json={"duration_ms": bad})
        assert r.status_code == 409, (bad, r.text)
    ok = await client.patch(f"/shots/{sid}", json={"duration_ms": 1001})
    assert ok.status_code == 200, ok.text
    assert ok.json()["duration_ms"] == 1001


async def test_duration_05(client, factory):
    """Positive duration plus strictly interior event is structurally valid."""
    sid, fid = await _target(client, factory, 5000)
    r = await client.post(f"/shots/{sid}/intra-shot/events", json=_event(fid, 4999))
    assert r.status_code == 201, r.text
    assert r.json()["time_ms"] == 4999
