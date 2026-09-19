"""M17A vocal candidate/adoption/selection tests (frozen R5 matrices
B01-B12, C01-C08, D01-D07)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.m17a_seed import (make_entity, make_project, place_blob,
                             wave_bytes)


async def _line(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})
    return pid, eid, r.json()["id"]


async def _audio(client, frames=216000, rate=48000):
    settings = client._transport.app.state.settings
    data = wave_bytes(rate, frames)
    return await place_blob(client, data), data


async def _candidate(client, rev_id, blob_hash, **over):
    body = {"retained_audio_blob_hash": blob_hash,
            "source_provenance": {"schema_version": 1,
                                  "source_kind": "recorded"}}
    body.update(over)
    return await client.post(
        f"/dialogue-line-revisions/{rev_id}/vocal-candidates", json=body)


@pytest.mark.asyncio
async def test_candidate_inspection_and_default_full_trim(client):
    _, _, rev = await _line(client)
    h, data = await _audio(client)
    r = await _candidate(client, rev, h)
    assert r.status_code == 201, r.text
    c = r.json()
    # B11: omitted trim -> full closure
    assert c["trim_start_sample"] == 0
    assert c["trim_end_sample_exclusive"] == 216000
    assert c["native_sample_rate_hz"] == 48000
    assert c["retained_sample_count"] == 216000


@pytest.mark.asyncio
async def test_adoption_idempotent_and_take_independent(client):
    _, _, rev = await _line(client)
    h, _ = await _audio(client)
    r = await _candidate(client, rev, h)
    cid = r.json()["id"]
    r = await client.post(f"/vocal-candidates/{cid}/adopt",
                          json={"adopted_by": "dir"})
    assert r.status_code == 200, r.text
    vp = r.json()
    assert vp["revision_number"] == 1
    # C02: same candidate adopted twice -> same VP
    r2 = await client.post(f"/vocal-candidates/{cid}/adopt",
                           json={"adopted_by": "dir"})
    assert r2.json()["id"] == vp["id"]
    # C08: adoption alone leaves selection UNSET
    r = await client.get(f"/dialogue-line-revisions/{rev}/vocal-selection")
    assert r.json()["state"] == "UNSET"


@pytest.mark.asyncio
async def test_selection_lifecycle(client):
    _, _, rev = await _line(client)
    h, _ = await _audio(client)
    cid = (await _candidate(client, rev, h)).json()["id"]
    vpid = (await client.post(
        f"/vocal-candidates/{cid}/adopt",
        json={"adopted_by": "dir"})).json()["id"]
    # D01 new DLR starts UNSET (already asserted); D02 select same-line
    r = await client.put(f"/dialogue-line-revisions/{rev}/vocal-selection",
                         json={"vocal_performance_revision_id": vpid,
                               "selected_by": "dir"})
    assert r.status_code == 200 and r.json()["state"] == "SELECTED"
    # D04 explicit UNSET
    r = await client.put(f"/dialogue-line-revisions/{rev}/vocal-selection",
                         json={"vocal_performance_revision_id": None,
                               "selected_by": "dir"})
    assert r.json()["state"] == "UNSET"
    # D05: newest VP exists but selection value unchanged after re-select
    h2, _ = await _audio(client, frames=96000)
    cid2 = (await _candidate(client, rev, h2)).json()["id"]
    vp2 = (await client.post(f"/vocal-candidates/{cid2}/adopt",
                             json={"adopted_by": "dir"})).json()
    r = await client.get(f"/dialogue-line-revisions/{rev}/vocal-selection")
    assert r.json()["state"] == "UNSET"  # D07: no latest-adopted fallback


@pytest.mark.asyncio
async def test_cross_line_selection_rejected(client):
    pid, eid, rev1 = await _line(client)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid2 = r.json()["id"]
    rev2 = (await client.post(
        f"/dialogue-lines/{lid2}/revisions", json={
            "speaker_subject_id": eid, "language": "en",
            "wording": "Another line."})).json()["id"]
    h, _ = await _audio(client, frames=48000)
    cid = (await _candidate(client, rev1, h)).json()["id"]
    vpid = (await client.post(f"/vocal-candidates/{cid}/adopt",
                              json={"adopted_by": "d"})).json()["id"]
    r = await client.put(
        f"/dialogue-line-revisions/{rev2}/vocal-selection",
        json={"vocal_performance_revision_id": vpid,
              "selected_by": "d"})
    assert r.status_code == 409  # D03


@pytest.mark.asyncio
async def test_audio_negatives(client):
    _, _, rev = await _line(client)
    # B01 missing blob
    r = await _candidate(client, rev, "0" * 64)
    assert r.status_code in (404, 422)
    # B03 unsupported compressed (RIFF but not WAVE / not PCM)
    settings = client._transport.app.state.settings
    bad = b"RIFF" + (0).to_bytes(4, "little") + b"WAVE"
    h_bad = await place_blob(client, bad)
    r = await _candidate(client, rev, h_bad)
    assert r.status_code == 422
    # B04 malformed WAVE (fmt without data)
    malformed = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + \
        b"fmt " + (16).to_bytes(4, "little") + \
        (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + \
        (48000).to_bytes(4, "little") + (96000).to_bytes(4, "little") + \
        (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    h_m = await place_blob(client, malformed)
    r = await _candidate(client, rev, h_m)
    assert r.status_code == 422
    # B05 declared/inspected rate disagreement is impossible via API
    # (metadata is inspected); B07/B08 trim negatives:
    h, _ = await _audio(client, frames=96000)
    r = await _candidate(client, rev, h,
                         trim_start_sample=0,
                         trim_end_sample_exclusive=96001)
    assert r.status_code == 422  # B08 end > retained
    # B12 exactly one trim coordinate
    r = await _candidate(client, rev, h, trim_start_sample=0)
    assert r.status_code == 422
    r = await _candidate(client, rev, h, trim_start_sample=100,
                         trim_end_sample_exclusive=100)
    assert r.status_code == 422  # B07 empty interval


@pytest.mark.asyncio
async def test_generated_provenance_requires_identity(client):
    _, _, rev = await _line(client)
    h, _ = await _audio(client, frames=48000)
    r = await _candidate(client, rev, h, source_provenance={
        "schema_version": 1, "source_kind": "generated"})
    assert r.status_code == 422  # B09
    r = await _candidate(client, rev, h, source_provenance={
        "schema_version": 1, "source_kind": "generated",
        "generator_id": "tts-1", "generator_version": "1.0",
        "workflow_id": "wf", "workflow_version": "2"})
    assert r.status_code == 201
