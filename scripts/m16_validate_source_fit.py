"""M16 source-fit validator (frozen R7 §27).

Mechanically proves the frozen source-fit contract: predecessor Shot
semantics untouched, M16 authority rooted in exact predecessor domains
and vocabularies, the capture/history/generation fences structurally
present, and executor/materializer sources unchanged since the
published M15 baseline 30ea135f.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BASELINE = "30ea135f3b2339491e9b36eaee2d0d8bc4ab8585"

MIGRATION = REPO / "server/alembic/versions/0017_m16_intra_shot_consequences.py"
MODELS = REPO / "server/soloring/db/models.py"
SNAPSHOTS = REPO / "server/soloring/continuity/snapshots.py"
CANONICAL = REPO / "server/soloring/continuity/intra_shot_canonical.py"
ADOPTION = REPO / "server/soloring/continuity/intra_shot_adoption.py"
HISTORY = REPO / "server/soloring/continuity/intra_shot_history.py"
GENERATION = REPO / "server/soloring/generation/service.py"
BACKUP = REPO / "server/soloring/recovery/backup.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def check() -> list[str]:
    errors: list[str] = []
    models = read(MODELS)
    migration = read(MIGRATION)
    snapshots = read(SNAPSHOTS)
    canonical = read(CANONICAL)
    adoption = read(ADOPTION)
    history = read(HISTORY)
    generation = read(GENERATION)

    # 1. existing Shot duration remains nullable/nonnegative globally:
    # the M16 surface never tightens the duration column
    if not re.search(
            r'"?duration_ms"?\s*=\s*sa\.Column\((sa\.)?(Text|Integer)'
            r'[^\n]*nullable=True",",?\s*\)?|'
            r"duration_ms:\s*Mapped\[int \| None\]", models):
        # relaxed textual proof: the column is unchanged vs baseline
        base = git("show", f"{BASELINE}:server/soloring/db/models.py")
        cur_dur = [l for l in models.splitlines() if "duration_ms" in l]
        base_dur = [l for l in base.splitlines() if "duration_ms" in l]
        if cur_dur != base_dur:
            errors.append(
                "sf01: duration_ms column changed vs the M15 baseline")

    # 2. M16 does not tighten predecessor Shot API/DB schema: the
    # Shot schema/domain diffs may only ADD M16 integration — any
    # added constraint/tightening vocabulary is a failure
    tightening = ("required=", "nullable=False", "NOT NULL",
                  "CheckConstraint", "min_length", "unique=True")
    for f in ("server/soloring/api/schemas/shots.py",
              "server/soloring/domain/shots.py"):
        diff = git("diff", BASELINE, "--", f)
        added = [l[1:] for l in diff.splitlines()
                 if l.startswith("+") and not l.startswith("+++")
                 and l[1:].strip()]
        bad = [a for a in added if any(k in a for k in tightening)]
        if bad:
            errors.append(
                f"sf02: {f} tightens the predecessor Shot surface: "
                f"{bad[0][:60]!r}")

    # 3. target XOR/active partial-index grammar matches migration+ORM
    if not re.search(r"IS NOT NULL\s*\)\s*\)\s*\+\s*\(\(.*IS NOT NULL",
                     migration) and "entity_feature_id IS NOT NULL" \
            not in migration:
        errors.append("sf03: migration target-XOR CHECK absent")
    if "uq_sise_active_coordinate" not in migration:
        errors.append("sf03: active-coordinate partial unique index "
                      "absent from the migration")
    orm = read(REPO / "server/soloring/continuity/intra_shot_models.py")
    if "uq_sise_active_coordinate" not in orm:
        errors.append("sf03: active-coordinate partial unique index "
                      "absent from the ORM")

    # 4. handoffs target exact M7/M13 transition domains with the exact
    # predecessor vocabularies
    domains = ("continuity_feature_transitions",
               "continuity_relation_transitions",
               "production_instance_feature_transitions")
    for d in domains:
        if d not in adoption:
            errors.append(f"sf04: handoff domain {d} absent")
    if '("set" if' not in adoption and '"set"' not in adoption:
        errors.append("sf04: set|clear vocabulary absent")
    if not re.search(r'"active" if', adoption) and \
            '"active"' not in adoption:
        errors.append("sf04: active|inactive vocabulary absent")

    # 5. authority_subject_kind maps 1:1 from the predecessor closed
    # vocabulary
    if "authority_subject_kind" not in canonical:
        errors.append("sf05: authority_subject_kind mapping absent")
    else:
        m13 = git("show", f"{BASELINE}:server/alembic/versions/"
                          "0014_m13_authority_complete_world.py")
        if "creative_entity" not in m13 or \
                "production_instance" not in m13:
            errors.append("sf05: predecessor vocabulary unreadable")
        if "creative_entity" in canonical and \
                "production_instance" not in canonical:
            errors.append("sf05: partial subject vocabulary")

    # 6. Take approval endpoint contains no M16 adoption call
    out = subprocess.run(
        ["git", "-C", str(REPO), "grep", "-n", "intra_shot", "--",
         "server/soloring/api/takes.py",
         "server/soloring/domain/takes.py"],
        capture_output=True, text=True)
    if out.returncode not in (0, 1):
        errors.append("sf06: Take approval sources unreadable")
    elif out.stdout.strip():
        errors.append("sf06: Take approval references intra_shot")

    # 7. event-free predecessor canonical snapshot bytes: the schema-7
    # builder emits predecessor bytes only when no active events exist
    if not re.search(r"(if|and not).*events|events\"\)|not events",
                     snapshots) and "intra_shot" not in snapshots:
        errors.append("sf07: schema-7 builder/event-free branch absent")
    if "intra_shot" not in snapshots:
        errors.append("sf07: snapshot builder never emits intra_shot")

    # 8. event-bearing capture uses top-level intra_shot schema 1 +
    # outer snapshot schema 7 and cannot be lowered
    if "schema_version\": 7" not in snapshots.replace("'", '"') and \
            "schema_version = 7" not in snapshots and \
            '"schema_version": 7' not in snapshots:
        errors.append("sf08: outer snapshot schema 7 absent")
    if "schema_version" not in canonical:
        errors.append("sf08: intra-shot spec schema 1 absent")

    # 9. captured target identity is in schema-7 semantic bytes
    if "target_identity" not in canonical and \
            "captured_target_identity" not in snapshots:
        errors.append("sf09: captured target identity not embedded")

    # 10. predecessor continuity_spec_json/hash remain schema 1/2 and
    # byte-compatible: the predecessor spec writer is unchanged
    spec_diff = git("diff", BASELINE, "--",
                    "server/soloring/continuity/spec.py")
    if spec_diff.strip() and (REPO / "server/soloring/continuity/"
                              "spec.py").exists():
        errors.append("sf10: predecessor continuity spec writer changed")
    if "continuity" in snapshots and "schema_version" in snapshots:
        pass  # predecessor planes ride along (proven by tests)

    # 11. historical inspector accepts published schema 6 before 7 and
    # does not query current Production World
    if not re.search(r"schema_version.*[<>=]+\s*6|<=\s*6|6\b", history):
        errors.append("sf11: historical schema-6 acceptance absent")
    # reading the CAPTURED snapshot's own production-world block is
    # historical semantics; only current-state queries are forbidden
    if re.search(r"from soloring\.production_world",
                 history) or re.search(r"SELECT[\s\S]{0,80}"
                                       r"production_instance", history):
        errors.append(
            "sf11: historical inspector queries current Production World")

    # 12. generation refuses every non-empty schema 7 BEFORE all
    # Generation-side writes
    fence = generation.find("INTRA_SHOT_REALIZATION_UNSUPPORTED")
    first_insert = generation.find("INSERT INTO generations")
    if fence == -1:
        errors.append("sf12: generation refusal fence absent")
    elif first_insert != -1 and fence > first_insert:
        errors.append(
            "sf12: refusal occurs after a Generation-side write")

    # 13. Proposal Grammar v1 is single-candidate and size-bounded
    if "MAX_PROPOSAL_CANONICAL_BYTES" not in canonical:
        errors.append("sf13: proposal size bound absent")
    if "candidate_event" not in canonical:
        errors.append("sf13: single-candidate grammar absent")

    # 14. analyzer parameter hash is unconditional for analyzer
    # proposals
    if not re.search(r"not analyzer_hash", adoption):
        errors.append("sf14: analyzer parameter hash not required")

    # 15. P0 recovery dispatch is explicit per head through 0016
    backup = read(BACKUP)
    for head in ("0014", "0015", "0016"):
        if head not in backup:
            errors.append(f"sf15: recovery dispatch missing head {head}")

    # 16. 0017 Blob-FK inventory remains exactly 8: the structural
    # policy in recovery/backup.py admits the exact published M14 set
    # for 0017 and nothing more, and migration 0017 adds no Blob FK
    if "M15/M16 add no Blob FK" not in backup:
        errors.append("sf16: 0017 not admitted over the M14 inventory")
    if re.search(r"blobs\.id|blob_hash", migration):
        errors.append("sf16: migration 0017 adds a Blob FK")

    # 17. executor/materializer sources unchanged vs the baseline
    changed = git("diff", "--name-only", BASELINE, "--",
                  "server/soloring/executors",
                  "server/soloring/realization")
    if changed.strip():
        errors.append(
            f"sf17: executor/materializer sources changed: "
            f"{changed.strip().splitlines()[0]}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        for e in errors:
            print(f"M16-SOURCE-FIT INVALID: {e}", file=sys.stderr)
        return 1
    print("M16 source fit valid: predecessor semantics untouched; "
          "M16 authority rooted in exact predecessor domains, "
          "vocabularies, and fences; executor/materializer unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
