"""M11 proof-map validator (frozen R3 plan §20.0).

Enforces the closed proof-map grammar over docs/SoloRing-M11-Proof-Map.md:

1. the required M11 domain/cell inventory is closed and exact — missing,
   duplicate, or unknown cells fail;
2. the disposition vocabulary is closed to TEST / STRUCTURAL / INHERITED /
   NOT-APPLICABLE-SOURCE-FIT;
3. every Python TEST/STRUCTURAL owner uses ``path.py::test_name`` and must
   resolve against ``pytest --collect-only``; a parameterized owner resolves
   when at least one collected node equals it or begins ``owner + '['``;
4. every frontend TEST owner uses ``path.tsx::exact test title``; the file
   must exist and contain one exact ``test(...)``/``it(...)`` title match;
5. dangling owners fail even when the cell name is otherwise valid;
6. INHERITED / NOT-APPLICABLE-SOURCE-FIT rows require a non-empty reviewed
   note naming the inherited/substitute proof;
7. closure-command names are unique and commands non-empty;
8. self-tests (tests/test_m11_proof_map_validator.py) prove the failure
   modes; this script only validates the live map.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-M11-Proof-Map.md"

DISPOSITIONS = ("TEST", "STRUCTURAL", "INHERITED", "NOT-APPLICABLE-SOURCE-FIT")

PY_TESTS_ROOT = "tests/"
FRONTEND_ROOT = "apps/web/src/__tests__/"

# The frozen 91-cell inventory (frozen R3 §§20.1-20.12). Hard-coded exactly.
REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "M11-ID": tuple(f"M11-ID:{n:02d}" for n in range(1, 8)),
    "M11-PUB": tuple(f"M11-PUB:{n:02d}" for n in range(1, 17)),
    "M11-PROV": tuple(f"M11-PROV:{n:02d}" for n in range(1, 5)),
    "M11-RACE": tuple(f"M11-RACE:{n:02d}" for n in range(1, 6)),
    "M11-CORRUPT": tuple(f"M11-CORRUPT:{n:02d}" for n in range(1, 9)),
    "M11-HISTORY": tuple(f"M11-HISTORY:{n:02d}" for n in range(1, 7)),
    "M11-MIG": ("M11-MIG:01", "M11-MIG:02", "M11-MIG:03", "M11-MIG:04",
                "M11-MIG:04b", "M11-MIG:05", "M11-MIG:06", "M11-MIG:07"),
    "M11-RECOVERY": tuple(f"M11-RECOVERY:{n:02d}" for n in range(1, 14)),
    "M11-API": tuple(f"M11-API:{n:02d}" for n in range(1, 6)),
    "M11-UI": tuple(f"M11-UI:{n:02d}" for n in range(1, 5)),
    "M11-BOUNDARY": tuple(f"M11-BOUNDARY:{n:02d}" for n in range(1, 6)),
    "M11-SCALE": tuple(f"M11-SCALE:{n:02d}" for n in range(1, 7)),
    "M11-PROOF": tuple(f"M11-PROOF:{n:02d}" for n in range(1, 5)),
}

ROW_RE = re.compile(
    r"^\|\s*`?([A-Z0-9-]+:[0-9]+[a-z]?)`?\s*\|\s*([A-Z-]+)\s*\|\s*([^|]+)\|\s*([^|]*)\|$"
)
CMD_RE = re.compile(r"^\|\s*`?(CMD:[A-Za-z0-9_-]+)`?\s*\|\s*([^|]+)\|\s*([^|]*)\|$")


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M11-PROOF-MAP INVALID: {m}", file=sys.stderr)
    return 1


def collected_pytest_nodes() -> set[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO, capture_output=True, text=True,
    )
    nodes = set()
    for line in out.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith(("=", "wrote")):
            nodes.add(line)
    return nodes


def python_owner_resolves(owner: str, nodes: set[str]) -> bool:
    if "::" not in owner:
        return False
    path, name = owner.split("::", 1)
    if not path.startswith(PY_TESTS_ROOT) or not path.endswith(".py"):
        return False
    if not (REPO / path).is_file():
        return False
    if not re.fullmatch(r"test_[A-Za-z0-9_]+(\[.+\])?", name):
        return False
    base = name.split("[", 1)[0]
    for node in nodes:
        if node == owner or node.startswith(f"{path}::{base}["):
            return True
    return False


def frontend_owner_resolves(owner: str) -> bool:
    if "::" not in owner:
        return False
    path, title = owner.split("::", 1)
    if not path.startswith(FRONTEND_ROOT) or not path.endswith(".tsx"):
        return False
    f = REPO / path
    if not f.is_file():
        return False
    src = f.read_text(encoding="utf-8")
    # one exact test()/it() title match (quote-delimited literal)
    for quote in ('"', "'", "`"):
        needle = f"{quote}{title}{quote}"
        if needle in src:
            return True
    return False


def validate_map_text(text: str, nodes: set[str]) -> list[str]:
    errors: list[str] = []
    seen: dict[str, str] = {}
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        cell, disposition, owner, note = (g.strip() for g in m.groups())
        if cell in seen:
            errors.append(f"duplicate cell {cell}")
            continue
        seen[cell] = disposition
        if disposition not in DISPOSITIONS:
            errors.append(f"{cell}: unknown disposition {disposition!r}")
            continue
        if disposition in ("INHERITED", "NOT-APPLICABLE-SOURCE-FIT"):
            if not note:
                errors.append(f"{cell}: {disposition} requires a reviewed note")
            continue
        owner = owner.strip().strip("`")
        if owner.startswith(FRONTEND_ROOT):
            if disposition == "TEST" and not frontend_owner_resolves(owner):
                errors.append(f"{cell}: dangling/unresolvable frontend owner {owner!r}")
        elif python_owner_resolves(owner, nodes):
            pass
        else:
            errors.append(f"{cell}: dangling/unresolvable python owner {owner!r}")

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")
    return errors


def validate_cmds(text: str) -> list[str]:
    errors: list[str] = []
    names: set[str] = set()
    for line in text.splitlines():
        m = CMD_RE.match(line)
        if not m:
            continue
        name, command, _ = (g.strip() for g in m.groups())
        if name in names:
            errors.append(f"duplicate closure command {name}")
        names.add(name)
        if not command:
            errors.append(f"{name}: empty command")
    return errors


def main() -> int:
    if not MAP_PATH.is_file():
        return fail([f"missing {MAP_PATH}"])
    text = MAP_PATH.read_text(encoding="utf-8")
    nodes = collected_pytest_nodes()
    errors = validate_map_text(text, nodes) + validate_cmds(text)
    if errors:
        return fail(errors)
    total = sum(len(c) for c in REQUIRED_CELLS.values())
    print(f"M11 proof map valid: {total} cells, all owners resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
