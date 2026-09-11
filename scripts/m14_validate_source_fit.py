"""M14 source-fit validator (frozen R2 §47/§48).

Rejects M15/M16/deferred vocabulary from the M14-changed product-source
surface (server/soloring/** and apps/web/src/**, versus the exact
predecessor 20429b3). Planning/proof text (docs/, scripts/, tests/)
legitimately quotes this vocabulary in its reject lists and is not
scanned.

Frozen §47/§48 rejected implementation classes, mechanically:
  M15  Production Revision substitution / Performance Revision
  M16  intra-Shot persistent consequences
       physical relationship/contact/support authority
       candidate-world extraction/adoption
       generalized multi-representation registry / scene import
       rig/deformation authoring / simulation
       qualification platform / reference-claim platform
       agent-authored workflows / agent task-context
       multi-user semantics

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = "20429b3bf2ead3ca6c1d2402d5028e500bd4f9e8"

PRODUCT_SOURCE_PREFIXES = (
    "server/soloring/",
    "apps/web/src/",
)

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\bperformance[_ ]?revisions?\b", "M15 Performance Revision"),
    (r"\brevision[_ ]?substitution\b", "M15 revision substitution"),
    (r"\bintra[_-]?shot\b", "M16 intra-Shot consequence"),
    (r"\bpersistent[_ ]?consequences?\b", "M16 persistent consequence"),
    (r"\bphysical[_ ]?(relationship|contact|support)", 
     "physical relationship/contact/support authority"),
    (r"\bcontact[_ ]?authority\b", "physical contact authority"),
    (r"\bcandidate[_ ]?world\b", "candidate-world extraction/adoption"),
    (r"\brepresentation[_ ]?registry\b", "generalized representation registry"),
    (r"\bscene[_ ]?import\b", "general scene/asset import framework"),
    (r"\bgltf\b|\bglb\b|\bfbx\b|\.usd\b|\busda?\b", 
     "GLTF/GLB/OBJ/USD/FBX import platform"),
    (r"\brig[_ ]?(authoring|deformation)\b|\bdeformation[_ ]?authoring\b",
     "rig/deformation authoring"),
    (r"\bsimulation\b", "simulation authority"),
    (r"\bqualification[_ ]?platform\b", "qualification platform"),
    (r"\breference[_ ]?(claim|evidence)[_ ]?platform\b",
     "reference-claim platform"),
    (r"\bagent[_ ]?(authored|task[_ ]?context)\b",
     "agent-authored workflows / task-context"),
    (r"\bmulti[_ ]?user\b", "multi-user semantics"),
]


def git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", BASELINE],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def main() -> int:
    errors: list[str] = []
    for changed in git_changed_files():
        if not changed.startswith(PRODUCT_SOURCE_PREFIXES):
            continue
        path = REPO / changed
        if not path.is_file():
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{changed}: not valid UTF-8 source")
            continue
        for pattern, what in FORBIDDEN_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{changed}: {what} vocabulary present")
    if errors:
        for e in errors:
            print(f"M14-SOURCE-FIT INVALID: {e}", file=sys.stderr)
        return 1
    print("M14 source fit clean: no M15/M16/deferred vocabulary in the "
          "changed product source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
