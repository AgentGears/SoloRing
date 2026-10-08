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

---

# Corrective cycle 3 (C2-01..04) — 2026-09-27

The final delta review accepted four findings (C2-01/02/03 blocking; C2-04 evidence defect). All four are implemented per the prescribed minimal shapes; DR26-02 and DR26-04 remain resolved (not regressed); the cycle-3 delta `1a920d0..` head below is frozen for the final delta-only review of exactly that range.

## C2-01 — complete adopted-pair closure: CLOSED

Implemented exactly the preferred minimal shape (no new bespoke pair verifier): `verify_revision_sync_classification` now (1) loads the adopted candidate, (2) calls `verify_candidate_sync_classification` — the candidate-LOCAL verifier with its full cardinality law, not a bare classification fetch — then (3) validates the revision's own classification/schema/cardinality and (4) requires mode equality before (5) returning. One non-recursive call proves candidate-local cardinality + revision-local cardinality + pair equality. The candidate authoritative GET invokes that full revision verifier on BOTH return paths (honest-NONE 404 and binding-return) whenever the candidate is adopted, replacing the two branch-local comparisons; the revision GET already calls it before its 404 path.

Regressions (all green): V1/V1 pair with ONLY the revision binding deleted — candidate GET **500** (the previously escaping case), revision GET 500, replay refuses, retarget zero candidates, recovery refuses; NONE/NONE genuine M17B pair with an injected candidate binding — both GETs 500, replay refuses, recovery refuses; lawful NONE/NONE keeps honest 404s on both GETs (and the pre-existing B06/X-cells confirm no regression).

## C2-02 — finished ADMISSION/HISTORICAL semantics: CLOSED

`performance_kind`: the transition-verifier branch is context-aware (admission keeps the 422; an impossible persisted kind corrupts), and the read law (`_read_binding_scalar_laws`) corrupts on an impossible persisted kind for both GETs. Project closure: `verify_vocal_performance_integrity` is now context-neutral — it verifies the VP's physical/identity closure and RETURNS the VP/DialogueLine project id; the comparison lives in `verify_candidate_vocal_binding` under its explicit context (admission → `PERFORMANCE_VOCAL_PROJECT_MISMATCH` 422; historical → corruption), and the reads prove project agreement through the VP's DLR/DialogueLine chain (no audio rehash). Regressions: fresh BODY-kind request keeps 422; persisted kind corruption → 500 (replay + GET); fresh cross-project VP keeps 422 with the exact code; persisted project disagreement → 500 (GET + replay).

## C2-03 — revision-owned temporal-domain law: CLOSED

Generic `_temporal_domain` helper over any object carrying the four temporal columns. The candidate GET validates against the candidate domain; the revision GET validates against the REVISION's own domain (matching recovery's revision-owned check). The regression tampers ONLY the revision's `temporal_end_num` (candidate untouched): the revision GET refuses 500 while the candidate GET stays a lawful 200 — proving the revision-owned law specifically — and the staged recovery refuses the same state (first observed via the predecessor closure law, which independently rejects the de-cohered revision; both refusals are corruption-contract).

## C2-04 — non-vacuous inverse recovery proof: CLOSED

The staged inverse state now deletes the candidate binding (candidate-local law fully satisfied: NONE + no binding) while the revision stays VOCAL_V1 with its binding intact, so the refusal can only come from the cross-pair classification disagreement — and the test asserts the word "classification" in the corruption message so a future earlier local check cannot silently make it vacuous again.

## Cycle-3 gates (committed tree `30bddf0` + record)

- C2 regression battery: **9/9**; C2+DR26: **20/20**; full M17C battery incl. M17B-interaction files (`test_m17b_matrix`, `test_m17b_recovery`): **127/127**.
- All nineteen validators: **VALID** (after admitting the new `test_m17c_c2_regressions.py` to the hygiene/nsec allowlists and the CI focused list).
- Full backend suite: **2763 passed / 8 skipped / 2 failed** — the 2 failures are `exec_09/exec_10`, and both **passed on immediate individual rerun** (146s / 227s) with the executor up; `git diff 1a920d0..HEAD` shows zero changes under the worker/executor/gate sources, so these are the known live-GPU flake class, not cycle-3 regressions.
- Frontend (local CI-equivalent): vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Residue: none; tracked tree clean.

## Frozen for the final delta review (cycle 3)

Cycle-3 delta: `1a920d0..30bddf0` (commit `8ddec61` C2-01..04, commit `30bddf0` allowlist sweep) plus this record update. Review scope per the handoff: exactly `1a920d0..NEW_HEAD`. No merge, no ready-mark, no M17C-B start until this cycle clears.

---

# Corrective cycle 4 / final (C3-01..02) — 2026-09-27

The final review verified both residuals against `40664f7`. Both are corrected here; C2-01/C2-03 remain closed, and C2-02/C2-04 now close through C3-01/C3-02 respectively. No other finding, gate, migration, recovery architecture, discriminator, retarget, timing, articulation, or vocabulary surface was reopened.

## C3-01 — VP verification split by cost; GETs prove full structural authority: CLOSED

`verify_vocal_performance_integrity` is refactored into two layers with **identical composite behavior** (transitions/recovery keep the full existing law set; nothing was weakened):

- `_verify_vp_structural_authority(session, vp)` — the CHEAP verifier, **no retained blob read/hash/WAVE inspection anywhere**: adopted VocalCandidate exists; adopted-exactly-once (a structural count law); every immutable VP copied-authority field equals the adopted candidate — explicitly including `dialogue_line_revision_id`; VocalCandidate provenance closed grammar/canonical bytes/hash/source-kind (pure column computation, no media reads); VP DialogueLineRevision exists and matches the adopted candidate's; VP speaker == DLR speaker; DialogueLine exists; speaker CreativeEntity exists and belongs to that project; **returns the authoritative VP/DialogueLine project id**.
- `_verify_vp_physical_media(session, settings, vp)` — retained blob existence/integrity/rehash, WAVE validity, sample rate, sample-frame count, authoritative trim containment.

The composite `verify_vocal_performance_integrity = structural + physical` (admission, adoption/replay/retarget, and recovery continue paying the full price). The binding GETs' project law (`_read_project_law`) now runs the **full structural verifier** — replacing the too-weak VP→DLR→DialogueLine-only check the review flagged — then requires the verified VP project to equal the reading parent's project. No retained VP audio bytes are read or rehashed on either GET.

**Adversarial regression (green):** repoint ONLY `vocal_performance_revisions.dialogue_line_revision_id` at an alternate same-project/same-speaker DLR — binding VP id, candidate/revision bindings, speaker, project, alignments, retained audio all unchanged, so every shallow GET check stays apparently valid — both GETs refuse with `INTERNAL_INVARIANT_VIOLATION` on the VP↔VocalCandidate structural closure, and staged recovery refuses the same state.

**Cost-boundary proof (green, direct):** a spy on the `soloring.performance.vocal._verify_blob` seam (the only VP-retained-audio read/hash path in the M17C verifier stack; the candidate payload storage used by `verify_candidate_integrity` is a different, unpatched path, so the seam is unambiguous) proves both lawful GETs return 200 with **zero** invocations of the retained-media verifier.

## C3-02 — branch-specific inverse recovery proof: CLOSED

The recovery verifier's cross-pair branch now emits the stable diagnostic marker `PAIR-CLASSIFICATION-DISAGREEMENT:` with both conflicting modes. The inverse fixture is unchanged conceptually (both sides locally cardinality-valid: candidate NONE + no binding; revision VOCAL_V1 + binding intact) and the assertion now requires the marker + "adopted candidate" + `'VOCAL_V1'` + `'NONE'` — unsatisfiable by a missing classification, malformed schema, NONE+binding, VOCAL_V1+missing-binding, or any unrelated classification error.

## Cycle-4 gates (exact, committed tree `6f9a72d`)

- C3 regressions **2/2**; full corrective battery (C3+C2+DR26+SR26+authority+transitions+migration+first-pass+route-ownership+M17B matrix+M17B recovery): **129/129**.
- All nineteen validators: **VALID** (after admitting `test_m17c_c3_regressions.py` to the hygiene/nsec allowlists and the CI focused list).
- Full backend suite: **2767 passed / 8 skipped / 0 failed / 0 errors** in 2:28:34 — a fully-green first pass **including the three live-GPU exec gates** (the run was long because the pinned Wan2.2 executor ran cold after the earlier environment work; no GPU flake occurred and no rerun was needed).
- Frontend (local CI-equivalent): vitest **143/143** (32 files), `tsc --noEmit` clean (0 errors), `next build` succeeds.
- Residue: none; tracked tree clean.

## Frozen for the final delta review (cycle 4)

Cycle-4 delta: `40664f7..NEW_HEAD` (commit `6f9a72d` corrections+regressions+allowlist sweep, plus this record update). Review scope per the handoff: exactly `40664f7..NEW_HEAD`, focused on (1) the structural-vs-physical VP verification split, (2) GET structural closure completeness, (3) confirmation GETs do not rehash VP audio, (4) the C3-02 branch-specific recovery proof, and (5) direct regressions caused by the small refactor. If clean with no new authority defect, M17C-A can be frozen technically sound and work can proceed to M17C-B while PR #26 remains draft.

---

# M17C-B — PF-02 Shot Performance working mappings + readiness — 2026-09-27

**Final reconciliation disposition:** M17C-A technically closed at `c502b81` (final review PASS; no further corrective cycle). M17C-B began immediately after per the handoff, treating `c502b81` as the frozen baseline. **No M17C-A invariant was weakened or reinterpreted** — every M17C-A surface touched here is consumed, not modified (see predecessor-impact note below).

**Primary-review supersession:** the M17C-B primary review returned **NO-GO at `f39eb9f`** (findings B-F1..B-F9). The "Delivered" description below documents the pre-correction state and is superseded where the B-F corrective cycle (appended at the end of this record) changes it — most materially the migration split (B-F1): this implementation modified `0020_m17c_perf_capture_r2` **in place**, which is not what shipped; the corrected tree restores its exact `c502b81` bytes and moves the working-mapping table to successor migration `0021_m17c_shot_performance_mappings`. The predecessor-impact note below is likewise superseded.

## Delivered (frozen R4 §8–§9, §17, §19, §21 M17C-B slice)

- **Migration:** `0020_m17c_perf_capture_r2` (draft-mutable per plan) gains `shot_performance_segment_mappings` — mutable working intent, PK `(shot_id, position)`, FKs RESTRICT to `shots` + `performance_revisions`, named CHECKs matching the ORM exactly, PR index, covered by the populated-downgrade fence.
- **Service** (`m17c_shot_mapping.py`): PUT/DELETE/list + readiness projection. Dialogue-bound detection goes through the M17C-A pair verifier (classification + both sides' cardinality + closure BEFORE mode interpretation). Dialogue-bound law set: `vocal_mapping_position` mandatory; paired `ShotVocalSegmentMapping` exists on the same Shot; its VP == the immutable revision-binding VP; rate equality; vocal source interval inside the binding interval; CURRENT-selection policy at PUT (409); and the exact induced interval/anchor with ZERO tolerance (`P0 = origin + (v0−s0)·1000/rate`). Generic law set: `vocal_mapping_position` prohibited; nonempty interval inside the immutable PR domain; picture intersection (J/L-cut lawful); project agreement.
- **Readiness** (never persisted): `READY / STALE_VOCAL_SELECTION / BLOCKED_BINDING_INTEGRITY / BLOCKED_TIMING_MISMATCH / BLOCKED_SUBJECT_OR_PROJECT / BLOCKED_CHANNEL_CONFLICT / BLOCKED_SHOT_DEPENDENCY` + the pairwise channel-conflict law computed from immutable payload channel keys (not `performance_kind` labels). Selection change projects STALE and never mutates rows; restoring the exact VP restores readiness.
- **API:** `PUT/DELETE/GET /shots/{shot_id}/performance-segments[/{position}]`, `GET /shots/{shot_id}/performance-readiness` — closed schemas, raw rational `{num, den}` inputs, seven new centralized `ErrorCode` members (corrected by the B-F cycle from an earlier "six"; `errors.py:308–314`; `PERFORMANCE_CAPTURE_NOT_READY` is registered for the frozen §17 capture-refusal grammar and has no live consumer in this slice).
- **Recovery:** the M17C verifier gains working-mapping laws per frozen §13.3 — canonical bytes/hash, rational canonicality, project/reference integrity, VOCAL_V1↔vocal_mapping_position pairing in both directions, and STALE-tolerant (a lawfully STALE mapping is a lawful stored working state; current selection is not historical truth during backup validation).

## Predecessor-impact note (per the final reconciliation requirement)

No M17C-A law, migration row, or verifier branch was modified; M17C-B only **consumes** `verify_revision_sync_classification` and the binding rows. The one addition inside an existing M17C-A file is the working-mapping verification function **appended** to `m17c_verifier.py` (a new law for the new table). Fixture sweeps touched only predecessor test assertions about table sets/heads (mechanical, in-file precedent).

*(Superseded by the B-F cycle — the migration claim was wrong: this implementation modified `0020` in place. The corrected tree restores it byte-identical to `c502b81`; see the corrected predecessor-impact statement in the B-F section. The "law/verifier-branch" part of the claim held.)*

## M17C-B gates (committed head `f505fd2`)

- D01–D16 battery + regressions: **20/20** (new `test_m17c_shot_mapping.py`, wired into the CI focused list).
- Full M17C battery incl. M17B interaction files (`test_m17b_migration/matrix/recovery/source_gate`): **160/160**.
- All nineteen validators: **VALID** (after `m14_validate_source_fit` admitted `m17c_shot_mapping.py` as a reviewed successor path — commit `f505fd2`).
- Full backend suite: **2787 passed / 8 skipped / 0 failed / 0 errors** in 57:09 — fully-green first pass including the three live-GPU exec gates; no flake, no rerun.
- Frontend (local CI-equivalent): vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- **CI run `36346081441` at head `f505fd2a0b76f0d5a2594c96066cb9d7c6aab8bc`: SUCCESS, first attempt.**
- Residue: none; tracked tree clean. PR #26 remains open, unmerged, draft.

---

# M17C-B corrective cycle (B-F1..B-F9) — 2026-09-28

The controlling primary review returned **NO-GO at `f39eb9f`** with findings B-F1..B-F9. All nine are implemented; this section is the corrected primary register for the delta `f39eb9f..f0a9e32` (commits `6dca4e2` corrective delta + `f0a9e32` validator fix-forward). PR #26 remains draft.

## B-F1 — migration identity immutability (blocker): IMPLEMENTED

`0020_m17c_perf_capture_r2.py` restored **byte-identical to the frozen `c502b81` form** (verified at the commit: `git diff c502b81 6dca4e2 -- <file>` = 0; creates only the four PF-03 companion tables). Successor migration `0021_m17c_shot_performance_mappings` creates `shot_performance_segment_mappings` (PK `shot_id+position`, FKs RESTRICT, named CHECKs matching the ORM, `ix_spsm_pr`); downgrade refuses on populated rows with a count fence naming the table. Recovery: `EXPECTED_ALEMBIC_HEAD`/`SUPPORTED_RESTORE_ALEMBIC_HEADS` advanced to 0021; the 13-path M17B Blob-FK inventory shared (0021 adds no Blob FK); both `successor_semantics` dispatch chains run the M17C verifier at 0021, with the working-mapping pass conditional on table presence (lawful absent at 0020). 36-file head sweep with two special cases: `test_m17c_dr26_regressions` keeps its superseded-draft rejection strings and pins the fresh-0019 upgrade target to the frozen `0020` identity (mapping table's lawful absence asserted there); the frozen 0020 file itself excluded from the sweep.

## B-F2 — downstream PerformanceRevision integrity seam: IMPLEMENTED

`verify_performance_revision_for_shot_use(session, settings, pr, *, media)` is the ONE seam PF-02 consumes. `media=True` (PUT — fresh authority) pays the FULL M17C-A verifier including retained media; `media=False` (readiness/list — the C3-01 read cost boundary) proves full structural closure without VP-audio rehash via `verify_revision_vocal_binding_structural` (classification/pair closure, binding canonical bytes on BOTH sides, candidate↔revision binding semantic equality, VP structural authority, adopted-candidate immutable payload closure). No PF-02 path reads raw binding scalars without the seam. Regressions: revision-binding hash tamper, coherently-rehashed candidate↔revision divergence (FK-satisfying REAL alternate VP so only the equality law can refuse), and candidate binding-bytes tamper each refuse PUT with **zero new mapping rows** and fail readiness/list closed (500 `INTERNAL_INVARIANT_VIOLATION`, never a 4xx stale answer).

## B-F3 — applicability from the discriminator: IMPLEMENTED

Mode gating reads `classification.sync_mode` only; `_verify_stored_mapping(row, pr, *, expected_mode)` enforces the mode/position shape law BEFORE any current-context law. Regressions prove the escape with canonical JSON/hash COHERENTLY rewritten (so only the shape law can refuse, not B-F6): VOCAL_V1 with NULLed position and generic with a position each refuse readiness as corruption.

## B-F4 — supported-DELETE vs recovery-corruption boundary: IMPLEMENTED

Live: a missing paired vocal mapping (API-creatable via the supported DELETE) is the lawful `BLOCKED_BINDING_INTEGRITY` working state; VP-id divergence of an EXISTING pair is corruption. Recovery (`_verify_shot_performance_mappings` rewritten): same split — the missing pair is preserved and everything else about the row verified; shape violations and pair VP divergence refuse.

## B-F5 — current-duration revalidation: IMPLEMENTED

`_project_one` revalidates the stored mapping's picture intersection against the CURRENT `shot.duration_ms` (and blocks on missing/nonpositive duration) → `BLOCKED_TIMING_MISMATCH` without rewriting stored intent. Regression: the lawful L-cut `[0,4500)@2000` is READY at duration 3000 and BLOCKED at 1000 with the stored row bytes and hash unchanged.

## B-F6 — stored-mapping integrity verifier: IMPLEMENTED

Schema version, per-column rational canonicality, canonical JSON/hash reproduction, nonempty interval, immutable-PR-domain containment, and the B-F3 mode shape — one verifier gating live reads. Regressions: stored hash tamper and a noncanonical persisted rational (0/5) refuse readiness/list closed.

## B-F7 — full recovery battery: IMPLEMENTED

New `tests/test_m17c_bf_recovery.py` (**9/9**): clean round trip preserving mapping rows byte-for-byte at head 0021; lawful blocked working-state round trip (missing pair preserved through backup/restore); **staged migration proof** — a REAL 0020-stamped database (a backup reshaped to exactly a 0020 database's shape: version stamped `0020`, mapping table dropped) upgraded to 0021 via the alembic CLI **retains every PF-03 row** (binding hashes identical before/after), gains the empty mapping table, and passes the FULL M17C recovery verifier afterwards — no rebuild of valid M17C-A draft databases required; adversarial matrix — canonical-hash tamper, noncanonical rational, cross-project revision (coherently rehashed so only the project law can refuse), both mode/position shapes (coherently rehashed), and a coordinated pair-VP divergence (the vocal mapping coherently rehashed to a REAL alternate VP so the M17A vocal verifier passes and only the mapping-pair law refuses) each refuse restore fail-closed.

## B-F8 — M17A missing-selection-row semantics: IMPLEMENTED

`_selection_posture`: a MISSING `VocalPerformanceSelection` row is corruption (every DLR is created with one) at PUT and readiness; lawful UNSET/different selection is STALE. Regressions: deletion refuses PUT (never a stale 409) and readiness, and the projection recovers exactly when the lawful row shape is restored; UNSET (all-three-null per `ck_vps_selection_shape`) projects `STALE_VOCAL_SELECTION` with `selection_state: UNSET`.

## B-F9 — record accuracy: this section

## Secondary cleanups (same cycle)

- `PerformanceSegmentPut.vocal_mapping_position` and the path `position` carry SQLite-i64 bounds (`le=2**63-1` in schema and service).
- Duplicate `created_at` removed from `PerformanceSegmentRead`.
- Error-code count corrected: **seven** new centralized members (`errors.py:308–314`). `PERFORMANCE_CAPTURE_NOT_READY` is registered for the frozen §17 capture-refusal grammar and has **no live consumer in this slice** — recorded as-is.
- **Concurrency narrowed and proven** (`test_m17c_bf_regressions`): sequential same-position PUTs converge last-committed-wins to exactly one row; truly concurrent same-position PUTs serialize on SQLite's single writer — one request commits its exact payload and the loser's unique-key/write-lock race escapes the app **untranslated** (an unhandled 5xx under a real server; an ASGI-transport exception under test transport) — never a duplicate or torn row, and the projection surface stays live afterwards. "Last committed PUT wins" is therefore the SEQUENTIAL upsert contract, not a claim about parallel-request ordering.

## Predecessor impact (corrected, supersedes the note above)

The initial M17C-B implementation modified migration `0020` **in place** — the delivered-state section's "no M17C-A migration row modified" claim was wrong. The corrected tree restores `0020` byte-identical to `c502b81`. Every other M17C-A surface is consumed, not modified; the working-mapping verification function remains the one M17C-B-owned addition inside `m17c_verifier.py` (its B-F4 pairing-law rewrite is confined to that function).

## Gates (corrected tree)

- New B-F regression battery: **12/12**; new B-F7 recovery battery: **9/9**.
- Focused M17A/M17B/M17C battery (27 files incl. migrations and M17B interaction): **319/319**.
- All 21 validator scripts green against the committed tree. Disclosed exactly: my first standalone runs of the two npm-audit validators failed on empty stdin (my invocation error — they consume `npm audit --omit=dev --json` via stdin); corrected invocation green, no environment or product failure. Six boundary/baseline validators required admitted-set repair (the head sweep had RENAMED their M17C-A admission entries to 0021 instead of admitting 0021 alongside the still-present frozen 0020); both migrations now admitted with per-file table sets in the hygiene validator. `test_m10a` chain-tail and `test_m7c` count companions completed for 0021; `test_m15_baseline`'s head listing is commit-dependent (proven via stash round-trip: the pre-cycle assertion passes against the pre-commit tree, the corrected one against the committed tree).
- Full backend suite (local, first run on the uncommitted corrective tree): **2806 passed / 8 skipped / 3 failed** in 58:00. The 3 failures are the `test_m10a` chain-tail, `test_m7c` count, and `test_m15` head-listing companions above — my sweep's incomplete companion assertions, fixed in the same cycle; the two glob-based files green post-fix locally, the head-listing one green at the committed tree. No rerun of the full local suite: **CI on the committed head is the full-suite authority** (below).
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- **CI run `36379941278` at `6dca4e2`: FAILURE, attempt 1 — Backend job, "Hygiene boundary" step.** Root cause: the hygiene and next-security allowlists enumerate M17C test files by exact name; the two new B-F battery files were untracked during local validation and entered the changed-set only once committed. Not a flake, not an environment failure — my commit-dependent fallout, reported as the first-run result. Fixed forward in `f0a9e32` (both batteries admitted; the 0021 migration prefix admitted to the next-security backend slice; all 21 validators then green against the committed tree, validator-gate tests 15/15).
- **CI run `36380259599` at `f0a9e32`: SUCCESS, attempt 1** (Backend **2797 passed / 20 skipped / 0 failed** in 30:22 — GPU gates skipped on Actions runners by design; Frontend green).
- Residue: this cycle's only new files are the three intended sources (0021 migration + two batteries) plus this record; no new repo-root generated residue.
- Live-GPU exec gates: no GPU/evidence/certification work in this delta; the BLOCKER-1B executor-venv operator item recorded above remains the standing caveat for local GPU runs (CI skips those gates by design).

## Frozen for the independent second review

Delta `f39eb9f..f0a9e32` exactly (two commits: `6dca4e2`, `f0a9e32`). No merge, no ready-mark, no Codex invocation yet — the corrected first pass freezes here and the independent second review of exactly this range is the next protocol step, per the controlling disposition.

*(Superseded: the independent second review of that delta returned **NO-GO with ten findings (SR2-01..SR2-10), all accepted** — see the SR2 cycle below. The B-F section above remains historical evidence; its "B-F1..B-F9 all implemented" statement is superseded where SR2 overturned it (most materially B-F4's paired-VP-divergence-as-corruption premise and B-F2's incomplete seam).)*

---

# M17C-B SR2 corrective cycle (SR2-01..SR2-10) — 2026-09-28

The independent second review of `f39eb9f..f0a9e32` found six High, three Medium, and one Low residual/new finding; the reconciliation accepted all ten. **Product correction base: `f0a9e32`** (the later `b74aa73` record commit is documentation-only and is not the review base). Corrected code head: **`a5f9d2d`** (`eb47648` product correction + `a5f9d2d` validator carve). No M17C-C started; PR #26 remains open, draft, unmerged.

## SR2-01 — restore the lost 0020 head (blocker): IMPLEMENTED

`M17C_A_ALEMBIC_HEAD = "0020_m17c_perf_capture_r2"`, `M17C_B_ALEMBIC_HEAD = "0021_m17c_shot_performance_mappings"`, `EXPECTED_ALEMBIC_HEAD = M17C_B_ALEMBIC_HEAD`; both distinct heads in `SUPPORTED_RESTORE_ALEMBIC_HEADS`, sharing the 13-path M17B Blob-FK inventory (the policy tuple already keyed on the constants). Audit findings fixed beyond the constant: the **manifest writer** hardcoded `EXPECTED_ALEMBIC_HEAD` and now records the ACTUAL staged head; the **M14-observation dispatch set** had silently dropped 0021 (the sweep added `M17C_B` to five of six sets only) and is restored; **four historical recovery tests** (m12/m13/m14-derived/m16) hardcode the expected supported-head set and regain the `0020` entry the original sweep renamed away. The **backup-side staged-head guard deliberately keeps the M12-era staleness law** (exactly the EXPECTED head — a stale-headed live database must migrate before backing up as current): an earlier draft of this correction loosened it to "any supported head", the local full suite's four historical-test failures exposed that as an overreach, and it was reverted; SR2-01's restorability requirement is satisfied RESTORE-side (below). Tests: distinct-heads/membership; a genuine 0020 backup tree (a real current backup reshaped to the 0020 identity: PF-02 table dropped, staged head + canonical manifest both 0020) restores successfully with PF-03 rows intact and restored head exactly 0020; an unknown future head refuses at the backup guard.

## SR2-02 — head-aware M17C recovery verifier (blocker): IMPLEMENTED

`verify_m17c_binding_state(staged_db, blob_root, *, head)` receives the exact staged head from BOTH successor-dispatch chains. At 0020: four PF-03 tables required and the PF-02 table MUST be absent. At 0021: the PF-02 table REQUIRED plus a deterministic physical-schema proof — PRAGMA `table_info` (exact columns, nullability, `shot_id`+`position` PK ordinals), `foreign_key_list` (both FKs with `RESTRICT`), `ix_spsm_pr` as an origin-`c` CREATE INDEX on exactly `performance_revision_id`, and the six named CHECK constraints in the sqlite_master DDL. Adversarial tests: 0021 + dropped table refuses; 0021 + malformed substitute table refuses on the column contract; 0020-genuine restores; 0020 + illicit successor table refuses at restore. (Development note, recorded: the first schema proof read `index_list`'s uniqueness flag instead of its origin column — caught by the SR2 battery itself.)

## SR2-03 — paired-vocal VP drift is lawful blocked working state (blocker): IMPLEMENTED

Live `_project_one`: a paired vocal mapping whose VP differs from the immutable revision binding projects `BLOCKED_BINDING_INTEGRITY` with drift diagnostics (paired vs bound VP ids) — never 500; neither row is rewritten during diagnosis. Recovery: the pair-VP refusal is REMOVED (missing pair and repointed pair are both preserved lawful working states; shape violations stay corruption). The B-F regression asserting refusal for that state is superseded and replaced by the **API-only 11-step lifecycle**: lawful READY world → select VP-B → supported M17A PUT repoints the existing vocal position to VP-B → readiness `BLOCKED_BINDING_INTEGRITY` → backup/restore succeeds with both rows byte-identical → restored readiness re-projected (against the restored tree) still blocked → select VP-A + PUT the pair back → readiness READY. A companion regression guards the creation law: a FRESH PF-02 PUT pairing a drifted position still refuses 422 `PERFORMANCE_VOCAL_MAPPING_MISMATCH`.

## SR2-04 — immutable PerformanceRevision copied closure (blocker): IMPLEMENTED

Both seam grades now run, BEFORE any PF-02 consumption of revision authority: adopted-candidate integrity + `revalidate_winner(pr, candidate)` (the frozen M17B `_CLOSURE_FIELDS` equality + `validate_adoption_metadata`), with admission-shaped grammar failures TRANSLATED to `INTERNAL_INVARIANT_VIOLATION` (a draft leaked the adoption branch as 422 — caught by the battery and wrapped). Six-case revision tamper matrix (project, subject, temporal domain, payload blob/hash identity reusing a REAL blobs row so only the closure law can refuse, provenance hash, adoption metadata): each refuses PUT 500 with zero new rows for that Shot, fails readiness/list closed, and the backup-side recovery enumeration refuses with the matching closure/adoption fragment.

## SR2-05 — one shared read-grade PF-03 verifier (blocker): IMPLEMENTED

`verify_revision_vocal_binding_read_grade` is extracted from the authoritative binding GET (parent identity, candidate + source-candidate-binding presence, candidate↔revision binding equality, scalar laws incl. rate/trim/subject/kind, full cheap VP structural authority + VP/Performance project agreement, induced interval inside the REVISION-owned domain, candidate payload integrity, exact-VP cited alignments, articulation). The binding GET and the PF-02 read-grade seam consume THIS verifier; the weaker parallel `verify_revision_vocal_binding_structural` is DELETED. Neither grade touches retained VP audio/WAVE. Five coordinated-tamper regressions (BOTH binding rows coherently rehashed): wrong sample rate; real alternate same-line VP (on a cited-alignment world — see the seed fact below); out-of-trim interval; origin outside the revision domain; wrong-VP cited alignment — each refuses readiness with the targeted law's fragment and the backup-side enumeration refuses with the same law's recovery fragment (branch-specific). **Recorded seed fact:** the default fixture payload cites NO alignments, so on an uncited world a coordinated binding move to a same-line alternate VP is indistinguishable from lawful history and correctly manifests as SR2-03 working drift — the exact-VP laws bite only where alignments are cited (the production shape). **Recorded layering:** for the cited-alignment tamper, M17A's derivation-run-digest law (which embeds VP identity) refuses in recovery BEFORE the M17C cited-alignment law is reached; the state is refused either way and the regression pins the actual firing branch.

## SR2-06 — M17A stored integrity vs current Shot readiness (blocker): IMPLEMENTED (predecessor recovery correction, documented in-source)

M17A recovery's `_verify_mappings` no longer certifies current Shot duration (NULL/≤0) or current picture intersection — structural/authority laws only (canonical bytes/hash, rationals, VP existence/rate/trim, project agreement). Regression: the lawful L-cut mapping goes `BLOCKED_TIMING_MISMATCH` under both PATCH duration 1000 (shrunken, non-intersecting) and PATCH duration 0 (API-legal `ge=0`); backup/restore succeeds in both states with the mapping row byte-identical and readiness re-projected against the restored tree still blocked. No test pinned the removed refusals (verified by grep before the change).

## SR2-07 — M17A vocal PUT selection split (Medium): IMPLEMENTED

Missing selection row → `INTERNAL_INVARIANT_VIOLATION` 500; lawful UNSET/different selection → the existing 409 `VOCAL_MAPPING_SELECTION_STALE`; selected requested VP → ordinary validation. Regression covers all three.

## SR2-08 — concurrent same-position PUT (Medium): IMPLEMENTED (preferred solution)

`put_shot_performance_segment_mapping` now issues ONE atomic SQLite upsert (`INSERT ... ON CONFLICT(shot_id, position) DO UPDATE`): the canonical document/hash are constructed deterministically before persistence, the conflict path replaces the complete mutable mapping in a single statement, and `created_at` is not in the update set (preserved; regression asserts). Concurrent first PUTs serialize on SQLite's single writer and BOTH return ordinary 200s — no raw Python/SQLAlchemy/SQLite exception escapes. Regression runs under an `httpx.ASGITransport(raise_app_exceptions=False)` client: both responses 200, exactly one complete coherent row, projection live afterwards. The B-F-era regression that accepted an escaped exception as success evidence is rewritten to this contract; no deterministic parallel ORDERING is claimed.

## SR2-09 — DELETE position domain (Medium): IMPLEMENTED

One shared `_validate_position` (integer, bool excluded, `[0, 2^63−1]`) for PUT and DELETE, applied BEFORE any storage access. Regression: DELETE −1 and 2^63 → stable 422 `PERFORMANCE_SHOT_MAPPING_INVALID`; 2^63−1 → 204, idempotent, other rows untouched.

## SR2-10 — 0021 documentation (Low): IMPLEMENTED

The 0021 docstring now states: frozen M17C-A migration `0020_m17c_perf_capture_r2` retained UNCHANGED; NEW successor `0021` creates the PF-02 storage; 0021 was NOT frozen with M17C-A. Git-based history proofs added as tests: the frozen 0020 blob at HEAD equals the `c502b81` blob byte-for-byte; `0021` did not exist at `c502b81` (`cat-file -e` refuses); `0021.down_revision` equals the imported `M17C_A_ALEMBIC_HEAD` constant (no hand-typed identity).

## Gates (corrected tree, first-run dispositions recorded exactly)

- New SR2 battery (`test_m17c_sr2_regressions.py`): **20/20**.
- B-F regression battery **12/12**; B-F7 recovery battery **8/8** (the premise-overturned paired-VP refusal test replaced per SR2-03, noted in-file).
- Focused M17A/M17B/M17C battery incl. the historical recovery families (m12/m13/m14-derived/m15/m16 + all M17C files): **379/379**.
- All 21 validators green **on the committed tree** (the two npm-audit validators via piped stdin). Disclosed: my pre-commit validator runs could not see the then-untracked SR2 battery file — CI on `eb47648` failed the Hygiene boundary step for exactly that one path (run `36428413488`); the carve `a5f9d2d` admits it and all 19 standalone validators are green on the committed tree. This is the same commit-dependent-allowlist failure mode as the B-F cycle, now repeated despite the recorded lesson — the process fix (run gates against the COMMITTED tree before pushing) is recorded again in the commit message.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite, FIRST RUN: **2824 passed / 8 skipped / 4 failed** in **2:16:21** (wall time inflated by a concurrent user GPU workload — `systems_matrix.py` saturating the 12 GiB GPU for part of the run; the three live-GPU exec gates PASSED in-suite under that contention). The 4 failures were the m12/m13/m14-derived/m16 expected-head-set literals above (sweep fallout from the ORIGINAL 0020→0021 rename, exposed by restoring 0020 to the supported set) — all four fixed in `eb47648` and green in the focused rerun. No full local rerun claimed: **CI on the corrected code head is the full-suite authority** (below).
- Residue: this cycle's only new file is the SR2 battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `f0a9e32..a5f9d2d`** (`eb47648` product correction + `a5f9d2d` validator carve). CI: run `36428413488` on `eb47648` FAILURE (the allowlist fallout above, carve follows); **run `36428850548` on `a5f9d2d`: SUCCESS, attempt 1** (Backend **2816 passed / 20 skipped / 0 failed** in 27:55 — GPU gates skipped on Actions runners by design; Frontend green). Per the controlling disposition, the next protocol step after this freeze is ONE independent Codex delta-only review of exactly `f0a9e32..a5f9d2d` plus direct predecessor implications, WITHOUT this reconciliation register. No merge, no ready-mark, no M17C-C.

*(Superseded: the independent Codex review of that range returned four findings — IR-01..IR-04, all accepted and corrected below. The SR2 section above remains historical evidence.)*

---

# M17C-B IR corrective cycle (IR-01..IR-04) — 2026-09-28

The independent Codex review of `f0a9e32..a5f9d2d` returned four findings (two schema-certification exactness gaps, one error-contract seam gap, one shared position-domain gap); all four are accepted and implemented. **Product correction base: `a5f9d2d`** (the later `0d0f403` record commit is documentation-only ancestry inside the range and does not redefine the base). Corrected code head: **`e0c4e07`** (`4c80d80` product correction + `e0c4e07` validator carve). No M17C-C; PR #26 remains open, draft, unmerged.

## IR-01 — exact 0021 physical-schema certification: IMPLEMENTED

`_verify_spsm_schema` now proves the exact frozen migration-0021 storage contract: declared column types per `PRAGMA table_info` (`VARCHAR(36)` ids, `INTEGER` scalars/rationals/version, `TEXT` payload/timestamps — arbitrary TEXT/BLOB substitutions refused), the complete FK contract (source column, target table/column, `ON DELETE RESTRICT`, and the deterministic `ON UPDATE`/`MATCH` values), and `ix_spsm_pr` as a non-unique, non-partial, origin-`c` CREATE INDEX over exactly `performance_revision_id` (a UNIQUE or partial replacement refuses). CHECK constraints are proven as **exact stored-name + normalized semantic-expression pairs** via a balanced-paren, quote-aware DDL parser — `CONSTRAINT ck_…_ck_spsm_position CHECK(1)` keeps the name but diverges on the expression and refuses. Recorded: the stored names carry the SQLAlchemy naming-convention table prefix (`ck_<table>_ck_spsm_…`) — identical in the ORM and alembic renderings (probed against both before pinning the contract). Six surgical DDL refusals proven (position CHECK(1), denominator CHECK(1), UNIQUE index, partial index, INTEGER→TEXT, VARCHAR(36)→VARCHAR(64)); the malformed-substitute case remains in the SR2 battery.

## IR-02 — exact frozen-0020 PF-03 schema certification at BOTH heads: IMPLEMENTED

All four migration-0020 tables are physically certified at head 0020 AND head 0021 (the successor inherits 0020 physically and does not weaken its certification): exact columns/types/nullability, one-column parent PK, RESTRICT parent + VP FKs, and every named CHECK expression (binding tables: start-nonneg, sample order, rate positive, origin denominator, sync basis = 1, binding schema = 1, and the 64-char lowercase-hex hash grammar; classification tables: the `sync_mode IN ('NONE','VOCAL_V1')` vocabulary and schema version). The schema phase runs BEFORE semantic row traversal, and structural failures translate to the recovery-corruption contract (never a raw `sqlite3.OperationalError`). Matrix: 4 tables × 5 weakenings (CHECK(1), missing FK, wrong declared type, wrong PK, missing column) at 0020, plus representative predecessor-schema tampering at claimed 0021; the four SR2 restore behaviors (genuine 0020 restore, genuine 0021 restore, 0020 rejects the successor table, 0021 requires the exact PF-02 table) are preserved and re-anchored in the IR battery.

## IR-03 — shared persisted-history candidate-integrity seam: IMPLEMENTED

`revision.verify_candidate_integrity_historical` wraps the FULL existing `verify_candidate_integrity`: same underlying verifier; already-correct historical `INTERNAL_INVARIANT_VIOLATION` 500s pass through; admission-shaped `SoloRingError` failures are translated to `INTERNAL_INVARIANT_VIOLATION` 500 with the original diagnostic preserved; fresh creation still calls the plain verifier and keeps its 4xx. Wired at every persisted-authority consumer: the PF-02 seam (both media grades), the candidate and revision authoritative binding GETs, the shared read-grade verifier, and the persisted candidate-binding verification (non-ADMISSION contexts). **Battery-exposed completeness gap fixed:** the revision-side authoritative read never proved the revision↔candidate copied closure, so a candidate-side subject tamper was invisible to the revision binding GET — `revalidate_winner` (closure + adoption metadata, admission-shaped failures wrapped) now runs inside the read-grade verifier as well. Candidate tamper matrix (revision untouched: payload dual-hash disagreement, coherent real-blob payload-identity swap, provenance hash, provenance-JSON canonicality, temporal-domain law, subject disagreement): each refuses PF-02 PUT (500, zero new rows), readiness/list (500), BOTH binding GETs (500), and the backup-side recovery enumeration; fresh malformed requests keep the admission 4xx on both the closed-schema layer (`VALIDATION_ERROR`) and the semantic grammar layer (`PERFORMANCE_VOCAL_INTERVAL_INVALID`). Recorded: candidate `payload_schema_version` and `performance_profile_id` are DB-CHECK-pinned (`ck_pc_payload_schema`/`ck_pc_profile`) — column tampering is mechanically impossible, so the "payload schema/profile" category is covered by the coherent real-blob identity swap instead.

## IR-04 — one shared SQLite-safe position domain: IMPLEMENTED

The low-level law lives in ONE neutral primitive (`temporal.validate_mapping_position`: actual integer, bool prohibited, `[0, 2^63-1]`, `PositionError`), consumed by BOTH services' PUT **and DELETE** — M17A `ShotVocalSegmentMapping` (keeping its `INVALID_SAMPLE_INTERVAL` vocabulary; DELETE previously validated nothing) and M17C-B `ShotPerformanceSegmentMapping` (keeping `PERFORMANCE_SHOT_MAPPING_INVALID`). Validation executes before any ORM/SQLite access in all four entry points. Matrix: M17A PUT −1/2^63 → 422, 2^63−1 → lawful 200; M17A DELETE −1/2^63 → 422, 2^63−1 → idempotent 204; direct-service `True`/`False` rejected for all four entry points with `session=None` (proving no ORM access precedes the law); no raw `OverflowError`/SQLAlchemy/SQLite exception escapes anywhere. The PF-02 bound behavior re-proven unchanged.

## Gates (first-run dispositions recorded exactly)

- New IR battery (`test_m17c_ir_regressions.py`): **40/40**.
- Focused M17A/M17B/M17C battery incl. SR2 + B-F + M17C-A + historical recovery families (34 files): **419/419**.
- **Hard process gate honored**: product committed (`4c80d80`) BEFORE validator runs; the two exact-name allowlist validators then failed LOCALLY on the IR battery path — caught before any push this time — and the carve (`e0c4e07`) precedes the push. All 19 standalone validators + the 2 piped-audit validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite (GPU datapoint): **2868 passed / 8 skipped / 0 failed in 44:07** — fully-green FIRST pass on the correction tree including the three live-GPU exec gates (no rerun, no flake); CI below is the full-suite authority at the exact code head.
- **CI run `36457412414` on `e0c4e07`: SUCCESS, attempt 1** — Backend **2856 passed / 20 skipped / 0 failed** in 30:42 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the IR battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `a5f9d2d..e0c4e07`** (`4c80d80` + `e0c4e07`; the `0d0f403` record commit rides inside the range as documentation-only ancestry). Per the controlling disposition, the next protocol step is ONE independent Codex delta-only review of exactly `a5f9d2d..e0c4e07` plus direct predecessor implications, WITHOUT this reconciliation. No merge, no ready-mark, no M17C-C.

*(Superseded: the independent Codex review of that range returned six findings — M17C-IR-01..06, all accepted and corrected below.)*

---

# M17C-B IR-final corrective cycle (M17C-IR-01..06) — 2026-09-28/29

The independent Codex review of `a5f9d2d..e0c4e07` returned six findings (two schema-proof exactness gaps, a shared persisted PF-02 law gap, mode-dependent historical verification, unnormalized blob-byte failures, and loose test evidence); all six are accepted and implemented. **Product correction base: `e0c4e07`.** Corrected code head: **`f84e6f9`** (`b6fcd3f` product correction + `f84e6f9` validator carve). No M17C-C; PR #26 remains open, draft, unmerged.

## M17C-IR-01 — closed-world, multiplicity-preserving physical-schema proof: IMPLEMENTED

`parse_table_checks` parses every table-level CHECK occurrence into a **complete ordered multiset** `[(name_or_none, normalized_expression), ...]` — case-insensitive whole-word scanning for CONSTRAINT/CHECK; anonymous CHECKs captured; duplicate names preserved; malformed/truncated syntax (no paren after CHECK, unbalanced parens, unterminated string, unnamed/unsupported constraint kinds) fails closed; nested parentheses and quoted strings balanced. The COMPLETE multiset must equal the frozen contract — anonymous extras, lowercase `constraint … check (…)`, duplicate same-name bad+good, and right-name-wrong-expression all refuse. FKs compare as the COMPLETE `PRAGMA foreign_key_list` row multiset (seq, target table, source/target column, ON UPDATE, ON DELETE, MATCH) — duplicate same-key rows with conflicting ON DELETE or ON UPDATE/MATCH cannot collapse. Explicit indexes are a **closed inventory** per migration-owned table (PF-03 tables: exactly none; PF-02: exactly `ix_spsm_pr`, non-unique/non-partial/origin-`c` over exactly `performance_revision_id`) while SQLite's PK/UNIQUE autoindexes are lawful and never rejected for existing. Adversarial matrix: eight 0021 DDL surgeries (anonymous CHECK, lowercase named CHECK, duplicate name bad+good, extra ordinary/UNIQUE/partial index, duplicate FK conflicting ON DELETE, conflicting ON UPDATE) plus two 0020 predecessor-table surgeries — all refuse at the schema phase, before semantic row traversal, with empty tables where possible.

## M17C-IR-02 — one transport-neutral persisted PF-02 mapping law: IMPLEMENTED

`verify_persisted_mapping_structural` is the ONE shared law (live readiness/list + staged recovery, field-extracted at each boundary): row `position` and `vocal_mapping_position` are actual-integral SQLite-safe mapping positions (SQLite affinity can persist TEXT/REAL there — non-integral and beyond-i64 storages refuse; the beyond-i64 tamper is constructed via an in-statement SQL literal because Python's driver refuses to bind 2^63, with SQLite demoting it to REAL); schema version; three canonical integer-pair rationals; nonempty interval; immutable PR-domain containment; discriminator↔position shape; canonical json/hash. Kept OUT (readiness concerns): current duration, picture intersection, current selection, paired mapping existence, paired CURRENT VP. Recovery independently keeps Shot/PR existence + project agreement. Coherent-rehash matrix: start==end, start>end, before/after/straddling PR domain, vocal position −1, non-integral, beyond-i64 — all refuse recovery; the lawful working-state positives (missing pair, VP drift, stale selection, duration 0, non-intersection) are anchored as still-restoring.

## M17C-IR-03 — historical parent authority BEFORE mode interpretation: IMPLEMENTED

`verify_candidate_authority_historical` (the previous cycle's seam, promoted to the clear IR name with the old name kept as alias) and the new `verify_revision_authority_historical` (+`revalidate_winner_historical`) are the mode-independent pair. Wiring: both binding GETs prove parent authority BEFORE the lawful NONE 404; adoption — first AND replay, changed in the SHARED revision service so both the M17B and M17C routes inherit it — consumes persisted candidate integrity through the corruption seam (active-subject stays admission); the M17C retarget wrapper proves complete source authority BEFORE `create_retarget_candidate`. **Battery-exposed leaks fixed:** the adoption replay leaked `adoption_id must be an exact UUID` as 422 (now wrapped); three M17B refusals legitimately moved EARLIER to retarget CREATION with the identical verdict and branch (x21f paired provenance, x21g transitive review-law-chain, x22 lineage) — tests updated to the historical 500 contract with the same diagnostics. The generic-NONE matrix (six corruptions of adopted NONE history): candidate binding GET 500 (not 404), revision binding GET 500, adoption replay 500, retarget 500 with ZERO new candidates and companions; lawful NONE history keeps honest 404s; fresh malformed creation keeps admission 4xx.

## M17C-IR-04 — complete adopted-pair closure on candidate binding reads: IMPLEMENTED

`verify_adopted_pair_closure` (non-media): revision authority + classification equality with both sides' cardinality + the FULL read-grade VOCAL_V1 pair closure by REUSE of `verify_revision_vocal_binding_read_grade` — no retained VP audio. The candidate binding GET proves it whenever the candidate is adopted, before returning the binding; a pre-adoption candidate proves only its own authority. Asymmetric matrix (one-sided coherent binding rehash on either side; one-sided copied-closure field on either side): candidate GET, revision GET, PF-02 readiness, and recovery all agree on corruption. **Recorded supersession:** c2_03's "candidate side stays lawful" expectation is overturned — revision temporal columns are copied-closure fields, so the closure branch subsumes copied-field tampering (the revision-owned domain law remains independently proven by the SR2-05 origin-domain coherent-binding case).

## M17C-IR-05 — normalized missing retained payload bytes: IMPLEMENTED

`read_verified_blob_bytes` at the immutable-candidate blob boundary: narrow catches for `FileNotFoundError`/`PermissionError`/`OSError` → structured `BLOB_BYTES_MISSING` SoloRingError (never a broad Exception catch); the historical seam translates to 500 with the diagnostic; fresh admission keeps structured codes. Recovery additionally hardens the payload JSON decode — a coherent audio-bytes swap previously escaped as a raw `UnicodeDecodeError` and is now structured recovery corruption ("is not UTF-8 JSON"). Regression: payload physical file deleted (Blob row kept) — PF-02 PUT 500 + zero rows, readiness/list 500, both binding GETs 500, adoption replay 500, retarget 500 + zero new candidates, recovery refuses via the M17B blob branch ("missing from Blob root"); every message pinned.

## M17C-IR-06 — branch-specific recovery evidence: IMPLEMENTED

The IR battery's `pytest.raises(Exception)` sites now assert the stable `SoloRingError` + `RECOVERY_CORRUPTION` contract plus a law-specific fragment per tamper (dual-hash disagreement, non-JSON payload, provenance, closure-diverges-on-subject_id with the layering comment that the M17B revision verifier legitimately fires after the candidate core passes). The IR-final battery is branch-specific from birth.

## Additional targeted sweep

Verified no other M17C route/transition interprets a classification without first proving parent authority: the adoption precheck/converge paths are always preceded (adoption) or followed (replay convergence) by the authority seam; collection endpoints are deliberately left as non-scanning per the disposition.

## Gates (first-run dispositions recorded exactly)

- New IR-final battery (`test_m17c_irf_regressions.py`): **31/31**; hardened IR battery: **40/40**.
- Focused M17A/M17B/M17C battery incl. M17B NONE/adoption/retarget matrices and the historical recovery families (35 files): **450/450**. First run 438/12: one legitimate IR-04 supersession (c2_03) and eleven M17B adoption/retarget tests asserting the superseded 4xx contract — all updated to the historical 500 with identical diagnostics, and three whose refusal moved earlier to creation.
- **Hard process gate honored**: committed (`b6fcd3f`) BEFORE validators; the two exact-name allowlist validators failed locally on the IR-final battery path (caught pre-push, third consecutive cycle); carve (`f84e6f9`) precedes the push. All 21 validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite: **2899 passed / 8 skipped / 0 failed in 43:10** — fully-green FIRST pass including the three live-GPU exec gates (no rerun, no flake).
- **CI run `36491026625` on `f84e6f9`: SUCCESS, attempt 1** — Backend **2887 passed / 20 skipped / 0 failed** in 27:37 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the IR-final battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `e0c4e07..f84e6f9`** (`b6fcd3f` + `f84e6f9`). Per the controlling disposition: after this freeze is green, ONE independent Codex delta-only review of exactly `e0c4e07..f84e6f9` plus direct implications, WITHOUT this reconciliation; if clean, M17C-B closes technically and M17C-C may proceed while PR #26 remains draft.

*(Superseded: the independent Codex review of that range returned four findings — IND-01..04, all accepted and corrected below.)*

---

# M17C-B IND corrective cycle (IND-01..04) — 2026-09-29

The independent Codex review of `e0c4e07..f84e6f9` returned four findings (numerator-only interval ordering, uncertified UNIQUE autoindexes, retarget-evidence authority only at adoption, and M17B recovery parser/OS leaks); all four are accepted and implemented. **Product correction base: `f84e6f9`.** Corrected code head: **`a8c822b`** (`84c074f` product correction + `a8c822b` validator carve). No M17C-C; PR #26 remains open, draft, unmerged.

## IND-01 — exact rational PF-02 interval ordering: IMPLEMENTED

The numerator-only ordering in the ONE shared persisted law is replaced by exact Fractions constructed after canonicality: `start = Fraction(start_num, start_den)`, `end = Fraction(end_num, end_den)`, requiring `start < end`, with the immutable PR-domain containment on those SAME exact values — no floats, no tolerance. 1/2→2/5 is inverted (0.5 > 0.4) even though 1 < 2 numerically; 3/4→1/1 is lawful. Regressions are denominator-sensitive end-to-end: the 3/4→1/1 positive survives live PUT/list/readiness and backup/restore; the 1/2→2/5 negative refuses the live PUT admission law, the live list/readiness of a coherently-rehashed persisted row, and recovery (backup taken from the lawful state first — the backup enumeration itself refuses the tampered source). The equal/before/after/straddle family is retained.

## IND-02 — UNIQUE-constraint autoindex certification: IMPLEMENTED

Every `PRAGMA index_list` entry of every migration-owned table is classified by origin: `pk` entries are lawful ONLY as the exact consequence of the frozen PK (each must index exactly the frozen PK columns in order); `u` entries are UNIQUE-constraint consequences and the frozen 0020/0021 migrations declare NO UNIQUE beyond the PK, so ANY `origin='u'` index refuses — arbitrary autoindexes are never benign; `c` remains the closed explicit inventory (with the PF-02 rebuilds recreating `ix_spsm_pr` so the UNIQUE law, not the explicit-index law, is the branch exercised). Adversarial tests on otherwise-exact EMPTY schemas: anonymous `UNIQUE(column)` and named `CONSTRAINT uq_extra UNIQUE(column)` refuse at the physical-schema phase before row semantics on a frozen-0020 PF-03 table and the successor-0021 PF-02 table. All CHECK/FK/explicit-index multiplicity tests preserved.

## IND-03 — persisted retarget-evidence authority BEFORE publication: IMPLEMENTED

`retarget.verify_retarget_evidence_historical` is the ONE shared historical retarget-evidence verifier — the complete assessment/review authority factored from the laws `_verify_retarget_evidence`/`verify_assessment_persisted_laws` already embody: assessment identity to the exact source revision; from/to ProductionRevision rows exist with the duplicated snapshot-hash columns equal to the referenced immutable rows; referenced ProductionObjects exist and belong to the source project; assessment project equality; exact evaluator schema/id/version; canonical scope and report RECOMPUTED through `_build_scope`/`_evaluate`/`_build_report` with stored-bytes and stored-verdict equality; REQUIRES_REVIEW eligibility (lawful COMPATIBLE_AS_IS / INCOMPATIBLE assessments keep their request-shaped no-op 4xx — the evidence is valid, the request is a no-op); accepted-review existence/ownership/decision/metadata grammar through the shared validator. Consumed by BOTH `create_retarget_candidate` BEFORE any `PerformanceCandidate` is constructed or flushed (transaction rollback is not the authority boundary) and `_verify_retarget_evidence` for later candidate historical validation (the envelope↔assessment coordinate law stays revision-side). Corruption matrix: nine reachable shapes (assessment project; duplicated from/to snapshot hashes; scope json with coherent scope-hash recompute; scope hash; report json with coherent report-hash recompute; report hash; stored verdict with a superficially acceptable value; review rationale grammar) plus review ownership — each refuses creation with the historical 500, the targeted diagnostic preserved, and ZERO new candidates/classifications/bindings; a dialogue-bound spot-check proves the PF-03 closure composes; lawful retarget creation is unchanged (201, exactly one new candidate + classification, no binding). **Recorded:** evaluator_id/evaluator_version/schema_version and whitespace `reviewed_by` are DB-CHECK-pinned (`ck_pra_*`/`ck_prr_*`) — those corrupted states cannot exist at this schema at all, proven by IntegrityError, with the verifier's corresponding laws as the recovery-parity mirror for any database that ever carried them. M17B fallout, all to the same verdicts/branches: g07/g09/g16 now historical 500s (decision/identity/ownership laws); g08/g17 cite real review rows (the route resolves the review before the verifier's eligibility branch); x21's main case and `_try_adopt_forge` subcases refuse at CREATION on the same recomputation/ownership branches with the identical diagnostics.

## IND-04 — complete M17B recovery error normalization: IMPLEMENTED

`_blob_bytes` retains the explicit absent-path law and the SHA-256 rehash, and now wraps `read_bytes()` narrowly: `PermissionError` and representative generic `OSError` translate to `_corrupt(...)` with path/hash context (never a broad Exception catch). The persisted provenance `json.loads` is wrapped in BOTH candidate passes (the generic and the retargeted) — malformed persisted provenance raises `RECOVERY_CORRUPTION`, never the raw parser exception; the payload decode keeps its existing structured Unicode/JSON handling, and the adjacent-decode audit found the second payload re-decode provably unable to fail after the first structured pass. Regressions (at the supported M17C head, monkeypatched at the recovery seam — cross-platform, never OS-ACL dependent, matching the blob BY NAME because restore verifies a staged copy): PermissionError, representative OSError, and malformed provenance JSON each assert `SoloRingError` + `RECOVERY_CORRUPTION` + a branch-specific diagnostic; the physically-missing-file, wrong-bytes, invalid-UTF-8, and invalid-payload-JSON cases are retained across the existing batteries.

## Gates (first-run dispositions recorded exactly)

- New IND battery (`test_m17c_ind_regressions.py`): **26/26**.
- Focused M17A/M17B/M17C battery incl. adoption/retarget matrices and the historical recovery families (36 files): **476/476** (first run 450-equivalent plus the IND battery; the g/x21 fallout above was resolved inside this cycle before the focused rerun).
- **Hard process gate honored**: committed (`84c074f`) BEFORE validators; the two exact-name allowlist validators failed locally on the IND battery path (caught pre-push, fourth consecutive cycle); carve (`a8c822b`) precedes the push. All 21 validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite: **2925 passed / 8 skipped / 0 failed in 45:46** — fully-green FIRST pass including the three live-GPU exec gates (no rerun, no flake).
- **CI run `36519545423` on `a8c822b`: SUCCESS, attempt 1** — Backend **2913 passed / 20 skipped / 0 failed** in 25:04 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the IND battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `f84e6f9..a8c822b`** (`84c074f` + `a8c822b`). Per the controlling disposition: ONE independent Codex delta-only review of exactly `f84e6f9..a8c822b` plus direct implications, WITHOUT this reconciliation; if it returns clean with no new fundamental authority/recovery defect, M17C-B may finally close technically and M17C-C may begin while PR #26 remains draft.

*(Superseded: the independent Codex review of that range returned three findings — IND2-01..03, all accepted and corrected below.)*

---

# M17C-B IND2 corrective cycle (IND2-01..03) — 2026-09-29

The independent Codex review of `f84e6f9..a8c822b` returned three findings (provenance storage-class/parser stability, the complete blob filesystem boundary, and retarget eligibility precedence); all three are accepted and implemented. **Product correction base: `a8c822b`.** Corrected code head: **`b2c50ff`** (`d21d89c` product correction + `b2c50ff` validator carve). No M17C-C; PR #26 remains open, draft, unmerged.

## IND2-01 — provenance TEXT storage + stable parser corruption: IMPLEMENTED

`m17b_verifier.parse_persisted_json_text(value, *, what)` is the ONE persisted-JSON parser for candidate provenance, used in BOTH `_verify_candidates` and `_verify_retargeted`: it requires an actual Python `str` (bytes/bytearray/memoryview/numeric values refuse as `RECOVERY_CORRUPTION` with a provenance-specific diagnostic — the frozen storage representation is TEXT, so a BLOB that happens to decode as UTF-8 is STILL an invalid runtime storage class), calls `json.loads`, and translates `JSONDecodeError` to recovery corruption — never a broad `except Exception`, never a raw `UnicodeDecodeError`. All subsequent provenance laws (closed grammar, canonical equality, hash, source-kind agreement, retarget chain) are retained. Regressions at BOTH supported heads: generic `X'FF'` BLOB, retargeted `X'FF'` BLOB, and a valid-UTF8 BLOB containing otherwise-valid JSON (storage class proven `blob` via `typeof()`) all refuse with the TEXT-storage diagnostic; the ordinary malformed-TEXT case remains covered.

## IND2-02 — the complete blob filesystem boundary normalized: IMPLEMENTED

`_blob_bytes` now treats the existence/type probe and the content read as ONE narrow filesystem boundary: the probe's `PermissionError`/representative `OSError` translate to the unreadable/storage-error corruption family with blob hash/path context; ordinary absence stays the missing-Blob family; the probe-to-read disappearance race (`FileNotFoundError` after a successful probe) lands back in the missing-Blob family; the read failures keep their IND-04 handling; the SHA-256 rehash is retained. **Adjacent-boundary normalization with recorded layering:** the restore-side manifest blob probe in `_verify_backup_tree` performs its own `is_file()` existence check BEFORE the semantic verifier runs, so it received the same narrow normalization — and in the restore flow that branch fires FIRST, which the probe-boundary regressions assert. Five monkeypatched regressions against the STAGED copy (matched by blob NAME — the staged tree's paths differ from the original): stat `PermissionError`, stat `OSError(EIO)`, read `PermissionError`, read `OSError`, and the disappearance race — each refuses through the stable recovery-corruption contract (the manifest-probe family raises the module's own `RecoveryCorruption` hierarchy; the semantic-verifier families raise `SoloRingError` with `RECOVERY_CORRUPTION`) with branch-specific diagnostics. The missing-file and wrong-hash cases are kept.

## IND2-03 — retarget eligibility precedence without stored-verdict trust: IMPLEMENTED

The shared verifier is split into two reusable historical phases. **Phase A** — `verify_retarget_assessment_historical(...) -> recomputed_verdict`: the complete assessment laws (exact source coordinate; from/to row existence; duplicated snapshot hashes; ProductionObject existence/project ownership; assessment project; evaluator schema/id/version; canonical scope recomputation with JSON/hash equality; evaluator verdict/reason recomputation; canonical report recomputation with JSON/hash equality; stored verdict == recomputed verdict), every persisted corruption a historical 500, and the STORED verdict is never the eligibility decision. **Eligibility precedence:** `create_retarget_candidate` maps the RECOMPUTED verdict — `COMPATIBLE_AS_IS` → `422 RETARGET_NOT_REQUIRED`, `INCOMPATIBLE` → `422 RETARGET_INCOMPATIBLE` — WITHOUT resolving or inspecting `accepted_review_id`; only recomputed `REQUIRES_REVIEW` resolves the review (a genuinely nonexistent request-supplied id keeps the established 404). **Phase B** — `verify_retarget_review_historical`: exact assessment ownership, `ACCEPT_FOR_NEW_CANDIDATE`, and the complete persisted metadata grammar. Candidate construction/flush stays strictly after both phases. The combined `verify_retarget_evidence_historical` wrapper is retained for later already-published candidate validation by composing the phases (with the published-evidence REQUIRES_REVIEW requirement), and the candidate-specific provenance↔assessment coordinate law remains at its higher layer. g08/g17 are restored to their original dummy-review-id shape (correct again under the precedence). The full precedence set is proven: lawful INCOMPATIBLE/COMPATIBLE_AS_IS + a syntactically valid nonexistent review id → the 4xx branches with zero new rows; corrupt assessment + missing review id → Phase A 500 fires FIRST; REQUIRES_REVIEW + missing id → 404; REQUIRES_REVIEW + a corrupt repointed existing review → Phase B 500; lawful chain → 201 unchanged.

## Gates (first-run dispositions recorded exactly)

- New IND2 battery (`test_m17c_ind2_regressions.py`): **15/15**.
- Focused M17A/M17B/M17C battery incl. the retarget G/x matrices and the historical recovery families (37 files): **491/491** (first run after the source fixes; the g08/g17 restoration passed first-run inside it).
- **Hard process gate honored**: committed (`d21d89c`) BEFORE validators; the two exact-name allowlist validators failed locally on the IND2 battery path (caught pre-push, fifth consecutive cycle); carve (`b2c50ff`) precedes the push. All 21 validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite: **2940 passed / 8 skipped / 0 failed in 44:56** — fully-green FIRST pass including the three live-GPU exec gates (no rerun, no flake).
- **CI run `36536429685` on `b2c50ff`: SUCCESS, attempt 1** — Backend **2928 passed / 20 skipped / 0 failed** in 30:48 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the IND2 battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `a8c822b..b2c50ff`** (`d21d89c` + `b2c50ff`). Per the controlling disposition: ONE independent Codex delta-only review of exactly `a8c822b..b2c50ff` plus direct predecessor implications, WITHOUT this reconciliation or the IND2 report; if it returns clean with no new fundamental authority/recovery defect, M17C-B may finally close technically and M17C-C may begin while PR #26 remains draft.

*(Superseded: the independent Codex review of that range returned one finding — IND3-01, accepted and corrected below.)*

---

# M17C-B IND3 corrective cycle (IND3-01) — 2026-09-29

The independent Codex review of `a8c822b..b2c50ff` returned one finding (the manifest layer's own content read leaking raw OS exceptions after a successful probe); it is accepted and implemented. **Product correction base: `b2c50ff`.** Corrected code head: **`b4c31e6`** (`6fcaf0b` product correction + `0f9c827` validator carve + `b4c31e6` fix-forward). No M17C-C; PR #26 remains open, draft, unmerged.

## IND3-01 — manifest Blob content reads normalized: IMPLEMENTED

`_verify_manifest_hashed_bytes(path, expected_hash, *, what, mismatch=None)` is the manifest/restore-tree layer's own content-read wrapper, used by `_verify_manifest_files` for every manifest-listed Blob: it invokes `_verify_bytes`, narrowly catches `FileNotFoundError` (probe-then-open disappearance → the missing family with a "disappeared during manifest content verification" diagnostic), `PermissionError`, and representative `OSError` (unreadable/storage-error families with hash/path context), and lets an already-raised hash-mismatch `RecoveryCorruption` pass through unchanged (`RecoveryCorruption` is not an `OSError`); the optional `mismatch` restates a mismatch with a caller's frozen diagnostic. No `except Exception` anywhere — programming errors remain visible. The generic `_stream_hash`/`_copy_verified` machinery is deliberately UNCHANGED (callsite-local, per the preferred boundary — backup/copy hashing keeps its own contracts).

**Adjacent audit of the same `_verify_bytes` callers in the PUBLIC RESTORE path:** the backup DB probe+content read and the workflow-artifact content read share `_verify_manifest_files`' exact leak shape and received the same narrow wrapper (the DB probe now also guards its stat boundary; the DB mismatch keeps its exact frozen `database_sha256` wording). Purely backup-side machinery (`_copy_verified` source reads) is left unchanged — not public restore.

**Layer proof:** the regressions patch the ACTUAL `builtins.open` seam selectively by target filename — `_stream_hash` uses built-in `open()`, not `Path.read_bytes`, so patching `read_bytes` alone demonstrably reaches only the semantic M17B reader (the IND2 experience). Tests A/B/C (probe succeeds; open gets `FileNotFoundError` / `PermissionError` / `OSError(EIO)`) each assert the MANIFEST layer fires first: `RecoveryCorruption` hierarchy, the blob hash present, a manifest-read-specific fragment, and the semantic `M17B payload blob` family explicitly NOT matched; never a raw OS exception. One representative adjacent regression proves the backup DB content-read permission branch (sqlite3 opens through its own C layer, so the selective `builtins.open` patch hits exactly the manifest hash read). The wrong-bytes hash-mismatch case keeps the existing `RecoveryCorruption` pass-through. The IND2 semantic-layer tests are retained unchanged and complementary.

## Gates (first-run dispositions recorded exactly)

- New IND3 battery (`test_m17c_ind3_regressions.py`): **5/5**; IND2/IND/IR-final/IR batteries **117/117** combined.
- Focused M17A/M17B/M17C battery (38 files): **496/496** — with the gap now disclosed: the focused set does not include `test_m10f_backup_restore.py`, which is how the fix-forward below escaped local pre-push gates.
- **Hard process gate honored**: committed (`6fcaf0b`) BEFORE validators; the two exact-name allowlist validators failed locally on the IND3 battery path (caught pre-push, sixth consecutive cycle); carve (`0f9c827`) precedes the push. All 21 validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite, FIRST RUN on `6fcaf0b`: **2943 passed / 8 skipped / 2 failed** — the two failures are the frozen M10F cells 02/05 pinning the DB hash-mismatch `database_sha256` diagnostic, which the IND3 wrapper had restated through `_verify_bytes`' generic message; CI run `36550409879` on `0f9c827` failed on exactly the same two tests (2/2931+20), independently reproducing the root cause. **Fix-forward `b4c31e6`**: the wrapper gained the optional bespoke mismatch restatement and the DB call passes the predecessor's exact frozen wording — the M10F evidence and the Blob pass-through are untouched; `test_m10f_backup_restore` + IND3 + IND2 files **61/61** green post-fix locally.
- **CI run `36555193243` on `b4c31e6` (the corrected code head): SUCCESS, attempt 1** — Backend **2933 passed / 20 skipped / 0 failed** in 30:47 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the IND3 battery; no new repo-root generated residue.

## Frozen for the independent Codex delta review

**Product delta `b2c50ff..b4c31e6`** (`6fcaf0b` + `0f9c827` + `b4c31e6`). Per the controlling disposition: ONE independent Codex delta-only review of exactly `b2c50ff..b4c31e6` plus direct predecessor implications, WITHOUT this reconciliation or the IND3 report; if it is clean, close M17C-B technically at the corrected head and proceed to M17C-C while PR #26 remains draft.

*(Superseded: the independent Codex review of that range returned two findings — F-01/F-02, both accepted and corrected below.)*

---

# M17C-B F corrective cycle (F-01/F-02) — 2026-09-29

The independent Codex review of `b2c50ff..b4c31e6` returned two findings (the workflow-artifact metadata probe and the initial manifest acquisition — the last two unguarded filesystem operations in the public restore envelope); both are accepted and implemented. **Public-restore error-envelope closure only — no PF-02/M17C-B semantic modified.** **Product correction base: `b4c31e6`.** Corrected code head: **`653a325`** (`bdf43ad` product correction + `653a325` validator carve). No M17C-C; PR #26 remains open, draft, unmerged.

## F-01 — workflow-artifact metadata probing normalized: IMPLEMENTED

The unguarded `Path.is_file()` immediately before the (already-normalized) artifact content read now executes inside a narrow filesystem boundary: `PermissionError` is caught before generic `OSError` (both → `RecoveryCorruption` carrying the artifact kind, sha256, path, and probe/permission or storage-error family); ordinary `False` keeps the established `backup workflow artifact <kind> <hash> is missing` semantics unchanged; only then does `_verify_manifest_hashed_bytes` run. No `except Exception`. The regressions synthesize a REAL manifest-listed workflow artifact into an otherwise-lawful backup (exact artifact path layout, grammar-satisfying sorted manifest entry, canonical manifest rewrite with the recomputed database hash), patch ONLY that artifact's `is_file`, and prove the PROBE layer fires — kind/hash in the diagnostic, the content-hash wrapper's message families explicitly not matched — with the raw OS exception unable to satisfy the contract; ordinary-absence and hash-mismatch artifact behavior re-pinned unchanged.

## F-02 — initial manifest acquisition normalized: IMPLEMENTED

`_verify_backup_tree`'s `manifest_path.read_bytes()` extends beyond its `FileNotFoundError`-only handling: `PermissionError` and representative `OSError` translate to `RecoveryCorruption` with the manifest identity/path and unreadable/storage-error diagnostics; the frozen missing-manifest behavior is preserved verbatim; after bytes are obtained, `parse_backup_manifest_v1` keeps sole responsibility for UTF-8/JSON/canonical grammar (the `BackupManifestInvalid` contract is untouched, re-pinned by the malformed-manifest regression); no `except Exception`. The regressions patch ONLY the target `backup-manifest.json`'s `read_bytes` — the acquisition boundary fires before any parse/probe stage.

## Eight-stage direct-implication sweep (recorded)

The complete public-restore filesystem sequence was classified once after correction: (1) manifest acquisition — F-02 (absence/permission/storage deliberate; parse errors remain the parse contract); (2) manifest parse — `parse_backup_manifest_v1` (domain-invalid family); (3) DB probe — guarded (absence/permission/storage); (4) DB content — `_verify_manifest_hashed_bytes` with the bespoke frozen `database_sha256` mismatch; (5) Blob probe — guarded (IND2-02); (6) Blob content — `_verify_manifest_hashed_bytes` (IND3-01); (7) artifact probe — F-01; (8) artifact content — `_verify_manifest_hashed_bytes`. Every stage now exposes deliberate recovery-domain behavior; `_stream_hash`/`_copy_verified` remain globally unchanged.

## Gates (first-run dispositions recorded exactly)

- New F battery (`test_m17c_f_regressions.py`): **8/8**.
- IND3 + IND2 + `test_m10f_backup_restore` + the recovery suites: **102/102** (the frozen M10F `database_sha256` contract re-proven).
- Focused M17A/M17B/M17C suite now INCLUDING `test_m10f_backup_restore.py` (the IND3 gap closed): **545/545**.
- **Hard process gate honored**: committed (`bdf43ad`) BEFORE validators; the two exact-name allowlist validators failed locally on the F battery path (caught pre-push, seventh consecutive cycle); carve (`653a325`) precedes the push. All 21 validators green on the committed tree.
- Frontend: vitest **143/143** (32 files), `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite: **2953 passed / 8 skipped / 0 failed in 44:03** — fully-green FIRST pass including the three live-GPU exec gates (no rerun, no flake).
- **CI run `36565427012` on `653a325`: SUCCESS, attempt 1** — Backend **2941 passed / 20 skipped / 0 failed** in 32:28 (GPU gates skipped on Actions runners by design); Frontend green.
- Residue: this cycle's only new file is the F battery; no new repo-root generated residue.

## Frozen for the final independent Codex delta review

**Product delta `b4c31e6..653a325`** (`bdf43ad` + `653a325`). Per the controlling disposition: ONE final independent Codex delta-only review of exactly `b4c31e6..653a325` plus only direct restore-envelope implications, WITHOUT this reconciliation or the prior review; if that delta returns clean, close M17C-B technically and begin M17C-C while PR #26 remains draft.

*(Outcome: the final independent review found NO runtime/product defect in F-01/F-02, NO fundamental M17C-B/PF-02 defect, and the product code technically sound at `653a325` — with ONE Low-severity proof-strength defect in `tests/test_m17c_f_regressions.py`, corrected below as a TEST-ONLY cycle.)*

---

# M17C-B FFINAL test-only proof hardening (FFINAL-01) — 2026-09-29

The final independent review verified the product implementation (artifact probe normalization, manifest acquisition normalization, parser ownership, DB/Blob/M10F contracts, `_stream_hash`/`_copy_verified` unchanged, the eight-stage sequence deliberate) and returned one Low-severity test-strength finding; this cycle makes the regression evidence mechanically match the contract the production code already implements. **No production file touched** — the delta is exactly one test file (`tests/test_m17c_f_regressions.py`, +32/−22). **Product-code semantic head of record: `653a325`.** Test head: **`8a92bc6`**.

## FFINAL-01 — the five required fixes: IMPLEMENTED

1. **Real-file existence proof**: the F-01 artifact-probe test asserts `path.is_file()` after `_add_real_artifact(root)` and before any monkeypatching — the injected failure replaces a genuinely successful metadata probe, never a masked absent fixture.
2. **Artifact kind assertion**: `kind in str(exc)` added alongside the sha assertion.
3. **Complete artifact path assertion**: `str(path) in str(exc)` — and the selective injection itself is now EXACT-PATH based (`if self == path:`) rather than filename-only, with the viability documented in the test: `_verify_backup_tree(backup_root, False)` probes the ORIGINAL backup root before any staging, so the probe receives exactly the constructed path (the staged-copy caveat applied only to the semantic M17B layer).
4. **Concrete manifest path assertion**: the F-02 test defines `manifest_path = root / "backup-manifest.json"`, selects the target by exact Path equality, and asserts `str(manifest_path) in str(exc)` (the concrete location production promises) instead of the bare filename.
5. **Exact subtype for the missing-manifest regression**: `pytest.raises(Exception)` replaced by `pytest.raises(RecoveryCorruption, match="no backup-manifest.json")` with the class imported from the authoritative production module; the frozen diagnostic and the no-destination assertion are preserved.

**Optional tightening applied**: the F-01 ordinary-absence and hash-mismatch tests (and both parametrized probe/acquisition tests) use direct `isinstance(exc, RecoveryCorruption)`; the now-dead `_artifact_filename` helper and one unused import were removed. Every prior branch-specific assertion is retained — the battery still covers artifact PermissionError/OSError probes, ordinary absence, hash mismatch, manifest PermissionError/OSError acquisition, missing manifest, and malformed manifest → `BackupManifestInvalid`.

## Gates (first-run dispositions; no failures)

- F battery: **8/8**; IND3 + IND2 + `test_m10f_backup_restore` + recovery suites: **102/102**; focused suite (40 files): **545/545**.
- All 19 standalone validators PASS on the committed tree **with NO carve** (the cycle modifies an existing admitted filename only — consistent with the disposition's expectation; no validator content changed at all). The two piped-audit validators green.
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite: **2953 passed / 8 skipped / 0 failed in 48:53** — fully-green first pass including the three live-GPU exec gates.
- **CI run `36575425321` on `8a92bc6`: SUCCESS, attempt 1** — Backend **2941 passed / 20 skipped / 0 failed** in 31:28; Frontend green.
- Residue: no new files; production tree byte-identical to `653a325`.

## Frozen for the final test-only Codex review

**Test-only delta `653a325..8a92bc6`** — proof only; NOT a new product-semantic baseline. Per the controlling disposition: ONE final independent Codex delta-only review of exactly `653a325..8a92bc6`, scoped only to whether FFINAL-01 is fully closed, whether the assertions are non-vacuous, whether production code is truly untouched, and whether any test/validator weakening was introduced — WITHOUT this reconciliation or the prior final report. If clean: freeze `8a92bc6` as the complete M17C-B repository baseline, record `653a325` as the final M17C-B product-code semantic head, declare M17C-B technically CLOSED, and proceed to M17C-C on the same draft PR; no merge, no ready-mark.

---

# M17C-B — TECHNICALLY CLOSED — 2026-09-29

**The final independent review of `653a325..8a92bc6` returned CLEAN and was accepted by the user without qualification.** The two baselines are frozen exactly:

- **Final M17C-B product-code semantic head: `653a325b1f8bac75b8e9c0a105e320b3c6cf4cd4`.**
- **Complete M17C-B repository/proof baseline: `8a92bc6d6fd3bb38a1809e6cb54d1ec33998078e`** (CI run `36575425321`, attempt 1, green — verified before this gate; the live PR head is the later record-only `67bb617`/`67bb617…` ancestry, which changes only documentation and alters neither baseline).

FFINAL-01 is closed. The final delta was test-only; no product-semantic reopening occurred. **There is no remaining M17C-B/PF-02 blocker and no additional M17C-B review cycle is warranted.**

Standing fence: PR #26 remains open, draft, and unmerged (no merge, no ready-mark). **M17C-C may now begin on PR #26**, using `8a92bc6` as the frozen repository predecessor baseline and `653a325` when reasoning specifically about final M17C-B product semantics; any subsequent modification to M17C-A/B authority, PF-02 storage/readiness, recovery, or their proof surfaces is explicitly predecessor impact.
