"""Post-M13 hygiene boundary validator (frozen R2 §6).

Diffs the working tree against exact M13 (384a46d...) and rejects:
  * any migration at or beyond the explicitly admitted successor heads;
  * any new authority table outside an admitted milestone migration;
  * M14 observation/workflow/executor semantics outside reviewed successor surfaces;
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

# The reviewed hygiene change surface (frozen R2 §3-§8) plus explicitly
# authorized successor milestone surfaces.
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
    # Post-M13 Next-security successor slice (frozen R2 @ 4c3d1846).
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
    "tests/test_m7d_relations.py",
    # M14 implementation slices.
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
    # M15 implementation slices.
    "docs/SoloRing-M15-Proof-Map.md",
    "scripts/m15_validate_proof_map.py",
    "tests/fixtures/m15/",
    "tests/test_m15_baseline.py",
    "server/soloring/compatibility/",
    "server/soloring/composition/service.py",
    "server/soloring/composition/impacts.py",
    "server/soloring/production_world/placement_consumer.py",
    "server/soloring/production_world/binding.py",
    "server/alembic/versions/0016_m15_revision_compatibility.py",
    "server/soloring/api/production.py",
    "server/soloring/api/schemas/production.py",
    "tests/m15_seed.py",
    "tests/test_m15_migration.py",
    "tests/test_m15_canonical.py",
    "tests/test_m15_evaluator.py",
    "tests/test_m15_translation.py",
    "tests/test_m15_placement_seam_probe.py",
    "tests/test_m15a_smoke.py",
    "tests/test_m15_placement_shared_classifier.py",
    "server/soloring/compatibility/impact.py",
    "server/soloring/api/compositions.py",
    "tests/test_m15_impact.py",
    "tests/test_m15_tracking.py",
    "tests/test_m15_scale.py",
    "tests/test_m15_apply.py",
    "tests/test_m15_races.py",
    "tests/test_m15_history.py",
    "tests/test_m15_scope.py",
    "tests/test_m12_identity.py",
    "tests/test_m12_working.py",
    "tests/test_m12_history.py",
    "tests/test_m12_publication.py",
    "tests/test_m13_subjects.py",
    "tests/test_m15_recovery.py",
    "tests/test_m15_api.py",
    "apps/web/src/components/M15UpdateSummary.tsx",
    "apps/web/src/components/M15TrackingBadge.tsx",
    "apps/web/src/components/M15HistoryMessage.tsx",
    "apps/web/src/components/M15CompatibilitySection.tsx",
    "apps/web/src/__tests__/m15-update-summary.test.tsx",
    "apps/web/src/__tests__/m15-tracking.test.tsx",
    "apps/web/src/__tests__/m15-history-message.test.tsx",
    "apps/web/src/components/ProductionLibrary.tsx",
    "apps/web/src/components/WorldSetWorkspace.tsx",
    "apps/web/src/lib/api.client.ts",
    # Post-M15 reviewed successor repairs.
    "server/soloring/executors/comfy/translate.py",
    "server/soloring/spatial/package3.py",
    "server/soloring/spatial/worker_inputs.py",
    "server/tests/test_post_m15_recovery_hardening.py",
    "tests/test_post_m15_worker_transport.py",
    "tests/test_m10f_adversarial_worker.py",
    # M16-P0 predecessor repair surface (frozen M16 R6 PRE:01-06).
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/__init__.py",
    "server/soloring/recovery/semantic_successors.py",
    "server/soloring/recovery/successor_semantics.py",
    "tests/test_m16_p0_repairs.py",
    # M16-A migration + event-authoring foundation. Exact only: no M16-B+
    # resolver/capture/review/UI surface is admitted by this slice.
    "server/alembic/versions/0017_m16_intra_shot_consequences.py",
    "server/soloring/continuity/intra_shot_models.py",
    "server/soloring/continuity/intra_shot_canonical.py",
    "server/soloring/continuity/intra_shot_service.py",
    "server/soloring/api/schemas/intra_shot.py",
    "server/soloring/api/intra_shot.py",
    "server/soloring/api/main.py",
    "server/soloring/domain/shots.py",
    "tests/test_m16_migration.py",
    "tests/test_m16_grammar.py",
    "tests/test_m16_duration.py",
    "tests/test_m16_events.py",
    "tests/test_m16_identity.py",
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


M15_OWNED_PREFIXES = (
    "docs/SoloRing-M15-",
    "scripts/m15_validate_",
    "tests/fixtures/m15/",
    "tests/test_m15",
    "tests/m15_seed.py",
    "server/soloring/compatibility/",
    "server/soloring/production_world/placement_consumer.py",
    "server/soloring/production_world/binding.py",
    "server/alembic/versions/0016_m15_revision_compatibility.py",
)


def m15_owned(path: str) -> bool:
    return path.startswith(M15_OWNED_PREFIXES)


M16_OWNED_PREFIXES = (
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/__init__.py",
    "server/soloring/recovery/semantic_successors.py",
    "server/soloring/recovery/successor_semantics.py",
    "tests/test_m16_p0_repairs.py",
    "server/alembic/versions/0017_m16_intra_shot_consequences.py",
    "server/soloring/continuity/intra_shot_models.py",
    "server/soloring/continuity/intra_shot_canonical.py",
    "server/soloring/continuity/intra_shot_service.py",
    "server/soloring/api/schemas/intra_shot.py",
    "server/soloring/api/intra_shot.py",
    "server/soloring/api/main.py",
    "server/soloring/domain/shots.py",
    "tests/test_m16_migration.py",
    "tests/test_m16_grammar.py",
    "tests/test_m16_duration.py",
    "tests/test_m16_events.py",
    "tests/test_m16_identity.py",
)


def m16_owned(path: str) -> bool:
    return path.startswith(M16_OWNED_PREFIXES)


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
    entry requires EXACT equality."""
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
    admitted_0015 = "0015_m14_world_observation_execution.py"
    admitted_0016 = "0016_m15_revision_compatibility.py"
    admitted_0017 = "0017_m16_intra_shot_consequences.py"
    mig_beyond = [p.name for p in versions.glob("*.py")
                  if p.stem >= "0015" and p.name not in (
                      admitted_0015, admitted_0016, admitted_0017)]
    if mig_beyond:
        errors.append(f"migration at/beyond 0015 beyond the frozen M14/M15/"
                      f"M16-A migrations exists: {mig_beyond}")

    for f in changed:
        p = REPO / f
        if not p.is_file() or f.endswith(("hygiene_validate_boundary.py",
                                          "next_security_validate_"
                                          "boundary.py")):
            continue
        if m14_owned(f) or m15_owned(f) or m16_owned(f):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for pattern, what in M14_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{f}: {what} vocabulary present")

    # New authority tables are admitted only in their reviewed milestone
    # migration. The M16-A table set is exact and closed.
    admitted_m15_tables = {
        "production_compatibility_assessments",
        "production_compatibility_uses",
        "composition_occurrence_revision_tracking",
        "production_update_operations",
        "production_update_items",
    }
    admitted_m16_tables = {
        "shot_intra_shot_event_proposals",
        "shot_intra_shot_events",
        "shot_revision_intra_shot_specs",
        "shot_revision_intra_shot_events",
        "persistent_consequence_reviews",
    }
    for f in changed:
        if not f.startswith("server/alembic/versions/"):
            continue
        p = REPO / f
        if not p.is_file() or not f.endswith(".py"):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        names = set(re.findall(r'CREATE TABLE\s+"?(\w+)"?', src, re.I))
        names.update(re.findall(r'op\.create_table\(\s*["\'](\w+)["\']', src))
        for name in names:
            if f.endswith("0015_m14_world_observation_execution.py"):
                # 0015 was already frozen/published before this validator grew
                # Alembic op.create_table awareness; preserve that predecessor.
                continue
            if (f.endswith("0016_m15_revision_compatibility.py")
                    and name in admitted_m15_tables):
                continue
            if (f.endswith("0017_m16_intra_shot_consequences.py")
                    and name in admitted_m16_tables):
                continue
            errors.append(f"{f}: new table {name} in migration source")
        if f.endswith("0017_m16_intra_shot_consequences.py") and names != admitted_m16_tables:
            errors.append(
                "0017 M16-A authority table set mismatch: "
                f"got {sorted(names)}, expected {sorted(admitted_m16_tables)}"
            )

    if errors:
        for error in errors:
            print(f"HYGIENE-BOUNDARY INVALID: {error}", file=sys.stderr)
        return 1
    print(
        "Hygiene boundary clean: reviewed successor diff only; M14 0015, "
        "M15 0016, and exact M16-A 0017 are the latest admitted migrations."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
