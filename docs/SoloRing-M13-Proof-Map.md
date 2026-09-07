# SoloRing M13 Proof Map

Frozen R3 §30: the machine-checkable M13 proof inventory (115 cells).
Validated by `python scripts/m13_validate_proof_map.py` (Backend CI, before tests).

## M13-SUBJECT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-SUBJECT:01` | TEST | `tests/test_m13_subjects.py::test_m13_subject_01` | Existing occurrence UUID is the ProductionInstance subject id. |
| `M13-SUBJECT:02` | TEST | `tests/test_m13_subjects.py::test_m13_subject_02` | CreativeEntity subject creates no duplicate PI subject. |
| `M13-SUBJECT:03` | TEST | `tests/test_m13_subjects.py::test_m13_subject_03` | Direct ProductionRevision occurrence promotion succeeds. |
| `M13-SUBJECT:04` | TEST | `tests/test_m13_subjects.py::test_m13_subject_04` | Nested CompositionRevision occurrence promotion rejects. |
| `M13-SUBJECT:05` | TEST | `tests/test_m13_subjects.py::test_m13_subject_05` | Cross-Project CreativeEntity rejects. |
| `M13-SUBJECT:06` | TEST | `tests/test_m13_subjects.py::test_m13_subject_06` | Active duplicate claim rejects; terminated claim releases the slot. |
| `M13-SUBJECT:07` | TEST | `tests/test_m13_subjects.py::test_m13_subject_07` | Rebinding/reclassification rejects. |
| `M13-SUBJECT:08` | TEST | `tests/test_m13_subjects.py::test_m13_subject_08` | Terminated occurrence cannot be newly adopted. |
| `M13-SUBJECT:09` | TEST | `tests/test_m13_instance_state.py::test_m13_state_01` | CreativeEntity-adopted occurrence rejects PI Feature/Track authoring (owner M13-STATE:01). |
| `M13-SUBJECT:10` | TEST | `tests/test_m13_subjects.py::test_m13_subject_10` | Adoption survives same-occurrence source substitution; nested-source exclusion is structural (M13-BIND:02). |
| `M13-SUBJECT:11` | TEST | `tests/test_m13_subjects.py::test_m13_subject_11` | mint/replace/split/merge/fork targets begin COMPOSITION-LOCAL, no implicit copy. |

## M13-INTERP

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-INTERP:01` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_01` | Canonical schema-1 golden bytes/hash. |
| `M13-INTERP:02` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_02` | M10 basis/unit/rotation constants are server-owned. |
| `M13-INTERP:03` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_03` | Integral/JS-safe transform grammar. |
| `M13-INTERP:04` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_04` | +180deg canonicalizes to -180deg; stored +180deg is corruption. |
| `M13-INTERP:05` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_05` | Identical create converges. |
| `M13-INTERP:06` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_06` | Conflicting second create rejects. |
| `M13-INTERP:07` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_07` | M11 ProductionRevision bytes remain unchanged. |
| `M13-INTERP:08` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_08` | Stored JSON/hash/projection corruption fails closed. |
| `M13-INTERP:09` | TEST | `tests/test_m13_interpretation.py::test_m13_interp_09` | Provenance equals exact M11 stored parents; unclosed rejects. |

## M13-STATE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-STATE:01` | TEST | `tests/test_m13_instance_state.py::test_m13_state_01` | PI Feature requires PI subject adoption (incl. SUBJECT:09 CE rejection). |
| `M13-STATE:02` | TEST | `tests/test_m13_instance_state.py::test_m13_state_02` | Value grammar equals M7 shared semantics. |
| `M13-STATE:03` | TEST | `tests/test_m13_instance_state.py::test_m13_state_03` | Random-access winner direct at target boundary. |
| `M13-STATE:04` | TEST | `tests/test_m13_instance_state.py::test_m13_state_04` | start/end inclusion exact. |
| `M13-STATE:05` | TEST | `tests/test_m13_instance_state.py::test_m13_state_05` | clear means canonical absence. |
| `M13-STATE:06` | TEST | `tests/test_m13_instance_state.py::test_m13_state_06` | Ambiguous winner is invariant corruption. |
| `M13-STATE:07` | TEST | `tests/test_m13_instance_state.py::test_m13_state_07` | Stored value corruption fails closed. |
| `M13-STATE:08` | TEST | `tests/test_m13_instance_state.py::test_m13_state_08` | Entity-vs-PI shared-subset equivalence. |

## M13-SPACE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-SPACE:01` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_01` | PI Track requires PI subject adoption. |
| `M13-SPACE:02` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_02` | Same-Project world required. |
| `M13-SPACE:03` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_03` | One active track per (world, occurrence). |
| `M13-SPACE:04` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_04` | set/clear grammar exact. |
| `M13-SPACE:05` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_05` | No interpolation/default-origin authority. |
| `M13-SPACE:06` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_06` | required means effective non-NULL transform at target Shot. |
| `M13-SPACE:07` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_07` | Ambiguous/corrupt staging fails closed. |
| `M13-SPACE:08` | TEST | `tests/test_m13_instance_spatial.py::test_m13_space_08` | EntityTrack-vs-PITrack shared-subset equivalence. |

## M13-BIND

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-BIND:01` | TEST | `tests/test_m13_binding.py::test_m13_bind_01` | Exact C/W verified and same Project. |
| `M13-BIND:02` | TEST | `tests/test_m13_binding.py::test_m13_bind_02` | Subject list is the complete server-derived set (incl. structural nested-source exclusion). |
| `M13-BIND:03` | TEST | `tests/test_m13_binding.py::test_m13_bind_03` | Entry list is the complete server-derived A4 subset. |
| `M13-BIND:04` | TEST | `tests/test_m13_binding.py::test_m13_bind_04` | Zero A4 target => composition-owned/no entry. |
| `M13-BIND:05` | TEST | `tests/test_m13_binding.py::test_m13_bind_05` | One A4 target => one entry. |
| `M13-BIND:06` | TEST | `tests/test_m13_binding.py::test_m13_bind_06` | Duplicate A4 target => conflict. |
| `M13-BIND:07` | TEST | `tests/test_m13_binding.py::test_m13_bind_07` | Non-identity Composition transform blocks authority-bound entry. |
| `M13-BIND:08` | TEST | `tests/test_m13_binding.py::test_m13_bind_08` | Missing spatial interpretation blocks authority-bound entry. |
| `M13-BIND:09` | TEST | `tests/test_m13_binding.py::test_m13_bind_09` | Canonical binding golden bytes/hash/order. |
| `M13-BIND:10` | TEST | `tests/test_m13_binding.py::test_m13_bind_10` | Client cannot omit/add/substitute entries. |
| `M13-BIND:11` | TEST | `tests/test_m13_binding.py::test_m13_bind_11` | Existing winner full parent/child validation. |
| `M13-BIND:12` | TEST | `tests/test_m13_binding.py::test_m13_bind_12` | Identical publication converges on one identity. |
| `M13-BIND:13` | TEST | `tests/test_m13_binding.py::test_m13_bind_13` | Freeze-versus-authority-change conflict for PI and Entity A4 targets. |
| `M13-BIND:14` | TEST | `tests/test_m13_binding.py::test_m13_bind_14` | Historical binding reader ignores current mapping changes. |
| `M13-BIND:15` | TEST | `tests/test_m13_binding.py::test_m13_bind_15` | Adoption absent from the exact bound revision is excluded. |
| `M13-BIND:16` | TEST | `tests/test_m13_binding.py::test_m13_bind_16` | Zero-subject binding is legal and canonical. |
| `M13-BIND:17` | TEST | `tests/test_m13_binding.py::test_m13_bind_17` | CreativeEntity A4 classification reuses exact M10 authority semantics. |

## M13-IMPACT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-IMPACT:01` | TEST | `tests/test_m13_impact.py::test_m13_impact_01` | FK inventory includes the exact M13 occurrence consumers. |
| `M13-IMPACT:02` | TEST | `tests/test_m13_impact.py::test_m13_impact_02` | Active PI Feature blocks termination. |
| `M13-IMPACT:03` | TEST | `tests/test_m13_impact.py::test_m13_impact_03` | Active PI Track blocks termination; fork never blocked by live state. |
| `M13-IMPACT:04` | TEST | `tests/test_m13_impact.py::test_m13_impact_04` | Current Shot selection through binding blocks termination. |
| `M13-IMPACT:05` | TEST | `tests/test_m13_impact.py::test_m13_impact_05` | Historical binding/Shot rows do not block. |
| `M13-IMPACT:06` | TEST | `tests/test_m13_impact.py::test_m13_impact_06` | Blocker-set change forces a fresh preview (stale_impact under fence). |
| `M13-IMPACT:07` | TEST | `tests/test_m13_impact.py::test_m13_impact_07` | Fork remains legal; target receives no copied M13 authority. |
| `M13-IMPACT:08` | TEST | `tests/test_m13_impact.py::test_m13_impact_08` | No new selection against a terminated bound subject. |

## M13-SHOT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-SHOT:01` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_01` | No selection => exact lower behavior; schemas 1-5 unchanged. |
| `M13-SHOT:02` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_02` | Exact selected binding loads/validates. |
| `M13-SHOT:03` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_03` | Stale binding blocks current capture. |
| `M13-SHOT:04` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_04` | M10 spatial context absent blocks. |
| `M13-SHOT:05` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_05` | M10 exact W revision mismatch blocks. |
| `M13-SHOT:06` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_06` | Every CreativeEntity subject requires an explicit semantic dependency. |
| `M13-SHOT:07` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_07` | PI state resolved on the same coherent read. |
| `M13-SHOT:08` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_08` | PI staging resolved on the same coherent read. |
| `M13-SHOT:09` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_09` | Schema-6 canonical golden bytes/hash. |
| `M13-SHOT:10` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_10` | Schemas 1-5 golden bytes/hashes unchanged. |
| `M13-SHOT:11` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_11` | M13 pack without M10 spatial pack is an invariant failure. |
| `M13-SHOT:12` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_12` | Working hash and capture use the same resolver/builder. |
| `M13-SHOT:13` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_13` | M7/M8/M10/M13 share one explicit database snapshot/connection. |
| `M13-SHOT:14` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_14` | Selection/current GET exposes deterministic stale-binding status. |
| `M13-SHOT:15` | TEST | `tests/test_m13_shot_capture.py::test_m13_shot_15` | Selected zero-subject binding produces legal non-null schema 6. |

## M13-HISTORY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-HISTORY:01` | TEST | `tests/test_m13_history.py::test_m13_history_01` | Schema-6 parent/child projection exact incl. position == pack index. |
| `M13-HISTORY:02` | TEST | `tests/test_m13_history.py::test_m13_history_02` | Existing schema-6 winner reuse validates all M13 children. |
| `M13-HISTORY:03` | TEST | `tests/test_m13_history.py::test_m13_history_03` | Missing immutable binding fails closed. |
| `M13-HISTORY:04` | TEST | `tests/test_m13_history.py::test_m13_history_04` | Missing ProductionRevision closure fails closed. |
| `M13-HISTORY:05` | TEST | `tests/test_m13_history.py::test_m13_history_05` | Missing/corrupt C or W revision fails closed. |
| `M13-HISTORY:06` | TEST | `tests/test_m13_history.py::test_m13_history_06` | Current Shot selection unavailable; historical read still succeeds. |
| `M13-HISTORY:07` | TEST | `tests/test_m13_history.py::test_m13_history_07` | Current PI feature tables unavailable; historical read still succeeds. |
| `M13-HISTORY:08` | TEST | `tests/test_m13_history.py::test_m13_history_08` | Current PI track tables unavailable; historical read still succeeds. |
| `M13-HISTORY:09` | TEST | `tests/test_m13_history.py::test_m13_history_09` | Exact Rerun current-M13 query spy clean (both halves). |
| `M13-HISTORY:10` | TEST | `tests/test_m13_history.py::test_m13_history_10` | Missing/corrupt pinned spatial interpretation fails closed. |

## M13-MIG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-MIG:01` | TEST | `tests/test_m13_migration.py::test_m13_mig_01` | Exact 0013->0014 upgrade + exact 13-table inventory. |
| `M13-MIG:02` | TEST | `tests/test_m13_migration.py::test_m13_mig_02` | Empty 0014->0013 downgrade. |
| `M13-MIG:03` | TEST | `tests/test_m13_migration.py::test_m13_mig_03` | Any M13 state refuses downgrade, incl. bare adoption. |
| `M13-MIG:04` | TEST | `tests/test_m13_migration.py::test_m13_mig_04` | ORM/migration parity exact. |

## M13-RECOVERY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-RECOVERY:01` | TEST | `tests/test_m13_recovery.py::test_m13_recovery_01` | Supported-head dispatch 0011/0012/0013/0014. |
| `M13-RECOVERY:02` | TEST | `tests/test_m13_recovery.py::test_m13_recovery_02` | Older-head restore invents zero M13 state (_prove_no_m13_state; suites in M11/M12 recovery). |
| `M13-RECOVERY:03` | TEST | `tests/test_m13_recovery.py::test_m13_recovery_03` | 0014 semantic verifier rejects corrupted binding/history. |
| `M13-RECOVERY:04` | TEST | `tests/test_m13_recovery.py::test_m13_recovery_04` | 0014 Blob-FK inventory remains exactly seven paths. |
| `M13-RECOVERY:05` | TEST | `tests/test_m13_recovery.py::test_m13_recovery_05` | Integrity-valid stale binding verifies after pinned target soft-deletion. |

## M13-RACE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-RACE:01` | TEST | `tests/test_m13_races.py::test_m13_race_01` | R1 identical interpretation create converges / different rejects. |
| `M13-RACE:02` | TEST | `tests/test_m13_races.py::test_m13_race_02` | R2 adoption vs termination: exactly one legal history. |
| `M13-RACE:03` | TEST | `tests/test_m13_races.py::test_m13_race_03` | R3 concurrent same-CE adoption: at most one commits. |
| `M13-RACE:04` | TEST | `tests/test_m13_races.py::test_m13_race_04` | R4 PI feature creation vs termination symmetric. |
| `M13-RACE:05` | TEST | `tests/test_m13_races.py::test_m13_race_05` | R5 PI track creation vs termination symmetric. |
| `M13-RACE:06` | TEST | `tests/test_m13_races.py::test_m13_race_06` | R6 binding freeze vs new subject adoption conflict. |
| `M13-RACE:07` | TEST | `tests/test_m13_races.py::test_m13_race_07` | R7 binding freeze vs PI/CE A4 target change conflict. |
| `M13-RACE:08` | TEST | `tests/test_m13_races.py::test_m13_race_08` | R8 binding freeze vs interpretation creation conflict. |
| `M13-RACE:09` | TEST | `tests/test_m13_races.py::test_m13_race_09` | R9 identical binding publication converges. |
| `M13-RACE:10` | TEST | `tests/test_m13_races.py::test_m13_race_10` | R10 competing selection CAS cannot both win. |
| `M13-RACE:11` | TEST | `tests/test_m13_races.py::test_m13_race_11` | R11 selection vs termination cannot create illegal state. |
| `M13-RACE:12` | TEST | `tests/test_m13_races.py::test_m13_race_12` | R12 selection change vs capture: whole BEFORE/AFTER. |
| `M13-RACE:13` | TEST | `tests/test_m13_races.py::test_m13_race_13` | R13 M10 approval change vs capture: no W-A/W-B mix. |
| `M13-RACE:14` | TEST | `tests/test_m13_races.py::test_m13_race_14` | R14 PI state change vs capture: whole BEFORE/AFTER. |
| `M13-RACE:15` | TEST | `tests/test_m13_races.py::test_m13_race_15` | R15 PI spatial change vs capture: whole BEFORE/AFTER. |
| `M13-RACE:16` | TEST | `tests/test_m13_races.py::test_m13_race_16` | R16 identical schema-6 captures converge via snapshot identity. |

## M13-SCALE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-SCALE:01` | TEST | `tests/test_m13_scale.py::test_m13_scale_01` | Binding query count small==representative incl. in-fence rederive. |
| `M13-SCALE:02` | TEST | `tests/test_m13_scale.py::test_m13_scale_02` | Shot resolver query count small==representative incl. staleness. |
| `M13-SCALE:03` | TEST | `tests/test_m13_scale.py::test_m13_scale_03` | Schema-6 rows/bytes + binding duplication recorded, no latency claim. |

## M13-BOUNDARY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M13-BOUNDARY:01` | TEST | `tests/test_m13_boundary.py::test_m13_boundary_01` | No M14 observation/executor/workflow/Generation-input semantics in M13 source. |
