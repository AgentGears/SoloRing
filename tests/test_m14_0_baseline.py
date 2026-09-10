"""M14-0 baseline wrapper tests (proof-map cells M14-BASE:01..03).

Each cell runs the corresponding focus of scripts/m14_validate_baseline.py
as a subprocess and requires a clean exit, mirroring the M13 boundary-
wrapper pattern: validator evidence surfaces as ordinary pytest cells.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "scripts" / "m14_validate_baseline.py"


def _run_focus(focus: str) -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--focus", focus],
        capture_output=True, text=True, cwd=REPO,
    )
    assert result.returncode == 0, (
        f"m14_validate_baseline --focus {focus} failed:\n"
        f"{result.stdout}\n{result.stderr}")


def test_m14_base_01() -> None:
    """M14-BASE:01 exact implementation predecessor 20429b3/0a755efe."""
    _run_focus("base01")


def test_m14_base_02() -> None:
    """M14-BASE:02 immutable M13 tag/commit unchanged."""
    _run_focus("base02")


def test_m14_base_03() -> None:
    """M14-BASE:03 migration predecessor exactly 0014."""
    _run_focus("base03")
