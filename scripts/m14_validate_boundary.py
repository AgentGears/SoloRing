"""M14 boundary validator (frozen R2 §47).

Mechanically proves the M14 implementation stays inside the frozen expected
implementation classes while explicitly classifying reviewed successor
milestone surfaces. Exit codes: 0 clean; 1 violation.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = "20429b3bf2ead3ca6c1d2402d5028e500bd4f9e8"

ALLOWED_PATTERNS = [
    # post-M16 R3 evidence-only publication (frozen R3 §23): frozen
    # regression freeze set + external certifying harness + the closed
    # R3 specification record. Evidence material; no production code.
    r"^post-m16-r3-freeze/",
    r"^post-m16-integrated-r3-evidence/harness/",
    r"^SoloRing-Post-M16-Integrated-Sequence-Regression-R3-CLOSED"
    r"\.md$",
    # PR #26 review records (M17C-A first pass + second-review
    # reconciliation): reviewed evidence documents, no product code
    r"^SoloRing-PR26-First-Pass-Review-R1\.md$",
    r"^SoloRing-PR26-Reconciliation-and-Correction-Record\.md$",
    # M17C-C scope record + slice-1 surfaces
    r"^SoloRing-M17C-C-Scope-R0\.md$",
    r"^server/alembic/versions/0022_m17c_schema8_capture"
    r"\.py$",
    # FPR-M17CC-04: the closure-preimage successor
    r"^server/alembic/versions/0023_m17cc_capture_closure_preimage"
    r"\.py$",
    r"^tests/test_m17cc_migration\.py$",
    # M17C-C slice 2 (the coherent performance-plane read)
    r"^server/soloring/performance/m17cc_capture_read\.py$",
    r"^tests/test_m17cc_capture\.py$",
    r"^tests/m17cc_capture_helper\.py$",
    # M17C-C slice 3 (frozen-companion persistence + winner reuse)
    r"^tests/test_m17cc_persist\.py$",
    # M17C-C slice 4 (§12 historical inspection)
    r"^server/soloring/performance/m17cc_history\.py$",
    r"^tests/test_m17cc_history\.py$",
    # M17C-C slice 5 (§13.4-13.6 recovery verifier)
    r"^tests/test_m17cc_recovery\.py$",
    # M17C-C slice 6 (§1.7 backup/restore + downgrade closure)
    r"^tests/test_m17cc_roundtrip\.py$",
    # FPR-M17CC correction battery
    r"^tests/test_m17cc_fpr_corrections\.py$",
    # RR-M17CC correction battery
    r"^tests/test_m17cc_rr_corrections\.py$",
    # RR2-M17CC correction battery
    r"^tests/test_m17cc_rr2_corrections\.py$",
    # RR3-M17CC correction battery
    r"^tests/test_m17cc_rr3_corrections\.py$",
    # RR4-M17CC correction battery
    r"^tests/test_m17cc_rr4_corrections\.py$",
    # RR5-M17CC correction battery
    r"^tests/test_m17cc_rr5_corrections\.py$",
    # RR6-M17CC correction battery
    r"^tests/test_m17cc_rr6_corrections\.py$",
    # RR7-M17CC correction battery
    r"^tests/test_m17cc_rr7_corrections\.py$",
    # RR8-M17CC correction battery
    r"^tests/test_m17cc_rr8_corrections\.py$",
    # RR9-M17CC correction battery
    r"^tests/test_m17cc_rr9_corrections\.py$",
    # RR10-M17CC correction battery
    r"^tests/test_m17cc_rr10_corrections\.py$",
    # SR-M17CC second-review correction battery
    r"^tests/test_m17cc_sr_corrections\.py$",
    # RR12-M17CC correction battery
    r"^tests/test_m17cc_rr12_corrections\.py$",
    # RR13-M17CC correction battery
    r"^tests/test_m17cc_rr13_corrections\.py$",
    # ISR2-M17CC correction battery
    r"^tests/test_m17cc_isr2_corrections\.py$",
    # RR15-M17CC correction battery
    r"^tests/test_m17cc_rr15_corrections\.py$",
    # RR16-M17CC correction battery
    r"^tests/test_m17cc_rr16_corrections\.py$",
    # RR17-M17CC correction battery
    r"^tests/test_m17cc_rr17_corrections\.py$",
    # RR18-M17CC correction battery
    r"^tests/test_m17cc_rr18_corrections\.py$",
    # RR19-M17CC correction battery
    r"^tests/test_m17cc_rr19_corrections\.py$",
    # RR20-M17CC correction battery + the shared storage-domain bound
    r"^tests/test_m17cc_rr20_corrections\.py$",
    r"^server/soloring/domain/storage\.py$",
    # M17A implementation (frozen R5): the dialogue/vocal foundation
    # surface — performance package, migration, API, recovery
    # verifier, boundary validators, and the M17A tests.
    r"^server/soloring/performance/",
    r"^server/soloring/api/performance\.py$",
    r"^server/soloring/api/schemas/performance\.py$",
    r"^server/soloring/api/main\.py$",
    r"^server/soloring/db/models\.py$",
    r"^server/soloring/errors\.py$",
    r"^server/soloring/recovery/backup\.py$",
    # RR16-M17CC: the shared recovery-side outer-ShotRevision parser
    r"^server/soloring/recovery/outer_snapshot\.py$",
    r"^server/soloring/recovery/successor_semantics\.py$",
    r"^server/soloring/recovery/m17a_verifier\.py$",
    r"^server/alembic/versions/0018_m17a_dialogue_vocal_foundation"
    r"\.py$",
    r"^scripts/(hygiene|next_security|m14|m16)_validate_boundary\.py$",
    r"^tests/m17a_seed\.py$",
    r"^tests/test_m17a_[a-z_]+\.py$",
    # M17B reviewed successor surface (frozen R7)
        r"^server/soloring/recovery/m17b_verifier\.py$",
    r"^server/soloring/performance/profile\.py$",
    r"^server/soloring/performance/revision\.py$",
    r"^server/soloring/performance/retarget\.py$",
    r"^server/alembic/versions/0019_m17b_performance_revisions"
    r"\.py$",
    r"^tests/m17b_seed\.py$",
    r"^tests/test_m17b_[a-z_]+\.py$",
    r"^docs/SoloRing-M17B-Proof-Map\.md$",
    r"^scripts/m17b_validate_proof_map\.py$",
    r"^server/soloring/api/m17b_performance\.py$",
    r"^server/soloring/api/schemas/m17b_performance\.py$",
    # M17C-A (PR #26): frozen at c502b81 (B-F1 restored its exact
    # bytes); M17C-B (PR #26, B-F1): the successor working-mapping
    # migration — reviewed successor surface + successor-maintained
    # files swept for the head-advance
    r"^server/soloring/performance/m17c_[a-z_]+\.py$",
    r"^server/soloring/performance/m17cc_models\.py$",
    r"^server/soloring/api/m17c_performance\.py$",
    r"^server/soloring/api/schemas/m17c_performance\.py$",
    r"^server/soloring/recovery/m17c_verifier\.py$",
    r"^server/alembic/versions/0020_m17c_perf_capture_r2"
    r"\.py$",
    r"^server/alembic/versions/0021_m17c_shot_performance_mappings"
    r"\.py$",
    r"^tests/m17c_seed\.py$",
    r"^tests/test_m17c_[a-z0-9_]+\.py$",
    r"^tests/test_post_m13_next_security\.py$",
    r"^tests/test_m14_b5_increment3\.py$",
    r"^tests/test_m14_base_corpus\.py$",
    r"^tests/test_m15_baseline\.py$",
    r"^tests/test_m16_recovery\.py$",
    r"^scripts/m17c_validate_[a-z0-9_]+\.py$",

    r"^docs/SoloRing-M14-[^/]+\.md$",
    r"^scripts/m14_validate_[a-z0-9_]+\.py$",
    r"^tests/fixtures/m14/[^/]+$",
    r"^tests/test_m14[a-z0-9_]*\.py$",
    r"^tests/test_m11_scope\.py$",
    r"^tests/test_m12_boundary\.py$",
    r"^tests/test_m1[123]_recovery\.py$",
    r"^tests/test_m(10a_migrations|11_migration|12_migration|"
    r"13_migration|5a10_migration_gate|7c_capture|9a_package|"
    r"8a_visual|igration_m6b|igration_m6|igration_m1|igration)\.py$",
    r"^tests/test_m10e_package3_production\.py$",
    r"^tests/test_post_m13_hygiene\.py$",
    r"^scripts/(hygiene|next_security|m13)_validate_boundary\.py$",
    r"^server/soloring/observation/",
    r"^server/soloring/errors\.py$",
    r"^server/soloring/db/models\.py$",
    r"^server/soloring/generation/",
    r"^server/soloring/workflows/",
    r"^server/soloring/realization/",
    r"^server/soloring/spatial/",
    r"^server/soloring/spatial/production_package\.py$",
    r"^server/soloring/worker/",
    r"^server/soloring/m14/",
    r"^server/alembic/versions/0015_m14_world_observation_execution\.py$",
    r"^server/soloring/recovery/",
    r"^apps/web/src/.+",
    r"^server/soloring/api/(realization|generations)\.py$",
    r"^\.github/workflows/ci\.yml$",
    r"^\.gitattributes$",
    # M15 authorized successor surface.
    r"^docs/SoloRing-M15-[^/]+\.md$",
    r"^scripts/m15_validate_[a-z0-9_]+\.py$",
    r"^tests/fixtures/m15/[^/]+$",
    r"^tests/test_m15[a-z0-9_]*\.py$",
    r"^tests/m15_seed\.py$",
    r"^tests/test_m15_(impact|tracking|scale)\.py$",
    r"^server/soloring/compatibility/",
    r"^server/soloring/production_world/placement_consumer\.py$",
    r"^server/soloring/production_world/binding\.py$",
    r"^server/soloring/composition/impacts\.py$",
    r"^server/alembic/versions/0016_m15_revision_compatibility\.py$",
    r"^server/soloring/api/production\.py$",
    r"^server/soloring/api/compositions\.py$",
    r"^server/soloring/composition/service\.py$",
    r"^tests/test_m12_identity\.py$",
    r"^tests/test_m12_working\.py$",
    r"^tests/test_m12_history\.py$",
    r"^tests/test_m12_publication\.py$",
    r"^tests/test_m13_subjects\.py$",
    r"^tests/test_m15_(recovery|api)\.py$",
    r"^server/soloring/api/schemas/production\.py$",
    # Post-M15 review remediation.
    r"^server/soloring/executors/comfy/translate\.py$",
    r"^tests/test_post_m15_worker_transport\.py$",
    r"^server/tests/test_post_m15_recovery_hardening\.py$",
    r"^tests/test_m10f_adversarial_worker\.py$",
    # M16-P0 predecessor repairs.
    r"^server/soloring/api/continuity\.py$",
    r"^tests/test_m16_p0_repairs\.py$",
    # M16-A migration + event-authoring foundation. This list is deliberately
    # exact: it does not admit resolver/capture/review/UI successor slices.
    r"^server/alembic/versions/0017_m16_intra_shot_consequences\.py$",
    r"^server/soloring/continuity/intra_shot_(models|canonical|service|"
    r"resolver|capture|history|adoption)\.py$",
    r"^server/soloring/continuity/(snapshots|intra_shot_history|"
    r"intra_shot_capture)\.py$",
    r"^server/soloring/domain/revisions\.py$",
    r"^server/soloring/api/schemas/shots\.py$",
    r"^server/soloring/api/shots\.py$",
    r"^server/soloring/api/schemas/intra_shot\.py$",
    r"^server/soloring/api/intra_shot\.py$",
    r"^server/soloring/api/main\.py$",
    r"^server/soloring/domain/shots\.py$",
    r"^tests/test_m16_(migration|grammar|duration|events|identity|"
    r"start_state|fold|handoff|readiness|entity|relation|instance|scale|"
    r"capture|history|history_c|races|generation_fence|recovery"
    r"|recovery_proposals|recovery_coherence|recovery_domains|proposals|adoption|take_isolation|downstream)\.py$",
    r"^tests/m16_seed_b\.py$",
    r"^tests/test_m3a_happy_path\.py$",
    r"^tests/test_working_state_comparison\.py$",
    # M16-A recovery-boundary correction (review follow-up on 0a213a5):
    # 0017 stays fail-closed until M16-C, so the M10F backup/restore
    # template and scale-metrics fixture construct the legitimate
    # certified 0016 posture.
    r"^tests/test_m10f_backup_restore\.py$",
    r"^tests/test_m10f_scale\.py$",
    # M16-D R7 review-artifact placement: successor plan revision +
    # delta record committed solely for the reviewer's byte inspection
    # ahead of the R7 freeze. Documentation, not code.
    r"^SoloRing-M16-Intra-Shot-Persistent-Consequences-"
    r"Implementation-Plan-R7\.md$",
    r"^SoloRing-M16-R6-to-R7\.delta\.md$",
    # post-M16-closure publication refresh (separately authorized):
    # the README status refresh to M16/0017. Documentation only.
    r"^README\.md$",
    # M17B second-Codex round: the sqlalchemy <2.1 ceiling pin
    # (dependency-drift incident, CI run #161). Packaging metadata only.
    r"^pyproject\.toml$",
    # M16-E closure surface (reviewed successor slice): the frozen §22
    # owner rename of the P0 module, the §23 source-gate owners, and
    # the four M16 validators.
    r"^tests/test_m16_predecessor_repairs\.py$",
    r"^tests/test_m16_source_gates\.py$",
    r"^scripts/m16_validate_baseline\.py$",
    r"^scripts/m16_validate_proof_map\.py$",
    r"^scripts/m16_validate_boundary\.py$",
    r"^scripts/m16_validate_source_fit\.py$",
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
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def main() -> int:
    errors: list[str] = []
    for changed in git_changed_files():
        forbidden = next(
            (what for pat, what in FORBIDDEN_PATTERNS if re.search(pat, changed)),
            None,
        )
        if forbidden:
            errors.append(f"{changed}: {forbidden}")
            continue
        if not any(re.match(pattern, changed) for pattern in ALLOWED_PATTERNS):
            errors.append(
                f"{changed}: outside frozen M14 implementation classes "
                "and reviewed successor surfaces (R2 §47)"
            )
    if errors:
        for error in errors:
            print(f"M14-BOUNDARY INVALID: {error}", file=sys.stderr)
        return 1
    print(
        "M14 boundary clean: all changed paths remain inside frozen §47 "
        "classes or exact reviewed M15/M16 successor surfaces."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
