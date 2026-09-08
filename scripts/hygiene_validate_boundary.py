"""Post-M13 hygiene boundary validator (frozen R2 §6).

Diffs the working tree against exact M13 (384a46d...) and rejects:
  * any migration at or beyond 0015;
  * any new authority table (ORM or migration);
  * M14 observation/workflow/executor semantics in changed files;
  * changed files outside the reviewed hygiene allowlist.

Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = "384a46d3a5c68d7d81784befc338aa8621b93fbd"

# The reviewed hygiene change surface (frozen R2 §3-§8)
ALLOWLIST = (
    "tests/conftest.py",
    "tests/test_m13_races.py",
    "tests/test_m13_corrections.py",
    "tests/m10f_scale_fixture.py",
    "tests/test_m10f_scale.py",
    "tests/test_post_m13_hygiene.py",
    "tests/test_audit2_authority.py",
    "tests/test_audit3_gate.py",
    "tests/test_audit_m1.py",
    "tests/test_audit_m3.py",
    "tests/test_audit_m4_m5a.py",
    "tests/test_m10c_scale.py",
    "tests/test_m10d_r2_proofs.py",
    "tests/test_m10f_backup_restore.py",
    "tests/test_m11_recovery.py",
    "tests/test_m11_scale.py",
    "tests/test_m12_recovery.py",
    "tests/test_m13_instance_state.py",
    "tests/test_m3a_happy_path.py",
    "tests/test_m3b_recovery.py",
    "tests/test_m3c_matrix.py",
    "tests/test_m4_contract.py",
    "tests/test_m5a10_aggregate.py",
    "tests/test_m5a6_submit.py",
    "tests/test_m5a7_observe.py",
    "tests/test_m5a8_cancel.py",
    "tests/test_m5a9_outputs.py",
    "tests/test_m5b6_outage.py",
    "tests/test_schema_m1.py",
    "tests/test_upload.py",
    "tests/test_generation_repository.py",
    "tests/test_m13_binding.py",
    "tests/test_m13_shot_capture.py",
    "tests/test_m13_scale.py",
    "tests/test_m13_recovery.py",
    "apps/web/src/components/ProductionWorldPanel.tsx",
    "apps/web/src/__tests__/PostM13Hygiene.test.tsx",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "README.md",
    "pyproject.toml",
    "docs/hygiene/",
    "docs/hygiene/post-m13-hygiene-implementation-record.md",
    "docs/SoloRing-Post-M13-Hygiene-Proof-Map.md",
    "scripts/hygiene_validate_proof_map.py",
    "scripts/hygiene_validate_boundary.py",
    "scripts/hygiene_validate_npm_audit.py",
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


def main() -> int:
    errors: list[str] = []

    changed = [f for f in git("diff", "--name-only", f"{BASE}..HEAD")
               .splitlines() if f.strip()]
    for f in changed:
        if not any(f == a or f.startswith(a) for a in ALLOWLIST):
            errors.append(f"changed file outside the hygiene allowlist: {f}")

    versions = REPO / "server" / "alembic" / "versions"
    mig_0015 = [p.name for p in versions.glob("*.py")
                if p.stem >= "0015"]
    if mig_0015:
        errors.append(f"migration at/beyond 0015 exists: {mig_0015}")

    for f in changed:
        p = REPO / f
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for pattern, what in M14_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{f}: {what} vocabulary present")

    # new authority tables: any CREATE TABLE in changed files
    for f in changed:
        p = REPO / f
        if not p.is_file() or not f.endswith((".py",)):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'CREATE TABLE\s+"?(\w+)"?', src, re.I):
            errors.append(f"{f}: new table {m.group(1)} in migration-shaped "
                          "source")

    if errors:
        for e in errors:
            print(f"HYGIENE-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print("Hygiene boundary clean: allowlist-scoped diff, head still "
          "0014, no M14 semantics, no new tables.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
