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
        tmp_path):
    """HYG-ART:02: a REAL representative history build places every
    generated package under the caller-owned (pytest temp) root with
    actual package files on disk; the repo-root directory stays absent
    before and after; omitting pkg_root_parent is rejected at entry
    instead of falling back to unscoped storage."""
    from pathlib import Path

    import pytest as _pytest

    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "m10f-scale-pkgs").exists()  # absent before

    from tests.m10f_scale_fixture import build_fixture

    # the containment contract is mandatory, not defaulted
    with _pytest.raises(ValueError, match="pkg_root_parent"):
        await build_fixture(None, None, None, with_history=True,
                            pkg_root_parent=None)

    from soloring.db import models  # noqa: F401
    from soloring.db.base import Base
    from soloring.db.engine import (
        create_session_factory,
        create_soloring_engine,
    )
    from soloring.settings import Settings
    import soloring.settings as settings_mod
    from tests.m10f_scale_fixture import deterministic_uuid4

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    settings = Settings(data_dir=data_dir)
    saved_singleton = settings_mod._settings
    settings_mod._settings = settings  # _assets writes via get_settings()
    engine = create_soloring_engine(settings)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = create_session_factory(engine)
        with deterministic_uuid4():
            ids = await build_fixture(
                engine, factory, settings, pkg_root_parent=data_dir.parent)
    finally:
        settings_mod._settings = saved_singleton
        await engine.dispose()

    # the history leg really ran (v1/v2/v3 targets all minted)
    assert ids["v1_target_shot"] and ids["v2_target_shot"] and \
        ids["v3_generation"]

    # generated package files exist BELOW pytest-owned temporary storage
    pkg_root = tmp_path / "m10f-scale-pkgs"  # == data_dir.parent
    assert pkg_root.is_dir(), sorted(p.name for p in tmp_path.iterdir())
    package_dirs = [p for p in pkg_root.iterdir() if p.is_dir()]
    assert package_dirs, "no generated package directories"
    files = [f for f in pkg_root.rglob("*") if f.is_file()]
    assert files, "generated package directories carry no files"

    # and the repository working directory stays clean
    assert not (repo_root / "m10f-scale-pkgs").exists()


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
    """HYG-BASE:02 (M14B-2 succession, authorized 2026-09-10): the alembic
    head is exactly 0015_m14_world_observation_execution — the one frozen
    M14 migration — and nothing beyond it exists."""
    from pathlib import Path

    versions = (Path(__file__).resolve().parents[1] / "server"
                / "alembic" / "versions")
    files = sorted(p.name for p in versions.glob("0*.py"))
    assert files[-1] == "0015_m14_world_observation_execution.py"
    assert not any(f >= "0016" for f in files)


# ---------------------------------------------------------------------------
# HYG-DEP:06 — npm-audit baseline validator negative matrix
# ---------------------------------------------------------------------------


def _dep06_baseline() -> dict:
    return {"schema_version": 1, "policy": "UPSTREAM_BLOCKED_RUNTIME_HIGH",
            "exceptions": [{
                "package": "pkg-x",
                "installed_version": "1.2.3",
                "severity": "high",
                "vulnerable_range": ">=1.0.0 <2.0.0",
                "advisories": ["GHSA-1111-2222-3333"],
                "fix_available": {"name": "pkg-x", "version": "9.1.0",
                                  "isSemVerMajor": True},
            }]}


def _dep06_audit(**finding_over) -> dict:
    finding = {
        "severity": "high",
        "range": ">=1.0.0 <2.0.0",
        "via": [{"url": "https://github.com/advisories/"
                        "GHSA-1111-2222-3333"}],
        "fixAvailable": {"name": "pkg-x", "version": "9.1.0",
                         "isSemVerMajor": True},
    }
    finding.update(finding_over)
    return {"vulnerabilities": {"pkg-x": finding}}


def _dep06_lockfile(version: str | None) -> dict:
    packages: dict = {}
    if version is not None:
        packages["node_modules/pkg-x"] = {"version": version}
    return {"lockfileVersion": 3, "packages": packages}


def _dep06_run(tmp_path, audit: dict, baseline: dict, lockfile: dict):
    import json
    import subprocess
    import sys

    repo = __import__("pathlib").Path(__file__).resolve().parents[1]
    audit_p = tmp_path / "audit.json"
    base_p = tmp_path / "baseline.json"
    lock_p = tmp_path / "lock.json"
    audit_p.write_text(json.dumps(audit), encoding="utf-8")
    base_p.write_text(json.dumps(baseline), encoding="utf-8")
    lock_p.write_text(json.dumps(lockfile), encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(repo / "scripts" /
                             "hygiene_validate_npm_audit.py"),
         str(audit_p), "--baseline", str(base_p),
         "--lockfile", str(lock_p)],
        capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_hyg_dep_06_audit_validator_rejects_drift(tmp_path):
    """HYG-DEP:06: the npm-audit baseline validator accepts the exact
    pinned identity and rejects every drift class: unlisted highs,
    advisory identity, vulnerable range, severity (downgrade or
    upgrade), fix package identity, offered-fix major, a non-major fix
    (invalidated exception), installed-version drift, an excepted
    package missing from the lockfile, and a stale exception. Offered
    fix patch/minor drift is upstream-normal and accepted."""
    cases = []
    # exact pinned identity — accepted
    cases.append(("exact accepted", _dep06_audit(),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 0))
    # unlisted runtime high — rejected
    a = _dep06_audit()
    a["vulnerabilities"]["pkg-y"] = dict(
        a["vulnerabilities"]["pkg-x"], via=[{"url": "https://x/GHSA-y"}])
    cases.append(("unlisted high", a, _dep06_baseline(),
                  _dep06_lockfile("1.2.3"), 1))
    # advisory identity drift — rejected
    cases.append(("advisory drift",
                  _dep06_audit(via=[{"url": "https://github.com/"
                                          "advisories/GHSA-9999-9999-9999"}]),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # vulnerable range drift — rejected
    cases.append(("range drift", _dep06_audit(range=">=1.0.0 <2.5.0"),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # severity downgrade must not let a stale exception ride through
    cases.append(("severity downgrade", _dep06_audit(severity="moderate"),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # fix package identity drift — rejected
    cases.append(("fix name drift",
                  _dep06_audit(fixAvailable={"name": "pkg-x-successor",
                                             "version": "9.1.0",
                                             "isSemVerMajor": True}),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # offered fix major drift — rejected (fix identity is material)
    cases.append(("fix major drift",
                  _dep06_audit(fixAvailable={"name": "pkg-x",
                                             "version": "10.0.0",
                                             "isSemVerMajor": True}),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # offered fix patch/minor drift — upstream-normal, accepted
    cases.append(("fix patch drift accepted",
                  _dep06_audit(fixAvailable={"name": "pkg-x",
                                             "version": "9.2.0",
                                             "isSemVerMajor": True}),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 0))
    # compatible (non-major) fix — the exception is invalidated
    cases.append(("invalidated exception",
                  _dep06_audit(fixAvailable={"name": "pkg-x",
                                             "version": "1.2.4",
                                             "isSemVerMajor": False}),
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))
    # installed-version drift vs the baseline pin — rejected
    cases.append(("installed version drift", _dep06_audit(),
                  _dep06_baseline(), _dep06_lockfile("1.9.0"), 1))
    # excepted package missing from the lockfile — rejected
    cases.append(("missing from lockfile", _dep06_audit(),
                  _dep06_baseline(), _dep06_lockfile(None), 1))
    # stale exception (package no longer in the audit) — rejected
    cases.append(("stale exception", {"vulnerabilities": {}},
                  _dep06_baseline(), _dep06_lockfile("1.2.3"), 1))

    for label, audit, baseline, lockfile, want_rc in cases:
        rc, out = _dep06_run(tmp_path, audit, baseline, lockfile)
        assert rc == want_rc, (
            f"{label}: expected rc={want_rc}, got rc={rc}\n{out[-600:]}")
