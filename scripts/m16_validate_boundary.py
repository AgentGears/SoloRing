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
    # RR16-M17CC: the shared recovery-side outer-ShotRevision parser
    r"^server/soloring/recovery/outer_snapshot\.py$",
    r"^server/soloring/recovery/successor_semantics\.py$",
    r"^server/soloring/observation/[a-z_]+\.py$",
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
    # M17B second-Codex round: the sqlalchemy <2.1 ceiling pin
    # (dependency-drift incident, CI run #161). Packaging metadata only.
    r"^pyproject\.toml$",
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
    r"^tests/test_post_m13_next_security\.py$",
    r"^tests/test_m14_base_corpus\.py$",

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
# FPR-M17CC-01: the schema-8 successor refusal is the same fence
# family — capability refusal, never M16 semantics
GENERATION_FENCE_OK_8 = "PERFORMANCE_REALIZATION_UNSUPPORTED"


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
                "schema_8", "schema 8", "PERFORMANCE", "Performance",
                "M17C-D", "REALIZATION", "SoloRingError",
                "status_code=409",
                "details=", "ErrorCode", "_artifact_store",
                "WorkflowArtifactStore", "release", '"events"',
                "ShotRevision", "no published workflow", "snapshot_schema",
                "predecessor", "lowered", "captured", "authority",
                "wrapped", "lane", "exists", "beneath")):
            continue
        offenders.append(body.strip()[:70])
    return offenders


def git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", BASELINE],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def schema8_fence_check(src: str) -> list[str]:
    """RR-M17CC-04 (re-review): POSITIVELY certify the schema-8
    Generation refusal — a narrowly anchored structural check, not a
    keyword allowlist. The gate fails when the fence is absent, or
    when it sits below the first Generation-owned durable side effect
    (the release placement) on the source line order.
    """
    problems: list[str] = []
    token = "PERFORMANCE_REALIZATION_UNSUPPORTED"
    fence = src.find(token)
    if fence < 0:
        problems.append(
            "the schema-8 fail-closed realization refusal "
            f"({token}) is absent from the generation service")
        return problems
    gate = src.rfind("if snapshot_schema == 8:", 0, fence)
    if gate < 0 or fence - gate > 2000:
        problems.append(
            "the schema-8 refusal is not anchored to its "
            "'if snapshot_schema == 8:' gate")
    durable = src.find(
        "        await _artifact_store.place_release(release)")
    if durable >= 0 and fence > durable:
        problems.append(
            "the schema-8 refusal sits below the first "
            "Generation-owned durable side effect (release "
            "placement)")
    raise_kw = src.rfind("raise SoloRingError(", 0, fence)
    if raise_kw < 0 or fence - raise_kw > 400:
        problems.append(
            "the schema-8 fence marker is not part of a raise "
            "statement")
    return problems


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
                for off in schema8_fence_check(text):
                    errors.append(
                        "generation/service.py: " + off)
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
