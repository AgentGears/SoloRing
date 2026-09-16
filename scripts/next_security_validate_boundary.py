"""Next-security boundary validator (frozen R2 §17).

Diffs the working tree against the implementation boundary and rejects:
  * changed files outside the reviewed security/successor allowlist;
  * unauthorized Alembic changes;
  * M14 observation/workflow/executor semantics outside reviewed surfaces;
  * a Next major other than 15 in apps/web/package.json.

Squash-survival (merge-review correction 2026-09-09): the repository
integrates by SQUASH merge only, so the intermediate hygiene commit is
NOT permanently reachable from published main. Base selection is
dual-mode and deterministic:
  * PREDECESSOR mode — when the reviewed hygiene head 3adead5 is
    reachable, diff exactly 3adead5..HEAD against the strict security
    allowlist;
  * PUBLISHED mode — otherwise, diff published M13 384a46d..HEAD against
    the union of the security and hygiene allowlists and require the
    checked-in predecessor evidence.

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

ALLOWLIST = (
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/web/next-env.d.ts",
    "apps/web/src/app/projects/[id]/production/page.tsx",
    "apps/web/src/app/projects/[id]/world/page.tsx",
    "docs/security/",
    "docs/SoloRing-Next-Security-Proof-Map.md",
    "scripts/next_security_validate.py",
    "scripts/next_security_validate_proof_map.py",
    "scripts/next_security_validate_boundary.py",
    "scripts/next_security_smoke.py",
    "tests/test_post_m13_next_security.py",
    "tests/test_m7d_relations.py",
    "docs/hygiene/npm-audit-runtime-exceptions.json",
    "docs/SoloRing-Post-M13-Hygiene-Proof-Map.md",
    "docs/hygiene/post-m13-hygiene-implementation-record.md",
    "scripts/hygiene_validate_boundary.py",
    ".github/workflows/ci.yml",
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
    "tests/test_m14_ui.py",
    "tests/test_m14_scale.py",
    "tests/test_m14_gpu_gate.py",
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
    "tests/test_m10a_migrations.py",
    "tests/test_m11_migration.py",
    "tests/test_m12_migration.py",
    "tests/test_m13_migration.py",
    "tests/test_m5a10_migration_gate.py",
    "tests/test_m8a_visual.py",
    "tests/test_migration_m6b.py",
    "tests/test_post_m13_hygiene.py",
    "tests/test_m7c_capture.py",
    "tests/test_m9a_package.py",
    "tests/test_migration.py",
    "tests/test_migration_m1.py",
    "tests/test_migration_m6.py",
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
    # Post-M15 review remediation.
    "apps/web/src/components/ProductionWorldPanel.tsx",
    "server/soloring/executors/comfy/translate.py",
    "server/soloring/spatial/package3.py",
    "server/soloring/spatial/worker_inputs.py",
    "server/tests/test_post_m15_recovery_hardening.py",
    "tests/test_post_m15_worker_transport.py",
    "tests/test_m10f_adversarial_worker.py",
    # M16-P0 predecessor repairs.
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/__init__.py",
    "server/soloring/recovery/semantic_successors.py",
    "server/soloring/recovery/successor_semantics.py",
    "tests/test_m16_p0_repairs.py",
    # M16-A exact authority surface.
    "server/alembic/versions/0017_m16_intra_shot_consequences.py",
    "server/soloring/continuity/intra_shot_models.py",
    "server/soloring/continuity/intra_shot_canonical.py",
    "server/soloring/continuity/intra_shot_service.py",
    "server/soloring/continuity/intra_shot_resolver.py",
    "server/soloring/continuity/intra_shot_capture.py",
    "server/soloring/continuity/intra_shot_history.py",
    "server/soloring/api/schemas/intra_shot.py",
    "server/soloring/api/intra_shot.py",
    "server/soloring/api/main.py",
    "server/soloring/domain/shots.py",
    "server/soloring/api/schemas/shots.py",
    "server/soloring/api/shots.py",
    "tests/test_m16_migration.py",
    "tests/test_m16_grammar.py",
    "tests/test_m16_duration.py",
    "tests/test_m16_events.py",
    "tests/test_m16_identity.py",
    # M16-B exact resolver/readiness surface (reviewed successor slice).
    "tests/test_m16_start_state.py",
    "tests/test_m16_fold.py",
    "tests/test_m16_handoff.py",
    "tests/test_m16_readiness.py",
    "tests/test_m16_entity.py",
    "tests/test_m16_relation.py",
    "tests/test_m16_instance.py",
    "tests/test_m16_scale.py",
    "tests/test_m16_capture.py",
    "tests/test_m16_history_c.py",
    "tests/test_m16_generation_fence.py",
    "tests/test_m16_recovery_c.py",
    "tests/m16_seed_b.py",
    "tests/test_m3a_happy_path.py",
    "tests/test_working_state_comparison.py",
    # Reviewed M16-A recovery-boundary fixture correction: 0017 stays
    # fail-closed until M16-C, so these two M10F fixtures construct the
    # legitimate certified 0016 posture. Test fixtures, not M16 product
    # source — deliberately NOT in M16_A_BACKEND_PATHS.
    "tests/test_m10f_backup_restore.py",
    "tests/test_m10f_scale.py",
)

POST_M15_REMEDIATION_BACKEND_PATHS = frozenset({
    "server/soloring/executors/comfy/translate.py",
    "server/soloring/spatial/package3.py",
    "server/soloring/spatial/worker_inputs.py",
    "server/tests/test_post_m15_recovery_hardening.py",
    "server/soloring/api/continuity.py",
    "server/soloring/recovery/__init__.py",
    "server/soloring/recovery/semantic_successors.py",
    "server/soloring/recovery/successor_semantics.py",
})


def post_m15_remediation_backend(path: str) -> bool:
    return path in POST_M15_REMEDIATION_BACKEND_PATHS


M16_A_BACKEND_PATHS = frozenset({
    "server/alembic/versions/0017_m16_intra_shot_consequences.py",
    "server/soloring/continuity/intra_shot_models.py",
    "server/soloring/continuity/intra_shot_canonical.py",
    "server/soloring/continuity/intra_shot_service.py",
    "server/soloring/continuity/intra_shot_resolver.py",
    "server/soloring/continuity/intra_shot_capture.py",
    "server/soloring/continuity/intra_shot_history.py",
    # M16-B Shot-detail readiness integration seam (reviewed successor).
    "server/soloring/api/schemas/shots.py",
    "server/soloring/api/shots.py",
    "server/soloring/api/schemas/intra_shot.py",
    "server/soloring/api/intra_shot.py",
    "server/soloring/api/main.py",
    "server/soloring/domain/shots.py",
    "server/soloring/db/models.py",
    "server/soloring/errors.py",
})


def m16_a_backend(path: str) -> bool:
    return path in M16_A_BACKEND_PATHS


M15_OWNED_PREFIXES = (
    "docs/SoloRing-M15-",
    "scripts/m15_validate_",
    "tests/fixtures/m15/",
    "tests/test_m15",
    "server/soloring/composition/service.py",
    "tests/m15_seed.py",
    "server/soloring/compatibility/",
    "server/soloring/production_world/placement_consumer.py",
    "server/soloring/production_world/binding.py",
    "server/alembic/versions/0016_m15_revision_compatibility.py",
    "server/soloring/api/production.py",
    "server/soloring/api/schemas/production.py",
    "server/soloring/api/compositions.py",
    "server/soloring/composition/impacts.py",
)


def m15_owned(path: str) -> bool:
    return path.startswith(M15_OWNED_PREFIXES)


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


def git(*args: str, repo: Path = REPO) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def path_allowed(path: str, allowlist) -> bool:
    for entry in allowlist:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def _union_allowlist() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location(
        "hygiene_validate_boundary",
        REPO / "scripts" / "hygiene_validate_boundary.py",
    )
    hyg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hyg)
    return tuple(sorted(set(ALLOWLIST) | set(hyg.ALLOWLIST)))


def _commit_reachable(sha: str, repo: Path) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
         f"{sha}^{{commit}}"],
        capture_output=True,
    ).returncode == 0


def _evidence_errors(repo: Path = REPO) -> list[str]:
    evidence = repo / "docs" / "security" / "nsec-predecessor-evidence.json"
    if not evidence.is_file():
        return [
            "squash-shaped history without the checked-in predecessor "
            f"evidence: {evidence} missing"
        ]
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
            errors.append(
                f"predecessor evidence {key} = {ev.get(key)!r}, "
                f"expected {want!r}"
            )
    return errors


def select_base(repo: Path = REPO) -> tuple[str, str]:
    if _commit_reachable(PREDECESSOR, repo):
        return ("predecessor", PREDECESSOR)
    return ("published", PUBLISHED_M13)


def main(repo: Path = REPO) -> int:
    errors: list[str] = []
    mode, base = select_base(repo)
    allowlist = ALLOWLIST if mode == "predecessor" else _union_allowlist()
    if mode == "published":
        errors.extend(_evidence_errors(repo))

    changed = [
        f for f in git("diff", "--name-only", f"{base}..HEAD", repo=repo)
        .splitlines() if f.strip()
    ]
    for f in changed:
        if f.startswith("server/") and not (
            m14_owned(f)
            or m15_owned(f)
            or post_m15_remediation_backend(f)
            or m16_a_backend(f)
        ):
            errors.append(f"backend change outside the security slice: {f}")
        if (f.startswith("server/alembic/")
                and f not in (
                    "server/alembic/versions/0015_m14_world_observation_execution.py",
                    "server/alembic/versions/0016_m15_revision_compatibility.py",
                    "server/alembic/versions/0017_m16_intra_shot_consequences.py",
                )):
            errors.append(f"alembic change outside the security slice: {f}")
        if not path_allowed(f, allowlist):
            errors.append(
                f"changed file outside the {mode}-mode allowlist: {f}"
            )

    versions = repo / "server" / "alembic" / "versions"
    admitted_0015 = "0015_m14_world_observation_execution.py"
    admitted_0016 = "0016_m15_revision_compatibility.py"
    admitted_0017 = "0017_m16_intra_shot_consequences.py"
    mig_beyond = [
        p.name for p in versions.glob("*.py")
        if p.stem >= "0015" and p.name not in (
            admitted_0015, admitted_0016, admitted_0017)
    ]
    if mig_beyond:
        errors.append(
            "migration at/beyond 0015 beyond the frozen M14/M15/M16-A "
            f"migrations exists: {mig_beyond}"
        )

    pkg = json.loads(
        (repo / "apps" / "web" / "package.json").read_text(encoding="utf-8")
    )
    next_decl = (pkg.get("dependencies") or {}).get("next", "")
    major = str(next_decl).strip().lstrip("^~").split(".")[0]
    if next_decl and (major != "15" or next_decl.startswith(("^", "~"))):
        errors.append(
            f"next declaration {next_decl!r} violates the frozen contract "
            "(exact 15.x pin)"
        )

    for f in changed:
        p = repo / f
        if not p.is_file() or f.endswith((
            "next_security_validate_boundary.py",
            "hygiene_validate_boundary.py",
        )):
            continue
        if m14_owned(f) or post_m15_remediation_backend(f) or m16_a_backend(f):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        for pattern, what in M14_PATTERNS:
            if re.search(pattern, src, re.I):
                errors.append(f"{f}: {what} vocabulary present")

    if errors:
        for error in errors:
            print(f"NEXT-SECURITY-BOUNDARY INVALID: {error}", file=sys.stderr)
        return 1
    print(
        f"Next-security boundary clean (mode={mode}, base={base[:12]}…): "
        f"{'security-slice' if mode == 'predecessor' else 'post-M13 union'} "
        "allowlist scoped; M14 0015, M15 0016, and exact M16-A 0017 are "
        "the latest admitted migrations; Next major exactly 15"
        + ("; checked-in predecessor evidence exact."
           if mode == "published" else ".")
    )
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    repo_arg = REPO
    if args and args[0] == "--repo":
        if len(args) < 2:
            sys.exit(2)
        repo_arg = Path(args[1])
    sys.exit(main(repo_arg))
