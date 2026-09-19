"""M16 boundary validator (frozen R7 §26/§27).

Fails any changed path outside the frozen M16 implementation surface
(diff against the published M15 baseline 30ea135f), with the two
predecessor-remediation exceptions the frozen plan authorizes —
P0-A (recovery head dispatch + M14/M15 semantic verification
correction, in recovery/) and P0-B (historical inspector acceptance of
published schema 6, in continuity/intra_shot_history.py) — classified
SEPARATELY rather than by widening predecessor allowlists broadly.

The generation-service file is admitted ONLY as the fail-closed
schema-7 refusal fence: every ADDED line in its diff must belong to
the fence vocabulary. Reviewed successor carves from the M16
correction rounds (predecessor-test era head-pins, the m10f 0016
fixtures, boundary-validator carve entries) are admitted by exact
reviewed class, never by wildcard.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BASELINE = "30ea135f3b2339491e9b36eaee2d0d8bc4ab8585"

# the frozen §26 expected source surface
M16_SURFACE = (
    r"^server/alembic/versions/0017_m16_intra_shot_consequences\.py$",
    r"^server/soloring/continuity/intra_shot_[a-z_]+\.py$",
    r"^server/soloring/continuity/snapshots\.py$",
    r"^server/soloring/production_world/[a-z_]+\.py$",
    r"^server/soloring/domain/revisions\.py$",
    r"^server/soloring/domain/shots\.py$",
    r"^server/soloring/generation/service\.py$",
    r"^server/soloring/api/intra_shot\.py$",
    r"^server/soloring/api/continuity\.py$",
    r"^server/soloring/api/main\.py$",
    r"^server/soloring/api/shots\.py$",
    r"^server/soloring/api/schemas/intra_shot\.py$",
    r"^server/soloring/api/schemas/shots\.py$",
    r"^server/soloring/recovery/backup\.py$",
    r"^server/soloring/recovery/m16_verifier\.py$",
    r"^server/soloring/db/models\.py$",
    r"^server/soloring/errors\.py$",
    r"^apps/web/src/(components|lib|app|__tests__)/",
    r"^tests/test_m16_[a-z0-9_]+\.py$",
    r"^tests/m16_seed_b\.py$",
    r"^tests/conftest\.py$",
    r"^scripts/m16_validate_(baseline|proof_map|boundary|source_fit)"
    r"\.py$",
    r"^\.github/workflows/ci\.yml$",
    # R7 review-artifact placement (documentation only)
    r"^SoloRing-M16-Intra-Shot-Persistent-Consequences-"
    r"Implementation-Plan-R7\.md$",
    r"^SoloRing-M16-R6-to-R7\.delta\.md$",
    # the M16-E closure authorized exec_08 repin (the isolated final
    # certification action): one pin constant + characterization note
    # in the M14 GPU-gate harness; no production code
    r"^tests/test_m14_gpu_gate\.py$",
    # post-closure publication refresh (separately authorized): the
    # README status refresh to M16/0017. Documentation only.
    r"^README\.md$",
    # post-M16 R3 evidence-only publication (frozen R3 §23): the frozen
    # regression freeze set (spec/oracles/reviews/lineage/correction +
    # manifest), the external certifying harness, and the closed R3
    # specification record. Evidence material; no production code.
    r"^post-m16-r3-freeze/",
    r"^post-m16-integrated-r3-evidence/harness/",
    r"^SoloRing-Post-M16-Integrated-Sequence-Regression-R3-CLOSED"
    r"\.md$",
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
    r"^server/soloring/recovery/m17a_verifier\.py$",
    r"^server/alembic/versions/0018_m17a_dialogue_vocal_foundation"
    r"\.py$",
    r"^tests/m17a_seed\.py$",
    r"^tests/test_m17a_[a-z_]+\.py$",
    # reviewed successor carves from the M16 correction rounds:
    # predecessor-test era head-pins/migration expectations, the m10f
    # 0016-posture fixtures, and boundary-validator carve entries
    r"^tests/test_m(3a_happy_path|5a10_migration_gate|7c_capture|"
    r"8a_visual|9a_package|10a_migrations|10f_backup_restore|"
    r"10f_scale|11_migration|11_recovery|12_migration|12_recovery|"
    r"13_recovery|14_b5_increment3|14_derived_storage|15_baseline|"
    r"15_migration|15_recovery)\.py$",
    r"^tests/test_(migration|migration_m1|migration_m6|migration_m6b|"
    r"post_m13_hygiene|working_state_comparison)\.py$",
    r"^scripts/(hygiene|m14|next_security|m15)_validate_"
    r"(baseline|boundary|source_fit|proof_map)\.py$",
)

# P0-A: recovery head dispatch + M14/M15 semantic verification repair
P0_A = (
    r"^server/soloring/recovery/(__init__|semantic_successors|"
    r"successor_semantics)\.py$",
    r"^server/soloring/compatibility/service\.py$",
)

# P0-B: historical inspector acceptance of published schema 6 lives in
# continuity/intra_shot_history.py, already inside the M16 surface —
# classified here for the record, admitted by name
P0_B = (
    r"^server/soloring/continuity/intra_shot_history\.py$",
)

FORBIDDEN_PATTERNS = [
    (r"^\.github/(?!workflows/ci\.yml$)",
     "repository/workflow settings beyond ci.yml"),
    (r"^apps/web/package(-lock)?\.json$", "frontend dependency manifest"),
    (r"^apps/web/next\.config\.[a-z]+$", "frontend framework config"),
    (r"^apps/web/tsconfig.*\.json$", "frontend TypeScript config"),
    (r"^server/soloring/executors/",
     "executor sources (frozen pins; repin unauthorized)"),
    (r"^server/soloring/materializers/",
     "materializer sources (frozen pins; repin unauthorized)"),
]

# the generation-service fence: ONLY the fail-closed refusal may add
# M16 behavior there — every ADDED line in its diff must belong to the
# schema-7 refusal fence vocabulary
GENERATION_FENCE_OK = "INTRA_SHOT_REALIZATION_UNSUPPORTED"


def generation_diff_is_fence_only() -> list[str]:
    out = subprocess.run(
        ["git", "diff", BASELINE, "--",
         "server/soloring/generation/service.py"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    offenders = []
    for line in out.stdout.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        if not body.strip() or body.lstrip().startswith("#"):
            # fence-explaining comments are part of the reviewed fence
            continue
        if any(k in body for k in (
                "INTRA_SHOT", "intra_shot", "schema_7", "schema 7",
                "REALIZATION", "SoloRingError", "status_code=409",
                "details=", "ErrorCode", "_artifact_store",
                "WorkflowArtifactStore", "release", '"events"',
                "ShotRevision", "no published workflow")):
            continue
        offenders.append(body.strip()[:70])
    return offenders


def git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", BASELINE],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def main() -> int:
    errors: list[str] = []
    p0a: list[str] = []
    p0b: list[str] = []
    for changed in git_changed_files():
        forbidden = next(
            (what for pat, what in FORBIDDEN_PATTERNS
             if re.search(pat, changed)), None)
        if forbidden:
            errors.append(f"{changed}: {forbidden}")
            continue
        if any(re.match(p, changed) for p in P0_B):
            p0b.append(changed)
            continue
        if any(re.match(p, changed) for p in M16_SURFACE):
            if changed == "server/soloring/generation/service.py":
                text = (REPO / changed).read_text(encoding="utf-8")
                if GENERATION_FENCE_OK not in text:
                    errors.append(
                        "generation/service.py: fail-closed schema-7 "
                        "fence absent")
                for off in generation_diff_is_fence_only():
                    errors.append(
                        "generation/service.py: added line outside the "
                        f"refusal fence: {off!r}")
            continue
        if any(re.match(p, changed) for p in P0_A):
            p0a.append(changed)
            continue
        errors.append(
            f"{changed}: outside the frozen M16 implementation surface "
            "(R7 §26)")
    if errors:
        for e in errors:
            print(f"M16-BOUNDARY INVALID: {e}", file=sys.stderr)
        return 1
    print(
        "M16 boundary valid: all changed paths inside the frozen "
        f"surface; P0-A classified separately {sorted(p0a)}; "
        f"P0-B classified separately {sorted(p0b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
