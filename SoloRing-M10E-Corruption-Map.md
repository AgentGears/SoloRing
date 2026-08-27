# M10E — §21 Corruption-Matrix Cell → Exact Test Map (E-080 closure record)

Every one of the 53 frozen §21 cells, mapped to the exact pinning test.
Disposition vocabulary: `TEST` = dedicated corruption-style test with
the full five-step cycle (positive control → isolated corruption →
fail-closed → exact restoration → restored positive); `STRUCTURAL` = the
corruption is rejected by the storage layer itself (migration-0011
FK/CHECK constraints) — the test proves the tampering UPDATE/DELETE
cannot be applied and the positive control stays valid; `INHERITED` =
the cell is owned by a frozen predecessor test that remains binding
regression coverage.

| # | Cell | Test |
|---|---|---|
| 1 | schema-3 descriptor malformed | TEST …::test_descriptor_malformed_fails (five-step) |
| 2 | descriptor/manifest hash disagreement | TEST …::test_descriptor_hash_disagreement_fails (five-step) |
| 3 | descriptor/template hash disagreement | TEST …::test_cells3to5_descriptor_hash_disagreements (five-step cycle: positive capture → tamper → fail → restore → positive) |
| 4 | descriptor/profile hash disagreement | TEST …::test_cells3to5_descriptor_hash_disagreements |
| 5 | descriptor/fingerprint hash disagreement | TEST …::test_cells3to5_descriptor_hash_disagreements |
| 6 | historical manifest bytes missing | INHERITED tests/test_m5a3_artifacts.py::test_missing_historical_manifest_and_template |
| 7 | historical manifest bytes hash-corrupt | INHERITED tests/test_m5a3_artifacts.py::test_corrupt_historical_artifacts_fail_integrity |
| 8 | historical template bytes missing/corrupt | INHERITED tests/test_m5a3_artifacts.py (same pair; template leg) |
| 9 | historical profile bytes missing/corrupt | INHERITED tests/test_m9a_package.py (profile store leg; INTERNAL_INVARIANT_VIOLATION) |
| 10 | historical fingerprint bytes missing/corrupt | INHERITED tests/test_m9a_package.py::(fingerprint unlink → INTERNAL_INVARIANT_VIOLATION) |
| 11 | profile v2 spatial capacity mutated | TEST …::test_profile_capacity_mutated_fails (five-step) |
| 12 | profile runtime requirement unclosed | TEST …::test_runtime_requirement_unclosed_fails (five-step) |
| 13 | manifest v3 spatial role unknown | TEST tests/test_m10e_corruption.py::test_cells13_15_manifest_grammar_corruptions |
| 14 | manifest world binding missing | INHERITED tests/test_m10a4_package.py::test_manifest_requires_exactly_one_world_stream |
| 15 | manifest duplicate/incompatible entity binding | TEST …::test_cells13_15… + INHERITED …::test_manifest_three_entity_streams_rejected |
| 16 | manifest binding node missing from template | TEST …::test_binding_node_missing_from_template_fails (five-step) |
| 17 | manifest binding field missing from node | TEST …::test_binding_field_missing_from_template_node_fails (five-step) |
| 18 | WorkflowSpec stored JSON malformed | TEST tests/test_m10e_corruption.py::test_cells18_19_20_five_step_cycle (real production loader; full five-step cycle) |
| 19 | WorkflowSpec stored hash disagreement | TEST …::test_cells18_19_20_five_step_cycle (same real seam, five-step cycle) |
| 20 | WorkflowSpec non-canonical bytes | TEST tests/test_m10e_corruption.py::test_cell20_noncanonical_stored_spec_bytes_rejected (real production function) |
| 21 | persisted `pending:` derived artifact ID | TEST …::test_cell21_pending_identity_in_workflow_spec_rejected (+ restored positive) |
| 22 | non-empty structured_bindings in Path B | TEST …::test_cell22_nonempty_structured_bindings_rejected (historical rehashed tamper + restored positive) + INHERITED creation-time rejection |
| 23 | derived spec JSON malformed | INHERITED tests/test_m10a_derived.py (parse_derived_spec → DERIVED_SPATIAL_SPEC_INVALID) |
| 24 | derived spec non-canonical bytes | INHERITED tests/test_m10a_derived.py (validate_derived_provenance_row canonical-bytes check) |
| 25 | derived spec hash disagreement | INHERITED tests/test_m10a_derived.py (projection `spec_hash` vs canonical) |
| 26 | derived projection column disagreement | INHERITED tests/test_m10a_derived.py (expected-projection mismatch) |
| 27 | runtime-fingerprint JSON malformed | INHERITED tests/test_m10a_derived.py (parse_runtime_fingerprint → DERIVED_SPATIAL_RUNTIME_UNPINNABLE) |
| 28 | runtime-fingerprint non-canonical bytes | INHERITED tests/test_m10a_derived.py |
| 29 | runtime-fingerprint hash disagreement | INHERITED tests/test_m10a_derived.py |
| 30 | materializer algorithm identity disagreement | INHERITED tests/test_m10a_derived.py (spec↔runtime algorithm agreement) |
| 31 | DerivedSpatialArtifact Blob hash mismatch | STRUCTURAL tests/test_m10e_corruption.py::test_cell31… (composite FK) |
| 32 | Blob DB row missing | STRUCTURAL …::test_cell32_blob_db_row_missing (fk_gdsi_blob) |
| 33 | physical Blob missing | TEST …::test_cell33_physical_blob_missing |
| 34 | physical Blob hash corruption | TEST …::test_cell34_physical_blob_corrupt |
| 35 | sibling derived artifact ID missing | TEST …::test_fault_at_derived_binding_rolls_back_all (five-step) |
| 36 | sibling artifact/blob composite mismatch | STRUCTURAL …::test_cell36_sibling_composite_mismatch (composite FK) |
| 37 | sibling Project/spatial-continuity mismatch | TEST both halves: continuity …::test_cell37_project_continuity_mismatch + Project …::test_cell37_project_ownership_mismatch |
| 38 | sibling role/scope mismatch | TEST …::test_cell38_role_scope_mismatch (five-step: positive create → corrupt binding → rollback → restored positive) |
| 39 | sibling world position not zero | TEST …::test_cells39_40_sibling_coordinate_violations (five-step) |
| 40 | sibling position gap | TEST …::test_cells39_40_sibling_coordinate_violations (five-step) |
| 41 | sibling canonical entity order violation | TEST …::test_entity_order_violation_fails (five-step: positive create → swapped order → rollback → restored positive) |
| 42 | extra sibling row versus WorkflowSpec | TEST …::test_cells42_43_extra_missing_sibling_vs_spec |
| 43 | missing sibling row versus WorkflowSpec | TEST …::test_cells42_43_extra_missing_sibling_vs_spec |
| 44 | sibling input key mismatch vs manifest/spec | TEST …::test_cell44_input_key_mismatch_vs_manifest |
| 45 | derived upload reference missing at translation | TEST …::test_missing_upload_reference_fails (positive → missing → fail → restored positive) |
| 46 | extra derived upload reference at translation | TEST …::test_extra_derived_reference_fails (positive → extra → fail → restored positive) |
| 47 | current package changed after creation | TEST tests/test_m10e_rerun.py::test_current_authority_mutation_cannot_change_rerun_identity (five-step: positive rerun → mutation → unchanged → exact restoration → restored-positive rerun) |
| 48 | current M10 authority changed after creation | TEST …::test_current_authority_mutation_cannot_change_rerun_identity (world/track/plan mutation leg of the five-step cycle) |
| 49 | current changes before Exact Rerun | TEST …::test_current_authority_mutation_cannot_change_rerun_identity (rerun-under-mutation + restored legs) |
| 50 | same spec/runtime different Blob | TEST tests/test_m10e_races.py::test_concurrent_divergent_registration_fails_nondeterministic (both forced orders) |
| 51 | derived_artifacts list order/position vs canonical | TEST tests/test_m10e_corruption.py::test_cell51_list_order_violation_rejected (historical rotation, five-step cycle) |
| 52 | ordinary/M9 key collides with derived key | TEST …::test_cross_family_key_collision_fails_in_unit (five-step: positive → collision → rollback → restored positive) |
| 53 | unrelated Project identity at production binding | TEST …::test_cell53_unrelated_project_identity_fails_closed (five-step: positive → cross-Project rebind → fail → exact restore → positive) |

All 53 cells are TEST-class cycles through real production seams or
STRUCTURAL storage-layer proofs; cells inherited from frozen predecessor
suites remain binding regression coverage. Cells 22/51 additionally have
dedicated HISTORICAL-corruption tests through the strict
validate_spatial_realization_block_history seam (tampered + consistently
rehashed stored spec, exact restoration, restored positive).
