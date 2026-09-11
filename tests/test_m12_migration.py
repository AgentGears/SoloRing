"""M12 migration proofs (frozen R3 §21 M12-MIG)."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]
VERSIONS = BASE_DIR / "server" / "alembic" / "versions"

M12_TABLES = [
    "compositions", "composition_occurrences", "composition_revisions",
    "composition_working_occurrences", "composition_revision_occurrences",
    "composition_revision_production_dependencies",
    "composition_revision_nested_dependencies",
    "composition_identity_operations",
    "composition_identity_operation_sources",
    "composition_identity_operation_targets",
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


def _populate_m11(tmp_path):
    """One legal M11 production revision at 0012 for the predecessor gate."""
    import hashlib

    con = _con(tmp_path)
    pid = "11111111-1111-1111-1111-111111111111"
    bh = hashlib.sha256(b"m12-mig").hexdigest()
    oid = "22222222-2222-2222-2222-222222222222"
    rid = "33333333-3333-3333-3333-333333333333"
    aid = "44444444-4444-4444-4444-444444444444"
    now = "2026-01-01T00:00:00.000Z"
    con.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'P', ?, ?)", (pid, now, now))
    con.execute(
        "INSERT INTO blobs (hash, path, size_bytes, detected_media_type, created_at) "
        "VALUES (?, ?, 8, NULL, ?)",
        (bh, f"sha256/{bh[:2]}/{bh[2:4]}/{bh}", now))
    con.execute(
        "INSERT INTO assets (id, project_id, blob_hash, kind, created_at) "
        "VALUES (?, ?, ?, 'reference', ?)", (aid, pid, bh, now))
    con.execute(
        "INSERT INTO production_objects (id, project_id, name, created_at, updated_at) "
        "VALUES (?, ?, 'Obj', ?, ?)", (oid, pid, now, now))
    from soloring.domain.canonical import canonical_hash, canonical_json_str
    from soloring.production.canonical import RetainedBlobClosure

    closure = RetainedBlobClosure(blob_hash=bh, size_bytes=8, media_type=None)
    sj = canonical_json_str({
        "schema_version": 1,
        "consumption": {
            "contract_key": "retained_blob", "contract_version": 1,
            "blob_hash": bh, "size_bytes": 8, "media_type": None,
        },
    })
    sh = canonical_hash({
        "schema_version": 1,
        "consumption": {
            "contract_key": "retained_blob", "contract_version": 1,
            "blob_hash": bh, "size_bytes": 8, "media_type": None,
        },
    })
    con.execute(
        "INSERT INTO production_revisions (id, production_object_id, revision_number, "
        "snapshot_json, snapshot_hash, created_at) VALUES (?, ?, 1, ?, ?, ?)",
        (rid, oid, sj, sh, now))
    con.execute(
        "INSERT INTO production_revision_closures (production_revision_id, "
        "contract_key, contract_version, blob_hash, size_bytes, media_type) "
        "VALUES (?, 'retained_blob', 1, ?, 8, NULL)", (rid, bh))
    con.execute(
        "INSERT INTO production_revision_source_assets (production_revision_id, "
        "asset_id, created_at) VALUES (?, ?, ?)", (rid, aid, now))
    con.commit()
    con.close()
    return {"project_id": pid, "production_revision_id": rid}


def test_0013_upgrade_adds_exact_ten_tables_without_predecessor_rebuild(
    tmp_path, monkeypatch
):
    """M12-MIG:01."""
    _upgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
    seeded = _populate_m11(tmp_path)
    _upgrade(tmp_path, monkeypatch, "0013_m12_composition_occurrences")
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(M12_TABLES) <= tables
    # predecessor rows untouched
    n = con.execute("SELECT COUNT(*) FROM production_revisions").fetchone()[0]
    cols = [r[1] for r in con.execute("PRAGMA table_info(production_revisions)")]
    con.close()
    assert n == 1
    assert "composition" not in " ".join(cols)


def test_0013_orm_metadata_matches_upgraded_schema_and_resolved_names(
    tmp_path, monkeypatch
):
    """M12-MIG:02 — exact ORM/migration parity incl. resolved names."""
    _upgrade(tmp_path, monkeypatch, "head")

    def snapshot(con) -> dict:
        import re as _re

        out = {}
        # M13 adds composition%-named production-world tables; M12 parity
        # stays exact over the fixed ten-table M12 inventory.
        for tbl in M12_TABLES:
            cols = tuple(sorted((r[1], r[2], r[3], r[5])
                                for r in con.execute(f'PRAGMA table_info("{tbl}")')))
            fks = tuple(sorted(con.execute(f'PRAGMA foreign_key_list("{tbl}")')))
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
            pks = tuple(_re.findall(r"CONSTRAINT\s+(\w+)\s+PRIMARY", table_sql or ""))
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
    assert set(mig) == set(M12_TABLES)
    assert set(mig) == set(orm)
    for tbl in mig:
        assert mig[tbl] == orm[tbl], f"ORM/migration drift on {tbl}"


def test_0013_downgrade_empty_schema_succeeds_exactly_to_0012(
    tmp_path, monkeypatch
):
    """M12-MIG:03."""
    _upgrade(tmp_path, monkeypatch, "head")
    _downgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    con.close()
    assert not (set(M12_TABLES) & tables)
    assert ver == "0012_m11_reusable_production_revisions"


@pytest.mark.parametrize("table", M12_TABLES)
def test_0013_downgrade_refuses_any_authored_m12_row(tmp_path, monkeypatch, table):
    """M12-MIG:04 (+ :09 identity-only variant) — preflight before DDL."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    now = "2026-01-01T00:00:00.000Z"
    cid = "aaaa0000-0000-0000-0000-00000000000c"
    con.execute(
        "INSERT INTO compositions (id, project_id, name, metadata_version, "
        "working_version, created_at, updated_at) VALUES "
        "(?, '11111111-1111-1111-1111-111111111111', 'C', 0, 0, ?, ?)", (cid, now, now))
    if table == "compositions":
        pass
    elif table == "composition_occurrences":
        con.execute(
            "INSERT INTO composition_occurrences (id, composition_id, created_at) "
            "VALUES ('bbbb0000-0000-0000-0000-00000000000c', ?, ?)", (cid, now))
    elif table == "composition_identity_operations":
        con.execute(
            "INSERT INTO composition_occurrences (id, composition_id, created_at) "
            "VALUES ('bbbb0000-0000-0000-0000-00000000000c', ?, ?)", (cid, now))
        con.execute(
            "INSERT INTO composition_identity_operations (id, composition_id, "
            "operation_kind, working_version_before, working_version_after, "
            "request_fingerprint, impact_fingerprint, operation_json, "
            "operation_hash, created_at) VALUES "
            "('cccc0000-0000-0000-0000-00000000000c', ?, 'mint', 0, 1, ?, ?, '{}', "
            "?, ?)",
            (cid, "0" * 64, "1" * 64, "2" * 64, now))
    else:
        # rows in the remaining tables require publish machinery (M12B/M12C);
        # their refusal is exercised there via the same preflight.
        pytest.skip("populated in M12B/M12C suites")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="downgrade refused"):
        _downgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
    con = _con(tmp_path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "compositions" in tables


def test_0013_upgrade_does_not_backfill_invented_compositions(tmp_path, monkeypatch):
    """M12-MIG:05."""
    _upgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
    _populate_m11(tmp_path)
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    for tbl in M12_TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        assert n == 0, f"{tbl} backfilled"
    con.close()


def test_migration_head_is_exactly_0013(tmp_path, monkeypatch):
    """M12-MIG:06."""
    _upgrade(tmp_path, monkeypatch)
    con = _con(tmp_path)
    ver = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    files = sorted(p.name for p in VERSIONS.glob("0*.py"))
    con.close()
    assert ver == "0015_m14_world_observation_execution"  # M14 advances the head
    assert files[-1] == "0015_m14_world_observation_execution.py"


def test_0012_predecessor_database_upgrades_cleanly_to_0013(tmp_path, monkeypatch):
    """M12-MIG:07."""
    _upgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
    seeded = _populate_m11(tmp_path)
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    n = con.execute("SELECT COUNT(*) FROM production_revisions WHERE id=?",
                    (seeded["production_revision_id"],)).fetchone()[0]
    con.close()
    assert n == 1


def test_composite_occurrence_fks_reject_cross_composition_rows(tmp_path, monkeypatch):
    """M12-MIG:08 — database-level lineage coherence."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    now = "2026-01-01T00:00:00.000Z"
    pid = "11111111-1111-1111-1111-111111111111"
    c1, c2 = "aaaa0001-0000-0000-0000-00000000000c", "aaaa0002-0000-0000-0000-00000000000c"
    occ1 = "bbbb0001-0000-0000-0000-00000000000c"
    for c in (c1, c2):
        con.execute(
            "INSERT INTO compositions (id, project_id, name, metadata_version, "
            "working_version, created_at, updated_at) VALUES (?, ?, 'C', 0, 0, ?, ?)",
            (c, pid, now, now))
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, created_at) "
        "VALUES (?, ?, ?)", (occ1, c1, now))
    con.commit()
    with pytest.raises(sqlite3.IntegrityError):
        # occurrence belongs to c1; a working row under c2 must be rejected
        con.execute(
            "INSERT INTO composition_working_occurrences (composition_id, "
            "occurrence_id, display_name, source_kind, visible, x_mm, y_mm, z_mm, "
            "yaw_udeg, pitch_udeg, roll_udeg, updated_at) VALUES "
            "(?, ?, 'X', 'production_revision', 1, 0, 0, 0, 0, 0, 0, ?)",
            (c2, occ1, now))
    con.close()


def test_nonempty_identity_history_without_revision_blocks_downgrade(
    tmp_path, monkeypatch
):
    """M12-MIG:09 — authored identity operations alone block downgrade."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = _con(tmp_path)
    cid = "dddd0000-0000-0000-0000-00000000000c"
    con.execute(
        "INSERT INTO compositions (id, project_id, name, metadata_version, "
        "working_version, created_at, updated_at) VALUES "
        "(?, '11111111-1111-1111-1111-111111111111', 'C', 1, 1, ?, ?)",
        (cid, "2026-01-01T00:00:00.000Z", "2026-01-01T00:00:00.000Z"))
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, created_at) "
        "VALUES ('dddd0001-0000-0000-0000-00000000000c', ?, ?)",
        (cid, "2026-01-01T00:00:00.000Z"))
    con.execute(
        "INSERT INTO composition_identity_operations (id, composition_id, "
        "operation_kind, working_version_before, working_version_after, "
        "request_fingerprint, impact_fingerprint, operation_json, "
        "operation_hash, created_at) VALUES "
        "('dddd0002-0000-0000-0000-00000000000c', ?, 'mint', 0, 1, ?, ?, "
        "'{}', ?, ?)",
        (cid, "1" * 64, "2" * 64, "3" * 64, "2026-01-01T00:00:00.000Z"))
    con.commit()
    con.close()
    # no composition_revisions row exists at all
    con = _con(tmp_path)
    n = con.execute("SELECT COUNT(*) FROM composition_revisions").fetchone()[0]
    con.close()
    assert n == 0
    with pytest.raises(RuntimeError, match="downgrade refused"):
        _downgrade(tmp_path, monkeypatch, "0012_m11_reusable_production_revisions")
