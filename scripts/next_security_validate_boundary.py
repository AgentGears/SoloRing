"""Next-security boundary validator (frozen R2 §17).

Diffs the working tree against exact post-m13-hygiene
(3adead55ca052808260bc4939403bd1fdcc29e13) and rejects:
  * changed files outside the reviewed security-slice allowlist
    (server/soloring, backend tests, unrelated frontend files);
  * any migration at or beyond 0015 / any Alembic change;
  * M14 observation/workflow/executor semantics in changed files;
  * a Next major other than 15 in apps/web/package.json;
  * M14 vocabulary in changed files.

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = "3adead55ca052808260bc4939403bd1fdcc29e13"

# The reviewed security-slice change surface (frozen R2 §5/§8.2/§17)
ALLOWLIST = (
    # framework dependency files
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/web/next-env.d.ts",
    # the two frozen async-param pages
    "apps/web/src/app/projects/[id]/production/page.tsx",
    "apps/web/src/app/projects/[id]/world/page.tsx",
    # security evidence + validators + harness
    "docs/security/",
    "docs/SoloRing-Next-Security-Proof-Map.md",
    "scripts/next_security_validate.py",
    "scripts/next_security_validate_proof_map.py",
    "scripts/next_security_validate_boundary.py",
    "scripts/next_security_smoke.py",
    "tests/test_post_m13_next_security.py",
    # frozen §5: hygiene successor-closure documents touched by this slice
    "docs/hygiene/npm-audit-runtime-exceptions.json",
    "docs/SoloRing-Post-M13-Hygiene-Proof-Map.md",
    "docs/hygiene/post-m13-hygiene-implementation-record.md",
    "scripts/hygiene_validate_boundary.py",
    ".github/workflows/ci.yml",
)

M14_PATTERNS = [
    (r"\bObservationSpec\b", "M14 ObservationSpec"),
    (r"\bWorldObservationSpec\b", "M14 WorldObservationSpec"),
    (r"\bobservation_compil", "M14 observation compilation"),
    (r"\bcapability_negotiation\b", "M14 capability negotiation"),
    (r"\bexecutor_capability\b", "M14 executor capability"),
    (r"workflow_spec.*production_world|production_world.*workflow_spec",
     "M14 workflow-spec projection"),
    (r"production.world.materializ", "M14 production-world materialization"),
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout


def path_allowed(path: str, allowlist) -> bool:
    """Directory entries (trailing '/') match by prefix; every other
    entry requires EXACT equality — an exact-file entry must never
    authorize near-prefix siblings like `x.py.bak`."""
    for entry in allowlist:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def main() -> int:
    errors: list[str] = []

    changed = [f for f in git("diff", "--name-only", f"{BASE}..HEAD")
               .splitlines() if f.strip()]
    for f in changed:
        if f.startswith("server/"):
            errors.append(f"backend change outside the security slice: {f}")
        if f.startswith("server/alembic/"):
            errors.append(f"alembic change outside the security slice: {f}")
        if not path_allowed(f, ALLOWLIST):
            errors.append(f"changed file outside the security allowlist: {f}")

    versions = REPO / "server" / "alembic" / "versions"
    mig_0015 = [p.name for p in versions.glob("*.py")
                if p.stem >= "0015"]
    if mig_0015:
        errors.append(f"migration at/beyond 0015 exists: {mig_0015}")

    # frozen §17: Next major other than 15
    pkg = json.loads((REPO / "apps" / "web" / "package.json")
                     .read_text(encoding="utf-8"))
    next_decl = (pkg.get("dependencies") or {}).get("next", "")
    major = str(next_decl).strip().lstrip("^~").split(".")[0]
    if next_decl and (major != "15" or next_decl.startswith(("^", "~"))):
        errors.append(f"next declaration {next_decl!r} violates the "
                      "frozen contract (exact 15.x pin)")

    for f in changed:
        p = REPO / f
        if not p.is_file() or f.endswith(("next_security_validate_"
                                          "boundary.py",
                                          "hygiene_validate_boundary.py")):
            continue  # boundary validators' own scan patterns name the vocabulary
        src = p.read_text(encoding="utf-8", errors="replace")
        for pattern, what in M14_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{f}: {what} vocabulary present")

    if errors:
        for e in errors:
            print(f"NEXT-SECURITY-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print("Next-security boundary clean: security-slice allowlist scoped, "
          "no server/alembic change, head still 0014, Next major exactly "
          "15, no M14 semantics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
