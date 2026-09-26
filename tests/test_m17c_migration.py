"""M17C-A migration 0020 binding-table and downgrade laws."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"
PY = sys.executable
HEAD = "0020_m17c_performance_capture"
TABLES = {
    "performance_candidate_vocal_bindings",
    "performance_revision_vocal_bindings",
}


def _run(db: Path, *args: str, expect: int = 0):
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "SOLORING_DATA_DIR": db.parent.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [PY, "-m", "alembic", *args],
        cwd=SERVER,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == expect, result.stderr[-2000:]
    return result


def test_m17c_0020_fresh_upgrade_creates_two_binding_tables(tmp_path):
    db = tmp_path / "m17c.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert version == HEAD
    assert TABLES <= tables


def _canonical_ddl(sql: str) -> tuple:
    """Canonicalize a CREATE TABLE statement for equality.

    The repository's migration chain renders named constraints inside
    CREATE TABLE in a per-process nondeterministic order (observed
    identical command + PYTHONHASHSEED producing different orders —
    object-identity iteration, recorded review finding). The invariant
    under test is that migration 0020 adds nothing to predecessor
    tables: same columns in the same order (positional meaning) and
    the same constraint SET, independent of textual order.
    """
    body = sql.split("(", 1)[1].rsplit(")", 1)[0]
    lines = [ln.strip().rstrip(",").strip() for ln in body.splitlines()]
    lines = [ln for ln in lines if ln]
    first_constraint = next(
        (i for i, ln in enumerate(lines)
         if ln.upper().startswith(("CONSTRAINT", "PRIMARY KEY",
                                   "FOREIGN KEY", "UNIQUE", "CHECK"))),
        len(lines))
    columns = lines[:first_constraint]
    constraints = sorted(lines[first_constraint:])
    return tuple(columns + constraints)


def test_m17c_0020_does_not_alter_predecessor_tables(tmp_path):
    before = tmp_path / "before.db"
    after = tmp_path / "after.db"
    _run(before, "upgrade", "0019_m17b_performance_revisions")
    _run(after, "upgrade", "head")

    def schema(path: Path):
        con = sqlite3.connect(path)
        rows = con.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%'"
        ).fetchall()
        con.close()
        return {name: _canonical_ddl(sql)
                for name, sql in rows if name not in TABLES}

    assert schema(before) == schema(after)


def test_m17c_0020_empty_downgrade_returns_to_0019(tmp_path):
    db = tmp_path / "m17c.db"
    _run(db, "upgrade", "head")
    _run(db, "downgrade", "0019_m17b_performance_revisions")
    con = sqlite3.connect(db)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == \
        "0019_m17b_performance_revisions"
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert not (TABLES & tables)


def test_m17c_0020_populated_binding_refuses_downgrade(tmp_path):
    db = tmp_path / "m17c.db"
    _run(db, "upgrade", "head")
    con = sqlite3.connect(db)
    # Raw sqlite3 starts with foreign_keys OFF. The downgrade law is an
    # authority-preservation count fence, so a minimal check-valid row is
    # sufficient to prove it refuses before any destructive DDL.
    con.execute(
        "INSERT INTO performance_candidate_vocal_bindings ("
        "performance_candidate_id,vocal_performance_revision_id,"
        "source_start_sample,source_end_sample_exclusive,sample_rate_hz,"
        "performance_origin_num,performance_origin_den,"
        "synchronization_basis_version,binding_schema_version,binding_json,"
        "binding_hash,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "c", "v", 0, 1, 48000, 0, 1, 1, 1, "{}", "a" * 64,
            "2026-09-25T00:00:00.000Z",
        ),
    )
    con.commit()
    con.close()

    result = _run(
        db, "downgrade", "0019_m17b_performance_revisions", expect=1)
    assert "performance_candidate_vocal_bindings" in \
        (result.stderr + result.stdout)
    con = sqlite3.connect(db)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    con.close()
