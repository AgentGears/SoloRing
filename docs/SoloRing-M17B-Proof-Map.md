# SoloRing M17B — Normative Proof Map R1

**Date:** 2026-09-22  
**Status:** R6 freeze-candidate companion — **NOT IMPLEMENTATION AUTHORIZATION**  
**Purpose:** Bind every mandatory M17B conformance cell to one exact future executable proof owner.

## Mechanical law

The implementation must add `scripts/m17b_validate_proof_map.py`.

That validator MUST hard-code the exact cell-id set in this document and fail on:

- missing cell;
- duplicate cell;
- unknown cell;
- empty owner;
- malformed owner;
- dangling pytest node owner;
- an owner whose test function does not exist;
- a matrix cell present in the implementation plan but absent here;
- a proof-map cell absent from the implementation plan.

Every owner below is a future exact pytest node id. Renaming a frozen owner after plan freeze is a plan deviation and requires reviewed freeze amendment/revision before implementation can certify.

One test may call shared helpers, but each cell has its own named pytest node so a green aggregate cannot hide an unexecuted obligation.

## Normative mapping

| Cell | Exact claim | Exact proof owner |
|---|---|---|
| `A01` | missing subject rejects | `tests/test_m17b_performance.py::test_a01_missing_subject_rejects` |
| `A02` | deleted subject rejects for new candidate/adoption | `tests/test_m17b_performance.py::test_a02_deleted_subject_rejects_for_new_candidate_adoption` |
| `A03` | cross-project subject rejects | `tests/test_m17b_performance.py::test_a03_cross_project_subject_rejects` |
| `A04` | valid active same-project subject passes | `tests/test_m17b_performance.py::test_a04_valid_active_same_project_subject_passes` |
| `B01` | unknown profile rejects | `tests/test_m17b_profile.py::test_b01_unknown_profile_rejects` |
| `B02` | BODY with face channel rejects | `tests/test_m17b_profile.py::test_b02_body_with_face_channel_rejects` |
| `B03` | FACIAL with body channel rejects | `tests/test_m17b_profile.py::test_b03_facial_with_body_channel_rejects` |
| `B04` | BODY_FACIAL missing body rejects | `tests/test_m17b_profile.py::test_b04_body_facial_missing_body_rejects` |
| `B05` | BODY_FACIAL missing face rejects | `tests/test_m17b_profile.py::test_b05_body_facial_missing_face_rejects` |
| `B06` | generic FACIAL with fewer than four articulation channels passes | `tests/test_m17b_profile.py::test_b06_generic_facial_with_fewer_than_four_articulation_channels_passes` |
| `B07` | root/world channel rejects | `tests/test_m17b_profile.py::test_b07_root_world_channel_rejects` |
| `B08` | exact profile descriptors pass | `tests/test_m17b_profile.py::test_b08_exact_profile_descriptors_pass` |
| `B09` | descriptor mismatch rejects | `tests/test_m17b_profile.py::test_b09_descriptor_mismatch_rejects` |
| `C01` | reducible positive denominator canonicalizes | `tests/test_m17b_profile.py::test_c01_reducible_positive_denominator_canonicalizes` |
| `C02` | zero canonicalizes to 0/1 | `tests/test_m17b_profile.py::test_c02_zero_canonicalizes_to_0_1` |
| `C03` | denominator zero rejects | `tests/test_m17b_profile.py::test_c03_denominator_zero_rejects` |
| `C04` | negative denominator rejects | `tests/test_m17b_profile.py::test_c04_negative_denominator_rejects` |
| `C05` | signed-64 overflow rejects | `tests/test_m17b_profile.py::test_c05_signed_64_overflow_rejects` |
| `C06` | start == end rejects | `tests/test_m17b_profile.py::test_c06_start_end_rejects` |
| `C07` | start > end rejects | `tests/test_m17b_profile.py::test_c07_start_end_rejects` |
| `C08` | negative start is lawful when end is greater | `tests/test_m17b_profile.py::test_c08_negative_start_is_lawful_when_end_is_greater` |
| `C09` | keyframe exactly at start passes | `tests/test_m17b_profile.py::test_c09_keyframe_exactly_at_start_passes` |
| `C10` | keyframe exactly at exclusive end rejects | `tests/test_m17b_profile.py::test_c10_keyframe_exactly_at_exclusive_end_rejects` |
| `C11` | fractional rational keyframe inside domain passes and remains exact | `tests/test_m17b_profile.py::test_c11_fractional_rational_keyframe_inside_domain_passes_and_remains_exact` |
| `D01` | empty payload rejects | `tests/test_m17b_profile.py::test_d01_empty_payload_rejects` |
| `D02` | duplicate channel rejects | `tests/test_m17b_profile.py::test_d02_duplicate_channel_rejects` |
| `D03` | duplicate canonical keyframe timestamp rejects | `tests/test_m17b_profile.py::test_d03_duplicate_canonical_keyframe_timestamp_rejects` |
| `D04` | unsorted input canonicalizes deterministically | `tests/test_m17b_profile.py::test_d04_unsorted_input_canonicalizes_deterministically` |
| `D05` | float timestamp/value rejects | `tests/test_m17b_profile.py::test_d05_float_timestamp_value_rejects` |
| `D06` | Python bool value rejects | `tests/test_m17b_profile.py::test_d06_python_bool_value_rejects` |
| `D07` | out-of-range ppm rejects | `tests/test_m17b_profile.py::test_d07_out_of_range_ppm_rejects` |
| `D08` | out-of-range microdegree rejects | `tests/test_m17b_profile.py::test_d08_out_of_range_microdegree_rejects` |
| `D09` | canonical payload bytes rehash exactly and duplicate digest fields agree | `tests/test_m17b_profile.py::test_d09_canonical_payload_bytes_rehash_exactly_and_duplicate_digest_fields_agree` |
| `D10` | physical Blob corruption rejects | `tests/test_m17b_profile.py::test_d10_physical_blob_corruption_rejects` |
| `D11` | unknown or missing payload/channel object keys reject | `tests/test_m17b_profile.py::test_d11_unknown_or_missing_payload_channel_object_keys_reject` |
| `D12` | unknown or missing keyframe/rational/keyframe-provenance object keys reject | `tests/test_m17b_profile.py::test_d12_unknown_or_missing_keyframe_rational_keyframe_provenance_object_keys_reject` |
| `D13` | every declared channel requires at least one keyframe | `tests/test_m17b_profile.py::test_d13_every_declared_channel_requires_at_least_one_keyframe` |
| `D14` | minimal canonical payload golden reproduces pinned bytes and SHA-256 | `tests/test_m17b_profile.py::test_d14_minimal_canonical_payload_golden_reproduces_pinned_bytes_and_sha256` |
| `E01` | AUTHORED + null alignment passes | `tests/test_m17b_performance.py::test_e01_authored_null_alignment_passes` |
| `E02` | AUTHORED + alignment id rejects | `tests/test_m17b_performance.py::test_e02_authored_alignment_id_rejects` |
| `E03` | DERIVED + valid same-project same-subject alignment passes | `tests/test_m17b_performance.py::test_e03_derived_valid_same_project_same_subject_alignment_passes` |
| `E04` | DERIVED_THEN_EDITED + valid same-project same-subject alignment passes | `tests/test_m17b_performance.py::test_e04_derived_then_edited_valid_same_project_same_subject_alignment_passes` |
| `E05` | missing alignment rejects | `tests/test_m17b_performance.py::test_e05_missing_alignment_rejects` |
| `E06` | cross-project alignment rejects | `tests/test_m17b_performance.py::test_e06_cross_project_alignment_rejects` |
| `E07` | different-subject alignment rejects | `tests/test_m17b_performance.py::test_e07_different_subject_alignment_rejects` |
| `E08` | viseme_hint inside authority payload rejects | `tests/test_m17b_performance.py::test_e08_viseme_hint_inside_authority_payload_rejects` |
| `F01` | candidate is not authority | `tests/test_m17b_performance.py::test_f01_candidate_is_not_authority` |
| `F02` | adoption copies exact candidate closure | `tests/test_m17b_performance.py::test_f02_adoption_copies_exact_candidate_closure` |
| `F03` | duplicate sequential adoption returns the same PerformanceRevision and adoption metadata | `tests/test_m17b_performance.py::test_f03_duplicate_sequential_adoption_returns_the_same_performancerevision_and_adoptio` |
| `F04` | concurrent duplicate adoption converges to one exact PerformanceRevision | `tests/test_m17b_performance.py::test_f04_concurrent_duplicate_adoption_converges_to_one_exact_performancerevision` |
| `F05` | adopted revision is immutable | `tests/test_m17b_performance.py::test_f05_adopted_revision_is_immutable` |
| `F06` | candidate is immutable | `tests/test_m17b_performance.py::test_f06_candidate_is_immutable` |
| `F07` | adoption does not create Take/canon/current state | `tests/test_m17b_performance.py::test_f07_adoption_does_not_create_take_canon_current_state` |
| `F08` | no current/latest PerformanceRevision inference exists | `tests/test_m17b_performance.py::test_f08_no_current_latest_performancerevision_inference_exists` |
| `F09` | identical payload under distinct candidates may adopt to distinct PerformanceRevisions | `tests/test_m17b_performance.py::test_f09_identical_payload_under_distinct_candidates_may_adopt_to_distinct_performancer` |
| `F10` | duplicate-adoption winner is revalidated against candidate closure before return | `tests/test_m17b_performance.py::test_f10_duplicate_adoption_winner_is_revalidated_against_candidate_closure_before_retu` |
| `G01` | same exact physical revision -> COMPATIBLE_AS_IS | `tests/test_m17b_retarget.py::test_g01_same_exact_physical_revision_to_compatible_as_is` |
| `G02` | same ProductionObject different revision -> REQUIRES_REVIEW | `tests/test_m17b_retarget.py::test_g02_same_productionobject_different_revision_to_requires_review` |
| `G03` | different ProductionObject -> INCOMPATIBLE | `tests/test_m17b_retarget.py::test_g03_different_productionobject_to_incompatible` |
| `G04` | evaluator v1 never emits COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION | `tests/test_m17b_retarget.py::test_g04_evaluator_v1_never_emits_compatible_via_deterministic_translation` |
| `G05` | REQUIRES_REVIEW without explicit accepted review cannot create retarget candidate | `tests/test_m17b_retarget.py::test_g05_requires_review_without_explicit_accepted_review_cannot_create_retarget_candid` |
| `G06` | exact ACCEPT_FOR_NEW_CANDIDATE review for the same assessment permits retarget candidate | `tests/test_m17b_retarget.py::test_g06_exact_accept_for_new_candidate_review_for_the_same_assessment_permits_retarget` |
| `G07` | REJECT review does not permit retarget candidate | `tests/test_m17b_retarget.py::test_g07_reject_review_does_not_permit_retarget_candidate` |
| `G08` | INCOMPATIBLE assessment blocks retarget candidate | `tests/test_m17b_retarget.py::test_g08_incompatible_assessment_blocks_retarget_candidate` |
| `G09` | retarget assessment/provenance coordinate mismatch rejects | `tests/test_m17b_retarget.py::test_g09_retarget_assessment_provenance_coordinate_mismatch_rejects` |
| `G10` | retarget candidate/adoption leaves source PerformanceRevision unchanged | `tests/test_m17b_retarget.py::test_g10_retarget_candidate_adoption_leaves_source_performancerevision_unchanged` |
| `G11` | assessment stores exact from/to ProductionRevision snapshot hashes | `tests/test_m17b_retarget.py::test_g11_assessment_stores_exact_from_to_productionrevision_snapshot_hashes` |
| `G12` | retarget verdict does not claim subject binding, rig support, or executor qualification | `tests/test_m17b_retarget.py::test_g12_retarget_verdict_does_not_claim_subject_binding_rig_support_or_executor_qualif` |
| `G13` | scope_json exact-key grammar enforced | `tests/test_m17b_retarget.py::test_g13_scope_json_exact_key_grammar_enforced` |
| `G14` | report_json exact-key grammar enforced | `tests/test_m17b_retarget.py::test_g14_report_json_exact_key_grammar_enforced` |
| `G15` | scope/report hashes recompute byte-exact from immutable referenced rows | `tests/test_m17b_retarget.py::test_g15_scope_report_hashes_recompute_byte_exact_from_immutable_referenced_rows` |
| `G16` | accepted review belonging to another assessment rejects | `tests/test_m17b_retarget.py::test_g16_accepted_review_belonging_to_another_assessment_rejects` |
| `G17` | COMPATIBLE_AS_IS assessment is valid evidence but retarget candidate creation rejects as a no-op | `tests/test_m17b_retarget.py::test_g17_compatible_as_is_assessment_is_valid_evidence_but_retarget_candidate_creation` |
| `G18` | retarget candidate inherits source project/subject/kind/profile/domain/channel payload byte-for-byte | `tests/test_m17b_retarget.py::test_g18_retarget_candidate_inherits_source_project_subject_kind_profile_domain_channel` |
| `G19` | identical retarget-assessment creation converges sequentially and concurrently | `tests/test_m17b_retarget.py::test_g19_identical_retarget_assessment_creation_converges_sequentially_and_concurrently` |
| `G20` | report scope_hash binding rejects cross-scope/report mixing or same-coordinate nondeterminism | `tests/test_m17b_retarget.py::test_g20_report_scope_hash_binding_rejects_cross_scope_report_mixing_or_same_coordinate` |
| `H01` | no VocalPerformance binding on base PerformanceRevision | `tests/test_m17b_source_gate.py::test_h01_no_vocalperformance_binding_on_base_performancerevision` |
| `H02` | no synchronization_basis_version | `tests/test_m17b_source_gate.py::test_h02_no_synchronization_basis_version` |
| `H03` | no dialogue-bound required-articulation enforcement | `tests/test_m17b_source_gate.py::test_h03_no_dialogue_bound_required_articulation_enforcement` |
| `H04` | no Shot Performance binding | `tests/test_m17b_source_gate.py::test_h04_no_shot_performance_binding` |
| `H05` | no ShotRevision schema 8 | `tests/test_m17b_source_gate.py::test_h05_no_shotrevision_schema_8` |
| `H06` | no Generation/WorkflowSpec performance schema | `tests/test_m17b_source_gate.py::test_h06_no_generation_workflowspec_performance_schema` |
| `H07` | no executor integration | `tests/test_m17b_source_gate.py::test_h07_no_executor_integration` |
| `H08` | no universal rig schema | `tests/test_m17b_source_gate.py::test_h08_no_universal_rig_schema` |
| `H09` | no profile/2 | `tests/test_m17b_source_gate.py::test_h09_no_profile_2` |
| `H10` | no M18 contact authority | `tests/test_m17b_source_gate.py::test_h10_no_m18_contact_authority` |
| `H11` | no M19 QC/correction authority and no M17B frontend product surface | `tests/test_m17b_source_gate.py::test_h11_no_m19_qc_correction_authority_and_no_m17b_frontend_product_surface` |
| `I01` | fresh upgrade reaches 0019 | `tests/test_m17b_recovery.py::test_i01_fresh_upgrade_reaches_0019` |
| `I02` | exactly four M17B tables | `tests/test_m17b_recovery.py::test_i02_exactly_four_m17b_tables` |
| `I03` | predecessor tables remain unchanged | `tests/test_m17b_recovery.py::test_i03_predecessor_tables_remain_unchanged` |
| `I04` | empty downgrade succeeds | `tests/test_m17b_recovery.py::test_i04_empty_downgrade_succeeds` |
| `I05` | populated downgrade refuses | `tests/test_m17b_recovery.py::test_i05_populated_downgrade_refuses` |
| `I06` | head 0018 remains exact 11 Blob-FK paths | `tests/test_m17b_recovery.py::test_i06_head_0018_remains_exact_11_blob_fk_paths` |
| `I07` | head 0019 has exactly 13 Blob-FK paths | `tests/test_m17b_recovery.py::test_i07_head_0019_has_exactly_13_blob_fk_paths` |
| `I08` | backup/restore preserves canonical payload bytes/hashes and immutable ids | `tests/test_m17b_recovery.py::test_i08_backup_restore_preserves_canonical_payload_bytes_hashes_and_immutable_ids` |
| `I09` | recovery rejects noncanonical payload | `tests/test_m17b_recovery.py::test_i09_recovery_rejects_noncanonical_payload` |
| `I10` | recovery rejects assessment reason/verdict/report drift | `tests/test_m17b_recovery.py::test_i10_recovery_rejects_assessment_reason_verdict_report_drift` |
| `I11` | restore at 0018 or earlier invents zero M17B state | `tests/test_m17b_recovery.py::test_i11_restore_at_0018_or_earlier_invents_zero_m17b_state` |
| `I12` | recovery rejects adopted-revision copied-closure drift while historical soft-deleted subjects remain valid | `tests/test_m17b_recovery.py::test_i12_recovery_rejects_adopted_revision_copied_closure_drift_while_historical_soft_d` |
| `J01` | candidate provenance unknown or missing top-level keys reject | `tests/test_m17b_performance.py::test_j01_candidate_provenance_unknown_or_missing_top_level_keys_reject` |
| `J02` | candidate provenance source_kind outside the closed vocabulary rejects | `tests/test_m17b_performance.py::test_j02_candidate_provenance_source_kind_outside_the_closed_vocabulary_rejects` |
| `J03` | producer_id empty/whitespace/over-255 rejects | `tests/test_m17b_performance.py::test_j03_producer_id_empty_whitespace_over_255_rejects` |
| `J04` | producer_version empty/whitespace/over-255 rejects | `tests/test_m17b_performance.py::test_j04_producer_version_empty_whitespace_over_255_rejects` |
| `J05` | malformed parameters_sha256 rejects | `tests/test_m17b_performance.py::test_j05_malformed_parameters_sha256_rejects` |
| `J06` | non-retarget source_kind requires retarget = null | `tests/test_m17b_performance.py::test_j06_non_retarget_source_kind_requires_retarget_null` |
| `J07` | retarget provenance unknown/missing nested keys reject | `tests/test_m17b_performance.py::test_j07_retarget_provenance_unknown_missing_nested_keys_reject` |
| `J08` | source_identity is audit provenance only and mutable/local filesystem path forms reject | `tests/test_m17b_performance.py::test_j08_source_identity_is_audit_provenance_only_and_mutable_local_filesystem_path_for` |
| `J09` | retarget provenance golden reproduces pinned bytes and SHA-256 | `tests/test_m17b_performance.py::test_j09_retarget_provenance_golden_reproduces_pinned_bytes_and_sha256` |
| `K01` | candidate collection rejects partial cursor | `tests/test_m17b_performance.py::test_k01_candidate_collection_rejects_partial_cursor` |
| `K02` | revision collection rejects partial cursor | `tests/test_m17b_performance.py::test_k02_revision_collection_rejects_partial_cursor` |
| `K03` | candidate pagination is stable and gap/duplicate-free for equal created_at using id tie-breaker | `tests/test_m17b_performance.py::test_k03_candidate_pagination_is_stable_and_gap_duplicate_free_for_equal_created_at_usi` |
| `K04` | revision pagination is stable and gap/duplicate-free for equal adopted_at using id tie-breaker | `tests/test_m17b_performance.py::test_k04_revision_pagination_is_stable_and_gap_duplicate_free_for_equal_adopted_at_usin` |
| `K05` | exact candidate and review evidence are dereferenceable; review listing is deterministic and implies no latest-wins rule | `tests/test_m17b_performance.py::test_k05_exact_candidate_and_review_evidence_are_dereferenceable_review_listing_is_dete` |

## Fixed totals

```text
sections: 11
cells: 113
first cell: A01
last cell: K05
```

## Validator execution

Certification requires:

```text
python scripts/m17b_validate_proof_map.py
pytest -q <all exact owner nodes or the focused suite containing them>
```

The validator is structural evidence only; it does not substitute for executing the proof owners.

**Current gate:** PROOF MAP R1 CANDIDATE FOR M17B R6 FREEZE VERIFICATION. IMPLEMENTATION NOT AUTHORIZED.
