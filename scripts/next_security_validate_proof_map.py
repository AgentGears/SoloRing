"""Next-security proof-map validator (frozen R2 §14).

Validates docs/SoloRing-Next-Security-Proof-Map.md for:
  * exactly the 20 frozen cell IDs, no duplicates/unknowns/missing;
  * closed disposition vocabulary;
  * the frozen owner contract: every cell carries EXACTLY ONE owner
    (no multi-owner fields) and that owner resolves for ALL
    dispositions (python via pytest --collect-only; scripts/documents
    as existing files; document-section owners as existing headings).

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-Next-Security-Proof-Map.md"

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "NSEC-BASE": tuple(f"NSEC-BASE:{n:02d}" for n in range(1, 5)),
    "NSEC-PKG": tuple(f"NSEC-PKG:{n:02d}" for n in range(1, 6)),
    "NSEC-APP": tuple(f"NSEC-APP:{n:02d}" for n in range(1, 5)),
    "NSEC-SEC": tuple(f"NSEC-SEC:{n:02d}" for n in range(1, 5)),
    "NSEC-CLOSE": tuple(f"NSEC-CLOSE:{n:02d}" for n in range(1, 4)),
}

DISPOSITIONS = ("TEST", "STRUCTURAL", "INHERITED", "SETTINGS-EVIDENCE",
                "AUDIT-EVIDENCE", "DISPOSITION")

ROW_RE = re.compile(
    r"^\|\s*`?(NSEC-[A-Z]+:[0-9]+)`?\s*\|\s*([A-Z-]+)\s*\|"
    r"\s*([^|]*?)\s*\|\s*([^|]*)\|$")


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"NEXT-SECURITY-PROOF-MAP INVALID: {m}", file=sys.stderr)
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


def _doc_owner_resolves(owner: str) -> bool:
    if "::" in owner:
        path_s, section = owner.split("::", 1)
        section = section.strip()
    elif " §" in owner:
        path_s, _, section = owner.partition(" §")
        section = section.strip()
    else:
        path_s, section = owner, ""
    f = REPO / path_s.strip().strip("`")
    if not f.is_file():
        return False
    if not section:
        return True
    m = re.match(r"§?\s*(\d+)", section.strip())
    text = f.read_text(encoding="utf-8")
    if not m:
        return section in text
    return re.search(
        rf"^#+\s*{re.escape(m.group(1))}\b", text, re.M) is not None


def owner_resolves(owner: str, nodes: set[str]) -> bool:
    owner = owner.strip().strip("`")
    if owner.startswith("scripts/"):
        return (REPO / owner).is_file()
    if owner.startswith("docs/"):
        return _doc_owner_resolves(owner)
    if owner.startswith("tests/"):
        if "::" not in owner:
            return (REPO / owner).is_file()
        path, name = owner.split("::", 1)
        if not (REPO / path).is_file():
            return False
        if not re.fullmatch(r"test_[A-Za-z0-9_]+(\[.+\])?", name):
            return False
        base = name.split("[", 1)[0]
        return any(
            node == owner or node.startswith(f"{path}::{base}[")
            for node in nodes)
    return False


def main() -> int:
    if not MAP_PATH.is_file():
        return fail([f"missing {MAP_PATH}"])
    text = MAP_PATH.read_text(encoding="utf-8")
    nodes = collected_pytest_nodes()

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
        if disposition not in DISPOSITIONS:
            errors.append(f"{cell}: unknown disposition {disposition!r}")
        if " + " in owner:
            errors.append(f"{cell}: owner field names multiple owners "
                          f"(frozen contract: exactly one): {owner!r}")
        elif not owner_resolves(owner, nodes):
            errors.append(f"{cell} [{disposition}]: unresolvable owner "
                          f"{owner!r}")

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")

    if errors:
        return fail(errors)
    total = sum(len(c) for c in REQUIRED_CELLS.values())
    print(f"Next-security proof map valid: {total} cells, every owner "
          "resolves (all dispositions, exactly one per cell).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
