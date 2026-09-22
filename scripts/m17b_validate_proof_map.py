"""M17B proof-map validator (frozen R7 §17).

Hard-codes the exact 113-cell id set and rejects missing cells,
duplicate cells, unknown cells, missing/malformed/dangling owners,
and plan/proof-map cell-set disagreement. Structural evidence only —
it does not substitute for executing the proof owners.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CELLS = (
    "A01", "A02", "A03", "A04",
    "B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09",
    "C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09",
    "C10", "C11",
    "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09",
    "D10", "D11", "D12", "D13", "D14",
    "E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08",
    "F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09",
    "F10",
    "G01", "G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09",
    "G10", "G11", "G12", "G13", "G14", "G15", "G16", "G17", "G18",
    "G19", "G20",
    "H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08", "H09",
    "H10", "H11",
    "I01", "I02", "I03", "I04", "I05", "I06", "I07", "I08", "I09",
    "I10", "I11", "I12",
    "J01", "J02", "J03", "J04", "J05", "J06", "J07", "J08", "J09",
    "K01", "K02", "K03", "K04", "K05",
)
CELL_SET = frozenset(CELLS)

OWNER_RE = re.compile(
    r"^tests/test_m17b_[a-z0-9_]+\.py::test_[a-z0-9_]+$")


def _fail(msg: str) -> int:
    print(f"M17B-PROOF-MAP INVALID: {msg}")
    return 1


def main() -> int:
    errors: list[str] = []

    if len(CELLS) != 113:
        errors.append(f"hard-coded cell list has {len(CELLS)} entries")
    if len(CELL_SET) != len(CELLS):
        errors.append("hard-coded cell list contains duplicates")

    doc = (REPO / "docs" / "SoloRing-M17B-Proof-Map.md").read_text(
        encoding="utf-8")
    rows = re.findall(
        r"\| `([A-K]\d+)` \| (.*?) \| `(tests/[^`]+)` \|", doc)
    md_cells = [c for c, _, _ in rows]
    md_owners = [o for _, _, o in rows]

    if len(md_cells) != 113:
        errors.append(f"docs proof map has {len(md_cells)} cells")
    if len(set(md_cells)) != len(md_cells):
        errors.append("docs proof map has duplicate cells")
    unknown = set(md_cells) - CELL_SET
    if unknown:
        errors.append(f"unknown cells in docs map: {sorted(unknown)}")
    missing = CELL_SET - set(md_cells)
    if missing:
        errors.append(f"missing cells in docs map: {sorted(missing)}")
    if len(md_owners) != len(set(md_owners)):
        errors.append("docs proof map has duplicate owners")
    for o in md_owners:
        if not OWNER_RE.match(o):
            errors.append(f"malformed owner {o!r}")
            continue
        path, func = o.split("::")
        src = REPO / path
        if not src.is_file():
            errors.append(f"owner file missing: {path}")
            continue
        if f"def {func}" not in src.read_text(encoding="utf-8"):
            errors.append(f"dangling owner (test function absent): "
                          f"{o}")

    if errors:
        for e in errors:
            _fail(e)
        return 1
    print(f"M17B proof map valid: {len(md_cells)} cells, every "
          "owner resolves to an existing test function.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
