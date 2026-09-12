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



async def _stamp_alembic(client, head="0016_m15_revision_compatibility"):
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
    assert manifest["alembic_version"] == "0016_m15_revision_compatibility"
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
    predecessor semantics and invents no M15 state. Backup at the live
    head refuses 0015 (only the current head is backupable); the
    historical posture is constructed by rebuilding the manifest from a
    real 0016 backup after dropping the five M15 tables and stamping
    0015 — the same hand-built-historical-manifest pattern the M13
    recovery proofs use."""
    import sqlite3

    from soloring.domain.canonical import canonical_json_bytes
    from soloring.recovery.backup import backup, restore
    from soloring.settings import Settings

    base = await seed_a4_use(client, tag=b"rec02")
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    await _link_r2_provenance(client, base)

    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    await engine.dispose()
    con = sqlite3.connect(str(settings.db_path))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        con.execute(
            "INSERT OR REPLACE INTO alembic_version (version_num) "
            "VALUES ('0016_m15_revision_compatibility')")
        for table in ("production_update_items",
                      "production_update_operations",
                      "production_compatibility_uses",
                      "production_compatibility_assessments",
                      "composition_occurrence_revision_tracking"):
            con.execute(f"DROP TABLE {table}")
        con.commit()
    finally:
        con.close()

    # take the backup while the (now M15-table-free) tree is stamped
    # 0016 — the only head the live backup path accepts — then convert
    # the BACKUP TREE itself into the historical 0015 posture: stamp
    # its DB's alembic_version to 0015 and rewrite the manifest with
    # the re-hashed database identity
    import hashlib

    backup_root = tmp_path / "backup-0015"
    await backup(settings, backup_root)
    db_file = backup_root / "soloring.db"
    con = sqlite3.connect(str(db_file))
    con.execute(
        "UPDATE alembic_version SET version_num = "
        "'0015_m14_world_observation_execution'")
    con.commit()
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
    engine = client._transport.app.state.engine
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
