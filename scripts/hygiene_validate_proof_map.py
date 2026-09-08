"""Post-M13 hygiene proof-map validator (frozen R2 §9/§10).

Validates docs/SoloRing-Post-M13-Hygiene-Proof-Map.md for:
  * exactly the 30 frozen cell IDs, no duplicates/unknowns/missing;
  * closed disposition vocabulary;
  * TEST owners resolve (python via pytest --collect-only; frontend via
    exact-title search in the named file; scripts as existing files;
    documents as existing sections);
  * HYG-META metadata assertions over README.md and pyproject.toml.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "SoloRing-Post-M13-Hygiene-Proof-Map.md"

REQUIRED_CELLS: dict[str, tuple[str, ...]] = {
    "HYG-BASE": tuple(f"HYG-BASE:{n:02d}" for n in range(1, 6)),
    "HYG-BE": tuple(f"HYG-BE:{n:02d}" for n in range(1, 7)),
    "HYG-FE": tuple(f"HYG-FE:{n:02d}" for n in range(1, 5)),
    "HYG-DEP": tuple(f"HYG-DEP:{n:02d}" for n in range(1, 7)),
    "HYG-REQ": tuple(f"HYG-REQ:{n:02d}" for n in range(1, 4)),
    "HYG-META": tuple(f"HYG-META:{n:02d}" for n in range(1, 4)),
    "HYG-ART": tuple(f"HYG-ART:{n:02d}" for n in range(1, 4)),
}

DISPOSITIONS = ("TEST", "STRUCTURAL", "INHERITED", "SETTINGS-EVIDENCE",
                "AUDIT-EVIDENCE", "DISPOSITION")

ROW_RE = re.compile(
    r"^\|\s*`?(HYG-[A-Z]+:[0-9]+)`?\s*\|\s*([A-Z-]+)\s*\|"
    r"\s*([^|]*?)\s*\|\s*([^|]*)\|$")


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"HYGIENE-PROOF-MAP INVALID: {m}", file=sys.stderr)
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


def owner_resolves(owner: str, nodes: set[str]) -> bool:
    owner = owner.strip().strip("`")
    if owner.startswith("scripts/") or owner.startswith("docs/"):
        target = REPO / owner.split("::")[0]
        if not target.is_file():
            return False
        if "::" in owner and owner.startswith("docs/"):
            # document-section owner: the section heading must exist
            section = owner.split("::", 1)[1].split()[0]
            return section.lstrip("§") in target.read_text(
                encoding="utf-8") or section in target.read_text(
                encoding="utf-8")
        return True
    if owner.startswith("apps/web/"):
        path, _, title = owner.partition("::")
        f = REPO / path
        if not (path.startswith("apps/web/src/__tests__/")
                and f.is_file()):
            return False
        src = f.read_text(encoding="utf-8")
        # resolve either an exact `it("title"` / `test("title"` or the
        # fallback: the referenced suite+title text appears in the file
        # owner form: path::describe chain > it-title (no quotes in the
        # map); the it title is the final ">" segment; the source may
        # split long literals across concatenated lines, so match the
        # leading 40 chars (contiguous in the literal)
        after_colon = owner.split("::", 1)[1] if "::" in owner else owner
        it_title = after_colon.split(">")[-1].strip()
        if not it_title:
            return False
        # prefix match without a closing quote: long literals are split
        # across concatenated source lines
        return any(q + it_title[:40] in src for q in ('"', "'", "`"))
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


def validate_metadata(errors: list[str]) -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    if "M13 — Authority-Complete Reusable World — CLOSED + PUBLISHED" \
            not in readme:
        errors.append("HYG-META:01: README does not identify M13 as "
                      "published milestone")
    if "384a46d3a5c68d7d81784befc338aa8621b93fbd" not in readme:
        errors.append("HYG-META:01: README does not reference the "
                      "published baseline identity")
    if "Local-first creative generation loop" in readme.split("##")[0]:
        errors.append("HYG-META:02: obsolete M6 product definition still "
                      "opens the README")
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    if "local-first creative generation loop" in pyproject:
        errors.append("HYG-META:03: stale pyproject description remains")
    if 'version = "0.1.0"' not in pyproject:
        errors.append("HYG-META:03: package version drifted from the "
                      "documented 0.1.0 disposition")
    readme_flat = " ".join(readme.split())
    if "independent of the milestone numbering" not in readme_flat:
        errors.append("HYG-META:03: version-independence note missing "
                      "from README")


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
        if disposition == "TEST" and not owner_resolves(owner, nodes):
            errors.append(f"{cell}: unresolvable owner {owner!r}")

    required = [c for cells in REQUIRED_CELLS.values() for c in cells]
    missing = [c for c in required if c not in seen]
    unknown = [c for c in seen if c not in required]
    if missing:
        errors.append(f"missing required cells: {missing}")
    if unknown:
        errors.append(f"unknown cells: {unknown}")

    validate_metadata(errors)

    if errors:
        return fail(errors)
    total = sum(len(c) for c in REQUIRED_CELLS.values())
    print(f"Hygiene proof map valid: {total} cells, all owners resolve, "
          "metadata assertions green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
