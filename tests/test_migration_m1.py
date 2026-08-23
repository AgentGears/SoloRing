"""M1 migration tests (plan §49, §50.2).

Populated 0001 -> 0002 preserves M0 state; every M1 table, named constraint,
and required index exists; foreign_key_check is clean; downgrade restores a
valid 0001 with no Alembic temp tables.
"""

from __future__ import annotations

import sqlite3 as sq
from pathlib import Path

from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR

_M1_TABLES = {
    "projects", "blobs", "shots", "shot_revisions", "generations",
    "takes", "assets", "shot_references", "generation_inputs",
}

_REQUIRED_INDEXES = [
    "ix_blobs_created_at",
    "ix_shots_project_active_number",
    "ix_shots_approved_take_id",
    "ix_shot_references_asset_id",
    "ix_assets_project_created",
    "ix_assets_take",
    "ix_assets_blob_hash",
    "ix_takes_shot_created",
    "ix_generation_inputs_asset_id",
    "ix_generations_queue",
    "ix_generations_active_recovery",
    "ix_generations_worker_active",
]

# Representative named constraints across tables (plan §4.2).
_CONSTRAINTS_TO_VERIFY = [
    ("projects", "ck_projects_name_nonempty"),
    ("shots", "fk_shots_project_id_projects"),
    ("shots", "uq_shots_project_id_shot_number"),
    ("shots", "ck_shots_subject_nonempty"),
    ("shot_references", "pk_shot_references"),
    ("shot_references", "ck_shot_references_role"),
    ("shot_revisions", "uq_shot_revisions_shot_id_snapshot_hash"),
    ("shot_revisions", "ck_shot_revisions_snapshot_hash_len"),
    ("blobs", "ck_blobs_hash_len"),
    ("assets", "ck_assets_kind"),
    ("assets", "ck_assets_kind_take_consistency"),
    ("assets", "fk_assets_blob_hash_blobs"),
    ("generations", "ck_generations_status"),
    ("generations", "ck_generations_executor"),
    ("generations", "ck_generations_operation"),
    ("generations", "fk_generations_rerun_of_generation_id_generations"),
    ("generation_inputs", "ck_generation_inputs_blob_hash_len"),
    ("takes", "uq_takes_generation_id_output_key"),
]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _connect(db_file: Path) -> sq.Connection:
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    return con


def test_populated_0001_to_0002_preserves_m0_and_creates_schema(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()

    # Start at 0001 with a populated worker lease.
    command.upgrade(cfg, "0001_worker_leases")
    con = _connect(db_file)
    try:
        con.execute(
            "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
            "VALUES ('generation-worker','w-abc','t1','t2')"
        )
        con.commit()
    finally:
        con.close()

    # Upgrade to 0002.
    command.upgrade(cfg, "head")

    con = _connect(db_file)
    try:
        # M0 state preserved exactly.
        row = con.execute(
            "SELECT worker_id, acquired_at, heartbeat_at FROM worker_leases "
            "WHERE name='generation-worker'"
        ).fetchone()
        assert row == ("w-abc", "t1", "t2")

        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        assert _M1_TABLES <= tables

        # foreign_key_check must be clean.
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []

        # All required indexes present.
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'ix_%'"
        )}
        for name in _REQUIRED_INDEXES:
            assert name in idx, f"missing index {name}"

        # Named constraints present in each table's CREATE SQL.
        sql = {r[0]: r[1] for r in con.execute(
            "SELECT tbl_name, sql FROM sqlite_master WHERE type='table'"
        )}
        for table, cname in _CONSTRAINTS_TO_VERIFY:
            assert cname in sql[table], f"missing constraint {cname} on {table}"

        # journal_mode is WAL (persistent, applied by the shared PRAGMA hook).
        assert str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower() == "wal"

        assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0011_m10_derived_spatial_execution"
        )
    finally:
        con.close()


def test_downgrade_0002_to_0001_removes_m1_tables(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()

    command.upgrade(cfg, "head")
    con = _connect(db_file)
    try:
        con.execute(
            "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
            "VALUES ('generation-worker','w-xyz','t1','t2')"
        )
        con.commit()
    finally:
        con.close()

    command.downgrade(cfg, "0001_worker_leases")

    con = _connect(db_file)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        for t in _M1_TABLES:
            assert t not in tables, f"{t} should be removed on downgrade"
        assert "worker_leases" in tables

        # worker lease row preserved.
        row = con.execute(
            "SELECT worker_id FROM worker_leases WHERE name='generation-worker'"
        ).fetchone()
        assert row == ("w-xyz",)

        # no Alembic batch temp tables leaked.
        tmps = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'"
        )]
        assert tmps == []

        assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0001_worker_leases"
        )
    finally:
        con.close()
