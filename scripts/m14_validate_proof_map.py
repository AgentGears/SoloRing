"""M14 proof-map validator (frozen R2 §46/§51).

Validates docs/SoloRing-M14-Proof-Map.md for:
  * exactly 90 unique cells across the frozen families
    (BASE 6 / OBS 19 / CAP 12 / PKG 9 / MAT 15 / HIST 12 / EXEC 10 /
     SCALE 5 / UI 2);
  * closed disposition vocabulary {TEST, STRUCTURAL, PENDING};
  * TEST owners resolve against pytest --collect-only;
  * STRUCTURAL owners name one of the M14 validator scripts;
  * PENDING owners follow the frozen future-test naming grammar
    (tests/test_m14*.py::test_m14*) and are permitted only while their
    slice has not landed — M14_REQUIRE_COMPLETE=1 forbids them and is
    the closure mode for M14B-6;
  * duplicate/dangling/unknown cells rejected.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-M14-Proof-Map.md"

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "M14-BASE": tuple(f"M14-BASE:{n:02d}" for n in range(1, 7)),
    "M14-OBS": tuple(f"M14-OBS:{n:02d}" for n in range(1, 20)),
    "M14-CAP": tuple(f"M14-CAP:{n:02d}" for n in range(1, 13)),
    "M14-PKG": tuple(f"M14-PKG:{n:02d}" for n in range(1, 10)),
    "M14-MAT": tuple(f"M14-MAT:{n:02d}" for n in range(1, 16)),
    "M14-HIST": tuple(f"M14-HIST:{n:02d}" for n in range(1, 13)),
    "M14-EXEC": tuple(f"M14-EXEC:{n:02d}" for n in range(1, 11)),
    "M14-SCALE": tuple(f"M14-SCALE:{n:02d}" for n in range(1, 6)),
    "M14-UI": tuple(f"M14-UI:{n:02d}" for n in range(1, 3)),
}

ROW_RE = re.compile(
    r"^\|\s*`?([A-Z0-9-]+:[0-9]+[a-z]?)`?\s*\|\s*(TEST|STRUCTURAL|PENDING)"
    r"\s*\|\s*`?([^|`]+)`?\s*\|\s*([^|]*)\|$"
)

STRUCTURAL_OWNER_RE = re.compile(
    r"^scripts/m14_validate_(baseline|boundary|proof_map|source_fit)\.py$"
)
PENDING_OWNER_RE = re.compile(
    r"^tests/test_m14[a-z0-9_]*\.py::test_m14_[a-z0-9_]+$"
)


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M14-PROOF-MAP INVALID: {m}", file=sys.stderr)
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


def validate_map_text(text: str, nodes: set[str]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    pending_cells: list[str] = []
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
        if disposition == "TEST":
            if not python_owner_resolves(owner, nodes):
                errors.append(f"{cell}: unresolvable TEST owner {owner!r}")
        elif disposition == "STRUCTURAL":
            if not STRUCTURAL_OWNER_RE.fullmatch(owner):
                errors.append(
                    f"{cell}: STRUCTURAL owner must name an M14 validator "
                    f"script, got {owner!r}")
        else:  # PENDING
            if not PENDING_OWNER_RE.fullmatch(owner):
                errors.append(
                    f"{cell}: PENDING owner must follow the frozen "
                    f"future-test grammar, got {owner!r}")
            pending_cells.append(cell)

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")
    if os.environ.get("M14_REQUIRE_COMPLETE") == "1" and pending_cells:
        errors.append(
            f"closure mode forbids PENDING cells: {sorted(pending_cells)}")
    return errors


def main() -> int:
    if not MAP_PATH.is_file():
        return fail([f"missing {MAP_PATH}"])
    text = MAP_PATH.read_text(encoding="utf-8")
    nodes = collected_pytest_nodes()
    errors = validate_map_text(text, nodes)
    if errors:
        return fail(errors)
    total = sum(len(c) for c in REQUIRED_CELLS.values())
    print(f"M14 proof map valid: {total} cells, frozen families exact, "
          "owners disciplined.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
