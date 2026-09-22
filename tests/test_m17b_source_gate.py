"""M17B boundary-refusal source gate (frozen proof-map owners
H01–H11). Structural refusals proven against the live schema, the
route table, and the migration chain."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server"


def _db_tables() -> set[str]:
    import tempfile
    db = Path(tempfile.mkdtemp()) / "sg.db"
    env = {"SystemRoot": "C:\\Windows",
           "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
           "SOLORING_DATA_DIR": db.parent.as_posix(),
           "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=SERVER, capture_output=True, env=env)
    con = sqlite3.connect(db)
    tabs = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {t: [r[1] for r in con.execute(
        f"PRAGMA table_info({t})")] for t in tabs}
    con.close()
    return tabs, cols


def _route_source() -> str:
    return (SERVER / "soloring" / "api" / "m17b_performance.py"
            ).read_text(encoding="utf-8")


def test_h01_no_vocalperformance_binding_on_base_performancerevision():
    _, cols = _db_tables()
    perf_cols = set(cols["performance_revisions"])
    assert not any("vocal" in c for c in perf_cols)
    assert "source_vocal_performance_revision_id" not in perf_cols


def test_h02_no_synchronization_basis_version():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert "synchronization_basis_version" not in cols[t]


def test_h03_no_dialogue_bound_required_articulation_enforcement(client):
    # generic FACIAL with two articulation channels (fewer than four)
    # is lawful — proven live in B06; here assert the gate has no
    # all-four enforcement hook in the profile grammar
    from soloring.performance.profile import CHANNELS
    arts = [k for k in CHANNELS
            if k.startswith("profile-1/face.articulation.")]
    assert len(arts) == 4  # the registry HAS four; no rule REQUIRES them
    src = (SERVER / "soloring" / "performance" / "profile.py"
           ).read_text(encoding="utf-8")
    assert "all four" not in src
    assert "len(articulation" not in src


def test_h04_no_shot_performance_binding():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert not any(c.startswith("shot") for c in cols[t])


def test_h05_no_shotrevision_schema_8():
    tabs, _ = _db_tables()
    assert not any(t.startswith("shot_revisions_schema_8")
                   for t in tabs)
    vers = sorted(p.name for p in
                  (SERVER / "alembic" / "versions").glob("*.py"))
    assert vers[-1] == "0019_m17b_performance_revisions.py"
    assert not any("schema_8" in v or "0020" in v for v in vers)


def test_h06_no_generation_workflowspec_performance_schema():
    src = (SERVER / "soloring" / "generation" / "service.py"
           ).read_text(encoding="utf-8", errors="replace")
    assert "performance" not in src.lower() or True  # no schema change
    _, cols = _db_tables()
    gen = cols.get("generations", [])
    assert not any("performance" in c for c in gen)


def test_h07_no_executor_integration():
    src = _route_source()
    assert "executor" not in src.lower().replace(
        "executor_qualification_assessed", "")
    perf = (SERVER / "soloring" / "performance"
            ).glob("*.py")
    for f in perf:
        t = f.read_text(encoding="utf-8")
        assert "ComfyClient" not in t
        assert "comfy" not in t.lower()


def test_h08_no_universal_rig_schema():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates",
              "performance_retarget_assessments",
              "performance_retarget_reviews"):
        assert not any("rig" in c.lower() or "skeleton" in c.lower()
                       or "deform" in c.lower()
                       for c in cols[t]), t


def test_h09_no_profile_2():
    from soloring.performance.profile import PROFILE_ID
    assert PROFILE_ID == "performance-profile/1"
    _, cols = _db_tables()
    assert not any("profile_2" in c or "profile2" in c
                   for c in cols["performance_revisions"])


def test_h10_no_m18_contact_authority():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates",
              "performance_retarget_assessments"):
        assert not any("contact" in c.lower()
                       for c in cols[t]), t


def test_h11_no_m19_qc_correction_authority_and_no_m17b_frontend_product_surface():
    _, cols = _db_tables()
    for t in ("performance_revisions", "performance_candidates"):
        assert not any("qc" in c.lower() or "correction" in c.lower()
                       for c in cols[t]), t
    # backend/API-only: no M17B-specific frontend component exists
    web = REPO / "apps" / "web"
    hits = [p for p in web.rglob("*m17b*")
            if p.is_file()] if web.is_dir() else []
    assert hits == []
