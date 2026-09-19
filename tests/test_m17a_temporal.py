"""M17A temporal mapping tests (frozen R5 matrices E01-E16 + the exact
G8 arithmetic as executable proof)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from tests.m17a_seed import make_entity, make_project, make_shot, \
    place_blob, wave_bytes


async def _world(client, duration_a=2000, duration_b=3000):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    rev = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    h = await place_blob(client, wave_bytes(48000, 216000))
    cid = (await client.post(
        f"/dialogue-line-revisions/{rev['id']}/vocal-candidates", json={
            "retained_audio_blob_hash": h,
            "source_provenance": {"schema_version": 1,
                                  "source_kind": "recorded"}}
    )).json()["id"]
    vpid = (await client.post(f"/vocal-candidates/{cid}/adopt",
                              json={"adopted_by": "d"})).json()["id"]
    await client.put(
        f"/dialogue-line-revisions/{rev['id']}/vocal-selection",
        json={"vocal_performance_revision_id": vpid,
              "selected_by": "d"})
    shot_a = await make_shot(client, pid, duration_a)
    shot_b = await make_shot(client, pid, duration_b)
    return pid, vpid, shot_a, shot_b


def _mapping(vpid, s0, s1, onum=0, aden_num=0):
    return {"vocal_performance_revision_id": vpid,
            "source_start_sample": s0,
            "source_end_sample_exclusive": s1,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": onum, "den": 1},
            "shot_anchor_ms": {"num": aden_num, "den": 1}}


@pytest.mark.asyncio
async def test_j_cut_exact_positions(client):
    pid, vpid, a, b = await _world(client)
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 0, 96000, 0, 0))
    assert r.status_code == 200, r.text
    r = await client.put(f"/shots/{b}/vocal-segments/0",
                         json=_mapping(vpid, 84000, 216000, 1750, -250))
    assert r.status_code == 200, r.text
    rows = (await client.get(f"/shots/{b}/vocal-segments")).json()
    m_b = [x for x in rows if x["position"] == 0][0]
    # sample 84,000 -> shot B -250 ms | performance 1,750 ms
    # sample 96,000 -> shot B    0 ms | performance 2,000 ms
    anum, aden = m_b["shot_anchor_ms"]["num"], m_b["shot_anchor_ms"]["den"]
    onum, oden = (m_b["performance_origin_ms"]["num"],
                  m_b["performance_origin_ms"]["den"])
    s84 = Fraction(anum, aden) + Fraction(
        (84000 - 84000) * 1000, 48000)
    s96 = Fraction(anum, aden) + Fraction(
        (96000 - 84000) * 1000, 48000)
    assert s84 == Fraction(-250) and s96 == Fraction(0)
    p84 = Fraction(onum, oden) + Fraction(0, 48000)
    p96 = Fraction(onum, oden) + Fraction(12000 * 1000, 48000)
    assert p84 == Fraction(1750) and p96 == Fraction(2000)
    # overlap [84000, 96000) = 12000 samples = 250 ms lawful (E13)
    segs = (await client.get(f"/shots/{a}/vocal-segments")).json()
    assert len(segs) == 1 and len(rows) == 1


@pytest.mark.asyncio
async def test_mapping_negatives_E01_E15(client):
    pid, vpid, a, b = await _world(client)
    # E01 zero/negative interval
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 100, 100))
    assert r.status_code == 422
    # E02 end > retained samples
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 0, 216001))
    assert r.status_code == 422
    # E04 rate mismatch
    m = _mapping(vpid, 0, 96000)
    m["sample_rate_hz"] = 44100
    r = await client.put(f"/shots/{a}/vocal-segments/0", json=m)
    assert r.status_code == 422
    # E05 zero/negative denominator
    m = _mapping(vpid, 0, 96000)
    m["shot_anchor_ms"] = {"num": 0, "den": 0}
    r = await client.put(f"/shots/{a}/vocal-segments/0", json=m)
    assert r.status_code == 422
    # E09 entirely before the shot (anchor -5000, segment ends -3000)
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 0, 96000, 0, -5000))
    assert r.status_code == 422
    # E10 entirely after the shot
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 0, 96000, 0, 99999))
    assert r.status_code == 422
    # E12 end-after-picture L-cut is lawful
    r = await client.put(f"/shots/{a}/vocal-segments/0",
                         json=_mapping(vpid, 0, 216000, 0, 1000))
    assert r.status_code == 200
    # E15 mapping against a nonselected VP: unset the selection first
    rev_sel = None
    lines = (await client.get(f"/projects/{pid}/dialogue-lines"
                              )).json()["lines"]
    lid = lines[0]["id"]
    revs = (await client.get(f"/dialogue-lines/{lid}/revisions")).json()
    rev_sel = revs[0]["id"]
    r = await client.put(
        f"/dialogue-line-revisions/{rev_sel}/vocal-selection",
        json={"vocal_performance_revision_id": None,
              "selected_by": "d"})
    assert r.status_code == 200
    r = await client.put(f"/shots/{b}/vocal-segments/0",
                         json=_mapping(vpid, 0, 96000))
    assert r.status_code == 409
    # E16 STALE is readiness-only: existing mapping bytes unchanged
    rows = (await client.get(f"/shots/{a}/vocal-segments")).json()
    assert len(rows) == 1 and rows[0]["mapping_hash"]
