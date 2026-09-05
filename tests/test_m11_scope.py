"""M11 authority-boundary / forbidden-expansion proofs (frozen R3 §20.10).

M11 must not widen Asset semantics, smuggle Shot/Generation/Take capture
scope, introduce an M15 update lifecycle, a generalized representation
registry, or any executor/live-render source delta.
"""

from __future__ import annotations

import subprocess
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

BASE_DIR = Path(__file__).resolve().parents[1]


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _upgrade(tmp_path, monkeypatch, target):
    import soloring.settings as settings_mod

    monkeypatch.setenv("SOLORING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_mod, "_settings", None)
    command.upgrade(_cfg(), target)


def _table_cols(root: Path, table: str) -> list[str]:
    con = sqlite3.connect(root / "soloring.db")
    try:
        return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    finally:
        con.close()


def test_asset_kind_constraint_unchanged(tmp_path, monkeypatch):
    """M11-BOUNDARY:01 — M11 does not widen Asset semantics."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        checks = [
            r[0] for r in con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='assets'")
        ]
        # Exact predecessor CHECKs, unchanged.
        assert "kind IN ('reference', 'output')" in checks[0]
        assert "(kind = 'reference' AND take_id IS NULL) " in checks[0]
        assert "production" not in checks[0]
    finally:
        con.close()


def test_no_shot_generation_take_schema_change(tmp_path, monkeypatch):
    """M11-BOUNDARY:02 — capture/execution authority tables untouched."""
    _upgrade(tmp_path, monkeypatch, "0011_m10_derived_spatial_execution")
    before = {
        t: _table_cols(tmp_path, t)
        for t in ("shots", "shot_revisions", "generations",
                  "generation_inputs", "takes")
    }
    _upgrade(tmp_path, monkeypatch, "head")
    after = {
        t: _table_cols(tmp_path, t)
        for t in ("shots", "shot_revisions", "generations",
                  "generation_inputs", "takes")
    }
    assert before == after


def test_no_production_current_revision_pointer(tmp_path, monkeypatch):
    """M11-BOUNDARY:03 — M15 update lifecycle absent."""
    _upgrade(tmp_path, monkeypatch, "head")
    cols = _table_cols(tmp_path, "production_objects")
    assert not any("revision" in c for c in cols)
    assert not any(c in ("current", "approved", "latest") for c in cols)


def test_no_generalized_representation_registry_table(tmp_path, monkeypatch):
    """M11-BOUNDARY:04 — RP-02 non-edge preserved."""
    _upgrade(tmp_path, monkeypatch, "head")
    con = sqlite3.connect(tmp_path / "soloring.db")
    try:
        prod_tables = sorted(
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE 'production_%'"))
    finally:
        con.close()
    assert prod_tables == [
        "production_objects",
        "production_revision_closures",
        "production_revision_source_assets",
        "production_revisions",
    ]


def test_no_execution_source_delta_in_m11_owned_diff():
    """M11-BOUNDARY:05 — no executor/live-runtime source changed by M11."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "6f5d9771e3e67fa4097b7b7babab238d1f57a57e..HEAD"],
        cwd=BASE_DIR, capture_output=True, text=True, check=True,
    ).stdout
    changed = {line for line in out.splitlines() if line.strip()}
    forbidden_markers = (
        "executor", "worker", "comfy", "realization", "render",
        "generation/", "workflows/",
    )
    offenders = sorted(
        p for p in changed
        if any(m in p.lower() for m in forbidden_markers)
        # the proof-mapping validator itself is an allowed test/CI artifact
        and not p.startswith(("tests/", "scripts/"))
    )
    assert offenders == [], f"execution source touched by M11: {offenders}"


def test_backend_ci_runs_m11_proof_map_validator_before_backend_tests():
    """M11-PROOF:04 — CI executes the M11 validator before backend tests
    and preserves the predecessor proof-map validation."""
    workflow = (BASE_DIR / ".github" / "workflows" / "ci.yml").read_text()
    m11_pos = workflow.find("m11_validate_proof_map.py")
    m10f_pos = workflow.find("m10f_validate_proof_map.py")
    pytest_pos = workflow.find("python -m pytest -q")
    assert m11_pos != -1, "M11 validator missing from Backend CI"
    assert m10f_pos != -1, "predecessor M10F validation was removed"
    assert m11_pos < pytest_pos, "M11 validator must run before backend tests"
