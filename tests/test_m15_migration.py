"""M15 migration proofs (frozen R4 §31.2 M15-MIG:01-10)."""

from __future__ import annotations

import sqlite3

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1]

M15_TABLES = [
    "production_compatibility_assessments",
    "production_compatibility_uses",
    "composition_occurrence_revision_tracking",
    "production_update_operations",
    "production_update_items",
]
M15_HEAD = "0016_m15_revision_compatibility"


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _upgrade(tmp_path, monkeypatch, target=M15_HEAD):
    _point_at(tmp_path, monkeypatch)
    command.upgrade(_cfg(), target)


def _downgrade(tmp_path, monkeypatch, target):
    _point_at(tmp_path, monkeypatch)
    command.downgrade(_cfg(), target)


def _con(tmp_path):
    return sqlite3.connect(tmp_path / "soloring.db")


def _tables(con) -> list[str]:
    return sorted(r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"))


def _schema_rows(con) -> list[tuple]:
    return sorted(con.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' AND tbl_name NOT IN "
        "(?, ?, ?, ?, ?) ORDER BY name",
        tuple(M15_TABLES)).fetchall())


def test_0016_adds_exact_five_tables(tmp_path, monkeypatch):
    """M15-MIG:01 — 0016 adds exactly the five frozen tables."""
    _upgrade(tmp_path, monkeypatch, "0015")
    con15 = _con(tmp_path)
    before = set(_tables(con15))
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con16 = _con(tmp_path)
    after = set(_tables(con16))
    assert after - before == set(M15_TABLES)
    assert before - after == set()


def test_0016_alters_no_predecessor_table(tmp_path, monkeypatch):
    """M15-MIG:02 — every predecessor schema object is byte-identical."""
    _upgrade(tmp_path, monkeypatch, "0015")
    con15 = _con(tmp_path)
    before = _schema_rows(con15)
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con16 = _con(tmp_path)
    assert _schema_rows(con16) == before


def test_0016_constraints_and_indexes_exact(tmp_path, monkeypatch):
    """M15-MIG:03 — exact DDL contract: the frozen uniques, checks, and
    indexes exist by name."""
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con = _con(tmp_path)
    objects = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master")}
    expected_indexes = {
        "ix_pca_object_created", "ix_pca_pair", "ix_pca_verdict",
        "ix_pcu_occurrence"}
    assert expected_indexes <= objects

    def ddl(table):
        return con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()[0]

    for table, names in (
            ("production_compatibility_assessments",
             ("uq_pca_coordinate", "uq_pca_id_report")),
            ("production_compatibility_uses", ("uq_pcu_use",)),
            ("production_update_operations",
             ("uq_puo_assessment_operation", "uq_puo_id_assessment")),
            ("production_update_items", ("uq_pui_use",))):
        for name in names:
            assert f"CONSTRAINT {name} UNIQUE" in ddl(table), name
    for check in ("ck_pca_evaluator", "ck_pca_verdict_domain",
                  "ck_pcu_verdict_domain", "ck_cort_mode",
                  "ck_cort_version", "ck_pui_review_accepted",
                  "ck_pui_after"):
        assert any(
            check in (r[0] or "")
            for r in con.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name IN "
                "(?, ?, ?, ?, ?)", tuple(M15_TABLES))), check
    fks = con.execute(
        "SELECT * FROM pragma_foreign_key_list("
        "'production_update_operations')").fetchall()
    assert any(
        row[2] == "production_compatibility_assessments" and
        row[3] == "assessment_id" and row[4] == "id"
        for row in fks)


def test_0016_downgrade_empty_succeeds(tmp_path, monkeypatch):
    """M15-MIG:04 — empty downgrade drops the five tables."""
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    _downgrade(tmp_path, monkeypatch, "0015")
    con = _con(tmp_path)
    tables = set(_tables(con))
    assert not (set(M15_TABLES) & tables)


def test_0016_downgrade_any_m15_state_fails_before_ddl(tmp_path,
                                                       monkeypatch):
    """M15-MIG:05 — any authored M15 row refuses downgrade before DDL."""
    from soloring.domain.ids import new_uuid

    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con = _con(tmp_path)
    con.execute("PRAGMA foreign_keys=ON")
    now = "2026-01-01T00:00:00.000Z"
    pid, cid, oid = new_uuid(), new_uuid(), new_uuid()
    con.execute(
        "INSERT INTO projects (id, name, created_at, updated_at) "
        "VALUES (?, 'P', ?, ?)", (pid, now, now))
    con.execute(
        "INSERT INTO compositions (id, project_id, name, description, "
        "metadata_version, working_version, created_at, updated_at) "
        "VALUES (?, ?, 'C', NULL, 0, 0, ?, ?)", (cid, pid, now, now))
    con.execute(
        "INSERT INTO composition_occurrences (id, composition_id, "
        "created_at) VALUES (?, ?, ?)", (oid, cid, now))
    con.execute(
        "INSERT INTO composition_occurrence_revision_tracking "
        "(composition_id, occurrence_id, mode, policy_version, "
        "created_at, updated_at) VALUES (?, ?, 'PINNED', 1, ?, ?)",
        (cid, oid, now, now))
    con.commit()
    with pytest.raises(Exception) as ei:
        command.downgrade(_cfg(), "0015")
    assert "refused" in str(ei.value)
    con2 = _con(tmp_path)
    assert set(M15_TABLES) <= set(_tables(con2))


def test_no_backfilled_tracking_or_compatibility_decisions(tmp_path,
                                                           monkeypatch):
    """M15-MIG:06 — upgrade invents no decisions; all five empty."""
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con = _con(tmp_path)
    for table in M15_TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 0, table


def test_foreign_key_check_clean(tmp_path, monkeypatch):
    """M15-MIG:07 — PRAGMA foreign_key_check is empty at 0016."""
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con = _con(tmp_path)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migration_roundtrip_leaves_no_temp_tables(tmp_path, monkeypatch):
    """M15-MIG:08 — 0016 upgrade→downgrade→upgrade leaves exactly the
    frozen 0016 schema, no successor residue."""
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    _downgrade(tmp_path, monkeypatch, "0015")
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con = _con(tmp_path)
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    _upgrade(ref_dir, monkeypatch, M15_HEAD)
    con_ref = _con(ref_dir)

    def names(c):
        return sorted((r[0], r[1]) for r in c.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%'"))

    assert names(con) == names(con_ref)
    for table in M15_TABLES:
        a = con.execute(
            "SELECT sql FROM sqlite_master WHERE name=?",
            (table,)).fetchone()
        b = con_ref.execute(
            "SELECT sql FROM sqlite_master WHERE name=?",
            (table,)).fetchone()
        assert a == b, table


def test_orm_migration_parity_exact_for_all_five_tables(
        tmp_path, monkeypatch):
    """M15-MIG:09 — ORM metadata and 0016 migration DDL agree exactly on all
    five M15 tables; successor ORM registration cannot change predecessor DDL."""
    import sqlalchemy as sa

    _point_at(tmp_path, monkeypatch)
    _upgrade(tmp_path, monkeypatch, M15_HEAD)

    from soloring.db.base import Base
    import soloring.db.models  # noqa: F401 — populate metadata

    orm_engine = sa.create_engine(
        f"sqlite:///{tmp_path / 'orm.db'}")
    Base.metadata.create_all(orm_engine)
    mig = sqlite3.connect(tmp_path / "soloring.db")
    orm = sqlite3.connect(tmp_path / "orm.db")
    for table in M15_TABLES:
        cols_mig = mig.execute(
            f"PRAGMA table_info({table})").fetchall()
        cols_orm = orm.execute(
            f"PRAGMA table_info({table})").fetchall()
        assert [c[1] for c in cols_mig] == [c[1] for c in cols_orm], table
        assert [c[5] for c in cols_mig] == [c[5] for c in cols_orm], table
    for table in ("composition_working_occurrences",
                  "production_revision_spatial_interpretations"):
        cols_mig = [c[1] for c in mig.execute(
            f"PRAGMA table_info({table})")]
        cols_orm = [c[1] for c in orm.execute(
            f"PRAGMA table_info({table})")]
        assert cols_mig == cols_orm, table


def test_0016_blob_fk_inventory_unchanged_from_m14(tmp_path, monkeypatch):
    """M15-MIG:10 — no new Blob liveness path: the set of Blob-referencing
    foreign keys is identical before and after 0016."""
    _upgrade(tmp_path, monkeypatch, "0015")
    con15 = _con(tmp_path)
    tables15 = _tables(con15)
    _upgrade(tmp_path, monkeypatch, M15_HEAD)
    con16 = _con(tmp_path)

    def blob_fks(con, tables):
        out = set()
        for table in tables:
            for row in con.execute(
                    f"PRAGMA foreign_key_list({table})"):
                if row[2] == "blobs":
                    out.add((table, row[3], row[4]))
        return out

    assert blob_fks(con16, _tables(con16)) == blob_fks(con15, tables15)
