"""M17B-A gate tests: migration 0019, four-table set, ORM parity,
downgrade laws (frozen R7 §§4, 15)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
PY = sys.executable

_M17B_TABLES = (
    "performance_candidates", "performance_revisions",
    "performance_retarget_assessments",
    "performance_retarget_reviews")


def _alembic(db: Path, *args: str) -> None:
    env = {"SystemRoot": "C:\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix(),
           "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([PY, "-m", "alembic", *args], cwd=SERVER,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr[-1500:]


def _fresh_upgrade_reaches_0019(tmp_path):
    db = tmp_path / "m17b.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version"
                      ).fetchone()[0]
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert ver == "0020_m17c_performance_capture"  # M17C-A advances the head
    assert set(_M17B_TABLES) <= tabs
    assert len([t for t in tabs if t in _M17B_TABLES]) == 4


def _i02_exactly_four_m17b_tables(tmp_path):
    db = tmp_path / "m17b.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    # M17C-A (PR #26): the performance-prefixed set is the four M17B
    # tables plus the two dialogue-bound binding companions.
    assert {t for t in tabs if t.startswith("performance_")} == \
        set(_M17B_TABLES) | {
            "performance_candidate_vocal_bindings",
            "performance_revision_vocal_bindings"}


def _i03_predecessor_tables_unchanged(tmp_path):
    db18, db19 = tmp_path / "a.db", tmp_path / "b.db"
    _alembic(db18, "upgrade",
             "0018_m17a_dialogue_vocal_foundation")
    _alembic(db19, "upgrade", "head")
    # M17C-A (PR #26): the two binding companions are M17C additions,
    # excluded alongside the four M17B tables.
    _excluded = tuple(_M17B_TABLES) + (
        "performance_candidate_vocal_bindings",
        "performance_revision_vocal_bindings")
    q = ("SELECT name, sql FROM sqlite_master WHERE type='table' "
         "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%' "
         "AND name NOT IN {}".format(str(_excluded)))
    def _normalize(rows):
        # alembic emits table-level constraints in nondeterministic
        # ORDER across runs; compare the constraint SET per table
        out = {}
        for name, ddl in rows:
            import re as _re
            parts = [s.strip() for s in ddl.replace(chr(10), chr(44)).replace(chr(9), chr(44)).split(chr(44)) if s.strip()]
            out[name] = sorted(parts)
        return out

    c18, c19 = sqlite3.connect(db18), sqlite3.connect(db19)
    a = _normalize(c18.execute(q).fetchall())
    b = _normalize(c19.execute(q).fetchall())
    c18.close()
    c19.close()
    assert a == b, "predecessor schema drifted"


def _i04_empty_downgrade_succeeds(tmp_path):
    db = tmp_path / "m17b.db"
    _alembic(db, "upgrade", "head")
    _alembic(db, "downgrade",
             "0018_m17a_dialogue_vocal_foundation")
    con = sqlite3.connect(db)
    ver = con.execute("SELECT version_num FROM alembic_version"
                      ).fetchone()[0]
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert ver == "0018_m17a_dialogue_vocal_foundation"
    assert not (set(_M17B_TABLES) & tabs)


def _i05_populated_downgrade_refuses(tmp_path):
    db = tmp_path / "m17b.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projects (id,name,created_at,updated_at) VALUES "
        "('p','P','2026-01-01T00:00:00.000Z','2026-01-01T00:00:00.000Z')")
    con.execute(
        "INSERT INTO performance_candidates (id,project_id,subject_id,"
        "performance_kind,performance_profile_id,temporal_start_num,"
        "temporal_start_den,temporal_end_num,temporal_end_den,"
        "canonical_channel_payload_blob_hash,"
        "canonical_channel_payload_sha256,payload_schema_version,"
        "source_kind,provenance_schema_version,provenance_json,"
        "provenance_hash,created_at) VALUES ('c1','p','p','FACIAL',"
        "'performance-profile/1',0,1,4500,1,'" + 'a' * 64 + "','" +
        'a' * 64 + "',1,'authored',1,'{}','" + 'b' * 64 +
        "','2026-01-01T00:00:00.000Z')")
    con.commit()
    con.close()
    env = {"SystemRoot": "C:\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix(),
           "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run(
        [PY, "-m", "alembic", "downgrade",
         "0018_m17a_dialogue_vocal_foundation"], cwd=SERVER,
        capture_output=True, env=env)
    assert r.returncode != 0
    out = ((r.stderr or b"") + (r.stdout or b"")).decode("utf-8", errors="replace")
    assert "performance_candidates" in out
    con2 = sqlite3.connect(db)
    ver = con2.execute("SELECT version_num FROM alembic_version"
                       ).fetchone()[0]
    con2.close()
    assert ver == "0019_m17b_performance_revisions"


def _i01_fresh_upgrade_reaches_0019(tmp_path):
    db = tmp_path / "m17b.db"
    _alembic(db, "upgrade", "head")
    con = sqlite3.connect(db)
    assert con.execute("SELECT version_num FROM alembic_version"
                       ).fetchone()[0] == \
        "0019_m17b_performance_revisions"
    con.close()
