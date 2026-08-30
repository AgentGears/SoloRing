# SoloRing M10F Proof Map (R6 §16)

Machine-validated by `scripts/m10f_validate_proof_map.py`. Row grammar:
`| <DOMAIN>:<id> | <disposition> | <pytest owner or substitute> | note |`.
Dispositions: TEST / STRUCTURAL / INHERITED / NOT-APPLICABLE-SOURCE-FIT.
Non-pytest closure commands live in the closure-command appendix
(`| CMD:<name> | <command> | <evidence owner> |`) and are never
misrepresented as pytest owners.

**Status:
M10F-A COMPLETE against R6
M10F-B COMPLETE
M10F-C COMPLETE
M10F-D COMPLETE
M10F-E COMPLETE (all gates incl. GPU + archive PASS)**

The validator passes only when every domain below is complete and every
TEST owner resolves.

## M10F-A — recovery matrix (§7.9 cells 1-31)

| RECOVERY:1 | TEST | tests/test_m10f_backup_restore.py::test_cell_01_missing_backup_db_fails_restore | |
| RECOVERY:2 | TEST | tests/test_m10f_backup_restore.py::test_cell_02_tampered_backup_db_fails_restore | |
| RECOVERY:3 | TEST | tests/test_m10f_backup_restore.py::test_cell_03_malformed_manifest_fails_restore | |
| RECOVERY:4 | TEST | tests/test_m10f_backup_restore.py::test_cell_04_noncanonical_manifest_fails_restore | noncanonical + unsorted (04b) + duplicate (04c) variants |
| RECOVERY:5 | TEST | tests/test_m10f_backup_restore.py::test_cell_05_manifest_db_hash_mismatch_fails_restore | |
| RECOVERY:6 | TEST | tests/test_m10f_backup_restore.py::test_cell_06_missing_live_blob_fails_backup | |
| RECOVERY:7 | TEST | tests/test_m10f_backup_restore.py::test_cell_07_corrupt_live_blob_fails_backup | |
| RECOVERY:8 | TEST | tests/test_m10f_backup_restore.py::test_cells_08_to_11_missing_artifact_fails_backup | parameterized over all four kinds; cell 17 covered by the profile/fingerprint parameters |
| RECOVERY:9 | TEST | tests/test_m10f_backup_restore.py::test_cells_08_to_11_missing_artifact_fails_backup | templates parameter |
| RECOVERY:10 | TEST | tests/test_m10f_backup_restore.py::test_cells_08_to_11_missing_artifact_fails_backup | realization_profiles parameter |
| RECOVERY:11 | TEST | tests/test_m10f_backup_restore.py::test_cells_08_to_11_missing_artifact_fails_backup | execution_model_fingerprints parameter |
| RECOVERY:12 | TEST | tests/test_m10f_backup_restore.py::test_cell_12_corrupt_artifact_bytes_fail_backup | |
| RECOVERY:13 | TEST | tests/test_m10f_backup_restore.py::test_cell_13_existing_destination_rejected | backup + restore destinations |
| RECOVERY:14 | TEST | tests/test_m10f_backup_restore.py::test_cell_14_fk_corruption_fails_backup | |
| RECOVERY:15 | TEST | tests/test_m10f_backup_restore.py::test_cell_15_spec_corruption_fails_backup | |
| RECOVERY:16 | TEST | tests/test_m10f_backup_restore.py::test_cell_16_missing_derived_blob_fails_backup | |
| RECOVERY:17 | TEST | tests/test_m10f_backup_restore.py::test_cells_08_to_11_missing_artifact_fails_backup | schema-3 release member missing = profile/fingerprint parameter on the schema-3 template history |
| RECOVERY:18 | TEST | tests/test_m10f_backup_restore.py::test_cell_18_source_changes_after_backup_do_not_leak_into_restore | |
| RECOVERY:19 | TEST | tests/test_m10f_backup_restore.py::test_cell_19_post_snapshot_generation_stays_absent | |
| RECOVERY:20 | TEST | tests/test_m10f_backup_restore.py::test_cell_20_injected_sqlite_backup_failure | injected one layer above the immutable C Connection.backup builtin; same exception type |
| RECOVERY:21 | TEST | tests/test_m10f_backup_restore.py::test_restore_process_death_before_publish_leaves_only_orphan_stage | real child-process os._exit at the final-publish seam |
| RECOVERY:22 | TEST | tests/test_m10f_backup_restore.py::test_cell_22_orphan_derived_artifact_blob_survives | |
| RECOVERY:23 | TEST | tests/test_m10f_backup_restore.py::test_cell_23_24_repeated_artifact_kinds_all_represented | v1+v1b+v4+v3 manifests; v1/v4 share workflow.json bytes (source-true) |
| RECOVERY:24 | TEST | tests/test_m10f_backup_restore.py::test_cell_23_24_repeated_artifact_kinds_all_represented | profile/fingerprint histories of schema-2 and schema-3 releases |
| RECOVERY:25 | TEST | tests/test_m10f_backup_restore.py::test_cell_25_source_change_between_prehash_and_copy_fails | |
| RECOVERY:26 | TEST | tests/test_m10f_backup_restore.py::test_cell_26_staged_artifact_altered_before_manifest_fails | |
| RECOVERY:27 | TEST | tests/test_m10f_backup_restore.py::test_cell_27_active_writer_overlapping_backup_yields_coherent_cut | |
| RECOVERY:28 | TEST | tests/test_m10f_backup_restore.py::test_cell_28_spec_ordinary_projection_mismatch_fails_backup | |
| RECOVERY:29 | TEST | tests/test_m10f_backup_restore.py::test_cell_29_spec_derived_identity_mismatch_fails_backup | |
| RECOVERY:30 | TEST | tests/test_m10f_backup_restore.py::test_external_deletion_fail_closed_no_rematerialization | |
| RECOVERY:31 | TEST | tests/test_m10f_backup_restore.py::test_workflow_artifact_root_override_rejected_before_staging | test-only divergent root injection; no settings surface exists |

## M10F-A — backup/restore algorithm obligations (§7.1-§7.8)

| BACKUPALGO:posture-db-url | TEST | tests/test_m10f_backup_restore.py::test_posture_database_url_override_rejected_before_staging | |
| BACKUPALGO:posture-blob-dir | TEST | tests/test_m10f_backup_restore.py::test_posture_blob_dir_override_rejected_before_staging | |
| BACKUPALGO:posture-default | TEST | tests/test_m10f_backup_restore.py::test_posture_default_passes | |
| BACKUPALGO:manifest-grammar | TEST | tests/test_m10f_backup_restore.py::test_cell_04_noncanonical_manifest_fails_restore | strict parser rejections across cells 3/4/4b/4c/5 |
| BACKUPALGO:finalize-contract | TEST | tests/test_m10f_backup_restore.py::test_same_filesystem_atomic_finalize_contract | |
| BACKUPALGO:ordering-blob | TEST | tests/test_m10f_backup_restore.py::test_blob_physical_before_reference_commit_invariant | with deliberate positive control |
| BACKUPALGO:ordering-artifacts | TEST | tests/test_m10f_backup_restore.py::test_workflow_artifacts_physical_before_generation_reference_commit | release identities hash-verified at the seam |
| BACKUPALGO:fk-completeness | TEST | tests/test_m10f_backup_restore.py::test_fk_liveness_drift_fails_backup | R6 exact six-path inventory, including both M8 visual-provenance FKs |
| BACKUPALGO:legacy-d0-path | TEST | tests/test_m10f_backup_restore.py::test_legacy_absolute_d0_blob_path_preserved_but_never_followed | R6 PD-2: old absolute D0 metadata preserved, never dereferenced; physical access is hash-derived under the active BlobStore root; mismatched canonical suffix rejected. |
| BACKUPALGO:full-cycle | TEST | tests/test_m10f_backup_restore.py::test_backup_restore_full_cycle_spans_schema_1_2_3 | §7.8 proof incl. restored Exact Rerun |
| BACKUPALGO:source-write-coherence | TEST | tests/test_m10f_backup_restore.py::test_cell_27_active_writer_overlapping_backup_yields_coherent_cut | online snapshot cut |

## M10F-B — error map (§8.3; F-034/F-035)

| ERROR:SPATIAL_WORLD_INVALID | INHERITED | tests/test_m10c_r2_guards.py::test_world_delete_blocked_while_active_track_exists | |
| ERROR:SPATIAL_WORLD_STATE_INVALID | TEST | tests/test_m10f_adversarial.py::test_error_world_state_invalid_nonuuid_location_revision | previously unasserted; added by M10F |
| ERROR:SPATIAL_WORLD_CAPTURE_CONFLICT | INHERITED | tests/test_m10b_closure.py::test_race_real_capture_vs_world_edit | |
| ERROR:SPATIAL_FRAME_INVALID | TEST | tests/test_m10f_adversarial.py::test_error_frame_invalid_transform_shape | previously unasserted |
| ERROR:SPATIAL_FRAME_CYCLE | STRUCTURAL | tests/test_m10f_adversarial.py::test_error_frame_cycle_planted_parent_graph | planted cycle; production patch-seam walk rejects |
| ERROR:SPATIAL_AXIS_INVALID | TEST | tests/test_m10f_adversarial.py::test_error_axis_invalid_frame_is_state_axis_endpoint | previously unasserted |
| ERROR:SPATIAL_WORLD_REVISION_NOT_FOUND | TEST | tests/test_m10f_adversarial.py::test_error_world_revision_not_found | previously unasserted |
| ERROR:SPATIAL_WORLD_APPROVAL_CONFLICT | TEST | tests/test_m10f_adversarial.py::test_error_world_approval_conflict_stale_expected | previously unasserted |
| ERROR:SPATIAL_TRACK_INVALID | TEST | tests/test_m10f_adversarial.py::test_error_track_invalid_cross_project_world | previously unasserted |
| ERROR:SPATIAL_ENTITY_INSTANCING_UNSUPPORTED | INHERITED | tests/test_m10c_tracks.py::test_track_create_valid_and_duplicate_translated | |
| ERROR:SPATIAL_TRANSITION_INVALID | INHERITED | tests/test_m10c_r3_guards.py::test_empty_patch_noop_fails_closed_beneath_tombstoned_world | |
| ERROR:SPATIAL_SHOT_PLAN_INVALID | INHERITED | tests/test_m10d_plans.py::test_plan_api_transport_strictness | |
| ERROR:SPATIAL_SHOT_PLAN_CONFLICT | TEST | tests/test_m10f_adversarial.py::test_error_shot_plan_conflict_stale_expected_hash | previously unasserted |
| ERROR:SPATIAL_CONTEXT_AMBIGUOUS | INHERITED | tests/test_m10d_resolver.py::test_world_selection_matrix | |
| ERROR:SPATIAL_SHOT_PLAN_REQUIRED | INHERITED | tests/test_m10d_r2_proofs.py::test_race_plan_delete_after | |
| ERROR:SPATIAL_WORLD_STATE_REQUIRED | INHERITED | tests/test_m10d_resolver.py::test_state_and_approval_issues | |
| ERROR:SPATIAL_WORLD_APPROVAL_REQUIRED | INHERITED | tests/test_m10d_capture.py::test_capture_blocked_by_spatial_issue | |
| ERROR:SPATIAL_TRACK_STATE_REQUIRED | INHERITED | tests/test_m10c_staging.py::test_staging_required_absence_blocks_optional_succeeds | |
| ERROR:SPATIAL_ENTITY_PLACEMENT_CONFLICT | INHERITED | tests/test_m10d_r2_guards.py::test_fixed_placement_conflicts_with_absent_applicable_track | placement leg |
| ERROR:SPATIAL_ENTITY_REVISION_MISMATCH | INHERITED | tests/test_m10d_r2_guards.py::test_fixed_placement_conflicts_with_absent_applicable_track | revision leg |
| ERROR:SPATIAL_BLOCKING_STATE_MISMATCH | INHERITED | tests/test_m10d_r2_proofs.py::test_race_transition_edit_after | |
| ERROR:SPATIAL_AXIS_CONSTRAINT_VIOLATION | INHERITED | tests/test_m10d_resolver.py::test_axis_enforcement | |
| ERROR:SPATIAL_REALIZATION_UNSUPPORTED | INHERITED | tests/test_m10d_capture.py::test_pre_m10e_generation_fence | capacity conversion seam additionally covered by M10E generation tests |
| ERROR:SPATIAL_REALIZATION_BINDING_INVALID | INHERITED | tests/test_m10e_atomic_persistence.py::test_cross_family_key_collision_fails_in_unit | |
| ERROR:DERIVED_SPATIAL_SPEC_INVALID | INHERITED | tests/test_m10a_derived.py::test_float_identity_and_runtime_algorithm_mismatch_fail | |
| ERROR:DERIVED_SPATIAL_KIND_UNSUPPORTED | TEST | tests/test_m10f_adversarial.py::test_derived_error_kind_unsupported | previously unasserted |
| ERROR:DERIVED_SPATIAL_RUNTIME_UNPINNABLE | TEST | tests/test_m10f_adversarial.py::test_derived_error_runtime_unpinnable | previously unasserted |
| ERROR:DERIVED_SPATIAL_NONDETERMINISTIC | INHERITED | tests/test_m10a_derived.py::test_global_d0_different_blob_fails | |
| ERROR:DERIVED_SPATIAL_MATERIALIZATION_FAILED | NOT-APPLICABLE-SOURCE-FIT | tests/test_m10f_adversarial.py::test_reserved_derived_codes_have_no_raiser | source: no raise site exists in the published tree — reserved frozen vocabulary (spatial/error_codes.py); substitute is the no-raiser structural scan |
| ERROR:DERIVED_SPATIAL_OUTPUT_INVALID | TEST | tests/test_m10f_adversarial.py::test_derived_error_output_invalid | previously unasserted |
| ERROR:DERIVED_SPATIAL_PROVENANCE_MISMATCH | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_provenance_mismatch_fails | |
| ERROR:DERIVED_SPATIAL_BLOB_MISSING | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_missing_blob_fails | |
| ERROR:DERIVED_SPATIAL_BLOB_CORRUPT | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_corrupt_blob_fails | |
| ERROR:DERIVED_SPATIAL_CAPTURE_CONFLICT | NOT-APPLICABLE-SOURCE-FIT | tests/test_m10f_adversarial.py::test_reserved_derived_codes_have_no_raiser | source: no raise site exists in the published tree — reserved vocabulary |
| ERROR:DERIVED_SPATIAL_BINDING_INVALID | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_wrong_binding_fails | |
| ERROR:DERIVED_SPATIAL_HARD_COMPONENT_LOSS | NOT-APPLICABLE-SOURCE-FIT | tests/test_m10f_adversarial.py::test_reserved_derived_codes_have_no_raiser | source: no raise site exists in the published tree — reserved vocabulary |

## M10F-B — frozen M10 §61 race classes 1-19 (§8.5; F-050)

| RACE61:1 | INHERITED | tests/test_m10b_closure.py::test_race_real_capture_vs_world_edit | world frame/axis membership/value edit vs capture |
| RACE61:2 | INHERITED | tests/test_m10d_races.py::test_race_world_approval_and_requirement | |
| RACE61:3 | INHERITED | tests/test_m10d_races.py::test_race_transition_edit_and_track_requirement | |
| RACE61:4 | INHERITED | tests/test_m10d_races.py::test_race_plan_edit_vs_capture_before_and_after | |
| RACE61:5 | INHERITED | tests/test_m10d_races.py::test_race_entity_revision_approval | |
| RACE61:6 | INHERITED | tests/test_m10d_races.py::test_race_entity_revision_approval | dependent EntityRevision leg |
| RACE61:7 | INHERITED | tests/test_m10b_world_authority.py::test_approval_cas_lifecycle | competing approvals resolve through the CAS |
| RACE61:8 | INHERITED | tests/test_m10b_closure.py::test_race_real_capture_vs_approval_change | approval vs unapproval pointer change |
| RACE61:9 | INHERITED | tests/test_m10d_races.py::test_race_world_approval_and_requirement | world requirement flip |
| RACE61:10 | INHERITED | tests/test_m10d_races.py::test_race_transition_edit_and_track_requirement | track requirement flip |
| RACE61:11 | INHERITED | tests/test_m9f_gate.py::test_package_switch_before_snapshot_uses_complete_after | package/profile replacement vs capture/readiness; after-snapshot variant alongside |
| RACE61:12 | TEST | tests/test_m10f_adversarial_worker.py::test_class19_worker_continues_from_retained_bytes_after_package_replacement | worker execution vs current package change |
| RACE61:13 | INHERITED | tests/test_m10e_rerun.py::test_current_authority_mutation_cannot_change_rerun_identity | Exact Rerun vs current changes |
| RACE61:14 | INHERITED | tests/test_m10b_closure.py::test_race_real_capture_vs_world_edit | stable-frame parent/bound-Entity metadata edit leg |
| RACE61:15 | TEST | tests/test_m10e_races.py::test_authority_mutation_during_realization_changes_nothing | derived materialization vs current M10 edit |
| RACE61:16 | TEST | tests/test_m10e_races.py::test_concurrent_identical_registrations_converge | |
| RACE61:17 | TEST | tests/test_m10e_atomic_persistence.py::test_pre_published_artifacts_survive_rollback | derived publication vs Generation fence loss |
| RACE61:18 | NOT-APPLICABLE-SOURCE-FIT | tests/test_m10f_backup_restore.py::test_external_deletion_fail_closed_no_rematerialization | source: no production GC/delete mechanism exists (§8.5.3); substitute is the external-deletion fail-closed proof |
| RACE61:19 | TEST | tests/test_m10f_adversarial_worker.py::test_class19_current_materializer_not_consulted_by_worker | worker vs materializer/package replacement pair |

## M10F-B — M10D §66 composed capture races (F-050/F-121)

| RACEM10D:66.1 | INHERITED | tests/test_m10d_races.py::test_race_plan_edit_vs_capture_before_and_after | |
| RACEM10D:66.2 | INHERITED | tests/test_m10d_races.py::test_race_world_approval_and_requirement | |
| RACEM10D:66.3 | INHERITED | tests/test_m10d_races.py::test_race_world_approval_and_requirement | |
| RACEM10D:66.4 | INHERITED | tests/test_m10d_races.py::test_race_transition_edit_and_track_requirement | |
| RACEM10D:66.5 | INHERITED | tests/test_m10d_races.py::test_race_entity_revision_approval | |
| RACEM10D:66.6 | INHERITED | tests/test_m10d_races.py::test_race_world_approval_and_requirement | |
| RACEM10D:66.7 | INHERITED | tests/test_m10d_races.py::test_race_transition_edit_and_track_requirement | |
| RACEM10D:66.8 | INHERITED | tests/test_m10d_races.py::test_race_narrative_reorder_vs_capture | |
| RACEM10D:66.9 | INHERITED | tests/test_m10d_races.py::test_race_duration_and_dependency_set | |
| RACEM10D:66.10 | INHERITED | tests/test_m10d_races.py::test_race_duration_and_dependency_set | |

## M10F-B — whole-M10 umbrella corruption cells 1-25 (§8.4; F-046)

| CORRUPT:1 | INHERITED | tests/test_m10b_world_authority.py::test_corrupt_snapshot_fails_reuse_then_restores | snapshot_json bytes |
| CORRUPT:2 | INHERITED | tests/test_m10b_world_authority.py::test_corrupt_snapshot_fails_reuse_then_restores | snapshot_hash leg of the same cycle |
| CORRUPT:3 | INHERITED | tests/test_m10b_closure.py::test_corrupt_frame_child_update_fails_then_restores | |
| CORRUPT:4 | INHERITED | tests/test_m10b_closure.py::test_corrupt_axis_child_update_fails_then_restores | |
| CORRUPT:5 | INHERITED | tests/test_m10b_world_authority.py::test_approval_cas_lifecycle | cross-state approved pointer |
| CORRUPT:6 | INHERITED | tests/test_m10d_capture.py::test_historical_denylist_and_corruption_loop | |
| CORRUPT:7 | INHERITED | tests/test_m10d_capture.py::test_schema5_capture_children_and_convergence | track-state child projection |
| CORRUPT:8 | INHERITED | tests/test_m10d_capture.py::test_working_hash_sensitivity | track transform/source transition |
| CORRUPT:9 | INHERITED | tests/test_m10d_plans.py::test_parser_canonical_byte_identity | plan bytes/hash |
| CORRUPT:10 | INHERITED | tests/test_m10d_capture.py::test_schema5_capture_children_and_convergence | schema-5 spatial_continuity vs nested world hash |
| CORRUPT:11 | INHERITED | tests/test_m10d_capture.py::test_schema5_capture_children_and_convergence | embedded plan vs normalized child projection |
| CORRUPT:12 | TEST | tests/test_m10f_adversarial_worker.py::test_schema5_m8_block_child_projection_corruption_cycle | dedicated M10F cross-slice cycle |
| CORRUPT:13 | INHERITED | tests/test_m10e_corruption.py::test_cells18_19_20_five_step_cycle | spec v3 document/hash |
| CORRUPT:14 | INHERITED | tests/test_m10e_corruption.py::test_cells18_19_20_five_step_cycle | spec runtime-fingerprint identity leg |
| CORRUPT:15 | INHERITED | tests/test_m10e_corruption.py::test_cells13_15_manifest_grammar_corruptions | package spatial binding target/format |
| CORRUPT:16 | INHERITED | tests/test_m10a_derived.py::test_prepare_canonical_runtime_separate_and_provenance_cross_validated | derived spec/hash (M10E cells 23-25) |
| CORRUPT:17 | INHERITED | tests/test_m10a_derived.py::test_prepare_canonical_runtime_separate_and_provenance_cross_validated | derived runtime fingerprint/hash (M10E cells 27-29) |
| CORRUPT:18 | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_provenance_mismatch_fails | provenance→Blob identity |
| CORRUPT:19 | INHERITED | tests/test_m10e_corruption.py::test_cell34_physical_blob_corrupt | physical derived Blob bytes |
| CORRUPT:20 | INHERITED | tests/test_m10e_corruption.py::test_cells42_43_extra_missing_sibling_vs_spec | gdsi projection |
| CORRUPT:21 | INHERITED | tests/test_m10e_corruption.py::test_cells18_19_20_five_step_cycle | workflow-spec artifact references |
| CORRUPT:22 | TEST | tests/test_m10f_adversarial_worker.py::test_schema3_structured_binding_corruption_cycle | dedicated M10F |
| CORRUPT:23 | TEST | tests/test_m10f_adversarial_worker.py::test_schema3_derived_list_order_corruption_cycle | dedicated M10F; M10E cell 51 alongside |
| CORRUPT:24 | TEST | tests/test_m10f_adversarial_worker.py::test_historical_package_member_corruption_cycle | dedicated M10F |
| CORRUPT:25 | TEST | tests/test_m10f_backup_restore.py::test_backup_restore_full_cycle_spans_schema_1_2_3 | recovery files/faults (§7.9 matrix) |

## M10F-B — authority-direction isolation (§8.6/§9; F-060..F-064)

| ISOLATION:authority-write-spy | TEST | tests/test_m10f_adversarial.py::test_no_authority_transfer_write_spy | converged recreate + rerun scope |
| ISOLATION:shot-revisions-positive-control | TEST | tests/test_m10f_adversarial.py::test_no_authority_transfer_positive_control_trips_on_shot_revisions | |
| ISOLATION:inventory-parity | TEST | tests/test_m10f_adversarial.py::test_authority_write_inventory_matches_owner_models | |
| ISOLATION:worker-zero-current-m10 | INHERITED | tests/test_m10a4_worker_rerun.py::test_worker_transport_valid | spy over current_m10_table_names during full transport |
| ISOLATION:rerun-zero-current-m10 | INHERITED | tests/test_m10e_rerun.py::test_rerun_zero_current_m10_reads_and_zero_rematerialization | |
| ISOLATION:current-read-positive-control | TEST | tests/test_m10f_adversarial.py::test_rerun_current_read_isolation_with_positive_control | |
| ISOLATION:rerun-zero-rematerialization | INHERITED | tests/test_m10e_rerun.py::test_rerun_zero_current_m10_reads_and_zero_rematerialization | |
| ISOLATION:drift-identity-stability | INHERITED | tests/test_m10e_rerun.py::test_current_authority_mutation_cannot_change_rerun_identity | |

## M10F-B — determinism obligations (§13; DETERM:10 lands with M10F-E)

| DETERM:1 | INHERITED | tests/test_m10a_math.py::test_fixture_1_identity_pose_camera_forward_is_world_negz | math goldens family; normalization/±180 fixtures alongside |
| DETERM:2 | INHERITED | tests/test_m10b_world_authority.py::test_capture_deterministic_and_converging | shuffled world inputs → identical revision bytes |
| DETERM:3 | INHERITED | tests/test_m10b_world_authority.py::test_capture_deterministic_and_converging | (axis.key, axis.id) ordering inside the same capture determinism |
| DETERM:4 | INHERITED | tests/test_m10c_scale.py::test_byte_identical_staging_bytes_under_shuffled_db_return_order | |
| DETERM:5 | INHERITED | tests/test_m10d_plans.py::test_parser_canonical_byte_identity | |
| DETERM:6 | INHERITED | tests/test_m10d_capture.py::test_schema5_capture_children_and_convergence | shuffled rows → identical schema-5 snapshot bytes |
| DETERM:7 | INHERITED | tests/test_m10e_generation.py::test_repeated_creation_converges_on_retained_identities | v3 shuffled-order convergence |
| DETERM:8 | INHERITED | tests/test_m10a_derived.py::test_global_d0_convergence_cross_project | semantic layer; N≥3 byte specimen recorded separately at M10F-E |
| DETERM:9 | INHERITED | tests/test_m10e_races.py::test_concurrent_identical_registrations_converge | |

## M10F-C — compatibility lattice (R6 §10.2/§10.1; F-070..F-082)

| COMPAT:shotrev-1 | INHERITED | tests/test_m10d_capture.py::test_lower_schema_byte_preservation_and_zero_children | schema-1/2 history readable, never fabricated |
| COMPAT:shotrev-2 | INHERITED | tests/test_m10d_capture.py::test_lower_schema_byte_preservation_and_zero_children | schema-2 predecessor semantic capture preserved |
| COMPAT:shotrev-3 | INHERITED | tests/test_m10d_capture.py::test_lower_schema_byte_preservation_and_zero_children | schema-3 predecessor continuity capture preserved |
| COMPAT:shotrev-4 | INHERITED | tests/test_m10d_capture.py::test_lower_schema_byte_preservation_and_zero_children | schema-4 M8-history capture preserved |
| COMPAT:shotrev-5 | INHERITED | tests/test_m10d_capture.py::test_schema5_capture_children_and_convergence | schema 5 requires its non-empty canonical spatial pack |
| COMPAT:pkg1-empty-v1 | TEST | tests/test_m10f_compatibility.py::test_pkg1_empty_authority_emits_exact_v1 | |
| COMPAT:pkg2-empty-v1 | INHERITED | tests/test_m9c_generation.py::test_v2_package_empty_authority_yields_exact_spec_v1 | exact-v1 selection on empty authority; cardinality-honesty leg |
| COMPAT:pkg2-m8-v2 | INHERITED | tests/test_m9c_generation.py::test_schema2_generation_captures_realization_and_model | |
| COMPAT:pkg12-m10-blocked | INHERITED | tests/test_m10d_capture.py::test_pre_m10e_generation_fence | non-spatial package + non-empty M10 fails closed |
| COMPAT:pkg3-empty-v1-fallback | TEST | tests/test_m10f_compatibility.py::test_schema3_package_v1_fallback_executes_worker_and_exact_rerun | creation leg: test_schema3_package_empty_m8_empty_m10_emits_exact_v1 |
| COMPAT:pkg3-m8-v2-fallback | TEST | tests/test_m10f_compatibility.py::test_schema3_package_v2_fallback_executes_worker_and_exact_rerun | creation leg: test_schema3_package_m8_only_emits_exact_v2 |
| COMPAT:pkg3-m10-only-v3 | INHERITED | tests/test_m10e_generation.py::test_schema5_full_realization_path | no fake M9 block; real model identity |
| COMPAT:pkg3-m8-m10-v3 | INHERITED | tests/test_m10e_generation.py::test_m9_v2_to_v3_payload_parity | independent M9+M10 blocks through the shared compiler seam |
| COMPAT:rerun-no-upgrade | INHERITED | tests/test_m10e_rerun.py::test_rerun_copies_spec_bytes_and_derived_projection | plus both M10F drives' rerun legs |
| COMPAT:worker-retained-artifacts | TEST | tests/test_m10f_adversarial_worker.py::test_class19_worker_continues_from_retained_bytes_after_package_replacement | |
| COMPAT:runtime-drift-executability-only | INHERITED | tests/test_m9d_worker.py::test_worker_model_byte_drift_blocks_before_submission | drift blocks execution, never rewrites identity |

## M10F-D — scale obligations (§11 / F-085..F-090)

| SCALE:fixture-determinism | TEST | tests/test_m10f_scale.py::test_representative_fixture_determinism | uuid5 identities; canonical inventory digest/counts equal across two clean builds |
| SCALE:resolution-bounded | TEST | tests/test_m10f_scale.py::test_current_resolution_statement_shape_small_vs_representative | identical normalized statement classes/count |
| SCALE:capture-bounded | TEST | tests/test_m10f_scale.py::test_first_schema5_capture_statement_shape_fresh_targets | both targets proven zero-revision before measurement |
| SCALE:generation-cold-bounded | TEST | tests/test_m10f_scale.py::test_first_generation_matched_cold_statement_shape | cold ledger gate + real D0/registration; identical statement multiset |
| SCALE:no-fanout | TEST | tests/test_m10f_scale.py::test_current_resolution_statement_shape_small_vs_representative | identical count at 2,500+ shots proves no per-track/frame round trips |
| SCALE:metrics-recorded | TEST | tests/test_m10f_scale.py::test_scale_metrics_recorded_without_thresholds | §11.5 metric set incl. backup/restore; wall times informational only |

## M10F-D — canonical continuity demonstrations (§12 / F-092..F-096)

| DEMO:lobby-reverse-angle | TEST | tests/test_m10f_scale.py::test_lobby_reverse_angle_shared_world_authority | shared approved world revision identity; independent cameras; current edits rewrite neither; rerun stays historical |
| DEMO:moving-character | TEST | tests/test_m10f_scale.py::test_moving_character_direct_resolution_no_playback | Shot 21 resolves desk transform directly; take changes never feed authority; transition change does alter future resolution |
| DEMO:cross-domain | TEST | tests/test_m10f_compatibility.py::test_schema3_package_v2_fallback_executes_worker_and_exact_rerun | schema-5+M8+M10 combined authority; mutation legs in rerun isolation tests; original identities retained |

## M10F-E — determinism specimen 10 + source-gate owners

| DETERM:10 | TEST | tests/test_m10f_source_gate.py::test_d0_n3_same_runtime_exact_blob_sha_specimen | N=3 same-runtime exact digest equality through the real compose path; recorded separately from GPU evidence (F-127) |

## Documentation / frontend / evidence obligations

| CMD:frontend-gate | npm test && npx tsc --noEmit && SOLORING_API_ORIGIN=http://127.0.0.1:65534 npm run build | apps/web — 92/92 + typecheck + production build at M10F-E |
| CMD:backend-x2 | python -m pytest -q ×2 consecutive | full backend — 1550/1550 both runs at M10F-E |
| CMD:compileall | python -m compileall server scripts | PASS at M10F-E |
| CMD:gpu-two-lane | scripts/m10f_two_lane_smoke.py | PASS 2026-08-30T05:58:31 — both lanes + reruns on the certified executor (b963f4ad + wrapper 088128b2 @ tree f3e0aea2); lane1 video:0 13.2MB, lane2 video:0 9.4MB; executor restart between lanes (12GB VRAM limit) |
| CMD:archive-fidelity | git archive HEAD → SoloRing-M10F-closing.zip + scripts/m10f_archive_fidelity.py | PASS @ e39f0d4f — 429/429 exact, 0 mismatches |
