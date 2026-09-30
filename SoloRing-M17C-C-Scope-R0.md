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

§1.7 backup/restore + downgrade closure: clean round trips preserving companions, staged real-0021→0022 upgrade retaining all M17C-C rows, populated downgrade refusals naming the tables, and the head-sweep of test constants.



