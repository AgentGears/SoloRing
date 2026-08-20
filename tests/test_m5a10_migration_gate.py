"""M5A-10 migration gate — populated pre-M5 upgrade through 0005.

Fresh upgrade to head is already pinned by test_migration.py (head ==
0005_soft_cancel_selection). This gate adds the populated-database path:
a real pre-M5 (0004) database carrying live rows upgrades cleanly to 0005,
existing rows receive the documented not_started/NULL defaults, referential
integrity holds, no temp-table debris remains, and a downgrade/re-upgrade
cycle preserves the data.
"""

from __future__ import annotations

import sqlite3 as sq
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR


def _make_config() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _populate_0004_db(db_file: Path) -> str:
    """Insert one full lineage (project→shot→revision→generation) at 0004."""
    pid, sid, rid, gid = (str(uuid.uuid4()) for _ in range(4))
    con = sq.connect(str(db_file))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES (?, ?, datetime('now'), datetime('now'))",
            (pid, "legacy"),
        )
        con.execute(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "created_at, updated_at) VALUES (?, ?, 1, 'Legacy shot', "
            "datetime('now'), datetime('now'))",
            (sid, pid),
        )
        con.execute(
            "INSERT INTO shot_revisions (id, shot_id, revision_number, "
            "snapshot_hash, snapshot_json, created_at) VALUES "
            "(?, ?, 1, ?, '{\"schema_version\": 1}', datetime('now'))",
            (rid, sid, "a" * 64),
        )
        con.execute(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "generation_number, status, operation, executor, workflow_id, "
            "workflow_version, workflow_template_hash, manifest_hash, "
            "compiled_prompt, prompt_compiler_version, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, created_at, updated_at, "
            "queued_at) VALUES (?, ?, ?, 3, 'succeeded', 'generate', 'fake', "
            "'hunyuan_i2v', 1, ?, ?, 'legacy prompt', '1', '{}', '{}', ?, "
            "datetime('now'), datetime('now'), datetime('now'))",
            (gid, sid, rid, "b" * 64, "c" * 64, "d" * 64),
        )
        con.commit()
    finally:
        con.close()
    return gid


def _open(db_file: Path) -> sq.Connection:
    con = sq.connect(str(db_file))
    con.execute("PRAGMA foreign_keys=ON")
    return con


def test_populated_0004_to_head_defaults_and_integrity(
    tmp_path: Path, monkeypatch,
):
    import soloring.settings as settings_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = _make_config()

    command.upgrade(cfg, "0004_comfy_submission_state")
    gid = _populate_0004_db(db_file)

    # Pre-M5 rows already carry the 0004 submission columns (nullable or
    # defaulted); 0005 must add soft_cancel_selected_at without touching them.
    command.upgrade(cfg, "head")

    con = _open(db_file)
    try:
        rev = con.execute("SELECT version_num FROM alembic_version").fetchone()
        cols = [r[1] for r in con.execute("PRAGMA table_info(generations)")]
        row = con.execute(
            "SELECT status, executor_submission_state, attempt_id, "
            "executor_job_id, soft_cancel_selected_at, "
            "executor_submission_json, executor_submission_hash "
            "FROM generations WHERE id=?", (gid,),
        ).fetchone()
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        debris = [r for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '_alembic_tmp_%'"
        ).fetchall()]
    finally:
        con.close()

    assert rev[0] == "0009_m8_visual_identity"
    assert "soft_cancel_selected_at" in cols
    # Documented defaults for pre-existing rows: submission not_started, no
    # attempt, no job, no soft cancel, no artifact.
    assert row == ("succeeded", "not_started", None, None, None, None, None)
    assert fk == []
    assert debris == []


def test_downgrade_reupgrade_preserves_data(tmp_path: Path, monkeypatch):
    import soloring.settings as settings_mod

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "soloring.db"
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings_mod, "_settings", None)
    cfg = _make_config()

    command.upgrade(cfg, "head")
    gid = _populate_0004_db(db_file)
    # A modern row state that 0005's column must survive round-trips.
    con = _open(db_file)
    con.execute(
        "UPDATE generations SET soft_cancel_selected_at=datetime('now'), "
        "cancel_requested_at=datetime('now') WHERE id=?", (gid,),
    )
    con.commit()
    con.close()

    command.downgrade(cfg, "0004_comfy_submission_state")
    con = _open(db_file)
    cols = [r[1] for r in con.execute("PRAGMA table_info(generations)")]
    assert "soft_cancel_selected_at" not in cols
    fk_down = con.execute("PRAGMA foreign_key_check").fetchall()
    con.close()
    assert fk_down == []

    command.upgrade(cfg, "head")
    con = _open(db_file)
    try:
        row = con.execute(
            "SELECT status, soft_cancel_selected_at FROM generations "
            "WHERE id=?", (gid,),
        ).fetchone()
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        con.close()
    assert row[0] == "succeeded"
    assert row[1] is None  # the column was dropped and re-added: reset to NULL
    assert fk == []
