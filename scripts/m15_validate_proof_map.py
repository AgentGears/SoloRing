"""M15 proof-map validator (frozen R4 §31/§36).

Validates docs/SoloRing-M15-Proof-Map.md for:
  * exactly 126 unique cells across the frozen R5 families
    (BASE 10 / MIG 10 / CAN 11 / EVAL 20 / TRANS 9 / IMPACT 8 /
     TRACK 8 / APPLY 16 / RACE 7 / HIST 10 / REC 4 / UI 6 / SCALE 7),
    with the
    diagnostic cardinalities derived mechanically from the hard-coded
    inventory and checked against the frozen counts;
  * closed disposition vocabulary {TEST, PENDING} — the frozen §31 map
    assigns every cell a test owner, so M15 has no STRUCTURAL cells;
  * TEST owners resolve against pytest --collect-only (python) or the
    exact quoted frontend test title (apps/web vitest);
  * PENDING owners follow the frozen future-test grammars;
  * M15_REQUIRE_COMPLETE=1 forbids PENDING — the closure mode for M15D;
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
MAP_PATH = REPO / "docs" / "SoloRing-M15-Proof-Map.md"

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "M15-BASE": tuple(f"M15-BASE:{n:02d}" for n in range(1, 11)),
    "M15-MIG": tuple(f"M15-MIG:{n:02d}" for n in range(1, 11)),
    "M15-CAN": tuple(f"M15-CAN:{n:02d}" for n in range(1, 12)),
    "M15-EVAL": tuple(f"M15-EVAL:{n:02d}" for n in range(1, 21)),
    "M15-TRANS": tuple(f"M15-TRANS:{n:02d}" for n in range(1, 10)),
    "M15-IMPACT": tuple(f"M15-IMPACT:{n:02d}" for n in range(1, 9)),
    "M15-TRACK": tuple(f"M15-TRACK:{n:02d}" for n in range(1, 9)),
    "M15-APPLY": tuple(f"M15-APPLY:{n:02d}" for n in range(1, 17)),
    "M15-RACE": tuple(f"M15-RACE:{n:02d}" for n in range(1, 8)),
    "M15-HIST": tuple(f"M15-HIST:{n:02d}" for n in range(1, 11)),
    "M15-REC": tuple(f"M15-REC:{n:02d}" for n in range(1, 5)),
    "M15-UI": tuple(f"M15-UI:{n:02d}" for n in range(1, 7)),
    "M15-SCALE": tuple(f"M15-SCALE:{n:02d}" for n in range(1, 8)),
}

# Frozen R4 §31 diagnostic cardinalities — derived counts must equal these.
FROZEN_FAMILY_COUNTS: dict[str, int] = {
    "M15-BASE": 10,
    "M15-MIG": 10,
    "M15-CAN": 11,
    "M15-EVAL": 20,
    "M15-TRANS": 9,
    "M15-IMPACT": 8,
    "M15-TRACK": 8,
    "M15-APPLY": 16,
    "M15-RACE": 7,
    "M15-HIST": 10,
    "M15-REC": 4,
    "M15-UI": 6,
    "M15-SCALE": 7,
}
FROZEN_TOTAL = 126

ROW_RE = re.compile(
    r"^\|\s*`?(M15-[A-Z-]+:[0-9]+)`?\s*\|\s*(TEST|PENDING)"
    r"\s*\|\s*`?([^|`]+)`?\s*\|\s*([^|]*)\|$"
)
PENDING_PYTHON_RE = re.compile(
    r"^tests/test_m15[a-z0-9_]*\.py::test_[a-z0-9_]+$"
)
PENDING_FRONTEND_RE = re.compile(
    r"^apps/web/src/__tests__/m15-[a-z0-9-]+\.test\.tsx::.+$"
)


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M15-PROOF-MAP INVALID: {m}", file=sys.stderr)
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


def frontend_owner_resolves(owner: str) -> bool:
    if "::" not in owner:
        return False
    path, title = owner.split("::", 1)
    if not (path.startswith("apps/web/src/__tests__/")
            and path.endswith(".tsx")):
        return False
    f = REPO / path
    if not f.is_file():
        return False
    src = f.read_text(encoding="utf-8")
    return any(q + title + q in src for q in ('"', "'", "`"))


def owner_resolves(owner: str, nodes: set[str]) -> bool:
    return python_owner_resolves(owner, nodes) or frontend_owner_resolves(
        owner)


def validate_map_text(text: str, nodes: set[str]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    per_family: dict[str, int] = {}
    pending_cells: list[str] = []
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cell, disposition, owner, _note = (g.strip() for g in m.groups())
        family = cell.rsplit(":", 1)[0]
        if cell in seen:
            errors.append(f"duplicate cell {cell}")
            continue
        seen[cell] = disposition
        per_family[family] = per_family.get(family, 0) + 1
        owner = owner.strip().strip("`")
        if disposition == "TEST":
            if not owner_resolves(owner, nodes):
                errors.append(f"{cell}: unresolvable TEST owner {owner!r}")
        else:  # PENDING
            if not (PENDING_PYTHON_RE.fullmatch(owner)
                    or PENDING_FRONTEND_RE.fullmatch(owner)):
                errors.append(
                    f"{cell}: PENDING owner must follow the frozen "
                    f"future-test grammars, got {owner!r}")
            pending_cells.append(cell)

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")
    # derived cardinalities must equal the frozen §31 diagnostic block
    for family, frozen_count in FROZEN_FAMILY_COUNTS.items():
        derived = per_family.get(family, 0)
        if derived != frozen_count:
            errors.append(
                f"family {family}: derived {derived} cells != frozen "
                f"{frozen_count}")
    derived_total = sum(per_family.values())
    if derived_total != FROZEN_TOTAL:
        errors.append(
            f"derived total {derived_total} != frozen {FROZEN_TOTAL}")
    if os.environ.get("M15_REQUIRE_COMPLETE") == "1" and pending_cells:
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
    print(f"M15 proof map valid: {FROZEN_TOTAL} cells, frozen families "
          "exact, owners disciplined.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
