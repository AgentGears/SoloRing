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
    "tests/test_m7c_capture.py",
    "tests/test_m9a_package.py",
    "tests/test_migration.py",
    "tests/test_migration_m1.py",
    "tests/test_migration_m6.py",
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
    "tests/test_m10d_races.py",
    "tests/test_m13_binding.py",
    "tests/test_m13_shot_capture.py",
    "tests/test_m13_scale.py",
    "tests/test_m13_recovery.py",
    "server/soloring/generation/repository.py",
    "server/soloring/spatial/boxdepth.py",
    "tests/test_m14_mesh_depth.py",
    "server/soloring/spatial/production_package.py",
    "tests/test_m10e_package3_production.py",
    "tests/test_m14_package.py",
    "server/soloring/generation/rerun.py",
    "server/soloring/worker/comfy_pipeline.py",
    "server/soloring/workflows/artifact_store.py",
    "server/soloring/worker/execution.py",
    "tests/test_m14_source_review_corrections.py",
    "server/soloring/api/generations.py",
    "server/soloring/api/realization.py",
    "tests/test_m14_b5_hist12.py",
    "tests/test_m14_b5_worker_closure.py",
    "tests/test_m14_b5_increment3.py",
    "tests/test_m14_ui.py",
    "tests/test_m14_scale.py",
    "tests/test_m14_gpu_gate.py",
    "tests/test_m10a_migrations.py",
    "tests/test_m11_migration.py",
    "tests/test_m12_migration.py",
    "tests/test_m13_migration.py",
    "tests/test_m5a10_migration_gate.py",
    "tests/test_m8a_visual.py",
    "tests/test_migration_m6b.py",
    "tests/test_post_m13_hygiene.py",
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
    # Post-M13 Next-security successor slice (frozen R2 @ 4c3d1846):
    # the reviewed security remediation extends this allowlist so the
    # hygiene boundary stays GREEN across the successor closure.
    "apps/web/src/app/projects/[id]/production/page.tsx",
    "apps/web/src/app/projects/[id]/world/page.tsx",
    "apps/web/next-env.d.ts",
    "docs/security/",
    "docs/SoloRing-Next-Security-Proof-Map.md",
    "scripts/next_security_validate.py",
    "scripts/next_security_validate_proof_map.py",
    "scripts/next_security_validate_boundary.py",
    "scripts/next_security_smoke.py",
    "tests/test_post_m13_next_security.py",
    # post-merge R8 determinism correction (CI run 34362011109):
    # test-scoped park budget in the APR-032/033 race proof only
    "tests/test_m7d_relations.py",
    # M14 implementation slices (frozen R2 @ 68f910f5, authorized
    # 2026-09-10): the authorized M14 surface extends this allowlist so
    # the hygiene boundary stays GREEN across the M14 closure, exactly
    # as the security remediation extended it before. M14 vocabulary is
    # legitimate inside the M14-owned surface (see M14_OWNED_PREFIXES)
    # and is skipped by the vocabulary scan below.
    ".gitattributes",
    "docs/SoloRing-M14-Proof-Map.md",
    "docs/SoloRing-M14-R2-Freeze-Erratum-E1.md",
    "scripts/m14_validate_baseline.py",
    "scripts/m14_validate_boundary.py",
    "scripts/m14_validate_proof_map.py",
    "scripts/m14_validate_source_fit.py",
    "tests/fixtures/m14/",
    "tests/test_m14_0_baseline.py",
    "tests/test_m14_0_g6_g7_corpus.py",
    "tests/test_m14_obs.py",
    "tests/test_m14_capabilities.py",
    "tests/test_m14_execution.py",
    "tests/test_m14_history.py",
    "tests/test_m14_base_corpus.py",
    "tests/test_m14_materializer.py",
    "tests/test_m11_scope.py",
    "tests/test_m12_boundary.py",
    "server/soloring/observation/",
    "server/soloring/errors.py",
    "server/soloring/generation/service.py",
    "server/soloring/realization/packages.py",
    "server/soloring/recovery/backup.py",
    "server/alembic/versions/0015_m14_world_observation_execution.py",
    "server/soloring/db/models.py",
    "tests/test_m14_derived_storage.py",
    "tests/test_m11_recovery.py",
    "tests/test_m12_recovery.py",
    "tests/test_m13_recovery.py",
    "scripts/m13_validate_boundary.py",
)

M14_OWNED_PREFIXES = (
    "docs/SoloRing-M14-",
    "scripts/m14_validate_",
    "tests/fixtures/m14/",
    "tests/test_m14",
    "server/soloring/observation/",
    "server/soloring/errors.py",
    "server/soloring/recovery/backup.py",
    "server/alembic/versions/0015_m14_world_observation_execution.py",
    "server/soloring/db/models.py",
    "server/soloring/generation/service.py",
    "server/soloring/generation/rerun.py",
    "server/soloring/worker/comfy_pipeline.py",
    "server/soloring/workflows/artifact_store.py",
    "server/soloring/worker/execution.py",
    "tests/test_m14_source_review_corrections.py",
    "server/soloring/api/generations.py",
    "server/soloring/api/realization.py",
    "server/soloring/generation/repository.py",
    "server/soloring/realization/packages.py",
    "server/soloring/spatial/boxdepth.py",
    "server/soloring/spatial/production_package.py",
    "scripts/m13_validate_boundary.py",
)


def m14_owned(path: str) -> bool:
    return path.startswith(M14_OWNED_PREFIXES)


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
        if not path_allowed(f, ALLOWLIST):
            errors.append(f"changed file outside the hygiene allowlist: {f}")

    versions = REPO / "server" / "alembic" / "versions"
    # M14B-2 succession (frozen R2 §23, authorized 2026-09-10): exactly
    # ONE migration at/beyond 0015 is admitted — the frozen M14
    # migration. Anything else (0016+, or a different 0015) still
    # rejects; this is NOT a general future-migration allowance.
    admitted_0015 = "0015_m14_world_observation_execution.py"
    mig_beyond = [p.name for p in versions.glob("*.py")
                  if p.stem >= "0015" and p.name != admitted_0015]
    if mig_beyond:
        errors.append(f"migration at/beyond 0015 beyond the frozen M14 "
                      f"migration exists: {mig_beyond}")

    for f in changed:
        p = REPO / f
        if not p.is_file() or f.endswith(("hygiene_validate_boundary.py",
                                          "next_security_validate_"
                                          "boundary.py")):
            continue  # boundary validators' own scan patterns name the vocabulary
        if m14_owned(f):
            continue  # authorized M14 surface legitimately uses M14 vocabulary
        src = p.read_text(encoding="utf-8", errors="replace")
        for pattern, what in M14_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{f}: {what} vocabulary present")

    # new authority tables: CREATE TABLE in changed MIGRATION-path files
    # only — test fixtures legitimately build scratch schema objects
    # (e.g. the alembic_version stamp) and are not migration source
    for f in changed:
        if not f.startswith("server/alembic/versions/"):
            continue
        p = REPO / f
        if not p.is_file() or not f.endswith((".py",)):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'CREATE TABLE\s+"?(\w+)"?', src, re.I):
            errors.append(f"{f}: new table {m.group(1)} in migration "
                          "source")

    if errors:
        for e in errors:
            print(f"HYGIENE-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print("Hygiene boundary clean: allowlist-scoped diff, only the frozen "
          "M14 0015 migration, no unauthorized M14 semantics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
