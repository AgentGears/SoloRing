"""M13 migration proofs (frozen R3 §30.9 M13-MIG:01-04)."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]

M13_TABLES = [
    "composition_occurrence_authority_subjects",
    "production_revision_spatial_interpretations",
    "production_instance_features",
    "production_instance_feature_transitions",
    "production_instance_spatial_tracks",
    "production_instance_spatial_transitions",
    "composition_spatial_bindings",
    "composition_spatial_binding_subjects",
    "composition_spatial_binding_entries",
    "shot_production_world_selections",
    "shot_revision_production_worlds",
    "shot_revision_production_instance_feature_states",
    "shot_revision_production_instance_spatial_states",
]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(tmp_path, monkeypatch, target="head"):
    _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(tmp_path, monkeypatch, target):
    _point_at(tmp_path, monkeypatch)
    command.downgrade(_cfg(), target)


def _con(tmp_path):
    return sqlite3.connect(tmp_path / "soloring.db")


def _populate_m12(tmp_path):
    """Minimal legal predecessor rows so M13 FK targets exist."""
    import hashlib

    from soloring.domain.ids import new_uuid

    con = _con(tmp_path)
    pid = new_uuid()
    bh = hashlib.sha256(b"m13-mig").hexdigest()
    pobj = new_uuid()
    prid = new_uuid()
    cid = new_uuid()
    oid = new_uuid()
    now = "2026-01-01T00:00:00.000Z"
    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as sj,
        production_revision_snapshot_hash as sh,
    )
    closure = RetainedBlobClosure(blob_hash=bh, size_bytes=6, media_type=None)
    con.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'P', ?, ?)", (pid, now, now))
    con.execute(
        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, "
        "created_at) VALUES (?, ?, 6, NULL, ?)",
        (bh, f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", now))
    con.execute(
        "INSERT INTO production_objects (id, project_id, name, created_at, "
        "updated_at) VALUES (?, ?, 'Obj', ?, ?)", (pobj, pid, now, now))
    con.execute(
        "INSERT INTO production_revisions (id, production_object_id, "
        "revision_number, snapshot_json, snapshot_hash, created_at) "
        "VALUES (?, ?, 1, ?, ?, ?)",
        (prid, pobj, sj(closure), sh(closure), now))
    con.execute(
        "INSERT INTO production_revision_closures "
        "(production_revision_id, contract_key, contract_version, "
        "blob_hash, size_bytes, media_type) VALUES "
        "(?, 'retained_blob', 1, ?, 6, NULL)", (prid, bh))
    con.execute(
        "INSERT INTO compositions (id, project_id, name, description, "
        "metadata_version, working_version, created_at, updated_at) "
        "VALUES (?, ?, 'C', NULL, 0, 0, ?, ?)", (cid, pid, now, now))
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, "
        "created_at) VALUES (?, ?, ?)", (oid, cid, now))
    con.commit()
    return {"pid": pid, "prid": prid, "cid": cid, "oid": oid}


def test_m13_mig_01(tmp_path, monkeypatch):
    """M13-MIG:01 — exact 0013→0014 upgrade + exact 13-table inventory."""
    _upgrade(tmp_path, monkeypatch, "0013_m12_composition_occurrences")
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == (
        "0014_m13_authority_complete_world")
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(M13_TABLES) <= tables
    # exactly thirteen new tables relative to 0013
    _downgrade(tmp_path, monkeypatch, "0013_m12_composition_occurrences")
    tables_0013 = {r[0] for r in sqlite3.connect(
        tmp_path / "soloring.db").execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables - tables_0013 == set(M13_TABLES)


def test_m13_mig_02(tmp_path, monkeypatch):
    """M13-MIG:02 — empty 0014→0013 downgrade succeeds."""
    _upgrade(tmp_path, monkeypatch, "head")
    _downgrade(tmp_path, monkeypatch, "0013_m12_composition_occurrences")
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not (set(M13_TABLES) & tables)
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == (
        "0013_m12_composition_occurrences")


def test_m13_mig_03(tmp_path, monkeypatch):
    """M13-MIG:03 — any M13 state refuses downgrade, incl. bare adoption."""
    _upgrade(tmp_path, monkeypatch, "head")
    ids = _populate_m12(tmp_path)
    con = _con(tmp_path)
    con.execute(
        "INSERT INTO composition_occurrence_authority_subjects "
        "(composition_id, occurrence_id, subject_kind, creative_entity_id, "
        "created_at) VALUES (?, ?, 'production_instance', NULL, "
        "'2026-01-01T00:00:00.000Z')",
        (ids["cid"], ids["oid"]))
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="downgrade refused"):
        _downgrade(tmp_path, monkeypatch, "0013_m12_composition_occurrences")
    # the schema is untouched after the fail-closed preflight
    con = _con(tmp_path)
    assert con.execute(
        "SELECT COUNT(*) FROM "
        "composition_occurrence_authority_subjects").fetchone()[0] == 1
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] == (
        "0014_m13_authority_complete_world")


def test_m13_mig_04(tmp_path, monkeypatch):
    """M13-MIG:04 — exact ORM/migration parity incl. resolved names."""
    _upgrade(tmp_path, monkeypatch, "head")

    def snapshot(con) -> dict:
        import re as _re

        out = {}
        for tbl in M13_TABLES:
            cols = tuple(sorted((r[1], r[2], r[3], r[5])
                                for r in con.execute(
                                    f'PRAGMA table_info("{tbl}")')))
            fks = tuple(sorted(
                con.execute(f'PRAGMA foreign_key_list("{tbl}")')))
            idx = tuple(sorted(
                r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name=? AND sql IS NOT NULL", (tbl,))))
            table_sql = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            checks = tuple(sorted(
                _re.findall(r"CONSTRAINT\s+(\w+)\s+CHECK", table_sql or "")))
            uniques = tuple(sorted(
                _re.findall(r"CONSTRAINT\s+(\w+)\s+UNIQUE", table_sql or "")))
            pks = tuple(_re.findall(
                r"CONSTRAINT\s+(\w+)\s+PRIMARY", table_sql or ""))
            out[tbl] = (cols, fks, idx, checks, uniques, pks)
        return out

    mig = snapshot(_con(tmp_path))
    from sqlalchemy import create_engine

    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base

    eng = create_engine(f"sqlite:///{tmp_path}/orm.db")
    Base.metadata.create_all(eng)
    eng.dispose()
    orm = snapshot(sqlite3.connect(tmp_path / "orm.db"))
    assert set(mig) == set(M13_TABLES)
    assert set(mig) == set(orm)
    for tbl in mig:
        assert mig[tbl] == orm[tbl], f"ORM/migration drift on {tbl}"
