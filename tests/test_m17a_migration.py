"""M17A-A gate tests: migration 0018, ORM parity, downgrade refusal."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
PY = sys.executable

_M17A_TABLES = (
    "dialogue_lines", "dialogue_line_revisions", "vocal_candidates",
    "vocal_performance_revisions", "vocal_performance_selections",
    "shot_vocal_segment_mappings", "dialogue_alignments",
)


def _alembic(db: Path, *args: str) -> None:
    env = {"SystemRoot": "C:\\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix(),
           "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([PY, "-m", "alembic", *args], cwd=SERVER,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-1500:]


def test_fresh_upgrade_creates_exactly_seven_tables(tmp_path):
    db = tmp_path / "m17a.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    ver = con.execute("SELECT version_num FROM alembic_version"
                      ).fetchone()[0]
    con.close()
    assert ver == "0018_m17a_dialogue_vocal_foundation"
    assert set(_M17A_TABLES) <= tabs
    # exactly seven M17A tables: no eighth table appears
    assert len([t for t in tabs if t in _M17A_TABLES]) == 7


def test_empty_downgrade_then_reupgrade(tmp_path):
    db = tmp_path / "m17a.db"
    _alembic(db, "upgrade", "head")
    _alembic(db, "downgrade", "0017_m16_intra_shot_consequences")
    con = sqlite3.connect(db)
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(t in tabs for t in _M17A_TABLES)
    con.close()
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    assert con.execute("SELECT version_num FROM alembic_version"
                       ).fetchone()[0] == \
        "0018_m17a_dialogue_vocal_foundation"
    con.close()


def test_downgrade_refuses_when_any_row_exists(tmp_path):
    """A row in ANY M17A table blocks the 0018 downgrade (frozen R5
    §13), including a bare DialogueLine with zero revisions."""
    import sqlite3
    db = tmp_path / "m17a_rows.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO dialogue_lines (id, project_id, created_at) "
        "VALUES ('00000000-0000-4000-8000-000000000001', "
        "'00000000-0000-4000-8000-000000000002', '2026-09-19T00:00:00Z')")
    con.commit()
    con.close()
    env = {"SystemRoot": "C:\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix()}
    r = subprocess.run([PY, "-m", "alembic", "downgrade",
                        "0017_m16_intra_shot_consequences"],
                       cwd=SERVER, capture_output=True, text=True,
                       env=env)
    assert r.returncode != 0
    assert "0018 downgrade refused" in (r.stdout + r.stderr)
    con = sqlite3.connect(db)
    assert con.execute("SELECT version_num FROM alembic_version"
                       ).fetchone()[0] ==         "0018_m17a_dialogue_vocal_foundation"
    con.close()
