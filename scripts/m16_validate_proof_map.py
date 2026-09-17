"""M16 proof-map validator (frozen R7 SS22/SS27).

Hard-codes EXACTLY the frozen 164-cell universe and family
counts (BASE 6 / PRE 6 / MIG 7 / GRAMMAR 10 / IDENTITY 6 /
DURATION 5 / START 4 / FOLD 8 / HANDOFF 9 / ENTITY 5 /
RELATION 5 / INSTANCE 6 / READY 7 / CAPTURE 8 / HIST 11 /
PROPOSAL 10 / ADOPT 13 / TAKE 5 / RACE 9 / RECOVERY 8 /
EXEC 5 / UI 6 / SCALE 5). The universe is NEVER discovered
from whatever tests happen to exist. Rejects: missing cell,
extra/unknown cell, duplicate cell, duplicate exact owner,
pending/TODO owner, owner path absent, PY owner not
collectable, FE owner marker absent, STRUCT owner function
absent.

Exit codes: 0 valid; 1 invalid; 2 usage error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FAMILY_COUNTS = {
    "ADOPT": 13,
    "BASE": 6,
    "CAPTURE": 8,
    "DURATION": 5,
    "ENTITY": 5,
    "EXEC": 5,
    "FOLD": 8,
    "GRAMMAR": 10,
    "HANDOFF": 9,
    "HIST": 11,
    "IDENTITY": 6,
    "INSTANCE": 6,
    "MIG": 7,
    "PRE": 6,
    "PROPOSAL": 10,
    "RACE": 9,
    "READY": 7,
    "RECOVERY": 8,
    "RELATION": 5,
    "SCALE": 5,
    "START": 4,
    "TAKE": 5,
    "UI": 6,
}

# cell -> owner (exactly the frozen SS22 table)
CELLS: dict[str, str] = {
    # ADOPT
    "M16:ADOPT:01": "PY tests/test_m16_adoption.py::test_adopt_01",
    "M16:ADOPT:02": "PY tests/test_m16_adoption.py::test_adopt_02",
    "M16:ADOPT:03": "PY tests/test_m16_adoption.py::test_adopt_03",
    "M16:ADOPT:04": "PY tests/test_m16_adoption.py::test_adopt_04",
    "M16:ADOPT:05": "PY tests/test_m16_adoption.py::test_adopt_05",
    "M16:ADOPT:06": "PY tests/test_m16_adoption.py::test_adopt_06",
    "M16:ADOPT:07": "PY tests/test_m16_adoption.py::test_adopt_07",
    "M16:ADOPT:08": "PY tests/test_m16_adoption.py::test_adopt_08",
    "M16:ADOPT:09": "PY tests/test_m16_adoption.py::test_adopt_09",
    "M16:ADOPT:10": "PY tests/test_m16_adoption.py::test_adopt_10",
    "M16:ADOPT:11": "PY tests/test_m16_adoption.py::test_adopt_11",
    "M16:ADOPT:21": "PY tests/test_m16_adoption.py::test_adopt_21",
    "M16:ADOPT:22": "PY tests/test_m16_adoption.py::test_adopt_22",
    # BASE
    "M16:BASE:01": "STRUCT scripts/m16_validate_baseline.py::test_base_01",
    "M16:BASE:02": "STRUCT scripts/m16_validate_baseline.py::test_base_02",
    "M16:BASE:03": "STRUCT scripts/m16_validate_baseline.py::test_base_03",
    "M16:BASE:04": "STRUCT scripts/m16_validate_baseline.py::test_base_04",
    "M16:BASE:05": "STRUCT scripts/m16_validate_baseline.py::test_base_05",
    "M16:BASE:06": "STRUCT scripts/m16_validate_baseline.py::test_base_06",
    # CAPTURE
    "M16:CAPTURE:01": "PY tests/test_m16_capture.py::test_capture_01",
    "M16:CAPTURE:02": "PY tests/test_m16_capture.py::test_capture_02",
    "M16:CAPTURE:03": "PY tests/test_m16_capture.py::test_capture_03",
    "M16:CAPTURE:04": "PY tests/test_m16_capture.py::test_capture_04",
    "M16:CAPTURE:05": "PY tests/test_m16_capture.py::test_capture_05",
    "M16:CAPTURE:06": "PY tests/test_m16_capture.py::test_capture_06",
    "M16:CAPTURE:07": "PY tests/test_m16_capture.py::test_capture_07",
    "M16:CAPTURE:08": "PY tests/test_m16_capture.py::test_capture_08",
    # DURATION
    "M16:DURATION:01": "PY tests/test_m16_duration.py::test_duration_01",
    "M16:DURATION:02": "PY tests/test_m16_duration.py::test_duration_02",
    "M16:DURATION:03": "PY tests/test_m16_duration.py::test_duration_03",
    "M16:DURATION:04": "PY tests/test_m16_duration.py::test_duration_04",
    "M16:DURATION:05": "PY tests/test_m16_duration.py::test_duration_05",
    # ENTITY
    "M16:ENTITY:01": "PY tests/test_m16_entity.py::test_entity_01",
    "M16:ENTITY:02": "PY tests/test_m16_entity.py::test_entity_02",
    "M16:ENTITY:03": "PY tests/test_m16_entity.py::test_entity_03",
    "M16:ENTITY:04": "PY tests/test_m16_entity.py::test_entity_04",
    "M16:ENTITY:05": "PY tests/test_m16_entity.py::test_entity_05",
    # EXEC
    "M16:EXEC:01": "PY tests/test_m16_generation_fence.py::test_exec_01",
    "M16:EXEC:02": "PY tests/test_m16_generation_fence.py::test_exec_02",
    "M16:EXEC:03": "PY tests/test_m16_generation_fence.py::test_exec_03",
    "M16:EXEC:04": "PY tests/test_m16_generation_fence.py::test_exec_04",
    "M16:EXEC:05": "PY tests/test_m16_generation_fence.py::test_exec_05",
    # FOLD
    "M16:FOLD:01": "PY tests/test_m16_fold.py::test_fold_01",
    "M16:FOLD:02": "PY tests/test_m16_fold.py::test_fold_02",
    "M16:FOLD:03": "PY tests/test_m16_fold.py::test_fold_03",
    "M16:FOLD:04": "PY tests/test_m16_fold.py::test_fold_04",
    "M16:FOLD:05": "PY tests/test_m16_fold.py::test_fold_05",
    "M16:FOLD:06": "PY tests/test_m16_fold.py::test_fold_06",
    "M16:FOLD:07": "PY tests/test_m16_fold.py::test_fold_07",
    "M16:FOLD:08": "PY tests/test_m16_fold.py::test_fold_08",
    # GRAMMAR
    "M16:GRAMMAR:01": "PY tests/test_m16_grammar.py::test_grammar_01",
    "M16:GRAMMAR:02": "PY tests/test_m16_grammar.py::test_grammar_02",
    "M16:GRAMMAR:03": "PY tests/test_m16_grammar.py::test_grammar_03",
    "M16:GRAMMAR:04": "PY tests/test_m16_grammar.py::test_grammar_04",
    "M16:GRAMMAR:05": "PY tests/test_m16_grammar.py::test_grammar_05",
    "M16:GRAMMAR:06": "PY tests/test_m16_grammar.py::test_grammar_06",
    "M16:GRAMMAR:07": "PY tests/test_m16_grammar.py::test_grammar_07",
    "M16:GRAMMAR:08": "PY tests/test_m16_grammar.py::test_grammar_08",
    "M16:GRAMMAR:09": "PY tests/test_m16_grammar.py::test_grammar_09",
    "M16:GRAMMAR:10": "PY tests/test_m16_grammar.py::test_grammar_10",
    # HANDOFF
    "M16:HANDOFF:01": "PY tests/test_m16_handoff.py::test_handoff_01",
    "M16:HANDOFF:02": "PY tests/test_m16_handoff.py::test_handoff_02",
    "M16:HANDOFF:03": "PY tests/test_m16_handoff.py::test_handoff_03",
    "M16:HANDOFF:04": "PY tests/test_m16_handoff.py::test_handoff_04",
    "M16:HANDOFF:05": "PY tests/test_m16_handoff.py::test_handoff_05",
    "M16:HANDOFF:06": "PY tests/test_m16_handoff.py::test_handoff_06",
    "M16:HANDOFF:07": "PY tests/test_m16_handoff.py::test_handoff_07",
    "M16:HANDOFF:08": "PY tests/test_m16_handoff.py::test_handoff_08",
    "M16:HANDOFF:09": "PY tests/test_m16_handoff.py::test_handoff_09",
    # HIST
    "M16:HIST:01": "PY tests/test_m16_history.py::test_hist_01",
    "M16:HIST:02": "PY tests/test_m16_history.py::test_hist_02",
    "M16:HIST:03": "PY tests/test_m16_history.py::test_hist_03",
    "M16:HIST:04": "PY tests/test_m16_history.py::test_hist_04",
    "M16:HIST:05": "PY tests/test_m16_history.py::test_hist_05",
    "M16:HIST:06": "PY tests/test_m16_history.py::test_hist_06",
    "M16:HIST:07": "PY tests/test_m16_history.py::test_hist_07",
    "M16:HIST:08": "PY tests/test_m16_history.py::test_hist_08",
    "M16:HIST:09": "PY tests/test_m16_history.py::test_hist_09",
    "M16:HIST:10": "PY tests/test_m16_history.py::test_hist_10",
    "M16:HIST:11": "PY tests/test_m16_history.py::test_hist_11",
    # IDENTITY
    "M16:IDENTITY:01": "PY tests/test_m16_identity.py::test_identity_01",
    "M16:IDENTITY:02": "PY tests/test_m16_identity.py::test_identity_02",
    "M16:IDENTITY:03": "PY tests/test_m16_identity.py::test_identity_03",
    "M16:IDENTITY:04": "PY tests/test_m16_identity.py::test_identity_04",
    "M16:IDENTITY:05": "PY tests/test_m16_identity.py::test_identity_05",
    "M16:IDENTITY:06": "PY tests/test_m16_identity.py::test_identity_06",
    # INSTANCE
    "M16:INSTANCE:01": "PY tests/test_m16_instance.py::test_instance_01",
    "M16:INSTANCE:02": "PY tests/test_m16_instance.py::test_instance_02",
    "M16:INSTANCE:03": "PY tests/test_m16_instance.py::test_instance_03",
    "M16:INSTANCE:04": "PY tests/test_m16_instance.py::test_instance_04",
    "M16:INSTANCE:05": "PY tests/test_m16_instance.py::test_instance_05",
    "M16:INSTANCE:06": "PY tests/test_m16_instance.py::test_instance_06",
    # MIG
    "M16:MIG:01": "PY tests/test_m16_migration.py::test_mig_01",
    "M16:MIG:02": "PY tests/test_m16_migration.py::test_mig_02",
    "M16:MIG:03": "PY tests/test_m16_migration.py::test_mig_03",
    "M16:MIG:04": "PY tests/test_m16_migration.py::test_mig_04",
    "M16:MIG:05": "PY tests/test_m16_migration.py::test_mig_05",
    "M16:MIG:06": "PY tests/test_m16_migration.py::test_mig_06",
    "M16:MIG:07": "PY tests/test_m16_migration.py::test_mig_07",
    # PRE
    "M16:PRE:01": "PY tests/test_m16_predecessor_repairs.py::test_pre_01",
    "M16:PRE:02": "PY tests/test_m16_predecessor_repairs.py::test_pre_02",
    "M16:PRE:03": "PY tests/test_m16_predecessor_repairs.py::test_pre_03",
    "M16:PRE:04": "PY tests/test_m16_predecessor_repairs.py::test_pre_04",
    "M16:PRE:05": "PY tests/test_m16_predecessor_repairs.py::test_pre_05",
    "M16:PRE:06": "PY tests/test_m16_predecessor_repairs.py::test_pre_06",
    # PROPOSAL
    "M16:PROPOSAL:01": "PY tests/test_m16_proposals.py::test_proposal_01",
    "M16:PROPOSAL:02": "PY tests/test_m16_proposals.py::test_proposal_02",
    "M16:PROPOSAL:03": "PY tests/test_m16_proposals.py::test_proposal_03",
    "M16:PROPOSAL:04": "PY tests/test_m16_proposals.py::test_proposal_04",
    "M16:PROPOSAL:05": "PY tests/test_m16_proposals.py::test_proposal_05",
    "M16:PROPOSAL:06": "PY tests/test_m16_proposals.py::test_proposal_06",
    "M16:PROPOSAL:07": "PY tests/test_m16_proposals.py::test_proposal_07",
    "M16:PROPOSAL:08": "PY tests/test_m16_proposals.py::test_proposal_08",
    "M16:PROPOSAL:09": "PY tests/test_m16_proposals.py::test_proposal_09",
    "M16:PROPOSAL:10": "PY tests/test_m16_proposals.py::test_proposal_10",
    # RACE
    "M16:RACE:01": "PY tests/test_m16_races.py::test_race_01",
    "M16:RACE:02": "PY tests/test_m16_races.py::test_race_02",
    "M16:RACE:03": "PY tests/test_m16_races.py::test_race_03",
    "M16:RACE:04": "PY tests/test_m16_races.py::test_race_04",
    "M16:RACE:05": "PY tests/test_m16_races.py::test_race_05",
    "M16:RACE:06": "PY tests/test_m16_races.py::test_race_06",
    "M16:RACE:07": "PY tests/test_m16_races.py::test_race_07",
    "M16:RACE:08": "PY tests/test_m16_races.py::test_race_08",
    "M16:RACE:09": "PY tests/test_m16_races.py::test_race_09",
    # READY
    "M16:READY:01": "PY tests/test_m16_readiness.py::test_ready_01",
    "M16:READY:02": "PY tests/test_m16_readiness.py::test_ready_02",
    "M16:READY:03": "PY tests/test_m16_readiness.py::test_ready_03",
    "M16:READY:04": "PY tests/test_m16_readiness.py::test_ready_04",
    "M16:READY:05": "PY tests/test_m16_readiness.py::test_ready_05",
    "M16:READY:06": "PY tests/test_m16_readiness.py::test_ready_06",
    "M16:READY:07": "PY tests/test_m16_readiness.py::test_ready_07",
    # RECOVERY
    "M16:RECOVERY:01": "PY tests/test_m16_recovery.py::test_recovery_01",
    "M16:RECOVERY:02": "PY tests/test_m16_recovery.py::test_recovery_02",
    "M16:RECOVERY:03": "PY tests/test_m16_recovery.py::test_recovery_03",
    "M16:RECOVERY:04": "PY tests/test_m16_recovery.py::test_recovery_04",
    "M16:RECOVERY:05": "PY tests/test_m16_recovery.py::test_recovery_05",
    "M16:RECOVERY:06": "PY tests/test_m16_recovery.py::test_recovery_06",
    "M16:RECOVERY:07": "PY tests/test_m16_recovery.py::test_recovery_07",
    "M16:RECOVERY:08": "PY tests/test_m16_recovery.py::test_recovery_08",
    # RELATION
    "M16:RELATION:01": "PY tests/test_m16_relation.py::test_relation_01",
    "M16:RELATION:02": "PY tests/test_m16_relation.py::test_relation_02",
    "M16:RELATION:03": "PY tests/test_m16_relation.py::test_relation_03",
    "M16:RELATION:04": "PY tests/test_m16_relation.py::test_relation_04",
    "M16:RELATION:05": "PY tests/test_m16_relation.py::test_relation_05",
    # SCALE
    "M16:SCALE:01": "PY tests/test_m16_scale.py::test_scale_01",
    "M16:SCALE:02": "PY tests/test_m16_scale.py::test_scale_02",
    "M16:SCALE:03": "PY tests/test_m16_scale.py::test_scale_03",
    "M16:SCALE:04": "PY tests/test_m16_scale.py::test_scale_04",
    "M16:SCALE:05": "PY tests/test_m16_scale.py::test_scale_05",
    # START
    "M16:START:01": "PY tests/test_m16_start_state.py::test_start_01",
    "M16:START:02": "PY tests/test_m16_start_state.py::test_start_02",
    "M16:START:03": "PY tests/test_m16_start_state.py::test_start_03",
    "M16:START:04": "PY tests/test_m16_start_state.py::test_start_04",
    # TAKE
    "M16:TAKE:01": "PY tests/test_m16_take_isolation.py::test_take_01",
    "M16:TAKE:02": "PY tests/test_m16_take_isolation.py::test_take_02",
    "M16:TAKE:03": "PY tests/test_m16_take_isolation.py::test_take_03",
    "M16:TAKE:04": "PY tests/test_m16_take_isolation.py::test_take_04",
    "M16:TAKE:05": "PY tests/test_m16_take_isolation.py::test_take_05",
    # UI
    "M16:UI:01": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:01",
    "M16:UI:02": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:02",
    "M16:UI:03": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:03",
    "M16:UI:04": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:04",
    "M16:UI:05": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:05",
    "M16:UI:06": "FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:06",
}


def fail(messages: list[str]) -> int:
    for m in messages:
        print(f"M16-PROOF-MAP INVALID: {m}", file=sys.stderr)
    return 1


def collected_pytest_nodes() -> set[str]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "tests"],
        cwd=REPO, capture_output=True, text=True,
    )
    return {
        line.strip() for line in out.stdout.splitlines()
        if "::" in line and not line.startswith(("=", "wrote"))
    }


def python_owner_resolves(owner: str, nodes: set[str]) -> bool:
    path, name = owner.split("::", 1)
    if not (REPO / path).is_file():
        return False
    base = name.split("[", 1)[0]
    return any(
        node == owner or node.startswith(f"{path}::{base}[")
        for node in nodes
    )


def fe_owner_resolves(owner: str) -> bool:
    # grammar: FE <file>#<marker>
    spec = owner[3:].strip()
    if "#" not in spec:
        return False
    path, marker = spec.split("#", 1)
    if not (REPO / path).is_file():
        return False
    return marker in (REPO / path).read_text(encoding="utf-8")


def struct_owner_resolves(owner: str) -> bool:
    # grammar: STRUCT <script>::<function>
    spec = owner[7:].strip()
    if "::" not in spec:
        return False
    path, func = spec.split("::", 1)
    if not (REPO / path).is_file():
        return False
    return f"def {func}(" in (REPO / path).read_text(encoding="utf-8")


def check(nodes: set[str]) -> list[str]:
    errors: list[str] = []
    total = 0
    owners_seen: dict[str, str] = {}
    per_family: dict[str, int] = {}
    for cell, owner in CELLS.items():
        total += 1
        fam = cell.split(":")[1]
        per_family[fam] = per_family.get(fam, 0) + 1
        low = owner.lower()
        if "pending" in low or "todo" in low:
            errors.append(f"{cell}: pending/TODO owner {owner!r}")
            continue
        if owner in owners_seen:
            errors.append(
                f"{cell}: duplicate exact owner also used by "
                f"{owners_seen[owner]}")
        owners_seen[owner] = cell
        if owner.startswith("PY "):
            path = owner[3:].split("::", 1)[0]
            if not (REPO / path).is_file():
                errors.append(f"{cell}: owner path absent {path!r}")
            elif not python_owner_resolves(owner[3:].strip(), nodes):
                errors.append(
                    f"{cell}: PY owner not collectable {owner!r}")
        elif owner.startswith("FE "):
            if not fe_owner_resolves(owner):
                errors.append(f"{cell}: FE owner marker absent {owner!r}")
        elif owner.startswith("STRUCT "):
            if not struct_owner_resolves(owner):
                errors.append(
                    f"{cell}: STRUCT owner function absent {owner!r}")
        else:
            errors.append(f"{cell}: unknown owner grammar {owner!r}")
    if total != 164:
        errors.append(f"universe is {total} cells, must be exactly 164")
    for fam, count in FAMILY_COUNTS.items():
        if per_family.get(fam, 0) != count:
            errors.append(
                f"family {fam} has {per_family.get(fam, 0)} cells, "
                f"must be {count}")
    unexpected = [f for f in per_family if f not in FAMILY_COUNTS]
    if unexpected:
        errors.append(f"unknown families: {sorted(unexpected)}")
    return errors


def main() -> int:
    nodes = collected_pytest_nodes()
    errors = check(nodes)
    if errors:
        return fail(errors)
    print(
        "M16 proof map valid: 164/164 cells, all PY owners collect, "
        "all FE markers present, all STRUCT functions exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
