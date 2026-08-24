"""M10B API-level smoke: routes registered, shapes honored, fencing intact."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


async def _seed(factory):
    pid, eid, rid = (str(uuid.uuid4()) for _ in range(3))
    async with factory() as session:
        async with session.begin():
            await session.execute(text(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (:p, 'P', 't','t')"), {"p": pid})
            await session.execute(text(
                "INSERT INTO creative_entities (id, project_id, kind, name,"
                " created_at, updated_at) VALUES (:e,:p,'location','L','t','t')"),
                {"e": eid, "p": pid})
            await session.execute(text(
                "INSERT INTO entity_revisions (id, entity_id, revision_number,"
                " schema_version, spec_hash, created_at) VALUES "
                "(:r,:e,1,1,:h,'t')"), {"r": rid, "e": eid, "h": "ab" * 32})
    return pid, eid, rid


async def test_world_api_end_to_end(client, factory):
    pid, eid, rid = await _seed(factory)
    r = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "api-lobby", "name": "Lobby", "requirement": "optional",
        "location_entity_id": eid})
    assert r.status_code == 201, r.text
    world_id = r.json()["id"]
    r = await client.post(f"/spatial-worlds/{world_id}/states", json={
        "location_entity_revision_id": rid})
    assert r.status_code == 201, r.text
    state_id = r.json()["id"]
    r = await client.post(f"/spatial-worlds/{world_id}/frames", json={
        "key": "origin", "name": "Origin"})
    assert r.status_code == 201, r.text
    frame_id = r.json()["id"]
    r = await client.put(
        f"/spatial-world-states/{state_id}/frames/{frame_id}", json={
            "translation_mm": [0, 0, 0], "rotation_udeg": [0, 0, 0]})
    assert r.status_code == 204, r.text
    r = await client.post(f"/spatial-world-states/{state_id}/revisions")
    assert r.status_code == 201, r.text
    rev = r.json()
    r = await client.put(f"/spatial-world-states/{state_id}/approval", json={
        "revision_id": rev["id"], "expected_approved_revision_id": None})
    assert r.status_code == 200 and r.json()["approved_revision_id"] == rev["id"]
    # unknown-field rejection
    r = await client.post(f"/projects/{pid}/spatial-worlds", json={
        "key": "x", "name": "X", "requirement": "optional",
        "location_entity_id": eid, "surprise": 1})
    assert r.status_code == 422
