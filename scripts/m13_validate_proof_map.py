"""M13 proof-map validator (frozen R3 §30/§31).

Validates docs/SoloRing-M13-Proof-Map.md for:
  * exactly 115 unique cells across the frozen families, with every
    R1-R16 race individually owned;
  * closed TEST disposition vocabulary;
  * Python owner resolution against pytest --collect-only;
  * dangling/duplicate/unknown cells rejected;
  * M13-RACE cells: race-proof sources contain no timing-sleep or
    transaction-acquisition-mock shortcuts (STRUCTURAL, validator-owned).

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-M13-Proof-Map.md"

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "M13-SUBJECT": tuple(f"M13-SUBJECT:{n:02d}" for n in range(1, 12)),
    "M13-INTERP": tuple(f"M13-INTERP:{n:02d}" for n in range(1, 10)),
    "M13-STATE": tuple(f"M13-STATE:{n:02d}" for n in range(1, 9)),
    "M13-SPACE": tuple(f"M13-SPACE:{n:02d}" for n in range(1, 9)),
    "M13-BIND": tuple(f"M13-BIND:{n:02d}" for n in range(1, 18)),
    "M13-IMPACT": tuple(f"M13-IMPACT:{n:02d}" for n in range(1, 9)),
    "M13-SHOT": tuple(f"M13-SHOT:{n:02d}" for n in range(1, 16)),
    "M13-HISTORY": tuple(f"M13-HISTORY:{n:02d}" for n in range(1, 11)),
    "M13-MIG": tuple(f"M13-MIG:{n:02d}" for n in range(1, 5)),
    "M13-RECOVERY": tuple(f"M13-RECOVERY:{n:02d}" for n in range(1, 6)),
    "M13-RACE": tuple(f"M13-RACE:{n:02d}" for n in range(1, 17)),
    "M13-SCALE": tuple(f"M13-SCALE:{n:02d}" for n in range(1, 4)),
    "M13-BOUNDARY": ("M13-BOUNDARY:01",),
}

ROW_RE = re.compile(
    r"^\|\s*`?([A-Z0-9-]+:[0-9]+[a-z]?)`?\s*\|\s*(TEST|STRUCTURAL)\s*\|"
    r"\s*`?([^|`]+)`?\s*\|\s*([^|]*)\|$"
)


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M13-PROOF-MAP INVALID: {m}", file=sys.stderr)
    return 1


def collected_pytest_nodes() -> set[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    return {
        line.strip() for line in out.stdout.splitlines()
        if "::" in line and not line.startswith(("=", "wrote"))
    }


def python_owner_resolves(owner: str, nodes: set[str]) -> bool:
    if "::" not in owner:
        return False
    path, name = owner.split("::", 1)
    if not (path.startswith("tests/") and path.endswith(".py")):
        return False
    if not (REPO / path).is_file():
        return False
    if not re.fullmatch(r"test_[A-Za-z0-9_]+(\[.+\])?", name):
        return False
    base = name.split("[", 1)[0]
    return any(
        node == owner or node.startswith(f"{path}::{base}[")
        for node in nodes
    )


def validate_race_proof_no_shortcuts() -> list[str]:
    """All M13 race evidence uses parked fences/events; no sleeps or mocks."""
    errors: list[str] = []
    race_files = sorted((REPO / "tests").glob("test_m13_race*.py"))
    race_files += sorted((REPO / "tests").glob("test_m13_races.py"))
    if not race_files:
        return ["race cells: no race-proof sources found"]
    for f in race_files:
        src = f.read_text(encoding="utf-8")
        if re.search(r"asyncio\.sleep\(\s*[1-9]", src):
            errors.append(f"{f.name}: timed sleep in race evidence")
        if re.search(r"asyncio\.sleep\(\s*0?\.\d", src):
            errors.append(f"{f.name}: fractional sleep in race evidence")
        if re.search(r"monkeypatch\(.+(exec_driver_sql|BEGIN IMMEDIATE)",
                     src, re.I):
            errors.append(f"{f.name}: transaction-acquisition mock")
        if ("before_cursor_execute" not in src
                and "exec_driver_sql" not in src
                and "PREFENCE_SEAM" not in src
                and "SELECTION_SEAM" not in src):
            errors.append(f"{f.name}: forced-interleaving mechanism absent")
    return errors


def validate_map_text(text: str, nodes: set[str]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cell, disposition, owner, _note = (g.strip() for g in m.groups())
        if cell in seen:
            errors.append(f"duplicate cell {cell}")
            continue
        seen[cell] = disposition
        owner = owner.strip().strip("`")
        if python_owner_resolves(owner, nodes):
            pass
        else:
            errors.append(f"{cell}: unresolvable owner {owner!r}")

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")
    return errors


def main() -> int:
    if not MAP_PATH.is_file():
        return fail([f"missing {MAP_PATH}"])
    text = MAP_PATH.read_text(encoding="utf-8")
    nodes = collected_pytest_nodes()
    errors = (validate_map_text(text, nodes)
              + validate_race_proof_no_shortcuts())
    if errors:
        return fail(errors)
    total = sum(len(c) for c in REQUIRED_CELLS.values())
    print(f"M13 proof map valid: {total} cells, all owners resolve, "
          "race discipline clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
