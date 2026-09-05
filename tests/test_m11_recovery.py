"""M11 recovery proofs (frozen R3 plan §20.8).

Head-dispatched recovery: current backups certify exactly the 0012 head and
the seven-path Blob-FK inventory; valid pre-M11 0011 manifests restore under
the frozen six-path policy without inventing M11 state; unsupported heads
fail closed. M11 semantic verification and strict consumption survive
backup/restore without the original creator.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

import importlib

rb = importlib.import_module("soloring.recovery.backup")
from soloring.assets.blob_store import BlobStore
from soloring.domain.ids import new_uuid
from soloring.recovery import RecoveryCorruption, restore
from soloring.settings import Settings

REPO = Settings.__module__  # unused marker; real repo root below
from soloring.settings import BASE_DIR  # noqa: E402

NOW = "2026-01-01T00:00:00.000Z"


def _alembic_upgrade(data_dir: Path, monkeypatch, target: str) -> None:
    """Point the pinned Settings singleton at data_dir and run alembic."""
    from alembic import command
    from alembic.config import Config

    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    command.upgrade(cfg, target)


def _blob_file(root: Path, h: str) -> Path:
    return root / "blobs" / f"sha256/{h[0:2]}/{h[2:4]}/{h}"


def _db(root: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(root / "soloring.db"))
    con.row_factory = sqlite3.Row
    return con


def _seed_m11_state(data_dir: Path, settings: Settings) -> dict:
    """Direct-SQL seed of one published revision over real physical bytes."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.production.canonical import RetainedBlobClosure
    from soloring.production.canonical import (
        production_revision_snapshot_hash,
        production_revision_snapshot_json,
    )
    from soloring.production.service import (
        create_production_object,
        publish_production_revision,
    )

    data = b"m11-recovery-bytes"
    bh = hashlib.sha256(data).hexdigest()
    p = _blob_file(data_dir, bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

    async def run() -> dict:
        eng = create_async_engine(
            f"sqlite+aiosqlite:///{(data_dir / 'soloring.db').as_posix()}"
        )
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
        pid = new_uuid()
        async with factory() as s:
            async with s.bind.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO projects (id, name, created_at, updated_at) "
                        "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
                await conn.commit()
        aid = new_uuid()
        async with factory() as s:
            async with s.bind.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
                        "VALUES (:h, :p, :s, 'image/png', :n)"),
                    {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                     "s": len(data), "n": NOW})
                await conn.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                        "VALUES (:a, :p, :h, 'reference', :n)"),
                    {"a": aid, "p": pid, "h": bh, "n": NOW})
                await conn.commit()
        blob_store = BlobStore(settings)
        async with factory() as s:
            obj = await create_production_object(s, pid, name="Desk")
            rev, created = await publish_production_revision(
                s, blob_store, production_object_id=obj["id"], source_asset_id=aid)
            assert created
        await eng.dispose()
        return {"project_id": pid, "asset_id": aid, "object_id": obj["id"],
                "revision": rev, "blob_hash": bh}

    return asyncio.run(run())


def _stamp_head(data_dir: Path, head: str) -> None:
    from alembic import command
    from alembic.config import Config

    import soloring.settings as settings_mod

    prev = settings_mod._settings
    settings_mod._settings = Settings(data_dir=data_dir)
    try:
        cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
        cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
        command.stamp(cfg, head)
    finally:
        settings_mod._settings = prev


def _assemble_backup(root: Path, dest: Path, alembic_version: str) -> dict:
    """Assemble a valid backup tree at an explicit head (test evidence
    builder for the 0011 historical policy, which current backup creation
    no longer certifies by design)."""
    dest.mkdir(parents=True)
    db = root / "soloring.db"
    shutil.copy(db, dest / "soloring.db")
    con = _db(root)
    hashes = sorted(
        r[0] for r in con.execute(
            "SELECT DISTINCT hash FROM blobs") if _blob_file(root, r[0]).exists()
    )
    con.close()
    for h in hashes:
        src = _blob_file(root, h)
        out = _blob_file(dest, h)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, out)
    digest = hashlib.sha256((dest / "soloring.db").read_bytes()).hexdigest()
    # Reuse recovery's own liveness enumeration (head-specific policy) so the
    # assembled manifest carries the exact Blob/Project diagnostics the
    # strict parser and restore re-verification expect.
    live = rb._enumerate_liveness(
        root / "soloring.db", rb._blob_fk_policy_for_head(alembic_version))
    manifest = {
        "schema_version": 1,
        "alembic_version": alembic_version,
        "database_sha256": digest,
        "blob_hashes": live.blob_hashes,
        "workflow_artifacts": [
            {"kind": k, "sha256": h} for k, h in live.artifacts
        ],
        "projects": live.projects,
    }
    for h in live.blob_hashes:
        src = _blob_file(root, h)
        out = _blob_file(dest, h)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, out)
    from soloring.domain.canonical import canonical_json_bytes

    (dest / "backup-manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


# --- Module template ---------------------------------------------------------


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = tmp_path_factory.mktemp("m11_recovery")
    data_dir = base / "data"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir)
    seeded = _seed_m11_state(data_dir, settings)
    _stamp_head(data_dir, "0012_m11_reusable_production_revisions")
    backup_root = base / "backup"
    evidence = asyncio.run(rb.backup(settings, backup_root))
    return {"data_dir": data_dir, "settings": settings, "seed": seeded,
            "backup_root": backup_root, "evidence": evidence}


@pytest.fixture
def env(template, tmp_path):
    src = tmp_path / "src" / "data"
    shutil.copytree(template["data_dir"], src)
    for suffix in ("-wal", "-shm"):
        side = src / ("soloring.db" + suffix)
        if side.exists():
            side.unlink()
    backup = tmp_path / "backup"
    shutil.copytree(template["backup_root"], backup)
    return {"src": src, "settings": Settings(data_dir=src), "backup": backup}


# --- Cells -------------------------------------------------------------------


def test_current_backup_expected_head_is_0012(template):
    """M11-RECOVERY:01 — new backups certify only the current head."""
    assert rb.EXPECTED_ALEMBIC_HEAD == "0012_m11_reusable_production_revisions"
    manifest = json.loads(
        (template["backup_root"] / "backup-manifest.json").read_text()
    )
    assert manifest["alembic_version"] == "0012_m11_reusable_production_revisions"


def test_recovery_blob_fk_inventory_is_six_for_0011_and_seven_for_0012():
    """M11-RECOVERY:02 — head-specific exact inventories; 6→7 transition."""
    six = rb.PRE_M11_BLOB_FK_COLUMNS
    seven = rb.M11_BLOB_FK_COLUMNS
    assert len(six) == 6
    assert len(seven) == 7
    assert set(seven) - set(six) == {("production_revision_closures", "blob_hash")}
    assert rb._blob_fk_policy_for_head(
        "0011_m10_derived_spatial_execution") is six
    assert rb._blob_fk_policy_for_head(
        "0012_m11_reusable_production_revisions") is seven
    with pytest.raises(RecoveryCorruption):
        rb._blob_fk_policy_for_head("0013_something_else")


async def test_backup_restore_roundtrip_preserves_production_revision_and_strict_consumption(
    env, tmp_path
):
    """M11-RECOVERY:03 — full 0012 historical liveness roundtrip."""
    from soloring.assets.blob_store import BlobStore
    from soloring.production.service import load_verified_production_revision

    dest = tmp_path / "restored"
    result = await restore(env["backup"], dest)
    assert result["blob_count"] >= 1
    settings = Settings(data_dir=dest)
    blob_store = BlobStore(settings)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    eng = create_async_engine(
        f"sqlite+aiosqlite:///{(dest / 'soloring.db').as_posix()}")
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    rid = env and template_rid(env)
    async with factory() as s:
        async with s.bind.connect() as conn:
            meta = await load_verified_production_revision(
                conn, revision_id=rid, blob_store=blob_store)
    await eng.dispose()
    assert meta["snapshot_hash"] == json.loads(json.dumps(meta))["snapshot_hash"]
    assert meta["closure"]["blob_hash"]


def template_rid(env) -> str:
    con = _db(env["src"])
    try:
        return con.execute(
            "SELECT id FROM production_revisions LIMIT 1").fetchone()[0]
    finally:
        con.close()


async def test_missing_m11_closure_blob_fails_backup(env, tmp_path):
    """M11-RECOVERY:04 — missing live closure bytes block certification."""
    con = _db(env["src"])
    bh = con.execute(
        "SELECT blob_hash FROM production_revision_closures LIMIT 1").fetchone()[0]
    con.close()
    _blob_file(env["src"], bh).unlink()
    with pytest.raises(RecoveryCorruption):
        await rb.backup(env["settings"], tmp_path / "b")
    # Exact restoration.
    (tmp_path / "seed").mkdir()
    p = _blob_file(env["src"], bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"m11-recovery-bytes")
    assert await rb.backup(env["settings"], tmp_path / "b2")


async def test_corrupt_m11_closure_blob_fails_backup(env, tmp_path):
    """M11-RECOVERY:05 — corrupt live closure bytes block certification."""
    con = _db(env["src"])
    bh = con.execute(
        "SELECT blob_hash FROM production_revision_closures LIMIT 1").fetchone()[0]
    con.close()
    _blob_file(env["src"], bh).write_bytes(b"X" * len(b"m11-recovery-bytes"))
    with pytest.raises(RecoveryCorruption):
        await rb.backup(env["settings"], tmp_path / "b")


async def test_m11_snapshot_or_closure_corruption_fails_backup_semantic_verifier(
    env, tmp_path
):
    """M11-RECOVERY:06 — backup does not certify malformed authority."""
    con = _db(env["src"])
    rid = con.execute("SELECT id FROM production_revisions LIMIT 1").fetchone()[0]
    con.execute(
        "UPDATE production_revisions SET snapshot_hash = ? WHERE id = ?",
        ("0" * 64, rid))
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption):
        await rb.backup(env["settings"], tmp_path / "b")


async def test_m11_source_provenance_corruption_fails_backup_semantic_verifier(
    env, tmp_path
):
    """M11-RECOVERY:07 — provenance corruption detected."""
    con = _db(env["src"])
    rid = con.execute("SELECT id FROM production_revisions LIMIT 1").fetchone()[0]
    # Delete the provenance link: no source Asset proves the closure.
    con.execute(
        "DELETE FROM production_revision_source_assets WHERE production_revision_id = ?",
        (rid,))
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption):
        await rb.backup(env["settings"], tmp_path / "b")


async def test_restore_does_not_require_original_creator(env, tmp_path):
    """M11-RECOVERY:08 — restored retained closure is sufficient."""
    from soloring.production.service import load_verified_production_revision

    rid = template_rid(env)
    dest = tmp_path / "restored"
    await restore(env["backup"], dest)
    # The creator path is dead: readiness resolution is poisoned.
    import soloring.production.readiness as readiness_mod

    def _boom(*a, **k):
        raise AssertionError("creator path touched during historical consumption")

    orig = readiness_mod.resolve_publication_readiness
    readiness_mod.resolve_publication_readiness = _boom
    try:
        blob_store = BlobStore(Settings(data_dir=dest))
        from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                            create_async_engine)

        eng = create_async_engine(
            f"sqlite+aiosqlite:///{(dest / 'soloring.db').as_posix()}")
        factory = async_sessionmaker(bind=eng, expire_on_commit=False,
                                     class_=AsyncSession)
        async with factory() as s:
            async with s.bind.connect() as conn:
                meta = await load_verified_production_revision(
                    conn, revision_id=rid, blob_store=blob_store)
        await eng.dispose()
    finally:
        readiness_mod.resolve_publication_readiness = orig
    assert meta["revision_id"] == rid


async def test_historical_0011_backup_manifest_restores_under_m11_binary(
    tmp_path, monkeypatch
):
    """M11-RECOVERY:09 — a valid pre-M11 backup restores without rewrite."""
    # Build a genuine 0011-era root: alembic-upgraded to 0011 only.
    src = tmp_path / "old" / "data"
    src.mkdir(parents=True)
    _alembic_upgrade(src, monkeypatch, "0011_m10_derived_spatial_execution")

    data = b"pre-m11-blob"
    bh = hashlib.sha256(data).hexdigest()
    p = _blob_file(src, bh)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    con = _db(src)
    pid = new_uuid()
    con.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'Old', ?, ?)", (pid, NOW, NOW))
    con.execute(
        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
        "VALUES (?, ?, ?, NULL, ?)",
        (bh, f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", len(data), NOW))
    con.execute(
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (?, ?, ?, 'reference', ?)", (new_uuid(), pid, bh, NOW))
    con.commit()
    con.close()

    backup_root = tmp_path / "old-backup"
    manifest = _assemble_backup(src, backup_root, "0011_m10_derived_spatial_execution")
    assert manifest["alembic_version"] == "0011_m10_derived_spatial_execution"

    dest = tmp_path / "restored-old"
    result = await restore(backup_root, dest)
    assert result["blob_count"] == 1
    con = _db(dest)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert ver == "0011_m10_derived_spatial_execution"
    assert "production_objects" not in tables  # nothing invented


async def test_0011_restore_invents_no_m11_tables_or_rows_then_normal_0012_migration_is_empty_additive(
    tmp_path, monkeypatch
):
    """M11-RECOVERY:10 — restore and migration remain separate."""
    src = tmp_path / "old2" / "data"
    src.mkdir(parents=True)
    _alembic_upgrade(src, monkeypatch, "0011_m10_derived_spatial_execution")

    backup_root = tmp_path / "old2-backup"
    _assemble_backup(src, backup_root, "0011_m10_derived_spatial_execution")
    dest = tmp_path / "restored-old2"
    await restore(backup_root, dest)

    # Ordinary (separate) migration afterwards: empty additive 0012 tables.
    _alembic_upgrade(dest, monkeypatch, "head")
    con = _db(dest)
    for tbl in ("production_objects", "production_revisions",
                "production_revision_closures", "production_revision_source_assets"):
        assert con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] == 0
    n_assets = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    con.close()
    assert n_assets == 0  # predecessor history unchanged (empty template root)


async def test_unsupported_backup_manifest_head_fails_closed(env, tmp_path):
    """M11-RECOVERY:11 — restore head negotiation is closed to 0011/0012."""
    tampered = tmp_path / "tampered-backup"
    shutil.copytree(env["backup"], tampered)
    manifest = json.loads((tampered / "backup-manifest.json").read_text())
    manifest["alembic_version"] = "0013_future_head"
    from soloring.domain.canonical import canonical_json_bytes

    (tampered / "backup-manifest.json").write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(rb.BackupManifestInvalid, match="alembic_version"):
        await restore(tampered, tmp_path / "nowhere")


async def test_backup_manifest_v1_field_grammar_is_unchanged_for_0011_and_0012(
    env,
):
    """M11-RECOVERY:12 — M11 changes head policy, not schema-1 fields."""
    manifest = json.loads((env["backup"] / "backup-manifest.json").read_text())
    assert set(manifest) == {
        "schema_version", "alembic_version", "database_sha256",
        "blob_hashes", "workflow_artifacts", "projects",
    }
    assert manifest["schema_version"] == 1
    # The strict parser accepts both supported heads and rejects new fields.
    raw0012 = (env["backup"] / "backup-manifest.json").read_bytes()
    doc = rb.parse_backup_manifest_v1(raw0012)
    assert doc["alembic_version"] == "0012_m11_reusable_production_revisions"
    bad = dict(doc)
    bad["m11_diagnostics"] = []
    from soloring.domain.canonical import canonical_json_bytes

    with pytest.raises(rb.BackupManifestInvalid, match="root fields"):
        rb.parse_backup_manifest_v1(canonical_json_bytes(bad))


async def test_backup_semantic_verifier_ignores_live_blob_media_type_drift_but_checks_closure_grammar_hash_and_size(
    env, tmp_path
):
    """M11-RECOVERY:13 — interpretation metadata is not a live dependency."""
    con = _db(env["src"])
    con.execute("UPDATE blobs SET detected_media_type = 'image/webp'")
    con.commit()
    con.close()
    # Live media drift alone must NOT block certification.
    backup_root = tmp_path / "drift-backup"
    assert await rb.backup(env["settings"], backup_root)
    # But closure-grammar corruption still does.
    con = _db(env["src"])
    con.execute(
        "UPDATE production_revision_closures SET size_bytes = size_bytes + 1")
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption):
        await rb.backup(env["settings"], tmp_path / "drift-backup-2")
