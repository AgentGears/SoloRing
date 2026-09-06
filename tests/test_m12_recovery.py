"""M12 recovery proofs (frozen R3 §21 M12-RECOVERY)."""

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
from soloring.recovery import RecoveryCorruption, restore
from soloring.settings import Settings

NOW = "2026-01-01T00:00:00.000Z"


def _db(root: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(root / "soloring.db"))
    con.row_factory = sqlite3.Row
    return con


# --- Module template: one real 0013 root with composition history ---------


def _seed_m12_state(data_dir: Path, settings: Settings) -> dict:
    """Project + M11 revision + Composition + mint + publish, real paths."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from soloring.composition.service import create_composition, mint_occurrence
    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.composition.readiness import publish_composition_revision

    pid = "11111111-1111-1111-1111-111111111111"
    bh = hashlib.sha256(b"m12-recovery").hexdigest()
    prid, pobj = ("22222222-2222-2222-2222-222222222222",
                  "33333333-3333-3333-3333-333333333333")
    from soloring.domain.canonical import canonical_hash, canonical_json_str as _cj
    from soloring.production.canonical import RetainedBlobClosure
    from soloring.production.canonical import (
        production_revision_snapshot_json as _prsj,
        production_revision_snapshot_hash as _prsh,
    )
    closure = RetainedBlobClosure(blob_hash=bh, size_bytes=12, media_type=None)
    pr_sj, pr_sh = _prsj(closure), _prsh(closure)

    async def run() -> dict:
        eng = create_async_engine(
            f"sqlite+aiosqlite:///{(data_dir / 'soloring.db').as_posix()}")
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(bind=eng, expire_on_commit=False,
                                     class_=AsyncSession)
        async with factory() as s:
            async with s.bind.connect() as conn:
                await conn.execute(text(
                    "INSERT INTO projects (id, name, created_at, updated_at) "
                    "VALUES (:id, 'P', :n, :n)"), {"id": pid, "n": NOW})
                await conn.execute(text(
                    "INSERT INTO blobs (hash, path, size_bytes, "
                    "detected_media_type, created_at) VALUES "
                    "(:h, :p, 12, NULL, :n)"),
                    {"h": bh, "p": f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", "n": NOW})
                await conn.execute(text(
                    "INSERT INTO production_objects (id, project_id, name, "
                    "created_at, updated_at) VALUES (:o, :p, 'Obj', :n, :n)"),
                    {"o": pobj, "p": pid, "n": NOW})
                await conn.execute(text(
                    "INSERT INTO production_revisions (id, production_object_id, "
                    "revision_number, snapshot_json, snapshot_hash, created_at) "
                    "VALUES (:r, :o, 1, :sj, :sh, :n)"),
                    {"r": prid, "o": pobj, "sj": pr_sj, "sh": pr_sh, "n": NOW})
                await conn.execute(text(
                    "INSERT INTO production_revision_closures "
                    "(production_revision_id, contract_key, contract_version, "
                    "blob_hash, size_bytes, media_type) VALUES "
                    "(:r, 'retained_blob', 1, :bh, 12, NULL)"),
                    {"r": prid, "bh": bh})
                await conn.execute(text(
                    "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
                    "VALUES (:a, :p, :bh, 'reference', :n)"),
                    {"a": "55555555-5555-5555-5555-555555555555",
                     "p": pid, "bh": bh, "n": NOW})
                await conn.execute(text(
                    "INSERT INTO production_revision_source_assets "
                    "(production_revision_id, asset_id, created_at) VALUES "
                    "(:r, :a, :n)"),
                    {"r": prid, "a": "55555555-5555-5555-5555-555555555555",
                     "n": NOW})
                await conn.commit()
        blob_file = settings.blob_dir / "sha256" / bh[:2] / bh[2:4] / bh
        blob_file.parent.mkdir(parents=True, exist_ok=True)
        blob_file.write_bytes(b"m12-recovery")
        async with factory() as s:
            comp = await create_composition(s, pid, name="Lobby", description=None)
            spec = {
                "display_name": "Chair 7",
                "source": {"kind": "production_revision", "revision_id": prid},
                "visible": True,
                "transform": {"translation_mm": [0, 0, 0],
                              "rotation_udeg": [0, 0, 0]},
            }
            m = await mint_occurrence(
                s, comp["id"], scope="composition_working_state",
                expected_working_version=0, spec=spec)
            rev, created = await publish_composition_revision(
                s, comp["id"], expected_working_version=1)
            assert created
        await eng.dispose()
        return {"project_id": pid, "composition_id": comp["id"],
                "occurrence_id": m["occurrence_id"],
                "revision_id": rev["revision_id"]}

    return asyncio.run(run())


def _stamp_head(data_dir: Path, head: str) -> None:
    from alembic import command
    from alembic.config import Config

    import soloring.settings as settings_mod
    from soloring.settings import BASE_DIR

    prev = settings_mod._settings
    settings_mod._settings = Settings(data_dir=data_dir)
    try:
        cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
        cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
        command.stamp(cfg, head)
    finally:
        settings_mod._settings = prev


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = tmp_path_factory.mktemp("m12_recovery")
    data_dir = base / "data"
    data_dir.mkdir()
    settings = Settings(data_dir=data_dir)
    seeded = _seed_m12_state(data_dir, settings)
    _stamp_head(data_dir, "0013_m12_composition_occurrences")
    backup_root = base / "backup"
    asyncio.run(rb.backup(settings, backup_root))
    return {"data_dir": data_dir, "settings": settings, "seed": seeded,
            "backup_root": backup_root}


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


def test_current_backup_requires_0013_head(template):
    """M12-RECOVERY:01."""
    assert rb.EXPECTED_ALEMBIC_HEAD == "0013_m12_composition_occurrences"
    manifest = json.loads(
        (template["backup_root"] / "backup-manifest.json").read_text())
    assert manifest["alembic_version"] == "0013_m12_composition_occurrences"
    assert rb.SUPPORTED_RESTORE_ALEMBIC_HEADS == {
        "0011_m10_derived_spatial_execution",
        "0012_m11_reusable_production_revisions",
        "0013_m12_composition_occurrences",
    }


def test_0013_blob_fk_inventory_remains_exactly_seven_paths(env):
    """M12-RECOVERY:02."""
    con = _db(env["src"])
    try:
        found = rb._blob_fk_inventory(con)
    finally:
        con.close()
    assert found == set(rb.M11_BLOB_FK_COLUMNS)  # unchanged seven
    assert ("composition_working_occurrences", "production_revision_id") not in found


def test_restore_0013_verifies_composition_snapshots_and_projections(
    env, tmp_path
):
    """M12-RECOVERY:05 — full roundtrip with M12 history."""
    dest = tmp_path / "restored"
    result = await_restore(env["backup"], dest)
    con = _db(dest)
    try:
        ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        n = con.execute("SELECT COUNT(*) FROM composition_revisions").fetchone()[0]
    finally:
        con.close()
    assert ver == "0013_m12_composition_occurrences"
    assert n == 1


def await_restore(backup, dest):
    return asyncio.run(restore(backup, dest))


def test_restore_0013_verifies_identity_operation_lineage(env, tmp_path):
    """M12-RECOVERY:06 — lineage verification accepts the real mint."""
    dest = tmp_path / "restored"
    await_restore(env["backup"], dest)
    # verifier accepts the template: also prove it rejects corruption
    bad = tmp_path / "bad" / "data"
    shutil.copytree(env["src"], bad)
    con = _db(bad)
    con.execute(
        "DELETE FROM composition_identity_operation_targets "
        "WHERE occurrence_id = (SELECT occurrence_id FROM "
        "composition_identity_operation_targets LIMIT 1)")
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption, match="birth|operation evidence"):
        rb._verify_m12_composition_state(bad / "soloring.db")


def test_restore_0013_rejects_terminated_occurrence_in_working_state(
    env, tmp_path
):
    """M12-RECOVERY:07."""
    bad = tmp_path / "bad" / "data"
    shutil.copytree(env["src"], bad)
    con = _db(bad)
    # add a terminated edge for the still-working occurrence (FK-bypassed)
    con.execute("PRAGMA foreign_keys=OFF")
    op = "44444444-4444-4444-4444-444444444444"
    occ = con.execute(
        "SELECT occurrence_id FROM composition_working_occurrences LIMIT 1"
    ).fetchone()[0]
    cid = con.execute("SELECT composition_id FROM "
                      "composition_working_occurrences LIMIT 1").fetchone()[0]
    con.execute("UPDATE compositions SET working_version = 2 "
                "WHERE id = (SELECT composition_id FROM "
                "composition_working_occurrences LIMIT 1)")
    from soloring.composition.canonical import (
        build_impact_value,
        build_operation_value,
        build_request_value,
        impact_fingerprint as _ifp,
        operation_hash as _oh,
        operation_json as _oj,
        request_fingerprint as _rfp,
    )
    req_v = build_request_value(
        composition_id=cid, kind="remove",
        source_occurrence_ids=[occ], target_specs=[])
    imp_v = build_impact_value(
        composition_id=cid, working_version=1,
        source_occurrence_ids=[occ],
        source_dispositions=[
            {"occurrence_id": occ, "active": True,
             "in_working_state": True}],
        live_blocking_references=[])
    req_fp, imp_fp = _rfp(req_v), _ifp(imp_v)
    fake_value = build_operation_value(
        composition_id=cid, kind="remove",
        working_version_before=1, working_version_after=2,
        request_fp=req_fp, impact_fp=imp_fp,
        sources=[{"occurrence_id": occ, "terminates_identity": True}],
        targets=[],
    )
    con.execute(
        "INSERT INTO composition_identity_operations (id, composition_id, "
        "operation_kind, working_version_before, working_version_after, "
        "request_fingerprint, impact_fingerprint, operation_json, "
        "operation_hash, created_at) VALUES (?, ?, 'remove', 1, 2, ?, ?, "
        "?, ?, ?)",
        (op, cid, req_fp, imp_fp, _oj(fake_value), _oh(fake_value), NOW))
    con.execute(
        "INSERT INTO composition_identity_operation_sources (composition_id, "
        "operation_id, occurrence_id, terminates_identity) "
        "VALUES (?, ?, ?, 1)", (cid, op, occ))
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption,
                       match="terminated occurrence remains"):
        rb._verify_m12_composition_state(bad / "soloring.db")


def test_restore_unknown_head_fails_closed(env, tmp_path):
    """M12-RECOVERY:08."""
    tampered = tmp_path / "tampered"
    shutil.copytree(env["backup"], tampered)
    manifest = json.loads((tampered / "backup-manifest.json").read_text())
    manifest["alembic_version"] = "0014_future"
    from soloring.domain.canonical import canonical_json_bytes

    (tampered / "backup-manifest.json").write_bytes(
        canonical_json_bytes(manifest))
    with pytest.raises(rb.BackupManifestInvalid, match="alembic_version"):
        await_restore(tampered, tmp_path / "nowhere")


def test_restore_0011_and_0012_policies(tmp_path, monkeypatch):
    """M12-RECOVERY:03/:04 — historical restores remain exact."""
    from alembic import command
    from alembic.config import Config

    from soloring.settings import BASE_DIR
    import soloring.settings as settings_mod

    def _upgrade(data_dir, target):
        monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
        monkeypatch.setattr(settings_mod, "_settings", None)
        cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
        cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
        command.upgrade(cfg, target)

    for head, blob_paths, m12_absent in (
        ("0011_m10_derived_spatial_execution", 6, True),
        ("0012_m11_reusable_production_revisions", 7, True),
    ):
        root = tmp_path / head / "data"
        root.mkdir(parents=True)
        _upgrade(root, head)
        backup_root = tmp_path / f"backup-{head}"
        manifest = _assemble_backup(root, backup_root, head)
        assert manifest["alembic_version"] == head
        dest = tmp_path / f"restored-{head}"
        await_restore(backup_root, dest)
        con = _db(dest)
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        assert "compositions" not in tables  # no M12 state invented
        assert "production_objects" not in tables or head != "0011_m10_derived_spatial_execution"


def _assemble_backup(root: Path, dest: Path, alembic_version: str) -> dict:
    dest.mkdir(parents=True)
    db = root / "soloring.db"
    shutil.copy(db, dest / "soloring.db")
    live = rb._enumerate_liveness(
        root / "soloring.db", rb._blob_fk_policy_for_head(alembic_version))
    manifest = {
        "schema_version": 1,
        "alembic_version": alembic_version,
        "database_sha256": hashlib.sha256(
            (dest / "soloring.db").read_bytes()).hexdigest(),
        "blob_hashes": live.blob_hashes,
        "workflow_artifacts": [
            {"kind": k, "sha256": h} for k, h in live.artifacts],
        "projects": live.projects,
    }
    for h in live.blob_hashes:
        rel = f"sha256/{h[:2]}/{h[2:4]}/{h}"
        src = root / "blobs" / rel
        if src.is_file():
            out = dest / "blobs" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, out)
    from soloring.domain.canonical import canonical_json_bytes

    (dest / "backup-manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def test_restore_rejects_self_consistent_dependency_omission_by_rederivation(
    env, tmp_path
):
    """M12-RECOVERY:10 — snapshot + rows collude; rederivation catches."""
    bad = tmp_path / "bad" / "data"
    shutil.copytree(env["src"], bad)
    con = _db(bad)
    rev = con.execute(
        "SELECT id FROM composition_revisions LIMIT 1").fetchone()[0]
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    snap = json.loads(con.execute(
        "SELECT snapshot_json FROM composition_revisions WHERE id = ?",
        (rev,)).fetchone()[0])
    snap["dependencies"]["production_revision_ids"] = []
    con.execute(
        "UPDATE composition_revisions SET snapshot_json = ?, snapshot_hash = ? "
        "WHERE id = ?",
        (canonical_json_str(snap), canonical_hash(snap), rev))
    con.execute(
        "DELETE FROM composition_revision_production_dependencies "
        "WHERE composition_revision_id = ?", (rev,))
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption, match="rederived"):
        rb._verify_m12_composition_state(bad / "soloring.db")


def test_restore_rejects_noncanonical_transform_or_invalid_lineage_timeline(
    env, tmp_path
):
    """M12-RECOVERY:11 — noncanonical rotation stored in immutable projection."""
    bad = tmp_path / "bad" / "data"
    shutil.copytree(env["src"], bad)
    con = _db(bad)
    rev = con.execute(
        "SELECT id FROM composition_revisions LIMIT 1").fetchone()[0]
    # store an out-of-range rotation in projection + snapshot consistently
    snap = json.loads(con.execute(
        "SELECT snapshot_json FROM composition_revisions WHERE id = ?",
        (rev,)).fetchone()[0])
    # pick a value outside [-180000000, 180000000): 180000000 exactly
    snap["occurrences"][0]["transform"]["rotation_udeg"] = [180000000, 0, 0]
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    con.execute(
        "UPDATE composition_revisions SET snapshot_json = ?, snapshot_hash = ? "
        "WHERE id = ?",
        (canonical_json_str(snap), canonical_hash(snap), rev))
    con.execute(
        "UPDATE composition_revision_occurrences SET yaw_udeg = 180000000 "
        "WHERE composition_revision_id = ?", (rev,))
    con.commit()
    con.close()
    with pytest.raises(RecoveryCorruption, match="normalized"):
        rb._verify_m12_composition_state(bad / "soloring.db")


def test_recovery_never_repairs_or_retargets_occurrence_identity(env):
    """M12-RECOVERY:09 — verifier is read-only for identity/history."""
    before = (env["src"] / "soloring.db").read_bytes()
    rb._verify_m12_composition_state(env["src"] / "soloring.db")
    after = (env["src"] / "soloring.db").read_bytes()
    assert before == after  # byte-identical: no repair/retarget writes


def test_restore_0011_uses_frozen_six_path_policy_and_invents_no_m12(
    tmp_path, monkeypatch
):
    """Alias owner for the 0011 leg of the historical-restore proof."""
    from alembic import command
    from alembic.config import Config

    from soloring.settings import BASE_DIR
    import soloring.settings as settings_mod

    root = tmp_path / "p0011" / "data"
    root.mkdir(parents=True)
    monkeypatch.setenv("SOLORING_DATA_DIR", str(root))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    command.upgrade(cfg, "0011_m10_derived_spatial_execution")
    backup_root = tmp_path / "b0011"
    manifest = _assemble_backup(root, backup_root,
                                "0011_m10_derived_spatial_execution")
    assert manifest["alembic_version"] == "0011_m10_derived_spatial_execution"
    assert rb._blob_fk_policy_for_head(
        "0011_m10_derived_spatial_execution") == rb.PRE_M11_BLOB_FK_COLUMNS
    dest = tmp_path / "r0011"
    await_restore(backup_root, dest)
    con = _db(dest)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "compositions" not in tables
    assert "production_objects" not in tables


def test_restore_0012_uses_seven_path_policy_and_invents_no_m12(
    tmp_path, monkeypatch
):
    """Alias owner for the 0012 leg of the historical-restore proof."""
    from alembic import command
    from alembic.config import Config

    from soloring.settings import BASE_DIR
    import soloring.settings as settings_mod

    root = tmp_path / "p0012" / "data"
    root.mkdir(parents=True)
    monkeypatch.setenv("SOLORING_DATA_DIR", str(root))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    command.upgrade(cfg, "0012_m11_reusable_production_revisions")
    backup_root = tmp_path / "b0012"
    manifest = _assemble_backup(
        root, backup_root, "0012_m11_reusable_production_revisions")
    assert manifest["alembic_version"] == "0012_m11_reusable_production_revisions"
    assert rb._blob_fk_policy_for_head(
        "0012_m11_reusable_production_revisions") == rb.M11_BLOB_FK_COLUMNS
    dest = tmp_path / "r0012"
    await_restore(backup_root, dest)
    con = _db(dest)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "compositions" not in tables  # no empty M12 schema invented
    assert "production_objects" in tables
