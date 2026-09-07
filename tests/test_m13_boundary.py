"""M13 boundary proofs (frozen R3 §30.11 M13-BOUNDARY:01)."""

from __future__ import annotations

import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def test_m13_boundary_01():
    """M13-BOUNDARY:01 — no M14 observation/executor/workflow/Generation-
    input semantics in M13 source; no execution/runtime module changes."""
    out = subprocess.run(
        [__import__("sys").executable,
         str(BASE_DIR / "scripts" / "m13_validate_boundary.py")],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr + out.stdout
    assert "M13 boundary clean" in out.stdout
