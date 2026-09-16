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
    r"resolver|capture|history)\.py$",
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
    r"capture|history_c|generation_fence|recovery_c|recovery_c2)\.py$",
    r"^tests/m16_seed_b\.py$",
    r"^tests/test_m3a_happy_path\.py$",
    r"^tests/test_working_state_comparison\.py$",
    # M16-A recovery-boundary correction (review follow-up on 0a213a5):
    # 0017 stays fail-closed until M16-C, so the M10F backup/restore
    # template and scale-metrics fixture construct the legitimate
    # certified 0016 posture.
    r"^tests/test_m10f_backup_restore\.py$",
    r"^tests/test_m10f_scale\.py$",
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
