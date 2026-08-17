# Source-Audit Remediation Record — M1→M5A repair pass

> **Second pass (R1–R8) and third pass (third re-gate patch) appended
> below.**

The source-level audit reopened M1, M2, M3B, M3C, M4, and M5A with fifteen
findings and blocked M5B until repair and re-gating. This record maps every
finding to its fix and its regression test. Suite: **640/640 × 2** (627 prior
+ 13 audit regressions), stress 5/5 clean on all remediation-sensitive files,
frontend tsc + component tests + production build green.

| # | Sev | Finding | Fix | Regression test |
|---|-----|---------|-----|-----------------|
| F1 | CRITICAL | Durable publication not ownership-fenced; stale worker can mint Takes | `import_staged_outputs` takes `worker_id`; lease + generation ownership verified INSIDE the same `BEGIN IMMEDIATE` that inserts Take/Asset (raw-SQL publication unit). Fake drive now stops at the importing fence; comfy pipeline already `_require_ok`'d it and its publication is fenced | `test_audit_m3.py::test_stale_worker_cannot_mint_take` (stale A refused, zero Takes/Assets; current authority B publishes) |
| F2 | HIGH | ShotRevision capture combines two DB snapshots | `_snapshot_one_read`: one connection + explicit `BEGIN` read snapshot for shot columns + references (same pattern as `read_shot_detail`) | `test_audit_m1.py::test_capture_revision_never_combines_two_db_states` (interleaved writer ⇒ all-old capture, never hybrid) |
| F3 | HIGH | Corrupt pre-existing Blob registered as valid | `BlobStore.place` hashes an existing destination; mismatch ⇒ REPAIR from the independently verified temp bytes (high-severity log); concurrent-winner convergence retained | `test_audit_m1.py::test_corrupt_preexisting_blob_repaired_from_verified_upload` + convergence test |
| F4 | HIGH | Reference UI mutates by `asset_id` only | `ReferencePanel`/`ReferenceRoleGroup` callbacks carry the complete `(asset_id, role)` occurrence identity for move / role-change / remove; vitest + testing-library harness added to the web app | `apps/web/src/__tests__/ReferencePanel.test.tsx` (4 tests: dual-role remove, role change, in-role move, attach duplicate rule) |
| F5 | HIGH | Claim-vs-cancel TOCTOU; unconditional "cancelled" report | Cancel route is ONE `BEGIN IMMEDIATE` read-decide-write unit (same lock domain as the claim); rowcount honored; rollbacks routed through SQLAlchemy bookkeeping | `test_audit_m3.py::test_cancel_vs_claim_race_atomic` (three legal serialized outcomes; report always matches durable state) + `..._always_matches_durable_state` |
| F6 | HIGH | Staging containment string-prefix bypass | `Path.resolve().relative_to(staging_dir)` — real containment semantics | `test_audit_m3.py::test_same_prefix_sibling_staging_dir_rejected` |
| F7 | MED/HIGH | Whole-file hashing in RAM during import | `_hash_and_detect` streams 1 MiB chunks; only the 16-byte media prefix retained | `test_audit_m3.py::test_large_output_hashed_in_bounded_chunks` (8 MiB output; instrumented reads ≤ chunk; hash identity verified) |
| F8 | HIGH | `load_workflow` parses A, hashes B | Each file read as ONE byte buffer that is both parsed and hashed | `test_audit_m4_m5a.py::test_load_workflow_semantics_and_hash_come_from_one_buffer` |
| F9 | HIGH | Comfy creation persists a second mutable read | After `capture_package`, the template is built from the EXACT captured bytes + captured hashes (`build_template(parse(captured…))`); `load_workflow()` is no longer called on the comfy path | `test_audit_m4_m5a.py::test_comfy_creation_persists_the_captured_release_only` (install switch inside the capture window ⇒ recorded pair is the captured one, retrievable) |
| F10 | HIGH | Binding validation never invoked in production | `validate_manifest_template_bindings` runs at comfy CAPTURE (invalid pair ⇒ 422 COMFY_TEMPLATE_BINDING_INVALID, nothing queued) and again after historical retrieval, before translation | `test_audit_m4_m5a.py::test_bad_binding_package_rejected_at_capture` (+ retrieval validation on the translate path in the pipeline) |
| F11 | HIGH | Upload subfolders discarded by translation | `comfy_input_reference(remote_name, subfolder)` — the attempt namespace is part of the bound value (`ns/name`); exact live wire form pinned at M5B-2 | `test_m5a5_translate.py` repinned bindings; aggregate headline asserts `namespace/hash.png` |
| F12 | HIGH/MED | Recovery does prework before consulting durable submission state | Pipeline entry reads submission state FIRST: `uncertain` → terminalize; `confirmed` → adopt persisted prompt_id, NO prework; `submission_possible` → REDISCOVER_ONLY, payload-less; only `not_started` retrieves/materializes/translates. `run_comfy_submission` accepts `payload_document=None` for the rediscover-only frame | `test_audit_m4_m5a.py::test_confirmed_adoption_skips_submission_prework` (injected FAILING materializer; one POST total; zero uploads; succeeds) |
| F13 | MED | `client.readiness()` contradicted the capability model | Removed (dead code — no production/test caller). Readiness is exclusively `capabilities.evaluate_readiness` over an evidence-backed report; M5B-1 builds the live probe | Existing `test_m5a2_wire.py` readiness tests (evaluate_readiness semantics) unchanged and passing |
| F14 | MED | History normalization rejected unrelated non-file data | `_history_outputs` tolerates non-list fields, non-dict items, and filename-less dicts (skipped); dicts that ARE file references stay strictly validated; binding-level cardinality strictness unchanged at resolve | `test_m5a2_wire.py::test_history_unrelated_nonfile_data_tolerated` + `test_history_invalid_filename_in_file_structure_rejected` |
| F15 | MED | One corrupt queued row starves the queue | `claim_next_generation` scans all queued candidates in order, logs loudly, and skips illegal-state rows (never resets them); claims the next valid one | `test_audit_m4_m5a.py::test_corrupt_queued_row_does_not_starve_the_queue` |

Not addressed (per the audit's own triage): `HttpInputMaterializer`'s upload
lock serializes unique uploads — recorded as a known performance note, not a
milestone blocker.

## Structural notes for reviewers

- The importer's publication unit is now raw SQL under `BEGIN IMMEDIATE`
  (Blob upsert, Take `ON CONFLICT DO NOTHING` convergence, Asset insert) so
  the fence and the mint share one transaction; the M3C checkpoint names and
  crash-matrix semantics are unchanged and the whole existing M3C suite
  passes unmodified.
- The cancel route's fenced unit serializes against `claim_next_generation`
  (same `BEGIN IMMEDIATE` lock domain), which is what closes the TOCTOU
  structurally rather than by re-read.
- F9 + F8 together mean every identity recorded at creation — manifest hash,
  template hash, spec — derives from byte buffers actually verified, with no
  second mutable read anywhere on the comfy path.

---

# Second re-audit remediation (R1–R8)

The re-audit re-closed M2 and M4, held M1/M3B/M3C/M5A on eight new findings,
and blocked M5B. All eight plus the composition and diagnostics notes are
fixed below. Suite: **648/648 × 2** (640 + 8 second-pass regressions),
stress 5/5 clean on all authority/race-sensitive files, frontend tsc +
component tests + production build green.

| ID | Sev | Finding | Fix | Regression test |
|----|-----|---------|-----|-----------------|
| R1 | CRITICAL | Pre-POST lease check compared against `None`; `refresh_worker_lease` returns RETAINED/LOST so it never fired | Correct `LeaseRetentionResult.LOST` comparison AND the new full `verify_execution_authority` gate (lease + Generation ownership in one fenced unit) before `/prompt` | `test_audit2_authority.py::test_lost_lease_before_prompt_blocks_post` (POST count == 0) |
| R2 | HIGH | Lease-lost workers could still issue destructive external cancellation (Fake `executor.cancel`, Comfy `cancel_pending`/`cancel_running`) | Central `verify_execution_authority` primitive in ownership.py; Fake `_cancel_if_requested` proves authority before the executor call and returns `"halt"`; `reconcile_cancellation` refuses remote effects via `_require_authority_for_remote_effect` | `test_lost_lease_before_fake_cancel_blocks_executor_cancel` (cancel count == 0); `test_lost_lease_before_comfy_cancel_blocks_remote_cancel` (interrupts == 0, queue-deletes == 0, POST count unchanged) |
| R3 | HIGH | Cancel API treated `preparing + no executor_job_id` as definitely unsubmitted; `submission_possible` may already be at the executor | The immediate-cancel branch additionally requires `executor_submission_state == 'not_started'`; `submission_possible`/`confirmed` fall through to persisted intent for recovery reconciliation | `test_submission_possible_cancel_persists_intent_not_terminal` |
| R4 | HIGH | Multi-output import could publish output 0 before discovering output 1 invalid | Two-phase importer: preflight the ENTIRE set (hash, sniff, media-contract, blob placement) before ANY Take/Asset; publication units run only after full preflight success | `test_second_output_media_invalid_leaves_zero_takes` (two outputs, second invalid → zero Takes/Assets) |
| R5 | HIGH | Concurrent staging of the same output_key with different bytes was last-writer-wins | Transfer is hashed while streaming; an existing target is verified — identical bytes converge, different bytes raise `OutputInvalid` (never silent overwrite) | `test_concurrent_conflicting_transfers_conflict_not_overwrite` (exactly one winner; sequential divergence refused; target never replaced) |
| R6 | MED/HIGH | Identity-bearing remote values (upload name/subfolder, output node/field) truncated at DIAGNOSTIC_MAX | `_identity_value`: preserved EXACTLY, rejected above a hard 1024 bound; DIAGNOSTIC_MAX remains for prose only | `test_long_legal_identity_round_trips_exactly_never_truncated` (130-char name exact + validator-accepted; 2000-char rejected; node binding identity exact) |
| R7 | MED/HIGH | Publication fence lacked attempt_id + importing-state checks | Fence now verifies lease + worker + **current attempt_id** + **status='importing'** in the publication transaction; `worker_id` without `attempt_id` is a contract error | `test_publication_fence_requires_attempt_and_importing` (stale-attempt and non-importing both refused, zero Takes) |
| R8 | MED/HIGH | M1 blob repair hashed an existing file with one whole-file read | `BlobStore._hash_file` streams 1 MiB chunks | bounded-read proof pattern shared with the importer (F7 regression instruments the same class of read) |

Composition fix (deauthorization promptness): every fenced mutation inside
an active drive is now checked — the Fake observe loop and the Comfy pipeline
(progress write + `running` transition) stop the local drive immediately on
LEASE_LOST/GENERATION_OWNERSHIP_LOST instead of continuing to poll, and the
Fake cancel path halts rather than touching the executor. The rule
"lease loss ≠ remote cancellation" is enforced at every external-effect
boundary.

Diagnostics fix: the F15 skipped-row count now counts actual illegal-state
rows (`sum(state != not_started)`), no longer falsely reporting corruption
when all queued rows are valid.


---

# Third re-gate patch

The second re-gate held M3B/M3C/M5A on four blockers. The narrow patch set
below addresses them; suite: **653/653 x2** (648 + 5 third-pass regressions),
stress 5/5 clean on all authority/race files, frontend tsc + component tests
+ production build green. **This archive is a FULL tree snapshot**, not a
delta: the r2 delta omitted `wire.py` and the updated first-pass regression
file even though both were fixed in the working tree, which produced the
reviewer's reconstructed-tree failures. Deliverable lesson recorded.

| ID | Finding | Fix | Regression test |
|----|---------|-----|-----------------|
| Gate-1 | r2 delta archive omitted `wire.py` (R6) and the updated `test_audit_m3.py`, so the reconstructed tree could not reproduce 648/648 | No code change needed (the working tree was correct); deliverable practice changed to full-tree archives | Third-gate runs re-verified `test_audit_m3` and the R6 test against this tree: both green |
| R5-residual | Staging finalization was exists()-then-replace — a barrier-forced interleaving let both finalizers succeed with divergent bytes | `_publish_no_clobber`: `os.link` interlock (atomic no-clobber; hard-linked target is complete by construction); loser verifies winner identity -> converge or `OutputInvalid`; exotic-FS replace-then-verify fallback documented | `test_audit3_gate.py::test_barrier_controlled_conflicting_publication_conflicts` (barrier INSIDE os.link; exactly one winner + one conflict; zero temp debris) and `..._identical_..._converges` |
| R2-residual | `verify_execution_authority` was read-only: an EXPIRED but not-yet-taken lease passed, then a successor took it between check and effect | The primitive is RETAINING: the conditional lease-heartbeat refresh and the ownership verification share one BEGIN IMMEDIATE — a passing caller holds a FRESH interval, so takeover cannot interleave; a taken lease fails the conditional refresh outright | `test_retaining_authority_blocks_takeover_after_expired_lease` (retain -> HELD_BY_OTHER for successor) and `test_taken_over_lease_refuses_effect_even_with_fresh_generation` (generation row fresh, lease taken -> zero executor cancels) |
| M3C rollback-expiry | `create_generation_request` dereferenced the pre-helper `shot` ORM object after `capture_revision` may roll the session back -> MissingGreenlet under concurrent identical Generates | The service validates then uses the PRIMITIVE `shot_id`; no ORM attribute is retained across the rollback-owning helper (audited: `refs` are dataclasses; the returned `revision` is alive on every return path) | `test_create_generation_survives_revision_rollback` (forced in-capture rollback; 202 + correctly-bound queued row) |

The `/prompt` path keeps its explicit `refresh_worker_lease` +
`verify_execution_authority` sequence (the re-gate cited it as the correct
pattern); the retaining upgrade makes the verify step itself fresh-windowed,
so every external-effect gate — Fake cancel, Comfy pending/running cancel,
and /prompt — now holds a retained lease interval at the moment of the
external call.


---

# Final M5A re-gate patch (R5 fallback removal)

The full-snapshot review narrowed the gate to exactly one defect: the
`except OSError: os.replace(...)` fallback in `_publish_no_clobber` was
overwrite-capable (the final writer observes its own bytes and cannot detect
the divergence it caused). The fallback is REMOVED — publication now fails
closed with `OutputFetchFailed` ("staging filesystem does not support atomic
no-clobber publication") whenever `os.link` cannot provide the interlock.

Regression: `test_audit3_gate.py::test_unsupported_no_clobber_filesystem_
fails_closed` — forced `os.link` OSError: no target created from scratch;
an existing staged target is preserved byte-for-byte; zero temp debris.

Suite: **654/654 x2** (653 + the fail-closed regression), 5/5 clean stress
on the output/staging suites.
