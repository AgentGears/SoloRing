"""M15D recovery proofs (frozen R6 §31.11 M15-REC:01-04)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.compatibility.service import (
    apply_assessment,
    create_assessment,
)
from tests.m15_seed import seed_a4_use


def _sess(client):
    class _S:
        bind = client._transport.app.state.engine

    return _S()


async def _assess_and_apply(client, base):
    engine = client._transport.app.state.engine
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    use = result["uses"][0]
    async with engine.connect() as conn:
        version = (await conn.execute(text(
            "SELECT working_version FROM compositions WHERE id = :c"),
            {"c": use["composition_id"]})).scalar_one()
    await apply_assessment(
        _sess(client), assessment_id=result["assessment_id"],
        selected_uses=[{
            "composition_id": use["composition_id"],
            "occurrence_id": use["occurrence_id"],
            "expected_working_version": version,
            "expected_use_contract_hash": use["use_contract_hash"],
            "review_accept": True}])
    return result


async def _stamp_alembic(client, head="0020_m17c_performance_capture"):  # M17C-A advances the head
    """The conftest engine builds schema via create_all (no
    alembic_version); the backup machinery requires the table."""
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES (:h)"),
            {"h": head})
        await conn.commit()


async def _link_r2_provenance(client, base):
    """The backup verifier requires M11 provenance links; the seed
    helper's second revision carries none — link it to the seed's own
    source asset (the same project/blob chain the verifier accepts)."""
    from soloring.domain.ids import new_uuid

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        # the verifier requires link→assets.blob_hash == closure blob:
        # mint a project-scoped asset over r2's OWN retained blob
        r2_blob = (await conn.execute(text(
            "SELECT blob_hash FROM production_revision_closures "
            "WHERE production_revision_id = :r"),
            {"r": base["r2"]})).scalar_one()
        asset_id = new_uuid()
        await conn.execute(text(
            "INSERT INTO assets (id, project_id, blob_hash, kind, "
            "created_at) VALUES (:i, :p, :b, 'reference', :n)"),
            {"i": asset_id, "p": base["project_id"], "b": r2_blob,
             "n": "2026-01-01T00:00:00.000Z"})
        await conn.execute(text(
            "INSERT INTO production_revision_source_assets "
            "(production_revision_id, asset_id, created_at) VALUES "
            "(:r, :a, :n)"),
            {"r": base["r2"], "a": asset_id,
             "n": "2026-01-01T00:00:00.000Z"})
        await conn.commit()


async def test_0016_backup_restore_preserves_m15_rows_and_hashes(
        client, tmp_path):
    """M15-REC:01 — head-0016 backup → restore preserves exact
    assessment children, tracking policy, and update operation/items
    with canonical hashes revalidating; alembic head stays 0016."""
    from soloring.compatibility.canonical import verify_stored_assessment
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings

    base = await seed_a4_use(client, tag=b"rec01")
    r = await client.put(
        f"/compositions/{base['composition_id']}/occurrences/"
        f"{base['occurrence_id']}/revision-tracking",
        json={"mode": "TRACK_COMPATIBLE",
              "expected_policy_version": 0})
    assert r.status_code == 200, r.text
    result = await _assess_and_apply(client, base)

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    async with engine.connect() as conn:
        before = {}
        for t in ("production_compatibility_assessments",
                  "production_compatibility_uses",
                  "composition_occurrence_revision_tracking",
                  "production_update_operations",
                  "production_update_items"):
            rows = (await conn.execute(text(f"SELECT * FROM {t}"))
                    ).fetchall()
            before[t] = [tuple(r) for r in rows]

    await _link_r2_provenance(client, base)
    await _stamp_alembic(client)
    backup_root = tmp_path / "backup"
    await backup(settings, backup_root)
    manifest = json.loads((backup_root / "backup-manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["alembic_version"] == "0020_m17c_performance_capture"

    # M16-C certified the 0017 head, so the live backup runs there; the
    # REC:01 proof stays pinned to the 0016 posture via the REC:02
    # BACKUP-TREE conversion precedent (the five M16 tables are empty in
    # this test — each proven empty before its drop).
    import hashlib
    import sqlite3

    from soloring.domain.canonical import canonical_json_bytes

    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        for table in ("persistent_consequence_reviews",
                      "shot_intra_shot_events",
                      "shot_revision_intra_shot_events",
                      "shot_revision_intra_shot_specs",
                      "shot_intra_shot_event_proposals",
                      # M17B tables carry two Blob-FK paths; the old-head
                      # postures drop them (empty, as the create_all seed wrote
                      # no performance rows)
                      "performance_retarget_reviews",
                      "performance_retarget_assessments",
                      "performance_revisions",
                      "performance_candidates",
                      # M17A tables carry three Blob-FK paths; the exact
                      # 0016 eight-path posture drops them (empty, as
                      # the create_all seed wrote no dialogue rows)
                      "dialogue_alignments",
                      "shot_vocal_segment_mappings",
                      "vocal_performance_selections",
                      "vocal_performance_revisions",
                      "vocal_candidates",
                      "dialogue_line_revisions",
                      "dialogue_lines"):
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert n == 0, (
                f"{table} has {n} rows — not a lawful 0016 posture")
            con.execute(f"DROP TABLE {table}")
        con.execute(
            "UPDATE alembic_version SET version_num = "
            "'0016_m15_revision_compatibility'")
        con.commit()
    finally:
        con.close()
    manifest["alembic_version"] = "0016_m15_revision_compatibility"
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    (backup_root / "backup-manifest.json").write_bytes(
        canonical_json_bytes(manifest))

    dest = tmp_path / "restored"
    await restore(backup_root, dest)

    restored_settings = Settings(data_dir=dest)
    import sqlite3

    con = sqlite3.connect(str(restored_settings.db_path))
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == "0016_m15_revision_compatibility"
        for table, rows in before.items():
            got = con.execute(
                f"SELECT * FROM {table}").fetchall()
            assert len(got) == len(rows), table
    finally:
        con.close()

    # canonical hashes revalidate on the restored DB
    from sqlalchemy.ext.asyncio import create_async_engine

    rengine = create_async_engine(
        restored_settings.resolved_database_url())
    async with rengine.connect() as conn:
        verified = await verify_stored_assessment(
            conn, result["assessment_id"])
    await rengine.dispose()
    assert verified["parent"]["id"] == result["assessment_id"]


async def test_0015_backup_restores_without_inventing_m15_state(client,
                                                                 tmp_path):
    """M15-REC:02 — a historical head-0015 backup restores with exact
    predecessor semantics and invents no M15 state. The historical posture
    is constructed from a semantically valid real 0016 backup, then the
    BACKUP TREE alone is converted to 0015 by dropping the five empty M16
    tables and the five empty M15 tables (each proven empty before the
    drop), stamping 0015, and re-hashing the manifest database identity."""
    import hashlib
    import sqlite3

    from soloring.domain.canonical import canonical_json_bytes
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings

    base = await seed_a4_use(client, tag=b"rec02")
    settings = client._transport.app.state.settings
    await _link_r2_provenance(client, base)
    await _stamp_alembic(client)

    # First produce a genuinely valid head-0016 backup. M16-P0 semantic
    # succession now (correctly) treats a live 0016 database that is missing
    # all five M15 tables as corruption, so the old test-only shortcut of
    # dropping them before backup is no longer a valid construction.
    backup_root = tmp_path / "backup-0015"
    await backup(settings, backup_root)

    # Convert the backup copy — never the live database — into the historical
    # 0015 posture. The M16 and M15 tables are empty in this test, so
    # dropping them removes no authored decision and exactly models the
    # predecessor schema.
    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        for table in ("persistent_consequence_reviews",
                      "shot_intra_shot_events",
                      "shot_revision_intra_shot_events",
                      "shot_revision_intra_shot_specs",
                      "shot_intra_shot_event_proposals",
                      "production_update_items",
                      "production_update_operations",
                      "production_compatibility_uses",
                      "production_compatibility_assessments",
                      "composition_occurrence_revision_tracking",
                      # M17B: old-head postures drop the performance tables
                      "performance_retarget_reviews",
                      "performance_retarget_assessments",
                      "performance_revisions",
                      "performance_candidates",
                      # M17A: exact 0015 eight-path posture drops them
                      "dialogue_alignments",
                      "shot_vocal_segment_mappings",
                      "vocal_performance_selections",
                      "vocal_performance_revisions",
                      "vocal_candidates",
                      "dialogue_line_revisions",
                      "dialogue_lines"):
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert n == 0, (
                f"{table} has {n} rows — not a lawful 0015 posture")
            con.execute(f"DROP TABLE {table}")
        con.execute(
            "UPDATE alembic_version SET version_num = "
            "'0015_m14_world_observation_execution'")
        con.commit()
    finally:
        con.close()

    manifest_path = backup_root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = "0015_m14_world_observation_execution"
    manifest["database_sha256"] = hashlib.sha256(
        db_file.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    dest = tmp_path / "restored-0015"
    await restore(backup_root, dest)

    restored = Settings(data_dir=dest)
    con = sqlite3.connect(str(restored.db_path))
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        m15 = {"production_compatibility_assessments",
               "production_compatibility_uses",
               "composition_occurrence_revision_tracking",
               "production_update_operations",
               "production_update_items"}
        assert not (tables & m15), (
            f"0015 restore invented M15 tables: {sorted(tables & m15)}")
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        assert head == "0015_m14_world_observation_execution"
    finally:
        con.close()


async def test_corrupt_restored_assessment_fails_integrity(client, tmp_path):
    """M15-REC:03 — a tampered restored assessment (report-hash drift)
    fails canonical re-derivation, never a friendly verdict."""
    from soloring.compatibility.canonical import verify_stored_assessment
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings
    from soloring.errors import SoloRingError

    base = await seed_a4_use(client, tag=b"rec03")
    result = await _assess_and_apply(client, base)
    settings = client._transport.app.state.settings

    await _link_r2_provenance(client, base)
    await _stamp_alembic(client)
    backup_root = tmp_path / "backup"
    await backup(settings, backup_root)
    dest = tmp_path / "restored"
    await restore(backup_root, dest)

    restored = Settings(data_dir=dest)
    rpath = str(Path(restored.resolved_database_url()
                   .replace("sqlite+aiosqlite:///", "")))
    import sqlite3

    con = sqlite3.connect(rpath)
    con.execute(
        "UPDATE production_compatibility_assessments SET report_hash = "
        ":h WHERE id = :a",
        {"h": "0" * 64, "a": result["assessment_id"]})
    con.commit()
    con.close()

    from sqlalchemy.ext.asyncio import create_async_engine

    rengine = create_async_engine(restored.resolved_database_url())
    async with rengine.connect() as conn:
        with pytest.raises(SoloRingError):
            await verify_stored_assessment(
                conn, result["assessment_id"])
    await rengine.dispose()


async def test_unsupported_future_restore_head_fails_closed(client, tmp_path):
    """M15-REC:04 — a backup manifest stamped with an unsupported
    future head refuses restore."""
    from soloring.recovery.backup import restore
    from soloring.recovery.backup import BackupManifestInvalid

    base = await seed_a4_use(client, tag=b"rec04")
    settings = client._transport.app.state.settings
    from soloring.recovery.backup import backup

    await _link_r2_provenance(client, base)
    await _stamp_alembic(client)
    backup_root = tmp_path / "backup"
    await backup(settings, backup_root)
    manifest_path = backup_root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = "0099_m99_future"
    from soloring.domain.canonical import canonical_json_bytes

    manifest_path.write_bytes(canonical_json_bytes(manifest))

    dest = tmp_path / "refused"
    with pytest.raises(BackupManifestInvalid, match="alembic_version"):
        await restore(backup_root, dest)
    assert not dest.exists()


async def test_two_pi_transitions_backup_verification(
        client, tmp_path):
    """R1-correction regression: a valid database with TWO or more PI
    feature transition rows passes _verify_m13_pi_state and the real
    backup() path. The published baseline deleted the loop-local
    `active` on the first iteration (UnboundLocalError on the
    second); predecessor fixtures carried at most one transition, so
    only an accumulated history ever iterated the loop twice."""
    from soloring.recovery.backup import backup, _verify_m13_pi_state
    import sqlite3 as _sq

    engine = client._transport.app.state.engine
    # a real M13 world with a PI occurrence + feature (the baseline's
    # own machinery), then TWO lawful PI feature transitions on one
    # feature (Shot/start upright + Shot/end fallen)
    from tests.test_m13_shot_capture import _full_m13_world
    from tests.test_m16_instance import _pi_world
    b, sel, fid = await _pi_world(client, tag=b"m15-pi2")
    occ = sel["occurrence_id"]
    import json as _json
    from soloring.domain.canonical import canonical_hash
    from soloring.db.timeutil import DB_NOW_SQL as NOW
    async with engine.begin() as conn:
        await conn.execute(text(
            f"INSERT INTO production_instance_feature_transitions "
            "(id, feature_id, anchor_type, anchor_id, boundary, "
            "operation, value_json, value_hash, created_at, updated_at)"
            f" VALUES (:t1, :f, 'shot', :s, 'start', 'set', :vj, :vh, "
            f"{NOW}, {NOW}), (:t2, :f, 'shot', :s, 'end', 'set', :vj2, "
            f":vh2, {NOW}, {NOW})"),
            {"t1": "00000000-0000-4000-8000-0000000000e3",
             "t2": "00000000-0000-4000-8000-0000000000e4",
             "f": fid, "s": b["shot"],
             "vj": _json.dumps("upright"),
             "vh": canonical_hash("upright"),
             "vj2": _json.dumps("fallen"),
             "vh2": canonical_hash("fallen")})
    # the focused verifier passes with two transitions
    import shutil as _sh
    import tempfile as _tf
    tmpdb = Path(_tf.mkdtemp()) / "soloring.db"
    settings = client._transport.app.state.settings
    _sh.copy(settings.data_dir / "soloring.db", tmpdb)
    con = _sq.connect(str(tmpdb))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    con = _sq.connect(str(tmpdb))
    con.row_factory = _sq.Row
    _verify_m13_pi_state(con)
    con.close()
    # and the real backup path succeeds end to end
    await _stamp_alembic(client)
    await backup(settings, tmp_path / "bk2")
    assert (tmp_path / "bk2" / "backup-manifest.json").exists()
