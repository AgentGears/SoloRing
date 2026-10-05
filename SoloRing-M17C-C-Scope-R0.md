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

---

# M17C-C slice 1 — migration 0022 (schema/storage-only) — 2026-09-29/30 — IMPLEMENTED

Per the sequencing discipline (0022 remains schema/storage-only; no capture, current-read, derived-input-production, or sampler semantics), slice 1 is complete and green. **Frozen repository predecessor baseline: `8a92bc6`.** Slice-1 head: **`3fe01db`** (`eee329d` migration+models+head plumbing, `742f80f` validator carve, `bcb256d` fixture companion sweep, `3fe01db` one stray literal).

## Delivered

- **Migration `0022_m17c_schema8_capture`** (down_revision `0021_m17c_shot_performance_mappings`): `shot_revision_performance_specs` (§10.4 parent; schema-version and 64-hex spec-hash CHECKs); `shot_revision_performance_segments` (§10.5 immutable children; PK `(shot_revision_id, position)`; the all-or-none dialogue-bound vocal-group CHECK; duplicated immutable hashes as capture closure — payload hashes deliberately carry NO independent Blob FK; FKs RESTRICT to shot_revisions + performance_revisions; `ix_srpss_pr`); `generation_performance_inputs` (§10.6; the two v1 `artifact_role` CHECK; `blob_hash` FK → blobs = the ONE new Blob-FK path; `translation_identity` + `derived_input_hash`). Populated-downgrade fences on all three tables.
- **ORM models** `server/soloring/performance/m17cc_models.py` (registered in `db/models`); create_all-vs-alembic DDL identity verified for all three tables.
- **Head plumbing**: `M17C_C_ALEMBIC_HEAD`/`EXPECTED_ALEMBIC_HEAD = 0022`; SUPPORTED extended; `_blob_fk_policy_for_head` gains the 14-path set at 0022 only (0020/0021 keep 13); successor dispatch extended at all six membership sites; the head-aware M17C verifier accepts 0022 with 0021-equivalent semantics (§13.4/§13.6 land with the capture/history slices; the new tables are storage-only at this head).
- **Tests**: new `tests/test_m17cc_migration.py` (fresh upgrade, empty downgrade, three populated-fence refusals, the all-or-none CHECK, staged real-0021→0022 upgrade preserving every M17C-B row + verifier green at 0022); the head/constant companion sweep across ~30 test files and five validator scripts.

## Predecessor impact (register)

Additive only: recovery head constants/dispatch (0022 admitted; 0020/0021 laws byte-identical), `_retarget_backup` fixture helper drops the three tables when reshaping to pre-0022 heads, `_stamp_alembic` default advanced, i03 comparison excludes the new tables. No PF-02/PF-03 semantic, no M17C-A/B test expectation weakened.

## Gates (first-run dispositions recorded exactly)

- New M17C-C migration battery **8/8**; migration-family suites **212+ passed**; focused suite (43 files incl. m10f + all recovery families) **559/559**.
- **Hard process gate honored**: committed BEFORE validators; committed-tree validation caught the m14/m16 regex-comma defect + the nsec slice/source-fit admissions (carve `742f80f`) and the companion fallout (`bcb256d`) — all fixed before push. All 19 standalone validators + 2 piped-audit validators green on the committed tree.
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite **on the final tree (`3fe01db`): 2960 passed / 8 skipped / 0 failed in 45:17 — fully-green FIRST pass including the three live-GPU exec gates.** (An earlier full-suite run started on the pre-carve tree reported 7 fixture-side failures — all fixed in `bcb256d`/`3fe01db`; disclosed, not erased.)
- **CI run `36639823643` on `3fe01db`: attempts 1–2 failed ONLY on `tests/test_m7d_relations.py::test_race_r8_...` — the repo-characterized SQLite "Database is busy" flake, identical signature both times (1 failed / 2947+20 each; every other step green; Frontend green); per repo precedent rerun-failed-jobs only, no source change. Attempt 3: SUCCESS — Backend 2948 passed / 20 skipped / 0 failed; Frontend green.** The flake passed first-run locally both full runs (2953 and 2960 suites).
- Residue: new files = migration 0022 + `m17cc_models.py` + `test_m17cc_migration.py` + this scope record; no other root residue.

## Next slice (unchanged from the R0 sequencing)

Slice 2: the one-read tenth element + `performance_pack` schema-8 wrap + no-empty law; slice 3: fenced persistence + reuse + §11.4 blockers; then §12 history, §13.4/§13.5/§13.6 verifier laws.

---

# M17C-C slice 2 — the coherent performance-plane READ + the pure schema-8 wrap — 2026-09-30 — IMPLEMENTED

Slice 2 is complete and green per the narrow-gate guidance. Slice-2 head: **`45d565f`** (`10b596b` slice-2 source + `91c62a2` carve + `45d565f` one-line spy fix-forward).

## Delivered (exactly the six boundary points)

1. **One-read coherence**: `_snapshot_one_read` returns a TENTH element — `resolve_performance_plane` (new `server/soloring/performance/m17cc_capture_read.py`) resolves the complete plane on the SAME pinned SQLite snapshot, last in the frozen precedence chain (after M16), as a plain immutable-in-practice value: mappings, PR closure fields, immutable revision vocal bindings, paired vocal mappings, and the full readiness projection. The M17C-B session-based verifiers run through an `AsyncSession` bound to the pinned connection in savepoint-join mode (verified by scratch: same-snapshot reads, no second pooled connection). No reconstruction from current state after the read; `_persist_revision_fenced` untouched (no companion writes — slice 3).
2. **Pure builder**: `build_capturable_snapshot(..., performance_pack=None)` performs schema construction only — it queries nothing and evaluates no readiness.
3. **No mapping ⇒ exact predecessor**: `performance_pack` absent/None leaves the output byte-identical (asserted at schema 1 and 2 builder forms AND live: the captured snapshot's canonical bytes AND hash equal the no-pack build).
4. **No-empty schema 8**: a pack with an empty segments list is unrepresentable (internal-invariant refusal); non-empty position-ordered segments only.
5. **Closed uniform vocal grammar**: complete 5-key vocal object or explicit `null`, enforced structurally, never omission.
6. **Schema 8 over schema 7 proven directly**: the M16 intra_shot block and every predecessor field are byte-equal beneath the new plane (only `schema_version` and `performance` change).

Plus the capture gate: `capture_revision_with_visual` refuses non-READY with typed **409 PERFORMANCE_CAPTURE_NOT_READY** (per-segment diagnostics; the error code's first live consumer) BEFORE any builder invocation, mirroring the frozen M7D→M16 blocker precedence; corruption fails closed 500 inside the read through the shared seam. Non-capture consumers of the one-read seam (observation_readiness) are unaffected for no-mapping shots (a COUNT-only fast path).

## The coherency proof (the reviewer's requested shape)

`test_one_read_coherence_survives_post_read_mutation`: after `_snapshot_one_read` returns, the test deletes the working mapping, repoints the paired vocal mapping through the supported M17A API, and shrinks the Shot duration — the already-resolved tenth element and the snapshot built from the READ tuple still carry the originally captured values. This directly proves the intended boundary: the schema-8 content is fixed at read time, immune to subsequent current-state mutation.

## Gates (first-run dispositions recorded exactly)

- New slice-2 battery (`test_m17cc_capture.py`): **11/11**; capture-family + interaction suites (m13_shot_capture, m10d races/proofs, m16 recovery, all M17C batteries): **120/120**; focused suite: **570/570**.
- **Hard process gate honored**: committed BEFORE validators; committed-tree validation caught the five-validator carve for the three slice-2 files pre-push (`91c62a2`). All 21 validators green on the committed tree.
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite, FIRST RUN on `10b596b`: **2970 passed / 8 skipped / 1 failed** — the M7C structural-singularity spy's builder signature lacked the new `performance_pack` pass-through (fixture-side; the single-builder proof now also covers the schema-8 plane). Fix-forward `45d565f` (one line + comment); `test_m7c_capture` 29/29 post-fix.
- **CI run `36679790505` on `45d565f`: SUCCESS, attempt 1 — Backend 2959 passed / 20 skipped / 0 failed**; Frontend green. (An intermediate run on `91c62a2` failed only on the same spy finding — superseded by the fix-forward head.)
- Residue: slice 2's new files = `m17cc_capture_read.py`, `test_m17cc_capture.py`, `m17cc_capture_helper.py`.

## Next slice (unchanged)

Slice 3: fenced persistence of the companion parent/children, reuse-winner validation extended to the performance plane, and the §11.4 blocker surface.

---

# M17C-C slice 3 — frozen-companion persistence + winner-reuse validation — 2026-09-30 — IMPLEMENTED

Slice 3 is complete and green per the frozen one-sentence boundary: **persist and validate the same already-captured value; never resolve Performance again.** Slice-3 heads: **`4996bec`** (implementation) + **`73d9ccc`** (validator carves).

## Delivered (exactly the eight gate points)

1. **Fresh schema-8 persistence**: `_persist_revision_fenced` gains `performance_pack` — inside the existing BEGIN IMMEDIATE unit, `persist_performance_companions` inserts the PARENT FIRST (immediate SQLite FKs) then exactly `len(performance.segments)` children, every column the mechanical projection of the READ value (never a DB reread). ShotRevision behavior is unchanged.
2. **Canonical parent identity**: `spec_json` is the canonical serialization of the EMBEDDED performance value (`embedded_performance_value`/`performance_spec_bytes` — the frozen §11.2 key projection of the captured pack) and `spec_hash` hashes those exact bytes; no independent row reconstruction. Child `segment_json`/`segment_hash` are the canonical embedded segment.
3. **Exact child projection**: dialogue-bound children carry the complete vocal group; generic children the all-NULL group (matching the DB all-or-none CHECK); rationals stored as num/den pairs.
4. **Zero-companion predecessor behavior**: schema <8 captures write ZERO companion rows (no opportunistic upgrade); a schema-<8 winner unexpectedly carrying companions is refused at convergence as an impossible state ("snapshot hash does not require" invariant — defense in depth mirroring the intra_shot fence).
5. **Reuse winner validation**: the loser of a `(shot_id, snapshot_hash)` convergence validates the committed winner's COMPLETE companion closure (`verify_performance_companions`: exactly-one parent with canonical bytes/hash; exact child count, order, every field). Missing parent/child, reordered or incorrect position, altered field/spec_json/spec_hash all fail closed and are NEVER repaired — durable-closure corruption is an internal-invariant 500, not another readiness decision (§11.4 vocabulary unchanged).
6. **Atomicity**: any companion insert failure rolls back the WHOLE unit (fault-injection at child k>0 proven: zero ShotRevision/parent/children survive; the surface stays live and a clean capture afterwards succeeds).
7. **Race/reuse proof**: two concurrent captures of the same shot converge on one revision id and the loser validates the winner's companions; a tampered winner refuses the loser.
8. **Coherence through persistence**: read → mutate current mappings/binding/duration → persist the ALREADY-READ value → companions carry the pre-mutation captured values (extends the slice-2 mutability proof through the write).

Supporting read-side change (slice-3 scope, no slice-2 semantics touched): `resolve_performance_plane` now also captures the projection keys (payload blob hash, performance mapping hash, vocal mapping hash) alongside the embedded keys; the builder PROJECTS the frozen embedded keys from these richer dicts, so snapshot bytes stay byte-stable while companions carry the projection.

## Tests

New `tests/test_m17cc_persist.py` (12 cases over 8 functions; the corrupt-winner matrix parametrized ×5 with exact invariant-fragment assertions). The slice-2 no-companions boundary test is superseded to the slice-3 assertions (parent/child row identity against the canonical embedded value); the slice-2 grammar test now proves MISSING-key refusal (extra projection keys project away by design).

## Gates (first-run dispositions recorded exactly)

- Three M17C-C batteries (`test_m17cc_persist` 12 + `test_m17cc_capture` 11 + `test_m17cc_migration` 7): **30/30** (re-confirmed post-commit). Focused suite (46 files): **606/606**.
- **Hard process gate honored**: committed BEFORE validators; committed-tree validation caught the four-boundary carve for `tests/test_m17cc_persist.py` pre-push (`73d9ccc`). All 21 validators green on the committed tree — including both npm-audit validators fed the runtime audit document the CI way (bare invocation reads empty stdin; zero runtime vulnerabilities, baseline exceptions empty).
- Local full backend suite, FIRST RUN on `4996bec`: **2983 passed / 8 skipped / 0 failed** in 47:24 — no fix-forward needed this slice.
- **CI run `36705552791` on `73d9ccc`: SUCCESS, attempt 1 — Backend 2971 passed / 20 skipped / 0 failed**; Frontend green.
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Residue: slice 3's new files = `tests/test_m17cc_persist.py`.

## Fences honored

NO §12 historical inspection and NO §13.4 general recovery pass were started (their own slices); the §11.4 error vocabulary is unchanged (409 admission gate before the builder; corruption 500 in the read; durable-closure corruption = internal-invariant 500 only). `_validate_reuse_integrity` and the intra_shot fence untouched. PR #26 remains draft, unmerged, unready.

## Next slice (unchanged)

§12 historical inspection, then §13.4/§13.5/§13.6 recovery-verifier laws, then backup/restore + downgrade coverage — each its own slice.

---

# M17C-C slice 4 — §12 historical inspection — 2026-09-30 — IMPLEMENTED

Slice 4 is complete and green under the frozen rule: **historical inspection reconstructs what was captured, never what is true now.** Slice-4 heads: **`a0dd9b9`** (implementation) + **`0181aba`** (validator carves).

## Delivered (the ten gate points)

1. **Captured-graph-only read path**: new `server/soloring/performance/m17cc_history.py` — ONE async entry `verify_performance_history` (the `intra_shot_history` pattern) — consumed by the PUBLIC historical reader (`_revision_continuity`, `GET /shot-revisions/{id}/continuity`; the Generation continuity path inherits). It resolves only immutable references named by the captured graph: snapshot bytes + companion parent/children + `performance_revisions` / `performance_revision_vocal_bindings` / `vocal_performance_revisions` + the retained Blob row. No readiness calculation, no current resolution, no latest substitution.
2. **Exact per-segment answer**: subject; exact PR + immutable identity (kind, profile, payload schema version, source kind, temporal domain, adopted_at); exact payload bytes/hash + retained Blob size; exact VP + identity (line revision, revision number, speaker, native rate, retained audio hash) when dialogue-bound; exact vocal sample interval; Performance interval and Shot-relative anchor as canonical rationals; the immutable synchronization binding (binding hash + VP + sample interval + performance origin + synchronization basis version); captured mapping hashes exposed as closure.
3. **Schema branching stays historical**: the endpoint's legal outer-schema tuple admits 8 (previously schema-8 revisions failed as illegal); schema 8 requires and fully validates the performance plane (exactly-one parent, canonical spec bytes/hash, snapshot-block byte identity with the companion parent, frozen §11.2 grammar, non-empty, position-canonical; exact child count/order/column projection incl. the all-or-none vocal group against the embedded grammar); schema <8 keeps the exact predecessor behavior and never consults the performance companions at all (spy-proven, not merely implied by output); Performance is never inferred because current mappings exist.
4. **Current-state mutation immunity** (the direct product proof for the milestone exit criterion): capture → record the full historical response → **temptation fixture** (a newer internally-valid VP on the same line re-selected as current + a newer valid PR/mapping on a lawful disjoint interval) → delete every current vocal and performance mapping → clear the current Shot dependency selection → change Shot duration → read again on a **reopened session** (each HTTP request binds a fresh session; no identity-map cover) → **exact equality**, captured identities and captured ordering intact.
5. **Absence, not just correct output**: a `before_cursor_execute` spy on the engine (async engines take synchronous listeners on `sync_engine`) asserts ZERO statements touch `vocal_performance_selections`, `shot_vocal_segment_mappings`, `shot_performance_segment_mappings`, `performance_candidate*`, or `shot_entity_dependencies` while the schema-8 historical read runs; a second spy proves the companion tables are not consulted for schema <8.
6. **Immutable-closure corruption fails closed**: 13-case tamper matrix (missing parent, missing child, moved position, altered field, altered segment_json/spec_json/spec_hash, snapshot-block disagreement with consistent outer hash, PR disagreement, gone binding, binding disagreement, vocal-group nulled, vocal-group grafted) — each a typed internal-invariant 500 with the exact fragment, never a present-day fallback. The FK-shielded shapes (missing retained Blob behind `fk_pr_payload_blob` RESTRICT; missing VP behind binding + selection) are proven UNCONSTRUCTIBLE by IntegrityError, with the reader's existence laws standing as the §13.4 recovery-parity mirror.
7. **Dialogue and non-dialogue both proved**: the dialogue segment reconstructs the complete vocal object (VP identity + binding + sample interval + captured mapping hash); the generic segment reconstructs `vocal: null` in the same answer shape — the two forms stay distinct (the nulled/grafted group flips refuse).
8. **Ordering is captured ordering**: children are read `ORDER BY position` with positions verified `0..n-1`; the order survives deletion of every current mapping (proving it is not derived from current mappings, UUIDs, row order, or a temporal sort).
9. **No recovery-verifier expansion**: `m17c_verifier.py` untouched (0022 stays 0021-equivalent); the reader's laws are the local defensive validation a trustworthy answer needs. The exhaustive §13.4 sweep is the next slice.
10. **No derived-input semantics**: `generation_performance_inputs` is untouched and irrelevant to the §12 answer; no Generation-history endpoint was added (M17C-D territory).

**§11.5 closed on the read path** (disclosed scope note, not a new plane): a schema-8 wrap of a schema-7 predecessor reconstructs BOTH planes — the intra_shot outer-schema law admits the wrap (`7` → `(7, 8)`), a present embedded intra_shot block with gone companions is corruption (never silent absence, proven by tamper), and intra_shot provenance follows the reconstructed block. Schema-7-only behavior is byte-identical.

## Gates (first-run dispositions recorded exactly)

- New §12 battery (`test_m17cc_history.py`): **19/19** first run after three fixture-level corrections (async-engine listener must attach to `sync_engine`; the error body carries `message` not `detail`; the spec-hash tamper must respect the length-64 CHECK — the first attempt tripped `ck_srpfs_hash_len`, exactly the DB-CHECK-pinned pattern). The 8-over-7 test then surfaced two REAL laws to update, not fixture defects: the intra_shot verifier's outer-schema-7 pin and the events-table FK shielding the intra_shot spec parent (tamper deletes children first).
- Families: M17C-C four batteries + the endpoint-history families (m16 history + history_c, m6c continuity, m13 history/corrections): **109/109**; focused battery: **146/146**.
- **Hard process gate honored**: committed BEFORE validators; committed-tree validation caught the six-validator carve for the two new files pre-push (`0181aba` — 9th consecutive cycle). All 21 validators green on the committed tree (npm-audit pair fed the runtime audit document the CI way).
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite, FIRST RUN on the slice-4 tree: **2983 passed / 8 skipped / 0 failed in 46:09, exit 0** — collection verified independently (`--collect-only` = 2991 = 2983+8, the run is complete and self-consistent); no fix-forward needed.
- **Counting note (disclosed, slice-3-era)**: the slice-3 head `73d9ccc` collects **2972** in a clean worktree, 19 below the 2991 total both its local run (2983/8) and CI (2971/20) executed — that anomaly predates this slice and does not touch the slice-4 tree, whose collection equals its local execution exactly; the slice-4 CI total (3010 = 2990/20) moved +19 from slice 3's exactly as the added battery predicts. Slice 3's green stands on its CI corroboration.
- **CI run `36718111656` on `0181aba`: SUCCESS, attempt 1 — Backend 2990 passed / 20 skipped / 0 failed**; Frontend green (143/143).
- Residue: slice 4's new files = `m17cc_history.py`, `test_m17cc_history.py`; touched predecessor files = `api/continuity.py` (schema-8 branch + response key), `continuity/intra_shot_history.py` (one law admits the wrap).

## Fences honored

NO §13.4/§13.5/§13.6 recovery-verifier expansion; NO derived-input semantics; §11.4 vocabulary unchanged; capture paths untouched (slice-3 persistence unmodified). PR #26 remains draft, unmerged, unready.

## Next slice (unchanged)

§13.4 captured-schema-8 recovery-verifier laws (+ §13.5 Blob-FK inventory advance, §13.6 structural derived-input laws), then §1.7 backup/restore + downgrade coverage.

---

# M17C-C slice 5 — §13.4/§13.5/§13.6 recovery verifier — 2026-09-30 — IMPLEMENTED

Slice 5 is complete and green under the frozen rule: **recovery independently proves that the durable database can reconstruct and validate every M17C-C historical claim without relying on current working state or the §12 API implementation.** Slice-5 heads: **`8468dde`** (implementation) + **`ebe7e1b`** (validator carves).

## Delivered (the fifteen gate points)

1. **Head behavior explicit**: at 0022 the three capture tables are REQUIRED (a 0022 database missing them is structurally corrupt) and two new passes run inside `verify_m17c_binding_state` AFTER every unchanged predecessor pass; at 0020/0021 any companion or derived-input ROW refuses ("rows those heads cannot represent") while the tables themselves may remain as create_all staging artifacts.
2. **Total schema classification**: every ShotRevision decodes, must declare integer schema 1..8, and is either schema <8 with ZERO companions or schema 8 with its parent — no "companions ignored because the snapshot is old", no "schema 8 accepted without companions"; orphan companion rows refuse.
3. **Predecessor verification first**: the passes extend the restore chain, never replace it — and the M16 recovery verifier now admits the §11.5 schema-8 wrap (history enumerated for schema 7 OR schema 8-with-retained-block; companions require outer 7 or the wrap WITH the block), so an 8-over-7 capture verifies BOTH planes through the unchanged intra_shot history law. This was a real gap: schema-8 wraps would previously have corrupted the M16 recovery pass.
4. **Snapshot↔parent equivalence** at canonical-BYTE strength: the embedded `performance` block reproduces the parent `spec_json` exactly; the canonical bytes reproduce `spec_hash`; the parent's own canonical form re-verifies.
5. **Parent↔children equivalence**: count, canonical ordering, `segment_json`/`segment_hash` canonical pair, every projection column, rational fields, and all-or-none vocal nullability project exactly from the embedded grammar (the recovery form of the slice-3 persistence invariant).
6. **Immutable closure revalidated independently**: PR existence + subject/kind/profile/sha/blob-hash agreement; the retained payload Blob exists, rehashes, and parses as the channel document; dialogue-bound children re-resolve the exact binding (hash/VP/rate) and the exact VP. The frozen `EMBEDDED_SEGMENT_KEYS` constant is the ONE shared law source; `m17cc_history` is never imported.
7. **Exact arithmetic recomputed** with Fractions (never float): canonical rationals (gcd law), non-empty interval, generic containment in the PR temporal domain, the §8.3 binding-induced interval `origin + (sample − s0)·1000/rate` reproduced with NO tolerance, and the captured sample interval inside both the binding interval and the VP trim.
8. **Historical project/subject coherence**: PR↔Shot project equality, VP speaker == captured subject, VP dialogue-line project == shot project — never current dependency selection or duration.
9. **Captured conflict law**: overlapping same-subject pairs refuse only when their retained-payload CHANNEL sets intersect — the lawful D14 disjoint-channel overlap (the fixture world itself) does not refuse. Evaluated from captured rows + immutable payloads, never current mappings.
10. **§13.5 stays mechanical**: the backup module's head-gated 14-path Blob-FK inventory at 0022 (slice 1) is untouched.
11. **§13.6 structural only**: parent Generation + same-creation-unit (`created_at` equality), role vocabulary (DB-CHECK-pinned — the law stands as the mirror), 64-char lowercase-hex digests, retained derived bytes rehash, exact segment tieback (`segment_hash` + position + PR + vocal group; `performance.vocal_audio` requires the vocal identity), translation identity materialized in the Generation execution spec (canonical spec pair + grammar-agnostic presence — the exact spec-field grammar freezes with the M17C-D writer, disclosed), and the control-schedule/vocal-audio §14.6 sampler laws remain the EXPLICIT deferral — no substitute sampler invented.
12. **No writer semantics**: recovery never creates or derives GPI rows; test fixtures construct them on staged copies.
13. **Tamper coverage mirrors the laws**: a 17-case matrix — schema8/no parent, empty children, count mismatch, moved position, altered field/segment_json/spec_json, snapshot-block disagreement (coherent outer hash), PR mismatch, gone binding, nulled vocal group, payload blob missing/corrupt, **three coherent-everywhere rewrites** (timing, subject+PR, PR-swap-to-shared-channels) that pass every internal-consistency law and are caught ONLY by the recomputed immutable-authority arithmetic/speaker/conflict laws, and cross-project.
14. **Independence from §12 proven**: with `verify_performance_history` monkeypatched to explode, recovery still passes clean state and still refuses tampered state.
15. **No backup/restore work started** beyond what the positive proof needs (the clean 8-over-7 full-restore round-trip is the §1.7 prerequisite evidence, not the slice).

## Gates (first-run dispositions recorded exactly)

- New §13.5 battery (`test_m17cc_recovery.py`): **23/23**. First-run corrections were fixture-level (restore entry lives in `recovery.backup`, not a `restore` module; the role vocabulary values are the full `performance.*` strings; a staged GPI blob must be placed at the canonical path on the staged copy — liveness at backup time knows nothing of fixture rows; the generation fixture inserts directly on the staged copy, the m13-history pattern, to avoid dragging workflow-artifact liveness in; raw-sqlite3 tampering raises the driver's IntegrityError). Two fragments deliberately name the PREDECESSOR pass that fires first (deleted binding → the PF-03 "total companion loss" refusal; PR subject → the chain's "subject != bound VP speaker") — the predecessor-first ordering is itself the proven law.
- Families: recovery/capture/history batteries incl. m16 recovery + m17a/m17b recovery: **103/103**; backup/restore + history: **76/76**.
- **Hard process gate honored**: committed BEFORE validators; committed-tree validation caught the four-boundary carve pre-push (`ebe7e1b` — 10th consecutive cycle). All 21 validators green on the committed tree.
- Frontend: vitest **143/143**, `tsc --noEmit` clean, `next build` succeeds.
- Local full backend suite, FIRST RUN on the slice-5 tree: **stalled** — killed and characterized in two stages. Stage 1 (memory): the §13.4 traversal held every decoded snapshot simultaneously and the process reached 9.3 GB into the scale tests (restore runs the pass over the whole staged DB); fixed the same slice by `2aba5e8` — the traversal STREAMS (phase 1 retains only `(shot_id, schema)` per revision; phase 2 re-decodes only the schema-8 snapshots; the memory law is documented in the pass). `test_m10f_scale` — the family that exposed the blowup — 7/7 in 26 s post-fix; battery 23/23 re-confirmed. Stage 2 (environment): the second run stalled at `test_m14_exec_100` with the ComfyUI worker's CPU frozen at 17.5 GB — leftover processes from the killed first run held the lane; after teardown the exec battery passes **9/9 in 28:05 in isolation**, and the clean third run is the recorded result: **3006 passed / 8 skipped / 0 failed in 50:13, exit 0** (collection 3014 = the slice-4 total 2991 + the 23-test battery — the arithmetic closes exactly). No product fix-forward beyond the streaming correction.
- **CI run `36764570572` on `2aba5e8`: attempt 1 failed ONLY on the characterized M7D race_r8 SQLite flake (`test_race_r8_concurrent_identical_relation_captures_converge` — "Database is busy"; 3012 passed / 20 skipped / 0 other failures); rerun-failed-jobs per the standing precedent → attempt 2 SUCCESS — Backend 3013 passed / 20 skipped / 0 failed** (CI total 3033 = its slice-4 total 3010 + the 23-test battery, arithmetic exact); Frontend green attempt 1.
- Residue: slice 5's new files = `tests/test_m17cc_recovery.py`; touched predecessor files = `recovery/m17c_verifier.py` (the two passes + head wiring), `recovery/m16_verifier.py` (the §11.5 wrap admission, two laws).

## Fences honored

NO backup/restore/downgrade slice work (§1.7 is next); NO §14.6 sampler or derived-input writer semantics (M17C-D); §13.5 inventory untouched; the §12 reader untouched. PR #26 remains draft, unmerged, unready.

## Next slice (unchanged)

§1.7 backup/restore + downgrade closure — CORRECTED WORDING (2026-09-30, review correction accepted): two DISTINCT assertions, not one. (1) A real populated **0021** database cannot already contain the three 0022 M17C-C tables — the frozen upgrade requirement is a real-0021→0022 upgrade retaining every **M17C-B predecessor row** verbatim with the three new tables created empty. (2) Separately, M17C-C state created AT 0022 (schema-8 captures, companion rows, fixture-valid derived inputs) then proves backup/restore durability. Clean round trips preserving companions, populated downgrade refusals naming the tables, and the head-sweep of test constants.




---

# M17C-C slice 6 — §1.7 backup/restore + downgrade closure — 2026-09-30 — IMPLEMENTED

Slice 6 is complete and green under the frozen rule: **valid M17C-C historical closure survives backup/restore exactly; invalid downgrade cannot erase it.** This closes the last M17C-C slice; the capture-phase record wording correction (real-0021→0022 retains M17C-B PREDECESSOR rows; M17C-C state is created AT 0022 and round-tripped separately) is applied above as two distinct assertions.

## Delivered (the fourteen gate points)

1. **Real 0021→0022 staged upgrade (verbatim)**: a genuine populated 0021 database (a lawful M17C-A/B world reshaped to the 0021 identity — three successor tables dropped, head stamped, manifest canonically rewritten) upgrades through the actual migration with ROW-CONTENT FINGERPRINTS over twelve predecessor surfaces (candidates, PRs, VPs, selections, alignments, both binding tables, both classification tables, both working-mapping tables, blobs) plus the table inventory (M17C-C tables excluded — they legitimately appear) provably IDENTICAL, the three new tables existing EMPTY, and recovery green at 0022.
2. **Clean schema-8 round trip**: dialogue+generic capture → backup → restore fresh → snapshot bytes/hash, companion parent, children (count/order/bytes/hashes/projection), immutable PR/VP/binding/classification rows, and the blobs table byte-identical (BEFORE fingerprints read the live DB file AFTER the backup — the backup checkpoints WAL, so the file is exactly the staged state); the §12 historical response IDENTICAL through the ACTUAL public reader running on a second app bound to the restored tree; full recovery verifier green.
3. **The milestone exit criterion composite**: 8-over-7 capture → every forbidden current surface mutated (newer VP re-selected, newer PR/mapping, all current mappings deleted, dependencies cleared, duration changed) → historical read A → backup → restore into a FRESH tree (the restored app is disjoint from the live tree, so read B provably reads only the restored closure) → recovery verifier green → historical read B → **A == B exactly**, both planes intact.
4. **8-over-7 survives restore**: covered by the composite (intra_shot AND performance planes both present and equal in B).
5. **GPI durability through a REAL backup**: fixture-valid rows inserted into the LIVE database (schema-1 WorkflowSpec carrying the translation identity, content-addressed manifest/template artifact files at the canonical hash-sharded paths, real placed Blob bytes so the 14-path liveness walk finds them) survive backup/restore with generation identity, roles, blob hashes, retained bytes, segment tiebacks, translation identity, and derived-input hashes EXACT; the §13.6 recovery laws validate them on the restored tree. No production writer.
6. **Blob-FK inventory restoration**: the restored 0022 database's FK metadata yields EXACTLY the 14-path head policy (generation_performance_inputs.blob_hash the sole M17C-C addition; the predecessor set proven 13 without it), certified mechanically by the restore-time liveness enumeration; a genuine 0021-retargeted backup restores at 13 paths with the verifier green at 0021.
7. **Three populated-downgrade fences** naming the blocking table — already frozen in test_m17cc_migration (specs/segments with the FK-off isolated child proving the SEGMENT fence independently/GPI), unchanged by this slice.
8. **Empty downgrade**: 0022→0021 drops cleanly with all three tables gone and the resulting database ACCEPTED by the predecessor head (verifier green at 0021).
9. **Non-destructive refusal**: on a VALID schema-8 staged state the downgrade refuses at the specs fence, the head stays 0022, parent/children fingerprints are byte-identical afterward, no table is partially dropped, and recovery stays green — the fence fires before any destructive DDL.
10. **Explicit backup inclusion**: the restored file's FK metadata + the liveness enumeration certify the three tables and their Blob path mechanically — a future logical-omission cannot pass the inventory equality.
11. **Head sweep (mechanical, this slice)**: every committed-tree occurrence of `0022_m17c_schema8_capture` / `0021_m17c_shot_performance_mappings` / the head sets classified — product side: backup.py (M17C_C head = current EXPECTED, M17C_B = predecessor restore target, SUPPORTED set, 14-path policy), successor_semantics (6 chain memberships incl. M17C_C), m17c_verifier (head-aware trio), the two migration identities; validator side: m14/m16 boundary regexes admit the 0021 migration path (predecessor-specific by design); test side: the seed/stamp/baseline constants advancing to 0022 (slice-1 sweep, annotated) and the sr2 assertion `M17C_C_ALEMBIC_HEAD == "0022..."`. **No stale 0021-as-latest anywhere.**
12. **Predecessor behavior frozen**: the 0021-retargeted restore green at 13 paths + verifier at 0021 + slice-5's rows-refused laws re-confirmed in the inventory test.
13. **No new capture/history/recovery semantics**: zero product-code changes in this slice — the battery proved the slices-2–5 laws compose; no defect was found requiring revision.
14. **No M17C-D encroachment**: GPI rows are fixtures only.

## Gates (first-run dispositions recorded exactly)

- New §1.7 battery (`test_m17cc_roundtrip.py`): **7/7**. First-run corrections were fixture-level (the predecessor-table fingerprint legitimately excludes the three appearing tables; the 13-path constant is `M17B_BLOB_FK_COLUMNS`; a live-DB fixture generation must satisfy the backup's generation-liveness contract — schema-1 spec with an `inputs` object, plus CONTENT-ADDRESSED manifest/template artifact files at `kind/sha256/xx/yy/<hash>.json` whose real hashes feed the generation row).
- Families: migration + recovery + history batteries re-confirmed alongside.
- Local full backend suite, FIRST RUN on the slice-6 tree: **3013 passed / 8 skipped / 0 failed in 47:00, exit 0** (collection 3021 = the slice-5 total 3014 + the 7-test battery — exact); no fix-forward, no stall.
- **CI run `36783206959` on `75dc465`: SUCCESS, attempt 1 — Backend 3020 passed / 20 skipped / 0 failed** (CI total 3040 = its slice-5 total 3033 + the 7-test battery, arithmetic exact); Frontend green (143/143).
- Residue: slice 6's new files = `tests/test_m17cc_roundtrip.py`; product code UNCHANGED.

## Fences honored

No capture/history/recovery law revisions; no §14.6 sampler or GPI writer; PR #26 remains draft, unmerged, unready — ready for the exhaustive final first-pass review against the frozen R0 scope and predecessor-impact register.

---

# M17C-C exhaustive first-pass review — 2026-10-01 — NOT CLEAN (findings register FROZEN)

The independent exhaustive first-pass review of final HEAD `1680e8c1078800fba9d1083b2c8763dc7620be57` is complete. PR #26 remained draft, open, unmerged, and unchanged during the review. **Verdict: NOT CLEAN — eight findings: 2 High, 4 Medium, 2 Low.** The register below is frozen; any second-review/Codex pass starts from it independently.

## Frozen findings register (summary; the review document is the authority)

1. **FPR-M17CC-01 — HIGH — Generation / successor-schema execution semantics.** The Generation service is not schema-8-aware: M16's event-capability refusal fires only at outer schema 7, spatial authority loads only at outer (5, 6), M14 observation integration only at outer 6 — so a legal schema-8 wrap can bypass `INTRA_SHOT_REALIZATION_UNSUPPORTED`, silently drop captured spatial/observation predecessor authority, and persist a Generation below the authority the revision actually carries. Safe pre-M17C-D posture = successor-aware preservation of predecessor execution laws OR a typed fail-closed schema-8 realization refusal — never lowering.
2. **FPR-M17CC-02 — HIGH — effective working snapshot / canon currency.** `effective_working_snapshot_hash()` has no `performance_pack` path and `read_shot_detail()` never resolves the Performance plane before exposing the working hash — while `differs_from_approved()` assumes the same canonical builder capture uses. An unchanged Performance state can report divergence; a Performance-only change does not participate. The currentness/canon invariant stops meaning what the API says.
3. **FPR-M17CC-03 — MEDIUM — observation readiness.** `observation_readiness()` consumes the 10-element one-read only through index 7, and declares any captured outer schema other than exactly 6 not-applicable ("carries no production world") — factually wrong for a schema-8-over-6 capture that retains the exact `production_world` block; `capture.is_current` also derives from the Performance-blind hash.
4. **FPR-M17CC-04 — MEDIUM — captured mapping-hash anchoring.** `performance_mapping_hash` and `vocal_mapping_hash` are companion-only closure fields — excluded from the embedded segment and from `segment_json`/`segment_hash`, unanchored in §12 reconstruction and §13.4 recovery, and unexercised by the tamper matrix. Post-capture mutation of either column alters the historical answer while every hash and recovery stays green. The fix needs an immutable anchor (captured preimage or a full-child closure hash), never a current-working-mapping read.
5. **FPR-M17CC-05 — MEDIUM — §12 retained payload bytes.** The historical reader verifies only the `blobs` DB row and returns hash/sha/size metadata; it neither opens nor rehashes nor can supply the retained payload bytes R0 requires. Physical deletion/corruption of the payload file with the DB row intact currently returns 200.
6. **FPR-M17CC-06 — MEDIUM — §13.6 translation identity.** Recovery accepts `translation_identity` occurring anywhere as any JSON string value in the WorkflowSpec — presence, not identity equality. A wrong identity passes when the same string appears in an unrelated field. The exact identity coordinate must be frozen before M17C-D writes rows.
7. **FPR-M17CC-07 — LOW — pure builder schema-8-over-schema-1.** `build_capturable_snapshot()` returns the zero-dependency schema-1 base before reaching the Performance wrapper, contradicting the frozen any-schema-1–7 wrap law. Unreachable through current PF-02 admission (READY Performance requires a dependency-bearing world) — a false pure-builder law, not a production data-loss path today.
8. **FPR-M17CC-08 — LOW — recovery fixture portability.** `_coherent_child_rewrite` mixes named SQLite placeholders with a positional parameter sequence passed to `sqlite3.execute` — 39 deprecation warnings in CI; becomes `ProgrammingError` under Python 3.14. Fixture-only.

## Review scope assessment (as recorded by the reviewer)

The six-slice record is materially accurate; the §1.7 proof, the one-read/persist core, the head-gated inventories, and the boundary-carve narrowness held up. The earlier concern about undisclosed M17C-A/B recovery-chain changes is CLOSED (the successor chain pre-existed frozen baseline 8a92bc6; M17C-C only adds 0022 membership; the M16 8-over-7 recovery admission is disclosed, required predecessor impact). The defects concentrate where the new outer schema crosses existing consumers, and where companion-only closure is weaker than the frozen historical/recovery claim.

## Open design decisions the corrections must resolve

- The pre-M17C-D Generation posture: preserve all predecessor execution semantics while deferring only Performance, or refuse schema-8 realization until the M17C-D adapter exists.
- A durable, §12-lawful anchor for the two captured mapping hashes (capture-schema/closure design, not another verifier `if`).
- The transport shape of §12 exact retained payload bytes (encoded, subresource, or other — R0 requires the bytes but not the encoding).

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. Known findings FPR-M17CC-01..08. Primary blockers 01 and 02. PR #26 remains draft, unmerged, unready. Merge/ready-mark NOT authorized by this review. Second reviewer/Codex NOT run.** No correction work has started; the correction cycle awaits its gate.

---

# M17C-C first-pass-review CORRECTION CYCLE — FPR-M17CC-01..08 — 2026-10-01 — IMPLEMENTED

The correction gate was authorized against the frozen register; the three architectural decisions were resolved FIRST per the mandated sequence, then all eight findings corrected, beginning with the blockers. Correction head: **`7a06474`** (amended; the first commit `05fc5b4` → `438ca1f` → `bc238f2` → `7a06474` chain reflects fixture/gate convergence inside one logical delta — a mid-cycle `git stash --keep-index` mishap cost the working tree and was fully recovered from the dangling stash commit `7a29c47f`, byte-verified by content greps before the commit; lesson recorded).

## The three architectural decisions (resolved first)

- **A — pre-M17C-D Generation posture = typed fail-closed refusal.** M17C-D owns Performance translation; running predecessor-only execution of a performance-bearing revision is not a lawful posture, and silent lowering is what FPR-01 condemned. New `ErrorCode.PERFORMANCE_REALIZATION_UNSUPPORTED`; the generation seam refuses ANY schema-8 ShotRevision terminally (409, before any Generation row/Input/artifact/queueing), mirroring the M16 schema-7 refusal contract. An 8-over-7 wrap can no longer bypass `INTRA_SHOT_REALIZATION_UNSUPPORTED`, and 8-over-5/6 can no longer silently drop captured spatial/observation authority.
- **B — mapping-hash anchor = captured preimage.** Successor migration **`0023_m17cc_capture_closure_preimage`** adds `vocal_mapping_position` + `vocal_performance_origin_num/den` to the companion children (verified: the vocal mapping's origin is caller-supplied at its PUT and pinned by NO law to the binding's origin) so BOTH mapping hashes recompute as pure functions of the stored child row. The frozen §11.2 embedded grammar and every snapshot byte law are untouched. The 0023 upgrade refuses populated 0022 segments (preimage is CAPTURE data, never backfilled); the downgrade fences ALL THREE M17C-C tables (alembic commits per migration step — a segments-only fence would let the destructive recreate run for a specs/GPI-only populate before the 0022 fence fires).
- **C — §12 byte transport = inline base64.** The historical answer carries `payload_bytes_base64` of the physically-read, sha256-verified retained bytes; a missing or corrupt physical file (DB row intact) fails closed with typed invariants.

## The eight corrections

1. **FPR-01 (HIGH)** — the refusal above; verified by plain-8 and 8-over-7 generation tests (typed code, no persistence).
2. **FPR-02 (HIGH)** — `effective_working_snapshot_hash` gains `performance_pack` (still delegating to THE builder) and `read_shot_detail` resolves the plane on its pinned snapshot: unchanged Performance equals the captured hash (canon equality), a Performance-only change moves it, reverting restores it exactly.
3. **FPR-03 (MEDIUM)** — `observation_readiness` consumes the full 10-element one-read and unwraps schema 8 to the WRAPPED predecessor for applicability: an 8-over-6 capture runs the schema-6 posture on the retained production_world (never "not-applicable"); `is_current` is Performance-aware; a profile-less release now declares no observation capability (refused branch) instead of crashing.
4. **FPR-04 (MEDIUM)** — `expected_mapping_hashes` / `_child_preimage_vocal` / `verify_mapping_hash_closure` (ONE pure law in m17cc_capture_read) consumed by §12, §13.4, and capture; tamper of EITHER mapping-hash column alone refuses at both surfaces (tested).
5. **FPR-05 (MEDIUM)** — `_verified_payload_bytes` in the §12 reader; bytes round-trip test + missing/corrupt fail-closed.
6. **FPR-06 (MEDIUM)** — identity equality at the frozen coordinate `spec["performance_translation"]` (recursive presence-anywhere removed); the coordinate is frozen ahead of M17C-D; an identity appearing only in an unrelated field refuses, and an unrelated duplicate does not refuse a correct identity.
7. **FPR-07 (LOW)** — the pure builder's zero-dependency schema-1 base falls through to the Performance wrap (any-schema-1-7 law now true, directly tested).
8. **FPR-08 (LOW)** — the recovery fixture is fully named-parameter.

## Head advance 0022→0023 (plumbing)

`EXPECTED/SUPPORTED` heads + the 14-path policy (0023 adds NO Blob path), successor chains (6 memberships), verifier heads (0022 remains supported; its schema-8 companion rows REFUSE — preimage-less closure cannot certify), seeds/stamps/test constants swept (SUPPORTED sets keep 0022 alongside 0023), migration-count/head asserts, and validator admissions (hygiene+nsec admit the 0023 file and its recreated table names; the m16 surface admits successor_semantics + observation; the m16 generation-fence vocabulary covers the schema-8 refusal; m14 source-fit admits readiness.py whose unwrap legitimately names the intra-shot block; the m14 baseline admits 0023 as the head; the m15 baseline byte-pins the readiness correction; the m17b h06 source gate modernizes to "every performance occurrence inside the refusal block"; sr2_01 asserts the C2 head). The roundtrip battery's non-destructive test now names the 0023 fence.

## Gates (first-run dispositions recorded exactly)

- FPR battery **10/10**; the combined affected battery converged to **230/230** after gate amendments (m15 baseline byte-pin + admitted sets; m16 recovery/m12/m14-derived SUPPORTED sets regain 0022; m17b h06 gate modernized; sr2_01 C2 head).
- Local full suite on the final amended tree: **3023 passed / 8 skipped / 0 failed in 45:37** (collection 3031 = the slice-6 total 3021 + the 10-test battery — exact). One earlier run (pre-final-fixes) was killed as tree-mixed; its 2 failures were the two gate tests fixed above.
- Committed-tree validators: all green after the four-boundary carve for `tests/test_m17cc_fpr_corrections.py` and the 0023 admissions.
- Frontend: vitest **143/143**, tsc clean, build succeeds.
- **CI run `36842093290` on `7a06474`: SUCCESS, attempt 1 — Backend 3030 passed / 20 skipped / 0 failed** (CI total 3050 = its slice-6 total 3040 + the 10-test battery, arithmetic exact); Frontend green attempt 1 (143/143).
- Residue: new files = migration 0023 + `tests/test_m17cc_fpr_corrections.py`; the §1.7 exit-criterion composite and every prior slice battery remain green under the corrected head.

## Fences honored

No Codex/second pass run; no merge/ready; PR #26 remains draft/unmerged/unready. The corrected HEAD now awaits the re-run of the exhaustive first-pass review and the freezing of the NEW register, per the mandated sequence.

---

# M17C-C corrected-head exhaustive first-pass RE-REVIEW — 2026-10-01 — NOT CLEAN (register RR-M17CC-01..04 FROZEN)

The fresh independent re-review of corrected HEAD `7a06474` (against the frozen R0 scope, the predecessor-impact register, the original register FPR-M17CC-01..08, and the correction claims; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 4 findings: 0 High, 3 Medium, 1 Low.** PR #26 remains draft, open, unmerged (tip `aa08e932`). The new register is frozen; the next lawful step is a correction cycle against RR-M17CC-01..04.

## Original-register closure status (as certified by the re-review)

- **CLOSED:** FPR-M17CC-01 (typed terminal schema-8 generation refusal), FPR-02 (READY Performance in the pinned working hash + canon equality/sensitivity), FPR-05 (physical §12 payload bytes, base64, fail-closed), FPR-06 (identity equality at the dedicated coordinate), FPR-07 (schema-8-over-schema-1 wrapping), FPR-08 (fully named SQLite parameters).
- **STILL OPEN:** FPR-M17CC-03 (the 8-over-6 unwrap is incomplete), FPR-M17CC-04 (preimage gives recomputability, not immutable anchoring).
- The 0023 recovery/head plumbing held up (expected head, 0022 as the preimage-less historical posture, 14-path inventory, predecessor chain), and CI 36842093290's green was independently corroborated — green gates do not invalidate the uncovered branches.

## Frozen findings register (summary; the review document is the authority)

1. **RR-M17CC-01 — MEDIUM — FPR-03 remains open.** The 8-over-6 observation unwrap strips only `performance` and leaves `schema_version: 8` on the "predecessor" handed to the frozen M14 compiler, which strictly refuses any schema ≠ 6 — the supported observation-capable case still fails. The correction test reached only the profile-less refusal branch. Required: reconstruct the actual wrapped schema-6 predecessor INCLUDING `schema_version: 6`; add an observation-capable test that reaches `compile_world_observation_spec`.
2. **RR-M17CC-02 — MEDIUM — NEW.** A supported DELETE of the paired vocal mapping is a lawful `BLOCKED_BINDING_INTEGRITY` working state (M17C-B), but `resolve_performance_plane()` raises corruption when the paired mapping is missing — BEFORE the capture gate can issue its frozen 409, and (via the FPR-02 route) making `GET /shots/{id}` 500 on a merely-blocked plane. Required: separate "project readiness" from "extract complete capturable closure" — non-READY must survive as data for the typed refusal and non-capture readers. The reviewer's open question to freeze during this correction: whether `working_snapshot_hash` for lawfully non-READY Performance is null (the predecessor unready-layer pattern) or hashes the current-but-uncapturable state — must be an explicit decision, not implicit.
3. **RR-M17CC-03 — MEDIUM — FPR-04 remains open.** The 0023 preimage makes both mapping hashes recomputable but not immutably anchored: a COHERENT rewrite of `vocal_mapping_position` (or the vocal origin pair) plus the recomputed mapping hash passes §12 and recovery — no snapshot field, segment hash, or immutable authority row carries the historical working-mapping value. The reviewer's correction-design note (accepted): preimage provides recomputability, not anchoring, unless a digest of the preimage is itself covered by the ShotRevision's immutable snapshot identity or an equivalently independent immutable authority; another companion-only self-hash is not enough. Required adversarial test: a coherent preimage+hash rewrite, not merely hash-only mutation.
4. **RR-M17CC-04 — LOW — NEW proof-gate defect.** The corrected M16 boundary validator defines `GENERATION_FENCE_OK_8` but never requires it; `main()` still verifies only the schema-7 fence while the broadened per-line vocabulary admits generic terms — the validator stays green even if the schema-8 refusal is removed. Not a product failure at `7a06474` (the FPR battery protects the implementation); a misleading proof claim. Required: positively require the schema-8 fence and its ordering, structurally/AST-anchored rather than a broad keyword allowlist.

## Missing evidence the correction battery must add

An observation-capable 8-over-6 readiness call reaching the M14 compiler; a supported paired-vocal DELETE followed by Shot detail AND capture proving no 500 and the correct non-READY posture; a coherent preimage+mapping-hash rewrite refused by §12 and recovery.

## Frozen disposition

**FIRST-PASS RE-REVIEW COMPLETE. New register RR-M17CC-01..04 frozen. Original findings: 01/02/05/06/07/08 closed; 03/04 open. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a correction cycle against RR-M17CC-01..04; only after another corrected HEAD passes an independent first-pass review does the second-review/Codex phase begin. No correction work has started; the cycle awaits its gate.

---

# M17C-C re-review CORRECTION CYCLE — RR-M17CC-01..04 — 2026-10-01 — IMPLEMENTED

The correction commission against the frozen re-review register is complete, with the non-READY working-hash posture frozen by the commission (mappings exist + any non-READY ⇒ `working_snapshot_hash` AND `working_state_differs_from_approved` NULL — a blocked state is never hashed into a second, uncapturable canon, mirroring the M16 unready-layer law). Correction heads: **`e172299`** (implementation) + the validator-carve commit.

## The four corrections

1. **RR-01 / FPR-03** — the observation compiler receives the LITERAL schema-6 view: the 8-over-6 unwrap reconstructs the true schema-6 predecessor (`schema_version: 6`), and an 8-over-7-over-6 chain ALSO strips the M16 successor layer (`intra_shot`) before the frozen M14 compiler. A projection for M14 consumption only — the captured ShotRevision is never rewritten (proven byte-identical before/after). Proven with a compiler SPY on observation-capable packages (the m14 execution fixture) for BOTH 8-over-6 and 8-over-7-over-6: called exactly once, `schema_version == 6`, no `performance`/`intra_shot` keys, `production_world` present.
2. **RR-02** — readiness CLASSIFICATION separated from capturable-closure EXTRACTION: `resolve_performance_plane` returns the blocked projection as DATA (`segments=None`) unless every segment is READY; a missing paired vocal mapping remains the lawful `BLOCKED_BINDING_INTEGRITY` state (the corruption raise now covers only the impossible mid-pinned-snapshot disappearance under an all-READY projection). The frozen posture is wired into Shot detail (hash/differs NULL) and the observation working-hash/`is_current`; capture consumes the same projection and returns the typed 409. The supported-DELETE test proves: readiness reports `BLOCKED_BINDING_INTEGRITY`, `GET /shots/{id}` succeeds with null hash/differs, capture 409s with diagnostics, zero revision/companion writes. DISCLOSED as the commission required: this correction necessarily touches the PF-02 boundary — it PRESERVES the existing blocked-state vocabulary (the projection is unchanged; only the consumer's classification of missing capture material changed from corruption to data).
3. **RR-03 / FPR-04** — the mapping identity is SNAPSHOT-ANCHORED via the explicit versioned capture-schema transition (grammar v2; no migration needed — the companion columns already exist from 0023, the grammar version IS the fence): the embedded performance block declares `schema_version: 2` and the frozen segment key set grows to fourteen — the two mapping hashes AND their preimage (`vocal_mapping_position` + the vocal origin pair) are now part of the schema-8 snapshot/segment identity. The chain: captured preimage → recomputed mapping hash → SNAPSHOT-ANCHORED hash (segment_hash → parent spec_hash → snapshot identity). The ONE shared projection (`_embedded_segment`) keeps snapshot and companion bytes in lockstep (the builder consumes it via `_performance_segments_value`). Grammar v1 blocks are REFUSED by both §12 and recovery ("grammar-v1 performance block … re-capture") — pre-anchor captures are never silently certified. The decisive adversarial proof: a COHERENT child-side `vocal_mapping_position` (or origin) rewrite WITH the recomputed mapping hashes refuses at both surfaces through the embedded-segment (snapshot identity) comparison — not through a forgotten dependent hash.
4. **RR-04** — the M16 boundary validator POSITIVELY certifies the schema-8 fence: new `schema8_fence_check` (structural — the `PERFORMANCE_REALIZATION_UNSUPPORTED` token must exist, be anchored to its `if snapshot_schema == 8:` gate inside a raise statement, and PRECEDE the first Generation-owned durable side effect, the release placement), wired into `main()` and proven by deletion + relocation negative tests. The generic keyword allowlist was NOT widened.

## Gates (first-run dispositions recorded exactly)

- Correction battery `tests/test_m17cc_rr_corrections.py`: **7/7** first run after the compiler-spy target fix (the readiness module resolves the compiler through the package attribute; patching the package symbol). The relocation negative test needed the precise fence span (the release-placement anchor lies between the two `if release is not None:` blocks).
- Batteries: the eight m17cc files **96/96**; predecessor families (m13 history/recovery, m14 obs/execution, m16 history/recovery, m7c, m6c) **118/118**.
- Committed-tree validators: all green after the four-boundary carve for the RR battery.
- Frontend: vitest **143/143**, tsc clean, build succeeds.
- Local full backend suite, first run: **3029 passed / 8 skipped / 1 failed** — the single failure was the m15 baseline's successor BYTE-PIN on `observation/readiness.py` (the RR corrections legitimately changed those bytes; the pin law working as designed), re-pinned in `82f51a6`. Clean rerun on `82f51a6`: **3030 passed / 8 skipped / 0 failed in 47:34, exit 0** (collection 3038 = the prior 3031 + the 7-test RR battery — exact).
- **CI run `36877119569` on `82f51a6`: SUCCESS, attempt 1 — Backend 3037 passed / 20 skipped / 0 failed** (CI total 3057 = its prior 3050 + the 7-test RR battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

The six certified-closed original findings were not reopened (RR-02's seam is the disclosed integration point); no Codex/second review run; no merge/ready; PR #26 remains draft/unmerged/unready. The corrected implementation head now awaits the NEXT fresh independent exhaustive first-pass review per the mandated sequence.

---

# M17C-C corrected-head exhaustive first-pass review (third pass) — 2026-10-01 — NOT CLEAN (register RR2-M17CC-01 FROZEN)

The fresh independent review of implementation HEAD `82f51a6` (against frozen R0, the predecessor-impact register, RR-M17CC-01..04, and the six certified-closed original findings; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 new Medium finding, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip = the record commit `47e68f0` above the reviewed head). The new register is frozen; the next lawful step is a narrowly scoped correction cycle for RR2-M17CC-01.

## Register closure (as certified by this pass)

- **RR-M17CC-01 / FPR-03: CLOSED** — the literal schema-6 projection (performance removed, intra_shot removed when present, schema_version restored to 6) reaches the unchanged compiler on both observation-capable wrap shapes while the stored ShotRevision remains unchanged.
- **RR-M17CC-02: CLOSED** — readiness/closure separation with the commissioned null posture; the supported DELETE proves blocked data through detail 200/nulls and the typed 409 with zero writes.
- **RR-M17CC-03 / FPR-04: CLOSED** — grammar-v2 snapshot anchoring; the coherent preimage+hash rewrite is refused via the snapshot identity at both surfaces.
- **RR-M17CC-04: CLOSED** — the positive structural fence check with deletion/relocation negatives.
- The six original certified-closed findings did not regress; CI 36877119569 was independently corroborated (3037/20 — green does not cover the new pre-capture shape); the grammar-v1 refusal was expressly authorized and is not reopened; a candidate predecessor-order concern in Shot detail was examined and NOT retained (below the evidence threshold).

## Frozen finding

- **RR2-M17CC-01 — MEDIUM — NEW — coherent capture / paired vocal mapping integrity at the fresh-capture admission seam.** The schema-v2 correction anchors the vocal mapping hash in immutable identity, but the fresh capture read does not first prove the CURRENT paired vocal mapping's own stored canonical bytes/hash are valid: the M17A table mechanically requires only schema 1 + a 64-char mapping_hash (no mapping_json↔fields↔hash law); M17C-B verifies the Performance mapping's full persisted canonical structure (`_verify_stored_mapping`) but `_project_one()` checks the paired vocal row's existence/VP identity/selection/induced interval WITHOUT verifying its mapping_schema_version/mapping_json/mapping_hash; `resolve_performance_plane()` then copies `paired.mapping_hash` and the origin preimage into the capture value, and fresh persistence writes it as-is. Concrete path: corrupt only `shot_vocal_segment_mappings.mapping_hash` to another 64-char value → PF-02 still READY → capture embeds the bad hash into grammar-v2 snapshot identity and persists the revision → the first §12 read recomputes from the captured preimage and rejects it — capture manufactures durable history its own historical/recovery contract regards as corrupt immediately (violating frozen §11.4; the M17A recovery verifier already knows the missing law — it reconstructs the vocal mapping document and requires the canonical hash to equal the stored one). Required correction: validate a PRESENT paired vocal mapping's complete persisted canonical law before extracting closure — a shared transport-neutral ShotVocalSegmentMapping structural verifier analogous to the PF-02 verifier; RR-02 preserved exactly (ABSENT pairing stays lawful BLOCKED; PRESENT-but-noncanonical is corruption and fails closed). Mandatory proofs: pre-capture corruption of mapping_hash ALONE (another 64-char value) and of mapping_json ALONE (semantic columns intact) — both refuse with the corruption posture BEFORE builder/persistence, revision/parent/children counts unchanged; a clean control still captures.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR2-M17CC-01 frozen (0H/1M/0L). RR-M17CC-01..04 all CLOSED; FPR-M17CC-01..08 all remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a narrowly scoped correction cycle for RR2-M17CC-01 followed by another independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR2-M17CC-01 CORRECTION — the fresh-capture admission seam — 2026-10-01 — IMPLEMENTED

The commissioned correction is complete: a PRESENT paired `ShotVocalSegmentMapping` must satisfy its complete persisted canonical structure before any of its bytes can enter grammar-v2 capture identity. Correction heads: **`e8e1b6b`** (implementation) + the validator-carve commit (`28a7dbe` pushed head at the time of the record).

## Delivered (the frozen gate exactly)

1. **ONE shared, transport-neutral structural law** — `performance/mapping.py` gains `vocal_mapping_canonical_document` + `verify_stored_vocal_mapping`: `mapping_schema_version == 1`; the exact canonical document reconstructed from the row's OWN fields; the stored `mapping_json` IS that document; `mapping_hash` IS its canonical digest. Never repairs, normalizes, or substitutes. **The M17A recovery verifier's `_verify_mappings` now consumes the SAME law** (its hand-inlined document reconstruction removed; its own transport and corruption vocabulary preserved — the two definitions cannot drift).
2. **Invoked before capturable closure extraction** — `m17c_shot_mapping._project_one` runs the verifier on the PRESENT paired vocal mapping immediately after the absence check, BEFORE the VP-identity/selection/induced-interval laws — hence before `resolve_performance_plane` can copy `mapping_hash` + the origin preimage into the capture value, and hence before the builder/persistence. ABSENCE stays the lawful `BLOCKED_BINDING_INTEGRITY` data (RR-02 preserved exactly, no readiness-vocabulary redesign); PRESENT-but-noncanonical raises the typed corruption so readiness AND capture fail closed — capture can no longer mint schema-8 history its own §12 contract would reject at first read.
3. **The frozen battery** (`tests/test_m17cc_rr2_corrections.py`, 4 tests): mapping_hash-only corruption (another storage-valid 64-hex; semantic fields + mapping_json untouched) and mapping_json-only corruption (semantic columns + hash untouched) — each proving the identical lawful world captured cleanly FIRST, then the precise corruption reason from both the readiness projection (500) and capture (500 before the builder), with revision/parent/children counts unchanged after each refusal; the clean control captures schema 8 and is immediately valid under §12 AND recovery; the RR-02 supported-delete re-proof (absence still blocked data, Shot detail 200 with nulls).

## Predecessor-impact disclosure

The only predecessor surface touched is the shared document law itself: recovery's `_verify_mappings` message now carries the precise reason suffix (same code path, same vocabulary family — disclosed). Grammar-v2, snapshot anchoring, §12 semantics, recovery semantics, PF-03 authority, Generation behavior, and M17C-D boundaries are untouched.

## Gates (first-run dispositions recorded exactly)

- RR2 battery **4/4** first run (fixture-level corrections only: a paren typo in the count helper; the corruption-reason assertion now names the precise member). The correction-affected batteries **130/130** (all nine m17cc files + m17a recovery + m17c shot-mapping) and the migration/recovery families **55/55**.
- Committed-tree validators: all green after the four-boundary carve for the RR2 battery.
- Frontend: vitest **143/143**, tsc clean, build succeeds.
- Local full backend suite, FIRST RUN: **3034 passed / 8 skipped / 0 failed in 50:22, exit 0** (collection 3042 = the prior 3038 + the 4-test battery — exact).
- **CI run `36910082107` on `28a7dbe`: SUCCESS, attempt 1 — Backend 3041 passed / 20 skipped / 0 failed** (CI total 3061 = its prior 3057 + the 4-test battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

No grammar-v2/snapshot/§12/recovery-semantics changes; PR #26 remains draft, unmerged, unready. After CI corroboration the next gate is another fresh independent exhaustive first-pass review of the corrected HEAD, findings frozen before any Codex/second-review step.

---

# M17C-C fourth first-pass review — 2026-10-01 — NOT CLEAN (register RR3-M17CC-01 FROZEN)

The independent review of implementation HEAD `28a7dbe` (the RR2 correction, its shared M17A recovery seam, the new adversarial battery, the readiness/capture path, predecessor impact, and the surrounding closed findings; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `505a8d5`, one documentation-only commit above the reviewed head). The register is frozen; the next lawful step is a minimal correction of the shared serialized-byte law plus the semantically-identical/noncanonical JSON adversarial proof.

## Register status

- **RR2-M17CC-01: REMAINS OPEN** — the core architecture was assessed CORRECT (the shared verifier placement after the lawful-absence branch and before VP/selection/timing/closure extraction; the genuine shared recovery seam; the battery; CI 36910082107 independently confirmed at 3041/20), but the correction does not implement the complete canonical-BYTE law it claims.
- **All earlier FPR/RR findings remain CLOSED** (no basis found to reopen FPR-01..08, RR-01..04, grammar-v2 anchoring, the non-READY/null-hash posture, the Generation fence, §12 physical-payload closure, or the schema-6 observation projection). An unrelated event-loop warning in the green CI run does not meet the finding threshold.

## Frozen finding

- **RR3-M17CC-01 — MEDIUM — persisted mapping_json canonical-BYTE integrity.** `verify_stored_vocal_mapping` decodes `mapping_json` and compares the decoded OBJECT to the canonical dict — it never checks `mapping_json == canonical_json_str(canonical)`. A row whose bytes are changed to a semantically identical but NONCANONICAL serialization (pretty-printed, reordered, or a duplicate-key form whose decoded last-value object equals the canonical document — a serialization the canonical writer can never emit) passes the verifier with every semantic field and `mapping_hash` untouched: PF-02 stays READY, capture proceeds, and M17A recovery — now sharing the same under-checking helper — also certifies the noncanonical predecessor row. This violates the frozen §11.4 requirement that capture refuse noncanonical stored mapping BYTES/hash. The existing forged-document test changes the decoded semantics, so it cannot catch the value-vs-serialization boundary. Required correction: the shared helper performs the exact serialized-form comparison (`mapping_json == canonical_json_str(canonical)`, retaining `mapping_hash == canonical_hash(canonical)`; parsing unnecessary for certification once byte equality holds, retained only for a differentiated diagnostic). Mandatory proof: a mapping-json-only mutation that is SEMANTICALLY IDENTICAL to the lawful document (pretty-print/reorder) with all semantic columns + the canonical hash untouched → readiness 500, capture fails before builder/persistence, revision/parent/child counts unchanged, M17A recovery independently refuses the same row, and the existing clean control + supported-delete case stay green. The forged-document case is RETAINED as a separate test (a different failure mode).

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR3-M17CC-01 frozen (0H/1M/0L). RR2-M17CC-01 remains OPEN. All earlier FPR/RR findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is the minimal serialized-byte correction + the semantically-identical adversarial proof, then another independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR3-M17CC-01 CORRECTION — the exact canonical serialized form — 2026-10-01 — IMPLEMENTED

The commissioned minimal correction is complete: the shared vocal-mapping verifier now certifies the exact canonical BYTE identity of the stored `mapping_json`. Correction heads: **`3bee776`** (implementation) + the validator-carve commit (pushed head `a029900` at record time).

## Delivered (the frozen boundary exactly)

1. **Exact serialized identity** — `verify_stored_vocal_mapping` now certifies `mapping_json == canonical_json_str(canonical)`; the independent digest law `mapping_hash == canonical_hash(canonical)` is retained. No normalize/reserialize-and-accept/repair/replace. **Parsing is DIAGNOSTIC-ONLY** — when the byte comparison fails, a single decode differentiates a semantic forgery ("not the canonical document") from a semantically identical but NONCANONICAL serialization ("decodes to the canonical document but is not its canonical serialized form" — pretty-print/reorder/duplicate-key forms the canonical writer can never emit); it never substitutes for byte equality.
2. **Still ONE shared law** — both the live PF-02/capture path (`_project_one`, after the lawful-absence branch) and the M17A recovery verifier certify the identical canonical-byte law. Disclosed predecessor impact: the recovery proof surface gains the differentiated reason (its own transport + vocabulary unchanged).
3. **RR-02 preserved exactly** — an ABSENT paired mapping stays lawful `BLOCKED_BINDING_INTEGRITY` data; the correction applies only to a PRESENT stored row. Frozen §11.4 enforcement of an EXISTING rule; grammar-v2/snapshot anchoring/§12/Generation/PF-03/non-READY posture/migration heads/M17C-D boundaries untouched.

## The frozen battery (`tests/test_m17cc_rr3_corrections.py`, 3 tests)

- **The decisive byte-canonicality proof**: start from the lawful `mapping_json`, deserialize it, write a semantically identical but NONCANONICAL serialization (reversed key order + `indent=2`), leaving every semantic column and `mapping_hash` untouched (both re-verified on the tampered row) → readiness 500 with the noncanonical-form reason; capture fails with the SAME corruption before builder/persistence; revision/parent/child counts unchanged; **M17A recovery independently refuses the same stored row** (hand-staged DB copy — the backup API itself runs the same verification chain and refuses during staging, which is the same law).
- **The semantic-forgery case retained** as a distinct failure mode (the RR2 proof, now with its precise differentiated reason).
- **The clean canonical control** (READY, schema-8 capture, §12 valid, M17A + M17C recovery valid) **+ the supported paired-vocal DELETE** (still blocked data, never corruption; Shot detail 200 with nulls).

## Gates (first-run dispositions recorded exactly)

- RR3 battery **3/3** first run after one staging correction (the backup API refuses during staging on the corrupted row — the recovery proof hand-stages the DB copy instead, disclosed in-test). The correction-affected batteries **133/133** (all ten m17cc files + m17a recovery + shot mapping + bf recovery), the RR2 battery unchanged and green under the byte law.
- Committed-tree validators: all green after the four-boundary carve for the RR3 battery.
- Frontend: vitest **143/143**, tsc clean, build succeeds.
- Local full backend suite, FIRST RUN: **3037 passed / 8 skipped / 0 failed in 49:42, exit 0** (collection 3045 = the prior 3042 + the 3-test battery — exact).
- **CI run `36924263930` on `a029900`: SUCCESS, attempt 1 — Backend 3044 passed / 20 skipped / 0 failed** (CI total 3064 = its prior 3061 + the 3-test battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

Minimal delta; PR #26 remains draft, unmerged, unready. After CI corroboration the next gate is another fresh independent exhaustive first-pass review of the corrected HEAD before any second-review phase.

---

# M17C-C fifth first-pass review — 2026-10-02 — NOT CLEAN (register RR4-M17CC-01 FROZEN)

The independent review of implementation HEAD `a029900` (the RR3 correction against actual code, the shared M17A recovery path, its adversarial tests, and the surrounding PF-02 → capture → §12 → §13.4 chain; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 new Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `42871ba`, one documentation-only commit above the reviewed head). The register is frozen; the next lawful step is a narrowly scoped correction cycle for RR4-M17CC-01.

## Register status

- **RR3-M17CC-01: CLOSED** — `verify_stored_vocal_mapping` uses the exact certifying law `mapping_json == canonical_json_str(canonical)` + the independent hash; parsing only differentiates diagnostics after byte inequality; the battery genuinely exercises the value-vs-serialization boundary; CI 36924263930 genuinely green on `a029900`.
- **RR2-M17CC-01:** its mapping-JSON/hash defect closed; **RR4-M17CC-01 is the newly identified broader predecessor-integrity seam**.
- **All earlier FPR/RR findings remain CLOSED** (no basis to reopen FPR-01..08, RR-01..04, or the grammar-v2 snapshot anchor; the correction delta is narrow — the only product file changed vs `28a7dbe` is `performance/mapping.py`).

## Frozen finding

- **RR4-M17CC-01 — MEDIUM — NEW — paired vocal-mapping predecessor-integrity closure before fresh capture.** The shared helper certifies the mapping document's SELF-consistency, but not all persisted M17A laws that make the paired row valid authority. Two independently provable gaps:
  1. **Sample-rate authority is not checked.** The M17A write path requires `sample_rate_hz == VP native rate` (and recovery enforces it independently), but the shared helper only reconstructs the document from the row's own fields — so corrupting the rate to another positive value + recomputing the exact canonical JSON/hash passes. PF-02's induced-interval uses `binding.sample_rate_hz`, never comparing the paired row's rate; `_project_one` checks VP identity/selection/induced timing but not the rate → READY → `resolve_performance_plane` copies the corrupted rate into the captured vocal closure → persistence writes it mechanically → the first §12 read compares against the immutable binding and refuses: capture mints a schema-8 revision its own first historical inspection rejects (exactly the RR2-class outcome).
  2. **Canonical rational representation is missing from the shared helper.** The table requires positive denominators but not reduced fractions; M17A recovery explicitly enforces gcd-canonical form after the shared helper — so the supposedly shared "complete persisted canonical law" is incomplete. A coherent vocal anchor rewrite `1/1 → 2/2` with exact recomputed canonical JSON/hash passes the helper; PF-02 compares anchors as `Fraction` values (equal); but the captured vocal hash was computed over `2/2` while the historical preimage reconstruction uses the Performance mapping's canonical `1/1` → §12/recovery reject the freshly captured mapping-hash closure.
- **Required correction:** do NOT weaken the RR3 byte law. Make fresh capture consume the FULL predecessor vocal-mapping integrity contract before closure extraction: enforce canonical `performance_origin`/`shot_anchor` rationals on a present row; require paired-vocal `sample_rate_hz` agreement with the immutable binding/VP rate; preserve VP identity/selection/induced-timing; share or prove-implied any other M17A interval/trim laws; keep ABSENCE lawful `BLOCKED_BINDING_INTEGRITY` exactly. Preferred shape: factor the row-local M17A structural law so live capture and recovery share the SAME rules, with cross-row binding/VP authority checks in the caller. Frozen battery: (1) rate-only corruption + exact JSON/hash recompute → readiness/capture 500 before persistence; (2) canonical-rational corruption (anchor ×k/k + exact recompute) → same refusal; (3) counts unchanged for both; (4) M17A recovery refuses both staged states on the same law; (5) clean control + the RR3 forgery/noncanonical cases + supported DELETE remain green.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR4-M17CC-01 frozen (0H/1M/0L). RR3-M17CC-01 CLOSED. All earlier FPR/RR findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a narrowly scoped correction cycle for RR4-M17CC-01, then another independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR4-M17CC-01 CORRECTION — the complete predecessor vocal-mapping integrity contract — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete: fresh capture now consumes the FULL predecessor vocal-mapping integrity contract before closure extraction. Correction heads: **`c9ceb74`** (implementation) + the validator-carve commit (pushed head `c44591f` at record time).

## Delivered (the six boundary points exactly)

1. **RR3 untouched** — the exact certifying byte law (`mapping_json == canonical_json_str(canonical)`) and the independent digest law are unchanged and remain the certification.
2. **The shared row-local verifier is now COMPLETE for persisted structural law** — `verify_stored_vocal_mapping` additionally enforces canonical rational representation on BOTH persisted pairs (positive denominator, gcd-reduced, zero only as 0/1) — the exact rule M17A recovery enforced separately; **recovery's duplicated rational loop is REMOVED** (one law in one place; live capture and recovery enforce the identical rules).
3. **Cross-row authority at the live caller seam** — `_project_one` (after the shared verifier + the VP-identity check, before selection/induced timing) now requires a PRESENT paired mapping to prove: `sample_rate_hz` AGREES with the immutable synchronization binding (binding rate == VP native rate is a binding-table law verified at both grades — agreement is transitive to the VP), and its source interval lies INSIDE the binding's authoritative source interval (the §8.3 creation law now proven at admission; binding interval within VP trim is a binding law, so trim containment is transitive). Typed corruption; VP identity, selection, and induced-timing checks preserved.
4. **The explicit M17A-law audit** — VP existence: IMPLIED (the seam-verified binding pins the VP + the identity check). VP-trim containment: IMPLIED transitively through the now-explicit binding-interval check. Shot/VP project coherence: IMPLIED (the PR subject/project seam checks + `BLOCKED_SUBJECT_OR_PROJECT` + the §12/§13.4 VP-lineage project law). Shot duration/picture: the SR2-06 recovery correction's own classification (mutable readiness, never restore corruption). **No recovery-only validity rule remains outside fresh-capture admission.**
5. **RR-02 exact** — absence stays lawful `BLOCKED_BINDING_INTEGRITY` data; every new law applies only to a PRESENT row.
6. **No collateral redesign** — grammar-v2, snapshot anchoring, §12, Generation, PF-03, migration heads, the non-READY posture, and M17C-D boundaries untouched. Predecessor impact disclosed: the shared law itself (recovery's duplicated loop removed) and the live seam's new present-row checks.

## The frozen battery (`tests/test_m17cc_rr4_corrections.py`, 4 tests)

- **Rate-only coherent corruption**: `sample_rate_hz` → another positive value, exact canonical JSON/hash recomputed from the row's own post-tamper fields (the RR3 byte law passes BY CONSTRUCTION — proven on the tampered row) → readiness 500 + capture failing with the same corruption before the builder + counts unchanged + M17A recovery independently refusing the hand-staged state ("mapping rate != VP native rate").
- **Canonical-rational coherent corruption**: the anchor rewritten ×2/×2 (not gcd-reduced), exact recompute (the byte law passes; the shared rational law refuses) → the same refusal chain, recovery refusing through the shared law's reason.
- **Clean control** (READY, schema-8 capture, §12 + M17A + M17C recovery valid) **+ the RR3 semantic-forgery and noncanonical-byte proofs still green under the completed law**.
- **Supported DELETE**: still blocked data, never corruption.

## Gates (first-run dispositions recorded exactly)

- RR4 battery **4/4** first run. Correction-affected batteries **137/137** (all eleven m17cc files + m17a recovery + shot mapping + bf recovery); migration/recovery families **47/47**.
- Committed-tree validators: all green after the four-boundary carve for the RR4 battery.
- Frontend: vitest **143/143**, tsc clean, build succeeds.
- Local full backend suite, FIRST RUN: **3041 passed / 8 skipped / 0 failed in 48:24, exit 0** (collection 3049 = the prior 3045 + the 4-test battery — exact).
- **CI run `36943996459` on `c44591f`: SUCCESS, attempt 1 — Backend 3048 passed / 20 skipped / 0 failed** (CI total 3068 = its prior 3064 + the 4-test battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. Once CI corroborates, the next gate is another fresh independent exhaustive first-pass review of the corrected HEAD — not an assumption that RR4 is closed.

---

# M17C-C sixth first-pass review — 2026-10-02 — NOT CLEAN (register RR5-M17CC-01..02 FROZEN)

The independent review of implementation HEAD `c44591f` (the RR4 product delta, the shared M17A recovery seam, the public vocal-mapping mutation surface, fresh-capture/readiness behavior, and the surrounding closed seams; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 2 new Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `ad42746`, one documentation-only commit above the reviewed head). The register is frozen; the next lawful step is a correction cycle against RR5-M17CC-01..02.

## Register status

- **RR4-M17CC-01: CLOSED for both its frozen shapes** (the coherent rate corruption and the noncanonical reduced-rational corruption); RR3 and all earlier FPR/RR findings remain CLOSED (no basis to reopen grammar-v2, §12, Generation's refusal, the schema-6 projection, or the earlier closures). CI 36943996459 independently corroborated (3048/20 — the green run simply does not contain either new adversarial shape).
- What held up: the shared rational rejection, the binding-rate transitivity (the read-grade binding verifier proves binding rate == VP native and binding interval ⊆ VP trim), the RR3 byte law, and the absence branch ordering (the supported DELETE stays blocked data).

## Frozen findings

1. **RR5-M17CC-01 — MEDIUM — supported vocal re-segmentation misclassified as corruption.** The RR4 binding-interval gate is too strong for a MUTABLE current `ShotVocalSegmentMapping`: `put_shot_vocal_segment_mapping` deliberately owns mutable Shot-local vocal timing (VP-trim containment, native rate, selected VP, picture intersection — but NOT containment within any already-existing PerformanceRevision binding). The standard fixture makes it concrete: the VP trim is the whole 144000 samples while the Performance binding is `[48000, 96000)`, so a lawful same-VP re-PUT to `[0, 48000)` is valid M17A working state — yet `_project_one` now raises corruption at the binding-interval gate instead of letting the existing induced-timing comparison classify the drift as `BLOCKED_TIMING_MISMATCH` (the pre-RR4 posture, proven by `test_vocal_mapping_edited_after_blocks_timing`). A lawful mutable edit can therefore become a Shot-detail 500 instead of the commissioned non-READY/null-hash posture. **Required:** check the actual immutable corruption law — the current vocal interval inside the seam-verified VP trim — not the old binding; inside-trim-but-outside-binding drift flows to the existing `BLOCKED_TIMING_MISMATCH`. Decisive missing test: a public same-VP vocal PUT after the Performance mapping exists, moving the interval outside the binding but inside the VP trim — PUT succeeds, readiness returns blocked data (not 500), Shot detail 200 with null hash/differs, capture the typed 409 with no new revision/companions; plus a direct-tamper case OUTSIDE the VP trim still failing 500 with recovery refusing it.
2. **RR5-M17CC-02 — MEDIUM — the shared "complete structural law" is not total over SQLite storage classes.** `verify_stored_vocal_mapping` assumes the persisted numerics are Python integers without proving it: the rational branch runs `gcd` on possibly-REAL values; the sample coordinates and rate are never type-checked (SQLite INTEGER affinity + numeric CHECKs permit non-integral REALs). A coherent corruption (`source_start_sample = 48000.5`, inside the binding/VP interval, exact canonical JSON/hash recomputed) passes the helper and the interval comparisons, then can escape `_induced_interval`'s exact Fraction arithmetic as a raw `TypeError` — and **M17A recovery can certify the row** (its post-helper checks never establish integer storage). The rational branch's non-total behavior: a REAL numerator reaches `math.gcd` before any controlled ValueError (both wrappers normalize only ValueError). **Required:** use the project's complete scalar primitive (actual integer pair, positive denominator, canonical reduction/zero, signed-64-bit bounds — `temporal.validate_mapping_position`-family) instead of the hand-reproduced gcd subset; certify the integer domains of the sample coordinates and rate; recovery verifies the mapping position's persisted integer domain through the same shared primitive. Mandatory proof: storage-valid REAL values staged directly (`source_start_sample=48000.5` with canonical recompute) → live readiness/capture AND M17A recovery issue their TYPED corruption responses (never a raw Python exception, never successful recovery); a non-integer rational scalar covered separately.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR5-M17CC-01..02 frozen (0H/2M/0L). RR4-M17CC-01 CLOSED for its frozen shapes; RR3 and all earlier FPR/RR findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a correction cycle against RR5-01..02, then another fresh independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR5-M17CC-01..02 CORRECTION — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete: the mutable-vs-immutable distinction is restored and the shared predecessor verifier is total over persisted storage classes. Correction heads: **`6f4e98e`** (implementation) + the validator-carve commit (pushed head `cb8b449` at record time).

## Delivered (the frozen boundary exactly)

1. **RR5-01** — `_project_one`'s interval gate now proves the immutable corruption law: the seam-verified **VP authoritative trim** (the VP row fetched via the binding's pinned id; a gone VP is corruption), NOT the mutable Performance binding window. The RR4 rate-agreement law is retained. A lawful same-VP public re-segmentation inside the trim but outside the old binding is mutable working drift that flows to the existing exact induced-timing comparison → `BLOCKED_TIMING_MISMATCH`; only an interval actually outside the VP trim is corruption (typed 500; recovery's own outside-trim law corroborates).
2. **RR5-02** — `verify_stored_vocal_mapping` certifies every persisted scalar BEFORE any arithmetic, hashing assumption, or Fraction use: `position` via the ONE shared `validate_mapping_position` (actual non-bool int in `[0, 2^63-1]`); the sample coordinates and rate actual non-bool integers in their persisted domains (start ≥ 0, rate > 0, start < end); both rational pairs actual non-bool integer pairs verified against the ONE shared `canonical_rational` (integer pair, positive denominator, gcd reduction, canonical zero, i64 bounds — the persisted row must already BE the canonical form; the hand-reproduced gcd subset removed). A storage-valid non-integral REAL refuses as the TYPED structural law — never a raw TypeError/OverflowError through `math.gcd` or `Fraction`, never successful certification. Recovery passes `position` into the shared helper (the mapping-position domain is the same law on both transports).
3. **Invariants preserved exactly:** the RR3 byte identity, the RR4 rate law, lawful absence → `BLOCKED_BINDING_INTEGRITY`, grammar-v2/snapshot anchoring, §12 semantics, Generation's fence, the schema-6 projection, the commissioned non-READY null posture, migration heads, and M17C-D boundaries. Predecessor surfaces touched (disclosed): the shared mapping law itself + the live seam's interval gate (binding-window → VP-trim).

## First-run dispositions recorded exactly

- **A shadowing bug in my own first draft was caught by the m17a recovery battery BEFORE commit**: the new rational loop's local `canonical = canonical_rational(...)` shadowed the canonical DOCUMENT dict, making every lawful row fail the byte law — renamed to `reduced` after diagnosing via a scratch reproduction (the rebuilt bytes equalled the stored bytes; the failure had to be in-processor).
- Battery: first run 4/5 — the `real_rational_den` case initially staged `2.0`, which SQLite's INTEGER affinity stores as an INTEGER, so the row landed in the canonical-reduction law instead of the storage-class law (still a typed refusal, but not the targeted one); the case now stages the non-integral `2.5` (genuinely REAL storage). Corrected run **5/5**.
- Affected batteries **142/142** (all twelve m17cc files + m17a recovery + shot mapping + bf recovery); migration/recovery families **45/45**.
- Committed-tree validators green after the four-boundary carve; frontend green (143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3046 passed / 8 skipped / 0 failed in 51:37, exit 0** (collection 3054 = the prior 3049 + the 5-test battery — exact).
- **CI run `36977392187` on `cb8b449`: SUCCESS, attempt 1 — Backend 3053 passed / 20 skipped / 0 failed** (CI total 3073 = its prior 3068 + the 5-test battery, exact); Frontend green attempt 1 (143/143).

## The frozen battery (`tests/test_m17cc_rr5_corrections.py`, 5 tests)

The decisive public-PUT re-segmentation (the same VP moved from the binding `[48000,96000)` to `[0,48000)` inside the 144000-sample trim — PUT succeeds, readiness reports `BLOCKED_TIMING_MISMATCH` data never 500, Shot detail 200 with the commissioned nulls, capture the typed 409, counts unchanged); the outside-trim COHERENT tamper (`[144000,150000)` + exact recompute — 500 both surfaces, counts unchanged, M17A recovery refuses "outside VP authoritative trim"); the REAL storage-class pair (`48000.5` coordinate + `2.5` denominator, each with the byte law passing by construction — typed corruption from readiness AND capture AND recovery, counts unchanged); the clean control + the RR3 noncanonical-byte and RR4 canonical-rational proofs still green + the supported DELETE.

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. After CI corroborates, the next gate is another fresh independent exhaustive first-pass review of the corrected HEAD — neither RR5 finding is considered closed merely because the correction tests pass.

---

# M17C-C seventh first-pass review — 2026-10-02 — NOT CLEAN (register RR6-M17CC-01..02 FROZEN)

The independent review of implementation HEAD `cb8b449` (the RR5 product delta, the shared scalar verifier, both live/recovery call sites, supported M17A mutation paths, PF-02 readiness/capture, §12, §13.4, and the correction battery; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 Medium semantic + 1 Low proof-only.** PR #26 remains draft, open, unmerged (tip `ece1dc5`, one documentation-only commit above the reviewed head). The register is frozen; the next lawful step is a correction cycle for the binding-subinterval contract plus the missing position proof.

## Register status

- **RR5-M17CC-01: CLOSED for its frozen defect** (public same-VP re-segmentation outside the binding but inside the VP trim → `BLOCKED_TIMING_MISMATCH`; detail nulls; typed 409).
- **RR5-M17CC-02: product implementation CLOSED** (position through `validate_mapping_position`; coordinates/rate before arithmetic; rational pairs through `canonical_rational`; recovery supplies the persisted position; the shadowing correction present; REAL rejection before Fraction/gcd; RR3 bytes + RR4 rate intact; absence still lawful blocked) — **mandatory persisted-position evidence incomplete** (the Low proof finding below).
- **RR3, RR4, and all earlier FPR/RR findings remain CLOSED.** CI 36977392187 independently corroborated (3053/20 — the green run contains neither new shape).

## Frozen findings

1. **RR6-M17CC-01 — MEDIUM — binding-subinterval semantics disagree across live admission and §12.** One semantic law expressed incorrectly at two seams:
   - **A supported API path can mint §12-rejected history**: the same VP's current mapping lawfully moved to a SUB-interval inside the binding (e.g. `[60000,84000)`) is legitimately READY (the Performance PUT lawfully accepts the exact induced `[250,750)`; capture persists it) — but the §12 reader requires the captured vocal interval to EQUAL the entire binding (`binding.start == captured.start && binding.end == captured.end`) instead of the frozen §8.3 CONTAINMENT, so the first historical inspection rejects a lawful capture. Recovery implements the correct law (containment + exact induced arithmetic); §12 and §13.4 disagree about a lawful captured state.
   - **A complementary live-admission hole**: with only VP-trim containment before the induced comparison, a coherent DUAL rewrite (vocal `[36000,84000)` + exact vocal JSON/hash; Performance `[-250,750)` + exact recompute — both inside their trims/domains, induced arithmetic exact) reaches READY although the vocal interval is outside the immutable binding and NO supported Performance PUT could create the pair — capture mints history §12/§13.4 reject.
   - **The lawful contract (both seams)**: `binding.start <= captured-vocal.start < captured-vocal.end <= binding.end` PLUS exact binding-induced Performance timing. Live: RR5-01 preserved (inside-VP-trim outside-binding = mutable working drift → `BLOCKED_TIMING_MISMATCH`, never 500) but never READY on a coherent dual rewrite. §12: whole-binding equality replaced by binding CONTAINMENT + the exact induced interval from the immutable binding origin/rate/samples (matching §13.4). Decisive battery: a public inside-binding SUBSEGMENT that captures and reads §12-green; an outside-binding coherent dual rewrite that stays non-READY and cannot capture.
2. **RR6-M17CC-02 — LOW — proof-only: the persisted-position storage-class evidence is missing.** The RR5-02 product implementation survives review; the commissioned proof set included persisted POSITION coverage, which the battery never staged (REAL coordinate + REAL denominator only; IR-04 covers API bounds, not the malformed persisted storage class through the newly shared verifier). A narrow recovery test suffices: stage `shot_vocal_segment_mappings.position = 0.5` in a copied DB → the M17A verifier returns typed `RECOVERY_CORRUPTION` through the shared position law (never a raw exception, never green).

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR6-M17CC-01..02 frozen (0H/1M/1L). RR5-01 CLOSED; RR5-02 product CLOSED with the position proof owed; all earlier findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is the binding-subinterval correction cycle + the missing position proof, then another fresh independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR6-M17CC-01..02 CORRECTION — the binding-subinterval contract — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete: one law at both seams. Correction heads: **`a402226`** (implementation) + the validator-carve commit (pushed head `132d2b3` at record time).

## Delivered (the frozen boundary exactly)

1. **RR6-01 live** — binding containment is now a READINESS gate in `_project_one`: after the present-row structural/rate/VP-trim checks and BEFORE the induced-timing equality, `binding.start <= vocal.start < vocal.end <= binding.end` is required; failure returns `BLOCKED_TIMING_MISMATCH` (data — RR5-01 preserved: outside-VP-trim stays typed 500 corruption). Because the gate runs before the equality a coherent dual rewrite would game, no coherently rewritten Performance row can reach READY or capture.
2. **RR6-01 §12** — whole-binding equality is replaced by the frozen §8.3 CONTAINMENT plus the exact binding-induced Performance interval recomputed from the immutable binding origin, binding source start, captured sample interval, and rate (Fraction arithmetic; matching §13.4's already-correct law). The immutable binding_hash/VP-identity/rate agreement is retained. A lawful inside-binding SUBSEGMENT capture now passes its first historical inspection.
3. **RR6-02 (proof-only)** — the persisted-position adversary: a staged `position = 0.5` row terminates as typed `RECOVERY_CORRUPTION` through the shared `validate_mapping_position` law ("persisted integer domain") — never a raw exception, never green. NO product change (the finding was explicitly proof-only and the law already correct).
4. **Predecessor impact disclosed**: the PF-02 readiness seam gains ONE classification gate restoring the already-established mutable-drift semantics (vocabulary untouched); §13.4 recovery semantics NOT modified (§12 was aligned TO it); M17A recovery untouched beyond the shared law's existing wiring; grammar-v2/snapshot anchoring/non-READY posture/Generation/PF-03/migration heads/M17C-D untouched.

## The frozen battery (`tests/test_m17cc_rr6_corrections.py`, 4 tests)

- **The positive public path**: binding `[48000,96000)`; the same VP publicly moved to the inside-binding subsegment `[60000,84000)` (vocal PUT 200, anchor 250); the Performance mapping publicly moved to the exact induced `[250,750)` (PUT 200) → READY, schema-8 capture, the FIRST §12 inspection GREEN (the captured sample interval and induced interval asserted in the answer), M17A + M17C recovery green.
- **The negative coherent dual rewrite**: vocal `[36000,84000)` + exact vocal JSON/hash AND Performance `[-250,750)` + exact Performance JSON/hash (both recomputed from the rows' own fields; inside the VP trim, outside the binding) → readiness `BLOCKED_TIMING_MISMATCH` data (never 500, never READY), Shot detail 200 with the commissioned nulls, capture the typed 409, counts unchanged; recovery deliberately NOT asserted against the live drift (the predecessor contract separates immutable structural validity from mutable readiness).
- **The persisted-position proof** and the clean control.

## Gates (first-run dispositions recorded exactly)

- Battery first run 3/4 → 4/4 after fixture-level fixes (a missing-argument typo in the test's recompute call; a stale fragment in the history matrix — the `binding_disagreement` tamper now surfaces the containment message, the same tamper under the new law's wording; the `Fraction` import + the dict-vs-Fraction `_rat` mismatch caught by the batteries).
- Affected batteries **166/166** (all thirteen m17cc files + m17a recovery + shot mapping + bf recovery + sr2); migration/recovery families **25/25**.
- Committed-tree validators green after the four-boundary carve; frontend green (143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3050 passed / 8 skipped / 0 failed in 48:54, exit 0** (collection 3058 = the prior 3054 + the 4-test battery — exact).
- **CI run `36992205203` on `132d2b3`: SUCCESS, attempt 1 — Backend 3057 passed / 20 skipped / 0 failed** (CI total 3077 = its prior 3073 + the 4-test battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. The next gate is a fresh independent exhaustive first-pass review of the corrected HEAD; neither RR6 finding is considered closed merely because the correction tests pass.

---

# M17C-C eighth first-pass review — 2026-10-02 — NOT CLEAN (register RR7-M17CC-01 FROZEN)

The independent review of implementation HEAD `132d2b3` (the RR6 delta against the actual code, both decisive RR6 tests, the persisted-position proof, PF-02 readiness/capture, §12, the existing §13.4 law, and the immutable PF-03 binding contract; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 new Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `715feb9`, one documentation-only commit above the reviewed head). The register is frozen; the next lawful step is a narrowly scoped §12 immutable-binding-authentication correction.

## Register status

- **RR6-M17CC-01: CLOSED** (the live containment gate before the induced equality returning `BLOCKED_TIMING_MISMATCH` — the dual rewrite cannot game READY; the supported inside-binding subsegment stays READY and captures; the §12 containment + induced arithmetic aligned with recovery).
- **RR6-M17CC-02: CLOSED** (the staged `position = 0.5` proof genuinely exercises the persisted storage-class path and terminates typed; no product change, consistent with proof-only).
- **All earlier FPR/RR findings remain CLOSED** (no basis to reopen the live readiness classification, the RR5 VP-trim/corruption distinction, the RR4 rate law, the RR3 canonical mapping bytes, grammar-v2 anchoring, the non-READY/null-hash posture, the Generation fence, or the schema-6 projection; the containment-before-selection ordering fact below the finding threshold — no frozen precedence contract requires stale-selection diagnostics to dominate timing drift). CI 36992205203 independently corroborated (3057/20).

## Frozen finding

- **RR7-M17CC-01 — MEDIUM — §12 does not authenticate the immutable PF-03 binding document before using it.** The RR6 §12 law validates the captured hash token, VP identity, rate, containment, and the induced arithmetic — but never proves the binding ROW's own stored scalars and `binding_json` reproduce `binding_hash`. The authoritative PF-03 service has the law (`_verify_binding_bytes`: the exact canonical binding document over schema version, sync-basis version, VP id, source start/end, rate, canonical origin; exact `binding_json`; recomputed hash == stored `binding_hash`), and M17C recovery enforces the same before §13.4 — §12 does neither, selecting only scalars + the hash token and then using the unauthenticated scalars in the containment/arithmetic. **Concrete surviving corruption:** after capture, extend only `binding.source_end_sample_exclusive` to a larger DB-valid value leaving `binding_json`/`binding_hash` untouched (`[48000,96000)` → `[48000,120000)`; the captured `[48000,96000)` remains contained; the induced arithmetic uses source START so it is unaffected) → §12 returns 200 exposing the corrupted binding as historical authority while the recovery chain refuses the same state. A simpler manifestation: mutate only `binding_json` (all scalars + hash intact) — §12 never reads it, so the malformed immutable companion is invisible. The RR6 containment correction itself is correct; removing whole-binding equality revealed the missing underlying PF-03 self-authentication. **Required:** do NOT restore whole-binding equality — before §12 uses or returns a binding, certify its own immutable canonical structure (schema version; sync-basis version; canonical rational origin; exact canonical binding document; exact `binding_json`; recomputed hash == stored `binding_hash`), then retain `stored binding_hash == captured vocal_binding_hash`. Cleanest shape: reuse/factor the existing transport-neutral PF-03 structural law rather than a third binding grammar. The immutable revision binding IS §12's allowed authority graph — no forbidden surface. **Decisive proofs:** (1) the scalar-with-stale-hash tamper (extend source end; captured subsegment still contained; bytes/hash untouched) → §12 500 on binding canonical integrity + recovery refuses; (2) the `binding_json`-only tamper → same structural refusal; (3) the RR6 supported-subsegment case rerun green (containment not collapsed back into equality).

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR7-M17CC-01 frozen (0H/1M/0L). RR6-01 and RR6-02 CLOSED; all earlier findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is the narrowly scoped §12 immutable-binding-authentication correction, then another fresh independent first-pass review of the corrected HEAD. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR7-M17CC-01 CORRECTION — §12 authenticates the immutable PF-03 binding document — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete: §12 self-authenticates the immutable binding before using it. Correction heads: **`e5ab1b6`** (implementation) + the validator-carve commit (pushed head `e9fc4d5` at record time).

## Delivered (the frozen boundary exactly)

1. **ONE shared transport-neutral structural law** — `m17c_binding` gains `verify_stored_vocal_binding`: binding and sync-basis versions frozen at 1; the persisted origin an actual integer pair in ALREADY-canonical reduced form (the shared `canonical_rational` primitive); the exact canonical binding document reconstructed from the row's own fields; exact `binding_json == canonical_json_str(document)`; recomputed canonical hash == stored `binding_hash`. Never normalizes, repairs, substitutes, or reconstructs. **PF-03's `_verify_binding_bytes` becomes a thin adapter** over the shared law, its corrupt vocabulary preserved verbatim (the three legacy messages reproduced from the shared law's precise reasons) — the disclosed predecessor impact.
2. **§12 (`_verify_one_child`)** — the binding row self-authenticates through the shared law BEFORE any scalar is used or exposed (the query now also selects `binding_json` and the version columns; §12 keeps its own `internal_invariant` vocabulary). Only then: the captured-hash comparison, VP identity, rate agreement, the RR6 containment, and the exact induced-arithmetic laws — containment NOT collapsed back into equality.
3. No PF-02/§13.4/grammar-v2/snapshot/Generation/PF-03-authority/migration-head/non-READY/M17C-D changes.

## The frozen battery (`tests/test_m17cc_rr7_corrections.py`, 4 tests)

- **The scalar/stale-hash tamper**: extend only `binding.source_end_sample_exclusive` (`[48000,96000)` → `[48000,120000)`; the captured `[48000,96000)` stays contained; `binding_json`/`binding_hash` untouched so the hash TOKEN still matches) → §12 typed 500 through the shared law AND the M17C recovery chain (`_verify_revision_bindings` — where the binding-document law lives) independently refusing the same staged state.
- **The `binding_json`-only tamper** (all scalars + hash intact; a semantically identical noncanonical serialization): the same structural refusal on both surfaces.
- **The RR6 positive regression**: the public inside-binding subsegment path READY → schema-8 capture → the FIRST §12 read green (the sample interval and induced interval asserted) → recovery green — self-authentication did not collapse containment.
- **The forbidden-current-table spy** green during the §12 read (authenticating the immutable revision binding is §12's allowed authority; zero current-surface statements).

## Gates (first-run dispositions recorded exactly)

- Battery first run 2/4 → 4/4 after fixture-level corrections, disclosed: an IndentationError from a wrapped assert; the per-mode reason expectation refined (BOTH tamper modes surface `binding_json is not the canonical document` — the shared law checks document bytes before the digest, and under a scalar tamper the recomputed document over the tampered fields no longer matches the untouched stored bytes — the precise reason is correct, my initial per-mode split was not); and the recovery leg retargeted from the M17A verifier to the M17C recovery chain, where the binding-document law actually lives (the M17A verifier does not certify PF-03 bindings). The old history-matrix `binding_disagreement` fragment updated to the new structural-law message (the same tamper, the new law's wording — firing EARLIER than the RR6 containment check, which is the point).
- Affected batteries **182/182** (all fourteen m17cc files + m17a/m17b recovery + shot mapping + bf recovery + sr2); committed-tree validators green after the four-boundary carve; frontend green (143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3054 passed / 8 skipped / 0 failed in 47:36, exit 0** (collection 3062 = the prior 3058 + the 4-test battery — exact).
- **CI run `37013556461` on `e9fc4d5`: SUCCESS, attempt 1 — Backend 3061 passed / 20 skipped / 0 failed** (CI total 3081 = its prior 3077 + the 4-test battery, exact); Frontend green attempt 1 (143/143).

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. The next gate is another fresh independent exhaustive first-pass review of the corrected HEAD; RR7 is not considered closed merely because the correction battery passes.

---

# M17C-C ninth first-pass review — 2026-10-02 — NOT CLEAN (register RR8-M17CC-01..02 FROZEN)

The independent fresh review of implementation HEAD `e9fc4d5` (no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — the core RR7-M17CC-01 historical-authentication defect is CORRECTED, but the RR7 correction round is not clean: 1 Medium + 1 Low.** PR #26 remains draft, open, unmerged (tip `f52ed0d`, record-only above the reviewed head). The register is frozen.

## Register status

- **RR7-M17CC-01: functionally corrected** — §12 authenticates the immutable PF-03 binding document before using or exposing any scalar; both decisive tamper shapes are real rather than tautological (the stale-hash scalar tamper fails the new self-authentication despite contained capture; the noncanonical-serialization case proves exact byte identity; the staged M17C recovery verifier independently rejects); the RR6 positive path remains semantically correct (`[60000,84000)` inside `[48000,96000)` → READY → schema-8 → §12 reconstructs `[250,750)`); the forbidden-current-surface proof stays correctly scoped; the carve is exactly four validator admissions; CI 37013556461 independently checked (synthetic merge `53eb2d0` of `e9fc4d5` into unchanged `d893d65`; Backend 3061/20/0, Frontend 143/143 + typecheck + build); no basis to reopen any earlier finding; recovery's pre-existing `_verify_binding_row` NOT counted as a new defect (RR7 left §13.4 untouched; §12 created no third grammar).
- **But the round is not closed** because the declared PF-03 predecessor-preservation contract is false as implemented, and one explicitly retained post-authentication law lacks a decisive §12 proof.

## Frozen findings

1. **RR8-M17CC-01 — MEDIUM — the "verbatim preserved" PF-03 corruption vocabulary is not actually preserved by the adapter.** At `132d2b3`, a noncanonical `2/2` origin produced exactly `M17C vocal binding stores a noncanonical rational`; at `e9fc4d5` the shared law raises `the persisted origin is not in canonical reduced form`, and because that string contains no `"rational"`... wait — it does contain no substring `rational`? It contains "canonical reduced form" — the substring `"rational"` is NOT in "the persisted origin is not in canonical reduced form" (correct: r-a-t-i-o-n-a-l does not appear), so `_verify_binding_bytes`'s substring router falls through to `M17C vocal binding canonical bytes/hash diverge (...)`. The malformed-rational branch also gains an extra prefix; JSON/hash divergence gains a parenthesized reason instead of the exact legacy message. Fail-closed/500/error-code intact — not an authority-integrity failure, but a direct contradiction of the correction's explicit predecessor-impact claim, and the substring adapter is brittle. **Required:** the shared verifier returns/raises a TYPED structural reason; PF-03 maps those reasons to the exact predecessor messages while §12 keeps its richer diagnostic; pin the legacy branches with regressions.
2. **RR8-M17CC-02 — LOW, proof-only — the RR7 positive battery contains a vacuous assertion and does not pin the retained captured-hash comparison.** `assert H == world["pr"]["id"] and False or H is not None` reduces by precedence to `assert H is not None` (the equality side can never make it succeed). More importantly, both RR7 corruption cases fail during the now-earlier self-authentication, so neither reaches the subsequent `binding.binding_hash == captured vocal_binding_hash` law; the older `binding_disagreement` case also dies earlier on document authentication. The comparison still exists in the implementation — not a product defect today. **Required proof:** after capture, coherently rewrite an immutable binding field (e.g. `source_end_sample_exclusive`) AND recompute its canonical `binding_json`/`binding_hash` (self-authentication passes), leaving the captured child/snapshot untouched → §12 reaches the CAPTURED-HASH DISAGREEMENT refusal after authentication; plus fix the malformed positive assertion to a real expected-hash equality.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. Known findings RR8-M17CC-01..02 (1M/1L). The core RR7 defect is corrected; the round is NOT clean. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a correction cycle for RR8-01..02, then another fresh independent first-pass review. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR8-M17CC-01..02 CORRECTION — the typed structural result + the retained captured-hash proof — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete. Correction heads: **`5e36ed9`** (implementation) + the validator-carve commit (pushed head `39675bb` at record time).

## Delivered (the commission exactly)

1. **RR8-01 — the typed structural result** — the shared law now raises `BindingStructuralError`, a `ValueError` subclass carrying a **stable category token** (`schema_basis` / `rational_malformed` / `rational_noncanonical` / `binding_json` / `binding_hash`) — the routing contract callers map on, never human-readable text — plus `reason` (§12's richer diagnostic) and, for the malformed-rational category, a `source` field with the temporal-primitive error text. PF-03's `_verify_binding_bytes` maps the categories to the **exact predecessor messages verified verbatim against `132d2b3`**: `M17C vocal binding schema/basis version is not 1`; `M17C vocal binding stores an invalid persisted rational: INVALID_RATIONAL: <reason>`; `M17C vocal binding stores a noncanonical rational`; `M17C vocal binding canonical bytes/hash diverge` (the predecessor merged json+hash divergence into one message — both categories map to that exact form). No prefix, suffix, or parenthetical; the substring router is deleted. §12's `except ValueError` accepts the typed subclass and embeds its reason unchanged. The structural law stays singular — same checks, no duplicate grammar, no weakening.
2. **RR8-02 — the retained captured-hash law proven after self-authentication** — the decisive layer-separation proof: after a lawful capture, the binding scalar is coherently mutated AND its canonical `binding_json`/`binding_hash` **recomputed** (self-authentication passes; the captured child/snapshot `vocal_binding_hash` untouched) → §12 reaches and fails specifically at the **captured-binding-hash disagreement** (asserted to be that message and NOT the self-authentication message). The RR7 positive battery's precedence-tautology hash assertion is **replaced with a real identity**: the exposed `synchronization_binding.binding_hash` == the canonical hash of the lawful immutable binding document == the captured child's `vocal_binding_hash`.
3. Every closed seam preserved: the RR7 adversaries still die at self-authentication, the RR6 subsegment path stays green end-to-end, and no RR6-containment/§13.4/PF-02-readiness/grammar-v2/snapshot/Generation/migration-head/non-READY/M17C-D/forbidden-surface change was made.

## The frozen battery (`tests/test_m17cc_rr8_corrections.py`, 8 tests, first run 8/8)

The five predecessor-message pins (schema/basis; malformed rational with the INVALID_RATIONAL source text; noncanonical 2/2; `binding_json` divergence; `binding_hash` divergence — **exact-message equality**, not fragments, making future message-routing drift impossible); the typed-reason-reaches-§12 proof (the category + the richer reason); the coherent re-sign captured-hash proof (both layers independently demonstrated); and the repaired positive assertion on the RR6 subsegment path.

## Gates (first-run dispositions recorded exactly)

- RR8 battery **8/8 first run**; the correction-affected batteries **191/191** (all fifteen m17cc files + m17a/m17b recovery + shot mapping + bf recovery + sr2).
- Committed-tree validators green after the four-boundary carve; frontend green (143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3062 passed / 8 skipped / 0 failed in 48:05, exit 0** (collection 3070 = the prior 3062 + the 8-test battery — exact).
- **CI run `37037965848` on `39675bb`: SUCCESS, attempt 1 — Backend 3069 passed / 20 skipped / 0 failed** (CI total 3089 = its prior 3081 + the 8-test battery, exact); Frontend green attempt 1 (143/143).
- Predecessor-impact disclosure: `m17c_binding.py`'s message-emitting block is the only PF-03 byte change (the adapter rewrite); the RR7 round's now-false "verbatim preserved" claim is corrected in fact — the messages now ARE verbatim.

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. The next gate is another fresh independent exhaustive first-pass review of the corrected HEAD; RR8-01/02 are not closed merely because the new battery turns green.

---

# M17C-C tenth first-pass review — 2026-10-02 — NOT CLEAN (register RR9-M17CC-01 FROZEN)

The independent fresh review of implementation HEAD `39675bb` (no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 new Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `1c50051`, record-only above the reviewed head). The register is frozen.

## Register status

- **RR8-M17CC-01: CLOSED** (the typed-category routing is real; PF-03's predecessor messages match `132d2b3`; the substring router gone).
- **RR8-M17CC-02: CLOSED** (the re-sign adversary genuinely passes self-authentication and reaches the captured-hash disagreement; the repaired positive assertion is a real canonical-hash identity).
- **RR7-M17CC-01 remains CLOSED**; all earlier FPR/RR findings remain CLOSED (the RR7 ordering, RR6 containment, the forbidden-surface boundary, grammar-v2, the blocked-state posture, the Generation fence, and migration heads showed no regression). CI `37037965848` independently corroborated (synthetic merge `841bbc9` of `39675bb` into unchanged `d893d65`; Backend 3069/20/0, Frontend 143/143 + tsc + build; the four validator changes are exactly the RR8 test-path admissions — the green run does not exercise the malformed REAL shapes).

## Frozen finding

- **RR9-M17CC-01 — MEDIUM — the shared PF-03 binding structural law, and independently the M17C recovery binding verifier, are not total over SQLite storage classes: storage-valid non-integral REAL binding scalars escape the typed corruption contract as raw Python TypeError.** The physical tables declare the coordinates/rate/origin as INTEGER with numeric CHECKs but no `typeof = 'integer'` law — the reviewer independently reproduced that `48000.5` persists with storage class `real` and a canonical document over it serializes/hashes normally. `verify_stored_vocal_binding` at `39675bb` proves actual-integer storage ONLY for the origin pair; `source_start_sample`/`source_end_sample_exclusive`/`sample_rate_hz` are uncertified, so a coherent `48000.5` row with recomputed canonical bytes/hash PASSES self-authentication — then `_vocal_performance_interval`'s `Fraction((end - start) * 1000, sample_rate_hz)` receives a float numerator and raises raw `TypeError: both arguments should be Rational instances`, outside the PF-03 SoloRingError contract. Recovery independently: `_verify_binding_row` does no coordinate storage certification before the same arithmetic, and `_check_rational` runs `math.gcd(abs(num), den)` without establishing integer storage — a coherent `0.5/1` origin can raise raw TypeError before `_corrupt()` runs; `verify_m17c_binding_state`'s narrow normalization covers only `sqlite3.Error` in the physical-schema phase. The same persistence-totality class RR5 corrected for `ShotVocalSegmentMapping`; the PF-03 binding authority lacks it. NOT a reopening of the `_verify_binding_row`-duplication disposition — the finding is the concrete untyped-exception divergence. **Required:** the transport-neutral verifier certifies ALL persisted binding scalars BEFORE canonical-byte certification or arithmetic (actual non-bool integer coordinates + rate; `0 <= start < end`; positive rate; the existing canonical/i64 rational law; a SQLite-returned actual int already carries i64); recovery consumes the same total primitive (or an exactly shared lower-level one) so `_check_rational` and the sample arithmetic are unreachable with unchecked storage classes — not a third grammar. **Decisive battery:** a coherent re-signed `source_start_sample = 48000.5` (preferably on both candidate/revision bindings so adopted-pair equality also passes) → typed PF-03 corruption AND typed `RECOVERY_CORRUPTION`, never TypeError; a coherent non-integral origin (`0.5/1`) → recovery terminates through the typed structural law; the RR8 five exact-message pins byte-for-byte green, the coherent captured-hash proof and the RR6 subsegment path green.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR9-M17CC-01 frozen (0H/1M/0L). RR8-01 and RR8-02 CLOSED; RR7-01 remains CLOSED; all earlier findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready NOT authorized. Codex/second reviewer NOT run.** The next lawful step is a narrowly scoped RR9 correction cycle, then another fresh independent first-pass review. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR9-M17CC-01 CORRECTION — binding storage-class totality — 2026-10-02 — IMPLEMENTED

The commissioned correction is complete. Correction head: **`d0fb98b`** (implementation + battery + the four validator carves in one commit; all validators ran against this committed tree).

## Delivered (the commission exactly)

1. **The shared law is total over persisted binding storage classes** — `verify_stored_vocal_binding` certifies `source_start_sample`, `source_end_sample_exclusive`, and `sample_rate_hz` as actual non-bool Python integers, requires `0 <= start < end` and `rate > 0`, BEFORE any canonical serialization, hashing, comparison, or arithmetic; the origin keeps its existing actual-integer canonical-reduced signed-64-bit law through the ONE shared temporal primitive. Two NEW stable typed categories (`sample_storage`, `sample_domain`) on `BindingStructuralError` — routing on category only, never diagnostic text. A SQLite REAL can no longer survive structural certification.
2. **Recovery consumes the same law** — `_verify_binding_row`'s local grammar (its schema/basis check, its `_check_rational`/`math.gcd` origin pass, and its doc reconstruction + bytes/hash comparison) is REPLACED by the shared verifier, with `BindingStructuralError` translated to typed `_corrupt` (`… binding fails its own canonical structural law: <reason>`); and `_check_rational` itself is made total (a non-int pair is typed corruption, never a raw `math.gcd` TypeError), so no unchecked gcd/Fraction path can receive a malformed storage class under any pass ordering. Staged recovery outcome for malformed persisted bindings is always typed `RECOVERY_CORRUPTION`, never raw TypeError/ValueError/OverflowError and never successful verification; no parallel/third PF-03 grammar.
3. **RR8's transport contract preserved exactly** — `BindingStructuralError` remains the typed transport-neutral result; the five existing category→message mappings are byte-for-byte identical to `132d2b3` (re-proven by the RR8 exact-message pins, green); the new categories map to two new stable typed messages (`M17C vocal binding stores a non-integer sample scalar: <reason>` / `M17C vocal binding stores an illegal sample interval/rate: <reason>`), category-routed.
4. **Decisive adversaries, not surrogate tests** — a genuine SQLite REAL `source_start_sample = 48000.5` coherently re-signed on BOTH the candidate and revision binding rows (pair equality over all `BINDING_FIELDS` intact so adopted-pair equality cannot mask the law; canonical bytes/hash recomputed so the byte laws pass by construction; `typeof(column) = 'real'` demonstrated on both tables) refuses LIVE PF-03/readiness authority (the exact new typed message) AND live §12 history (the rich structural reason, NOT the captured-hash branch) AND staged M17C recovery (`RECOVERY_CORRUPTION`, same reason) — never a raw TypeError, never green, binding/mapping counts unchanged. A genuine non-integral origin `0.5/1` (the exact former raw-`math.gcd`-TypeError site) refuses typed on the recovery chain and both live seams — PF-03 surfacing the RR8-pinned predecessor vocabulary byte-for-byte.
5. **Every directly endangered closed seam re-proven** — the RR8 five exact-message pins (byte-for-byte), the RR8 coherent re-sign/captured-hash separation, the repaired positive hash identity, the RR7 stale-scalar and `binding_json` adversaries (still dying at self-authentication with their precise reasons), and the RR6 supported binding-subsegment path (READY → capture → first §12 read → recovery) all green in the affected suites; the clean control proves the certification refuses nothing lawful (boundary shapes `start == 0`, `rate == 1`, and a `2^63-1 / 2^63-2` origin verify green).
6. **Scope narrow** — no PF-02 readiness redesign, grammar-v2/snapshot change, Generation change, migration-head change, non-READY posture change, M17C-D work, or unrelated recovery redesign. **Predecessor impact of recovery calling the shared primitive, disclosed:** recovery's three former structural binding messages (`binding schema/basis version is not 1`; the `_check_rational` origin message; `binding canonical bytes/hash diverge`) consolidate into the one shared-law form `… binding fails its own canonical structural law: <reason>` carrying the shared law's precise reason (no test pinned the old wordings; the RR7 recovery assertion is code/substring-loose and stays green); `_check_rational` remains as defense-in-depth for the captured-child rationals but is itself total.

## The frozen battery (`tests/test_m17cc_rr9_corrections.py`, 15 tests, first run 15/15)

Eleven parametrized unit adversaries (REAL `48000.5`/`96000.5`/`48000.5`-rate, `True`, `"96000"`, `None` → `sample_storage`; `start == end`, inverted, negative-start, `rate == 0`, negative rate → `sample_domain` — each with the exact PF-03 message pinned by equality, and the byte laws passing by construction so only the scalar law can refuse); the lawful-pass proof (three boundary shapes verify green, returning the canonical document); the decisive REAL-coordinate end-to-end adversary (typeof integer→real demonstrated on both tables, stored bytes equal the canonical serialization of the row's own REAL-bearing fields, pair equality asserted, live readiness + §12 + staged recovery all typed, counts unchanged); the genuine `0.5/1` origin adversary (recovery typed at the exact former raw-TypeError site; live seams typed); the clean control (readiness READY → §12 green with the exposed `binding_hash` == the canonical hash of the lawful immutable document → backup + M17A + M17C recovery green).

## Gates (first-run dispositions recorded exactly)

- RR9 battery **15/15 first run**; affected suites **216/216** (the nine prior correction batteries 49 + the recovery/roundtrip/persist/capture/history/migration/bf-recovery/bf-regressions/binding-transitions/sr26/shot-mapping/rr9 set 167).
- Committed-tree validators **21/21 green** after the four-boundary carve (the two npm-audit validators consume the live `apps/web` audit on stdin; my first validator loop FAILed them by feeding no stdin — an invocation error, not a tree defect — rerun green with the live audit).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3077 passed / 8 skipped / 0 failed in 48:21, exit 0** (collection 3085 = the prior 3070 + the 15-test battery — exact).
- **CI run `37053903677` on `d0fb98b`: SUCCESS, attempt 1 — Backend 3084 passed / 20 skipped / 0 failed** (CI total 3104 = its prior 3089 + the 15-test battery, exact); Frontend green attempt 1.

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. The next gate is another fresh independent exhaustive first-pass review of the corrected HEAD; RR9 is not closed merely because the battery turns green.

---

# M17C-C eleventh first-pass review — 2026-10-03 — NOT CLEAN (register RR10-M17CC-01 FROZEN)

The independent fresh review of implementation HEAD `d0fb98b` (no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 1 new Medium, 0 High, 0 Low.** PR #26 remains draft, open, unmerged (tip `6ff512b`, record-only above the reviewed head). The register is frozen.

## Register status

- **RR9-M17CC-01: CLOSED** for the frozen REAL-coordinate/origin defect — the shared verifier rejects non-integer sample coordinates/rate before serialization or arithmetic; recovery genuinely delegates its binding-row structural certification to that same primitive; `_check_rational` no longer exposes malformed storage classes to `math.gcd`; the RR8 exact-message contract remains intact. This closes the sole open finding from the tenth-pass register.
- **RR8-M17CC-01..02 remain CLOSED; RR7-M17CC-01 remains CLOSED; all earlier FPR/RR findings remain CLOSED.**
- The `d0fb98b` source delta verified narrow (`m17c_binding.py`, `m17c_verifier.py`, the RR9 battery, the four validator admissions — no PF-02 semantics, capture grammar, snapshot anchoring, Generation behavior, migration head, non-READY posture, or M17C-D surface changed). The RR9 REAL-coordinate adversary verified substantive (both candidate and revision binding rows modified; `typeof` asserted `real`; canonical bytes/hash regenerated from the malformed row; `BINDING_FIELDS` pair equality explicitly checked before the three refusal surfaces; the `0.5/1` origin reaches the precise prior `math.gcd` escape shape). The RR8 exact-message regressions remain literal equality assertions for all five predecessor branches; the coherent post-authentication captured-hash proof unchanged and correctly ordered. CI `37053903677` independently corroborated on synthetic merge `1a1e498` (exact implementation `d0fb98b79004970f5e22ca787844a256c3674586` into unchanged base `d893d65`; Backend 3084/20/0; Frontend 143/143 + `tsc --noEmit` + production build) — those green gates do not exercise the BLOB-identity storage class.

## Frozen finding

- **RR10-M17CC-01 — MEDIUM — `verify_stored_vocal_binding` is still not total over SQLite storage classes: `vocal_performance_revision_id` reaches canonical JSON serialization without storage-type certification; a persisted BLOB produces a raw Python `TypeError` instead of typed PF-03 / §12 / recovery corruption.** The RR9 implementation correctly certifies all numerical binding authority before canonicalization, but the canonical document also contains `vocal_performance_revision_id`, which remains unchecked. The physical PF-03 table declares it `VARCHAR(36)` plus an FK, but there is no `typeof(...) = 'text'` constraint — SQLite permits a BLOB to be persisted in that TEXT-affinity column when corruption is staged through a raw connection with FK enforcement disabled (the same direct-SQLite corruption construction used throughout the recovery adversarial batteries). The reviewer independently checked the runtime behavior: a BLOB stored in a TEXT-affinity column is returned through SQLite/SQLAlchemy as Python `bytes`; Python's JSON encoder cannot serialize `bytes` — `json.dumps({"vocal_performance_revision_id": b"..."})` raises `TypeError: Object of type bytes is not JSON serializable`. That exception is reachable because `verify_stored_vocal_binding()` constructs the document and calls `canonical_json_str(doc)` immediately after the now-total numeric checks. None of the three consumers normalizes the failure: PF-03 `_verify_binding_bytes()` catches `BindingStructuralError` only; §12 catches `ValueError`, not `TypeError`; recovery `_verify_binding_row()` catches `BindingStructuralError` only. The recovery physical-schema phase does not make the shape unreachable (`_verify_table_schema()` certifies declared FK metadata, column types, CHECK inventory, and indexes; it performs no row-level `PRAGMA foreign_key_check` before `_verify_binding_row()`), so a staged BLOB VP identifier reaches the shared serializer first. The live authority path has the same ordering (canonical structure verified before the subsequent `session.get(VocalPerformanceRevision, ...)`, so the later typed "missing VP" law cannot intercept the malformed storage class either). A **typed-totality defect, not an authority-acceptance defect** — the corrupted binding is not silently accepted, but verification can escape through an uncontrolled Python exception rather than the established corruption contracts. **Required:** keep the RR9 numerical checks and every RR8 message mapping unchanged; before constructing the canonical document, the shared binding verifier certifies the document-bearing VP identity as its lawful persisted type — at minimum an actual Python `str` with the existing nonempty/exact-ID semantics; a BLOB becomes a new stable `BindingStructuralError` category (or another structurally appropriate typed category), never reaching `canonical_json_str()`; for completeness within the same primitive it is reasonable to type-certify the other serialized text inputs (`binding_json`, `binding_hash`) before their equality checks (those two currently fail through typed divergence rather than throwing); no new duplicate grammar; the five predecessor RR8 messages unchanged. **Decisive regression:** stage the actual SQLite shape — the SAME BLOB `vocal_performance_revision_id` on BOTH candidate and revision bindings with a raw SQLite connection, prove `typeof(...) == 'blob'` on both, preserve candidate↔revision pair equality so no pair-law surrogate masks the structural failure; then prove live PF-03/readiness terminates in a typed 500 (never raw `TypeError`); §12 terminates through its structural-binding invariant (never an unhandled exception); staged `verify_m17c_binding_state()` terminates as `RECOVERY_CORRUPTION`; no authority/persistence mutation occurs; RR8's five exact predecessor-message pins, the captured-hash separation, the RR7 adversaries, the RR6 subsegment, and the new RR9 REAL-scalar proofs all remain green.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR10-M17CC-01 frozen (0H/1M/0L). RR9-M17CC-01 CLOSED; RR8-M17CC-01..02 remain CLOSED; RR7-M17CC-01 remains CLOSED; all earlier FPR/RR findings remain CLOSED. PR #26 remains draft, unmerged, unready. Merge/ready authorization remains withheld. Codex/second reviewer NOT run.** The next lawful step is a narrowly scoped RR10 correction cycle followed by another fresh independent first-pass review. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR10-M17CC-01 CORRECTION — VP-identity storage certification — 2026-10-03 — IMPLEMENTED

The commissioned correction is complete. Correction heads: **`2aae452`** (implementation + battery) then **`8debfb4`** (the four validator carves — implementation preceded the carve adjustments per the commission; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **The remaining binding-document storage-class escape is closed** — `verify_stored_vocal_binding` certifies `vocal_performance_revision_id` BEFORE constructing or canonicalizing the binding document: an actual Python `str` and nonempty. A persisted BLOB/`bytes` value terminates as `BindingStructuralError`, never reaching `canonical_json_str()` and never producing a raw `TypeError`.
2. **A dedicated stable typed category** — `vp_identity_storage` (routing on category only, never human-readable diagnostics). PF-03, §12, and recovery continue consuming the single shared structural primitive; recovery's routing is unchanged (it already catches `BindingStructuralError`).
3. **Existing contracts preserved exactly** — the RR9 `sample_storage`/`sample_domain` checks unchanged; the five RR8 predecessor category→message mappings byte-for-byte unchanged (re-proven by the RR8 pins, green); no RR8 category repurposed — the new category carries its own new PF-03 corruption message (`M17C vocal binding stores a malformed persisted VP revision id: <reason>`).
4. **The identity rule kept appropriately narrow** — actual persisted `str` storage + nonempty is the WHOLE new law (mirroring the admission path's `isinstance(vp_id, str) and vp_id`); no UUID-format normalization, case rewriting, ID substitution, or other identity grammar introduced; existing cross-row VP existence/identity laws remain responsible for semantic referential validation after structural certification (on the read-grade live seam the VP fetch precedes the scalar laws, so a BLOB id surfaces that seam's own typed missing-VP corruption — typed either way, never raw).
5. **No parallel grammar for the other serialized inputs, disclosed** — `binding_json` and `binding_hash` are only ever `!=`-compared in the shared law (never serialized), and `bytes != str` evaluates to `True` (RR11-M17CC-01: this sentence originally — and falsely — said "a plain `False`"; corrected in the RR11 proof-only cycle, the executable proof added to the RR10 battery), so malformed storage there makes the guards' conditions TRUE and terminates through the existing typed divergence categories (`binding_json`/`binding_hash`); no hardening was needed and none was added.
6. **Recovery wording disclosure** — NONE introduced: the new category flows through the existing RR9 recovery translation (`… binding fails its own canonical structural law: <reason>` → typed `RECOVERY_CORRUPTION`) unchanged.
7. **The decisive proof stages the real SQLite shape** — the SAME genuine BLOB `vocal_performance_revision_id` written to BOTH the candidate and revision binding rows through a raw sqlite3 connection (bytes bind as BLOB; raw connections enforce no FK), with `typeof(...) == 'blob'` proven on both tables (and `'text'` proven before), candidate↔revision pair equality preserved over all `BINDING_FIELDS` so no pair-divergence law masks the target failure, and deliberately NO canonical re-sign — certification refuses before serialization becomes possible. Refusals proven on every surface: live PF-03 PUT authority (media-grade seam; the exact new typed message), live readiness (typed 500), live §12 (the typed structural-binding invariant carrying the VP-identity reason, NOT the captured-hash branch), and staged `verify_m17c_binding_state` (`RECOVERY_CORRUPTION`, same reason) — none emits raw `TypeError`, and binding/mapping counts are unchanged. The prior proofs re-run green in the affected suites: the RR9 REAL-coordinate/origin adversaries, all five RR8 exact-message pins, the RR8 captured-hash separation and positive hash identity, the RR7 self-auth adversaries, and the RR6 supported subsegment path.
8. **Scope frozen** — no PF-02 redesign, grammar-v2/snapshot change, Generation change, migration-head change, non-READY-posture change, M17C-D work, or unrelated recovery redesign. (The uncalled legacy helper `_row_document` in `m17c_binding.py` was noticed and deliberately left untouched — narrow scope.)

## The frozen battery (`tests/test_m17cc_rr10_corrections.py`, 7 tests, first run 7/7)

Four parametrized unit pins (the genuine 36-byte BLOB `b'00000000-…-bb'`, an int, `None`, and the empty string — each the exact `vp_identity_storage` category, the exact reason, and the exact new PF-03 message by equality); the lawful-str pass proof (two boundary shapes verify green, returning the canonical document); the decisive BLOB-on-both-rows end-to-end adversary (typeof text→blob proven on both tables, pair equality asserted, live PUT/readiness/§12/staged-recovery all typed with counts unchanged); the clean control (readiness READY → §12 green with the exposed `binding_hash` == the canonical hash of the lawful document → backup + M17A + M17C recovery green).

## Gates (first-run dispositions recorded exactly)

- RR10 battery **7/7 first run**; affected suites **223/223** (the ten prior correction batteries 64 — including the mandated RR9 REAL adversaries, the RR8 five pins + captured-hash + positive identity, the RR7 self-auth adversaries, the RR6 subsegment — plus the recovery/roundtrip/persist/capture/history/migration/bf-recovery/bf-regressions/binding-transitions/sr26/shot-mapping/rr10 set 159).
- Committed-tree validators **21/21 green** after the four-boundary carve (implementation commit `2aae452` preceded the carve commit `8debfb4`; the two npm-audit validators consume the live `apps/web` audit on stdin).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3084 passed / 8 skipped / 0 failed in 47:32, exit 0** (collection 3092 = the prior 3085 + the 7-test battery — exact).
- **CI run `37069665202` on `8debfb4`: SUCCESS, attempt 1 — Backend 3091 passed / 20 skipped / 0 failed** (plus the focused 107; CI total 3111 = its prior 3104 + the 7-test battery, exact); Frontend green attempt 1.

## Fences honored

No Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. RR10 is not closed by this implementation or the green CI — the corrected implementation HEAD gets a twelfth fresh independent exhaustive first-pass review.

---

# M17C-C twelfth first-pass review — 2026-10-03 — NOT CLEAN (register RR11-M17CC-01 FROZEN)

The independent fresh review of carve HEAD `8debfb4` (implementation `2aae452`; no Codex/second reviewer) is complete. **Verdict: NOT CLEAN — 0 High / 0 Medium / 1 Low.** PR #26 remains draft, open, unmerged (tip `a94f4ee`, record-only above the reviewed carve head). The register is frozen.

## Register status

- **RR10-M17CC-01: CLOSED** — the commissioned product correction is real: `vocal_performance_revision_id` is certified as a nonempty `str` before canonical document construction; the dedicated typed category is wired into PF-03; §12 and recovery remain on the shared primitive; RR9 numerical totality and all five RR8 predecessor-message mappings remain intact; the correction record accurately describes the substantive implementation and gate results. The commit discipline independently confirmed (`a057b3e → 2aae452` changes only `m17c_binding.py` plus the RR10 battery; `2aae452 → 8debfb4` changes only the four validator admissions).
- **RR9, RR8, RR7, and all earlier findings remain CLOSED.**
- The decisive RR10 BLOB adversary verified substantive (the same BLOB on both candidate and revision binding rows; `typeof(...) == 'blob'` proved on both; `BINDING_FIELDS` equality prevents pair divergence from masking the target; §12 and recovery terminate typed; the live PUT fails before its upsert, so the count-only no-mutation assertion is backed by actual control-flow ordering rather than being the sole evidence). The legacy `_row_document` helper verified definition-only at the reviewed head — no active alternative binding grammar. CI `37069665202` independently corroborated on synthetic merge `07562f6` of exact carve head `8debfb4` into unchanged base `d893d65` (focused M17C 107 passed; full backend 3091 passed / 20 skipped; frontend 143/143; typecheck clean; production build successful).

## Frozen finding

- **RR11-M17CC-01 — LOW — proof-record factual inversion.** The RR10 implementation is correct, but its proof narrative contains a false Python-semantics statement in two committed artifacts: both `tests/test_m17cc_rr10_corrections.py` and the pushed scope record say, in substance, that `bytes != str` evaluates to `False`, therefore malformed `binding_json`/`binding_hash` storage falls into the existing typed divergence laws. That boolean statement is backwards: `b"x" != "x"` → **`True`** — and that is precisely why the implementation is safe: `if binding_json != expected_json:` makes the condition TRUE for a BLOB/`bytes` `binding_json` compared with canonical `str` and takes the typed divergence branch; `binding_hash` behaves analogously. The pushed correction record contains the inverted claim explicitly. The product law does not share the defect; this is a proof/documentation accuracy failure. The reviewer also examined the related ordering statement: the read-grade revision seam can resolve the malformed BLOB VP identity as a typed missing-VP corruption before `_read_binding_scalar_laws` reaches the new category — that does NOT reopen RR10 (it remains fail-closed and cannot reach serialization/arithmetic); media-grade PF-03, §12, and standalone M17C recovery directly exercise the new structural category; no separate finding warranted. **Required narrow correction — proof-only; no product source change indicated:** correct the RR10 battery narrative and scope record from `bytes != str is False` to the actual law (`bytes != str` is `True`, which causes the existing `!=` guards to enter their typed `binding_json`/`binding_hash` divergence branches); a very small direct regression for BLOB `binding_json` and BLOB `binding_hash` would be useful to turn that reasoning into executable evidence, but it must not introduce another grammar or modify `m17c_binding.py` unless the test exposes an actual product defect; preserve the first-run disposition if such a proof test is added.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE. New register RR11-M17CC-01 frozen (0H/0M/1L). RR10-M17CC-01 CLOSED; RR9, RR8, RR7, and all earlier findings remain CLOSED. PR #26 remains draft, unmerged, unready. No Codex/second reviewer, merge, or ready-mark yet.** The next lawful step is the narrowly scoped RR11 proof-record correction, followed by another fresh first-pass review. No correction work has started; the cycle awaits its gate.

---

# M17C-C RR11-M17CC-01 CORRECTION — proof-only — 2026-10-03 — IMPLEMENTED

The commissioned proof-only correction is complete. Correction head: **`83d5c99`** (the battery narrative fix + executable proof — the test file is the ONLY changed executable artifact) then the record commit (this section + the RR10 prose correction above). **No product source byte changed: `m17c_binding.py`, PF-03 routing, recovery, §12, schema/storage, migrations, and all authority semantics untouched — `83d5c99` changes only `tests/test_m17cc_rr10_corrections.py`; the record commit changes only this file.**

## Delivered (the commission exactly)

1. **Both committed false statements corrected** — the RR10 battery narrative (`tests/test_m17cc_rr10_corrections.py` module docstring) and the RR10 scope-record prose (point 5 of its "Delivered" section, corrected in place above with the inversion identified inline) now state the actual Python law: `bytes != str` evaluates to **`True`**, so the existing `!=` conditions are TRUE for BLOB/`bytes` `binding_json`/`binding_hash` and ENTER the typed `binding_json`/`binding_hash` divergence branches. The original inverted text remains in git history at `a94f4ee` for exact comparison.
2. **The executable proof added to the existing RR10 battery** (no new file — no validator carve needed; no new category or grammar; `m17c_binding.py` untouched): a BLOB/`bytes` `binding_json` (the other input lawful) → `BindingStructuralError.CATEGORY_BINDING_JSON`; a BLOB/`bytes` `binding_hash` → `CATEGORY_BINDING_HASH`; each case asserts the `bytes != str` premise in-band and proves PF-03 maps BOTH to the exact RR8 predecessor message `M17C vocal binding canonical bytes/hash diverge` by equality. **The executable cases confirmed the product law and exposed NO defect — RR10 remains CLOSED throughout this proof correction (recorded explicitly per the commission).**
3. **First-run disposition preserved exactly** — the two proof cases were added this cycle and were green on their FIRST run (no fixture corrections, no re-runs after edits); nothing is recorded as though it had been green earlier. The prior seven RR10 tests were untouched by the executable change (narrative-only docstring edit) and remain green.
4. **Directly endangered evidence re-run** — the RR10 VP-identity battery (9/9 incl. the new proofs), the RR9 storage-totality adversaries, the RR8 five exact-message pins, and RR7 all green; the broader recovery/history/persist/capture/roundtrip/migration/bf/binding-transitions/sr26/shot-mapping set (152) green as corroboration only — no unrelated code was touched, and none needed to be.

## Gates (first-run dispositions recorded exactly)

- Extended RR10 battery **9/9** (the two new RR11 proof cases green on first run); mandated re-runs **27/27** (RR9 + RR8 + RR7) and prior batteries **37/37**; corroboration set **152/152**.
- Committed-tree validators **21/21 green** (no carve change — the proof lives in the already-admitted RR10 battery file; run against the committed battery head `83d5c99`).
- Frontend green (vitest 143/143 + tsc + build — unaffected by a test/docs-only delta; run for completeness).
- Local full backend suite, FIRST RUN: **3086 passed / 8 skipped / 0 failed in 52:13, exit 0** (collection 3094 = the prior 3092 + the 2 proof cases — exact).
- **CI run `37076818197` on `83d5c99`: SUCCESS, attempt 1 — Backend 3093 passed / 20 skipped / 0 failed** (CI total 3113 = its prior 3111 + the 2 proof cases, exact); Frontend green attempt 1.

## Fences honored

No product source change; no Codex/second review; no merge/ready; PR #26 remains draft, unmerged, unready. RR11 is NOT closed by editing prose or by the green proof — a thirteenth fresh independent first-pass review must independently verify both corrected prose and the executable evidence before closing it.

---

# M17C-C thirteenth first-pass review — 2026-10-03 — CLEAN (no new register)

The independent fresh review of proof HEAD `83d5c99` (record `6ad263e`; no Codex/second reviewer) is complete. **Verdict: CLEAN — 0 High / 0 Medium / 0 Low. No new findings register.**

## Register status

- **RR11-M17CC-01: CLOSED** — the proof-only correction is complete and accurate: the previously inverted statement is corrected in the RR10 record (`bytes != str` evaluates to `True`, so malformed BLOB/`bytes` serialized fields make the existing `!=` guards true and enter the typed divergence branches). The executable evidence verified substantive: `83d5c99` modifies only `tests/test_m17cc_rr10_corrections.py` (no product source changed); the two new cases independently exercise `binding_json` and `binding_hash` as `bytes`, assert the actual Python comparison premise, require `CATEGORY_BINDING_JSON`/`CATEGORY_BINDING_HASH`, and pin PF-03 to the unchanged RR8 message `M17C vocal binding canonical bytes/hash diverge`; the correction record accurately describes that proof and explicitly keeps RR10 closed.
- **RR10, RR9, RR8, RR7, and all earlier FPR/RR findings remain CLOSED.** No regression found in the shared binding law: VP identity remains certified before serialization; all document-bearing numeric values are type/domain-certified; canonical rational certification remains before document construction; `binding_json`/`binding_hash` comparisons are exception-safe over malformed storage classes; the five RR8 mappings unchanged; no new duplicate grammar or altered transport contract.
- **Evidentiary distinction examined and accepted:** the new tests are unit-level Python-`bytes` cases rather than another `typeof(...) = 'blob'` database adversary — sufficient for this frozen proof defect because the disputed proposition was Python comparison behavior; and the storage representation is reachable, not artificial (the physical schema leaves both serialized fields as TEXT-affinity values; a 64-byte ASCII BLOB can satisfy the existing `binding_hash` length/hex CHECK; SQLite/SQLAlchemy returns such BLOB values as Python `bytes`).
- **Repository discipline intact:** PR #26 open, draft, unmerged; current tip is record-only `6ad263e`; exact proof head `83d5c992b00f84a7cf31feb75d7dcc5cc532b02d`; `283f5fd → 83d5c99` changes only the RR10 test file; `83d5c99 → 6ad263e` changes only this record. CI `37076818197` independently corroborated on synthetic merge `1e311b3` of the exact proof head into unchanged base `d893d65` (focused M17C 107 passed; full backend 3093 passed / 20 skipped; frontend 143/143; typecheck clean; production build successful). The recorded local/full gate arithmetic verified internally consistent (3086/8 with collection 3094, exactly +2 from the prior tree).

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE — CLEAN. No new findings register. RR11-M17CC-01 CLOSED; RR10, RR9, RR8, RR7, and all earlier FPR/RR findings remain CLOSED.** This is the FIRST clean independent first-pass state after the correction sequence (FPR 8 → RR 4 → RR2 → RR3 → RR4 → RR5 → RR6 → RR7 → RR8 → RR9 → RR10 → RR11, every register corrected under an explicit commission and re-reviewed). The project is **eligible for the Codex/second-review phase — NOT run**. PR #26 remains draft, unmerged, unready; **merge/ready authorization remains withheld pending the user's next explicit gate.**

---

# M17C-C independent second review (Codex phase) — 2026-10-03 — reconciled disposition NOT CLEAN (register SR-M17CC-01..05 FROZEN)

The independent second review of exact proof head `83d5c992b00f84a7cf31feb75d7dcc5cc532b02d` (predecessor baseline `8a92bc6`) is complete, and the user's reconciliation against that head confirms all five findings. **Reconciled disposition: NOT CLEAN — 1 High / 4 Medium / 0 Low.** The review itself was properly frozen at the intended baseline/head and explicitly performed no historical reconciliation and made no merge/readiness recommendation. PR #26 remains open, draft, unmerged (tip `50dc7bb`, record-only above the proof head). The register is frozen.

## Frozen findings (each independently CONFIRMED at reconciliation)

1. **SR-M17CC-01 — HIGH — sparse-but-READY public positions mint §12/recovery-invalid durable history.** A supported public PUT permits a mapping solely at position `1` (`validate_mapping_position()` requires only an integer in the SQLite-i64 domain); readiness orders whatever rows exist and computes `ready = all(...)` with NO dense `[0..n-1]` requirement; `resolve_performance_plane()` accepts the all-READY sparse projection; `_performance_segments_value()` checks only sorted/unique positions; persistence mechanically writes child position `1`. Both §12 and recovery independently require the first embedded element to declare position `0` — so NORMAL API USE can successfully capture a ShotRevision whose FIRST historical inspection and recovery verification reject it. Not corruption injection: ordinary supported authority creation producing internally invalid durable history. **High appropriate.**
2. **SR-M17CC-02 — MEDIUM — §12 missing the canonical-rational and immutable PR-domain timing laws recovery enforces.** The §12 `_rat()` helper proves only `isinstance(..., int)` and a positive denominator — no reduced form, no canonical zero, and it admits `bool` (a Python `int` subclass); more materially, the generic §12 branch loads the immutable PerformanceRevision but never proves the captured Performance interval lies inside that revision's immutable temporal domain. Recovery performs both. A coherently re-signed captured graph (all dependent hashes recomputed) can remain self-consistent at snapshot/parent/child/hash level, pass §12, and fail recovery solely on the missing immutable timing laws. A genuine history/recovery semantic divergence; both subcases (unreduced `2/2`; canonical-but-out-of-PR-domain) identified accurately.
3. **SR-M17CC-03 — MEDIUM — embedded scalar projection is Python-value-equivalent, not type-exact (`False == 0`).** The schema-8 history grammar checks `seg["position"] != index` and recovery later checks `row["position"] != seg["position"]` — ordinary Python comparison, so a fully canonical/rehashed JSON graph declaring `"position": false` compares EQUAL to relational integer position `0` at BOTH seams. Neither canonical snapshot bytes nor canonical segment bytes help (the forged `false` document is itself canonical JSON and consistently rehashable). The immutable serialized authority and its relational projection are therefore only Python-value equivalent, not type-exact. The same equality-class problem affects other scalar projection comparisons; position alone demonstrates the defect. Medium stands.
4. **SR-M17CC-04 — MEDIUM — §12 exposes the referenced PR/VP semantic closure without revalidating it.** §12 authenticates the PF-03 binding but then loads the referenced VP and exposes its semantic fields without the semantic closure recovery requires: captured subject == VP speaker; VP dialogue lineage belongs to the Shot project; captured sample interval inside immutable VP trim; VP native rate agreement; PerformanceRevision project == Shot project. A raw mutation of the referenced immutable VP's `speaker_subject_id` to another valid entity leaves the authenticated binding and captured graph untouched while §12 returns the mutated speaker as historical truth and recovery refuses the database. The VP-speaker case alone establishes the defect; the PR-project variant is also supported.
5. **SR-M17CC-05 — MEDIUM — GPI recovery not total over SQLite storage classes (raw `TypeError` from `bytes.strip(str)`).** `generation_performance_inputs.derived_input_hash` is TEXT-affinity with only `length(...) = 64`; SQLite accepts a 64-byte BLOB under that CHECK, and SQLite/SQLAlchemy returns it as Python `bytes`. The recovery verifier then calls `value.strip("0123456789abcdef")` without first requiring `value` to be `str`; `bytes.strip(str)` raises `TypeError: a bytes-like object is required, not 'str'`, and the top-level recovery function has no normalization covering that semantic traversal — a storage-valid malformed M17C-C-owned GPI row escapes the typed `RECOVERY_CORRUPTION` contract. The reviewer's additional REAL-position concern is credible from the schema shape but NOT needed to confirm the finding (the BLOB hash adversary is decisive, reproducible directly from SQLite/Python semantics without involving a Blob FK).

## Reconciliation against the first-pass history (frozen as stated)

These are **NOT grounds to reopen any old FPR/RR register** — five NEW defects discovered by the independent reviewer after the first-pass sequence was clean. `SR-M17CC-05` resembles the RR9/RR10 storage-class-totality class but is a DISTINCT M17C-C-owned GPI recovery surface — it remains a new second-review finding, not folded into or described as a regression of RR9/RR10. The thirteenth first-pass CLEAN disposition remains historically accurate (it reported what that pass found); the independent second review subsequently found additional defects. NEITHER record is rewritten. The reviewer's own non-findings (binding structural authentication, paired vocal mapping integrity, binding subsegment semantics, mapping-hash capture closure, forbidden current reads, physical payload closure, schema-8 Generation fence, observation successor behavior, working currentness, migration/downgrade, backup/restore + Blob inventory, and the M17C-D boundary all challenged with no additional defect) and its explicit treatment of the green CI totals as reproducibility information rather than acceptance evidence stand as part of the frozen report.

## Eventual correction boundary (as frozen by the reconciliation — five decisive regressions)

1. sparse-but-READY public positions cannot produce §12/recovery-invalid capture;
2. §12 enforces canonical captured rationals plus immutable PR-domain timing;
3. embedded scalar projection is type-exact, with the `false ↔ 0` adversary refused;
4. §12 revalidates the immutable PR/VP semantic closure it exposes;
5. GPI recovery is total over SQLite storage classes, beginning with the real 64-byte-BLOB digest adversary.

## Frozen disposition

**SECOND-REVIEW RECONCILIATION COMPLETE. Register SR-M17CC-01..05 frozen — CONFIRMED — 1H/4M/0L.** The clean first-pass had made the project eligible for second review; this second review has correctly returned it to a **correction gate**. PR #26 remains open, draft, unmerged, unready. **No product/test/document correction begins until the user explicitly commissions `SR-M17CC-01..05`.**

---

# M17C-C SR-M17CC-01..05 CORRECTION — second-review findings — 2026-10-03 — IMPLEMENTED

The commissioned correction cycle is complete. Correction heads: **`6bc1ac4`** (implementation + battery) then **`5c71022`** (the four validator carves — implementation preceded the carve adjustments; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **SR-01 — sparse positions never READY/capturable.** The captured-history grammar stays dense canonical `[0..n-1]` (§12/recovery untouched); the READINESS projection now carries the density law — a position set that is not exactly `[0..n-1]` classifies EVERY segment `BLOCKED_POSITIONS_NOT_DENSE` with a plane-level diagnostic (a lawful working-state data classification, the same posture family as the supported-DELETE `BLOCKED_BINDING_INTEGRITY`), so a sparse public set can never project READY nor reach `resolve_performance_plane` capture. Proof: a lawful public PUT solely at position 1 → readiness `ready: false` with the new classification on every segment; capture refuses as the typed non-ready 409 with ZERO new revision/spec/children rows; filling position 0 restores READY and the dense capture path stays green.
2. **SR-02 — §12 rational/domain parity.** `_rat` now enforces the SAME canonical rational law recovery enforces, through the ONE shared temporal primitive (`canonical_rational`: actual non-bool integer pair, positive denominator, gcd-reduced, canonical zero — no parallel §12 grammar); every captured interval must be nonempty; GENERIC captured intervals must lie inside the immutable PerformanceRevision temporal domain (the dialogue-bound branch proves its interval exactly through the binding induction instead — mirroring recovery's branch split). Proofs: the coherent unreduced `2/2` rewrite and the coherent canonical-but-out-of-domain rewrite (child columns + embedded segment + recomputed mapping hashes + segment/spec/snapshot bytes/hashes) refused by BOTH §12 (typed 500, the new §12 reasons) and staged recovery.
3. **SR-03 — type-exact projection.** ONE shared helper (`m17cc_capture_read.exact_projection_equal`: same value AND same lawful type) now backs §12's embedded-position grammar check, §12's two companion/embedded projection loops, and recovery's `_verify_m17cc_child` position + both projection loops — Python cross-type aliases (`False == 0`, `True == 1`, `1.0 == 1`) no longer satisfy field identity. Proof: the coherent `position: 0 → false` rewrite (all canonical hashes recomputed; the relational child proven `typeof == 'integer'`) refused by BOTH surfaces (§12 "declares position False"; recovery "disagrees with the embedded captured ordering").
4. **SR-04 — §12 authenticates the PR/VP semantic closure it exposes.** The PR query now selects `project_id` and every child proves PR project == Shot project (the Shot resolved once per history call from the revision's own `shot_id` — the ShotRevision/Shot/dialogue tables only, none on the forbidden current-surface list); dialogue-bound children prove subject == VP speaker, VP native rate == captured rate, captured samples inside the immutable VP trim, and VP dialogue-line lineage project == Shot project, all BEFORE any VP field answers as historical truth. Proofs: the raw VP-speaker mutation and the raw PR-project mutation (captured graph and authenticated binding untouched) each make §12 fail closed typed AND staged recovery refuse — recovery's refusal fires from its own earliest applicable law over the mutated immutable row (the candidate-binding subject law / the mapping project law), fail-closed either way.
5. **SR-05 — GPI recovery total over storage classes.** The GPI verifier certifies persisted types BEFORE any string/integer operation: `position`/`shot_revision_segment_position` actual nonnegative non-bool ints; `blob_hash`/`segment_hash`/`derived_input_hash`/`binding_hash` actual `str` — a genuine 64-byte BLOB `derived_input_hash` (which passes the TEXT-affinity `length` CHECK; `typeof` proven `'blob'`) and genuine REAL coordinates (`1.5`/`2.5`, `typeof` proven `'real'`) terminate as typed `RECOVERY_CORRUPTION`, never a raw `bytes.strip` TypeError and never acceptance.
6. **No unrelated redesign; every previously closed law preserved** — all FPR/RR batteries green unchanged (endangered suites below); no executable contradiction of a prior law was uncovered (no new finding).

## The frozen battery (`tests/test_m17cc_sr_corrections.py`, 10 tests, final 10/10)

SR-01 sparse-PUT adversary (blocked classification asserted, 409 capture, zero new rows, dense control READY → capture → §12 200 with both children); SR-02's two coherent timing rewrites refused at both surfaces with per-surface fragments; SR-03's coherent `position:false` rewrite refused at both surfaces with the child's integer storage proven; SR-04's two immutable semantic mutations fail-closed at both surfaces (backup always taken while the world is lawful — the live database is corrupted only after the staged copy exists); SR-05's three GPI storage-class adversaries with `typeof` proven per column; the clean control (dense world green end-to-end: readiness READY, §12 answering both children with the canonical in-domain generic interval and the verified VP speaker, backup + M17A + M17C recovery).

## Gates (first-run dispositions recorded exactly)

- SR battery **first run 8/10, disclosed**: the two SR-04 recovery-leg fragments assumed the §13.4 child law fires first — the recovery chain's earlier laws (the candidate-binding subject law; the M17A mapping project law) refuse first, both typed `RECOVERY_CORRUPTION`; the test fragments were corrected to the actual earliest typed laws (a test-expectation correction — no product or fixture change); rerun **10/10**.
- Directly endangered batteries first: core m17cc (capture/history/persist/recovery/roundtrip/migration + SR) **89/89**; all eleven prior correction batteries (FPR, RR, RR2–RR10 incl. RR5's readiness-tamper laws, RR7's spy, RR8 pins, RR9/RR10 totality) **73/73**; live-seam + predecessor recovery (shot mapping, bf recovery/regressions, binding transitions, sr26, M17A/M17B recovery) **87/87**.
- Committed-tree validators **21/21 green** (implementation `6bc1ac4` preceded the carve commit `5c71022`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3096 passed / 8 skipped / 0 failed in 48:55, exit 0** (collection 3104 = the prior 3094 + the 10-test battery — exact).
- **CI run `37124494037` on `5c71022`: SUCCESS, attempt 1 — Backend 3103 passed / 20 skipped / 0 failed** (CI total 3123 = its prior 3113 + the 10-test battery, exact); Frontend green attempt 1.

## Fences honored

No Codex/second review beyond the one already reconciled; no merge/ready; PR #26 remains draft, unmerged, unready. Green gates are corroboration only — SR-M17CC-01..05 are not closed by this implementation: the corrected implementation HEAD gets a **fresh independent first-pass review** next, per the commission.

---

# M17C-C fourteenth first-pass review — 2026-10-03 — NOT CLEAN (SR-M17CC-03 remains OPEN at Medium)

The fresh independent first-pass review of the corrected executable tree is complete — executable head **`5c71022a312cb98c41f1b0f2d38ffb6f59813027`**, implementation commit **`6bc1ac430c78b493ce66e9d56792309756a0b146`**, with **`d9f56e58979ab1b60c1604935cc0ecffe9f78869`** confirmed documentation-only above it. PR #26 still open, draft, unmerged (base `d893d65c343777b6711c0f772e2059ce273e985f`). No Codex/second-review run occurred. **Verdict: NOT CLEAN — 0 High / 1 Medium / 0 Low.**

## Register resolution (frozen by the review)

- **SR-M17CC-01: CLOSED** — the density gate is effective (a sparse working set survives as lawful working data but every row is reclassified `BLOCKED_POSITIONS_NOT_DENSE`, so `resolve_performance_plane()` cannot treat it as capturable); the dense `[0..n-1]` historical grammar remains unchanged, the correct boundary.
- **SR-M17CC-02: CLOSED** — §12 rejects bool/non-int rational storage, runs the shared canonicalization primitive, requires the persisted representation itself to be canonical, rejects empty/inverted captured intervals, and checks generic captures against the immutable PR domain; no remaining history/recovery divergence in the commissioned timing cases.
- **SR-M17CC-03: NOT CLOSED — Medium (residual).** The decisive `position:false` path is fixed, but the frozen finding explicitly identified the broader Python cross-type equality class, not only position: **the snapshot-anchored vocal-origin preimage still uses ordinary comparisons** in `verify_mapping_hash_closure()` and in recovery (`row["vocal_performance_origin_num"] != embedded_origin["num"]` and the denominator equivalent) — a child integer origin `0/1` still compares equal to embedded JSON `false/1.0`. A coherent adversary can leave the child and its `vocal_mapping_hash` based on integer `0/1`, rewrite only the embedded origin scalar type, and recompute `segment_json`/hash, parent spec bytes/hash, and outer snapshot bytes/hash; both §12 and recovery accept the origin comparison because Python evaluates `0 == False` and `1 == 1.0` as true — the immutable serialized preimage and relational projection remain only Python-value-equivalent at this coordinate, not type-exact. **The same seam has a second failure manifestation:** `_verify_embedded_grammar()` does not validate the shape of `vocal_performance_origin_ms` or the nested timing rational objects before later code subscripts `["num"]`/`["den"]` — a coherently rehashed embedded `"vocal_performance_origin_ms": false` reaches `embedded_origin["num"]` and raises a raw `TypeError`; similarly a malformed `performance_start_ms` object can fail while the projection tuple is being constructed. Recovery therefore still has a malformed-captured-JSON route that escapes `RECOVERY_CORRUPTION`, and §12 does not convert it through its typed internal-invariant contract.
- **SR-M17CC-04: CLOSED** — §12 proves PR→Shot project coherence for every child and, before exposing dialogue VP fields, speaker/subject, native-rate, trim containment, and dialogue-lineage project coherence; the new reads remain historical/immutable lineage reads, not current selection or working-mapping reads.
- **SR-M17CC-05: CLOSED** — GPI recovery certifies the two integer coordinates and all hash-string storage classes before arithmetic, slicing, `len`, or `.strip`; the 64-byte BLOB and REAL-coordinate escape routes are closed through typed corruption.

The committed green evidence verified internally consistent but remains corroboration only; the review independently confirmed CI `37124494037` succeeded (focused backend 107 passed; full backend 3103 passed / 20 skipped; frontend 143/143 with `tsc --noEmit` and a successful production build).

## Required narrow correction (as frozen by the review)

Extend the shared type-exact law to the snapshot-anchored vocal-origin preimage, and validate the closed nested rational/origin object grammar before any subscripting. Decisive regressions: an embedded `origin.num: false` versus relational integer `0` with the whole hash chain recomputed, plus a non-object nested rational/origin adversary proving §12 returns typed internal corruption and recovery returns `RECOVERY_CORRUPTION` — never raw `TypeError`.

## Frozen disposition

**FIRST-PASS REVIEW COMPLETE — NOT CLEAN. SR-M17CC-01, -02, -04 and -05 CLOSED; SR-M17CC-03 remains OPEN at Medium. No Codex/second review is authorized at this state. PR #26 remains draft, unmerged, unready; no correction has been started by this review — the residual SR-03 correction awaits its gate.**

---

# M17C-C SR-M17CC-03 residual correction — 2026-10-03 — IMPLEMENTED

The commissioned residual correction (strictly the fourteenth-review frozen Medium) is complete. Correction head: **`cbf599c`** (implementation + the residual battery appended to the existing `tests/test_m17cc_sr_corrections.py` — no new test file, therefore no validator admission was required; implementation/tests were committed before any gate).

## Delivered (the commission exactly)

1. **The remaining type-exact projection seam is closed.** The snapshot-anchored `vocal_performance_origin_ms.num`/`.den` comparisons in BOTH consumers — §12's `verify_mapping_hash_closure()` and recovery's child preimage block — now go through the ONE shared `exact_projection_equal` law: the immutable embedded JSON value and the relational projection must agree in both value AND lawful type; `False == 0`, `True == 1`, and `1.0 == 1` never satisfy captured identity at this coordinate.
2. **The malformed nested-grammar escape is closed.** A NEW shared `embedded_rational_shape_error` validates that the nested captured objects required by the schema-8 segment grammar — `performance_start_ms`, `performance_end_ms`, `shot_anchor_ms`, and a non-null `vocal_performance_origin_ms` — are each an actual `{num, den}` object BEFORE any `["num"]`/`["den"]` access. It is wired into `_verify_embedded_grammar()` (§12: typed internal-invariant, "carries a malformed nested value") and the START of recovery's `_verify_m17cc_child` (typed `RECOVERY_CORRUPTION`, "carries a malformed nested captured value"). Malformed embedded JSON terminates through the existing typed contracts on both surfaces — no raw `TypeError`/`KeyError` can escape.
3. **The decisive regressions, exactly as commissioned.** (a) The coherent `origin.num: 0 → false` rewrite — the relational child left at integer `0/1`, its mapping hashes rebuilt from the row's own untouched integer preimage, the complete segment/spec/snapshot hash chain recomputed — is refused by BOTH §12 and recovery with the origin-preimage disagreement message; the lawful dialogue-bound control was proven green immediately BEFORE the tamper. (b) The non-object nested adversaries (`vocal_performance_origin_ms: false` and `performance_start_ms: false`, with the surrounding canonical hashes refreshed by a bytes-only coherent rewriter that leaves every relational column untouched) fail typed on both surfaces — §12 through the internal-invariant contract, recovery as `RECOVERY_CORRUPTION` — never a raw Python exception.
4. **No broadening.** Capture grammar, readiness, PF-02/PF-03 authority, mapping semantics, schema/storage, migrations, Generation behavior, and error vocabulary untouched. SR-01/02/04/05 and all earlier FPR/RR closures re-proved green (below); no executable regression of any prior law was demonstrated.

## Gates (first-run dispositions recorded exactly)

- Extended SR battery **13/13 on FIRST run** (the three residual tests green on first run — no fixture corrections, no re-runs after edits).
- Directly endangered batteries first: history/recovery/capture/persist/roundtrip/migration + the SR battery **92/92**; prior type-totality + correction + live-seam batteries (RR/RR2–RR10 incl. RR5's mapping totality and RR7's read-isolation guard, FPR, shot mapping, sr26) **114/114**.
- Committed-tree validators **21/21 green** (no validator change — the residual battery lives in the already-admitted SR battery file).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3099 passed / 8 skipped / 0 failed in 49:40, exit 0** (collection 3107 = the prior 3104 + the 3 residual tests — exact).
- **CI run `37152752470` on `cbf599c`: SUCCESS, attempt 1 — Backend 3106 passed / 20 skipped / 0 failed** (CI total 3126 = its prior 3123 + the 3 residual tests, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No Codex/second review; no ready-mark; no merge; PR #26 remains draft, unmerged, unready. **This correction does not close SR-M17CC-03** — the work now stops and holds for the **fifteenth fresh independent first-pass review** of the corrected head.

---

# M17C-C fifteenth first-pass review — 2026-10-04 — NOT CLEAN (register RR12-M17CC-01..02 FROZEN)

The fifteenth fresh independent first-pass review of executable head **`cbf599c47de6ffd451fba1f7eb45037071b68687`** is complete (**`7abe3992e107bb015e4a7a99ff7933293ac5e99a`** confirmed documentation-only above it; PR #26 open, draft, unmerged; no Codex/second review run). **Verdict: NOT CLEAN — 0 High / 2 Medium / 0 Low.**

## Register resolution

- **SR-M17CC-03: CLOSED for its frozen two manifestations** — the correction is substantive (the vocal-origin snapshot preimage uses type-exact comparison on both §12 and recovery; malformed nested rational/origin objects are rejected before any `["num"]/["den"]` access through the appropriate typed contracts; the three new regressions exercise the intended adversaries rather than surrogates). The reported green gates remain corroborative only; CI `37152752470` independently confirmed on synthetic merge `f150d34` (exact `cbf599c` into unchanged base `d893d65`: focused backend 107 passed; full backend 3106 passed / 20 skipped; frontend 143/143; typecheck and production build green).
- The fresh adjacent scan found **two new defects** (below). SR-01/02/04/05 and all earlier closures stand.

## Frozen findings

1. **RR12-M17CC-01 — Medium — captured vocal child scalars are not total over SQLite storage classes.** The schema-8 child verifier compares captured vocal fields to the embedded JSON with `exact_projection_equal`, but that helper establishes only **same Python type + value**, not that the shared type is lawful authority — the child table's INTEGER-affinity fields can physically contain non-integral SQLite REAL values. The concrete surviving path (`source_start_sample = 48000.5`): raw-update the captured child to REAL `48000.5`; put JSON `48000.5` in the embedded vocal object; recompute `vocal_mapping_hash` from the malformed child preimage and update its embedded copy; recompute `segment_json`/hash, parent spec bytes/hash, and outer snapshot bytes/hash — the projection check passes (both values Python `float`), the mapping-hash closure passes (canonical JSON serializes the float), binding containment still passes (`48000.5` lies inside the lawful binding interval), and both §12 and recovery then execute `Fraction((row.source_start_sample - binding_start) * 1000, rate)` with a float first argument → raw `TypeError: both arguments should be Rational instances`. The reviewer independently reproduced the underlying SQLite/Python facts (an INTEGER-affinity column stores `48000.5` with `typeof(...) == 'real'`; the two-argument `Fraction` call raises that `TypeError`). The same missing captured-preimage structural certification also leaves `vocal_performance_origin_num/den` and `vocal_mapping_position` weaker than the predecessor vocal-mapping law: coherent REAL/noncanonical values can be snapshot-anchored and hashed without proving actual-integer/canonical-rational form. **Required narrow correction:** before any captured vocal preimage is hashed or used arithmetically, certify its persisted scalar law through ONE shared transport-neutral primitive — actual non-bool integers for the source coordinates/rate/position with their domains, and canonical reduced integer rational form for the vocal origin; §12 maps failure to its internal-invariant contract, recovery to `RECOVERY_CORRUPTION`. **Decisive adversary:** the coherent REAL `source_start_sample = 48000.5` rewrite — typed on both surfaces, never reaching `Fraction`; accompanied by a coherent noncanonical/REAL origin adversary.
2. **RR12-M17CC-02 — Medium — inner performance grammar accepts `schema_version: 2.0`.** Both independent grammar verifiers use ordinary numeric equality for the embedded performance schema discriminator (§12: `perf.get("schema_version") != 2`; recovery: the equivalent `== 1` / `!= 2` checks) — and Python considers `2.0 == 2` true. A coherent corruption survives: change only the embedded Performance block's `"schema_version": 2` to JSON `2.0`; apply the same value to the companion parent spec; recompute the parent canonical hash and outer snapshot bytes/hash; leave all children untouched — the parent/snapshot byte-equivalence checks pass, both grammar functions admit `2.0` as version 2, and no later child projection carries this discriminator to reject it; both §12 and recovery therefore certify a canonical JSON grammar value the writer cannot emit and that is not the frozen integer schema discriminator. This contrasts with the outer ShotRevision recovery classifier, which already explicitly requires an actual non-bool `int`. **Required correction:** make the inner Performance schema discriminator actual-integer/type-exact in the shared grammar law used by both surfaces; a coherent `2 → 2.0` parent+snapshot rewrite must produce typed refusal in §12 and recovery.

## Frozen disposition

**FIFTEENTH FIRST-PASS REVIEW COMPLETE — NOT CLEAN. SR-M17CC-03 is CLOSED for its frozen residual correction. New register `RR12-M17CC-01..02` frozen at 0H / 2M / 0L.** PR #26 remains draft, unmerged, unready. No Codex/second review, ready-mark, merge, or correction work has been initiated — the RR12 correction cycle awaits its gate.

---

# M17C-C RR12-M17CC-01..02 CORRECTION — 2026-10-04 — IMPLEMENTED

The commissioned correction (strictly the two frozen Medium findings) is complete. Correction heads: **`c7dbfa7`** (implementation + battery, committed first) then **`5691918`** (the four validator admissions, committed afterward per the gate discipline; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **RR12-01 — the captured vocal preimage's persisted scalar law.** ONE new transport-neutral primitive, `captured_vocal_preimage_error` (in `m17cc_capture_read`; both `sqlite3.Row` and mapping rows subscript), certifies the captured vocal preimage **BEFORE it is hashed, anchored into snapshot identity, or used in any exact arithmetic**: actual non-bool persisted integers for `source_start_sample`/`source_end_sample_exclusive`/`sample_rate_hz` with `0 <= start < end` and `rate > 0`; an actual mapping-position-domain integer for `vocal_mapping_position` (the ONE shared position primitive); and an actual canonical-reduced integer rational for the captured origin (the ONE shared temporal primitive — positive denominator, canonical zero, signed-64-bit persistence range). §12 consumes it at the START of `verify_mapping_hash_closure` (typed internal invariant, before `expected_mapping_hashes`); recovery consumes it at the top of `_verify_m17cc_child` (typed `RECOVERY_CORRUPTION`, before the mapping-hash closure and the §8.3 arithmetic). ONE law, both transports, no divergent history/recovery scalar grammar — the coherent REAL coordinate that previously passed every projection/hash law and then raised raw `TypeError` at `Fraction((float - int) * 1000, rate)` now refuses typed BEFORE arithmetic.
2. **RR12-02 — the inner Performance schema discriminator.** ONE new shared `is_actual_int_schema` law (actual non-bool integer exactly equal to the frozen version), consumed by BOTH §12's `_verify_embedded_grammar` and recovery's `_m17cc_embedded_grammar`; the explicit grammar-v1 diagnostic and the unknown-schema messages are preserved verbatim (only `!= 2` became `not is_actual_int_schema(..., 2)`) — the coherent parent+snapshot `2 → 2.0` rewrite (children untouched) now refuses typed on both surfaces instead of certifying a JSON float the canonical writer cannot emit.
3. **The decisive evidence, exactly as commissioned.** (a) The coherent SQLite REAL `source_start_sample = 48000.5`: the child column REAL (`typeof(...) == 'real'` demonstrated), the embedded vocal object carrying JSON `48000.5`, the mapping hash rebuilt from the malformed preimage, and the complete segment/spec/snapshot hash chain recomputed; the lawful dialogue-bound control proven green BEFORE the tamper; BOTH surfaces refuse through the shared scalar law BEFORE exact arithmetic — no raw `TypeError` escapes. (b) The coherent malformed-origin adversaries — the noncanonical integer rational `2/2` and the REAL scalar `0.5` (child columns + embedded values + hashes coherently rebuilt) — both surfaces typed-refuse through the shared captured-preimage law. (c) The coherent `2 → 2.0` parent+snapshot discriminator rewrite (canonical parent hash and outer snapshot bytes/hash refreshed, children lawful) — §12 refuses "declares unknown schema 2.0", recovery refuses `RECOVERY_CORRUPTION` "unknown schema". (d) Lawful dialogue-bound captured history remains green at both surfaces.
4. **No broadening.** Capture grammar, PF-02/PF-03 authority, readiness, mappings, migrations, storage schema, Generation behavior, and error vocabulary untouched. SR-M17CC-03 remains CLOSED; SR-01/02/04/05 and all prior FPR/RR closures re-proved green; no genuine regression demonstrated.

## Gates (first-run dispositions recorded exactly)

- RR12 battery (`tests/test_m17cc_rr12_corrections.py`) **5/5 on FIRST run** — no fixture corrections, no re-runs after edits.
- Directly endangered batteries first: history/recovery/capture/persist/roundtrip/migration + rr12 + sr **97/97**; prior storage-totality/type-exact + correction + live-seam batteries (RR5 mapping totality, RR7 isolation guard, RR8 pins, RR9/RR10 binding totality, FPR, RR/RR2–RR6, shot mapping, sr26, binding transitions) **126/126**.
- Committed-tree validators **21/21 green** (implementation `c7dbfa7` committed before the validator-admission commit `5691918`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3104 passed / 8 skipped / 0 failed in 48:40, exit 0** (collection 3112 = the prior 3107 + the 5-test battery — exact).
- **CI run `37182093494` on `5691918`: SUCCESS, attempt 1 — Backend 3111 passed / 20 skipped / 0 failed** (CI total 3131 = its prior 3126 + the 5-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No Codex/second review; no ready-mark; no merge; PR #26 remains draft, unmerged, unready. **This correction does not close RR12-M17CC-01..02** — the work stops here and holds for the **sixteenth fresh independent first-pass review** of the corrected executable head.

---

# M17C-C sixteenth first-pass review — 2026-10-04 — NOT CLEAN (register RR13-M17CC-01 FROZEN)

The sixteenth fresh independent first-pass review of executable head **`5691918e30370a19a6debeb85b88d6f9ea6dee5d`** is complete (implementation **`c7dbfa7a6d71ad452c6f77e45e0c1b21986b6ccc`**; record-only **`ff10c8c8487df31d451e2197da71459104cb1dd4`** above it; repository discipline verified correct — implementation first, four validator admissions second, documentation only third; PR #26 open, draft, unmerged; no Codex/second review run). **Verdict: NOT CLEAN — 0 High / 1 Medium / 0 Low.**

## Register resolution

- **RR12-M17CC-01: CLOSED** — `captured_vocal_preimage_error()` verified a genuine shared transport-neutral law rather than duplicated §12/recovery validation: it certifies before mapping-hash reconstruction or exact arithmetic the actual persisted integer sample coordinates and rate, `0 <= start < end`, positive rate, the lawful mapping-position domain, the actual integer vocal-origin pair, and canonical reduction/canonical zero with signed-64 persistence through the shared temporal primitive; §12 invokes it at the beginning of `verify_mapping_hash_closure()` and recovery at the beginning of `_verify_m17cc_child()`; the decisive REAL-coordinate proof verified substantive (the database actually stores `48000.5` as SQLite `real`; the embedded JSON and mapping/hash/snapshot closure coherently rebuilt; both consumers fail through their typed structural contracts before `Fraction` arithmetic; the `2/2` and REAL-origin cases independently cover the rational side); **no residual raw-arithmetic route found for these captured vocal scalars**.
- **RR12-M17CC-02: CLOSED** — `is_actual_int_schema()` correctly excludes `bool` and floating JSON numbers and is shared between the two inner Performance grammar consumers; a coherently rehashed `2 → 2.0` block no longer survives either surface; the explicit grammar-v1 refusal remains intact (the pre-anchor fence not weakened).
- **SR-M17CC-01..05 remain CLOSED; all earlier FPR/RR closures remain CLOSED.** CI `37182093494` independently corroborated on synthetic merge `dc0e65d` (exact carve head `5691918` into unchanged base `d893d65`: focused 107, backend 3111/20 with collection 3112, frontend 143/143 across 32 files, TypeScript clean, production build successful) — those gates do not exercise the new adversary.

## Frozen finding

- **RR13-M17CC-01 — Medium — the versioned Performance block does not enforce its own top-level key grammar: a coherently re-signed schema-2 document containing unknown top-level members is accepted by both §12 and recovery.** The writer defines the captured Performance value as exactly `{"schema_version": 2, "segments": [...]}` (`embedded_performance_value()` emits only those two members), and every nested grammar is otherwise deliberately closed (exact `EMBEDDED_SEGMENT_KEYS` per segment; exactly `{num, den}` nested rationals; the exact five-key vocal object; the actual-integer schema discriminator) — but neither top-level grammar verifier checks the Performance object's key set (§12's `_verify_embedded_grammar()` checks `schema_version`, nonempty `segments`, and the exact segment grammar, never `set(perf) == {"schema_version", "segments"}`; recovery's `_m17cc_embedded_grammar()` has the same omission). The valid coherent adversary against the current tree: start from a lawful schema-8 capture; add an arbitrary member to BOTH the companion spec and the snapshot Performance block (e.g. `"unexpected": {"meaning": "not emitted by the writer"}`); recompute `spec_json`/`spec_hash`/`snapshot_json`/`snapshot_hash`; leave every child row and segment unchanged — parent↔snapshot byte equality remains exact, the actual-integer schema check passes, every segment and nested object remains lawful, §12 accepts the history, recovery accepts the captured graph, and both silently ignore the extra captured field. The versioned grammar can therefore certify canonical history the canonical writer CANNOT produce, and an unrecognized captured member can be incorporated into immutable snapshot identity yet disappear semantically during reconstruction — the same integrity class that made `schema_version: 2.0` material (canonical bytes and hashes authenticate what was stored, but do not establish that what was stored belongs to the frozen grammar). No existing test challenges an additional top-level Performance member. **Required narrow correction:** define ONE shared top-level Performance grammar law — preferably the exact frozen key set `{"schema_version", "segments"}` — consumed by both §12 and recovery; preserve current diagnostic ordering where useful, especially the explicit grammar-v1 refusal; no writer, persistence, migration, capture, readiness, PF-02/PF-03, or Generation change indicated. **Decisive regression:** from a lawful schema-8 capture, add one unknown top-level key to both parent spec and snapshot Performance block, recompute canonical parent and snapshot hashes, leave children untouched, and prove §12 typed-refuses, recovery returns `RECOVERY_CORRUPTION`, and the ordinary schema-2 control remains green. A nested-extra-key surrogate is INSUFFICIENT (those grammars are already closed) — the target is specifically the Performance block itself.

## Frozen disposition

**SIXTEENTH FIRST-PASS REVIEW COMPLETE — NOT CLEAN. RR12-M17CC-01: CLOSED. RR12-M17CC-02: CLOSED. SR-M17CC-01..05 remain CLOSED. All earlier FPR/RR closures remain CLOSED. New frozen register: `RR13-M17CC-01` — 0H / 1M / 0L. No other suspected issue from this pass met the evidence threshold.** PR #26 remains draft, unmerged, unready. No Codex/second review, ready-mark, merge, or correction work has been initiated — the RR13 correction cycle awaits its gate.

---

# M17C-C RR13-M17CC-01 CORRECTION — 2026-10-04 — IMPLEMENTED

The commissioned correction (strictly the frozen Medium finding) is complete. Correction heads: **`97acdc3`** (implementation + battery, committed first) then **`dafa335`** (the four validator admissions, committed afterward per the gate discipline; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **The top-level Performance grammar is closed.** ONE shared structural law — `performance_block_key_error` over the frozen `PERFORMANCE_BLOCK_KEYS = {"schema_version", "segments"}` (exactly what the canonical writer emits; `embedded_performance_value` produces only those two members) — consumed by BOTH §12's `_verify_embedded_grammar()` and recovery's `_m17cc_embedded_grammar()`. No second key grammar.
2. **Diagnostic ordering and existing contracts preserved.** The law is placed AFTER the schema discriminator and the explicit grammar-v1/pre-anchor refusal (RR14-M17CC-01: this sentence originally — and overbroadly — said "a block missing frozen members now reports the precise missing members"; corrected in the RR14 proof-record-only cycle, the original text remaining in git history at `012ef5f`). The exact per-shape behavior: unknown top-level Performance members are reported through the shared `performance_block_key_error` law; when the block already carries a lawful actual-integer `schema_version: 2`, missing remaining frozen members such as `segments` are reported precisely by that key-set law; a missing or malformed `schema_version` fails FIRST, by design, through the existing schema-discriminator path and therefore retains that diagnostic (`unknown schema …`) rather than reaching the key-set law. A v1 block carrying the two frozen keys still reaches its v1 refusal, and a `2.0` block still reaches "unknown schema 2.0". The RR12 actual-integer discriminator and the existing exact segment / rational-object / vocal-object grammars are unchanged.
3. **The decisive adversary is top-level, exactly as commissioned.** From a lawful schema-8 capture: one unknown member (`"unexpected": {"meaning": "not emitted by the writer"}`) added directly to the Performance block in BOTH the companion `spec_json` and the snapshot `performance`, with `spec_hash`, `snapshot_json`, and `snapshot_hash` recomputed and every child and segment untouched — §12 returns its typed internal-corruption contract ("carries unknown top-level member(s) `['unexpected']` outside the frozen schema-2 grammar") and staged recovery returns typed `RECOVERY_CORRUPTION` with the same law's wording. The ordinary writer-produced schema-2 block remains green at both surfaces (the stored spec asserted to carry exactly the frozen key set, §12 200, recovery green), and the lawful control was proven green immediately before the tamper. No nested surrogate was used.
4. **Prior closures preserved.** The mandated re-runs green: the RR12 REAL/preimage-totality proofs and the `2 → 2.0` discriminator proof, the SR-03 nested-shape/type-exact proofs, and the directly endangered schema-8 history/recovery/capture/persistence batteries (below). RR12-M17CC-01/02 and SR-M17CC-01..05 remain CLOSED; no regression demonstrated.
5. **No broadening.** No writer format change, migration, storage schema change, capture/readiness change, PF-02/PF-03 authority change, Generation change, or new grammar version — this is validation of the already-frozen grammar, not a schema evolution.

## Gates (first-run dispositions recorded exactly)

- RR13 battery (`tests/test_m17cc_rr13_corrections.py`) **2/2 on FIRST run** — no fixture corrections, no re-runs after edits.
- Mandated re-runs + directly endangered suites first: RR12 + SR + RR13 + history/recovery/capture/persist/roundtrip/migration **99/99**; prior correction + live-seam batteries **126/126**.
- Committed-tree validators **21/21 green** (implementation `97acdc3` committed before the validator-admission commit `dafa335`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3106 passed / 8 skipped / 0 failed in 48:11, exit 0** (collection 3114 = the prior 3112 + the 2-test battery — exact).
- **CI run `37197931261` on `dafa335`: SUCCESS, attempt 1 — Backend 3113 passed / 20 skipped / 0 failed** (CI total 3133 = its prior 3131 + the 2-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No Codex/second review; no ready-mark; no merge; PR #26 remains draft, unmerged, unready. **This correction does not close RR13-M17CC-01** — the work stops here and holds for the **seventeenth fresh independent first-pass review** of the corrected executable head.

---

# M17C-C seventeenth first-pass review — 2026-10-04 — NOT CLEAN (register RR14-M17CC-01 FROZEN)

The seventeenth fresh independent first-pass review of executable head **`dafa335f5c98b42c3630fae9efd048cbc79fbf44`** is complete (implementation **`97acdc318d0a9f2fdf8f43a5eee4e372b04e7950`**; record-only **`012ef5f862ce99c9c098932ec9478e7e58118280`** above it; PR #26 open, draft, unmerged; no Codex/second review run). **Verdict: NOT CLEAN — 0 High / 0 Medium / 1 Low.**

## Register resolution

- **RR13-M17CC-01: substantively CLOSED** — `performance_block_key_error()` verified genuinely ONE shared top-level grammar law, consumed by both §12 and recovery, correctly placed after schema discrimination/v1 refusal; the coherent extra-top-level-member adversary fails typed on both surfaces while the canonical writer-produced control remains green. **No new product defect met the evidence threshold in the fresh adjacent scan.**
- RR12, SR-M17CC-01..05, and all earlier FPR/RR findings remain CLOSED. CI `37197931261` independently corroborated on synthetic merge `73d01a3` (exact carve head `dafa335` into unchanged base `d893d65`: focused 107, backend 3113/20 with collection 3114, frontend 143/143, typecheck clean, production build successful).

## Frozen finding

- **RR14-M17CC-01 — Low — the RR13 correction record overstates the missing-key diagnostics.** The product behavior is correct, but the pushed RR13 correction record claims, in substance, that "a block missing frozen members now reports the precise missing members." That is true for a schema-2 block missing `segments` (execution reaches `performance_block_key_error()`), but NOT true for a block missing `schema_version`: because the shared key-set law was intentionally placed after schema discrimination, `{"segments": [...]}` never reaches the key-set law and retains the pre-existing `unknown schema None` diagnostic. This is not a product correctness problem — the malformed block still fails typed on both surfaces, and the ordering is consistent with the commission's requirement to preserve schema/v1 diagnostic precedence. It is a **proof-record accuracy defect only**. **Required correction (proof/documentation only):** correct the RR13 record to say precisely that unknown top-level members are reported by the shared key-set law; that with a valid integer schema-2 discriminator, missing remaining frozen members such as `segments` are reported precisely; and that a missing or malformed `schema_version` continues to fail first through the existing schema-discriminator diagnostic BY DESIGN. No product source change indicated; a tiny diagnostic regression may be added if desired but is not necessary to establish the product law.

## Frozen disposition

**SEVENTEENTH FIRST-PASS REVIEW COMPLETE — NOT CLEAN. RR13-M17CC-01: CLOSED. RR12, SR-M17CC-01..05, and all earlier FPR/RR findings remain CLOSED. New register: `RR14-M17CC-01` — 0H / 0M / 1L.** PR #26 remains draft, unmerged, unready. No Codex/second review, ready-mark, merge, or correction work has been initiated — the RR14 proof-record correction awaits its gate.

---

# M17C-C RR14-M17CC-01 CORRECTION — proof-record-only — 2026-10-04 — IMPLEMENTED

The commissioned proof-record-only correction is complete. **No product, test, validator, migration, or workflow byte changed — this commit touches documentation only, and the executable review head remains `dafa335`.**

## Delivered (the commission exactly)

1. **The RR13 record's diagnostic claim is now exact.** The overbroad sentence ("a block missing frozen members now reports the precise missing members") is corrected IN PLACE in the RR13 correction record's point 2, with the correction identified inline and attributed to RR14 (the original text preserved in git history at `012ef5f` for exact comparison). The corrected statement gives the per-shape behavior precisely: unknown top-level Performance members are reported through the shared `performance_block_key_error` law; when the block already carries a lawful actual-integer `schema_version: 2`, missing remaining frozen members such as `segments` are reported precisely by that key-set law; and a missing or malformed `schema_version` fails FIRST, by design, through the existing schema-discriminator path, retaining that diagnostic rather than reaching the key-set law.
2. **The intentional ordering is documented as design, not defect.** The corrected record states the discriminator / grammar-v1 fence first, key-set law afterward ordering as deliberate (preserving the RR13 commission's diagnostic-precedence requirement) — the seventeenth review's observation is thereby explained, not obscured.
3. **No executable-tree change.** Per the commission, the optional diagnostic regression was NOT added (it would have turned a documentation correction into an executable-tree change), and the implementation was NOT altered to make the earlier prose true.
4. **Historical chain preserved.** The seventeenth review's Low finding, its reasoning, and this correction are all explicit: git history carries the original record at `012ef5f`, the seventeenth-review register section records the finding verbatim, and the current authoritative documentation no longer makes the overbroad claim.

## Closure evidence (per the commission)

This commission is proof-record-only: the only required verification is that the resulting commit touches documentation only and the tracked tree is clean — no backend/frontend/validator/CI rerun is required for closure evidence (the executable tree is unchanged from the CI-corroborated `37197931261` head).

## Fences honored

No Codex/second review; no ready-mark; no merge; PR #26 remains draft, unmerged, unready. **RR14-M17CC-01 is not closed merely by this edit** — the work stops here and holds for the **eighteenth fresh independent first-pass review** (the executable review head remains `dafa335`; this commit is record-only above it).

---

# M17C-C independent second review (rerun) — reconciled — register ISR2-M17CC-01..03 FROZEN — 2026-10-04

The independent second-review rerun against exact executable target **`dafa335f5c98b42c3630fae9efd048cbc79fbf44`** (baseline `8a92bc6d6fd3bb38a1809e6cb54d1ec33998078e`; the reviewer package matched its manifest SHA-256 and byte count) returned **NOT CLEAN — 0 High / 2 Medium / 1 Low**, and the user's reconciliation against `dafa335` confirms **all three findings**. The reviewer's independence statement is accepted: Phase A was frozen before any correction-oriented M17C-C tests were inspected; the one incidental exposure (GitHub run metadata revealing the target head's RR13-carve commit message) occurred after the Phase-A freeze and did not affect the findings. This rerun follows the **eighteenth first-pass CLEAN state** (the RR14 proof-record correction `7a5f897` stands record-only above `dafa335`); per the reconciliation, the eighteenth CLEAN disposition remains historically correct — these are three NEW independent-second-review findings that do not reopen RR14, RR13, RR12, SR-M17CC, or any earlier FPR/RR register. PR #26 remains open, draft, unmerged (tip `7a5f897`, executable review target `dafa335`). CI `37197931261` on the exact target was independently confirmed green (focused 107; backend 3113/20/0 with collection 3114; frontend 143/143; tsc; build) — none of the three adversaries is represented in the current suite, so the green gates do not falsify the findings.

## Frozen findings (each CONFIRMED at reconciliation)

1. **ISR2-M17CC-01 — Medium — recovery does not authenticate the outer schema-8 ShotRevision snapshot.** `_verify_m17cc_capture_state` classifies every ShotRevision from only `id`, `shot_id`, and `snapshot_json` — it never reads `shot_revisions.snapshot_hash` and never requires the persisted `snapshot_json` bytes to equal their canonical serialization; the schema-8 pass then authenticates only the embedded Performance closure. The public historical path (`api/continuity.py`) recomputes BOTH the canonical snapshot JSON and `snapshot_hash` and fails closed — a direct history/recovery authority divergence. The reconciliation verified there is no hidden generic shield: the M13 recovery path authenticates outer canonical bytes/hash only for revisions participating in the M13 production-world companion closure, and a schema-8 revision wrapping lawful predecessor shapes without that M13 companion path reaches M17C-C recovery unauthenticated. The existing `snapshot_block` matrix adversary recomputes `snapshot_hash`, so it isolates Performance-block-vs-parent disagreement rather than testing outer self-authentication. **Correction boundary (as frozen):** in the schema-8 recovery path, retrieve `snapshot_hash` with `snapshot_json` and require `canonical_json_str(decoded) == persisted snapshot_json` AND `canonical_hash(decoded) == persisted snapshot_hash` before schema-8 interpretation — restricted to schema-8 revisions to preserve predecessor recovery posture. **Decisive evidence:** a canonical schema-8 `snapshot_json` with one unrelated predecessor field changed but a stale hash, and semantically identical but noncanonical snapshot bytes — both the direct verifier and full restore refuse typed.
2. **ISR2-M17CC-02 — Medium — recovery does not verify the physical schema of the three M17C-C tables.** The verifier's strong `_verify_table_schema` primitive (exact columns/types/nullability/PK ordinals, FK multiset, CHECK multiset, explicit indexes, PK/UNIQUE autoindexes) is used by PF-03 (`_PF03_CONTRACTS`) and PF-02 (`_verify_spsm_schema`) but NOT for `shot_revision_performance_specs`, `shot_revision_performance_segments`, or `generation_performance_inputs` — those get table-presence checks plus semantic row traversal. On an otherwise lawful head-0023 database with EMPTY M17C-C tables, rebuilding a table without `ck_srpfs_schema`, or with a weakened PK/FK/CHECK, or dropping `ix_srpss_pr` leaves `quick_check`, `foreign_key_check`, the presence test, and the Blob-FK inventory all green — recovery can certify a physical schema the migration never creates, installing weakened successor constraints that future durable authority would mechanically forbid. **Correction boundary (as frozen):** add exact physical contracts for all three M17C-C tables and call the existing verifier before semantic traversal, with SEPARATE 0022 and 0023 contracts for the child table (0023 legitimately adds the vocal mapping preimage columns and constraints). **Decisive evidence:** on empty lawful 0023 state, independently remove one CHECK, one non-Blob FK, and the `ix_srpss_pr` index in separate cases — each must fail recovery before row traversal; include an equivalent 0022 contract test.
3. **ISR2-M17CC-03 — Low — historical inspection exposes unverified Blob `size_bytes`.** §12's `_verify_one_child` loads `blobs.size_bytes` and `_verified_payload_bytes` rehashes the physical payload, but nothing proves `size_bytes` is an actual nonnegative integer or equals `len(payload_bytes)` — the answer exposes both the verified bytes and the unchecked stored size. After a lawful capture, `size_bytes + 1` (bytes and hash untouched) yields a successful §12 response attesting contradictory retained-closure data, while backup/recovery liveness DOES compare the physical byte count — a narrow history/recovery asymmetry (payload identity itself stays authenticated, hence Low). **Correction boundary (as frozen):** validate that `size_bytes` is an actual nonnegative integer and equals the physically read byte count, failing through the existing historical invariant/corruption contract rather than normalizing. **Decisive evidence:** the `size_bytes` mutation with bytes/hash intact must make §12 fail; a REAL/BLOB storage-class adversary for `size_bytes` closes the representation boundary; lawful payload history stays green.

## Open questions (accepted as NOT promoted)

The reviewer declined to promote (a) a `generation_performance_inputs.derived_input_hash` recompute law — the reviewer-safe contract establishes no frozen M17C-C preimage that recovery is already required to recompute (M17C-D owns the writer/sampler semantics), and (b) the 0023 populated-upgrade refusal — an explicit migration posture, not an independently demonstrated defect. The reconciliation agrees with both non-promotions. The reviewer's challenged-with-no-issue list (coherent single-read capture, lawful non-ready vs corruption, dense ordering/channel conflict, schema-8 wrapping, companion persistence/convergence, mapping-hash anchoring, current-state isolation, PR/VP/binding identity + exact arithmetic, project/subject coherence, head dispatch/predecessor ordering, Blob-FK inventory, GPI tie-back + physical rehash, downgrade behavior, backup/restore closure, the Generation fence, observation readiness, storage-class hardening) stands as part of the frozen report.

## Frozen disposition

**INDEPENDENT SECOND REVIEW (RERUN) RECONCILED — NOT CLEAN. Register `ISR2-M17CC-01..03` frozen — CONFIRMED — 0H / 2M / 1L.** The eighteenth first-pass CLEAN disposition remains historically correct; these are three NEW findings that reopen nothing. PR #26 remains draft, unmerged, unready. **No correction has started — the `ISR2-M17CC-01..03` correction cycle awaits its commission.**

---

# M17C-C ISR2-M17CC-01..03 CORRECTION — 2026-10-04 — IMPLEMENTED

The commissioned correction cycle is complete. Correction heads: **`cb1a90a`** (implementation + battery, committed first) then **`86717fe`** (the four validator admissions, committed afterward; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **ISR2-01 — the outer schema-8 ShotRevision envelope is authenticated in recovery.** The schema-8 pass in `_verify_m17cc_capture_state` now reads `snapshot_hash` alongside `snapshot_json` and requires `canonical_json_str(decoded) == persisted snapshot_json` AND `canonical_hash(decoded) == persisted snapshot_hash` BEFORE any M17C-C closure interpretation — the same pair the public historical path proves. A canonical snapshot with one predecessor field coherently rewritten but a stale hash, or semantically identical noncanonical bytes, no longer certifies. Predecessor (<8) recovery posture deliberately unchanged — the law is restricted to the schema-8 successor case exactly as commissioned.
2. **ISR2-02 — frozen physical contracts for all three M17C-C tables, through the existing machinery.** `_srpfs_contract` / `_srpss_contract(successor=…)` / `_gpi_contract` (frozen from PRAGMA + sqlite_master evidence of genuinely migrated 0022 and 0023 databases, probed by real alembic upgrades) run through the SAME `_verify_table_schema` primitive inside the existing physical-schema phase — BEFORE any semantic row traversal — with SEPARATE lawful segment contracts per head (0023 adds the captured mapping-preimage columns and their constraints). **Disclosed enabling change:** the ORM model's segment `CheckConstraint` declarations were REORDERED to the migration's exact declaration order, because the two engines stored the same constraint SET in different DDL orders and one frozen ordered contract must hold across both (the PF-03 determinism precedent; no schema semantics change, no migration touched, no head change). A staged successor-head database with a weakened CHECK / FK / index / PK shape now refuses at the physical boundary even with EMPTY tables, where `quick_check`, `foreign_key_check`, presence, and row semantics all stay green.
3. **ISR2-03 — §12's retained Blob size is part of the verified closure.** After `_verified_payload_bytes` physically reads and content-address-verifies the payload, `blobs.size_bytes` must be an actual nonnegative integer exactly equal to the physical byte count before either is exposed as historical truth — failing through the existing typed internal-invariant contract, never normalizing. The bytes/hash verification and historical error contract are preserved; recovery/backup liveness already proved the same equality, closing the asymmetry.
4. **The two frozen non-findings stay out of scope** — no canonical GPI `derived_input_hash` preimage was invented, and the populated-0022→0023 migration-refusal policy is untouched. No unrelated redesign; the predecessor recovery chain is unchanged beyond the successor tables' contracts.

## The decisive evidence (the commission's adversaries, 8/8 on FIRST run)

The two outer adversaries — a canonical `snapshot_json` with one predecessor field changed but a stale hash, and semantically identical noncanonical bytes with a semantics-matching hash (Performance block and every companion row untouched) — are refused by BOTH the direct M17C recovery verifier AND the full restore, typed. The three empty-0023 physical adversaries (the `ck_srpfs_schema` expression weakened in place; `fk_srpss_pr` RESTRICT→CASCADE with the migration's index recreated so only the FK diverges; `ix_srpss_pr` dropped) each refuse at the physical boundary with the UNDAMAGED empty state proven green first; the GENUINE 0022 shape (a real alembic 0021→0022 upgrade of a reshaped staged database) passes the 0022 contracts green and then refuses the same CHECK damage at 0022. The two retained-size adversaries (off-by-one integer; a genuine SQLite REAL with `typeof` proven) make §12 typed-refuse, with the lawful control asserting the exposed `size_bytes` equals the decoded payload byte count immediately before the tamper.

## Gates (first-run dispositions recorded exactly)

- ISR2 battery (`tests/test_m17cc_isr2_corrections.py`) **8/8 on FIRST run** — no fixture corrections, no re-runs after edits (one disclosed intermediate correction DURING development, before any battery run: the first contract draft transcribed the segments CHECK declaration order differently from the probed migration truth and was refused by the lawful recovery battery — the probe-driven reorder is the frozen form above).
- Directly endangered suites first: recovery/roundtrip/migration/history/capture/persist + isr2 **87/87** (the real 0021→0022 and 0022→0023 upgrade/round-trip batteries now exercise the new physical contracts on genuinely migrated shapes); prior correction + live-seam batteries **122/122**.
- Committed-tree validators **21/21 green** (implementation `cb1a90a` committed before the validator-admission commit `86717fe`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3114 passed / 8 skipped / 0 failed in 49:34, exit 0** (collection 3122 = the prior 3114 + the 8-test battery — exact).
- **CI run `37218609448` on `86717fe`: SUCCESS, attempt 1 — Backend 3121 passed / 20 skipped / 0 failed** (CI total 3141 = its prior 3133 + the 8-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No ready-mark; no merge; no publication; PR #26 remains draft, unmerged, unready. **The ISR2 findings are NOT closed by this implementation or the green gates** — they remain open until a fresh independent review verifies them. The work stops here and holds for that review of the corrected executable head (`86717fe`).

---

# M17C-C nineteenth fresh independent review — 2026-10-04 — NOT CLEAN (register RR15-M17CC-01..02 FROZEN)

The nineteenth fresh independent review of executable head **`86717fe1ad6436334dce52562f5ea2bf9fcbfb6d`** is complete (implementation **`cb1a90aeba05db4354e834a3482c877e3cf3278f`** committed first; record **`115a7af260276cb7cd8f690f13c9854c6eea7f07`** confirmed documentation-only above it; the validator carve changes only the four expected boundary validators; PR #26 open, draft, unmerged; no Codex/second review at this state). **Verdict: NOT CLEAN — 0 High / 1 Medium / 1 Low.**

## Register resolution

- **ISR2-M17CC-01, -02, -03: CLOSED for their frozen second-review adversaries.** The three commissioned corrections verified substantive: the stale-hash schema-8 document and noncanonical schema-8 bytes refuse on both commissioned surfaces; the damaged CHECK, weakened non-Blob FK, missing `ix_srpss_pr`, and the genuine 0022/0023 contract separation are substantively fixed; §12 verifies an actual nonnegative integer `size_bytes` equal to the physical byte count after content-address verification with **no residual seam (ISR2-03 fully closed)**. The two accepted non-findings remain appropriately untouched. No earlier RR/SR/FPR register is reopened.
- CI `37218609448` independently corroborated on synthetic merge `c0ef407` (exact executable head `86717fe` into unchanged base `d893d65`: focused 107, collection 3122, backend 3121/20/0, frontend 143/143 across 32 files, TypeScript clean, production build successful) — those gates cover neither newly identified adversary.

## Frozen findings

1. **RR15-M17CC-01 — Medium — outer authentication can be bypassed by corrupting the schema discriminator downward.** The ISR2-01 check correctly authenticates canonical bytes and `snapshot_hash` for revisions the first classification pass has already decided are schema 8 — but the verifier TRUSTS the unauthenticated `schema_version` BEFORE deciding whether the authentication law applies (decode → read `schema_version` from the unverified document → `schema < 8` ⇒ require zero M17C-C companions and SKIP schema-8 envelope authentication; `schema == 8` ⇒ later prove canonical bytes + hash). The coherent evasion from a lawful schema-8 capture: change `snapshot_json.schema_version` from 8 to an older legal value (e.g. 1); remove that revision's specs/segments companion rows; leave `snapshot_hash` stale; leave the physical successor schemas and unrelated authority untouched — the classifier sees a legal `schema < 8` revision with zero companions, satisfies the total-classification branch, never enters `schema8_ids`, and the new authentication block is never reached. No DDL weakening or Python type-equality exploitation — a direct consequence of using the mutable/unauthenticated field to decide whether its containing immutable document gets authenticated. The public historical path still generically verifies the persisted bytes/hash, so the history/recovery divergence remains reachable; on a Shot without an independently applicable predecessor companion verifier authenticating the outer snapshot, recovery can certify the stale-hash document. **Required narrow correction:** at successor heads 0022/0023, authenticate the canonical bytes and `snapshot_hash` of EVERY ShotRevision before trusting its schema discriminator for M17C-C classification (the scope stays the M17C-C successor verifier — historical predecessor heads unchanged; classification consumes an authenticated snapshot, never decides authentication eligibility from an unauthenticated one). **Decisive regression:** a lawful schema-8 capture with the discriminator rewritten to a lawful older version, only its M17C-C companion closure removed, `snapshot_hash` left stale — the direct verifier typed-refuses on outer authentication AND the full restore typed-refuses; AND lawful mixed successor databases containing genuine historical schema<8 revisions remain green (authenticating old revisions INSIDE a 0022/0023 database must not be confused with changing support for restoring an actual older alembic head).
2. **RR15-M17CC-02 — Low — the "exact" physical contract does not verify `ix_srpss_pr`'s indexed column.** `_verify_table_schema` records explicit indexes as name → (unique, origin, partial): the segment contract proves an index NAMED `ix_srpss_pr` exists, non-unique, explicit, non-partial — but never inspects `PRAGMA index_info(ix_srpss_pr)`. The predecessor PF-02 verifier already demonstrates the necessary extra step (`_verify_spsm_schema`'s `ix_cols != ["performance_revision_id"]` check); no corresponding check exists for `ix_srpss_pr`. `DROP INDEX ix_srpss_pr; CREATE INDEX ix_srpss_pr ON shot_revision_performance_segments(subject_id);` passes the new physical contract (index_list still reports the exact expected tuple under the exact expected name) — recovery certifies a physical index different from the one migrations 0022/0023 create. **Low** because the index is non-unique and the wrong-column substitution has no demonstrated durable-authority bypass (it violates the claimed exact physical-schema proof and can affect query behavior/performance; ISR2-02's material constraint/FK integrity closure stands). **Required narrow correction:** extend the shared schema-contract representation with explicit-index column sequences, or add a segment-table wrapper analogous to `_verify_spsm_schema` — both 0022 and 0023 must require `ix_srpss_pr → ["performance_revision_id"]`. **Decisive adversary:** the same-name, same-flags index recreated over `subject_id` must be refused.

## Frozen disposition

**NINETEENTH FRESH INDEPENDENT REVIEW COMPLETE — NOT CLEAN. The frozen second-review adversaries for ISR2-M17CC-01..03 are closed, and ISR2-M17CC-03 is fully closed. No earlier RR/SR/FPR register is reopened. New register: `RR15-M17CC-01..02` — 0H / 1M / 1L.** PR #26 remains draft, unmerged, unready. No further second review, ready-mark, merge, publication, or correction work is authorized at this state. The next step is the documentation-only recording of this frozen register; the RR15 correction cycle awaits its commission.

---

# M17C-C RR15-M17CC-01..02 CORRECTION — 2026-10-05 — IMPLEMENTED

The commissioned correction cycle is complete. Correction heads: **`0985bd2`** (implementation + battery, committed first) then **`34e9300`** (the four validator admissions, committed afterward; all validators ran against the committed carve-inclusive tree).

## Delivered (the commission exactly)

1. **RR15-01 — authenticate before classification.** The classification pass in `_verify_m17cc_capture_state` now reads `snapshot_hash` alongside `snapshot_json` and authenticates **EVERY** ShotRevision envelope — canonical persisted bytes, then hash — **BEFORE** the schema discriminator is trusted for M17C-C classification, exactly the commissioned ordering (load → decode → prove canonical → prove hash → only now trust `schema_version` → classify → closure laws). The discriminator corrupted downward no longer exempts its own document from authentication. The redundant phase-2 re-authentication block is removed (every envelope is authenticated once, up front), and the messages generalize from "schema-8 snapshot…" to "snapshot…" — **a disclosed test-expectation update:** the two ISR2-01 fragments in `tests/test_m17cc_isr2_corrections.py` were updated to the generalized wording, and the ISR2-01 stale-hash and noncanonical-byte adversaries still refuse (now at classification time). This is a successor-head M17C-C verifier law only; restoring an actual pre-0022 alembic head is an unchanged, separate concern.
2. **RR15-02 — index column identity.** The shared `_verify_table_schema` gained an OPTIONAL `index_columns` contract mapping (exact ordered `PRAGMA index_info` sequences per named explicit index) — mechanically general, and contracts that omit the key keep byte-identical behavior (the frozen predecessor PF-03 contracts untouched; PF-02 keeps its own wrapper check — neither opportunistically rewritten, per the commission). Both the 0022 and 0023 segment contracts now require `ix_srpss_pr → ["performance_revision_id"]`, so the same-name, same-flags index rebuilt over a different column no longer certifies.
3. **The decisive proofs, exactly as commissioned.** The discriminator-downgrade adversary (from a lawful schema-8 capture: only the embedded outer discriminator `8 → 7` rewritten with canonical bytes persisted, precisely that revision's M17C-C companion closure removed, `snapshot_hash` left stale) is refused by the direct recovery verifier through outer authentication BEFORE classification can legitimize the downgraded shape, and the full staged restore independently refuses. The **mixed-successor control** — one lawful head-0023 database containing a GENUINE historical schema<8 revision (captured before any performance mappings existed) alongside a lawful schema-8 revision — remains green. The wrong-column `ix_srpss_pr` adversary is refused at the physical boundary at BOTH heads (0023 with the undamaged state green first; 0022 from a genuine alembic 0021→0022 upgrade proving the correct index green first), distinguishing name+flags+wrong-column from ISR2-02's absence law.
4. **Preservation / no broadening.** ISR2-M17CC-01/02/03 frozen adversaries re-proven green (the ISR2 battery with the two generalized fragments); RR14 and all earlier closures stand; the GPI `derived_input_hash` non-finding and the populated-0022→0023 refusal untouched; no capture/readiness/history grammar, Generation behavior, migration-head semantics, PF-02/PF-03 authority, or unrelated DDL change.

## Gates (first-run dispositions recorded exactly, in the commissioned order)

- RR15 battery (`tests/test_m17cc_rr15_corrections.py`) **4/4 on FIRST run** (run together with the ISR2 battery — **12/12**, the ISR2 fragments' generalization green on first run after the disclosed edit).
- Directly endangered recovery/full-restore/schema-contract + M17C-C recovery/round-trip/migration/backup batteries **100/100**.
- ISR2 correction battery **8/8** (see above).
- Predecessor PF-02/PF-03 schema-recovery batteries (the shared `_verify_table_schema` enhancement proven behavior-identical) **56/56**; prior correction + live-seam batteries **45/45**.
- Committed-tree validators **21/21 green** (implementation `0985bd2` committed before the validator-admission commit `34e9300`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3118 passed / 8 skipped / 0 failed in 45:51, exit 0** (collection 3126 = the prior 3122 + the 4-test battery — exact).
- **CI run `37265367335` on `34e9300`: SUCCESS, attempt 1 — Backend 3125 passed / 20 skipped / 0 failed** (CI total 3145 = its prior 3141 + the 4-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No second-review rerun; no ready-mark; no merge; no publication; PR #26 remains draft, unmerged, unready. **RR15-M17CC-01/02 remain open until a fresh independent review closes them** — the work stops here and holds for the **twentieth fresh independent first-pass review** of the corrected executable head (`34e9300`).

---

# M17C-C twentieth fresh independent review — 2026-10-05 — NOT CLEAN (register RR16-M17CC-01 FROZEN)

The twentieth fresh independent review of executable head **`34e930020a0392d8c4b2b26435f13296c527f0a2`** is complete (implementation **`0985bd2a68efaa0910cb2a42592cff62aee6c80c`** committed first; **`5b2fb875638b2150ec6d651c6bca21a66916fae4`** confirmed documentation-only above it; the validator carve changes only the expected four boundary validators; PR #26 open, draft, unmerged; no second-review rerun at this state). **Verdict: NOT CLEAN — 0 High / 1 Medium / 0 Low.**

## Register resolution

- **RR15-M17CC-01: CLOSED** — `_verify_m17cc_capture_state()` authenticates every ShotRevision envelope before using the embedded discriminator (decode → object check → canonical persisted bytes → snapshot_hash → schema_version → classification); the later schema law independently requires an actual non-bool integer in `[1,8]`, so cross-type discriminator aliases do not reopen the bypass; the `8 → 7` companion-removal stale-hash adversary is genuinely stopped BEFORE it can enter the old-schema branch; the mixed-successor positive control is meaningful (a genuine historical schema<8 revision and a schema-8 revision coexist at head 0023); **no surviving downward-classification bypass found**.
- **RR15-M17CC-02: CLOSED** — the shared physical-schema verifier optionally proves exact ordered explicit-index columns through `PRAGMA index_info`; both 0022/0023 segment contracts require `ix_srpss_pr → ["performance_revision_id"]`; a same-name same-flags index over `subject_id` no longer certifies; the 0022 proof uses an actual alembic 0021→0022 upgrade and proves the lawful shape green first (not an ORM-only surrogate). Differences such as DESC/collation spelling were examined and NOT promoted (no durable-authority effect demonstrated; the frozen defect was specifically column identity).
- **ISR2-M17CC-01..03 remain CLOSED; all earlier RR/SR/FPR findings remain CLOSED.** CI `37265367335` independently corroborated on synthetic merge `776c26a` (exact executable head `34e9300` over unchanged base `d893d65`: focused 107, collection 3126, backend 3125/20/0, frontend 143/143 across 32 files, TypeScript clean, production build successful) — those gates do not exercise the newly identified predecessor raw-exception shapes.

## Frozen finding

- **RR16-M17CC-01 — Medium — the full successor recovery chain is still not total over malformed ShotRevision snapshot JSON because the M16 predecessor verifier parses every ShotRevision before M17C-C gets control.** The corrected M17C-C verifier itself handles malformed decode correctly (`json.loads` inside `except (ValueError, TypeError)` — `UnicodeDecodeError` is a `ValueError` subclass, so an invalid-UTF-8 BLOB is normalized correctly IF M17C-C is reached). The problem is predecessor ordering: for heads 0022/0023, successor recovery runs M15 → M16 → M17A → M17B → M17C-C, and M16 traverses EVERY ShotRevision with `snap = json.loads(snapshot_json); if snap.get("schema_version") == 7 or ...` with NO decode or container guard — its companion sweep repeats the same unguarded pattern. Two direct uncontrolled paths: malformed JSON / invalid-UTF-8 BLOB → raw `JSONDecodeError` / `UnicodeDecodeError`; valid JSON with a non-object top level such as `[]` → raw `AttributeError` at `.get()`. Because M16 runs before the new M17C-C universal envelope authentication, the full backup/restore path can terminate through those raw Python exceptions rather than the typed recovery-corruption contract. There is no later normalization — the successor orchestration calls M16 directly, and the outer backup/restore operation catches `BaseException` only to delete staging state and then re-raises it. This is a genuine successor recovery-totality defect, not a failure of the RR15 implementation itself — the M17C-C recovery scope explicitly extends the predecessor verifier chain rather than replacing it, so predecessor failure ordering remains part of the effective recovery boundary. **Severity Medium** (a malformed durable ShotRevision is refused rather than silently accepted, but an integrity boundary exposes uncontrolled runtime exceptions instead of deterministic recovery corruption — the established Medium totality class of this review arc). **Required narrow correction (as framed):** either make M16's ShotRevision traversal consume a shared total outer-snapshot parser, or establish that total parser before predecessor semantic dispatch — without weakening predecessor-first semantic verification or duplicating a new ShotRevision grammar. **Decisive closing evidence:** on a lawful head-0023 database containing a genuine historical schema<8 ShotRevision plus lawful successor state: (1) replace that old revision's `snapshot_json` with malformed JSON — or an actual invalid-UTF-8 SQLite BLOB — updating the backup DB/manifest identity as necessary; (2) separately persist a valid non-object JSON value such as `[]` (a coherent hash isolating the object-shape law if useful); then prove the direct M17C-C verifier terminates typed, the full staged restore terminates typed as recovery corruption — NEVER `JSONDecodeError`, `UnicodeDecodeError`, or `AttributeError` — and a lawful mixed-successor database remains green.

## Frozen disposition

**TWENTIETH FRESH INDEPENDENT REVIEW COMPLETE — NOT CLEAN. RR15-M17CC-01: CLOSED. RR15-M17CC-02: CLOSED. ISR2-M17CC-01..03 remain CLOSED. All earlier RR/SR/FPR findings remain CLOSED. New register: `RR16-M17CC-01` — 0H / 1M / 0L. No other issue from this pass met the evidence threshold.** PR #26 remains draft, unmerged, unready. No second-review rerun, ready-mark, merge, publication, or correction work has been initiated — the RR16 correction cycle awaits its commission.

---

# M17C-C RR16-M17CC-01 CORRECTION — 2026-10-05 — IMPLEMENTED

The commissioned correction cycle is complete. Correction heads: **`2e7dde7`** (implementation + battery, committed first) then **`eb1bfd0`** (the validator admissions — two commits: the boundary-allowlist/regex/source-fit admissions, then the follow-up admitting the new module to the third rule, the security-slice backend-change list, which the first refused validator run disclosed; all validators ran against the committed admission-inclusive tree).

## Delivered (the commission exactly)

1. **ONE shared recovery-side outer-ShotRevision parser.** `soloring.recovery.outer_snapshot.load_outer_snapshot` carries exactly the parse/shape boundary: it accepts the persisted text/bytes forms the recovery contract supports, converts EVERY decode failure into the typed `RecoveryCorruption` contract (the `ValueError` catch covers `JSONDecodeError` and `UnicodeDecodeError` — so malformed JSON and an invalid-UTF-8 SQLite BLOB are normalized; `TypeError` covers non-text/non-bytes storage classes), and requires a JSON OBJECT before any consumer calls `.get()` on the result. No semantic interpretation lives there — schema discrimination, canonical-bytes/hash authentication, and closure laws stay with the owning verifier.
2. **M16 consumes the shared boundary for ALL of its ShotRevision snapshot reads** — the global history enumeration, the intra-shot companion sweep, and the proposal source-revision lookup. No residual bare `json.loads(snapshot_json)` over ShotRevision history remains in the M16 verifier (its remaining `json.loads` sites parse proposal/canonical-pair/review documents — already guarded where applicable — and are outside this commission's scope). Predecessor-first verification and the M16-before-M17C ordering are unchanged; the M17C-C classification keeps its own guarded decode and its RR15 authenticate-before-classification law untouched; existing valid historical snapshots are behavior-identical.
3. **No broadening:** no ShotRevision schema redesign, migration work, capture/history semantics, RR15 authentication change, M17A/B/C grammar change, or generic JSON refactoring.
4. **The decisive battery, exactly the frozen shapes on a lawful head-0023 mixed-successor database** (a GENUINE schema<8 revision captured before any mappings, plus lawful schema-8 state): the green control verifies green on the direct M17C-C verifier AND restores successfully through the full predecessor chain; the three malformed shapes on the old revision — malformed JSON and an actual invalid-UTF-8 BLOB (`typeof` proven `blob`; stale identity explicitly intentional, no canonical form existing to recompute), and valid non-object `[]` with a COHERENT hash isolating the object-shape law — each refuse through the typed contract on BOTH the direct M17C-C verifier and the full staged restore, with the backup manifest rehashed so the restore reaches semantic verification rather than failing artifact authentication first. The typed classes themselves are the never-raw proof: the direct chain's `SoloRingError` carrying `RECOVERY_CORRUPTION` and the restore chain's `RecoveryCorruption` are neither `JSONDecodeError`, `UnicodeDecodeError`, nor `AttributeError`.

## Gates (first-run dispositions recorded exactly, in the commissioned order)

- RR16 battery **first run 1/4, disclosed**: the two failing expectations were MY test's exception-class assumptions, not product defects — the direct M17C-C leg's typed contract is `SoloRingError` carrying the `RECOVERY_CORRUPTION` code (not M16's `RecoveryCorruption` class), and `RecoveryCorruption` exposes `str()` rather than `.message`; the product was typed throughout. After the two test-expectation corrections (no product or fixture change): **4/4**.
- Directly endangered M16 recovery + M17C-C recovery/full-restore/round-trip/migration/backup + rr16 **71/71**; RR15 + ISR2 batteries **12/12**; prior correction + live-seam + predecessor recovery/schema batteries **94/94**.
- Committed-tree validators: the FIRST run after the implementation commit **refused the new module (5 validator FAILs, disclosed)** — the boundary gates working as designed against an unadmitted new source file; the admission commits admit exactly `server/soloring/recovery/outer_snapshot.py` (both hygiene/next-security allowlists, the m16/m14 regexes, the m14 source-fit `REVIEWED_SUCCESSOR_PATHS`, and the security-slice backend-change rule) plus the RR16 battery carves; final **21/21 green**.
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3122 passed / 8 skipped / 0 failed in 46:40, exit 0** (collection 3130 = the prior 3126 + the 4-test battery — exact).
- **CI run `37275398955` on `eb1bfd0`: SUCCESS, attempt 1 — Backend 3129 passed / 20 skipped / 0 failed** (CI total 3149 = its prior 3145 + the 4-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No second-review rerun; no ready-mark; no merge; no publication; PR #26 remains draft, unmerged, unready. **RR16-M17CC-01 remains OPEN until a fresh independent review closes it** — the work stops here and holds for the **twenty-first fresh independent first-pass review** of the corrected executable head (`eb1bfd0`).

---

# M17C-C twenty-first fresh independent review — 2026-10-05 — NOT CLEAN (register RR17-M17CC-01 FROZEN)

The twenty-first fresh independent review of executable head **`eb1bfd032ea663881607cdf451f19947f57a331c`** is complete (implementation **`2e7dde778a501400faeda18cfd969bddd136d2de`** committed first; the three subsequent commits `1096218 → 7dc8e48 → eb1bfd0` are validator-admission changes only; **`733a8bfa9cb2d64945dbea88ffd9dd579ce807b9`** documentation-only above the executable head; PR #26 open, draft, unmerged; no second-review rerun at this state). **Verdict: NOT CLEAN — 0 High / 1 Medium / 0 Low.**

## Register resolution

- **RR16-M17CC-01: CLOSED** — the correction verified substantive: `load_outer_snapshot()` is a genuine shared parse/container boundary, not a duplicate semantic grammar (malformed JSON, invalid-UTF-8 BLOBs, unsupported storage classes, and non-object JSON all normalize to `RecoveryCorruption`, while schema interpretation and canonical/hash authority stay with the owning verifiers); all three M16 reads identified by the twentieth review consume the boundary with **no remaining bare `json.loads(snapshot_json)` over ShotRevision history in M16**; the three decisive malformed shapes are real (the full restore reaches semantic verification because the manifest is rehashed — no masking by backup authentication); the lawful mixed-successor control is meaningful; the disclosed first-run test failures were expectation errors rather than product failures (the typed product behavior was already present). The exact frozen RR16 defect is closed.
- **RR15-M17CC-01/02 remain CLOSED; ISR2-M17CC-01..03 and every earlier RR/SR/FPR register remain CLOSED.** CI `37275398955` independently corroborated on synthetic merge `644c1c0` (exact executable head `eb1bfd0` over unchanged base `d893d65`: focused 107, collection 3130, backend 3129/20/0, frontend 143/143 across 32 files, TypeScript clean, production build successful) — those gates exercise the RR16 outer malformed shapes but not the new nested `intent` adversaries.

## Frozen finding

- **RR17-M17CC-01 — Medium — outer ShotRevision parsing is now total, but M16's first semantic reads of the parsed snapshot are still not total over malformed nested `intent` structure; the same defect is reachable through both historical inspection and full restore.** The shared parser guarantees decodable JSON and a dict top level — appropriate — but the next predecessor layer assumes the nested `intent` member is itself a dictionary: the shared M16 historical verifier contains `snapshot.get("intent", {}).get("duration_ms")` after rebuilding the intra-shot companion closure, and a canonical, hash-authenticated schema-7 or schema-8 snapshot containing `"intent": []` passes every RR16 parse/container guard and then raises raw **`AttributeError`** at the nested `.get()`. Reachable on BOTH major integrity surfaces: on **historical inspection**, `api/continuity.py` decodes the outer snapshot, proves it a dict, validates the discriminator, and calls `verify_intra_shot_history(...)` BEFORE its final outer canonical-bytes/hash comparison — a coherent outer hash does not rescue the path (the raw exception emits instead of the typed historical invariant); on **full restore**, M16 runs before M17C-C — its global enumeration correctly calls `load_outer_snapshot()`, obtains the valid outer dict, identifies schema 7 (or schema 8 carrying `intra_shot`), calls `verify_intra_shot_history_sync(...)`, and the shared verifier reaches the same nested `.get()` and the same raw `AttributeError` BEFORE M17C-C's envelope authentication runs. **A second manifestation in `_verify_proposal_source()`** performs the same nested access and, if `duration_ms` is non-null, immediately executes `1 <= t < duration` — even with `intent` an object, a coherently persisted non-integer `duration_ms` (e.g. a string) produces raw **`TypeError`** during the comparison; the canonical writer's `intent.duration_ms` is integer-or-null and recovery does not certify that representation before arithmetic. **Decisive adversary (as frozen):** a lawful schema-8 capture wrapping schema-7 intra-shot history — (1) the lawful control proven green on §12/history plus full restore; (2) only the outer snapshot's `intent` changed from its writer-produced object to `[]`; (3) `schema_version`, `intra_shot`, the Performance block, and all companion rows unchanged; (4) canonical `snapshot_json` and `snapshot_hash` recomputed so outer self-authentication passes by construction; (5) historical inspection refuses through its typed invariant contract, never `AttributeError`; (6) staged full restore refuses through `RecoveryCorruption`, never `AttributeError`. Plus a second focused M16 proposal adversary: `intent` an object but `duration_ms` a canonical non-integer, the ShotRevision hash AND the proposal's relational `source_shot_revision_hash` coherently updated, typed refusal BEFORE the range comparison. **Required narrow correction (as framed):** do NOT expand `load_outer_snapshot` into a full snapshot grammar (the parse/container layer is correctly scoped) — the predecessor semantic code should certify the nested value it consumes before use: `intent` must have a lawful object shape for this read, and a non-null captured `duration_ms` must have the lawful actual-integer/domain representation required by M16 before equality/range arithmetic; ONE shared predecessor helper used by BOTH intra-shot history and proposal-source verification, avoiding another pair of subtly different grammars.

## Frozen disposition

**TWENTY-FIRST FRESH INDEPENDENT REVIEW COMPLETE — NOT CLEAN. RR16-M17CC-01: CLOSED. RR15-M17CC-01/02 remain CLOSED. ISR2-M17CC-01..03 and every earlier RR/SR/FPR register remain CLOSED. New frozen register: `RR17-M17CC-01` — 0H / 1M / 0L — nested ShotRevision `intent`/duration semantic use is not total after the newly corrected outer parse boundary. No other issue in this pass met the evidence threshold.** PR #26 remains draft, unmerged, unready. No second-review rerun, ready-mark, merge, publication, or RR17 correction work has been initiated — the RR17 correction cycle awaits its commission.

---

# M17C-C RR17-M17CC-01 CORRECTION — 2026-10-05 — IMPLEMENTED

The commissioned correction cycle is complete. Correction heads: **`abff4f4`** (implementation + battery, committed first) then **`eabf3e3`** (the four validator admissions, committed afterward; all validators ran against the committed carve-inclusive tree; no new source module this cycle — the shared helper lives in the already-admitted `intra_shot_canonical.py`).

## Delivered (the commission exactly)

1. **ONE shared predecessor helper.** `intra_shot_canonical.captured_intent_duration_ms` establishes, BEFORE any consumer performs `.get()`, equality, or range arithmetic: the outer snapshot's `intent` exists in the representation the M16 consumer expects and is a JSON OBJECT; its `duration_ms` is either null or a PLAIN JSON integer through the frozen `require_plain_int` discipline (bool rejected; the canonical writer emits integer-or-null); returns the captured duration or `None` — no duration invented. Deliberately NOT a general snapshot grammar (only the nested facts actually consumed are certified), and `load_outer_snapshot` stays scoped exactly as RR16 froze it.
2. **Both consumers use the one law.** `intra_shot_history` — the captured-duration EQUALITY law with the immutable intra-shot companion duration now consumes the certified value, failing the typed historical invariant BEFORE the comparison (the commission's semantic fact preserved exactly); a non-object `intent` such as `[]` no longer reaches `.get()` as a raw `AttributeError` on either surface. `m16_verifier._verify_proposal_source` — the raw `1 <= t < duration` boundary over uncertified data is REPLACED by the frozen `require_interior_time` (plain-int discipline for both operands + the strict interior rule), so cross-type values, booleans, strings, floats, out-of-domain values, and non-interior times terminate as typed recovery corruption, never raw `TypeError`; the null-captured-duration behavior is preserved exactly (no interior law runs when the ShotRevision captured no duration).
3. **Disclosed typed-contract alignment:** the m16 enumeration's `verify_intra_shot_history_sync` call now surfaces the shared history module's typed laws as the recovery corruption contract on the restore path (the live API keeps its internal-invariant vocabulary) — matching the commission's requirement that the full staged restore refuse through `RecoveryCorruption`; every existing m16 recovery/proposal test's assertion contract accepts this (verified green below).
4. **The decisive battery, exactly the frozen shapes.** The history/full-restore adversary: a lawful schema-8 ShotRevision wrapping GENUINE schema-7 intra-shot history (one event-bearing capture, then a generic performance mapping on the same shot and a second capture — schema discriminator, `intra_shot`, Performance block, and all companion rows unchanged), the lawful inspection proven green first, then ONLY the outer `intent` changed to `[]` with canonical `snapshot_json`/`snapshot_hash` recomputed so outer self-authentication passes by construction — historical inspection refuses through the typed historical invariant (never `AttributeError`) and the full staged restore (manifest rehashed so it reaches semantic verification) refuses through `RecoveryCorruption` (never `AttributeError`). The proposal-duration adversary: a lawful M16 proposal-review world with `intent` kept an object and `duration_ms` a canonical STRING (the frozen decisive case) plus `True` and `5000.0` as the cross-type regressions — the ShotRevision hash recomputed AND every pinning proposal's relational `source_shot_revision_hash` coherently updated so source-hash coherence passes — full M16 recovery refuses typed BEFORE any comparison (never `TypeError`; the `RecoveryCorruption` class itself is the proof).
5. **Preservation:** RR16 stays closed (its battery green — the outer malformed shapes and the mixed-successor control unchanged); RR15, ISR2, RR14, and every earlier register re-proven green; no M17C-C envelope-authentication, migration-schema, capture-grammar, public-Shot-input, M17A/B/C-semantics, proposal-authority, current-state-independence, or predecessor-ordering change.

## Gates (first-run dispositions recorded exactly, in the commissioned order)

- RR17 battery (`tests/test_m17cc_rr17_corrections.py`) **4/4 on FIRST run** — no fixture corrections, no re-runs after edits.
- Directly endangered M16 historical/recovery/proposal/capture batteries + rr17 **39/39**; M17C-C history + full-restore + round-trip/migration/backup **77/77**; RR16 + RR15 + ISR2 batteries **16/16**; prior correction + live-seam + predecessor recovery batteries **106/106**.
- Committed-tree validators **21/21 green** (implementation `abff4f4` committed before the validator-admission commit `eabf3e3`).
- Frontend green (vitest 143/143 + tsc + build).
- Local full backend suite, FIRST RUN: **3126 passed / 8 skipped / 0 failed in 47:05, exit 0** (collection 3134 = the prior 3130 + the 4-test battery — exact).
- **CI run `37295567672` on `eabf3e3`: SUCCESS, attempt 1 — Backend 3133 passed / 20 skipped / 0 failed** (CI total 3153 = its prior 3149 + the 4-test battery, exact); Frontend green attempt 1. Corroboration only.

## Fences honored

No second-review rerun; no ready-mark; no merge; no publication; PR #26 remains draft, unmerged, unready. **RR17-M17CC-01 remains OPEN until a fresh independent review closes it** — the work stops here and holds for the **twenty-second fresh independent first-pass review** of the corrected executable head (`eabf3e3`).
