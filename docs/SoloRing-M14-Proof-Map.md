# SoloRing M14 Proof Map

Frozen R2 §46: the machine-checkable M14 proof inventory (90 cells).
Validated by `python scripts/m14_validate_proof_map.py` (Backend CI, before tests).

Disposition vocabulary:

- `TEST` — owner resolves against `pytest --collect-only` today;
- `STRUCTURAL` — owner is an M14 validator script;
- `PENDING` — the owning slice has not landed; the owner follows the
  frozen future-test grammar (`tests/test_m14*.py::test_m14_*`) and
  flips to `TEST` when its slice (R2 §54 cadence) delivers it. Closure
  mode (`M14_REQUIRE_COMPLETE=1`, used from M14B-6 on) forbids `PENDING`.

## M14-BASE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-BASE:01` | TEST | `tests/test_m14_0_baseline.py::test_m14_base_01` | Exact implementation predecessor 20429b3 / tree 0a755efe. |
| `M14-BASE:02` | TEST | `tests/test_m14_0_baseline.py::test_m14_base_02` | Immutable M13 tag/commit unchanged. |
| `M14-BASE:03` | TEST | `tests/test_m14_0_baseline.py::test_m14_base_03` | Migration predecessor exactly 0014. |
| `M14-BASE:04` | TEST | `tests/test_m14_base_corpus.py::test_m14_base_04` | WorkflowSpec schema-1/2/3 regression corpus green. |
| `M14-BASE:05` | PENDING | `tests/test_m14_base_corpus.py::test_m14_base_05` | ShotRevision schema-1..6 historical corpus green. |
| `M14-BASE:06` | PENDING | `tests/test_m14_base_corpus.py::test_m14_base_06` | Predecessor proof/boundary/security validators green. |

## M14-OBS

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-OBS:01` | TEST | `tests/test_m14_obs.py::test_m14_obs_01` | Strict WorldObservationSpec root grammar. |
| `M14-OBS:02` | TEST | `tests/test_m14_obs.py::test_m14_obs_02` | Canonical bytes/hash deterministic. |
| `M14-OBS:03` | TEST | `tests/test_m14_obs.py::test_m14_obs_03` | Strict Requirement grammar + identity ordering. |
| `M14-OBS:04` | TEST | `tests/test_m14_obs.py::test_m14_obs_04` | Strict ProductionOccurrence grammar + canonical order. |
| `M14-OBS:05` | TEST | `tests/test_m14_obs.py::test_m14_obs_05` | Strict Materialization grammar + canonical order. |
| `M14-OBS:06` | TEST | `tests/test_m14_obs.py::test_m14_obs_06` | Duplicate/conflicting requirement coordinate rejected. |
| `M14-OBS:07` | TEST | `tests/test_m14_obs.py::test_m14_obs_07` | camera.projection emission exact. |
| `M14-OBS:08` | TEST | `tests/test_m14_obs.py::test_m14_obs_08` | world.structure emission exact. |
| `M14-OBS:09` | TEST | `tests/test_m14_obs.py::test_m14_obs_09` | occurrence.structure emission exact. |
| `M14-OBS:10` | TEST | `tests/test_m14_obs.py::test_m14_obs_10` | occurrence.placement emission exact. |
| `M14-OBS:11` | TEST | `tests/test_m14_obs.py::test_m14_obs_11` | visual.identity conservative emission exact. |
| `M14-OBS:12` | TEST | `tests/test_m14_obs.py::test_m14_obs_12` | Every PI feature state emits exact requirement; no heuristic omission. |
| `M14-OBS:13` | TEST | `tests/test_m14_obs.py::test_m14_obs_13` | shot.intent emitted INFERABLE/PERMITTED_INFERENCE. |
| `M14-OBS:14` | TEST | `tests/test_m14_obs.py::test_m14_obs_14` | Nested Composition emits typed unsupported requirement, never flatten/omit. |
| `M14-OBS:15` | TEST | `tests/test_m14_obs.py::test_m14_obs_15` | Non-mesh retained ProductionRevision emits typed unsupported requirement. |
| `M14-OBS:16` | TEST | `tests/test_m14_obs.py::test_m14_obs_16` | Exact captured shot_revision_id drives compiler; schema-6 never enters the predecessor lower-logical fail-open path; zero current Shot resolver calls. |
| `M14-OBS:17` | TEST | `tests/test_m14_obs.py::test_m14_obs_17` | All executable structural meshes require exact interpretation. |
| `M14-OBS:18` | TEST | `tests/test_m14_0_g6_g7_corpus.py::test_m14_obs_18` | Golden WorldObservationSpec fixture bytes/hash exact. |
| `M14-OBS:19` | PENDING | `tests/test_m14_obs.py::test_m14_obs_19` | Current production-world resolver unavailable does not affect historical compiler/inspector path. |

## M14-CAP

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-CAP:01` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_01` | Strict profile schema-3 parser. |
| `M14-CAP:02` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_02` | Inherited profile-2 semantics delegated, not reimplemented. |
| `M14-CAP:03` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_03` | Policy identity exact-match gate. |
| `M14-CAP:04` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_04` | Exact property/preservation/source-contract/materializer tuple match. |
| `M14-CAP:05` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_05` | Supported hard requirement → SUPPORTED. |
| `M14-CAP:06` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_06` | Property-known tuple mismatch → UNSUPPORTED. |
| `M14-CAP:07` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_07` | Property absent → UNKNOWN. |
| `M14-CAP:08` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_08` | PERMITTED_INFERENCE does not require capability support. |
| `M14-CAP:09` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_09` | Overall verdict precedence exact. |
| `M14-CAP:10` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_10` | UNSUPPORTED/UNKNOWN refuses before Generation publication. |
| `M14-CAP:11` | TEST | `tests/test_m14_0_g6_g7_corpus.py::test_m14_cap_11` | NegotiationResult golden bytes/hash exact. |
| `M14-CAP:12` | TEST | `tests/test_m14_capabilities.py::test_m14_cap_12` | Live runtime availability cannot upgrade domain capability verdict. |

## M14-PKG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-PKG:01` | TEST | `tests/test_m14_package.py::test_m14_pkg_01` | Descriptor schema-4 coherent four-artifact capture. |
| `M14-PKG:02` | TEST | `tests/test_m14_package.py::test_m14_pkg_02` | Workflow identity agreement across descriptor/manifest/profile. |
| `M14-PKG:03` | TEST | `tests/test_m14_package.py::test_m14_pkg_03` | Captured capability contract hash bound to profile bytes. |
| `M14-PKG:04` | TEST | `tests/test_m14_package.py::test_m14_pkg_04` | Runtime fingerprint/template closure remains exact. |
| `M14-PKG:05` | TEST | `tests/test_m14_package.py::test_m14_pkg_05` | wan21_spatial_v1 v1 immutable/executable. |
| `M14-PKG:06` | TEST | `tests/test_m14_package.py::test_m14_pkg_06` | wan21_spatial_v1 v2 package validates. |
| `M14-PKG:07` | TEST | `tests/test_m14_package.py::test_m14_pkg_07` | Release-switch race cannot capture hybrid. |
| `M14-PKG:08` | TEST | `tests/test_m14_package.py::test_m14_pkg_08` | Recovery retains all four schema-4 package artifacts. |
| `M14-PKG:09` | TEST | `tests/test_m14_0_g6_g7_corpus.py::test_m14_pkg_09` | Profile schema-3 observation golden fixture/hash exact. |

## M14-MAT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-MAT:01` | TEST | `tests/test_m14_materializer.py::test_m14_mat_01` | structural_mesh.v1 canonical parser. |
| `M14-MAT:02` | TEST | `tests/test_m14_materializer.py::test_m14_mat_02` | Zero-area/out-of-range/malformed mesh rejected; winding not semantic. |
| `M14-MAT:03` | TEST | `tests/test_m14_materializer.py::test_m14_mat_03` | Retained Blob physical hash verified and is representation identity. |
| `M14-MAT:04` | TEST | `tests/test_m14_materializer.py::test_m14_mat_04` | Exact ProductionRevision/hash/blob agreement. |
| `M14-MAT:05` | TEST | `tests/test_m14_materializer.py::test_m14_mat_05` | Composition-owned interpretation + transform composition exact. |
| `M14-MAT:06` | TEST | `tests/test_m14_materializer.py::test_m14_mat_06` | A4 spatial-owned interpretation + placement composition exact. |
| `M14-MAT:07` | TEST | `tests/test_m14_materializer.py::test_m14_mat_07` | PI captured spatial-state matching/composition exact. |
| `M14-MAT:08` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_08` | Mesh contribution reaches world-depth non-background pixels. |
| `M14-MAT:09` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_09` | Zero-mesh schema-4 bytes == exact M10 bytes. |
| `M14-MAT:10` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_10` | Deterministic repeat under same materializer contract → identical digest. |
| `M14-MAT:11` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_11_real_concurrent_publication` | Identical concurrent publication converges. |
| `M14-MAT:12` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_12_same_coordinate_different_bytes` | Conflicting same-coordinate bytes fail invariant. |
| `M14-MAT:13` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_13_contract_hash_is_coordinate` | materializer_contract_hash participates in convergence identity. |
| `M14-MAT:14` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_14` | Retained mesh suppresses exact identity-matched M10 proxy once; inherited entity-depth double-conditioning for the same subject refuses in schema 1. |
| `M14-MAT:15` | TEST | `tests/test_m14_mesh_depth.py::test_m14_mat_15` | observation.world_depth media/frame/encoding/binding grammar exact. |

## M14-HIST

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-HIST:01` | TEST | `tests/test_m14_history.py::test_m14_hist_01` | Schema-4 WorkflowSpec stores exact observation/hash. |
| `M14-HIST:02` | TEST | `tests/test_m14_history.py::test_m14_hist_02` | Schema-4 stores exact negotiation/hash/capability-contract hash. |
| `M14-HIST:03` | TEST | `tests/test_m14_history.py::test_m14_hist_03` | Exact Rerun copies exact schema-4 bytes/hash. |
| `M14-HIST:04` | TEST | `tests/test_m14_history.py::test_m14_hist_04_observation_binding_copied` | Exact Rerun copies exact derived-observation artifact + Blob-hash binding. |
| `M14-HIST:05` | TEST | `tests/test_m14_b5_worker_closure.py::test_m14_hist_05_06` | Newer ProductionRevision cannot alter history. |
| `M14-HIST:06` | TEST | `tests/test_m14_b5_worker_closure.py::test_m14_hist_05_06` | Newer Composition/current binding/state cannot alter history. |
| `M14-HIST:07` | TEST | `tests/test_m14_b5_worker_closure.py::test_m14_hist_07` | Missing retained Production closure fails closed. |
| `M14-HIST:08` | TEST | `tests/test_m14_history.py::test_m14_hist_08_missing_artifact_fails_closed_no_remat` | Missing/corrupt observation artifact fails closed; never rematerialized. |
| `M14-HIST:09` | TEST | `tests/test_m14_derived_storage.py::test_recovery_blob_fk_inventory_eight_paths` | Backup/restore preserves schema-4 Generation + exact artifact binding. |
| `M14-HIST:10` | PENDING | `tests/test_m14_history.py::test_m14_hist_10` | Old schema-1/2/3 Generations remain legible/executable. |
| `M14-HIST:11` | TEST | `tests/test_m14_derived_storage.py::test_downgrade_schema4_history_refuses` | 0015 downgrade refuses live schema-4 history / non-empty derived state. |
| `M14-HIST:12` | TEST | `tests/test_m14_b5_hist12.py::test_m14_hist_12_captured_contract_not_current` | Historical provenance validates against captured contract, not current materializer. |

## M14-EXEC

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-EXEC:01` | TEST | `tests/test_m14_execution.py::test_m14_exec_01` | Schema-4 lower_schema_3 uses one shared inherited helper. |
| `M14-EXEC:02` | PENDING | `tests/test_m14_execution.py::test_m14_exec_02` | Pre-publication materialization completed before Generation commit. |
| `M14-EXEC:03` | PENDING | `tests/test_m14_execution.py::test_m14_exec_03` | Generation + WorkflowSpec-4 + exact artifact binding atomic. |
| `M14-EXEC:04` | TEST | `tests/test_m14_derived_storage.py::test_no_fake_asset_or_generation_input_for_m14_closure` | Schema-4 creates no fake Asset / dishonest GenerationInput. |
| `M14-EXEC:05` | TEST | `tests/test_m14_b5_worker_closure.py::test_m14_exec_05` | Worker makes zero current production-world resolver calls. |
| `M14-EXEC:06` | PENDING | `tests/test_m14_execution.py::test_m14_exec_06` | Runtime availability gate occurs before Comfy submission. |
| `M14-EXEC:07` | TEST | `tests/test_m14_b5_worker_closure.py::test_m14_exec_07` | Exact observation artifact binds inherited spatial.world_depth coordinate. |
| `M14-EXEC:08` | PENDING | `tests/test_m14_execution.py::test_m14_exec_08` | Real production workflow consumes exact retained control and imports Take. |
| `M14-EXEC:09` | PENDING | `tests/test_m14_execution.py::test_m14_exec_09` | Generation/Take causes zero production-authority mutation. |
| `M14-EXEC:10` | PENDING | `tests/test_m14_execution.py::test_m14_exec_10` | Full same-world/new-camera SHOOT THE WORLD + anti-wrapper source gate passes. |

## M14-SCALE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-SCALE:01` | PENDING | `tests/test_m14_scale.py::test_m14_scale_01` | 10/100/1000 closure load has bounded SQL classes. |
| `M14-SCALE:02` | PENDING | `tests/test_m14_scale.py::test_m14_scale_02` | No per-occurrence closure/interpretation SELECT loop. |
| `M14-SCALE:03` | PENDING | `tests/test_m14_scale.py::test_m14_scale_03` | B1 frozen resource caps fail before rasterization allocation. |
| `M14-SCALE:04` | PENDING | `tests/test_m14_scale.py::test_m14_scale_04` | Benchmark/materializer records CPU + peak memory + artifact size. |
| `M14-SCALE:05` | PENDING | `tests/test_m14_scale.py::test_m14_scale_05` | Repository residue absent after scale/benchmark proofs. |

## M14-UI

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M14-UI:01` | PENDING | `tests/test_m14_ui.py::test_m14_ui_01` | Refusal traces property → preservation → authority/source → contract → verdict. |
| `M14-UI:02` | PENDING | `tests/test_m14_ui.py::test_m14_ui_02` | Historical inspector separates captured observation/artifact from current environment. |
