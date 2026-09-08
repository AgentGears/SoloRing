"""M13 boundary validator (frozen R3 §31/§33).

Mechanically proves the M13 implementation did not cross into M14:
  * no production-world observation compiler / executor semantics /
    workflow-spec projection / Generation-input materialization in the
    M13-owned source surface;
  * no M13 writes into execution/materialization/runtime modules;
  * no M14 vocabulary in the M13 package.

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

M13_SURFACE = [
    "server/soloring/production_world/",
    "server/soloring/api/production_world.py",
    "server/soloring/api/schemas/production_world.py",
    "server/soloring/spatial/targets.py",
]

# Frozen §33 M14-only vocabulary: observation compilation, executor
# negotiation, workflow-spec evolution, Generation input binding,
# materialization.
FORBIDDEN_PATTERNS = [
    (r"\bobservation_compil", "M14 observation compilation"),
    (r"\bworld_observation\b", "M14 world observation"),
    (r"\bexecutor_capability\b", "M14 executor negotiation"),
    (r"\bcapability_negotiation\b", "M14 executor negotiation"),
    (r"workflow_spec.*production_world|production_world.*workflow_spec",
     "M14 workflow-spec projection"),
    (r"\bmaterializ\w*_world\b|production.world.materializ",
     "M14 production-world materialization"),
    (r"generation_inputs?\"\s*:.*production|production.*generation_input",
     "M14 Generation-input materialization"),
]


def git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only",
         "52af4b151480b8c5931212eba7f927ff2ebda9f0..HEAD"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def main() -> int:
    errors: list[str] = []
    # 1. M13-owned surface carries no M14 semantics
    for surface in M13_SURFACE:
        root = REPO / surface
        files = ([root] if root.is_file() else sorted(
            root.glob("*.py"))) if root.exists() else []
        for f in files:
            src = f.read_text(encoding="utf-8")
            for pattern, what in FORBIDDEN_PATTERNS:
                if re.search(pattern, src, re.I):
                    errors.append(
                        f"{f.relative_to(REPO)}: {what} vocabulary present")
    # 2. M13 must not touch execution/materialization/runtime modules
    for changed in git_changed_files():
        if re.search(
                r"soloring/(executors|worker|realization|generation"
                r"|workflows)/", changed):
            errors.append(
                f"M13 modified execution/runtime module: {changed}")
    if errors:
        for e in errors:
            print(f"M13-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print("M13 boundary clean: no M14 semantics, no runtime-module "
          "changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
