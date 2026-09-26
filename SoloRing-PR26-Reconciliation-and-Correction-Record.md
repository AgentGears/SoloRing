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
- All thirteen CI validators: **green locally** (proof maps + the nine individually-classified boundary/source-fit/baseline validators).
- Full backend suite + residue: recorded in the corrective commit message.
