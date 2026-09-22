"""M17A compatibility/readiness tests (frozen R5 matrix G01-G07)."""

from __future__ import annotations

import pytest

from tests.m17a_seed import make_entity, make_project, place_blob, \
    wave_bytes


async def _world(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    rev1 = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    h = await place_blob(client, wave_bytes(48000, 48000))
    cid = (await client.post(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-candidates", json={
            "retained_audio_blob_hash": h,
            "source_provenance": {"schema_version": 1,
                                  "source_kind": "recorded"}}
    )).json()["id"]
    vp = (await client.post(f"/vocal-candidates/{cid}/adopt",
                            json={"adopted_by": "d"})).json()
    return pid, eid, lid, rev1, vp


async def _compat(client, vpid, target_rev):
    return await client.post(
        f"/vocal-performance-revisions/{vpid}/compatibility/"
        f"dialogue-line-revisions/{target_rev}")


@pytest.mark.asyncio
async def test_g01_same_revision_compatible_as_is(client):
    _, _, _, rev1, vp = await _world(client)
    r = await _compat(client, vp["id"], rev1["id"])
    assert r.status_code == 200
    assert r.json()["verdict"] == "COMPATIBLE_AS_IS"


@pytest.mark.asyncio
async def test_g02_identical_semantics_new_revision_requires_review(
        client):
    # an identical semantic triple on a DIFFERENT line is a distinct
    # revision carrying the same speaker/wording/language
    pid, eid, lid, rev1, vp = await _world(client)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid2 = r.json()["id"]
    rev2 = (await client.post(f"/dialogue-lines/{lid2}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    assert rev2["id"] != rev1["id"]
    r = await _compat(client, vp["id"], rev2["id"])
    assert r.status_code == 200
    assert r.json()["verdict"] == "REQUIRES_REVIEW"


@pytest.mark.asyncio
async def test_g03_g05_incompatible_on_differences(client):
    pid, eid, lid, rev1, vp = await _world(client)
    # wording differs
    rw = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "Different words."})).json()
    r = await _compat(client, vp["id"], rw["id"])
    assert r.json()["verdict"] == "INCOMPATIBLE"
    # language differs
    rl = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "fr",
        "wording": "You weren't supposed to see this."})).json()
    r = await _compat(client, vp["id"], rl["id"])
    assert r.json()["verdict"] == "INCOMPATIBLE"
    # speaker differs
    eid2 = await make_entity(client, pid, "Other")
    rs = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid2, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    r = await _compat(client, vp["id"], rs["id"])
    assert r.json()["verdict"] == "INCOMPATIBLE"


@pytest.mark.asyncio
async def test_g07_stale_does_not_mutate(client):
    from tests.m17a_seed import make_shot
    pid, eid, lid, rev1, vp = await _world(client)
    await client.put(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp["id"],
              "selected_by": "d"})
    shot = await make_shot(client, pid, 2000)
    r = await client.put(f"/shots/{shot}/vocal-segments/0", json={
        "vocal_performance_revision_id": vp["id"],
        "source_start_sample": 0, "source_end_sample_exclusive": 48000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1}})
    assert r.status_code == 200
    before = (await client.get(f"/shots/{shot}/vocal-segments"
                               )).json()[0]
    # adopt a second VP and advance the selection explicitly
    h2 = await place_blob(client, wave_bytes(48000, 48000))
    cid2 = (await client.post(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-candidates",
        json={"retained_audio_blob_hash": h2,
              "source_provenance": {"schema_version": 1,
                                    "source_kind": "adr"}}
    )).json()["id"]
    vp2 = (await client.post(f"/vocal-candidates/{cid2}/adopt",
                             json={"adopted_by": "d"})).json()
    await client.put(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp2["id"],
              "selected_by": "d"})
    after = (await client.get(f"/shots/{shot}/vocal-segments")).json()[0]
    assert after["mapping_hash"] == before["mapping_hash"]
    assert after["vocal_performance_revision_id"] == vp["id"]
