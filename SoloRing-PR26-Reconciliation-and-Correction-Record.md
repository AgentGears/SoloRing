# SoloRing PR #26 — Second-Review Reconciliation and Correction Record

**Date:** 2026-09-26  
**PR:** #26 (draft), first-pass head `dd075fb78a6cba571cb79382b56d3f348ac6a4af` (CI #184 green there)  
**Status:** corrective cycle executed per the reconciled second-review disposition; **M17C-A at `dd075fb` was NO-GO as a completed slice — SR26-01/SR26-02 accepted as real authority/recovery defects; this record documents their correction and the disposition of SR26-03..06.**

The frozen first-pass register (`SoloRing-PR26-First-Pass-Review-R1.md`) remains evidence; its "M17C-A is sound" conclusion is superseded by the reconciled disposition recorded here.

---

## SR26-01 — immutable PF-03 applicability discriminator: IMPLEMENTED

**Design:** two new immutable 1:1 classification companions in migration 0020 (still mutable inside this draft PR by its own header): `performance_candidate_sync_classifications` / `performance_revision_sync_classifications`, closed mode `NONE | VOCAL_V1`, schema version 1, FK RESTRICT to their parents. Predecessor M17B rows are backfilled `NONE`; rows with bindings `VOCAL_V1` (bootstrap caveat recorded: a database whose bindings were already totally lost before this migration classifies NONE — the discriminator protects all state created or verified after it lands).

**Laws (all fail-closed as `INTERNAL_INVARIANT_VIOLATION`):**
- every candidate/revision carries exactly one classification; absence = corruption;
- `VOCAL_V1` requires exactly one binding companion; `NONE` prohibits one (both directions);
- candidate creation writes the classification atomically (generic route `NONE`; dialogue-bound route `VOCAL_V1`);
- adoption copies the classification independently of the binding payload; replay verifies equality + cardinality;
- retarget copies the source revision's classification and verifies it before creating fresh evidence;
- total companion loss therefore refuses at pre-adoption, adoption replay, retarget, authoritative reads, and recovery — it can no longer pass as generic M17B.

**Regressions (all green):** pre-adoption total loss refuses with zero revisions; post-adoption total loss refuses replay + both GETs + retarget with zero new candidates; `NONE`+binding refuses; missing classification refuses; adoption/retarget classification copies verified; generic candidates classify `NONE` end-to-end.

## SR26-02 — minimal PF-03 recovery verifier at 0020: IMPLEMENTED

`server/soloring/recovery/m17c_verifier.py::verify_m17c_binding_state` runs at head 0020 after every predecessor verifier (wired into BOTH `successor_semantics` dispatch chains). It verifies: table presence; exactly-one classification per candidate/revision with closed vocabulary + schema version; NONE/VOCAL_V1 cardinality; canonical binding bytes/hash reproduction; rational canonicality; schema/basis versions; VP existence, rate equality, trim containment, subject/speaker agreement; induced interval inside the temporal domain (exact `Fraction`); revision↔candidate classification and binding-closure equality; articulation-keyframe and cited-alignment laws over the retained payload blob; retarget-lineage binding preservation. The 0020 head is no longer certified only through M17B depth.

**Regressions (all green):** clean round-trip preserves exact PF-03 rows (field-wise candidate==revision); total loss, one-sided loss, missing classification, NONE+binding, binding-hash divergence, binding-json divergence, one-sided VP substitution, retarget-lineage loss, and missing-VP staged tamper each refuse backup/restore verification fail-closed.

## SR26-03 — fail-closed authoritative reads: IMPLEMENTED

GET candidate/revision vocal-binding now runs `read_candidate_vocal_binding` / `read_revision_vocal_binding`: classification-aware (missing classification = corruption; `NONE` = honest 404 `PERFORMANCE_VOCAL_BINDING_NOT_FOUND`), canonical bytes/hash, parent/companion closure, revision↔candidate closure equality, VP identity + rate/trim/subject laws, interval-in-domain, and cited-alignment exact-VP — before representing the binding as authority. **Recorded cost boundary:** reads do not rehash the retained VP audio bytes (a transition-time and recovery-time check). Tampered hash/json/rational/rate and one-sided VP substitution each return the corruption contract (500), and the lawful closure reads cleanly again after restore.

## SR26-04 — boundary/source-fit gates individually classified and restored: IMPLEMENTED

Individual classification against the corrective tree: **successor-aware and KEPT** — `m13_validate_boundary` (green as-is), `hygiene_validate_boundary` (swept: exact M17C successor paths + reviewed successor-maintained files + admitted 0020 migration + admitted M17C tables), `next_security_validate_boundary` (same sweep, both predecessor/published gates), `m14_validate_boundary` (successor-pattern sweep), `m14_validate_source_fit` (exact M17C paths into `REVIEWED_SUCCESSOR_PATHS` — the gate's own "exact path, not weakening" contract), `m14_validate_baseline` (admitted-set sweep from the first pass), `m16_validate_baseline` (green as-is), `m16_validate_boundary` (swept), `m16_validate_source_fit` (green as-is). **All thirteen validators (incl. proof maps) restored to CI**; the wholesale-retirement rationale removed with an individual-classification comment. `test_m15_baseline`/`test_m14_base_corpus` validator lists restored to the full sets; the nsec squash-survival skip **removed** (boundary green over the current tree again — 45/45 incl. that proof).

## SR26-05 — corruption-contract normalization: IMPLEMENTED (with an admission/history split)

Persisted-history verification now translates admission-shaped failures into corruption: missing cited VP (when the binding is already persisted), missing cited alignment (via `history=True` on the shared provenance verifier — admission-time 404/422 behavior preserved for NEW requests), and malformed persisted rationals. Admission remains client-facing: a client-supplied VP id that does not exist is still a 404 at creation (the pending-binding flag distinguishes the two worlds). Recorded residual: the alignment-side `history` flag currently flips only the missing-alignment branch; deeper admission/history splits can land with M17C-B.

## SR26-06 — centralized error codes: IMPLEMENTED

The seven M17C codes are `ErrorCode` members in `soloring/errors.py`; `m17c_contract` keeps stable aliases to the same strings. Regression asserts central registration + alias equality.

## First-pass fixes carried forward

F1–F3 (route-proof introspection, canonical DDL comparison, exact-Fraction induced interval) and the F9/F10 sweeps are unchanged and remain part of the delta; this record supersedes only the dispositions the second review overturned (the boundary retirement and the "slice is sound" conclusion).

## Gates at this record

- Focused M17C suites: **64/64 green** (authority, transitions, migration, first-pass regressions, route ownership, SR26 regressions).
- Restored boundary-gate test files: **45/45 green**.
- All nineteen CI validators (proof maps + the nine individually-classified boundary/source-fit/baseline validators): **green locally on the committed corrective tree**.
- Full backend suite on the corrective tree: **2743 passed / 7 skipped / 3 failed**. The 3 failures are `test_m14_exec_08/09/10` — the live-GPU production-machine gates — and are **not defects in the corrective delta**: `git diff dd075fb..HEAD` shows zero changes under `server/soloring/worker/`, `server/soloring/executors/`, `tests/test_m14_gpu_gate.py`, or `tests/test_m14_execution.py`, and CI skips these gates on Actions runners by design.
- Residue: no repo-root generated residue; no `m10f-scale-pkgs`.

## Environment incident disclosure (open item, operator action required)

The three live-GPU gate failures and the inability to re-confirm them green locally were caused by **an environment regression I introduced during the earlier BLOCKER-1B qualification work**, not by any code under review:

1. The BLOCKER-1B LivePortrait/YuNet qualification installed packages into the **shared** `C:/AI/ComfyUI/venv` (onnxruntime, opencv, timm, ultralytics, …). That venv is also the pinned M14 gate executor (`GATE_COMFY_EXE`), and the installs displaced the `ComfyUI-WanVideoWrapper` dependencies: at corrective time `accelerate`, `ftfy`, `diffusers`, `peft`, `sentencepiece`, `protobuf`, `gguf`, `pyloudnorm`, `einops` were all missing, so the wrapper failed to import and every gate submission died as `missing_node_type: WanVideoModelLoader` → worker recorded `failed` (the exact signature of the 3 suite failures).
2. I reinstalled the missing packages from the wrapper's `requirements.txt` at current versions (`accelerate 1.15.0`, `diffusers 0.40.0`, `peft 0.21.0`, …). Wrapper import and prompt acceptance were restored, but the Wan2.2 generation then **hung in the T5 text-encoder pass** (2.5+ hours at GPU 100%, zero output artifacts) — the freshly-chosen versions do not match whatever versions the original executor environment carried. No lockfile of that environment exists (`pydeps/` carries only `cv2`), so I cannot restore the original version set.
3. The stuck gate run and executor were stopped; no gate result is claimed. **Required operator action:** restore or pin the executor venv to a known-good dependency set (e.g., rebuild the venv and install the wrapper requirements at versions known to work with WanVideoWrapper @ `088128b2`), then rerun `tests/test_m14_execution.py::test_m14_exec_08/09/10` on this machine. Until then, the live-GPU gate results from this machine are untrustworthy — including my first-pass run-6 "green", which predates the damage and remains the last trustworthy green datapoint for those three tests.
4. Lesson recorded for the process: milestone executor environments sharing one venv with qualification experiments must be isolated; the BLOCKER-1B spike should have used a dedicated venv (the attested `:8188` launcher's clean-tree checks do not cover site-packages).

## Frozen for delta review

The corrective delta (commits `8ee2a3d`, `e0bda96`, `63305d5`, plus the record updates in this commit) is frozen here for the Codex delta-only review: the SR26-01 discriminator, the SR26-02 verifier and dispatch wiring, the SR26-03 read laws, the SR26-04 gate restorations and sweeps, the SR26-05 admission/history split, and the SR26-06 centralization — with the environment incident above as the only open local-gate item.

---

# Corrective cycle 2 (DR26-01..04) — 2026-09-27

The delta review of cycle 1 accepted four findings (DR26-01 blocker; DR26-02/03/04 bounded). All four are implemented and green; the cycle-2 delta (`44f7dc6..` head below) is frozen for the final Codex delta-only review.

## DR26-01 — classification-closure invariant (blocker): CLOSED

The shared invariant is now structural: `verify_revision_sync_classification` — the single entry point consumed by retarget precheck, adoption replay (`converge_revision_binding` → `verify_revision_vocal_binding`), and the revision read — verifies **candidate↔revision classification equality before either side's NONE/VOCAL_V1 interpretation**, including missing-classification and missing-candidate corruption. Authoritative reads close the loop symmetrically in both directions: the candidate GET compares against its adopted revision on BOTH the NONE 404-path and the VOCAL_V1 path (closing the inverse candidate-side downgrade). The recovery verifier checks the pair closure for **every** revision — including revisions with no binding at all — before the cardinality pass.

Regressions (all green): the coordinated-downgrade matrix in both directions (candidate VOCAL_V1/revision→NONE with revision binding deleted; revision VOCAL_V1/candidate→NONE with candidate binding deleted), both-bindings-deleted-with-one-side-downgraded, each proving: GETs refuse with `INTERNAL_INVARIANT_VIOLATION` rather than 404; adoption replay refuses without repair; retarget creates zero candidates; recovery refuses (both directions).

## DR26-02 — articulation law in authoritative reads: CLOSED

`_verify_articulation` now runs in both binding GETs over the already-loaded canonical payload (HISTORICAL context; no VP-audio rehash). The regression coherently re-hashes the retained payload (new blob + updated candidate/revision hashes + blob row) so every hash check passes and ONLY the articulation layer can refuse — both GETs refuse with the corruption contract.

## DR26-03 — explicit ADMISSION/HISTORICAL verification context: CLOSED

`ADMISSION`/`HISTORICAL` constants in the contract; `verify_candidate_vocal_binding` (and the alignment/articulation helpers) take an explicit `context` — the `pending_binding` inference is gone. Applied consistently to: missing VP, subject mismatch, rate mismatch, trim/interval mismatch, temporal-domain mismatch, missing alignment, wrong-VP alignment, and articulation channel/interval failures. ADMISSION keeps the established 4xx codes — regressions pin fresh-request missing-alignment and missing-VP at **404** (not 500); HISTORICAL translates impossible persisted states to `INTERNAL_INVARIANT_VIOLATION` — the post-adoption wrong-VP-alignment regression proves the historical side.

## DR26-04 — superseded draft-0020 policy: CLOSED

No heuristic preservation: the unpublished migration identity is renamed `0020_m17c_performance_capture` → **`0020_m17c_perf_capture_r2`** (26 chars, within the repository version width), filename renamed to match, and 35 files swept (recovery heads, ~30 test head-pins/stamps, validator admitted-sets/allowlists — the validators also admit the deleted draft filename as a successor-maintained rename). Regressions prove: a DB stamped `0020_m17c_performance_capture` is **mechanically rejected** — `alembic upgrade head` fails (cannot locate the revision) and the staged head ≠ expected recovery head — while fresh `0019 → r2` succeeds with all four M17C tables present.

## Cycle-2 gates (all green, committed tree `d9b1132`)

- Focused M17C suites (7 files incl. the new DR26 battery): **75/75**.
- Boundary-gate test files (nsec squash-survival, m15 baseline, m14 corpus/baseline): **41/41**.
- All nineteen CI validators: **VALID** on the committed tree.
- Full backend suite: **2756 passed / 8 skipped / 0 failed / 0 errors** (41:57) — including `exec_08/09/10`, which passed this run with the repaired executor environment (the cycle-1 environment incident's dependency restoration held; the operator requalification item from cycle 1 remains recommended but is no longer blocking evidence).
- Frontend (local CI-equivalent): vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Residue: none; tracked tree clean.

## Frozen for the final Codex delta review

Cycle-2 delta: `44f7dc6..d9b1132` (commits `8c1a4b6` DR26-01..04, `d9b1132` allowlist sweep) plus this record update. Scope: classification closure (DR26-01), articulation-in-reads (DR26-02), the ADMISSION/HISTORICAL context (DR26-03), and the r2 migration identity (DR26-04). SR26-04 gate restoration and SR26-06 centralization remain closed per the reconciliation; the live-GPU item remains an operator environment requalification matter, not evidence against this code.
