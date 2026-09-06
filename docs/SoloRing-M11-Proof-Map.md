# SoloRing M11 Proof Map

Frozen R3 plan §20: the machine-checkable M11 proof inventory. Row grammar:
`| <DOMAIN>:<id> | <disposition> | <exact owner> | <note> |` with the closed
disposition vocabulary TEST / STRUCTURAL / INHERITED / NOT-APPLICABLE-SOURCE-FIT.
Validated by `python scripts/m11_validate_proof_map.py` (Backend CI, before tests).

## M11-ID

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-ID:01` | TEST | `tests/test_m11_production_canonical.py::test_duplicate_object_names_have_distinct_uuid_identity` | Name is not Production Object identity. |
| `M11-ID:02` | TEST | `tests/test_m11_production_canonical.py::test_same_blob_on_two_objects_produces_distinct_revision_ids` | Blob identity does not collapse Production Objects/Revisions. |
| `M11-ID:03` | TEST | `tests/test_m11_production_canonical.py::test_schema1_hash_excludes_source_and_display_provenance` | Asset ID/name/path/filename/object display metadata excluded from canonical identity. |
| `M11-ID:04` | TEST | `tests/test_m11_production_canonical.py::test_schema1_exact_utf8_fixture` | Exact schema-1 bytes pinned (200 bytes, frozen SHA-256). |
| `M11-ID:05` | TEST | `tests/test_m11_production_canonical.py::test_schema1_reordered_input_dict_is_byte_identical` | Existing canonical serializer order independence. |
| `M11-ID:06` | TEST | `tests/test_m11_production_canonical.py::test_schema1_null_media_type_is_explicit` | Null is explicit canonical state. |
| `M11-ID:07` | TEST | `tests/test_m11_production_canonical.py::test_different_blob_or_interpretation_changes_snapshot_hash` | Consumption-semantic change changes hash. |
## M11-PUB

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-PUB:01` | TEST | `tests/test_m11_publication.py::test_publish_reference_asset_creates_immutable_revision_and_closure` | Happy publication. |
| `M11-PUB:02` | TEST | `tests/test_m11_publication.py::test_publish_output_asset_preserves_asset_provenance_kind` | Generated/output provenance is not rewritten or re-parented. |
| `M11-PUB:03` | TEST | `tests/test_m11_publication.py::test_cross_project_source_is_not_ready_and_publish_is_blocked` | Preview SOURCE_PROJECT_MISMATCH; Publish 409 NOT_READY, no competing top-level code. |
| `M11-PUB:04` | TEST | `tests/test_m11_publication.py::test_missing_or_malformed_source_asset_is_not_found` | Missing/malformed Asset identity uses the existing Asset lookup contract. |
| `M11-PUB:05` | TEST | `tests/test_m11_publication.py::test_zero_byte_registered_blob_is_not_publishable` | M11 declared consumer rejects empty payload. |
| `M11-PUB:06` | TEST | `tests/test_m11_publication.py::test_missing_physical_blob_is_corruption_not_readiness` | Missing registered bytes fail as corruption. |
| `M11-PUB:07` | TEST | `tests/test_m11_publication.py::test_corrupt_physical_blob_is_corruption` | Hash mismatch fails closed. |
| `M11-PUB:08` | TEST | `tests/test_m11_publication.py::test_blob_size_mismatch_is_corruption` | Captured size is exact. |
| `M11-PUB:09` | TEST | `tests/test_m11_publication.py::test_readiness_preview_and_publish_use_same_canonical_builder` | Preview/publish canonical parity. |
| `M11-PUB:10` | TEST | `tests/test_m11_publication.py::test_object_metadata_patch_cannot_change_published_revision` | Mutable display metadata cannot reinterpret history. |
| `M11-PUB:11` | TEST | `tests/test_m11_publication.py::test_publish_creates_no_current_or_approved_revision_pointer` | M15 lifecycle not smuggled into M11. |
| `M11-PUB:12` | TEST | `tests/test_m11_publication.py::test_unpublishable_registered_media_type_is_readiness_not_corruption` | Legal predecessor metadata outside the M11 closure grammar yields SOURCE_MEDIA_TYPE_INVALID, no invariant error. |
| `M11-PUB:13` | TEST | `tests/test_m11_publication.py::test_publish_never_reaches_closure_check_for_invalid_media_type` | Readiness classification precedes INSERT; closure CHECK is defense in depth. |
| `M11-PUB:14` | TEST | `tests/test_m11_publication.py::test_publish_recomputes_physical_readiness_and_does_not_trust_preview` | Publish performs a fresh physical verification in the Publish call. |
| `M11-PUB:15` | TEST | `tests/test_m11_publication.py::test_untrimmed_media_type_is_not_normalized_into_publishable_closure` | Invalid registered interpretation metadata is not silently transformed. |
| `M11-PUB:16` | TEST | `tests/test_m11_publication.py::test_not_ready_publish_returns_complete_readiness_result` | Publish reports the complete deterministic blocker set. |
## M11-PROV

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-PROV:01` | TEST | `tests/test_m11_publication.py::test_two_same_blob_assets_remain_distinct_provenance_sources` | Asset provenance does not collapse. |
| `M11-PROV:02` | TEST | `tests/test_m11_publication.py::test_source_asset_id_does_not_change_revision_hash` | Derivation/provenance independent of revision identity. |
| `M11-PROV:03` | TEST | `tests/test_m11_production_history.py::test_source_link_wrong_blob_fails_provenance_verification` | Contradictory source provenance fails closed. |
| `M11-PROV:04` | TEST | `tests/test_m11_production_history.py::test_source_link_cross_project_corruption_fails` | Historical provenance Project ownership is verified. |
## M11-RACE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-RACE:01` | TEST | `tests/test_m11_publication_races.py::test_concurrent_identical_publish_converges_one_revision` | G1 concurrent identical convergence. |
| `M11-RACE:02` | TEST | `tests/test_m11_publication_races.py::test_concurrent_same_blob_distinct_assets_converge_and_keep_both_sources` | One revision plus both distinct source links under real interleaving. |
| `M11-RACE:03` | TEST | `tests/test_m11_publication_races.py::test_concurrent_different_publish_proves_order_independent_two_revision_invariant` | Distinct semantic states both survive with revision numbers {1,2}. |
| `M11-RACE:04` | TEST | `tests/test_m11_publication_races.py::test_project_deleted_after_preview_before_publish_fence_blocks_publish` | Publish re-verifies parent authority. |
| `M11-RACE:05` | STRUCTURAL | `tests/test_m11_publication_races.py::test_race_suite_uses_real_begin_immediate_parking_and_no_timing_shortcuts` | Real parking seam; no sleep or PRAGMA-based, progress-handler, mock-lock ordering. |
## M11-CORRUPT

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-CORRUPT:01` | TEST | `tests/test_m11_production_history.py::test_snapshot_hash_corruption_cycle` | Hash corruption detected, restored positive. |
| `M11-CORRUPT:02` | TEST | `tests/test_m11_production_history.py::test_snapshot_json_noncanonical_or_mismatched_cycle` | Stored canonical bytes are authoritative. |
| `M11-CORRUPT:03` | TEST | `tests/test_m11_production_history.py::test_missing_closure_row_cycle` | Exactly one closure required. |
| `M11-CORRUPT:04` | TEST | `tests/test_m11_production_history.py::test_closure_projection_mismatch_cycle` | Normalized closure must equal canonical document. |
| `M11-CORRUPT:05` | TEST | `tests/test_m11_production_history.py::test_closure_blob_hash_or_size_mismatch_cycle` | Closure/Blob byte identity cross-check. |
| `M11-CORRUPT:06` | TEST | `tests/test_m11_production_history.py::test_reuse_of_corrupted_existing_revision_fails_instead_of_returning_winner` | Convergence never hides corruption. |
| `M11-CORRUPT:07` | TEST | `tests/test_m11_production_history.py::test_missing_retained_bytes_fails_without_substitution` | No current/latest/regeneration fallback. |
| `M11-CORRUPT:08` | TEST | `tests/test_m11_production_history.py::test_same_size_physical_byte_corruption_is_detected_by_strict_consumer` | Strict consumption hashes bytes; stat-only inspection is not mislabeled as full verification. |
## M11-HISTORY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-HISTORY:01` | TEST | `tests/test_m11_production_history.py::test_strict_consumption_query_spy_reads_no_source_asset_or_creator_tables` | Consumption closure independent of derivation provenance. |
| `M11-HISTORY:02` | TEST | `tests/test_m11_production_history.py::test_creator_services_disabled_strict_consumption_still_succeeds` | Original creation mechanism not live dependency. |
| `M11-HISTORY:03` | TEST | `tests/test_m11_production_history.py::test_later_source_link_does_not_change_revision_bytes_or_hash` | Append-only provenance cannot reinterpret revision. |
| `M11-HISTORY:04` | TEST | `tests/test_m11_production_history.py::test_current_object_metadata_change_does_not_change_historical_read` | Current/history isolation. |
| `M11-HISTORY:05` | TEST | `tests/test_m11_production_history.py::test_later_blob_media_type_drift_does_not_reinterpret_historical_closure` | Publication-time interpretation metadata is frozen; live metadata drift alone is not corruption. |
| `M11-HISTORY:06` | TEST | `tests/test_m11_production_history.py::test_metadata_detail_does_not_hash_full_physical_blob` | Ordinary browse/detail does not perform the strict full-byte hot-path hash. |
## M11-MIG

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-MIG:01` | TEST | `tests/test_m11_migration.py::test_0012_upgrade_from_populated_0011_preserves_predecessor_rows` | Additive populated upgrade. |
| `M11-MIG:02` | TEST | `tests/test_m11_migration.py::test_0012_exact_orm_migration_parity` | Exact table/constraint/index parity. |
| `M11-MIG:03` | TEST | `tests/test_m11_migration.py::test_0012_empty_downgrade_to_0011` | Unused schema removable. |
| `M11-MIG:04` | TEST | `tests/test_m11_migration.py::test_0012_populated_tables_refuse_downgrade_before_ddl` | No production identity/history destruction. |
| `M11-MIG:04b` | TEST | `tests/test_m11_migration.py::test_0012_bare_production_object_refuses_downgrade_without_becoming_adopted_revision` | Any persisted M11 row makes the schema non-empty; refusal protects authored state while Publish remains the revision-adoption boundary. |
| `M11-MIG:05` | TEST | `tests/test_m11_migration.py::test_0012_does_not_backfill_existing_assets_or_projects` | No invented adoption. |
| `M11-MIG:06` | TEST | `tests/test_m11_migration.py::test_0012_foreign_key_check_clean` | Relational integrity. |
| `M11-MIG:07` | TEST | `tests/test_m11_migration.py::test_migration_head_is_0012` | Exact new head. |
## M11-RECOVERY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-RECOVERY:01` | TEST | `tests/test_m11_recovery.py::test_current_backup_expected_head_is_0012` | New backups certify only current schema head. |
| `M11-RECOVERY:02` | TEST | `tests/test_m11_recovery.py::test_recovery_blob_fk_inventory_is_six_for_0011_and_seven_for_0012` | Head-specific exact inventories; source-true six-to-seven transition. |
| `M11-RECOVERY:03` | TEST | `tests/test_m11_recovery.py::test_backup_restore_roundtrip_preserves_production_revision_and_strict_consumption` | Full 0012 historical liveness roundtrip. |
| `M11-RECOVERY:04` | TEST | `tests/test_m11_recovery.py::test_missing_m11_closure_blob_fails_backup` | Missing live closure bytes block certification. |
| `M11-RECOVERY:05` | TEST | `tests/test_m11_recovery.py::test_corrupt_m11_closure_blob_fails_backup` | Corrupt live closure bytes block certification. |
| `M11-RECOVERY:06` | TEST | `tests/test_m11_recovery.py::test_m11_snapshot_or_closure_corruption_fails_backup_semantic_verifier` | Backup does not certify malformed authority. |
| `M11-RECOVERY:07` | TEST | `tests/test_m11_recovery.py::test_m11_source_provenance_corruption_fails_backup_semantic_verifier` | Provenance corruption detected. |
| `M11-RECOVERY:08` | TEST | `tests/test_m11_recovery.py::test_restore_does_not_require_original_creator` | Restored retained closure is sufficient. |
| `M11-RECOVERY:09` | TEST | `tests/test_m11_recovery.py::test_historical_0011_backup_manifest_restores_under_m11_binary` | Valid pre-M11 backup remains recoverable without rewriting manifest bytes. |
| `M11-RECOVERY:10` | TEST | `tests/test_m11_recovery.py::test_0011_restore_invents_no_m11_tables_or_rows_then_normal_0012_migration_is_empty_additive` | Restore and migration remain separate; migration invents no adoption. |
| `M11-RECOVERY:11` | TEST | `tests/test_m11_recovery.py::test_unsupported_backup_manifest_head_fails_closed` | Restore head negotiation is closed to 0011/0012. |
| `M11-RECOVERY:12` | TEST | `tests/test_m11_recovery.py::test_backup_manifest_v1_field_grammar_is_unchanged_for_0011_and_0012` | M11 changes head policy, not manifest schema-1 fields. |
| `M11-RECOVERY:13` | TEST | `tests/test_m11_recovery.py::test_backup_semantic_verifier_ignores_live_blob_media_type_drift_but_checks_closure_grammar_hash_and_size` | Historical interpretation metadata is not a live Blob-field dependency. |
## M11-API

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-API:01` | TEST | `tests/test_m11_api.py::test_production_object_and_revision_happy_path` | Complete backend product path. |
| `M11-API:02` | TEST | `tests/test_m11_api.py::test_publish_status_201_new_200_converged` | API convergence is explicit. |
| `M11-API:03` | TEST | `tests/test_m11_api.py::test_revision_detail_never_exposes_local_path` | Storage paths remain internal. |
| `M11-API:04` | TEST | `tests/test_m11_api.py::test_revision_list_is_summary_only_and_sorted_by_revision_number` | List is bounded, summary-only, deterministic. |
| `M11-API:05` | TEST | `tests/test_m11_api.py::test_revision_detail_uses_metadata_verification_not_full_physical_hash` | Ordinary detail does not turn browse into media re-hashing. |
## M11-UI

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-UI:01` | TEST | `apps/web/src/__tests__/production-library.test.tsx::candidate readiness publish revision inspection` | candidate to readiness to publish to revision inspection. |
| `M11-UI:02` | TEST | `apps/web/src/__tests__/production-library-readiness.test.tsx::unresolved blocker disables publish` | unresolved blocker shown; Publish disabled. |
| `M11-UI:03` | TEST | `apps/web/src/__tests__/production-library-provenance.test.tsx::closure and source provenance remain distinct` | closure and source provenance rendered as distinct concepts. |
| `M11-UI:04` | TEST | `apps/web/src/__tests__/production-library.test.tsx::duplicate object names are disambiguated by stable id` | Duplicate display names never become identity. |
## M11-BOUNDARY

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-BOUNDARY:01` | STRUCTURAL | `tests/test_m11_scope.py::test_asset_kind_constraint_unchanged` | M11 does not widen Asset semantics. |
| `M11-BOUNDARY:02` | STRUCTURAL | `tests/test_m11_scope.py::test_no_shot_generation_take_schema_change` | M11 does not smuggle capture/execution scope. |
| `M11-BOUNDARY:03` | STRUCTURAL | `tests/test_m11_scope.py::test_no_production_current_revision_pointer` | M15 update lifecycle absent. |
| `M11-BOUNDARY:04` | STRUCTURAL | `tests/test_m11_scope.py::test_no_generalized_representation_registry_table` | RP-02 non-edge preserved. |
| `M11-BOUNDARY:05` | STRUCTURAL | `tests/test_m11_scope.py::test_no_execution_source_delta_in_m11_owned_diff` | No executor/live-runtime requirement introduced. |
## M11-SCALE

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-SCALE:01` | TEST | `tests/test_m11_scale.py::test_representative_fixture_is_deterministic_and_meets_frozen_cardinalities` | Representative scale is reproducible (2000 objects / 10000 revisions / 10000 links / 20000 unrelated Assets). |
| `M11-SCALE:02` | TEST | `tests/test_m11_scale.py::test_production_object_list_query_shape_is_bounded` | Object list query class does not grow with object cardinality. |
| `M11-SCALE:03` | TEST | `tests/test_m11_scale.py::test_revision_list_query_shape_is_bounded` | Revision list for one object stays bounded. |
| `M11-SCALE:04` | TEST | `tests/test_m11_scale.py::test_readiness_query_class_independent_of_total_project_assets` | Readiness does not scan unrelated Assets. |
| `M11-SCALE:05` | TEST | `tests/test_m11_scale.py::test_readiness_hashes_selected_blob_only` | Physical work is one selected Blob, not Project media. |
| `M11-SCALE:06` | TEST | `tests/test_m11_scale.py::test_metadata_detail_query_shape_is_bounded_and_performs_no_full_hash` | Ordinary detail is bounded in SQL and physical work. |
## M11-PROOF

| Cell | Disposition | Exact proof owner | Claim |
|---|---|---|---|
| `M11-PROOF:01` | TEST | `tests/test_m11_proof_map_validator.py::test_parameterized_python_owner_resolution` | Parameterized backend owners resolve exactly under the frozen grammar. |
| `M11-PROOF:02` | TEST | `tests/test_m11_proof_map_validator.py::test_frontend_exact_title_owner_resolution` | Frontend owner resolution requires file + exact test title, not a bare filename. |
| `M11-PROOF:03` | TEST | `tests/test_m11_proof_map_validator.py::test_missing_duplicate_unknown_and_dangling_evidence_fail_closed` | Required-cell removal, duplicates, unknown IDs, and dangling owners all fail validation. |
| `M11-PROOF:04` | STRUCTURAL | `tests/test_m11_scope.py::test_backend_ci_runs_m11_proof_map_validator_before_backend_tests` | CI executes the M11 validator before tests and preserves predecessor proof-map validation. |

## Closure commands

| Command | Exact invocation | Evidence owner |
|---|---|---|
| CMD:proof-map | `python scripts/m11_validate_proof_map.py` | CI + M11-PROOF:04 |
| CMD:backend-x2 | `python -m pytest -q` (two consecutive passes) | closure record |
| CMD:compileall | `python -m compileall server scripts` | closure record |
| CMD:frontend | `npm run test` + `npx tsc --noEmit` + `npm run build` in `apps/web` | closure record |
| CMD:migration-suite | `python -m pytest tests/test_m11_migration.py -q` | M11-MIG domain |
| CMD:external-name-scan | external research/product-name scan over new normative artifacts | closure record |
