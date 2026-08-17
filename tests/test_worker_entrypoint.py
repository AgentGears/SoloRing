"""Real `python -m soloring.worker` entrypoint tests (audit #2, #3).

These exercise the actual OS process boundary (not monkeypatched internals):

  * restart on the same persisted DB yields a new lease worker_id (plan §118),
    and HOSTNAME/SOLORING_WORKER_ID cannot fix it (plan §8);
  * a fatal condition exits non-zero at the OS level (plan §9);
  * lease loss exits zero at the OS level (plan §9, §57).
"""

from __future__ import annotations

import os
import sqlite3 as sq
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from soloring.settings import BASE_DIR

pytestmark = pytest.mark.slow


def _cfg() -> Config:
    cfg = Config(str(BASE_DIR / "server" / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "server" / "alembic"))
    return cfg


def _migrate(data_dir: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    import soloring.settings as settings_mod

    monkeypatch.setattr(settings_mod, "_settings", None)
    command.upgrade(_cfg(), "head")


def _env(data_dir: Path, **extra: object) -> dict[str, str]:
    env = {
        **os.environ,
        "SOLORING_DATA_DIR": str(data_dir),
        # Timing fields are int seconds; values must satisfy the validator
        # (TTL >= 3*refresh). TTL=3/refresh=1 is the fastest valid integer config.
        "SOLORING_WORKER_LEASE_TTL_SECONDS": "3",
        "SOLORING_WORKER_LEASE_REFRESH_INTERVAL_SECONDS": "1",
        "SOLORING_WORKER_POLL_INTERVAL_SECONDS": "1",
    }
    env.update({k: str(v) for k, v in extra.items()})
    return env


def _launch(data_dir: Path, **extra: object) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "soloring.worker"],
        env=_env(data_dir, **extra),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _lease_worker_id(data_dir: Path) -> str | None:
    try:
        con = sq.connect(str(data_dir / "soloring.db"))
        try:
            row = con.execute(
                "SELECT worker_id FROM worker_leases WHERE name='generation-worker'"
            ).fetchone()
        finally:
            con.close()
    except sq.OperationalError:
        return None
    return row[0] if row else None


def _wait_for_lease(
    data_dir: Path, not_equal: str | None = None, timeout: float = 8.0
) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        wid = _lease_worker_id(data_dir)
        if wid and (not_equal is None or wid != not_equal):
            return wid
        time.sleep(0.1)
    raise AssertionError(
        f"timed out waiting for lease (not_equal={not_equal!r}); "
        f"last={_lease_worker_id(data_dir)!r}"
    )


def _reap(proc: subprocess.Popen | None) -> None:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_restart_produces_new_worker_identity(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _migrate(data_dir, monkeypatch)

    a = _launch(data_dir)
    b = None
    try:
        wid_a = _wait_for_lease(data_dir, timeout=8)
        assert uuid.UUID(wid_a).version == 4
        a.terminate()
        a.wait(timeout=5)
        a = None

        # Lease must go stale so a fresh process takes over (plan §118).
        time.sleep(4.0)
        b = _launch(data_dir)
        wid_b = _wait_for_lease(data_dir, not_equal=wid_a, timeout=8)
        assert uuid.UUID(wid_b).version == 4
        assert wid_a != wid_b
    finally:
        _reap(a)
        _reap(b)


def test_env_overrides_cannot_fix_worker_identity(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _migrate(data_dir, monkeypatch)

    a = _launch(
        data_dir,
        SOLORING_WORKER_ID="fixed-identity",
        HOSTNAME="machine-zeta",
        COMPUTERNAME="machine-zeta",
    )
    try:
        wid = _wait_for_lease(data_dir, timeout=8)
    finally:
        _reap(a)
    assert wid != "fixed-identity"
    assert uuid.UUID(wid).version == 4


def test_fatal_condition_exits_nonzero_at_os_level(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("SOLORING_DATA_DIR", str(data_dir))
    # Deliberately NOT migrated -> no worker_leases table -> worker fatals (plan §9).
    res = subprocess.run(
        [sys.executable, "-m", "soloring.worker"],
        env={**os.environ},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert res.returncode == 70, res.stdout + res.stderr
    combined = res.stdout + res.stderr
    assert "fatal worker error" in combined or "no such table" in combined


def test_lease_loss_exits_zero_at_os_level(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _migrate(data_dir, monkeypatch)

    # refresh=2 gives a clean ~2s observation window between A's refreshes.
    a = _launch(
        data_dir,
        SOLORING_WORKER_LEASE_TTL_SECONDS="6",
        SOLORING_WORKER_LEASE_REFRESH_INTERVAL_SECONDS="2",
    )
    try:
        wid_a = _wait_for_lease(data_dir, timeout=8)

        # Simulate a competitor takeover by flipping the lease owner. With the
        # timing invariant in place a *healthy* worker never goes stale, so we
        # exercise A's reaction to losing authority directly: A's next refresh
        # matches 0 rows -> LOST -> clean exit (plan §57, §9).
        con = sq.connect(str(data_dir / "soloring.db"))
        try:
            con.execute("PRAGMA busy_timeout=5000")
            con.execute(
                "UPDATE worker_leases SET worker_id='taken-over-by-other' "
                "WHERE name='generation-worker'"
            )
            con.commit()
        finally:
            con.close()

        rc = a.wait(timeout=10)
        assert rc == 0, f"lease-loss exit was {rc}, expected 0"
        assert wid_a  # sanity: A had owned it
    finally:
        _reap(a)
