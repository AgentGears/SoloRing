# SoloRing M17C-C — Schema-8 Capture / History / Recovery — Implementation Scope (R0)

**Date:** 2026-09-29 · **PR:** #26 (draft, open, unmerged) · **Branch:** `m17c-implementation-r4`
**Frozen repository predecessor baseline:** `8a92bc6d6fd3bb38a1809e6cb54d1ec33998078e` (complete M17C-B repository/proof baseline)
**M17C-B product semantics referent:** `653a325b1f8bac75b8e9c0a105e320b3c6cf4cd4` (final product-code semantic head)

M17C-B is TECHNICALLY CLOSED (final review CLEAN, accepted without qualification). This document establishes the M17C-C scope from the frozen R4 plan (§10.3–§10.7, §11, §12, §13.4–§13.6, cell families E/F/G as they apply to capture/history/recovery), grounded against the actual codebase seams. Any modification to M17C-A/B authority, PF-02 storage/readiness, recovery, or their proof surfaces during M17C-C is explicitly **predecessor impact** and must be flagged as such in commits and this record.

---

## 1. Frozen-plan deliverables (R4 §"M17C-C") mapped to code

### 1.1 Coherent capture integration (§11.1)

- Extend the existing ONE-read seam `_snapshot_one_read` (`server/soloring/domain/revisions.py:40`) — currently a 9-tuple (`read[8]` = intra-shot) — with a tenth element: the resolved performance plane (mappings + PR closures + revision vocal bindings + paired vocal mappings + the readiness projection needed to permit capture). All values fixed in memory before the fenced persistence unit begins. **No parallel M17C capture service** (plan constraint).
- The readiness gate is the existing `project_shot_performance_readiness` projection (M17C-B, unchanged); capture requires every segment READY (§11.2 "all readiness laws pass"; §11.4 blocker list maps 1:1 onto the M17C-B readiness vocabulary + the fail-closed 500 corruption reads).

### 1.2 Schema-8 builder extension (§11.2–§11.5)

- `build_capturable_snapshot` (`server/soloring/continuity/snapshots.py:198`) gains a `performance_pack` parameter; schema 8 wraps the EXACT predecessor base (any of schemas 1–7), following the established wrap-chain precedent at `snapshots.py:260-292` (schema 5/6/7 wraps).
- No-empty law: no `ShotPerformance` mapping ⇒ predecessor snapshot emitted byte-identically, schema unchanged; ≥1 mapping and all-ready ⇒ schema 8 = exact predecessor + non-empty `performance` block (`schema_version: 1`, segments sorted by `position`). Empty schema 8 is unrepresentable.
- Dialogue-bound segments embed the `vocal` sub-object (VP id, `vocal_binding_hash`, source interval, rate); non-dialogue embeds explicit `null` (R1 preference retained: uniform closed grammar).
- Schema-8 may wrap schema 7 (M16 intra-shot authority) — valid, never reinterpreted (§11.5).

### 1.3 Capture companion parent/children (§10.4–§10.5, §10.7)

- New successor migration **`0022_m17c_schema8_capture`** (down_revision `0021_m17c_shot_performance_mappings`), creating:
  - `shot_revision_performance_specs` — one parent per schema-8 ShotRevision (`shot_revision_id` PK/FK, `schema_version CHECK = 1`, `spec_json`, `spec_hash` 64-hex);
  - `shot_revision_performance_segments` — immutable canonical-order children (PK `(shot_revision_id, position)`), carrying the §10.5 field set (duplicated immutable hashes = capture closure, not authority; nullable all-or-none dialogue-bound group);
  - `generation_performance_inputs` (§10.6) — the durable Generation-owned derived-input sibling table (`artifact_role` CHECK in the two v1 roles, blob FK, tie-back `segment_hash`, `translation_identity`, `derived_input_hash`).
- Downgrade fences (§10.7 precedent + the 0020/0021 pattern): populated companion/children/derived-input rows refuse downgrade; empty steps drop cleanly.
- ORM models in a new `soloring/performance/m17c_capture_models.py` (or the established models home) with named CHECKs matching the migration exactly.

### 1.4 Reuse integrity (§10.4 reuse-validate winner; §11.4 blockers)

- The fenced persistence unit `_persist_revision_fenced` (`revisions.py:428`) inserts parent-first then children from the SAME captured value (UOW has no mapper relationship; SQLite FKs immediate — existing precedent). Reuse lookup by `(shot_id, snapshot_hash)` then semantic validation of the winner extends to the performance companions.
- §11.4 blocker set (missing/corrupt PR; missing/corrupt binding; VP integrity; Shot/project/subject mismatch; subject not coherently resolved; paired vocal mapping missing OR stale; vocal id mismatch; rational/timing mismatch; interval outside immutable domain/binding; local-channel ownership conflict; noncanonical stored mapping bytes/hash) is enforced by refusing capture (500 corruption for tampered shapes; 409/422 admission shapes where the readiness projection already says so).

### 1.5 Historical inspection (§12)

- Historical schema-8 reads reconstruct from: snapshot bytes + companion rows + immutable referenced authority + retained Blob closure — and MUST NOT read current `VocalPerformanceSelection`, current `ShotVocalSegmentMapping`, current `ShotPerformanceSegmentMapping`, current candidate rows, or current Shot dependency selection.
- New read path answers, per captured segment: subject, exact PR, exact payload bytes/hash, exact VP (if dialogue-bound), exact vocal sample interval, exact Performance interval, exact Shot-relative anchor, exact immutable synchronization binding hash.

### 1.6 M17C recovery verifier extension (§13.4–§13.6, §13.5)

- `verify_m17c_binding_state` (now head-aware, dispatched at 0021) extends to head **0022**:
  - §13.4 captured-schema-8 laws: exactly one companion parent per schema-8 snapshot; predecessor planes valid under predecessor verifiers; embedded performance block bytes == companion spec bytes/hash; child count/order/projection equality; every captured PR/VP/binding/hash resolves and revalidates; exact timing arithmetic reproduces; subject/Project coherence; no overlapping same-subject channel conflict in captured history; schema < 8 carries ZERO companions; schema 8 never has an empty segment list.
  - §13.6 derived-input laws: parent Generation exists, same-creation-unit; role vocabulary; retained bytes rehash; tie-back resolves to the exact captured segment; translation identity equals the Generation execution-spec identity; control-schedule bytes RECOMPUTE identically under §14.6; vocal-audio bytes sample-exact under the J/L-cut intersection law (no negative-anchor leading-silence realization).
  - §13.5: Blob-FK inventory gains the `generation_performance_inputs.blob_hash` path — count asserted mechanically in the 13→14-path inventory advance.
- Head dispatch: 0022 admitted in `EXPECTED/SUPPORTED` + both successor chains; 0020/0021 laws unchanged (schema < 8 ⇒ zero companions is a REFUSAL at those heads when companions exist).

### 1.7 Backup/restore and downgrade tests

- Clean round trip preserving companions; staged real-0021→0022 upgrade retaining all M17C-B rows; populated downgrade refusals naming the tables; head-sweep of test constants (the M17C-B lesson, applied with companion assertions).

## 2. Sequencing (implementation order)

1. Migration `0022` + ORM models + migration tests (fences, head sweep).
2. One-read extension (10th element) + `performance_pack` builder + schema-8 wrap law.
3. Fenced persistence (parent/children) + reuse validation + §11.4 blocker surface.
4. Historical inspection read path (+ API surface per §12).
5. Recovery verifier §13.4 (schema-8) at head 0022 + dispatch + §13.5 inventory.
6. `generation_performance_inputs` writer is **M17C-D territory** (executor translation produces the derived bytes); M17C-C delivers the TABLE + §13.6 verifier laws + the recovery surface, with the recomputability laws proven against fixtures the M17C-D translation will produce. (Scope note recorded: §13.6's "control-schedule bytes reproduce under §14.6" requires the frozen sampling law implementation, which R4 places in M17C-D's productionized adapter. M17C-C proves the structural laws — role/tie-back/rehash/identity — and the arithmetic laws where the §14.6 sampler is already available as a pure function; otherwise they land with M17C-D and this is disclosed.)

## 3. Predecessor-impact register (explicit)

- `_snapshot_one_read`, `build_capturable_snapshot`, `_persist_revision_fenced`: EXTENDED (additive parameter/tuple element), following the in-file precedent of each prior schema wrap. Treated as predecessor impact; regression coverage = the full existing capture/reuse/history suites must stay green unchanged.
- `m17c_verifier.py`: extended (new head 0022 + §13.4/§13.6 passes; 0020/0021 behavior byte-identical).
- Recovery heads/dispatch: 0022 admitted; `SUPPORTED` extended; Blob inventory 13→14 paths at 0022 only.
- No PF-02 service semantics, no PF-03 authority, no M17C-A/B test expectation changes.

## 4. Exit criterion (R4)

> Vocal/facial segment identity survives current-state changes and restore.

Concretely: after capture, mutating every current-state surface the historical read must not consult (VP selection, vocal mappings, working performance mappings, dependencies, Shot duration) leaves the historical inspection byte-identical; a backup/restore round trip preserves it; recovery refuses every §13.4/§13.6 tamper shape.
