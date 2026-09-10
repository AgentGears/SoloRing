"""M14 boundary validator (frozen R2 §47).

Mechanically proves the M14 implementation stays inside the frozen
expected implementation classes by classifying every changed path
(working tree + committed, versus the exact predecessor 20429b3):

  allowed classes (frozen §47):
    observation compiler/capability/materializer modules
    Generation schema-4 integration
    workflow/package/profile schema extensions (+ spatial seam reuse)
    worker schema-4 execution
    M14 execution-only provenance models/migration
    recovery head/policy extension
    M14 UI projection (source files only — dependency/framework files
      are rejected outright so an unrelated upgrade cannot ride along)
    proof/evidence/tests scaffolding
    CI validator wiring in ci.yml only

  rejected outright:
    any other repository path, GitHub workflow/settings files beyond
    ci.yml, and frontend dependency/framework manifests.

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = "20429b3bf2ead3ca6c1d2402d5028e500bd4f9e8"

ALLOWED_PATTERNS = [
    # proof / evidence / tests scaffolding (M14-0 surface)
    r"^docs/SoloRing-M14-[^/]+\.md$",
    r"^scripts/m14_validate_[a-z0-9_]+\.py$",
    r"^tests/fixtures/m14/[^/]+$",
    r"^tests/test_m14[a-z0-9_]*\.py$",
    # observation compiler / capability / materializer modules
    r"^server/soloring/observation/",
    # Generation schema-4 integration
    r"^server/soloring/generation/",
    # workflow/package/profile schema extensions + spatial seam reuse
    r"^server/soloring/workflows/",
    r"^server/soloring/realization/",
    r"^server/soloring/spatial/",
    # worker schema-4 execution
    r"^server/soloring/worker/",
    # M14 execution-only provenance models
    r"^server/soloring/m14/",
    # migration 0015 (M14B-2 scope; absent until that slice lands)
    r"^server/alembic/versions/0015_m14_world_observation_execution\.py$",
    # recovery head/policy extension
    r"^server/soloring/recovery/",
    # M14 UI projection: app source only, never manifests/config
    r"^apps/web/src/.+",
    # CI validator wiring + byte-exactness attributes for pinned fixtures
    r"^\.github/workflows/ci\.yml$",
    r"^\.gitattributes$",
]

FORBIDDEN_PATTERNS = [
    (r"^\.github/(?!workflows/ci\.yml$)",
     "repository/workflow settings beyond ci.yml"),
    (r"^apps/web/package(-lock)?\.json$", "frontend dependency manifest"),
    (r"^apps/web/next\.config\.[a-z]+$", "frontend framework config"),
    (r"^apps/web/tsconfig.*\.json$", "frontend TypeScript config"),
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
        forbidden = next(
            (what for pat, what in FORBIDDEN_PATTERNS
             if re.search(pat, changed)), None)
        if forbidden:
            errors.append(f"{changed}: {forbidden}")
            continue
        if not any(re.match(p, changed) for p in ALLOWED_PATTERNS):
            errors.append(f"{changed}: outside frozen M14 implementation "
                          "classes (R2 §47)")
    if errors:
        for e in errors:
            print(f"M14-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print("M14 boundary clean: all changed paths inside frozen §47 "
          "implementation classes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
