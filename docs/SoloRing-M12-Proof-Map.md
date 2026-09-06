# SoloRing M12 Proof Map

Frozen R3 §21: the machine-checkable M12 proof inventory (123 cells).
Validated by `python scripts/m12_validate_proof_map.py` (Backend CI, before tests).

## M12-ID

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-ID:01` | TEST | `tests/test_m12_identity.py::test_occurrence_id_is_fresh_uuid_not_source_or_name` | Minted occurrence identity is independent from source revision and display metadata. |
| `M12-ID:02` | TEST | `tests/test_m12_identity.py::test_two_occurrences_of_same_revision_receive_distinct_ids` | The same Production Revision can appear twice as distinct physical occurrences. |
| `M12-ID:03` | TEST | `tests/test_m12_identity.py::test_display_name_change_preserves_occurrence_id` | Display metadata never changes occurrence identity. |
| `M12-ID:04` | TEST | `tests/test_m12_identity.py::test_transform_change_preserves_occurrence_id` | Composition-local transform edits preserve occurrence identity. |
| `M12-ID:05` | TEST | `tests/test_m12_identity.py::test_visibility_change_preserves_occurrence_id` | Visibility edits preserve occurrence identity. |
| `M12-ID:06` | TEST | `tests/test_m12_identity.py::test_same_production_object_revision_update_preserves_occurrence_id` | Same Production Object revision evolution preserves identity. |
| `M12-ID:07` | TEST | `tests/test_m12_identity.py::test_same_nested_composition_revision_update_preserves_occurrence_id` | Same nested Composition lineage revision evolution preserves identity. |
## M12-WORK

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-WORK:01` | TEST | `tests/test_m12_working.py::test_create_composition_requires_active_project_inside_writer_fence` | Composition creation cannot race an owning-Project soft delete. |
| `M12-WORK:02` | TEST | `tests/test_m12_working.py::test_mint_records_birth_operation_and_working_membership_atomically` | Mint produces identity, lineage birth, and working membership atomically. |
| `M12-WORK:03` | TEST | `tests/test_m12_working.py::test_working_mutation_requires_exact_expected_version` | Every assembly working mutation is optimistic-version fenced. |
| `M12-WORK:04` | TEST | `tests/test_m12_working.py::test_successful_working_mutation_increments_version_once` | One successful assembly mutation increments working_version exactly once. |
| `M12-WORK:05` | TEST | `tests/test_m12_working.py::test_stale_working_version_writes_nothing` | Stale edits fail with zero partial writes. |
| `M12-WORK:06` | TEST | `tests/test_m12_working.py::test_cross_project_source_is_rejected` | Working source must belong to the Composition Project. |
| `M12-WORK:07` | TEST | `tests/test_m12_working.py::test_same_lineage_self_nested_revision_is_rejected` | A Composition cannot directly nest its own lineage. |
| `M12-WORK:08` | TEST | `tests/test_m12_working.py::test_terminated_occurrence_cannot_return_to_working_state` | Terminated occurrence identity cannot be silently resurrected. |
| `M12-WORK:09` | TEST | `tests/test_m12_working.py::test_metadata_patch_uses_metadata_version_without_advancing_working_version` | Composition metadata has an independent optimistic concurrency domain. |
| `M12-WORK:10` | TEST | `tests/test_m12_working.py::test_stale_metadata_version_writes_nothing` | Stale metadata PATCH cannot overwrite newer metadata. |
## M12-PUB

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-PUB:01` | TEST | `tests/test_m12_publication.py::test_publish_one_occurrence_pins_exact_source_and_dependency` | Published snapshot pins exact direct Production Revision and closure. |
| `M12-PUB:02` | TEST | `tests/test_m12_publication.py::test_publish_occurrence_order_is_canonical_by_id` | Array/list order cannot influence identity. |
| `M12-PUB:03` | TEST | `tests/test_m12_publication.py::test_publish_fixture_bytes_hash_and_permutation_invariance_are_exact` | The 403-byte schema-1 golden fixture/hash is exact under adversarial input ordering. |
| `M12-PUB:04` | TEST | `tests/test_m12_publication.py::test_publish_unchanged_working_state_converges` | Unchanged state returns same revision and created=false (content-addressed, incl. edit-revert). |
| `M12-PUB:05` | TEST | `tests/test_m12_publication.py::test_publish_changed_working_state_creates_next_revision` | Changed semantic state creates next immutable revision. |
| `M12-PUB:06` | TEST | `tests/test_m12_publication.py::test_publish_preserves_surviving_occurrence_ids` | Publication copies surviving occurrence IDs exactly. |
| `M12-PUB:07` | TEST | `tests/test_m12_publication.py::test_publish_does_not_write_occurrence_identity_or_lineage` | Publish is identity-neutral. |
| `M12-PUB:08` | TEST | `tests/test_m12_publication.py::test_publish_does_not_change_metadata_or_working_versions` | Publication mutates neither authoring concurrency token. |
| `M12-PUB:09` | TEST | `tests/test_m12_publication.py::test_publish_rejects_empty_composition` | Empty working assembly does not publish. |
| `M12-PUB:10` | TEST | `tests/test_m12_publication.py::test_publish_rejects_stale_expected_working_version` | Stale preview cannot publish after current edits. |
| `M12-PUB:11` | TEST | `tests/test_m12_publication.py::test_existing_winner_projection_corruption_fails_closed` | Converged historical winner is fully revalidated. |
| `M12-PUB:12` | TEST | `tests/test_m12_publication.py::test_published_revision_rows_have_no_update_delete_path` | Published revision/projection tables are immutable authority. |
## M12-NEST

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-NEST:01` | TEST | `tests/test_m12_nested.py::test_nested_revision_is_pinned_exactly_not_latest` | Parent revision never tracks mutable/latest nested state. |
| `M12-NEST:02` | TEST | `tests/test_m12_nested.py::test_nested_closure_flattens_transitive_production_dependencies` | Parent closure includes nested leaf Production Revisions. |
| `M12-NEST:03` | TEST | `tests/test_m12_nested.py::test_nested_closure_flattens_transitive_composition_dependencies` | Parent closure includes all exact nested Composition Revisions. |
| `M12-NEST:04` | TEST | `tests/test_m12_nested.py::test_nested_dependency_duplicates_coalesce_deterministically` | Repeated dependency identity appears once in canonical closure. |
| `M12-NEST:05` | TEST | `tests/test_m12_nested.py::test_later_nested_publication_does_not_change_parent_history` | Historical parent snapshot is isolated from nested evolution. |
| `M12-NEST:06` | TEST | `tests/test_m12_nested.py::test_nested_projection_corruption_fails_internal_invariant` | Malformed nested immutable closure is corruption, not a readiness guess. |
| `M12-NEST:07` | TEST | `tests/test_m12_nested.py::test_transitive_same_composition_lineage_embedding_is_rejected` | Parent cannot transitively contain an older revision from its own Composition lineage. |
| `M12-NEST:08` | TEST | `tests/test_m12_nested.py::test_self_consistent_dependency_omission_fails_independent_rederivation` | Snapshot + normalized closure cannot collude to omit a required dependency. |
## M12-LINEAGE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-LINEAGE:01` | TEST | `tests/test_m12_lineage.py::test_remove_terminates_source_with_zero_target` | Remove has one terminating source and zero targets. |
| `M12-LINEAGE:02` | TEST | `tests/test_m12_lineage.py::test_replace_as_new_terminates_old_and_mints_one_new` | Replace-as-new records old-new lineage and new identity. |
| `M12-LINEAGE:03` | TEST | `tests/test_m12_lineage.py::test_split_terminates_one_and_mints_multiple_targets` | Split cardinality and lineage are explicit. |
| `M12-LINEAGE:04` | TEST | `tests/test_m12_lineage.py::test_merge_terminates_multiple_and_mints_one_target` | Merge cardinality and lineage are explicit. |
| `M12-LINEAGE:05` | TEST | `tests/test_m12_lineage.py::test_fork_preserves_source_and_mints_one_target` | Fork source remains active while child identity is distinct. |
| `M12-LINEAGE:06` | TEST | `tests/test_m12_lineage.py::test_identity_can_terminate_at_most_once` | DB/service contract prevents double termination. |
| `M12-LINEAGE:07` | TEST | `tests/test_m12_lineage.py::test_every_occurrence_has_exactly_one_birth_target` | Every stable occurrence has one lineage birth event. |
| `M12-LINEAGE:08` | TEST | `tests/test_m12_lineage.py::test_identity_operation_json_hash_matches_normalized_edges` | Canonical lineage evidence equals normalized source/target edge IDs. |
| `M12-LINEAGE:09` | TEST | `tests/test_m12_lineage.py::test_identity_operation_never_retargets_historical_revision_membership` | History retains old occurrence IDs after identity transformation. |
| `M12-LINEAGE:10` | TEST | `tests/test_m12_lineage.py::test_request_fingerprint_binds_kind_sources_and_complete_target_specs` | Preview token mechanically binds exact normalized operation intent. |
| `M12-LINEAGE:11` | TEST | `tests/test_m12_lineage.py::test_identity_targets_use_same_validator_as_mint` | Identity operations cannot bypass source/project/XOR/nesting/transform validation. |
| `M12-LINEAGE:12` | TEST | `tests/test_m12_lineage.py::test_terminated_occurrence_cannot_be_future_operation_source` | Post-termination source use is impossible. |
| `M12-LINEAGE:13` | TEST | `tests/test_m12_lineage.py::test_duplicate_identity_operation_version_interval_is_rejected` | Only one identity operation can own a working-version transition. |
| `M12-LINEAGE:14` | TEST | `tests/test_m12_lineage.py::test_active_source_may_fork_multiple_times_without_termination` | Fork multiplicity is explicit and non-terminating. |
## M12-SCOPE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-SCOPE:01` | TEST | `tests/test_m12_scope.py::test_occurrence_patch_requires_composition_working_scope` | Consequential edits have no implicit scope. |
| `M12-SCOPE:02` | TEST | `tests/test_m12_scope.py::test_shot_local_scope_is_rejected_not_promoted` | Shot-local intent cannot silently mutate reusable Composition state. |
| `M12-SCOPE:03` | TEST | `tests/test_m12_scope.py::test_unknown_scope_is_rejected` | Future/unknown scope strings do not coerce. |
| `M12-SCOPE:04` | TEST | `tests/test_m12_scope.py::test_source_lineage_change_requires_replace_as_new` | Cross-lineage source change cannot masquerade as same-occurrence update. |
| `M12-SCOPE:05` | TEST | `tests/test_m12_scope.py::test_no_generic_occurrence_delete_route_or_service` | Removal must go through lineage-bearing identity operation. |
| `M12-SCOPE:06` | TEST | `tests/test_m12_scope.py::test_no_arbitrary_property_override_storage` | M12 override vocabulary remains typed and closed. |
## M12-HISTORY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-HISTORY:01` | TEST | `tests/test_m12_history.py::test_old_revision_ignores_current_working_edits` | Historical revision read never consults current working state. |
| `M12-HISTORY:02` | TEST | `tests/test_m12_history.py::test_old_revision_ignores_composition_display_metadata_changes` | Composition metadata does not rewrite historical snapshot. |
| `M12-HISTORY:03` | TEST | `tests/test_m12_history.py::test_old_revision_keeps_occurrence_after_later_remove` | Later termination does not erase old revision membership. |
| `M12-HISTORY:04` | TEST | `tests/test_m12_history.py::test_old_revision_keeps_exact_old_source_after_update` | Later source revision update cannot reinterpret history. |
| `M12-HISTORY:05` | TEST | `tests/test_m12_history.py::test_revision_reader_crosschecks_snapshot_and_occurrence_projection` | Canonical snapshot and normalized child rows must agree. |
| `M12-HISTORY:06` | TEST | `tests/test_m12_history.py::test_revision_reader_rederives_dependency_closure_independently` | Historical reader derives closure from direct immutable sources. |
## M12-MIG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-MIG:01` | TEST | `tests/test_m12_migration.py::test_0013_upgrade_adds_exact_ten_tables_without_predecessor_rebuild` | Migration is exact additive scope. |
| `M12-MIG:02` | TEST | `tests/test_m12_migration.py::test_0013_orm_metadata_matches_upgraded_schema_and_resolved_names` | ORM/Alembic structure and deterministic constraint/index names align exactly. |
| `M12-MIG:03` | TEST | `tests/test_m12_migration.py::test_0013_downgrade_empty_schema_succeeds_exactly_to_0012` | Unused M12 schema downgrades with no residual M12 schema state. |
| `M12-MIG:04` | TEST | `tests/test_m12_migration.py::test_0013_downgrade_refuses_any_authored_m12_row` | No M12 authored/history state is destroyed by downgrade. |
| `M12-MIG:05` | TEST | `tests/test_m12_migration.py::test_0013_upgrade_does_not_backfill_invented_compositions` | Migration invents no reusable assemblies or occurrence identities. |
| `M12-MIG:06` | TEST | `tests/test_m12_migration.py::test_migration_head_is_exactly_0013` | Current migration head advances exactly once. |
| `M12-MIG:07` | TEST | `tests/test_m12_migration.py::test_0012_predecessor_database_upgrades_cleanly_to_0013` | Published M11 database is a valid predecessor. |
| `M12-MIG:08` | TEST | `tests/test_m12_migration.py::test_composite_occurrence_fks_reject_cross_composition_rows` | Database-level lineage coherence rejects cross-Composition child references. |
| `M12-MIG:09` | TEST | `tests/test_m12_migration.py::test_nonempty_identity_history_without_revision_blocks_downgrade` | Identity authorship alone is durable state and blocks downgrade. |
## M12-RECOVERY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-RECOVERY:01` | TEST | `tests/test_m12_recovery.py::test_current_backup_requires_0013_head` | M12 backup creation certifies only the current 0013 head. |
| `M12-RECOVERY:02` | TEST | `tests/test_m12_recovery.py::test_0013_blob_fk_inventory_remains_exactly_seven_paths` | M12 adds no hidden durable Blob-reference path. |
| `M12-RECOVERY:03` | TEST | `tests/test_m12_recovery.py::test_restore_0011_uses_frozen_six_path_policy_and_invents_no_m12` | Historical pre-M11 restore remains exact. |
| `M12-RECOVERY:04` | TEST | `tests/test_m12_recovery.py::test_restore_0012_uses_seven_path_policy_and_invents_no_m12` | Historical M11 restore remains exact with no empty M12 state invention. |
| `M12-RECOVERY:05` | TEST | `tests/test_m12_recovery.py::test_restore_0013_verifies_composition_snapshots_and_projections` | Current restore validates M12 immutable revision state. |
| `M12-RECOVERY:06` | TEST | `tests/test_m12_recovery.py::test_restore_0013_verifies_identity_operation_lineage` | Current restore validates birth/termination/operation evidence. |
| `M12-RECOVERY:07` | TEST | `tests/test_m12_recovery.py::test_restore_0013_rejects_terminated_occurrence_in_working_state` | Impossible active-working/terminated identity combination fails closed. |
| `M12-RECOVERY:08` | TEST | `tests/test_m12_recovery.py::test_restore_unknown_head_fails_closed` | Recovery dispatch remains closed to supported historical heads. |
| `M12-RECOVERY:09` | TEST | `tests/test_m12_recovery.py::test_recovery_never_repairs_or_retargets_occurrence_identity` | Recovery is verify-only for M12 identity/history. |
| `M12-RECOVERY:10` | TEST | `tests/test_m12_recovery.py::test_restore_rejects_self_consistent_dependency_omission_by_rederivation` | Recovery does not trust snapshot-projection agreement without semantic closure derivation. |
| `M12-RECOVERY:11` | TEST | `tests/test_m12_recovery.py::test_restore_rejects_noncanonical_transform_or_invalid_lineage_timeline` | Recovery validates transform canonicality and full temporal lineage rules. |
## M12-API

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-API:01` | TEST | `tests/test_m12_api.py::test_api_create_list_detail_composition` | Composition metadata/current summary API is wired and project-scoped. |
| `M12-API:02` | TEST | `tests/test_m12_api.py::test_api_mint_and_patch_occurrence_returns_stable_id_and_version` | Working occurrence API exposes durable identity/version semantics. |
| `M12-API:03` | TEST | `tests/test_m12_api.py::test_api_identity_preview_then_apply_requires_request_and_impact_fingerprints` | Identity changes are exact-request and impact fenced. |
| `M12-API:04` | TEST | `tests/test_m12_api.py::test_api_publish_returns_201_created_and_200_converged` | Publication HTTP contract exposes semantic convergence. |
| `M12-API:05` | TEST | `tests/test_m12_api.py::test_api_revision_detail_exposes_exact_occurrence_and_dependency_identity` | Historical API exposes exact published identities, not current names/paths. |
| `M12-API:06` | TEST | `tests/test_m12_api.py::test_api_has_no_occurrence_delete_endpoint` | HTTP surface cannot bypass lineage-bearing removal. |
| `M12-API:07` | TEST | `tests/test_m12_api.py::test_api_list_endpoints_use_stable_cursor_pagination` | Composition/occurrence/revision/history list contracts are bounded and stable. |
| `M12-API:08` | TEST | `tests/test_m12_api.py::test_metadata_patch_requires_metadata_version_and_does_not_advance_working_version` | HTTP metadata concurrency is independent from assembly concurrency. |
## M12-UI

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-UI:01` | TEST | `apps/web/src/__tests__/world-set-workspace.test.tsx::same occurrence survives revision publication` | UI shows the same occurrence across two published revisions. |
| `M12-UI:02` | TEST | `apps/web/src/__tests__/world-set-scope.test.tsx::consequential edit displays reusable set scope` | UI surfaces reusable-Composition edit scope before mutation. |
| `M12-UI:03` | TEST | `apps/web/src/__tests__/world-set-identity.test.tsx::update source and replace as new are distinct actions` | UI distinguishes same-occurrence source update from new identity. |
| `M12-UI:04` | TEST | `apps/web/src/__tests__/world-set-lineage.test.tsx::identity history renders old to new without retargeting` | UI can inspect lineage operations and stable IDs. |
| `M12-UI:05` | TEST | `apps/web/src/__tests__/world-set-nesting.test.tsx::nested internal occurrences require context switch` | Parent UI does not expose nested internals as parent-authority editable occurrences. |
| `M12-UI:06` | TEST | `apps/web/src/__tests__/world-set-compatibility.test.tsx::same lineage update warns identity preserved not physical compatibility` | UI does not misrepresent identity preservation as compatibility certification. |
## M12-RACE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-RACE:01` | TEST | `tests/test_m12_races.py::test_two_same_version_edits_only_one_commits` | Concurrent assembly edits serialize through genuine writer fence/version check. |
| `M12-RACE:02` | TEST | `tests/test_m12_races.py::test_edit_before_publish_fence_causes_publish_conflict` | Publish cannot commit a stale pre-edit snapshot. |
| `M12-RACE:03` | TEST | `tests/test_m12_races.py::test_publish_before_edit_fence_publishes_exact_then_edit_advances_working` | Lock order yields coherent before/after states. |
| `M12-RACE:04` | TEST | `tests/test_m12_races.py::test_two_identical_concurrent_publishes_converge` | Concurrent publish race creates one semantic winner. |
| `M12-RACE:05` | TEST | `tests/test_m12_races.py::test_apply_rejects_stale_request_or_live_impact_after_intervening_change` | Preview cannot be replayed after decision-relevant request/impact state changes. |
| `M12-RACE:06` | TEST | `tests/test_m12_races.py::test_intervening_publish_does_not_stale_identity_impact_by_historical_count_only` | Publication alone cannot create a false identity-operation conflict. |
| `M12-RACE:07` | TEST | `tests/test_m12_races.py::test_metadata_patch_and_working_edit_use_independent_tokens` | Metadata and assembly optimistic concurrency domains do not spuriously invalidate each other. |
| `M12-RACE:08` | STRUCTURAL | `scripts/m12_validate_proof_map.py::validate_race_proof_no_shortcuts` | STRUCTURAL: race proofs use parked real writer locks plus deterministic events and contain no timing-sleep or transaction-acquisition-mock shortcut. |
## M12-SCALE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-SCALE:01` | TEST | `tests/test_m12_scale.py::test_scale_working_occurrence_listing_is_bounded_queries` | Occurrence listing does not N+1. |
| `M12-SCALE:02` | TEST | `tests/test_m12_scale.py::test_scale_publication_readiness_source_validation_is_set_oriented` | Readiness does not query once per occurrence. |
| `M12-SCALE:03` | TEST | `tests/test_m12_scale.py::test_scale_nested_closure_uses_normalized_dependency_sets` | Wide nested closure avoids recursive current-state N+1 traversal. |
| `M12-SCALE:04` | TEST | `tests/test_m12_scale.py::test_scale_identity_impact_resolution_is_set_oriented` | Impact diagnostics scale by rows, not round trips per source. |
| `M12-SCALE:05` | TEST | `tests/test_m12_scale.py::test_scale_revision_detail_load_is_bounded_queries` | Historical detail loads occurrences/dependencies with bounded query count. |
| `M12-SCALE:06` | TEST | `tests/test_m12_scale.py::test_scale_composition_listing_is_bounded_queries` | Listing 2,000 Compositions performs no per-Composition query pattern. |
| `M12-SCALE:07` | TEST | `tests/test_m12_scale.py::test_scale_deep_nested_chain_uses_frozen_closure_without_recursive_current_state_walk` | Depth-32 chain exercises accepted flattened-closure growth without N+1 current-state traversal. |
## M12-BOUNDARY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-BOUNDARY:01` | TEST | `tests/test_m12_boundary.py::test_m12_has_no_writes_to_production_revision_authority` | A6 cannot mutate A5 published production authority. |
| `M12-BOUNDARY:02` | TEST | `tests/test_m12_boundary.py::test_m12_has_no_writes_to_spatial_continuity_authority` | M12 does not duplicate or supersede A4. |
| `M12-BOUNDARY:03` | TEST | `tests/test_m12_boundary.py::test_m12_has_no_writes_to_continuity_or_shot_capture` | M12 does not pre-implement M13 history/state integration. |
| `M12-BOUNDARY:04` | TEST | `tests/test_m12_boundary.py::test_m12_has_no_generation_executor_or_render_source_delta` | M12 is not an execution milestone. |
| `M12-BOUNDARY:05` | TEST | `tests/test_m12_boundary.py::test_m12_occurrence_fk_consumer_inventory_is_exhaustive` | Every relational FK to stable occurrence identity has registered impact semantics. |
| `M12-BOUNDARY:06` | TEST | `tests/test_m12_boundary.py::test_m12_normative_external_name_scan_is_clean` | Repository-facing M12 docs/source comments contain no external research/product names. |
| `M12-BOUNDARY:07` | TEST | `tests/test_m12_boundary.py::test_no_unregistered_non_fk_durable_occurrence_consumer_contract` | A future authoritative non-FK occurrence reference cannot silently bypass impact registration. |
## M12-PROOF

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M12-PROOF:01` | TEST | `tests/test_m12_proof_map_validator.py::test_m12_proof_map_has_exactly_122_unique_cells` | Proof-map cardinality and IDs are frozen. |
| `M12-PROOF:02` | TEST | `tests/test_m12_proof_map_validator.py::test_m12_proof_map_all_test_owners_collect` | Every TEST owner resolves in pytest/frontend ownership validation. |
| `M12-PROOF:03` | TEST | `tests/test_m12_proof_map_validator.py::test_m12_proof_map_structural_owners_resolve` | Every STRUCTURAL owner/path/claim resolves. |
| `M12-PROOF:04` | TEST | `tests/test_m12_proof_map_validator.py::test_m12_proof_map_validator_is_run_in_backend_ci_before_pytest` | CI validates the binding proof map before backend suite execution. |

## Closure commands

| Command | Exact invocation | Evidence owner |
|---|---|---|
| CMD:proof-maps | `python scripts/m10f_validate_proof_map.py` + `m11` + `m12` validators | CI + M12-PROOF:04 |
| CMD:backend-x2 | `python -m pytest -q` (two consecutive passes) | closure record |
| CMD:compileall | `python -m compileall server scripts tests` | closure record |
| CMD:frontend | `npm ci` + `npm test` + `npx tsc --noEmit` + `npm run build` in `apps/web` | closure record |
| CMD:migration-gate | 0012-to-0013 upgrade / empty downgrade / nonempty refusal / restore dispatch | M12-MIG + M12-RECOVERY |
| CMD:external-scan | external research/product-name hygiene scan | M12-BOUNDARY:06 |
