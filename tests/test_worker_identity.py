"""Worker identity tests (plan §8, §106, §118).

worker_id is generated as str(uuid4()) exactly once at process startup and is:
not configurable, not loaded from the environment, not persisted, not derived
from hostname/PID/machine identity.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

from soloring.worker.runtime import new_worker_id

PRINT_ID = "from soloring.worker.runtime import new_worker_id; print(new_worker_id())"


def _spawn_id(env: dict[str, str] | None = None) -> str:
    """Run a fresh Python process that prints a worker id, return its output."""
    result = subprocess.run(
        [sys.executable, "-c", PRINT_ID],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=True,
    )
    return result.stdout.strip()


def test_new_worker_id_is_canonical_uuid() -> None:
    wid = new_worker_id()
    # canonical lowercase uuid4 form
    assert uuid.UUID(wid).version == 4
    assert wid == str(uuid.UUID(wid))
    assert wid == wid.lower()


def test_repeated_calls_within_process_are_distinct() -> None:
    ids = {new_worker_id() for _ in range(50)}
    assert len(ids) == 50


def test_process_restart_yields_new_worker_id() -> None:
    """Two fresh processes must produce different worker ids (plan §118)."""
    a = _spawn_id()
    b = _spawn_id()
    assert a != b
    assert uuid.UUID(a).version == 4
    assert uuid.UUID(b).version == 4


def test_worker_id_ignores_hostname() -> None:
    """A configured hostname must not replace the worker id (plan §8, §118)."""
    out = _spawn_id(env={"HOSTNAME": "machine-alpha", "COMPUTERNAME": "machine-alpha"})
    assert out != "machine-alpha"
    assert uuid.UUID(out).version == 4


def test_worker_id_ignores_env_override() -> None:
    """No environment variable can fix the worker id (plan §8)."""
    for var in (
        "SOLORING_WORKER_ID",
        "WORKER_ID",
        "SOLORING_WORKERID",
    ):
        out = _spawn_id(env={var: "fixed-identity"})
        assert out != "fixed-identity"
        assert uuid.UUID(out).version == 4


def test_worker_id_not_derived_from_pid() -> None:
    """PID reuse must not recycle a worker id (plan §118)."""
    out = _spawn_id()
    # not purely numeric (a PID would be); must be a uuid
    assert "-" in out
    assert uuid.UUID(out).version == 4


def test_settings_has_no_worker_id_field() -> None:
    """There is deliberately no worker_id setting (plan §8)."""
    from soloring.settings import Settings

    assert "worker_id" not in Settings.model_fields
