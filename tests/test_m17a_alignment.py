"""M17A alignment evidence tests (frozen R5 matrices F01-F10)."""

from __future__ import annotations

import pytest

from tests.m17a_seed import make_entity, make_project, place_blob, \
    wave_bytes


async def _vp(client, frames=216000):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    rev = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    h = await place_blob(client, wave_bytes(48000, frames))
    cid = (await client.post(
        f"/dialogue-line-revisions/{rev['id']}/vocal-candidates", json={
            "retained_audio_blob_hash": h,
            "source_provenance": {"schema_version": 1,
                                  "source_kind": "recorded"}}
    )).json()["id"]
    vp = (await client.post(f"/vocal-candidates/{cid}/adopt",
                            json={"adopted_by": "d"})).json()
    return vp, h


def _alignment(vp_id, audio_hash, words, run_ts="2026-09-19T12:34:56.123456Z",
               analyzer="X", version="1.2.0"):
    return {
        "analyzer_id": analyzer, "analyzer_version": version,
        "model_identity": "Mx", "runtime_identity": "Rx",
        "parameters_sha256": "a" * 64,
        "alignment_document": {"schema_version": 1, "words": words,
                               "phonemes": [], "viseme_classes": []},
        "derivation_run": {
            "schema_version": 1, "run_timestamp_utc": run_ts,
            "host_context": "worker-7 (CPython 3.12.10, Windows x64)",
            "input_digest": {
                "vocal_performance_revision_id": vp_id,
                "retained_audio_blob_sha256": audio_hash}}}


@pytest.mark.asyncio
async def test_three_alignments_coexist_no_dedupe(client):
    vp, h = await _vp(client)
    words = [{"start_sample": 0, "end_sample_exclusive": 12000,
              "label": "You"}]
    body = _alignment(vp["id"], h, words)
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 201, r.text
    d1 = r.json()
    # F07: same basis + same bytes -> distinct row, same retained hash
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 201
    d1_same = r.json()
    assert d1_same["id"] != d1["id"]
    assert d1_same["retained_sha256"] == d1["retained_sha256"]
    # F08: same basis + different bytes -> distinct row, different hash
    body_v = _alignment(vp["id"], h, words=[
        {"start_sample": 0, "end_sample_exclusive": 6000, "label": "You"},
        {"start_sample": 6000, "end_sample_exclusive": 13000,
         "label": "weren't"}])
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body_v)
    d1_var = r.json()
    assert d1_var["id"] not in (d1["id"], d1_same["id"])
    assert d1_var["retained_sha256"] != d1["retained_sha256"]
    rows = (await client.get(
        f"/vocal-performance-revisions/{vp['id']}/alignments")).json()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_alignment_negatives(client):
    vp, h = await _vp(client, frames=96000)
    words = [{"start_sample": 0, "end_sample_exclusive": 12000,
              "label": "You"}]
    # F02 missing analyzer field
    body = _alignment(vp["id"], h, words)
    body["model_identity"] = ""
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    # F03 malformed parameter hash
    body = _alignment(vp["id"], h, words)
    body["parameters_sha256"] = "xyz"
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    # F04 entry interval outside the VP authoritative trim (default
    # full [0, 96000))
    body = _alignment(vp["id"], h, words=[
        {"start_sample": 0, "end_sample_exclusive": 96001,
         "label": "x"}])
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    # ALIGNMENT_SOURCE_MISMATCH: run digest names a different VP
    body = _alignment(vp["id"], h, words)
    body["derivation_run"]["input_digest"][
        "vocal_performance_revision_id"] = \
        "00000000-0000-4000-8000-0000000000ff"
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    # ALIGNMENT_PROVENANCE_INCOMPLETE: malformed timestamp
    body = _alignment(vp["id"], h, words, run_ts="2026-09-19 12:34:56")
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    # F01 missing VP
    body = _alignment("00000000-0000-4000-8000-0000000000ff", h, words)
    r = await client.post(
        "/vocal-performance-revisions/"
        "00000000-0000-4000-8000-0000000000ff/alignments", json=body)
    assert r.status_code == 404
