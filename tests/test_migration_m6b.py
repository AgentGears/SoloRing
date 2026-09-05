"""M6B re-gate migration tests: 0007 is the FIRST structural migration that
batch-rebuilds POPULATED tables (sequences, scenes). This activates the
long-deferred populated-table preservation gate: every row must survive the
rebuild byte-identically, constraints swap exactly as designed, no batch
temp tables leak, and the downgrade restores the 0006 form with data intact.
"""

from __future__ import annotations

import sqlite3 as sq

import pytest
from pathlib import Path

from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _point_at(data_dir: Path, monkeypatch) -> None:
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)


def _populate_0006(cfg: Config, db_file: Path) -> None:
    command.upgrade(cfg, "0006_story_world_semantic_dependencies")
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    try:
        con.executescript(
            """
            INSERT INTO projects(id, name, created_at, updated_at)
              VALUES ('p1', 'P', 't', 't');
            INSERT INTO sequences(id, project_id, title, position,
                                  created_at, updated_at)
              VALUES ('sq1', 'p1', 'Act I', 0, 't1', 't1'),
                     ('sq2', 'p1', 'Act II', 1, 't2', 't2'),
                     ('sq3', 'p1', 'Act III', 2, 't3', 't3');
            -- tombstoned sequence keeps its coordinates
            UPDATE sequences SET deleted_at = 'td', updated_at = 'td'
              WHERE id = 'sq2';
            INSERT INTO scenes(id, sequence_id, title, position,
                               created_at, updated_at)
              VALUES ('c1', 'sq1', 'Lobby', 0, 't1', 't1'),
                     ('c2', 'sq1', 'Roof', 1, 't2', 't2');
            UPDATE scenes SET deleted_at = 'td', updated_at = 'td'
              WHERE id = 'c2';
            INSERT INTO shots(id, project_id, shot_number, subject,
                              scene_id, scene_position, created_at, updated_at)
              VALUES ('s1', 'p1', 1, 'a', 'c1', 0, 't', 't'),
                     ('s2', 'p1', 2, 'b', 'c1', 1, 't', 't'),
                     ('s3', 'p1', 3, 'c', NULL, NULL, 't', 't');
            UPDATE shots SET deleted_at = 'td', updated_at = 'td'
              WHERE id = 's2';
            """
        )
        con.commit()
    finally:
        con.close()


def _snapshot(db_file: Path) -> dict[str, list[tuple]]:
    con = sq.connect(str(db_file))
    try:
        out = {}
        for table, order in (
            ("sequences", "id"), ("scenes", "id"), ("shots", "id"),
        ):
            rows = con.execute(
                f"SELECT * FROM {table} ORDER BY {order}"
            ).fetchall()
            out[table] = [tuple(r) for r in rows]
        return out
    finally:
        con.close()


def test_0007_rebuild_preserves_populated_rows_exactly(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    _populate_0006(cfg, db_file)
    before = _snapshot(db_file)

    command.upgrade(cfg, "head")

    # The deferred populated-table preservation obligation: byte-identical
    # survival across the batch rebuilds.
    after = _snapshot(db_file)
    assert after == before

    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master"
        ).fetchall()}
        assert not [t for t in tables if t.startswith("_alembic_tmp")]

        # Active-only partial unique indexes exist with the WHERE clauses.
        idx_sql = {
            r[0]: r[1] for r in con.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert "uq_sequences_project_id_position" in idx_sql
        assert "WHERE deleted_at IS NULL" in idx_sql[
            "uq_sequences_project_id_position"
        ]
        assert "uq_scenes_sequence_id_position" in idx_sql
        assert "WHERE deleted_at IS NULL" in idx_sql[
            "uq_scenes_sequence_id_position"
        ]
        assert "uq_shots_scene_position" in idx_sql
        assert "deleted_at IS NULL" in idx_sql["uq_shots_scene_position"]
        assert "scene_id IS NOT NULL" in idx_sql["uq_shots_scene_position"]

        # Non-unique indexes survived the rebuild.
        assert "ix_sequences_project_active" in idx_sql
        assert "ix_scenes_sequence_active" in idx_sql

        # Table-level UNIQUE constraints are gone; the named CHECKs remain
        # in the recreated table DDL.
        seq_ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='sequences'"
        ).fetchone()[0]
        assert "CONSTRAINT" in seq_ddl
        assert "uq_sequences_project_id_position" not in seq_ddl

        # Partial-index semantics live: an ACTIVE row may take a tombstone's
        # position; two ACTIVE rows still collide.
        con.execute(
            "INSERT INTO sequences(id, project_id, title, position, "
            "created_at, updated_at) VALUES ('sq4', 'p1', 'IV', 1, 't', 't')"
        )
        con.commit()
        try:
            con.execute(
                "INSERT INTO sequences(id, project_id, title, position, "
                "created_at, updated_at) VALUES ('sq5', 'p1', 'V', 1, 't', 't')"
            )
            con.commit()
            raised = False
        except sq.IntegrityError:
            raised = True
            con.rollback()
        assert raised, "active-only uniqueness not enforced"

        assert con.execute("SELECT version_num FROM alembic_version"
                           ).fetchone()[0] == "0012_m11_reusable_production_revisions"
    finally:
        con.close()


def test_0007_downgrade_restores_0006_constraints_and_data(
    tmp_path: Path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()
    _populate_0006(cfg, db_file)
    before = _snapshot(db_file)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0006_story_world_semantic_dependencies")

    # Data survived the full round-trip through both rebuild directions.
    assert _snapshot(db_file) == before
    con = sq.connect(str(db_file))
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master"
        ).fetchall()}
        assert not [t for t in tables if t.startswith("_alembic_tmp")]
        # Table-level constraints restored.
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        # The partial indexes are gone; the constraint is back in DDL.
        seq_ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE name='sequences'"
        ).fetchone()[0]
        assert "uq_sequences_project_id_position" in seq_ddl
        assert "uq_sequences_project_id_position" not in idx
    finally:
        con.close()

# --- 0007 downgrade refusal on legal-but-unrepresentable 0007 state ---------------


def _snapshot_schema(db_file: Path) -> dict:
    con = sq.connect(str(db_file))
    try:
        objects = con.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        version = con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        return {
            "objects": [(r[0], r[1], r[2]) for r in objects],
            "version": version,
        }
    finally:
        con.close()


def _snapshot_rows(db_file: Path, table: str) -> list[tuple]:
    con = sq.connect(str(db_file))
    try:
        return [tuple(r) for r in con.execute(f"SELECT * FROM {table}")]
    finally:
        con.close()


def _attempt_downgrade(cfg: Config) -> None:
    # Legitimately leave 0008 (unused M7 schema drops cleanly), then
    # attempt the 0007 -> 0006 boundary this suite has always targeted.
    command.downgrade(cfg, "0007_active_narrative_uniqueness")
    command.downgrade(cfg, "0006_story_world_semantic_dependencies")


def test_downgrade_refuses_cleanly_on_sequence_coordinate_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    """A/B/C, delete B, create D: actives 0/1/2 with tombstone B at 1 — a
    legal 0007 state 0006 cannot represent. The downgrade must refuse
    BEFORE any DDL: rows, schema, indexes, version, and FK integrity all
    untouched, no batch temp tables."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()

    import uuid

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        ids = [str(uuid.uuid4()) for _ in range(4)]
        con.executescript(
            f"""
            INSERT INTO projects(id, name, created_at, updated_at)
              VALUES ('p1', 'P', 't', 't');
            INSERT INTO sequences(id, project_id, title, position,
                                  created_at, updated_at)
              VALUES ('{ids[0]}', 'p1', 'A', 0, 't', 't'),
                     ('{ids[1]}', 'p1', 'B', 1, 't', 't'),
                     ('{ids[2]}', 'p1', 'C', 2, 't', 't');
            -- Compaction semantics: delete B, then C moves to 1 and D lands
            -- at 2 while tombstone B keeps 1.
            UPDATE sequences SET deleted_at = 'td', updated_at = 'td'
              WHERE id = '{ids[1]}';
            UPDATE sequences SET position = 1 WHERE id = '{ids[2]}';
            INSERT INTO sequences(id, project_id, title, position,
                                  created_at, updated_at)
              VALUES ('{ids[3]}', 'p1', 'D', 2, 't', 't');
            """
        )
        con.commit()
    finally:
        con.close()

    rows_before = _snapshot_rows(db_file, "sequences")
    schema_before = _snapshot_schema(db_file)

    with pytest.raises(RuntimeError, match="cannot represent"):
        _attempt_downgrade(cfg)

    assert _snapshot_rows(db_file, "sequences") == rows_before
    schema_after = _snapshot_schema(db_file)
    assert schema_after == schema_before
    assert schema_after["version"] == "0007_active_narrative_uniqueness"

    names = {o[1] for o in schema_after["objects"]}
    assert "uq_sequences_project_id_position" in names  # partial index intact
    assert not [n for n in names if n.startswith("_alembic_tmp")]
    con = sq.connect(str(db_file))
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()


def test_downgrade_refuses_cleanly_on_shot_coordinate_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    """Shot X deleted at (scene, 0) and Shot Y active at (scene, 0): legal
    0007 state. Previously this failed at the FIRST downgrade step (drop
    partial index, then global create fails) leaving a version-0007 DB with
    no shot-ordering uniqueness at all; the preflight must refuse before
    touching the index."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    _point_at(data_dir, monkeypatch)
    cfg = _cfg()

    import uuid

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0007_active_narrative_uniqueness")
    con = sq.connect(str(db_file))
    try:
        scene = str(uuid.uuid4())
        shot_x = str(uuid.uuid4())
        shot_y = str(uuid.uuid4())
        con.executescript(
            f"""
            INSERT INTO projects(id, name, created_at, updated_at)
              VALUES ('p1', 'P', 't', 't');
            INSERT INTO shots(id, project_id, shot_number, subject,
                              scene_id, scene_position, created_at,
                              updated_at)
              VALUES ('{shot_x}', 'p1', 1, 'x', '{scene}', 0, 't', 't'),
                     ('{shot_y}', 'p1', 2, 'y', NULL, NULL, 't', 't');
            UPDATE shots SET deleted_at = 'td', updated_at = 'td'
              WHERE id = '{shot_x}';
            UPDATE shots SET scene_id = '{scene}', scene_position = 0
              WHERE id = '{shot_y}';
            """
        )
        con.commit()
    finally:
        con.close()

    rows_before = _snapshot_rows(db_file, "shots")
    schema_before = _snapshot_schema(db_file)

    with pytest.raises(RuntimeError, match="cannot represent"):
        _attempt_downgrade(cfg)

    assert _snapshot_rows(db_file, "shots") == rows_before
    schema_after = _snapshot_schema(db_file)
    assert schema_after == schema_before
    assert schema_after["version"] == "0007_active_narrative_uniqueness"
    names = {o[1] for o in schema_after["objects"]}
    assert "uq_shots_scene_position" in names  # partial index never dropped
    assert not [n for n in names if n.startswith("_alembic_tmp")]
