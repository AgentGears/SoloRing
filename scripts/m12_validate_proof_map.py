"""M12 proof-map validator (frozen R3 §21).

Validates docs/SoloRing-M12-Proof-Map.md for:
  * exactly 123 unique cells across the frozen domain cardinalities;
  * closed TEST/STRUCTURAL owner vocabulary;
  * Python owner resolution against pytest --collect-only;
  * frontend owner resolution against exact test titles;
  * dangling/duplicate/unknown cells rejected;
  * M12-RACE:08: race-proof sources contain no timing-sleep or
    transaction-acquisition-mock shortcuts (STRUCTURAL, validator-owned).

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-M12-Proof-Map.md"

DISPOSITIONS = ("TEST", "STRUCTURAL")

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "M12-ID": tuple(f"M12-ID:{n:02d}" for n in range(1, 8)),
    "M12-WORK": tuple(f"M12-WORK:{n:02d}" for n in range(1, 11)),
    "M12-PUB": tuple(f"M12-PUB:{n:02d}" for n in range(1, 13)),
    "M12-NEST": tuple(f"M12-NEST:{n:02d}" for n in range(1, 9)),
    "M12-LINEAGE": tuple(f"M12-LINEAGE:{n:02d}" for n in range(1, 15)),
    "M12-SCOPE": tuple(f"M12-SCOPE:{n:02d}" for n in range(1, 7)),
    "M12-HISTORY": tuple(f"M12-HISTORY:{n:02d}" for n in range(1, 7)),
    "M12-MIG": tuple(f"M12-MIG:{n:02d}" for n in range(1, 10)),
    "M12-RECOVERY": tuple(f"M12-RECOVERY:{n:02d}" for n in range(1, 12)),
    "M12-API": tuple(f"M12-API:{n:02d}" for n in range(1, 9)),
    "M12-UI": tuple(f"M12-UI:{n:02d}" for n in range(1, 7)),
    "M12-RACE": tuple(f"M12-RACE:{n:02d}" for n in range(1, 9)),
    "M12-SCALE": tuple(f"M12-SCALE:{n:02d}" for n in range(1, 8)),
    "M12-BOUNDARY": tuple(f"M12-BOUNDARY:{n:02d}" for n in range(1, 8)),
    "M12-PROOF": tuple(f"M12-PROOF:{n:02d}" for n in range(1, 5)),
}

ROW_RE = re.compile(
    r"^\|\s*`?([A-Z0-9-]+:[0-9]+[a-z]?)`?\s*\|\s*(TEST|STRUCTURAL)\s*\|"
    r"\s*`?([^|`]+)`?\s*\|\s*([^|]*)\|$"
)


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M12-PROOF-MAP INVALID: {m}", file=sys.stderr)
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
    """M12-RACE:08 STRUCTURAL owner (frozen §21).

    Race-proof sources must use the parked real BEGIN IMMEDIATE mechanism
    and contain no timing sleeps or transaction-acquisition mocks.
    """
    errors: list[str] = []
    race_files = sorted((REPO / "tests").glob("test_m12_race*.py"))
    race_files += sorted((REPO / "tests").glob("test_m12_races.py"))
    if not race_files:
        return ["M12-RACE:08: no race-proof sources found"]
    for f in race_files:
        src = f.read_text(encoding="utf-8")
        if re.search(r"asyncio\.sleep\(\s*[1-9]", src):
            errors.append(f"{f.name}: timed sleep in race evidence")
        if re.search(r"asyncio\.sleep\(\s*0?\.\d", src):
            errors.append(f"{f.name}: fractional sleep in race evidence")
        if re.search(r"monkeypatch\(.+(exec_driver_sql|BEGIN IMMEDIATE)",
                     src, re.I):
            errors.append(f"{f.name}: transaction-acquisition mock")
        if "before_cursor_execute" not in src and "exec_driver_sql" not in src:
            errors.append(f"{f.name}: parked real writer mechanism absent")
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
        if owner.startswith("apps/web/"):
            if disposition == "TEST" and not frontend_owner_resolves(owner):
                errors.append(f"{cell}: unresolvable frontend owner {owner!r}")
        elif owner.startswith(("scripts/", "server/")):
            target = REPO / owner.split("::")[0]
            if not target.is_file():
                errors.append(f"{cell}: structural owner file missing {owner!r}")
        elif python_owner_resolves(owner, nodes):
            pass
        else:
            errors.append(f"{cell}: unresolvable python owner {owner!r}")

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
    print(f"M12 proof map valid: {total} cells, all owners resolve, "
          "race discipline clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
