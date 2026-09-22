"""M17A recovery integration tests (frozen R5 §12/§16)."""

from __future__ import annotations

import pytest

from soloring.recovery.backup import backup, restore
from soloring.recovery.backup import (M17A_BLOB_FK_COLUMNS,
                                      M14_BLOB_FK_COLUMNS)

from tests.m17a_seed import (make_entity, make_project, make_shot,
                             place_blob, stamp_alembic, wave_bytes)


def test_blob_fk_inventory_is_exactly_eleven():
    assert len(M14_BLOB_FK_COLUMNS) == 8
    extra = M17A_BLOB_FK_COLUMNS - M14_BLOB_FK_COLUMNS
    assert extra == frozenset({
        ("vocal_candidates", "retained_audio_blob_hash"),
        ("vocal_performance_revisions", "retained_audio_blob_hash"),
        ("dialogue_alignments", "retained_blob_hash"),
    })
    assert len(M17A_BLOB_FK_COLUMNS) == 11


@pytest.mark.asyncio
async def test_backup_restore_round_trip(client, tmp_path):
    pid = await make_project(client)
    eid = await make_entity(client, pid)
    r = await client.post(f"/projects/{pid}/dialogue-lines", json={})
    lid = r.json()["id"]
    rev1 = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You weren't supposed to see this."})).json()
    rev2 = (await client.post(f"/dialogue-lines/{lid}/revisions", json={
        "speaker_subject_id": eid, "language": "en",
        "wording": "You were never supposed to see this."})).json()
    h1 = await place_blob(client, wave_bytes(48000, 216000))
    h2 = await place_blob(client, wave_bytes(48000, 96000))
    c1 = (await client.post(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-candidates",
        json={"retained_audio_blob_hash": h1,
              "source_provenance": {"schema_version": 1,
                                    "source_kind": "recorded"}}
    )).json()["id"]
    c2 = (await client.post(
        f"/dialogue-line-revisions/{rev2['id']}/vocal-candidates",
        json={"retained_audio_blob_hash": h2,
              "source_provenance": {"schema_version": 1,
                                    "source_kind": "adr"}}
    )).json()["id"]
    v1 = (await client.post(f"/vocal-candidates/{c1}/adopt",
                            json={"adopted_by": "d"})).json()
    v2 = (await client.post(f"/vocal-candidates/{c2}/adopt",
                            json={"adopted_by": "d"})).json()
    await client.put(
        f"/dialogue-line-revisions/{rev1['id']}/vocal-selection",
        json={"vocal_performance_revision_id": v1["id"],
              "selected_by": "d"})
    shot_a = await make_shot(client, pid, 2000)
    shot_b = await make_shot(client, pid, 3000)
    await client.put(f"/shots/{shot_a}/vocal-segments/0", json={
        "vocal_performance_revision_id": v1["id"],
        "source_start_sample": 0, "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1}})
    await client.put(f"/shots/{shot_b}/vocal-segments/0", json={
        "vocal_performance_revision_id": v1["id"],
        "source_start_sample": 84000,
        "source_end_sample_exclusive": 216000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 1750, "den": 1},
        "shot_anchor_ms": {"num": -250, "den": 1}})
    words = [{"start_sample": 0, "end_sample_exclusive": 12000,
              "label": "You"}]

    def _al(vpid, audio, ws, run_ts="2026-09-19T12:34:56.123456Z"):
        return {"analyzer_id": "X", "analyzer_version": "1.2.0",
                "model_identity": "Mx", "runtime_identity": "Rx",
                "parameters_sha256": "a" * 64,
                "alignment_document": {"schema_version": 1, "words": ws,
                                       "phonemes": [],
                                       "viseme_classes": []},
                "derivation_run": {
                    "schema_version": 1,
                    "run_timestamp_utc": run_ts,
                    "host_context": "worker-7",
                    "input_digest": {
                        "vocal_performance_revision_id": vpid,
                        "retained_audio_blob_sha256": audio}}}

    a1 = _al(v1["id"], h1, words)
    r = await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments", json=a1)
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments", json=a1)
    assert r.status_code == 201  # D1_same
    a1v = _al(v1["id"], h1, [
        {"start_sample": 0, "end_sample_exclusive": 6000,
         "label": "You"}],
        run_ts="2026-09-19T12:41:09.654321Z")  # distinct run R2
    r = await client.post(
        f"/vocal-performance-revisions/{v1['id']}/alignments", json=a1v)
    assert r.status_code == 201, r.text  # D1_variant
    r = await client.post(
        f"/vocal-performance-revisions/{v2['id']}/alignments",
        json=_al(v2["id"], h2, words))
    assert r.status_code == 201  # D2
    # flush WAL then backup/restore
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await stamp_alembic(client)
    backup_root = tmp_path / "m17a-backup"
    settings = client._transport.app.state.settings
    await backup(settings, backup_root)
    dest = tmp_path / "m17a-restored"
    await restore(backup_root, dest)
    import sqlite3
    con = sqlite3.connect(dest / "soloring.db")
    ver = con.execute("SELECT version_num FROM alembic_version"
                      ).fetchone()[0]
    n_dlr = con.execute(
        "SELECT COUNT(*) FROM dialogue_line_revisions").fetchone()[0]
    n_vp = con.execute(
        "SELECT COUNT(*) FROM vocal_performance_revisions").fetchone()[0]
    n_da = con.execute(
        "SELECT COUNT(*) FROM dialogue_alignments").fetchone()[0]
    sel = con.execute(
        "SELECT selected_vocal_performance_revision_id FROM "
        "vocal_performance_selections").fetchall()
    n_map = con.execute(
        "SELECT COUNT(*) FROM shot_vocal_segment_mappings").fetchone()[0]
    con.close()
    assert ver == "0019_m17b_performance_revisions"
    assert (n_dlr, n_vp, n_da, n_map) == (2, 2, 4, 2)
    assert sel == [(v1["id"],), (None,)]
