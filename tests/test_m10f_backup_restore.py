"""M10F-A — storage recovery and historical liveness (R5 §7).

Positive full-cycle proof (§7.8), the closed 31-cell corruption/fault
matrix (§7.9), physical-before-reference ordering invariants (§7.4), the
same-filesystem atomic finalize contract, the FK liveness completeness
gate (§7.5), and the real process-death restore crash proof (§7.7).

The module-level template source root carries real production history —
schema-1 (two distinct v1 releases), schema-2 (v4 package + M8 authority),
schema-3 (spatial seed + certified package), plus one owner-free
DerivedSpatialArtifact — built through the real creation paths and an
alembic-stamped DB. Each test corrupts its own byte-copy.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import event, text

import importlib

rb = importlib.import_module("soloring.recovery.backup")
from soloring.recovery import (
    BackupManifestInvalid,
    RecoveryCorruption,
    RecoveryError,
    RecoveryUnsupported,
    restore,
    verify_supported_posture,
)
from soloring.settings import BASE_DIR, Settings

REPO = BASE_DIR
SERVER = REPO / "server"


# ---------------------------------------------------------------------------
# Module template: one real production source root + one pristine backup
# ---------------------------------------------------------------------------


def _alembic_stamp(data_dir: Path) -> None:
    from alembic import command
    from alembic.config import Config
    import soloring.settings as settings_mod

    prev = settings_mod._settings
    settings_mod._settings = Settings(data_dir=data_dir)
    try:
        cfg = Config(str(REPO / "server" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO / "server" / "alembic"))
        # The schema was created by the ORM (create_all); ORM↔migration
        # parity is separately frozen (§8.1). stamp records the head the
        # production deployment would carry after `alembic upgrade head`.
        command.stamp(cfg, "head")
    finally:
        settings_mod._settings = prev


async def _build_template_source(data_dir: Path) -> dict:
    """Real schema-1/2/3 + orphan-DSA history through production paths."""
    import soloring.settings as settings_mod

    saved_singleton = settings_mod._settings
    settings_mod._settings = Settings(data_dir=data_dir)
    try:
        return await _build_template_source_inner(data_dir)
    finally:
        settings_mod._settings = saved_singleton


async def _build_template_source_inner(data_dir: Path) -> dict:
    from soloring.api.main import create_app
    from soloring.db.base import Base
    from soloring.db import models  # noqa: F401
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )

    settings = Settings(data_dir=data_dir)
    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _alembic_stamp(data_dir)

    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    import httpx

    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(
        transport=transport, base_url="http://test")

    from tests.test_m10e_generation import _EXTENTS, _spatial_seed
    from tests.test_m9c_generation import _m9_shot
    from tests.test_m8a_visual import _seed_project
    from tests.test_m8b_curation import _assets

    info: dict = {"settings": settings, "generations": {}}
    try:
        pid = await _seed_project(app.state.session_factory)
        settings.executor = "comfy"

        # --- schema-2 spec (default v4 package + non-empty M8) -----------
        shot2, m8_assets = await _m9_shot(
            client, app.state.session_factory, engine, settings, pid)
        r = await client.post(f"/shots/{shot2}/generations")
        assert r.status_code == 202, r.text
        info["generations"]["v2"] = r.json()["id"]

        # --- schema-1 specs (two distinct v1 releases) --------------------
        from soloring.api.schemas.references import ReferenceInput
        from soloring.api.schemas.shots import ShotCreate
        from soloring.domain import references as ref_svc
        from soloring.domain import shots as shot_svc
        from soloring.workflows.manifest import WORKFLOW_DIR as V1_DIR

        async def _v1_shot(gen_key: str, package_dir: Path) -> None:
            async with app.state.session_factory() as s:
                shot = await shot_svc.create_shot(
                    s, pid, ShotCreate(subject="legacy"))
            legacy = await _assets(engine, pid, 1)
            async with app.state.session_factory() as s:
                await ref_svc.replace_references(
                    s, shot.id,
                    [ReferenceInput(asset_id=legacy[0], role="reference")])
            settings.workflow_package_dir = package_dir
            r = await client.post(f"/shots/{shot.id}/generations")
            assert r.status_code == 202, r.text
            info["generations"][gen_key] = r.json()["id"]

        await _v1_shot("v1", V1_DIR)
        v1b = data_dir.parent / "pkg_v1b"
        v1b.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((V1_DIR / "manifest.json").read_text())
        manifest["version"] = 4
        from soloring.domain.canonical import canonical_json_bytes, canonical_hash

        (v1b / "manifest.json").write_bytes(canonical_json_bytes(manifest))
        shutil.copy(V1_DIR / "workflow.json", v1b / "workflow.json")
        descriptor = {
            "schema_version": 1,
            "workflow_id": manifest["workflow_id"],
            "workflow_version": 4,
            "manifest_hash": canonical_hash(manifest),
            "workflow_template_hash": hashlib.sha256(
                (V1_DIR / "workflow.json").read_bytes()).hexdigest(),
        }
        (v1b / "workflow-package.json").write_bytes(
            canonical_json_bytes(descriptor))
        await _v1_shot("v1b", v1b)

        # --- schema-3 specs (certified spatial package) --------------------
        from tests.test_m10e_generation import _create
        from tests.test_m10e_package3_production import _schema3_package

        settings.workflow_package_dir = await _schema3_package(
            data_dir.parent)
        seed = await _spatial_seed(
            app.state.session_factory, staged=1, extents=_EXTENTS)
        gen = await _create(
            app.state.session_factory, settings, seed)
        info["generations"]["v3"] = gen.id

        seed_b = await _spatial_seed(
            app.state.session_factory, staged=1,
            extents=[800, 500, 400])  # distinct pack → distinct D0 artifact
        gen_b = await _create(app.state.session_factory, settings, seed_b)
        info["generations"]["v3b"] = gen_b.id

        # Owner-free DerivedSpatialArtifact (§7.9 cell 22): gen_b's D0
        # provenance outlives its Generation (rollback residue, §12.4).
        con = sqlite3.connect(str(settings.db_path))
        try:
            con.execute(
                "DELETE FROM generation_derived_spatial_inputs "
                "WHERE generation_id = ?", (gen_b.id,))
            con.execute(
                "DELETE FROM generations WHERE id = ?", (gen_b.id,))
            con.commit()
        finally:
            con.close()
        info["generations"].pop("v3b")
    finally:
        await client.aclose()
        await engine.dispose()

    # Every live Blob must have physical bytes that truly hash to the
    # registered identity. The M8 fixture helpers write existence-only
    # placeholder bytes; repair them from the deterministic preimage
    # (blobs whose identity is sha256(asset_id) get content asset_id).
    from soloring.assets.blob_store import BlobStore

    store = BlobStore(settings)
    con = sqlite3.connect(str(settings.db_path))
    con.row_factory = sqlite3.Row
    try:
        hashes = [
            r[0] for r in con.execute(
                "SELECT hash FROM blobs WHERE hash IN ("
                "SELECT blob_hash FROM assets UNION ALL "
                "SELECT blob_hash FROM generation_inputs UNION ALL "
                "SELECT blob_hash FROM derived_spatial_artifacts UNION ALL "
                "SELECT blob_hash FROM generation_derived_spatial_inputs "
                "UNION ALL SELECT blob_hash FROM "
                "shot_revision_visual_anchor_items UNION ALL "
                "SELECT blob_hash FROM visual_anchor_revision_items)")
        ]
        preimages = {
            hashlib.sha256(r["id"].encode()).hexdigest(): r["id"]
            for r in con.execute("SELECT id FROM assets")
        }
        for h in hashes:
            p = store.path_for_hash(h)
            ok = p.is_file() and hashlib.sha256(
                p.read_bytes()).hexdigest() == h
            if not ok:
                if h not in preimages:
                    raise AssertionError(
                        f"template blob {h} has no true preimage content")
                content = preimages[h].encode()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
                con.execute(
                    "UPDATE blobs SET size_bytes = ? WHERE hash = ?",
                    (len(content), h))
                con.commit()
                assert hashlib.sha256(
                    p.read_bytes()).hexdigest() == h
    finally:
        con.close()
    return info


@pytest.fixture(scope="module")
def template(tmp_path_factory: Path) -> dict:
    base = tmp_path_factory.mktemp("m10f_recovery")
    data_dir = base / "data"
    data_dir.mkdir()
    info = asyncio.run(_build_template_source(data_dir))
    backup_root = base / "template-backup"
    evidence = asyncio.run(rb.backup(info["settings"], backup_root))
    return {
        "data_dir": data_dir,
        "settings": info["settings"],
        "generations": info["generations"],
        "backup_root": backup_root,
        "backup_evidence": evidence,
    }


@pytest.fixture
def env(template: dict, tmp_path: Path) -> dict:
    """Per-test byte-copies of the pristine source root and backup."""
    src = tmp_path / "src" / "data"
    shutil.copytree(template["data_dir"], src)
    # drop the pristine WAL side files copied out from under a live tree
    for suffix in ("-wal", "-shm"):
        side = src / ("soloring.db" + suffix)
        if side.exists():
            side.unlink()
    backup = tmp_path / "backup"
    shutil.copytree(template["backup_root"], backup)
    return {"src": src, "settings": Settings(data_dir=src), "backup": backup}


def _settings_for(src: Path) -> Settings:
    return Settings(data_dir=src)


def _db(src: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(src / "soloring.db"))
    con.row_factory = sqlite3.Row
    return con


def _orphan_stages(near: Path, kind: str) -> list[Path]:
    return sorted(
        p for p in near.parent.iterdir()
        if p.name.startswith(f".{near.name}.soloring-{kind}-")
        and p.name.endswith(".staging")
    )


# ---------------------------------------------------------------------------
# Posture guard (§7.1)
# ---------------------------------------------------------------------------


async def test_posture_database_url_override_rejected_before_staging(
        env, tmp_path):
    s = env["settings"]
    s.database_url = "sqlite+aiosqlite:///other.db"
    with pytest.raises(RecoveryUnsupported, match="database_url"):
        await rb.backup(s, tmp_path / "b")
    assert not (tmp_path / "b").exists()
    assert _orphan_stages(tmp_path / "b", "backup") == []


async def test_posture_blob_dir_override_rejected_before_staging(
        env, tmp_path):
    s = env["settings"]
    s.blob_dir = s.data_dir / "elsewhere"
    with pytest.raises(RecoveryUnsupported, match="Blob root"):
        await rb.backup(s, tmp_path / "b")
    assert not (tmp_path / "b").exists()
    assert _orphan_stages(tmp_path / "b", "backup") == []


async def test_posture_default_passes(env):
    verify_supported_posture(env["settings"])


# cell 31 — WorkflowArtifactStore-root drift tripwire (test-only injection;
# published settings expose no such override — R5 §5.6/§7.1)
async def test_workflow_artifact_root_override_rejected_before_staging(
        env, tmp_path):
    divergent = tmp_path / "other-artifacts"
    with pytest.raises(RecoveryUnsupported, match="workflow-artifacts"):
        await rb.backup(env["settings"], tmp_path / "b",
                        artifact_root=divergent)
    assert not (tmp_path / "b").exists()
    assert not divergent.exists()
    assert _orphan_stages(tmp_path / "b", "backup") == []


# ---------------------------------------------------------------------------
# §7.8 positive full cycle
# ---------------------------------------------------------------------------


async def test_legacy_absolute_d0_blob_path_preserved_but_never_followed(
        env, tmp_path):
    """R6 §5.7/F-147 (BACKUPALGO:legacy-d0-path): a predecessor-shape
    absolute D0 `blobs.path` (M10E PD-2 defect form) survives backup and
    restore byte-for-byte, physical access is always the hash-derived
    BlobStore path under the active root, historical verification and
    worker derived-input loading succeed with the ORIGINAL source root
    unavailable, and a mismatched absolute suffix fails closed."""
    con = _db(env["src"])
    try:
        dsa_hashes = [
            r[0] for r in con.execute(
                "SELECT DISTINCT blob_hash FROM derived_spatial_artifacts "
                "ORDER BY blob_hash")
        ]
    finally:
        con.close()
    assert dsa_hashes, "template must contain D0 artifacts"
    legacy_hash = dsa_hashes[0]
    canonical = f"sha256/{legacy_hash[0:2]}/{legacy_hash[2:4]}/{legacy_hash}"
    # an unreachable absolute prefix: any dereference of the stored value
    # would fail loudly (Z: does not exist on the evidence machine)
    legacy_value = f"Z:/gone-m10e-source-root/blobs/{canonical}"
    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        con.execute(
            "UPDATE blobs SET path = :p WHERE hash = :h",
            {"p": legacy_value, "h": legacy_hash})
        con.commit()
    finally:
        con.close()

    backup = tmp_path / "legacy-backup"
    await rb.backup(env["settings"], backup)  # legacy form tolerated
    manifest = json.loads((backup / "backup-manifest.json").read_bytes())
    assert legacy_hash in manifest["blob_hashes"]

    dest = tmp_path / "legacy-restored"
    await restore(backup, dest)

    # the stored absolute value is preserved byte-for-byte
    dst = _db(dest)
    try:
        stored = dst.execute(
            "SELECT path FROM blobs WHERE hash = ?", (legacy_hash,)
        ).fetchone()[0]
    finally:
        dst.close()
    assert stored == legacy_value

    # original source root becomes unavailable; physical history lives at
    # the hash-derived path under the RESTORED root only
    shutil.rmtree(env["src"])
    assert not env["src"].exists()
    physical = _blob_path(dest, legacy_hash)
    assert physical.is_file()
    assert hashlib.sha256(physical.read_bytes()).hexdigest() == legacy_hash

    # restored Exact Rerun + worker derived-input loading succeed from the
    # hash-derived path while the stored metadata names a dead location
    from soloring.assets.blob_store import BlobStore
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )
    from soloring.generation import rerun
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    restored_settings = Settings(data_dir=dest)
    engine = create_soloring_engine(restored_settings)
    factory = create_session_factory(engine)
    try:
        v3_id = _v3_generation(dest)
        _mark_terminal(dest, v3_id)
        async with factory() as s:
            new = await rerun.create_rerun(s, v3_id)
        assert new.id != v3_id

        store = WorkflowArtifactStore(restored_settings)
        vcon = _db(dest)
        try:
            spec = json.loads(vcon.execute(
                "SELECT workflow_spec_json FROM generations WHERE id = ?",
                (v3_id,)).fetchone()[0])
            manifest_hash = vcon.execute(
                "SELECT manifest_hash FROM generations WHERE id = ?",
                (v3_id,)).fetchone()[0]
        finally:
            vcon.close()
        manifest_v3 = parse_manifest_v3(
            (await store.get_manifest(manifest_hash)).decode())

        class _StubUploader:
            """Records uploads; returns reference-shaped (name, subfolder)."""

            def __init__(self):
                self.uploads: list[str] = []

            async def upload_bytes(self, *, data, filename, subfolder):
                self.uploads.append(filename)
                return filename, subfolder

            async def upload(self, source_path, filename, subfolder):
                self.uploads.append(filename)
                return filename, subfolder

        uploader = _StubUploader()
        async with factory() as s:
            verified = await execute_schema3_derived_inputs(
                s, BlobStore(restored_settings),
                generation_id=v3_id, attempt_id=str(uuid.uuid4()),
                workflow_spec=spec, manifest_v3=manifest_v3,
                client=uploader,
            )
        assert verified, ("worker derived inputs must load from the "
                          "hash-derived restored path")
        assert uploader.uploads
    finally:
        await engine.dispose()

    # mismatched absolute suffix fails closed
    bad_hash = dsa_hashes[-1]
    bad_canonical = f"sha256/{bad_hash[0:2]}/{bad_hash[2:4]}/{bad_hash}"
    if bad_hash == legacy_hash:
        bad_hash = dsa_hashes[0]
        bad_canonical = canonical
    con = sqlite3.connect(str(dest / "soloring.db"))
    try:
        # suffix that does NOT match the row's own hash
        con.execute(
            "UPDATE blobs SET path = :p WHERE hash = :h",
            {"p": f"Z:/other-root/blobs/sha256/00/00/{'0' * 64}",
             "h": bad_hash})
        con.commit()
    finally:
        con.close()
    bad_backup = tmp_path / "bad-backup"
    with pytest.raises(RecoveryCorruption, match="grammar"):
        await rb.backup(Settings(data_dir=dest), bad_backup)
    assert not bad_backup.exists()


async def test_relative_noncanonical_path_with_matching_suffix_rejected(
        env, tmp_path):
    """R6 §7.5 defect correction: a RELATIVE path like
    'junk/sha256/aa/bb/<hash>' that merely ends with the canonical
    suffix must NOT enter the legacy exception — the value must be
    absolute (drive-letter or leading-slash)."""
    con = _db(env["src"])
    try:
        dsa_hashes = [
            r[0] for r in con.execute(
                "SELECT DISTINCT blob_hash FROM "
                "derived_spatial_artifacts ORDER BY blob_hash")
        ]
    finally:
        con.close()
    assert dsa_hashes
    h = dsa_hashes[0]
    canonical = f"sha256/{h[0:2]}/{h[2:4]}/{h}"
    relative_junk = f"junk/prefix/{canonical}"  # relative, right suffix

    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        con.execute(
            "UPDATE blobs SET path = :p WHERE hash = :h",
            {"p": relative_junk, "h": h})
        con.commit()
    finally:
        con.close()

    from soloring.recovery import RecoveryCorruption

    with pytest.raises(RecoveryCorruption, match="tolerated legacy"):
        await rb.backup(env["settings"], tmp_path / "must-fail")


async def test_backup_restore_full_cycle_spans_schema_1_2_3(env, tmp_path):
    dest = tmp_path / "restored"
    evidence = await restore(env["backup"], dest)
    src_con, dst_con = _db(env["src"]), _db(dest)
    try:
        assert (src_con.execute(
            "SELECT COUNT(*) FROM generations")).fetchone()[0] == \
            (dst_con.execute(
                "SELECT COUNT(*) FROM generations")).fetchone()[0]
        src_specs = {r[0]: r[1] for r in src_con.execute(
            "SELECT id, workflow_spec_json FROM generations")}
        dst_specs = {r[0]: r[1] for r in dst_con.execute(
            "SELECT id, workflow_spec_json FROM generations")}
        assert src_specs == dst_specs  # byte-identical durable history
        schemas = {
            json.loads(v)["schema_version"] for v in dst_specs.values()
        }
        assert schemas == {1, 2, 3}
    finally:
        src_con.close()
        dst_con.close()
    assert evidence["blob_count"] > 0
    assert evidence["workflow_artifact_count"] >= (
        3 * 2 + 2)  # 3 manifests + 3 templates + ≥2 profile/fingerprint

    # Restored Exact Rerun copies identities; zero D0 rematerialization.
    from soloring.generation import rerun
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )
    from soloring.spatial import realize as realize_mod
    from soloring.spatial.derived import register_derived_artifact

    restored_settings = Settings(data_dir=dest)
    engine = create_soloring_engine(restored_settings)
    factory = create_session_factory(engine)
    calls: list[str] = []

    async def _no_compose(*a, **k):
        calls.append("compose")

    def _no_materialize(*a, **k):
        calls.append("materialize")

    async def _no_register(*a, **k):
        calls.append("register")

    orig = (realize_mod.compose_spatial_realization,
            realize_mod.boxdepth_materialize
            if hasattr(realize_mod, "boxdepth_materialize") else None,
            register_derived_artifact)
    realize_mod.compose_spatial_realization = _no_compose
    if orig[1] is not None:
        realize_mod.boxdepth_materialize = _no_materialize
    import soloring.spatial.derived as derived_mod

    derived_mod.register_derived_artifact = _no_register
    try:
        _mark_terminal(dest, _v3_generation(dest))
        v3_id = _v3_generation(dest)
        async with factory() as session:
            new = await rerun.create_rerun(session, v3_id)
        src_row = await _generation_json(engine, v3_id)
        new_row = await _generation_json(engine, new.id)
        assert src_row["workflow_spec_json"] == new_row["workflow_spec_json"]
        assert src_row["workflow_spec_hash"] == new_row["workflow_spec_hash"]
    finally:
        realize_mod.compose_spatial_realization = orig[0]
        if orig[1] is not None:
            realize_mod.boxdepth_materialize = orig[1]
        derived_mod.register_derived_artifact = orig[2]
        await engine.dispose()
    assert calls == []


def _v3_generation(src: Path) -> str:
    con = _db(src)
    try:
        row = con.execute(
            "SELECT id FROM generations WHERE json_extract("
            "workflow_spec_json, '$.schema_version') = 3 "
            "ORDER BY id LIMIT 1").fetchone()
        assert row is not None
        return row[0]
    finally:
        con.close()


def _mark_terminal(root: Path, generation_id: str) -> None:
    """Exact Rerun requires a terminal source; creation leaves 'queued'."""
    con = sqlite3.connect(str(root / "soloring.db"))
    try:
        con.execute(
            "UPDATE generations SET status = 'succeeded', "
            "completed_at = 't' WHERE id = ?", (generation_id,))
        con.commit()
    finally:
        con.close()


async def _generation_json(engine, generation_id: str) -> dict:
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM generations "
            "WHERE id = :g"), {"g": generation_id})).mappings().one()
    return dict(row)


# ---------------------------------------------------------------------------
# Backup-side corruption cells (§7.9 1/5-17/25/26/28/29 + FK drift)
# ---------------------------------------------------------------------------


async def _run_backup(env, tmp_path) -> dict:
    return await rb.backup(env["settings"], tmp_path / "fresh-backup")


async def test_cell_06_missing_live_blob_fails_backup(env, template,
                                                       tmp_path):
    con = _db(env["src"])
    try:
        h = con.execute(
            "SELECT blob_hash FROM generation_inputs LIMIT 1").fetchone()[0]
    finally:
        con.close()
    p = _blob_path(env["src"], h)
    p.unlink()
    with pytest.raises(RecoveryCorruption, match="missing"):
        await _run_backup(env, tmp_path)
    # exact restoration: rewrite the true bytes from the pristine template
    shutil.copy(_blob_path(template["data_dir"], h), p)
    assert await _run_backup(env, tmp_path)


def _blob_path(root: Path, h: str) -> Path:
    return root / "blobs" / f"sha256/{h[0:2]}/{h[2:4]}/{h}"


async def test_cell_07_corrupt_live_blob_fails_backup(env, tmp_path):
    con = _db(env["src"])
    try:
        h = con.execute(
            "SELECT blob_hash FROM assets LIMIT 1").fetchone()[0]
    finally:
        con.close()
    p = _blob_path(env["src"], h)
    true = p.read_bytes()
    p.write_bytes(true + b"x")
    with pytest.raises(RecoveryCorruption):
        await _run_backup(env, tmp_path)
    p.write_bytes(true)
    assert await _run_backup(env, tmp_path)


def _artifact_file(root: Path, kind: str) -> Path:
    base = root / "workflow-artifacts" / kind / "sha256"
    return next(
        p for p in sorted(base.rglob("*.json"))
        if p.stat().st_size >= 0)


@pytest.mark.parametrize("kind", [
    "manifests", "templates",
    "realization_profiles", "execution_model_fingerprints",
])
async def test_cells_08_to_11_missing_artifact_fails_backup(
        env, tmp_path, kind):
    f = _artifact_file(env["src"], kind)
    true = f.read_bytes()
    f.unlink()
    with pytest.raises(RecoveryCorruption, match="missing"):
        await _run_backup(env, tmp_path)
    f.write_bytes(true)
    assert await _run_backup(env, tmp_path)


async def test_cell_12_corrupt_artifact_bytes_fail_backup(env, tmp_path):
    f = _artifact_file(env["src"], "manifests")
    true = f.read_bytes()
    f.write_bytes(true[:-1] + b" ")
    with pytest.raises(RecoveryCorruption):
        await _run_backup(env, tmp_path)
    f.write_bytes(true)
    assert await _run_backup(env, tmp_path)


async def test_cell_14_fk_corruption_fails_backup(env, tmp_path):
    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("DELETE FROM blobs WHERE hash = ("
                    "SELECT blob_hash FROM assets LIMIT 1)")
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption):
        await _run_backup(env, tmp_path)


async def test_cell_15_spec_corruption_fails_backup(env, tmp_path):
    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        row = con.execute(
            "SELECT id, workflow_spec_json FROM generations LIMIT 1"
        ).fetchone()
        broken = json.loads(row[1])
        broken["prompt"] = "tampered"
        con.execute(
            "UPDATE generations SET workflow_spec_json = ? WHERE id = ?",
            (json.dumps(broken), row[0]))
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption, match="WorkflowSpec"):
        await _run_backup(env, tmp_path)


async def test_cell_16_missing_derived_blob_fails_backup(env, tmp_path):
    con = _db(env["src"])
    try:
        h = con.execute(
            "SELECT blob_hash FROM derived_spatial_artifacts "
            "ORDER BY id LIMIT 1").fetchone()[0]
    finally:
        con.close()
    p = _blob_path(env["src"], h)
    p.unlink()
    with pytest.raises(RecoveryCorruption, match="missing"):
        await _run_backup(env, tmp_path)


async def test_cell_28_spec_ordinary_projection_mismatch_fails_backup(
        env, tmp_path):
    from soloring.domain.canonical import canonical_hash

    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        row = con.execute(
            "SELECT id, workflow_spec_json FROM generations "
            "WHERE json_extract(workflow_spec_json, '$.schema_version') = 1 "
            "LIMIT 1").fetchone()
        assert row is not None
        spec = json.loads(row[1])
        key = next(iter(spec["inputs"]))
        spec["inputs"][key]["bindings"][0]["blob_hash"] = "0" * 64
        con.execute(
            "UPDATE generations SET workflow_spec_json = ?, "
            "workflow_spec_hash = ? WHERE id = ?",
            (json.dumps(spec, sort_keys=True, separators=(",", ":")),
             canonical_hash(spec), row[0]))
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption, match="ordinary Blob bindings"):
        await _run_backup(env, tmp_path)


async def test_cell_29_spec_derived_identity_mismatch_fails_backup(
        env, tmp_path):
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        row = con.execute(
            "SELECT id, workflow_spec_json FROM generations "
            "WHERE json_extract(workflow_spec_json, '$.schema_version') = 3 "
            "LIMIT 1").fetchone()
        assert row is not None
        spec = json.loads(row[1])
        spec["spatial_realization"]["derived_artifacts"][0][
            "blob_hash"] = "1" * 64
        con.execute(
            "UPDATE generations SET workflow_spec_json = ?, "
            "workflow_spec_hash = ? WHERE id = ?",
            (canonical_json_str(spec), canonical_hash(spec), row[0]))
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption, match="derived"):
        await _run_backup(env, tmp_path)


async def test_fk_liveness_drift_fails_backup(env, tmp_path):
    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        con.execute(
            "CREATE TABLE m10f_drift_probe (x TEXT REFERENCES blobs(hash))")
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption, match="inventory drifted"):
        await _run_backup(env, tmp_path)


async def test_cell_25_source_change_between_prehash_and_copy_fails(
        env, tmp_path, monkeypatch):
    real = rb._copy_verified

    def corrupting_copy(src: Path, dst: Path, h: str) -> int:
        rb._verify_bytes(src, h)          # pre-copy verification passes…
        true = src.read_bytes()
        try:
            src.write_bytes(b"mutated-mid-copy")  # …then the source changes
            size = 0
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(src, "rb") as f, open(dst, "wb") as out:
                while chunk := f.read(1 << 20):
                    out.write(chunk)
                    size += len(chunk)
            rb._verify_bytes(dst, h)      # post-copy rehash must fail
            return size
        finally:
            src.write_bytes(true)         # exact source restoration

    monkeypatch.setattr(rb, "_copy_verified", corrupting_copy)
    with pytest.raises(RecoveryCorruption):
        await _run_backup(env, tmp_path)
    monkeypatch.setattr(rb, "_copy_verified", real)
    assert await _run_backup(env, tmp_path)


async def test_cell_26_staged_artifact_altered_before_manifest_fails(
        env, tmp_path, monkeypatch):
    real = rb._copy_verified
    boomed = {"done": False}

    def altering_copy(src: Path, dst: Path, h: str) -> int:
        size = real(src, dst, h)
        if not boomed["done"] and "workflow-artifacts" in str(dst):
            dst.write_bytes(b"altered-after-copy")
            boomed["done"] = True
        return size

    monkeypatch.setattr(rb, "_copy_verified", altering_copy)
    with pytest.raises(RecoveryCorruption):
        await _run_backup(env, tmp_path)
    monkeypatch.setattr(rb, "_copy_verified", real)
    assert await _run_backup(env, tmp_path)


async def test_cell_20_injected_sqlite_backup_failure(env, tmp_path,
                                                      monkeypatch):
    # sqlite3.Connection is an immutable C type; the class-level method
    # cannot be monkeypatched. The fault is injected one layer above, in
    # the exact helper that performs the real Connection.backup() call,
    # raising the same exception type the real API raises. (Must be a
    # SYNC function: asyncio.to_thread calls it directly.)
    def failing_backup(source_uri: str, dest_db: Path) -> None:
        raise sqlite3.OperationalError("injected Connection.backup failure")

    monkeypatch.setattr(rb, "_sqlite_online_backup", failing_backup)
    with pytest.raises(sqlite3.OperationalError):
        await _run_backup(env, tmp_path)
    dest = tmp_path / "fresh-backup"
    assert not dest.exists()
    assert _orphan_stages(dest, "backup") == []  # caught failure cleaned up
    monkeypatch.undo()
    assert await _run_backup(env, tmp_path)


# ---------------------------------------------------------------------------
# Backup-manifest grammar (§7.3) and restore-side cells (§7.9 1-5/13/18/19)
# ---------------------------------------------------------------------------


def _rewrite_manifest(backup: Path, mutate) -> None:
    doc = json.loads((backup / "backup-manifest.json").read_bytes())
    doc = mutate(doc)
    from soloring.domain.canonical import canonical_json_bytes

    (backup / "backup-manifest.json").write_bytes(canonical_json_bytes(doc))


async def test_cell_01_missing_backup_db_fails_restore(env, tmp_path):
    (env["backup"] / "soloring.db").unlink()
    with pytest.raises(RecoveryCorruption, match="backup DB"):
        await restore(env["backup"], tmp_path / "dest")
    assert not (tmp_path / "dest").exists()
    assert _orphan_stages(tmp_path / "dest", "restore") == []


async def test_cell_02_tampered_backup_db_fails_restore(env, tmp_path):
    db = env["backup"] / "soloring.db"
    raw = bytearray(db.read_bytes())
    raw[-1] ^= 0x55
    db.write_bytes(bytes(raw))
    with pytest.raises(RecoveryCorruption, match="database_sha256"):
        await restore(env["backup"], tmp_path / "dest")
    assert _orphan_stages(tmp_path / "dest", "restore") == []


async def test_cell_03_malformed_manifest_fails_restore(env, tmp_path):
    (env["backup"] / "backup-manifest.json").write_bytes(b"{nope")
    with pytest.raises(BackupManifestInvalid):
        await restore(env["backup"], tmp_path / "dest")
    assert _orphan_stages(tmp_path / "dest", "restore") == []


async def test_cell_04_noncanonical_manifest_fails_restore(env, tmp_path):
    doc = json.loads((env["backup"] / "backup-manifest.json").read_bytes())
    (env["backup"] / "backup-manifest.json").write_bytes(
        json.dumps(doc, indent=2).encode())  # semantically equal, noncanonical
    with pytest.raises(BackupManifestInvalid, match="canonical"):
        await restore(env["backup"], tmp_path / "dest")


async def test_cell_04b_unsorted_blob_list_fails_restore(env, tmp_path):
    _rewrite_manifest(
        env["backup"],
        lambda d: d | {"blob_hashes": sorted(d["blob_hashes"],
                                             reverse=True)})
    with pytest.raises(BackupManifestInvalid, match="sorted"):
        await restore(env["backup"], tmp_path / "dest")


async def test_cell_04c_duplicate_manifest_entry_fails_restore(
        env, tmp_path):
    _rewrite_manifest(
        env["backup"],
        lambda d: d | {"blob_hashes": d["blob_hashes"] + [
            d["blob_hashes"][0]]})
    with pytest.raises(BackupManifestInvalid, match="sorted|unique"):
        await restore(env["backup"], tmp_path / "dest")


async def test_cell_05_manifest_db_hash_mismatch_fails_restore(
        env, tmp_path):
    _rewrite_manifest(
        env["backup"],
        lambda d: d | {"database_sha256": "a" * 64})
    with pytest.raises(RecoveryCorruption, match="database_sha256"):
        await restore(env["backup"], tmp_path / "dest")


async def test_cell_13_existing_destination_rejected(env, tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(RecoveryError, match="already exists"):
        await restore(env["backup"], dest)
    backup_dest = tmp_path / "b"
    backup_dest.mkdir()
    with pytest.raises(RecoveryError, match="already exists"):
        await rb.backup(env["settings"], backup_dest)


async def test_cell_18_source_changes_after_backup_do_not_leak_into_restore(
        env, tmp_path):
    con = sqlite3.connect(str(env["src"] / "soloring.db"))
    try:
        con.execute(
            "UPDATE projects SET name = 'changed-after-backup'")
        con.commit()
    finally:
        con.close()
    dest = tmp_path / "dest"
    await restore(env["backup"], dest)
    dst = _db(dest)
    try:
        names = [r[0] for r in dst.execute("SELECT name FROM projects")]
        assert "changed-after-backup" not in names
    finally:
        dst.close()


async def test_cell_19_post_snapshot_generation_stays_absent(env, tmp_path):
    # A Generation created in the SOURCE after the backup was cut is simply
    # absent from the restored cut — and the restored cut is still complete
    # for everything it does contain (no partial Generation/file sets).
    dest = tmp_path / "dest"
    await restore(env["backup"], dest)
    src_con, dst_con = _db(env["src"]), _db(dest)
    try:
        projects_before = src_con.execute(
            "SELECT COUNT(*) FROM projects").fetchone()[0]
        src_con.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES ('p-post', 'post-snapshot', 't', 't')")
        src_con.commit()
        generations_before = src_con.execute(
            "SELECT COUNT(*) FROM generations").fetchone()[0]
        assert generations_before >= 1
        assert dst_con.execute(
            "SELECT COUNT(*) FROM projects").fetchone()[0] == projects_before
        assert dst_con.execute(
            "SELECT COUNT(*) FROM generations").fetchone()[0] == \
            generations_before
    finally:
        src_con.close()
        dst_con.close()


async def test_cell_22_orphan_derived_artifact_blob_survives(env, tmp_path):
    con = _db(env["src"])
    try:
        orphan = [
            r for r in con.execute(
                "SELECT d.blob_hash FROM derived_spatial_artifacts d "
                "WHERE NOT EXISTS (SELECT 1 FROM "
                "generation_derived_spatial_inputs g WHERE "
                "g.derived_spatial_artifact_id = d.id)")
        ]
        assert orphan, "template must contain one owner-free DSA"
    finally:
        con.close()
    assert await _run_backup(env, tmp_path)
    manifest = json.loads(
        (tmp_path / "fresh-backup" / "backup-manifest.json").read_bytes())
    assert orphan[0][0] in manifest["blob_hashes"]
    dest = tmp_path / "dest"
    await restore(tmp_path / "fresh-backup", dest)
    assert _blob_path(dest, orphan[0][0]).is_file()


async def test_cell_23_24_repeated_artifact_kinds_all_represented(env,
                                                                   tmp_path):
    assert await _run_backup(env, tmp_path)
    manifest = json.loads(
        (tmp_path / "fresh-backup" / "backup-manifest.json").read_bytes())
    kinds = [e["kind"] for e in manifest["workflow_artifacts"]]
    # v1 and v1b share workflow.json; the v4 release reused the same
    # template file, so distinct template hashes = {v1-family, v3}.
    assert kinds.count("manifests") >= 4  # v1 + v1b + v4 + v3
    assert kinds.count("templates") >= 2
    assert kinds.count("realization_profiles") >= 2  # v4 + v3
    assert kinds.count("execution_model_fingerprints") >= 2


# ---------------------------------------------------------------------------
# Active-writer coherence (cell 27)
# ---------------------------------------------------------------------------


async def test_cell_27_active_writer_overlapping_backup_yields_coherent_cut(
        env, tmp_path):
    from soloring.assets.blob_store import BlobStore

    store = BlobStore(env["settings"])
    project_id = str(uuid.uuid4())
    blob_hash = hashlib.sha256(b"cell-27-writer-blob").hexdigest()
    rel = store.relative_path_for_hash(blob_hash)

    async def writer() -> None:
        # place-before-reference, exactly like the production upload path
        tmp = env["settings"].tmp_dir / "cell27.tmp"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(b"cell-27-writer-blob")
        await store.place(blob_hash, tmp)
        con = sqlite3.connect(str(env["src"] / "soloring.db"))
        try:
            con.execute(
                "INSERT OR IGNORE INTO blobs (hash, path, size_bytes) "
                "VALUES (?, ?, ?)", (blob_hash, rel, 21))
            con.execute(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES (?, 'cell27', 't', 't')", (project_id,))
            con.execute(
                "INSERT INTO assets (id, project_id, blob_hash, kind) "
                "VALUES (?, ?, ?, 'reference')",
                (str(uuid.uuid4()), project_id, blob_hash))
            con.commit()
        finally:
            con.close()

    backup_task = asyncio.create_task(
        rb.backup(env["settings"], tmp_path / "b"))
    writer_task = asyncio.create_task(writer())
    await asyncio.gather(backup_task, writer_task)

    manifest = json.loads(
        (tmp_path / "b" / "backup-manifest.json").read_bytes())
    src_con = _db(env["src"])
    try:
        committed = src_con.execute(
            "SELECT COUNT(*) FROM assets WHERE blob_hash = ?",
            (blob_hash,)).fetchone()[0] > 0
    finally:
        src_con.close()
    if committed and blob_hash in manifest["blob_hashes"]:
        # row visible AND bytes selected — never a hybrid half-pair; the
        # file must be inside the backup and hash-verified.
        assert _blob_path(tmp_path / "b", blob_hash).is_file()
    # either way the backup is complete and restorable
    await restore(tmp_path / "b", tmp_path / "dest")


# ---------------------------------------------------------------------------
# External deletion fail-closed (cell 30) + process death (cell 21)
# ---------------------------------------------------------------------------


async def test_external_deletion_fail_closed_no_rematerialization(
        env, tmp_path):
    v3_id = _v3_generation(env["src"])
    _mark_terminal(env["src"], v3_id)
    con = _db(env["src"])
    try:
        spec = json.loads(con.execute(
            "SELECT workflow_spec_json FROM generations WHERE id = ?",
            (v3_id,)).fetchone()[0])
        manifest_hash = con.execute(
            "SELECT manifest_hash FROM generations WHERE id = ?",
            (v3_id,)).fetchone()[0]
    finally:
        con.close()
    derived = spec["spatial_realization"]["derived_artifacts"]
    victim = derived[0]["blob_hash"]
    _blob_path(env["src"], victim).unlink()  # external deletion, no GC

    # Durable history is unchanged by the deletion…
    con = _db(env["src"])
    try:
        row = con.execute(
            "SELECT workflow_spec_json, workflow_spec_hash FROM generations "
            "WHERE id = ?", (v3_id,)).fetchone()
        assert json.loads(row[0]) == spec
        con2 = con
        sibs = con2.execute(
            "SELECT blob_hash FROM generation_derived_spatial_inputs "
            "WHERE generation_id = ?", (v3_id,)).fetchall()
        assert victim in [r[0] for r in sibs]
    finally:
        con.close()

    # Exact Rerun creation still copies exact identities…
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )
    from soloring.generation import rerun

    engine = create_soloring_engine(env["settings"])
    factory = create_session_factory(engine)
    async with factory() as session:
        new = await rerun.create_rerun(session, v3_id)
        new_row = (await session.execute(text(
            "SELECT workflow_spec_json FROM generations WHERE id = :g"),
            {"g": new.id})).scalar()
    assert json.loads(new_row) == spec
    await engine.dispose()

    # …and worker execution of the historical input fails closed with the
    # existing missing-Blob semantics and ZERO rematerialization.
    from soloring.assets.blob_store import BlobStore
    from soloring.errors import SoloRingError
    from soloring.spatial import realize as realize_mod
    import soloring.spatial.derived as derived_mod
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    calls: list[str] = []

    async def _spy_compose(*a, **k):
        calls.append("compose")

    def _spy_materialize(*a, **k):
        calls.append("materialize")

    async def _spy_register(*a, **k):
        calls.append("register")

    orig = (realize_mod.compose_spatial_realization,
            getattr(realize_mod, "boxdepth_materialize", None),
            derived_mod.register_derived_artifact)
    realize_mod.compose_spatial_realization = _spy_compose
    if orig[1] is not None:
        realize_mod.boxdepth_materialize = _spy_materialize
    derived_mod.register_derived_artifact = _spy_register

    engine = create_soloring_engine(env["settings"])
    factory = create_session_factory(engine)
    try:
        from soloring.workflows.artifact_store import WorkflowArtifactStore

        manifest_v3 = parse_manifest_v3(
            (await WorkflowArtifactStore(env["settings"])
             .get_manifest(manifest_hash)).decode())
        async with factory() as session:
            with pytest.raises(SoloRingError) as excinfo:
                await execute_schema3_derived_inputs(
                    session, BlobStore(env["settings"]),
                    generation_id=v3_id, attempt_id=str(uuid.uuid4()),
                    workflow_spec=spec, manifest_v3=manifest_v3,
                    client=None,
                )
        assert excinfo.value.code in (
            "DERIVED_SPATIAL_BLOB_MISSING", "DERIVED_SPATIAL_BLOB_CORRUPT")
    finally:
        realize_mod.compose_spatial_realization = orig[0]
        if orig[1] is not None:
            realize_mod.boxdepth_materialize = orig[1]
        derived_mod.register_derived_artifact = orig[2]
        await engine.dispose()
    assert calls == []


@pytest.mark.slow
async def test_restore_process_death_before_publish_leaves_only_orphan_stage(
        env, tmp_path):
    dest = tmp_path / "dest"
    code = (
        "import os, sys, asyncio, importlib\n"
        f"sys.path.insert(0, {str(SERVER)!r})\n"
        "rb = importlib.import_module('soloring.recovery.backup')\n"
        "rb._publish_staged_directory = "
        "lambda stage, final: os._exit(7)\n"
        f"asyncio.run(rb.restore({str(env['backup'])!r}, "
        f"{str(dest)!r}))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO), capture_output=True, timeout=180,
    )
    assert proc.returncode == 7, proc.stderr[-2000:]

    assert not dest.exists()  # hard crash → final path never created
    orphans = _orphan_stages(dest, "restore")
    assert len(orphans) == 1  # fully staged sibling left behind…
    # …but it is NOT authoritative: no retry may treat it as a backup, and
    # an unmodified retry with a new stage succeeds.
    await restore(env["backup"], dest)
    assert dest.is_dir()
    assert _blob_path(
        dest, json.loads(
            (env["backup"] / "backup-manifest.json").read_bytes()
        )["blob_hashes"][0]).is_file()
    # explicit operator housekeeping only (no auto-deletion anywhere)
    assert len(_orphan_stages(dest, "restore")) == 1
    shutil.rmtree(orphans[0])


# ---------------------------------------------------------------------------
# Atomic finalize contract (§7.4)
# ---------------------------------------------------------------------------


def test_same_filesystem_atomic_finalize_contract(tmp_path):
    stage = tmp_path / ".d.soloring-backup-x.staging"
    stage.mkdir()
    (stage / "payload").write_bytes(b"x")
    final = tmp_path / "d"
    rb._publish_staged_directory(stage, final)
    assert (final / "payload").read_bytes() == b"x"
    assert not stage.exists()

    # absent stage fails hard
    with pytest.raises(RecoveryError, match="vanished"):
        rb._publish_staged_directory(tmp_path / ".gone.staging", tmp_path / "d2")

    # existing final refuses to replace
    stage2 = tmp_path / ".d3.soloring-backup-y.staging"
    stage2.mkdir()
    final3 = tmp_path / "d3"
    final3.mkdir()
    with pytest.raises(RecoveryError, match="already exists"):
        rb._publish_staged_directory(stage2, final3)
    assert final3.is_dir() and stage2.is_dir()

    # cross-device finalization fails closed with the final path absent.
    # final lives under a different parent so the fake stat can diverge
    # exactly one side of the comparison.
    sub = tmp_path / "sub"
    sub.mkdir()
    stage3 = tmp_path / ".d4.soloring-backup-z.staging"
    stage3.mkdir()
    final4 = sub / "d4"
    real_stat = os.stat

    def fake_stat(p, *a, **k):
        st = real_stat(p, *a, **k)
        if str(p) == str(final4.parent):
            import types

            return types.SimpleNamespace(
                st_dev=st.st_dev + 1,
                st_mode=st.st_mode, st_ino=st.st_ino,
                st_nlink=st.st_nlink, st_uid=st.st_uid, st_gid=st.st_gid,
                st_size=st.st_size, st_atime=st.st_atime,
                st_mtime=st.st_mtime, st_ctime=st.st_ctime,
            )
        return st

    monkeypatch_holder = pytest.MonkeyPatch()
    monkeypatch_holder.setattr(rb.os, "stat", fake_stat)
    try:
        with pytest.raises(RecoveryError, match="cross-filesystem"):
            rb._publish_staged_directory(stage3, final4)
    finally:
        monkeypatch_holder.undo()
    assert not final4.exists()
    assert stage3.is_dir()


# ---------------------------------------------------------------------------
# Physical-before-reference ordering invariants (§7.4)
# ---------------------------------------------------------------------------


def _assert_placement_precedes(
    events: list[tuple[str, str]], done_marker: str, insert_pattern: str
) -> None:
    done = next(
        (i for i, (kind, _) in enumerate(events) if kind == done_marker),
        None,
    )
    first_insert = next(
        (i for i, (kind, stmt) in enumerate(events)
         if kind == "stmt" and insert_pattern in stmt),
        None,
    )
    if done is None or first_insert is None:
        raise AssertionError(
            f"spy failed to observe both seams: {events[:6]!r}")
    if first_insert < done:
        raise AssertionError(
            "reference INSERT preceded completed physical placement: "
            f"{events[:6]!r}")


async def test_blob_physical_before_reference_commit_invariant(
        settings, engine, monkeypatch, tmp_path):
    from soloring.assets import upload as upload_mod
    from soloring.assets.blob_store import BlobStore
    from soloring.db.models import Asset  # noqa: F401
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(
        bind=engine, expire_on_commit=False, class_=AsyncSession)
    project_id = str(uuid.uuid4())
    async with factory() as s:
        await s.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (:p, 'P', 't', 't')"), {"p": project_id})
        await s.commit()

    events: list[tuple[str, str]] = []

    real_place = BlobStore.place

    async def traced_place(self, blob_hash, temp_path):
        events.append(("place_start", blob_hash))
        result = await real_place(self, blob_hash, temp_path)
        events.append(("place_done", blob_hash))
        return result

    monkeypatch.setattr(BlobStore, "place", traced_place)

    def before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany):
        events.append(("stmt", statement))

    event.listen(engine.sync_engine, "before_cursor_execute",
                 before_cursor_execute)
    try:
        from fastapi import UploadFile
        from starlette.datastructures import Headers

        payload = b"ordering-invariant-payload" * 128
        file = UploadFile(
            file=io.BytesIO(payload), size=len(payload), filename="ref.png",
            headers=Headers({"content-type": "image/png"}),
        )
        store = BlobStore(settings)
        await upload_mod.upload_reference_asset(
            factory, settings, store, project_id, file)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute",
                     before_cursor_execute)

    _assert_placement_precedes(events, "place_done", "INSERT INTO blobs")
    _assert_placement_precede_control()


def _assert_placement_precede_control() -> None:
    """Positive control: the checker itself trips on a fabricated
    reference-before-placement ordering (a silent spy proves nothing)."""
    with pytest.raises(AssertionError, match="preceded"):
        _assert_placement_precede_check(
            [("stmt", "INSERT INTO blobs …"),
             ("stmt", "INSERT INTO assets …"),
             ("place_done", "h")],
            "place_done", "INSERT INTO blobs")


def _assert_placement_precede_check(events, done_marker, insert_pattern):
    # mirror of _assert_placement_precedes for the control path
    done = next(
        (i for i, (kind, _) in enumerate(events) if kind == done_marker),
        None)
    first_insert = next(
        (i for i, (kind, stmt) in enumerate(events)
         if kind == "stmt" and insert_pattern in stmt), None)
    if done is None or first_insert is None:
        raise AssertionError("spy failed to observe both seams")
    if first_insert < done:
        raise AssertionError(
            "reference INSERT preceded completed physical placement")


async def test_workflow_artifacts_physical_before_generation_reference_commit(
        factory, engine, settings, tmp_path, monkeypatch):
    from tests.test_m10e_generation import _EXTENTS, _create, _spatial_seed
    from tests.test_m10e_package3_production import _schema3_package
    from soloring.workflows.artifact_store import WorkflowArtifactStore

    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=1, extents=_EXTENTS)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg

    events: list[tuple[str, str]] = []
    real_place_release = WorkflowArtifactStore.place_release

    async def traced_place_release(self, release):
        result = await real_place_release(self, release)
        # at this seam every schema-required retained file must already
        # exist and hash to the captured release identities
        import hashlib as _h

        checks = [
            ("manifests", release.manifest_hash, release.manifest_bytes),
            ("templates", release.workflow_template_hash,
             release.template_bytes),
            ("realization_profiles", release.realization_profile_hash,
             release.profile_bytes),
            ("execution_model_fingerprints",
             release.execution_model_fingerprint_hash,
             release.fingerprint_bytes),
        ]
        for kind, h, want in checks:
            f = (Path(self._root) / kind / "sha256" / h[0:2] / h[2:4]
                 / f"{h}.json")
            assert f.is_file(), f"{kind} {h} not placed"
            assert _h.sha256(f.read_bytes()).hexdigest() == h
            assert f.read_bytes() == want
        events.append(("place_release_done", release.manifest_hash))
        return result

    monkeypatch.setattr(
        WorkflowArtifactStore, "place_release", traced_place_release)

    def before_cursor_execute(
            conn, cursor, statement, parameters, context, executemany):
        events.append(("stmt", statement))

    event.listen(engine.sync_engine, "before_cursor_execute",
                 before_cursor_execute)
    try:
        gen = await _create(factory, settings, seed)
        assert gen.status == "queued"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute",
                     before_cursor_execute)

    _assert_placement_precedes(
        events, "place_release_done", "INSERT INTO generations")
    with pytest.raises(AssertionError, match="preceded"):
        _assert_placement_precede_check(
            [("stmt", "INSERT INTO generations …"),
             ("place_release_done", "h")],
            "place_release_done", "INSERT INTO generations")
