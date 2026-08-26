"""Alembic migration tests (plan §103; audit #1, #7).

Covers:
  * upgrade/downgrade produce the correct worker_leases schema;
  * a freshly-migrated SoloRing DB already satisfies journal_mode=WAL (audit #1
    — Alembic must apply the same SQLite configuration as the app engine);
  * migration operations run cleanly against a database that already holds
    data, and the recreated schema retains its PK semantics (plan §103:
    "Migration tests must include populated databases").

NOTE on audit #7: migration 0001 contains only create_table/drop_table — there
is no structural N->N+1 change, so there is nothing across which populated data
could be *preserved* by a batch ALTER. The populated-DB test below is therefore
a harness establishing that discipline; a genuine data-preservation test across
a batch_alter_table is deferred until migration 0002 in M1.
"""

from __future__ import annotations

import sqlite3 as sq
from pathlib import Path

from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR


def _make_config() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_settings_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def test_alembic_upgrade_creates_worker_leases(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_settings_at(data_dir, monkeypatch)

    command.upgrade(_make_config(), "head")

    con = sq.connect(str(db_file))
    try:
        cols = con.execute("PRAGMA table_info(worker_leases)").fetchall()
        names = [row[1] for row in cols]
        pk_row = [row for row in cols if row[5] >= 1]
        rev = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()

    assert names == ["name", "worker_id", "acquired_at", "heartbeat_at"]
    assert len(pk_row) == 1 and pk_row[0][1] == "name", "name must be the primary key"
    # head advanced through M1/M3C; worker_leases is created by 0001 and remains.
    assert rev is not None and rev[0] == "0011_m10_derived_spatial_execution"


def test_migrated_database_is_already_wal(tmp_path: Path, monkeypatch) -> None:
    """Audit #1: a freshly-migrated DB must already be WAL (persistent PRAGMA)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_settings_at(data_dir, monkeypatch)

    command.upgrade(_make_config(), "head")

    # Open with a plain sqlite3 connection (no app listener) and observe the
    # persisted journal mode.
    con = sq.connect(str(db_file))
    try:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        con.close()
    assert str(mode).lower() == "wal", (
        f"freshly-migrated DB journal_mode={mode!r}; Alembic did not apply WAL"
    )


def test_migration_ops_run_on_populated_db_and_recreate_keeps_constraints(
    tmp_path: Path, monkeypatch
) -> None:
    """Populated-DB migration harness (plan §103; audit #7).

    Migration 0001 is create_table/drop_table only, so there is no structural
    N->N+1 change and no batch ALTER to preserve data across. What this test
    actually proves: migration ops run cleanly against a DB that already holds
    data, and the schema recreated by a fresh upgrade retains its PK semantics
    (duplicate-name inserts still rejected). A real data-preservation test
    across a batch_alter_table is deferred until migration 0002 in M1.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_settings_at(data_dir, monkeypatch)
    cfg = _make_config()

    command.upgrade(cfg, "head")

    # Populate with a realistic row and verify the PK rejects duplicates.
    con = sq.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
            "VALUES ('generation-worker','A','t','t')"
        )
        con.commit()
        try:
            con.execute(
                "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
                "VALUES ('generation-worker','B','t','t')"
            )
            con.commit()
            raised = False
        except sq.IntegrityError:
            raised = True
            con.rollback()
    finally:
        con.close()
    assert raised, "PK on worker_leases.name must reject duplicate inserts"

    # Round-trip through batch recreate: downgrade drops, upgrade recreates.
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    con = sq.connect(str(db_file))
    try:
        names = [r[1] for r in con.execute("PRAGMA table_info(worker_leases)").fetchall()]
        # Constraint semantics must survive the batch recreate.
        con.execute(
            "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
            "VALUES ('generation-worker','C','t','t')"
        )
        con.commit()
        try:
            con.execute(
                "INSERT INTO worker_leases(name, worker_id, acquired_at, heartbeat_at) "
                "VALUES ('generation-worker','D','t','t')"
            )
            con.commit()
            raised2 = False
        except sq.IntegrityError:
            raised2 = True
            con.rollback()
        # No leftover temp tables from batch mode.
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        con.close()

    assert names == ["name", "worker_id", "acquired_at", "heartbeat_at"]
    assert raised2, "PK must still reject duplicates after recreate"
    assert "_alembic_tmp_worker_leases" not in tables, "batch temp table leaked"


def test_alembic_downgrade_removes_worker_leases(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_settings_at(data_dir, monkeypatch)
    cfg = _make_config()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    con = sq.connect(str(db_file))
    try:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        con.close()

    assert "worker_leases" not in tables


def test_inprocess_migration_does_not_disable_application_loggers(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression: Alembic's fileConfig previously disabled every logger that
    existed before an in-process migration ran (disable_existing_loggers
    defaults to True), muting SoloRing integrity/repair logging for the rest
    of the process. env.py must keep application loggers enabled.

    A handler is attached to the probe logger itself (not root) because
    fileConfig also replaces root handlers — which would rip out pytest's
    caplog handler mid-test even with disable_existing_loggers=False.
    """
    import logging

    probe = logging.getLogger("soloring.probe.logger_regression")
    probe.setLevel(logging.ERROR)
    records: list[str] = []

    class _ProbeHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _ProbeHandler(level=logging.ERROR)
    probe.addHandler(handler)
    try:
        probe.error("before migration")
        assert records == ["before migration"]

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _point_settings_at(data_dir, monkeypatch)
        command.upgrade(_make_config(), "head")

        assert not probe.disabled, "in-process migration disabled an application logger"
        records.clear()
        probe.error("after migration")
        assert records == ["after migration"], "application logger no longer emits"
    finally:
        probe.removeHandler(handler)
