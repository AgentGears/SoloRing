"""Next-security boundary validator (frozen R2 §17).

Diffs the working tree against the implementation boundary and rejects:
  * changed files outside the reviewed security-slice allowlist
    (server/soloring, backend tests, unrelated frontend files);
  * any migration at or beyond 0015 / any Alembic change;
  * M14 observation/workflow/executor semantics in changed files;
  * a Next major other than 15 in apps/web/package.json.

Squash-survival (merge-review correction 2026-09-09): the repository
integrates by SQUASH merge only, so the intermediate hygiene commit is
NOT permanently reachable from published main. Base selection is
dual-mode and deterministic:
  * PREDECESSOR mode — when the reviewed hygiene head 3adead5 is
    reachable, diff exactly 3adead5..HEAD against the strict security
    allowlist (the frozen implementation-boundary proof, unchanged);
  * PUBLISHED mode — otherwise (squash-shaped published history), diff
    published M13 384a46d..HEAD against the union of the security and
    hygiene allowlists (the full reviewed post-M13 surface), and
    require the checked-in predecessor evidence
    (docs/security/nsec-predecessor-evidence.json) to be present and
    internally exact. No ephemeral branch is ever a prerequisite.

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PREDECESSOR = "3adead55ca052808260bc4939403bd1fdcc29e13"
PUBLISHED_M13 = "384a46d3a5c68d7d81784befc338aa8621b93fbd"
EVIDENCE_PATH = REPO / "docs" / "security" / "nsec-predecessor-evidence.json"

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


def git(*args: str, repo: Path = REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True,
                          check=True).stdout


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


def _union_allowlist() -> tuple[str, ...]:
    """Published-mode surface: the reviewed security slice UNION the
    reviewed hygiene slice (post-squash the two collapse into one
    diff against published M13)."""
    spec = importlib.util.spec_from_file_location(
        "hygiene_validate_boundary",
        REPO / "scripts" / "hygiene_validate_boundary.py")
    hyg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hyg)
    merged = sorted(set(ALLOWLIST) | set(hyg.ALLOWLIST))
    return tuple(merged)


def _commit_reachable(sha: str, repo: Path) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
         f"{sha}^{{commit}}"], capture_output=True).returncode == 0


def _evidence_errors(repo: Path = REPO) -> list[str]:
    evidence = repo / "docs" / "security" / "nsec-predecessor-evidence.json"
    if not evidence.is_file():
        return ["squash-shaped history without the checked-in "
                f"predecessor evidence: {evidence} missing"]
    try:
        ev = json.loads(evidence.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"predecessor evidence is not valid JSON: {exc}"]
    expected = {
        "predecessor_commit": PREDECESSOR,
        "predecessor_lock_blob":
            "946639773277989cbc05aca7b28e5a524d764f72",
        "predecessor_lock_next": "14.2.35",
        "published_base_commit": PUBLISHED_M13,
    }
    errors = []
    for key, want in expected.items():
        if ev.get(key) != want:
            errors.append(f"predecessor evidence {key} = "
                          f"{ev.get(key)!r}, expected {want!r}")
    return errors


def select_base(repo: Path = REPO) -> tuple[str, str]:
    """Deterministic dual-mode base selection: the exact reviewed
    predecessor when reachable (frozen implementation-boundary proof),
    otherwise published M13 for squash-shaped history."""
    if _commit_reachable(PREDECESSOR, repo):
        return ("predecessor", PREDECESSOR)
    return ("published", PUBLISHED_M13)


def main(repo: Path = REPO) -> int:
    errors: list[str] = []
    mode, base = select_base(repo)
    allowlist = ALLOWLIST if mode == "predecessor" else \
        _union_allowlist()
    if mode == "published":
        errors.extend(_evidence_errors(repo))

    changed = [f for f in git("diff", "--name-only", f"{base}..HEAD",
                              repo=repo).splitlines() if f.strip()]
    for f in changed:
        if f.startswith("server/"):
            errors.append(f"backend change outside the security slice: {f}")
        if f.startswith("server/alembic/"):
            errors.append(f"alembic change outside the security slice: {f}")
        if not path_allowed(f, allowlist):
            errors.append(f"changed file outside the {mode}-mode "
                          f"allowlist: {f}")

    versions = repo / "server" / "alembic" / "versions"
    mig_0015 = [p.name for p in versions.glob("*.py")
                if p.stem >= "0015"]
    if mig_0015:
        errors.append(f"migration at/beyond 0015 exists: {mig_0015}")

    # frozen §17: Next major other than 15
    pkg = json.loads((repo / "apps" / "web" / "package.json")
                     .read_text(encoding="utf-8"))
    next_decl = (pkg.get("dependencies") or {}).get("next", "")
    major = str(next_decl).strip().lstrip("^~").split(".")[0]
    if next_decl and (major != "15" or next_decl.startswith(("^", "~"))):
        errors.append(f"next declaration {next_decl!r} violates the "
                      "frozen contract (exact 15.x pin)")

    for f in changed:
        p = repo / f
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
    print(f"Next-security boundary clean (mode={mode}, base={base[:12]}…): "
          f"{'security-slice' if mode == 'predecessor' else 'post-M13 union'} "
          "allowlist scoped, no server/alembic change, head still 0014, "
          "Next major exactly 15, no M14 semantics"
          + ("; checked-in predecessor evidence exact."
             if mode == "published" else ""))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    repo_arg = REPO
    if args and args[0] == "--repo":
        if len(args) < 2:
            sys.exit(2)
        repo_arg = Path(args[1])
    sys.exit(main(repo_arg))
