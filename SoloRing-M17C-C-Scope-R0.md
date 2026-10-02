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
