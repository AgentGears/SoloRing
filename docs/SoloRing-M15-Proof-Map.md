# SoloRing M15 Proof Map

Frozen R5 §31: the machine-checkable M15 proof inventory (126 cells).
Validated by `python scripts/m15_validate_proof_map.py` (Backend CI, before tests).

Disposition vocabulary:

- `TEST` — owner resolves against `pytest --collect-only` (python) or the
  exact quoted vitest title (frontend) today;
- `PENDING` — the owning slice has not landed; the owner follows the
  frozen future-test grammars (`tests/test_m15*.py::test_*` or
  `apps/web/src/__tests__/m15-*.test.tsx::<title>`) and flips to `TEST`
  when its slice (R4 §28 cadence) delivers it. Closure mode
  (`M15_REQUIRE_COMPLETE=1`, used from M15D on) forbids `PENDING`.

M15 has no STRUCTURAL cells: the frozen §31 map assigns every cell a
test owner. Diagnostic cardinalities (derived mechanically by the
validator from the hard-coded inventory): BASE 10 / MIG 10 / CAN 11 /
EVAL 20 / TRANS 9 / IMPACT 8 / TRACK 8 / APPLY 16 / RACE 7 / HIST 10 /
REC 4 / UI 6 / SCALE 7 — total 126.

## M15-BASE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-BASE:01` | TEST | `tests/test_m15_baseline.py::test_m14_commit_tree_and_tag_baseline` | exact M14 predecessor identity |
| `M15-BASE:02` | TEST | `tests/test_m15_baseline.py::test_migration_head_is_0015_before_m15` | predecessor migration head |
| `M15-BASE:03` | TEST | `tests/test_m15_baseline.py::test_predecessor_proof_validators_green` | M11–M14 validators preserved |
| `M15-BASE:04` | TEST | `tests/test_m15_baseline.py::test_no_predecessor_migration_bytes_changed` | migrations immutable |
| `M15-BASE:05` | TEST | `tests/test_m15_baseline.py::test_m15_source_scope_excludes_execution_source` | no execution-source expansion |
| `M15-BASE:06` | TEST | `tests/test_m15_baseline.py::test_direct_source_swap_is_the_intended_m15_seam` | source-fit characterization |
| `M15-BASE:07` | TEST | `tests/test_m15_baseline.py::test_m12_direct_patch_proof_has_explicit_m15_successor` | behavioral succession is named, not disabled |
| `M15-BASE:08` | TEST | `tests/test_m15_placement_shared_classifier.py::test_m13_and_m15_use_one_shared_placement_classifier` | one pure/no-I/O product-code owner of placement classification |
| `M15-BASE:09` | TEST | `tests/test_m15_placement_shared_classifier.py::test_m13_published_behavior_matches_pinned_m14_across_full_case_matrix` | semantics-preserving M13 refactor across all six issue codes + clean/ambiguous cases |
| `M15-BASE:10` | TEST | `tests/test_m15_placement_seam_probe.py::test_working_state_twin_oracle_matches_published_shared_classifier` | working/published caller wiring congruence |

## M15-MIG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-MIG:01` | TEST | `tests/test_m15_migration.py::test_0016_adds_exact_five_tables` | exact additive schema |
| `M15-MIG:02` | TEST | `tests/test_m15_migration.py::test_0016_alters_no_predecessor_table` | no predecessor rebuild |
| `M15-MIG:03` | TEST | `tests/test_m15_migration.py::test_0016_constraints_and_indexes_exact` | exact DDL contract |
| `M15-MIG:04` | TEST | `tests/test_m15_migration.py::test_0016_downgrade_empty_succeeds` | empty downgrade |
| `M15-MIG:05` | TEST | `tests/test_m15_migration.py::test_0016_downgrade_any_m15_state_fails_before_ddl` | fail-closed authored state |
| `M15-MIG:06` | TEST | `tests/test_m15_migration.py::test_no_backfilled_tracking_or_compatibility_decisions` | no invented decisions |
| `M15-MIG:07` | TEST | `tests/test_m15_migration.py::test_foreign_key_check_clean` | FK integrity |
| `M15-MIG:08` | TEST | `tests/test_m15_migration.py::test_migration_roundtrip_leaves_no_temp_tables` | migration hygiene |
| `M15-MIG:09` | TEST | `tests/test_m15_migration.py::test_orm_migration_parity_exact_for_all_five_tables` | ORM/DDL parity |
| `M15-MIG:10` | TEST | `tests/test_m15_migration.py::test_0016_blob_fk_inventory_unchanged_from_m14` | no new Blob liveness path |

## M15-CAN

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-CAN:01` | TEST | `tests/test_m15_canonical.py::test_four_verdict_grammar_exact` | closed verdict vocabulary |
| `M15-CAN:02` | TEST | `tests/test_m15_canonical.py::test_dimension_status_grammar_exact` | closed dimension vocabulary |
| `M15-CAN:03` | TEST | `tests/test_m15_canonical.py::test_use_contract_canonical_ordering` | deterministic use hash |
| `M15-CAN:04` | TEST | `tests/test_m15_canonical.py::test_scope_hash_from_ordered_use_hashes` | scope identity |
| `M15-CAN:05` | TEST | `tests/test_m15_canonical.py::test_report_hash_from_normalized_children` | report identity |
| `M15-CAN:06` | TEST | `tests/test_m15_canonical.py::test_update_operation_hash_exact` | update audit identity |
| `M15-CAN:07` | TEST | `tests/test_m15_canonical.py::test_stored_assessment_corruption_fails_closed` | parent/child integrity |
| `M15-CAN:08` | PENDING | `tests/test_m15_canonical.py::test_stored_update_corruption_fails_closed` | operation integrity |
| `M15-CAN:09` | TEST | `tests/test_m15_canonical.py::test_feature_transition_set_change_changes_use_contract_hash` | A2 transition closure |
| `M15-CAN:10` | TEST | `tests/test_m15_canonical.py::test_spatial_transition_set_change_changes_use_contract_hash` | A4 transition closure |
| `M15-CAN:11` | TEST | `tests/test_m15_canonical.py::test_placement_contract_change_changes_use_contract_hash` | exact placement consumer |

## M15-EVAL

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-EVAL:01` | TEST | `tests/test_m15_evaluator.py::test_same_object_distinct_revision_required` | exact lineage law |
| `M15-EVAL:02` | TEST | `tests/test_m15_evaluator.py::test_changed_retained_blob_requires_review_without_equivalence_evidence` | no false AS_IS over changed bytes |
| `M15-EVAL:03` | TEST | `tests/test_m15_evaluator.py::test_media_type_change_requires_review` | media dimension |
| `M15-EVAL:04` | TEST | `tests/test_m15_evaluator.py::test_equal_spatial_interpretation_is_compatible` | spatial equality |
| `M15-EVAL:05` | TEST | `tests/test_m15_evaluator.py::test_exact_frame_bridge_yields_translation_verdict` | deterministic translator verdict |
| `M15-EVAL:06` | TEST | `tests/test_m15_evaluator.py::test_unsupported_frame_delta_requires_review` | no approximation |
| `M15-EVAL:07` | TEST | `tests/test_m15_evaluator.py::test_missing_required_target_interpretation_is_incompatible` | hard block |
| `M15-EVAL:08` | TEST | `tests/test_m15_evaluator.py::test_persistent_state_subject_identity_preserves_occurrence_contract` | state contract |
| `M15-EVAL:09` | TEST | `tests/test_m15_evaluator.py::test_verdict_precedence` | fold law |
| `M15-EVAL:10` | TEST | `tests/test_m15_evaluator.py::test_corrupt_revision_is_not_friendly_incompatibility` | corruption distinction |
| `M15-EVAL:11` | TEST | `tests/test_m15_evaluator.py::test_unimplemented_future_dimensions_not_claimed` | no speculative compatibility |
| `M15-EVAL:12` | TEST | `tests/test_m15_evaluator.py::test_completed_assessment_can_be_nonpass_verdict` | operational/domain separation |
| `M15-EVAL:13` | TEST | `tests/test_m15_evaluator.py::test_parent_summary_fold_exact_and_not_apply_gate` | assessment summary semantics |
| `M15-EVAL:14` | TEST | `tests/test_m15_evaluator.py::test_zero_current_uses_returns_no_current_uses_without_persistence` | empty-scope law |
| `M15-EVAL:15` | TEST | `tests/test_m15_evaluator.py::test_spatial_relevance_follows_resolved_placement_owner` | consumer-specific placement |
| `M15-EVAL:16` | TEST | `tests/test_m15_evaluator.py::test_manual_backward_same_lineage_assessment_is_directional` | rollback without identity loss |
| `M15-EVAL:17` | TEST | `tests/test_m15_evaluator.py::test_multiworld_or_ambiguous_placement_consumer_refuses_without_a6_fallback` | no hidden world/tie-break/fallback |
| `M15-EVAL:18` | TEST | `tests/test_m15_evaluator.py::test_emitted_a4_contract_requires_source_interpretation_and_exact_world_context` | predecessor A4 prerequisite is mechanical |
| `M15-EVAL:19` | TEST | `tests/test_m15_evaluator.py::test_semantically_equal_interpretations_are_satisfied_even_when_parent_hashes_differ` | semantic equality, not parent-pinned hash equality |
| `M15-EVAL:20` | TEST | `tests/test_m15_evaluator.py::test_evaluator_v1_distinct_legal_revisions_never_emit_auto_pass_verdict` | documented v1 retained-byte limitation |

## M15-TRANS

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-TRANS:01` | TEST | `tests/test_m15_translation.py::test_frame_bridge_schema_and_identity` | versioned translator |
| `M15-TRANS:02` | TEST | `tests/test_m15_translation.py::test_frame_bridge_integer_equivalence` | exact shared-subset semantics |
| `M15-TRANS:03` | TEST | `tests/test_m15_translation.py::test_rotation_outside_v1_refuses_translation` | bounded subset |
| `M15-TRANS:04` | TEST | `tests/test_m15_translation.py::test_translation_parameters_and_output_hash_persisted` | inspectable evidence |
| `M15-TRANS:05` | TEST | `tests/test_m15_translation.py::test_forged_translator_pin_fails_integrity` | anti-forgery |
| `M15-TRANS:06` | TEST | `tests/test_m15_translation.py::test_translation_never_mutates_source_or_target_revision` | authority isolation |
| `M15-TRANS:07` | TEST | `tests/test_m15_translation.py::test_translation_evidence_retained_when_overall_use_requires_review` | dimension controls pins |
| `M15-TRANS:08` | TEST | `tests/test_m15_translation.py::test_frame_bridge_only_applies_to_a4_consumer_and_mutates_no_authority` | applicability boundary |
| `M15-TRANS:09` | TEST | `tests/test_m15_translation.py::test_frame_bridge_overflow_refuses_without_wrap` | arithmetic safety |

## M15-IMPACT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-IMPACT:01` | PENDING | `tests/test_m15_impact.py::test_direct_working_uses_enumerated_exactly` | updateable use set |
| `M15-IMPACT:02` | PENDING | `tests/test_m15_impact.py::test_feature_contracts_enter_use_hash` | state dependency |
| `M15-IMPACT:03` | PENDING | `tests/test_m15_impact.py::test_spatial_contracts_enter_use_hash` | spatial dependency |
| `M15-IMPACT:04` | PENDING | `tests/test_m15_impact.py::test_published_composition_refs_are_advisory_only` | immutable published refs |
| `M15-IMPACT:05` | PENDING | `tests/test_m15_impact.py::test_current_shot_selections_are_advisory_and_unchanged` | no Shot pointer mutation |
| `M15-IMPACT:06` | PENDING | `tests/test_m15_impact.py::test_historical_shot_refs_are_advisory_only` | history isolation |
| `M15-IMPACT:07` | PENDING | `tests/test_m15_impact.py::test_advisory_count_drift_does_not_change_assessment_identity` | advisory distinction |
| `M15-IMPACT:08` | PENDING | `tests/test_m15_impact.py::test_nested_composition_sources_not_m15_update_targets` | scope boundary |

## M15-TRACK

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-TRACK:01` | PENDING | `tests/test_m15_tracking.py::test_absence_means_pinned_without_backfill` | default semantics |
| `M15-TRACK:02` | PENDING | `tests/test_m15_tracking.py::test_track_compatible_requires_explicit_opt_in` | explicit policy |
| `M15-TRACK:03` | PENDING | `tests/test_m15_tracking.py::test_tracking_offer_never_mutates_source` | no auto-follow |
| `M15-TRACK:04` | PENDING | `tests/test_m15_tracking.py::test_update_offer_resolves_concrete_revision_ids` | no stored latest |
| `M15-TRACK:05` | PENDING | `tests/test_m15_tracking.py::test_tracking_policy_cas` | current policy race safety |
| `M15-TRACK:06` | PENDING | `tests/test_m15_tracking.py::test_policy_version_never_aba_after_authored_cycle` | monotonic authored policy |
| `M15-TRACK:07` | PENDING | `tests/test_m15_tracking.py::test_terminated_tracked_occurrence_is_inert_and_not_offered` | occurrence lifecycle |
| `M15-TRACK:08` | PENDING | `tests/test_m15_tracking.py::test_discovery_returns_concrete_newer_candidates_and_creates_no_assessment` | no hidden latest/implicit assess |

## M15-APPLY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-APPLY:01` | PENDING | `tests/test_m15_apply.py::test_compatible_as_is_updates_selected_working_source_only` | core apply |
| `M15-APPLY:02` | PENDING | `tests/test_m15_apply.py::test_translation_verdict_pins_exact_translator` | translation apply evidence |
| `M15-APPLY:03` | PENDING | `tests/test_m15_apply.py::test_review_requires_explicit_acceptance` | review gate |
| `M15-APPLY:04` | PENDING | `tests/test_m15_apply.py::test_incompatible_cannot_be_forced` | hard block |
| `M15-APPLY:05` | PENDING | `tests/test_m15_apply.py::test_each_composition_working_version_increments_once` | version law |
| `M15-APPLY:06` | PENDING | `tests/test_m15_apply.py::test_occurrence_identity_unchanged` | APR-103 |
| `M15-APPLY:07` | PENDING | `tests/test_m15_apply.py::test_instance_feature_and_subject_rows_unchanged` | persistent state |
| `M15-APPLY:08` | PENDING | `tests/test_m15_apply.py::test_instance_spatial_rows_unchanged` | spatial subject |
| `M15-APPLY:09` | PENDING | `tests/test_m15_apply.py::test_stale_use_contract_rolls_back_all` | fenced apply |
| `M15-APPLY:10` | PENDING | `tests/test_m15_apply.py::test_exact_retry_is_idempotent` | duplicate apply |
| `M15-APPLY:11` | PENDING | `tests/test_m15_apply.py::test_partial_apply_stales_remaining_same_composition_uses` | partial semantics |
| `M15-APPLY:12` | PENDING | `tests/test_m15_apply.py::test_direct_patch_source_swap_cannot_bypass_compatibility` | bypass closure |
| `M15-APPLY:13` | PENDING | `tests/test_m15_apply.py::test_parent_incompatible_summary_does_not_block_selected_compatible_use` | per-use authority |
| `M15-APPLY:14` | PENDING | `tests/test_m15_apply.py::test_update_operation_fk_pins_exact_assessment_report_hash` | report pin backstop |
| `M15-APPLY:15` | PENDING | `tests/test_m15_scope.py::test_all_direct_production_revision_source_mutation_paths_are_gated` | no backdoor source swap |
| `M15-APPLY:16` | PENDING | `tests/test_m15_apply.py::test_partial_apply_response_lists_stale_remaining_uses` | explicit continuation semantics |

## M15-RACE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-RACE:01` | PENDING | `tests/test_m15_races.py::test_assessment_vs_working_edit_no_hybrid` | coherent assess |
| `M15-RACE:02` | PENDING | `tests/test_m15_races.py::test_three_identical_assessments_converge` | assessment convergence |
| `M15-RACE:03` | PENDING | `tests/test_m15_races.py::test_apply_vs_working_edit_refuses_atomically` | stale version |
| `M15-RACE:04` | PENDING | `tests/test_m15_races.py::test_apply_vs_feature_contract_edit_refuses` | non-working-version dependency |
| `M15-RACE:05` | PENDING | `tests/test_m15_races.py::test_duplicate_apply_cannot_double_increment` | apply convergence |
| `M15-RACE:06` | PENDING | `tests/test_m15_races.py::test_apply_vs_spatial_transition_edit_refuses` | non-working-version spatial dependency |
| `M15-RACE:07` | PENDING | `tests/test_m15_races.py::test_tracking_policy_aba_is_rejected` | CAS generation safety |

## M15-HIST

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-HIST:01` | PENDING | `tests/test_m15_history.py::test_old_composition_revision_byte_identical_after_update` | published history |
| `M15-HIST:02` | PENDING | `tests/test_m15_history.py::test_old_binding_byte_identical_after_update` | binding history |
| `M15-HIST:03` | PENDING | `tests/test_m15_history.py::test_old_shot_revision_byte_identical_after_update` | Shot history |
| `M15-HIST:04` | PENDING | `tests/test_m15_history.py::test_current_shot_selection_unchanged_by_update` | current pinned Shot |
| `M15-HIST:05` | PENDING | `tests/test_m15_history.py::test_future_publish_and_binding_pin_target_revision` | future world |
| `M15-HIST:06` | PENDING | `tests/test_m15_history.py::test_future_shot_captures_target_revision` | future Shot |
| `M15-HIST:07` | PENDING | `tests/test_m15_history.py::test_exact_rerun_old_shot_uses_source_with_m15_current_resolvers_poisoned` | captured-only history |
| `M15-HIST:08` | PENDING | `tests/test_m15_history.py::test_compatibility_translation_never_rewrites_historical_source_bytes` | APR-099/104 |
| `M15-HIST:09` | PENDING | `tests/test_m15_history.py::test_chair_07_fallen_state_survives_r2_to_r3_update` | headline continuity |
| `M15-HIST:10` | PENDING | `tests/test_m15_history.py::test_old_exact_rerun_ignores_all_m15_evidence_and_tracking` | M15 not historical dependency |

## M15-REC

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-REC:01` | PENDING | `tests/test_m15_recovery.py::test_0016_backup_restore_preserves_m15_rows_and_hashes` | head-0016 liveness |
| `M15-REC:02` | PENDING | `tests/test_m15_recovery.py::test_0015_backup_restores_without_inventing_m15_state` | predecessor restore |
| `M15-REC:03` | PENDING | `tests/test_m15_recovery.py::test_corrupt_restored_assessment_fails_integrity` | recovery corruption |
| `M15-REC:04` | PENDING | `tests/test_m15_recovery.py::test_unsupported_future_restore_head_fails_closed` | future-head refusal |

## M15-UI

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-UI:01` | PENDING | `apps/web/src/__tests__/m15-update-summary.test.tsx::shows exact four-verdict impact groups` | impact UX |
| `M15-UI:02` | PENDING | `apps/web/src/__tests__/m15-update-summary.test.tsx::requires explicit review acceptance and disables incompatible uses` | review/block UX |
| `M15-UI:03` | PENDING | `apps/web/src/__tests__/m15-tracking.test.tsx::pinned_and_track_compatible_modes_are_explicit` | tracking UX |
| `M15-UI:04` | PENDING | `apps/web/src/__tests__/m15-history-message.test.tsx::states_current_only_and_history_unchanged` | history message |
| `M15-UI:05` | PENDING | `tests/test_m15_api.py::test_http_surface_uses_backend_verdict_trace_not_frontend_reinterpretation` | one authority interpretation |
| `M15-UI:06` | PENDING | `apps/web/src/__tests__/m15-update-summary.test.tsx::compatibility_does_not_claim_geometric_fit_or_visual_identity` | product-honesty boundary |

## M15-SCALE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M15-SCALE:01` | PENDING | `tests/test_m15_scale.py::test_10_100_1000_impact_uses_bounded_query_classes` | bounded SQL |
| `M15-SCALE:02` | PENDING | `tests/test_m15_scale.py::test_no_per_occurrence_feature_select_loop` | feature batching |
| `M15-SCALE:03` | PENDING | `tests/test_m15_scale.py::test_no_per_occurrence_spatial_select_loop` | spatial batching |
| `M15-SCALE:04` | PENDING | `tests/test_m15_scale.py::test_historical_diagnostic_counts_are_batched` | history batching |
| `M15-SCALE:05` | PENDING | `tests/test_m15_scale.py::test_scale_evidence_records_cpu_memory_bytes` | evidence |
| `M15-SCALE:06` | PENDING | `tests/test_m15_scale.py::test_scale_run_leaves_zero_repository_residue` | hygiene |
| `M15-SCALE:07` | PENDING | `tests/test_m15_scale.py::test_assessment_scale_records_writer_fence_duration` | SQLite contention evidence |
