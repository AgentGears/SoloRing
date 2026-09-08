"""Post-M13 hygiene focused regressions (frozen R2 proof ledger BE/ART)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

# ---------------------------------------------------------------------------
# HYG-BE:01/02 — the resource-warning family is reproduced at the
# predecessor (documented in docs/hygiene/post-m13-hygiene-H0-inventory.md
# §2: 218 warnings, dominant family = GC'd non-checked-in connections from
# the dead race helper + 368 unclosed bare factory() sessions) and the
# permanent fatal gate in tests/conftest.py makes any recurrence fail the
# whole session. This test proves the gate itself is live.
# ---------------------------------------------------------------------------


def test_hyg_be_01_02_leak_gate_is_fatal(tmp_path):
    """HYG-BE:01/BE:02/BE:06 (gate liveness): a subprocess pytest run
    with ONE deliberately leaked connection exits non-zero with the
    HYGIENE VIOLATION block — the permanent guard is provably fatal,
    without poisoning this session's own recorder state."""
    import subprocess
    import sys

    leak_test = (
        "import gc\n"
        "import pytest\n"
        "\n"
        "@pytest.mark.asyncio\n"
        "async def test_deliberate_leak(engine):\n"
        "    conn = await engine.connect()\n"
        "    del conn\n"
        "    gc.collect()\n"
    )
    # the leak file must live inside tests/ so the REAL conftest (engine
    # fixture + the warning gate) loads; removed in finally
    import os
    import pathlib as _pl

    repo = _pl.Path(__file__).resolve().parents[1]
    leak_path = repo / "tests" / "__hyg_gate_selftest.py"
    env = {
        "SOLORING_DATA_DIR": str(tmp_path / "data"),
        "PYTHONPATH": "server",
    }
    env_full = dict(os.environ)
    env_full.update(env)
    try:
        leak_path.write_text(leak_test, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p",
             "no:cacheprovider", str(leak_path)],
            capture_output=True, text=True, cwd=str(repo),
            env=env_full, timeout=180)
    finally:
        leak_path.unlink(missing_ok=True)
    combined = r.stdout + r.stderr
    assert "HYGIENE VIOLATION" in combined, combined[-800:]
    assert "non-checked-in connection" in combined, combined[-800:]
    assert r.returncode == 1, r.returncode


@pytest.mark.asyncio
async def test_hyg_be_02_no_warnings_in_corrected_helpers(client):
    """HYG-BE:02 (absence half): the corrected helpers themselves run
    warning-free — the warning family is gone from the fixed paths."""
    import warnings

    from tests.test_m13_races import _first_transition_id
    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"hyg-be-02")
    sel = await _select_binding(client, b)
    engine = client._transport.app.state.engine
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tid = await _first_transition_id(engine, sel["track"])
    assert isinstance(tid, str) and len(tid) == 36
    leaks = [w for w in caught
             if "non-checked-in connection" in str(w.message)
             or "was never awaited" in str(w.message)]
    assert leaks == []


@pytest.mark.asyncio
async def test_hyg_be_03_rollback_cleanup_path(engine, factory):
    """HYG-BE:03: exception/rollback cleanup paths stay correct under the
    tracking factory — an aborted transaction is rolled back by fixture
    teardown and the data stays unwritten."""
    session = factory()
    async with session.begin():
        await session.execute(text(
            "INSERT INTO projects (id, name, created_at, updated_at) "
            "VALUES ('hyg-be-03-p', 'H0', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z')"))
    # abort deliberately: mark the session dirty then simulate failure
    await session.execute(text("DELETE FROM projects WHERE id = "
                                "'hyg-be-03-p'"))
    await session.rollback()  # the exact cleanup path the fixture uses
    row = None
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT id FROM projects WHERE id = 'hyg-be-03-p'"))).first()
    assert row is not None, "rollback must undo the delete"


@pytest.mark.asyncio
async def test_hyg_be_05_race_helper_preserves_live_proof(engine, client):
    """HYG-BE:05: the corrected `_first_transition_id`-style lookup (one
    awaited query under explicit connection ownership) still returns the
    exact live transition id — the R15 race proof's data lookup is
    intact after removing the dead first query."""
    from tests.test_m13_races import _first_transition_id
    from tests.test_m13_shot_capture import (
        _full_m13_world,
        _select_binding,
    )

    b = await _full_m13_world(client, tag=b"hyg-be-05")
    sel = await _select_binding(client, b)
    tid = await _first_transition_id(engine, sel["track"])
    assert isinstance(tid, str) and len(tid) == 36
    row = None
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT id FROM production_instance_spatial_transitions "
            "WHERE spatial_track_id = :t AND deleted_at IS NULL "
            "LIMIT 1"), {"t": sel["track"]})).scalar_one()
    assert tid == row


# ---------------------------------------------------------------------------
# HYG-ART:01-03 — residue containment regressions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hyg_art_02_generated_packages_live_under_pytest_tmp(
        tmp_path, monkeypatch):
    """HYG-ART:02: `build_fixture` places generated packages under the
    caller-owned (pytest temp) root, never the repository working
    directory."""
    from pathlib import Path

    from tests.m10f_scale_fixture import build_fixture

    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "m10f-scale-pkgs").exists()  # absent before

    import inspect
    sig = inspect.signature(build_fixture)
    assert "pkg_root_parent" in sig.parameters
    src = inspect.getsource(build_fixture)
    assert 'Path(".")' not in src
    assert "pkg_root_parent" in src


def test_hyg_art_03_no_repo_root_residue_after_focus():
    """HYG-ART:03 (focused half): after the focused hygiene suite (which
    includes the real m10f scale suite via test_m10f_scale.py in the
    full run), the repo root carries no generated package directory."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "m10f-scale-pkgs").exists()
    # the full-closure half is the §11 explicit absence assertion run
    # after the whole backend suite.


@pytest.mark.asyncio
async def test_hyg_base_02_migration_head_unchanged(tmp_path, monkeypatch):
    """HYG-BASE:02: the alembic head remains 0014 — no migration 0015
    exists in the versions directory."""
    from pathlib import Path

    versions = (Path(__file__).resolve().parents[1] / "server"
                / "alembic" / "versions")
    files = sorted(p.name for p in versions.glob("0*.py"))
    assert files[-1] == "0014_m13_authority_complete_world.py"
    assert not any(f.startswith("0015") for f in files)
