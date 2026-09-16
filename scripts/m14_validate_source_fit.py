"""M14 source-fit validator (frozen R2 §47/§48).

Rejects M15/M16/deferred vocabulary from the M14-owned product-source surface
(server/soloring/** and apps/web/src/**, versus the exact predecessor 20429b3).
Reviewed later-milestone files are classified explicitly by exact path rather
than weakening the M14 vocabulary gate. Planning/proof text (docs/, scripts/,
tests/) legitimately quotes this vocabulary in its reject lists and is not
scanned.

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

# Exact reviewed successor surfaces. These are not M14 implementation and must
# not be judged as if they were. Keep this set exact so unrelated product source
# containing M16 vocabulary still fails the predecessor source-fit gate.
REVIEWED_SUCCESSOR_PATHS = frozenset({
    # M16-P0 predecessor repairs.
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/__init__.py",
    "server/soloring/recovery/semantic_successors.py",
    "server/soloring/recovery/successor_semantics.py",
    "server/soloring/recovery/m16_verifier.py",
    # M16-A exact authority/lifecycle slice + the reviewed M16-B
    # resolver/Shot-detail readiness integration seam.
    "server/soloring/continuity/intra_shot_models.py",
    "server/soloring/continuity/intra_shot_canonical.py",
    "server/soloring/continuity/intra_shot_service.py",
    "server/soloring/continuity/intra_shot_resolver.py",
    "server/soloring/continuity/intra_shot_capture.py",
    "server/soloring/continuity/intra_shot_history.py",
    "server/soloring/continuity/snapshots.py",
    "server/soloring/domain/revisions.py",
    "server/soloring/generation/service.py",
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/backup.py",
    "server/soloring/recovery/successor_semantics.py",
    "server/soloring/recovery/m16_verifier.py",
    "server/soloring/api/schemas/shots.py",
    "server/soloring/api/shots.py",
    "server/soloring/api/schemas/intra_shot.py",
    "server/soloring/api/intra_shot.py",
    "server/soloring/api/main.py",
    "server/soloring/domain/shots.py",
    "server/soloring/db/models.py",
    "server/soloring/errors.py",
})

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
        if changed in REVIEWED_SUCCESSOR_PATHS:
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
    print(
        "M14 source fit clean: no M15/M16/deferred vocabulary in M14-owned "
        "changed product source; exact reviewed M16 successor paths classified."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
