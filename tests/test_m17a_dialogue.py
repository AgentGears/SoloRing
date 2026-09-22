"""M17A dialogue identity tests (frozen R5 matrix A01-A07)."""

from __future__ import annotations

import pytest

from tests.m17a_seed import make_entity, make_project


@pytest.mark.asyncio
async def test_line_and_revision_lifecycle(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    assert r.status_code == 201, r.text
    line_id = r.json()["id"]
    r = await client.post(f"/dialogue-lines/{line_id}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["revision_number"] == 1 and len(rev["spec_hash"]) == 64
    # A06: identical semantic revision converges by spec hash
    r2 = await client.post(f"/dialogue-lines/{line_id}/revisions", json={
        "speaker_subject_id": eid, "language": "EN",
        "wording": "You weren't supposed to see this."})
    assert r2.status_code == 201
    assert r2.json()["id"] == rev["id"]
    # a different wording is a NEW revision
    r3 = await client.post(f"/dialogue-lines/{line_id}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You were never supposed to see this."})
    assert r3.json()["revision_number"] == 2


@pytest.mark.asyncio
async def test_list_route_and_isolation(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en", "wording": "one"})
    await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en", "wording": "two"})
    r = await client.get(f"/projects/{pid}/dialogue-lines")
    assert r.status_code == 200 and len(r.json()["lines"]) == 1
    r = await client.get(f"/dialogue-lines/{lid}/revisions")
    assert [x["revision_number"] for x in r.json()] == [1, 2]


@pytest.mark.asyncio
async def test_negatives_A01_A04(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    other_pid = await make_project(client)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    # A01 empty wording
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en", "wording": "  "})
    assert r.status_code == 422
    # A02 invalid language grammar
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "not a tag!",
        "wording": "x"})
    assert r.status_code == 422
    # A03 speaker from another project
    other_eid = await make_entity(client, other_pid, "Other")
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": other_eid, "language": "en",
        "wording": "x"})
    assert r.status_code == 422
    # A04 nonexistent speaker
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": "00000000-0000-4000-8000-0000000000ff",
        "language": "en", "wording": "x"})
    assert r.status_code == 404
    # A05: no mutation surface exists (no PUT/PATCH/DELETE routes)
    r = await client.put(f"/dialogue-lines/{lid}/revisions", json={})
    assert r.status_code == 405
