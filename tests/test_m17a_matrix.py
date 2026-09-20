"""M17A negative/edge matrix completion (source-review correction round,
finding 9). Every cell the frozen plan marks MANDATORY that the first
implementation did not mechanically prove: C03 true concurrency, A04
tombstoned speaker, B02 corrupt physical Blob, B06 negative trim, E03
outside-trim alignment, E06 non-canonical rational, E07 i64 overflow,
E08 missing/zero Shot duration, E14 simultaneous speaker positions,
E16 OBSERVABLE STALE readiness, F06 retained Blob/hash disagreement,
F09 missing alignment bytes during recovery, the exact-wording and
closed-schema laws, the same-timestamp pagination tie-breaker, typed
durable error codes, the same-run/different-bytes conflict, and
fractional-denominator restore verification.
"""

from __future__ import annotations

import asyncio
import json
import struct

import pytest
from sqlalchemy import text

from tests.m17a_seed import (make_entity, make_project, make_shot,
                             place_blob, stamp_alembic, wave_bytes)


# ---------------------------------------------------------------- helpers

async def _line(client, wording="You weren't supposed to see this.",
                language="en", speaker=None):
    pid = await make_project(client)
    eid = speaker or await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": language,
        "wording": wording})
    return pid, eid, lid, r


async def _candidate(client, pid, eid, lid, blob_hash, **over):
    rev = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    body = {"retained_audio_blob_hash": blob_hash,
            "source_provenance": {"schema_version": 1,
                                  "source_kind": "recorded"}}
    body.update(over)
    r = await client.post(
        f"/dialogue-line-revisions/{rev['id']}/vocal-candidates", json=body)
    return rev, r


async def _selected_vp(client, frames=216000, rate=48000, wording=None):
    """A line with ONE adopted + explicitly selected VP."""
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    _, r = await _candidate(client, pid, eid, lid,
                            await place_blob(client, wave_bytes(rate,
                                                               frames)))
    assert r.status_code == 201, r.text
    c = r.json()
    vp = (await client.post(f"/vocal-candidates/{c['id']}/adopt",
                            json={"adopted_by": "director"})).json()
    r = await client.put(
        f"/dialogue-line-revisions/{vp['dialogue_line_revision_id']}"
        "/vocal-selection",
        json={"vocal_performance_revision_id": vp["id"],
              "selected_by": "director"})
    assert r.status_code == 200, r.text
    return pid, eid, lid, vp


def _al(vpr_id, audio_hash, words, run_ts="2026-09-20T12:00:00.000000Z"):
    return {"analyzer_id": "X", "analyzer_version": "1.2.0",
            "model_identity": "Mx", "runtime_identity": "Rx",
            "parameters_sha256": "a" * 64,
            "alignment_document": {"schema_version": 1, "words": words,
                                   "phonemes": [], "viseme_classes": []},
            "derivation_run": {
                "schema_version": 1, "run_timestamp_utc": run_ts,
                "host_context": "worker-7",
                "input_digest": {
                    "vocal_performance_revision_id": vpr_id,
                    "retained_audio_blob_sha256": audio_hash}}}


async def _map(client, shot_id, position, vpr_id, *, s=0, e=96000,
               rate=48000, pnum=0, pden=1, anum=0, aden=1):
    return await client.put(f"/shots/{shot_id}/vocal-segments/{position}",
                            json={"vocal_performance_revision_id": vpr_id,
                                  "source_start_sample": s,
                                  "source_end_sample_exclusive": e,
                                  "sample_rate_hz": rate,
                                  "performance_origin_ms": {"num": pnum,
                                                            "den": pden},
                                  "shot_anchor_ms": {"num": anum,
                                                     "den": aden}})


# ------------------------------------------------- A04 tombstoned speaker

@pytest.mark.asyncio
async def test_a04_tombstoned_speaker_rejected(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.delete(f"/entities/{eid}")
    assert r.status_code in (200, 204), r.text
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    r = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "A tombstoned speaker must not author revisions."})
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "SPEAKER_DELETED"


# ------------------------------------- exact wording / language grammar

@pytest.mark.asyncio
async def test_exact_wording_preserved_not_trimmed(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    r1 = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "  padded wording  "})
    assert r1.status_code == 201, r1.text
    assert r1.json()["wording"] == "  padded wording  "
    r2 = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "padded wording"})
    assert r2.status_code == 201, r2.text
    assert r2.json()["spec_hash"] != r1.json()["spec_hash"], (
        "whitespace differences are DISTINCT authority revisions")
    r3 = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": " en ",
        "wording": "x"})
    assert r3.status_code == 422
    assert r3.json()["error_code"] == "INVALID_LANGUAGE_TAG"
    r4 = await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "w" * 25000})
    assert r4.status_code == 201, r4.text  # no unfrozen length cap
    assert r4.json()["wording"] == "w" * 25000


# ------------------------------------------------------- B02 corrupt blob

@pytest.mark.asyncio
async def test_b02_corrupt_physical_blob_rejected(client):
    pid, eid, lid = None, None, None
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    h = await place_blob(client, wave_bytes(48000, 48000))
    settings = client._transport.app.state.settings
    target = (settings.blob_dir / "sha256" / h[:2] / h[2:4] / h)
    target.write_bytes(b"corrupted physical bytes")
    _, r = await _candidate(client, pid, eid, lid, h)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "BLOB_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_blob_not_found_is_typed(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    _, r = await _candidate(client, pid, eid, lid, "b" * 64)
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "BLOB_NOT_FOUND"


# ---------------------------------------------- typed audio rejections

@pytest.mark.asyncio
async def test_unsupported_media_and_invalid_audio_bytes_typed(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    h = await place_blob(client, b"ID3 not a wave at all..............")
    _, r = await _candidate(client, pid, eid, lid, h)
    assert r.status_code == 422
    assert r.json()["error_code"] == "UNSUPPORTED_VOCAL_MEDIA"

    good = bytearray(wave_bytes(48000, 48000))
    # break the RIFF container size (declared size += 4)
    struct.pack_into("<I", good, 4, len(good) - 8 + 4)
    h2 = await place_blob(client, bytes(good))
    _, r = await _candidate(client, pid, eid, lid, h2)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_AUDIO_BYTES"

    bad_align = bytearray(wave_bytes(48000, 48000))
    struct.pack_into("<H", bad_align, 32, 4)  # block_align != ch*bits/8
    h3 = await place_blob(client, bytes(bad_align))
    _, r = await _candidate(client, pid, eid, lid, h3)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_AUDIO_BYTES"


# ----------------------------------------------------------- B06 trim

@pytest.mark.asyncio
async def test_b06_negative_and_inverted_trim(client):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    for ts, te in ((-1, 48000), (24000, 24000), (0, 48001), (30000, 100)):
        _, r = await _candidate(client, pid, eid, lid, h,
                                trim_start_sample=ts,
                                trim_end_sample_exclusive=te)
        assert r.status_code == 422, (ts, te, r.text)
        assert r.json()["error_code"] == "INVALID_AUDIO_TRIM"


# ------------------------------------------------ closed-schema negatives

@pytest.mark.asyncio
async def test_provenance_closed_schema_negatives(client):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    _, r = await _candidate(client, pid, eid, lid, h)
    assert r.status_code == 201  # control: clean recorded provenance
    _, r = await _candidate(client, pid, eid, lid, h, source_provenance={
        "schema_version": 1, "source_kind": "recorded",
        "unexpected": "field"})
    assert r.status_code == 422, r.text  # pydantic extra=forbid
    _, r = await _candidate(client, pid, eid, lid, h, source_provenance={
        "schema_version": 2, "source_kind": "recorded"})
    assert r.status_code == 422
    _, r = await _candidate(client, pid, eid, lid, h, source_provenance={
        "schema_version": 1, "source_kind": "recorded",
        "generator_id": "g"})
    assert r.status_code == 422  # recorded may not carry generated fields


@pytest.mark.asyncio
async def test_derivation_run_closed_schema_negatives(client):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    words = [{"start_sample": 0, "end_sample_exclusive": 120,
              "label": "You"}]
    good = _al(vp["id"], h, words)
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=good)
    assert r.status_code == 201, r.text

    untrimmed = _al(vp["id"], h, words)
    untrimmed["derivation_run"]["host_context"] = " worker-7"
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=untrimmed)
    assert r.status_code == 422
    assert r.json()["error_code"] == "ALIGNMENT_PROVENANCE_INCOMPLETE"

    extra_run = _al(vp["id"], h, words)
    extra_run["derivation_run"]["gpu"] = "RTX"
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=extra_run)
    assert r.status_code == 422  # closed run schema

    doc_missing = _al(vp["id"], h, words)
    del doc_missing["alignment_document"]["phonemes"]
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=doc_missing)
    assert r.status_code == 422  # closed document schema


# --------------------------------------------- E03 alignment outside trim

@pytest.mark.asyncio
async def test_e03_alignment_entry_outside_trim(client):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    body = _al(vp["id"], h, [
        {"start_sample": 0, "end_sample_exclusive": 48100,
         "label": "beyond"}])
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments", json=body)
    assert r.status_code == 422
    assert r.json()["error_code"] == "ALIGNMENT_INVALID"


# --------------------------------------- same-run/different-bytes conflict

@pytest.mark.asyncio
async def test_same_run_different_bytes_fails_closed(client):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    words = [{"start_sample": 0, "end_sample_exclusive": 120,
              "label": "You"}]
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=_al(vp["id"], h, words))
    assert r.status_code == 201
    # SAME run identity, DIFFERENT retained bytes -> contradiction
    conflicting = _al(vp["id"], h, [
        {"start_sample": 0, "end_sample_exclusive": 60, "label": "You"}])
    assert conflicting["derivation_run"] == \
        _al(vp["id"], h, words)["derivation_run"]
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=conflicting)
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "ALIGNMENT_RUN_CONFLICT"


# ----------------------------------------------- E06/E07 rational grammar

@pytest.mark.asyncio
async def test_e06_noncanonical_rational_rejected(client):
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    r = await _map(client, shot, 0, vp["id"], pnum=2, pden=4)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "INVALID_RATIONAL"
    r = await _map(client, shot, 0, vp["id"], anum=0, aden=4)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_RATIONAL"
    r = await _map(client, shot, 0, vp["id"], anum=1, aden=-2)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_RATIONAL"


@pytest.mark.asyncio
async def test_e07_rational_overflow_rejected(client):
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    r = await _map(client, shot, 0, vp["id"], pnum=2 ** 63, pden=1)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "INVALID_RATIONAL"
    r = await _map(client, shot, 0, vp["id"], anum=2 ** 63, aden=1)
    assert r.status_code == 422
    assert r.json()["error_code"] == "INVALID_RATIONAL"


# ------------------------------------------- E08 shot duration required

@pytest.mark.asyncio
async def test_e08_zero_duration_shot_rejects_mapping(client):
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE shots SET duration_ms = 0 WHERE id = :s"),
            {"s": shot})
    r = await _map(client, shot, 0, vp["id"])
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "SHOT_DURATION_REQUIRED"
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE shots SET duration_ms = NULL WHERE id = :s"),
            {"s": shot})
    r = await _map(client, shot, 0, vp["id"])
    assert r.status_code == 422
    assert r.json()["error_code"] == "SHOT_DURATION_REQUIRED"


# --------------------------------- E14 simultaneous speaker positions

@pytest.mark.asyncio
async def test_e14_simultaneous_positions_rejected(client):
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    # position 0: [0, 1000) ms (samples [0,48000) @ 48 kHz)
    r = await _map(client, shot, 0, vp["id"], s=0, e=48000, anum=0)
    assert r.status_code == 200, r.text
    # position 1 overlapping position 0 in shot-domain time -> rejected
    r = await _map(client, shot, 1, vp["id"], s=24000, e=72000, anum=500)
    assert r.status_code == 422, r.text
    assert "simultaneous" in r.json()["message"]
    # an ADJACENT second position is lawful (no shared shot-domain time)
    r = await _map(client, shot, 1, vp["id"], s=48000, e=96000, anum=1000)
    assert r.status_code == 200, r.text


# ------------------------------------------- E16 observable STALE result

@pytest.mark.asyncio
async def test_e16_stale_readiness_is_observable_and_never_mutates(client):
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    r = await _map(client, shot, 0, vp["id"])
    assert r.status_code == 200, r.text
    mapping_hash_before = r.json()["mapping_hash"]
    listed = (await client.get(f"/shots/{shot}/vocal-segments")).json()
    assert listed[0]["current_readiness"]["readiness"] == "CURRENT"

    # advance the selection away from the mapped VP
    r = await client.put(
        f"/dialogue-line-revisions/{vp['dialogue_line_revision_id']}"
        "/vocal-selection",
        json={"vocal_performance_revision_id": None,
              "selected_by": "director"})
    assert r.status_code == 200, r.text
    listed = (await client.get(f"/shots/{shot}/vocal-segments")).json()
    assert listed[0]["current_readiness"]["readiness"] == "STALE", (
        "E16 requires the OBSERVABLE STALE current-readiness result")
    assert listed[0]["mapping_hash"] == mapping_hash_before, (
        "the readiness projection must never mutate the mapping")


# ---------------------------------------- C03 true concurrent adoption

@pytest.mark.asyncio
async def test_c03_concurrent_duplicate_adoption_converges(client):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    lid = (await client.post(f"/projects/{pid}/dialogue-lines",
                             json={})).json()["id"]
    h = await place_blob(client, wave_bytes(48000, 48000))
    _, r = await _candidate(client, pid, eid, lid, h)
    cid = r.json()["id"]
    r1, r2 = await asyncio.gather(
        client.post(f"/vocal-candidates/{cid}/adopt",
                    json={"adopted_by": "director"}),
        client.post(f"/vocal-candidates/{cid}/adopt",
                    json={"adopted_by": "producer"}))
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json()["id"] == r2.json()["id"], (
        "concurrent duplicate adoption must converge on ONE VP")
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        n = (await conn.execute(text(
            "SELECT COUNT(*) FROM vocal_performance_revisions WHERE "
            "adopted_candidate_id = :c"), {"c": cid})).scalar()
    assert n == 1, "exactly one VP exists for the candidate (C03)"


# ---------------------------------- same-timestamp pagination boundary

@pytest.mark.asyncio
async def test_pagination_same_timestamp_tiebreaker(client):
    pid = await make_project(client)
    engine = client._transport.app.state.engine
    now = "2026-09-20T12:00:00.000Z"
    async with engine.begin() as conn:
        for i in range(4):
            await conn.execute(text(
                "INSERT INTO dialogue_lines (id, project_id, created_at) "
                "VALUES (:i, :p, :t)"),
                {"i": f"tie{i}", "p": pid, "t": now})
    seen = []
    url = f"/projects/{pid}/dialogue-lines?limit=2"
    while url:
        page = (await client.get(url)).json()
        seen += [row["id"] for row in page["lines"]]
        cursor = page.get("next_cursor")
        url = (f"/projects/{pid}/dialogue-lines?limit=2"
               f"&cursor_created={cursor[0]}&cursor_id={cursor[1]}") \
            if cursor else None
    assert sorted(seen) == ["tie0", "tie1", "tie2", "tie3"], (
        "same-timestamp rows must not disappear between pages")


# ------------------------------------------- fractional-den restore case

@pytest.mark.asyncio
async def test_fractional_denominator_mapping_restores_exactly(client,
                                                               tmp_path):
    from soloring.recovery.backup import backup, restore
    pid, eid, lid, vp = await _selected_vp(client)
    shot = await make_shot(client, pid, 2000)
    # non-integral anchor: -250/7 ms, segment [0, 96000) @ 48 kHz
    # -> shot interval [-250/7, 5750/7) ms intersects (0, 2000)
    r = await _map(client, shot, 0, vp["id"], s=0, e=96000,
                   anum=-250, aden=7)
    assert r.status_code == 200, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    settings = client._transport.app.state.settings
    root = tmp_path / "bk"
    await backup(settings, root)
    dest = tmp_path / "rs"
    await restore(root, dest)  # verifier must accept the fractional anchor
    import sqlite3
    con = sqlite3.connect(dest / "soloring.db")
    row = con.execute(
        "SELECT shot_anchor_num, shot_anchor_den FROM "
        "shot_vocal_segment_mappings").fetchone()
    con.close()
    assert row == (-250, 7)


# ------------------------------------ F06 / F09 recovery byte integrity

async def _seeded_alignment(client, tmp_path):
    pid, eid, lid, vp = await _selected_vp(client, frames=48000)
    h = vp["retained_audio_blob_hash"]
    r = await client.post(
        f"/vocal-performance-revisions/{vp['id']}/alignments",
        json=_al(vp["id"], h, [
            {"start_sample": 0, "end_sample_exclusive": 120,
             "label": "You"}]))
    assert r.status_code == 201, r.text
    settings = client._transport.app.state.settings
    retained = r.json()["retained_sha256"]
    blob_path = (settings.blob_dir / "sha256" / retained[:2]
                 / retained[2:4] / retained)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    return settings, retained, blob_path


@pytest.mark.asyncio
async def test_f06_retained_blob_hash_disagreement_fails_recovery(
        client, tmp_path):
    from soloring.recovery.backup import backup
    settings, retained, blob_path = await _seeded_alignment(client, tmp_path)
    blob_path.write_bytes(b"{\"tampered\": true}")  # wrong bytes at path
    with pytest.raises(Exception) as exc_info:
        await backup(settings, tmp_path / "bk")
    assert "rehash" in str(exc_info.value) or "RECOVERY" in str(
        exc_info.value) or "hash" in str(exc_info.value)


@pytest.mark.asyncio
async def test_f09_missing_alignment_bytes_fail_recovery(
        client, tmp_path):
    from soloring.recovery.backup import backup
    settings, retained, blob_path = await _seeded_alignment(client, tmp_path)
    blob_path.unlink()
    with pytest.raises(Exception) as exc_info:
        await backup(settings, tmp_path / "bk")
    assert "missing" in str(exc_info.value)
