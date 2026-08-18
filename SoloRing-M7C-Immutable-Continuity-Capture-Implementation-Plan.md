# SoloRing M7C — Immutable Continuity Capture Implementation Plan

**Status:** Planning specification — **implementation NOT authorized by this document**
**Milestone:** M7C — Immutable Continuity Capture
**Predecessor:** M7B CLOSED + published (`main@018babbaaf3cbe8d2e2e76c2dc5bc297fdb8f831`)
**Successor boundary:** M7D — Controlled Relations + UI

M7C completes the temporal core of the narrative-state layer: the resolved
current Feature state that M7B computes becomes, at capture time, immutable
historical fact inside a schema-3 ShotRevision — and the temporary M7B
capture gate is removed because capture becomes real.

---

## 1. Objective

M7B established:

```text
ContinuityFeature
→ FeatureTransition CRUD
→ canonical narrative ordering
→ effective Feature resolver at Shot/start
→ readiness projection
→ temporary capture/generation gate
```

M7C adds:

```text
effective Feature state at Shot/start
        ↓
ONE consistent read (current state materialized in memory)
        ↓
ONE canonical builder (schema 1 | 2 | 3 — total rule)
        ↓
ONE fenced write unit (reuse-or-insert + immutable child rows)
        ↓
historical ShotRevision = fact
        ↓
Generation / Exact Rerun consume history only
```

The governing invariant (M7 defining rule):

> **Narrative state is resolved from mutable story topology only before
> capture. Once captured into a ShotRevision, the resolved state is
> historical fact and is never resolved again.**

### Exit criterion

Effective Feature states are captured into immutable schema-3 ShotRevisions
with exact feature-history rows; current transitions mutating afterward
never alter historical bytes; Exact Rerun succeeds with the current-state
resolver disabled; M6 schema-1/2 bytes and behaviors are preserved exactly;
and the temporary `NARRATIVE_STATE_CAPTURE_UNAVAILABLE` gate no longer
exists.

---

## 2. Architecture-pattern applicability (binding set)

The register is not a backlog; only the patterns owned by this problem
bind. For M7C:

| Pattern | Binding instantiation in this plan |
|---|---|
| **APR-012** one resolver / canonical builder | §5, §8–§10.3: `continuity/state.py` remains the only effective-state resolver; `build_capturable_snapshot` remains the only snapshot/spec builder; no consumer re-implements either |
| **APR-013** current-history isolation | §8, §12, §15: capture resolves current state in one read; history is written once and never re-resolved; historical endpoints reconstruct only from immutable rows |
| **APR-014** resolved state becomes historical fact | §9: the in-memory resolution is the single source for snapshot bytes, spec bytes, and child rows |
| **APR-015** explicit readiness | §10: the readiness matrix loses its temporary false row; `NARRATIVE_CONTEXT_REQUIRED` remains the only not-ready condition |
| **APR-016** no empty higher-schema alternative | §4: zero effective states with dependencies is EXACTLY schema 2; no empty schema-3 exists |
| **APR-020** immutable execution inputs | §9, §11: Generations point at the captured revision; rerun copies history; neither reads current transitions |
| **APR-022** semantic provenance equivalence | §6: canonical bytes include the anchor triple but exclude `source_transition_id`; equivalent recreated transitions converge |
| **APR-023** fail closed on incomplete provenance | §6, §12: semantic child mismatch and malformed history raise `INTERNAL_INVARIANT_VIOLATION`; no repair, no current-state fallback |
| **APR-025** Exact Rerun isolation | §11: rerun provably succeeds with the resolver disabled |
| **APR-030** fenced derived writes | §9: persistence is one connection + `BEGIN IMMEDIATE` (reuse → allocate → parent insert → child inserts → COMMIT) |
| **APR-031** coherent semantic reads | §8: shot, references, dependencies, approvals, transitions, ordering, and effective resolution from ONE WAL snapshot |
| **APR-032** identical capture convergence | §9, §14: `UNIQUE(shot_id, snapshot_hash)` + in-unit reuse lookup; loser validates the winner semantically and returns it |
| **APR-040** inspection/capture parity | §5, §10.3, §12: the strict current-state endpoint and the capture path use the same resolver and the same canonical ordering |
| **APR-033** race proofs prove the intended interleaving | §14: any race claimed as forced uses barrier/event synchronization at the actual contested seam (the M7B `BEGIN IMMEDIATE`-instrumentation pattern); sleep-based synchronization is categorically rejected |

APR-072 (test naming) governs the source gate as general audit
methodology, not as part of the M7C architecture contract.

---

## 3. Source-fit audit against `main@018babb`

The plan is written against the code that exists. Verified seams:

| Existing (M6/M6C/M7B) | Location | M7C action |
|---|---|---|
| Effective-state resolver + readiness projection | `continuity/state.py` (`resolve_effective_feature_state`, `readiness_projection`, `capture_unavailable`) | resolver unchanged; readiness row flips (§10); `capture_unavailable` deleted (§10) |
| Temporal gate inside the capture read unit | `domain/revisions.py:83–85` (context raise stays; states raise removed) | replace the states-raise with returning the captured states (§8) |
| Snapshot/spec builder, v1/v2 selection | `continuity/snapshots.py::build_capturable_snapshot` | extend selection to v3 (§4–§5); `effective_working_snapshot_hash` follows automatically |
| Fenced persistence + M6 child-row inserts | `domain/revisions.py::_persist_revision_fenced` (dependency inserts at :176) | add feature-history inserts after the parent, same unit (§9) |
| Historical provenance with rebuild-and-compare | `api/continuity.py::_revision_continuity` (v2 spec rebuild, bytes+hash equality) | extend to feature rows for schema-3 (§12) |
| Exact Rerun | `generation/rerun.py` — no resolver/capture invocation (verified: copies the source Generation's historical spec fields) | no change; add the resolver-disabled proof (§11) |
| Historical feature table | `shot_revision_feature_states` exists since migration `0008` (created, constraints live, rows empty) | fill it (§7); **no migration required** (§16) |
| Continuity columns on `shot_revisions` | `continuity_spec_json`/`continuity_spec_hash` since `0006` | store spec-v2 bytes/hash for schema 3 |
| Resolver presentation order | `(entity_id, feature_key)` — the API display order (M7 §48) | unchanged for display; **canonical order differs** (§5.3) |
| Frontend null-safe panels | `WorkingStatePanel`, `ApprovedTakePanel` | no changes (§10.6) |

One deliberate divergence to pin: **API display order ≠ canonical order.**
Display: `(entity_id, feature_key)`. Canonical bytes: `(entity_id,
feature_kind, feature_id)` (M7 §25). The canonical builder re-sorts; the
divergence is named here so it cannot silently drift into the hashing.

---

## 4. Snapshot schema selection — total rule

Selection is a function of ONE captured in-memory value (shot intent +
references + resolved dependencies + effective feature states):

```text
zero semantic dependencies
→ EXACT existing schema 1
→ continuity_spec_json = NULL, continuity_spec_hash = NULL

one or more dependencies AND zero effective Feature states
→ EXACT existing schema 2
→ EXACT existing continuity-spec schema 1
→ no M7 fields injected

one or more effective Feature states
→ ShotRevision schema 3
→ continuity-spec schema 2
```

**There is no empty schema-3 representation** (M6-F14 extended). A Shot
whose effective states all clear converges back onto its schema-2
revision — already proven in M7B; M7C preserves it.

---

## 5. Continuity-spec schema 2 — frozen grammar

### 5.1 Shape

```json
{
  "schema_version": 2,
  "dependencies": [
    {
      "entity_id": "…",
      "entity_kind": "character",
      "entity_revision_id": "…",
      "entity_revision_number": 12,
      "entity_revision_hash": "…",
      "role": "subject",
      "position": 0,
      "source": "shot_explicit"
    }
  ],
  "feature_states": [
    {
      "entity_id": "…",
      "feature_id": "…",
      "feature_key": "forehead_cut",
      "feature_kind": "injury",
      "value_type": "enum",
      "unit": null,
      "value": "fresh",
      "value_hash": "…",
      "source_anchor": {
        "anchor_type": "shot",
        "anchor_id": "…",
        "boundary": "end"
      }
    }
  ],
  "relations": []
}
```

`relations` is frozen now, always `[]` in M7C; behavior lands in M7D.

### 5.2 Value representation

`value` is the canonical typed scalar embedded as parsed JSON (enum →
`"fresh"`, boolean → `true`, integer → `17`, decimal → `"1.5"`). It is the
parsed form of the stored `value_json`; the single canonical serializer
re-serializes it identically. `value_hash` is the SHA-256 of the scalar's
canonical JSON bytes — the same value the resolver verified against the
immutable Feature schema (M7B stored-value verification), carried through
unchanged.

### 5.3 Canonical ordering

```text
dependencies: (role, position, entity_id, entity_revision_id)   [unchanged M6]
feature_states: (entity_id, feature_kind, feature_id)
relations: (subject_entity_id, predicate_key, object_entity_id, relation_id)  [dormant]
```

Arrays are explicitly sorted before canonicalization; database row order,
UUID, and timestamps are never semantic.

### 5.4 Exclusions (binding)

Canonical spec bytes never contain: `source_transition_id`, entity names,
feature display names, current approval pointers, Asset ids, realization
data, executor data, or timestamps.

The spec is persisted twice as identical content, exactly as M6 did for
schema 2: embedded as the snapshot's `continuity` block AND as the
`continuity_spec_json` column, with `continuity_spec_hash` the SHA-256 of
the canonical spec bytes. `snapshot_hash` is the hash of the complete
schema-3 snapshot (embedded block included) — so any feature-state change
necessarily changes `snapshot_hash`.

---

## 6. Provenance-equivalence hashing (M7 §21–§22)

```text
canonical identity includes:   feature identity, key, kind,
                               value type, unit, normalized value,
                               semantic source anchor triple
canonical identity excludes:   source_transition_id
```

Consequences, all gate-pinned:

```text
delete transition A
recreate equivalent transition B
at the same semantic anchor with the same semantic value
→ identical canonical bytes → identical working hash
→ capture converges onto the SAME historical revision
→ stored child rows keep source_transition_id = A (audit truth)

move the same value to a different anchor
→ canonical bytes change → working hash changes → new revision
```

Reuse-integrity validation (§9.4) therefore compares children
**semantically** — `(entity_id, feature_id, feature_key, feature_kind,
value_type, unit, value_json, value_hash, anchor triple)` — and never on
`source_transition_id`.

---

## 7. Historical feature-state storage

`shot_revision_feature_states` (exists since 0008; immutable; no
updated_at/deleted_at):

```text
shot_revision_id, entity_id, feature_id          identity + FKs
feature_key, feature_kind, value_type, unit      semantic schema
value_json, value_hash                           canonical value bytes
source_transition_id                             audit metadata ONLY
source_anchor_type, source_anchor_id, source_boundary
```

Only effective `set` states appear. Cleared/absent features never do
(M7 §27). PK `(shot_revision_id, feature_id)`.

---

## 8. Capture read phase — one consistent read

`_snapshot_one_read` extends from its M7B shape (gates in, states
discarded) to the M7C shape (states returned):

```text
BEGIN
Shot
references
M6 dependency resolution (current approvals)
effective Feature resolution (resolver, unchanged)
if unassigned AND relevant temporal data:
    raise NARRATIVE_CONTEXT_REQUIRED            [unchanged]
COMMIT
return (shot, refs, resolved_dependencies, effective_states)
```

The temporary states-raise is deleted. Everything still derives from ONE
WAL snapshot: a capture observes complete-before or complete-after any
concurrent transition edit/approval/reorder — never a hybrid. All state
used by canonicalization comes from this single in-memory value.

---

## 9. Capture canonicalization + write phase

### 9.1 Canonicalization (pure, no DB access)

From the captured value: select schema (§4), build snapshot + spec + the
child-row values. All three derive from the same resolution; nothing is
re-queried.

### 9.2 Write unit — one connection, `BEGIN IMMEDIATE`

```text
BEGIN IMMEDIATE
reuse lookup by (shot_id, snapshot_hash)
existing?
├─ yes → validate expected child set semantically (§9.4)
│         → return existing revision
└─ no
    ↓ allocate revision_number (existing seam)
    ↓ INSERT ShotRevision                     (parent first — UOW lesson)
    ↓ INSERT shot_revision_entity_dependencies (M6 children)
    ↓ INSERT shot_revision_feature_states      (M7 children)
    ↓ COMMIT
```

Bounded `IntegrityError` retry remains defense in depth only.

### 9.3 Convergence

Two concurrent identical captures (same semantic state, even with
different source transition ids) produce the same `snapshot_hash` and
converge on one revision. Different captures both persist; revision
numbers are persistence order, never narrative chronology.

### 9.4 Reuse integrity (fail closed)

For a reuse candidate found by `(shot_id, snapshot_hash)`:

```text
verify exact parent snapshot bytes (snapshot_json)
↓ verify continuity_spec bytes AND hash
↓ verify exact M6 dependency child set
↓ verify exact M7 Feature semantic child set:
    entity_id, feature_id, feature_key, feature_kind, value_type, unit,
    value_json, value_hash, anchor triple
    — NEVER source_transition_id
↓ all valid → return the existing revision
```

Any failure — missing child, extra child, wrong child, bad value hash,
wrong semantic source anchor, wrong Feature semantic schema, wrong spec
bytes — is `INTERNAL_INVARIANT_VIOLATION` (500). The prohibited outcomes
are explicit:

```text
NEVER "reuse declined" → create another revision around the corruption
NEVER repair/refill historical rows from current state
NEVER silently omit the disagreement
```

When a recreated equivalent current transition converges onto the
revision, the stored child's original `source_transition_id` remains
untouched — the APR-022 distinction.

---

## 10. Readiness, error contract, and the gate removal

### 10.1 Removals

```text
NARRATIVE_STATE_CAPTURE_UNAVAILABLE   — error code deleted
capture_unavailable()                 — helper deleted
readiness row "effective states → not ready" — deleted
```

### 10.2 Readiness matrix after M7C

```text
dependency-free Shot
→ continuity_ready = false, continuity_state_ready = true
→ schema-1 working hash, normal comparison        [unchanged]

dependencies + no relevant temporal data
→ ready/true/true, exact M6 hash                  [unchanged]

assigned + relevant + effective result empty
→ continuity_state_ready = true, exact schema-2 hash, capture legal
                                                  [unchanged]

assigned + one or more effective Feature states
→ continuity_state_ready = TRUE                   [FLIPPED]
→ working_snapshot_hash = schema-3 snapshot hash
→ working_state_differs_from_approved = normal comparison

unassigned + relevant temporal data
→ continuity_state_ready = false, hash/differs NULL
→ NARRATIVE_CONTEXT_REQUIRED on strict paths      [unchanged]
```

### 10.3 Structural singularity — one captured value, one builder

M7C defines ONE current-state value and ONE canonical consumer:

```text
CapturedCurrentState = (shot, refs, resolved_dependencies, effective_states)

read_shot_detail()  → CapturedCurrentState → build_capturable_snapshot
                                          → working hash + differs
capture_revision()  → CapturedCurrentState → build_capturable_snapshot
                                          → persistence
```

`effective_working_snapshot_hash` remains a thin wrapper that delegates to
`build_capturable_snapshot` (it already does); M7C extends its signature
to carry the effective states rather than adding a second builder. The
Shot-detail hash must be the hash of the EXACT value capture would persist
at that database moment.

Output equivalence is not the contract — two duplicate builders can
accidentally agree. The source gate includes a STRUCTURAL proof:

```text
spy on build_capturable_snapshot
→ BOTH the working-hash path and the capture-persistence path
  demonstrably invoke it for the same database moment
+ AST/source scan: no snapshot/spec builder exists outside
  continuity/snapshots.py (the M6C/M7A.5 single-implementation family)
```

### 10.4 Working-hash semantics under schema 3

`effective_working_snapshot_hash` becomes the schema-3 hash when states
are non-empty (automatic via the builder extension). M6-F15 extends:
transition mutations change the working hash **without any Shot-row
change**; the next capture is a new revision. Readiness conditioning in
`read_shot_detail` keeps its one-builder/one-value discipline.

### 10.5 Deliberate test churn

M7B gate tests asserting the 409 flip polarity: "nonempty → blocked"
becomes "nonempty → schema-3 captured with exact children". This churn is
contracted here so the reviewer reads it as design, not drift.

### 10.6 Frontend

**No changes.** Null-safe panels already render both readiness states; the
capture-unavailable "unresolved" case disappears, the context-required
case remains NULL — both handled.

---

## 11. Generation and Exact Rerun

Generation creation already funnels through `capture_revision()` — gate
removal makes it capture schema 3 with zero generation-code changes; the
Generation inherits the historical graph by pointing at the revision. A
source-gate guard (AST scan, the established family) proves no alternative
Generation path independently resolves current M7 state.

Exact Rerun copies the source Generation's `shot_revision_id` and spec
fields (verified: no resolver or capture call exists in `generation/rerun.py`).
M7C adds the required negative proof:

```text
create Generation A from schema-3 ShotRevision X
radically mutate current transitions/topology/approvals
monkeypatch the current-state resolver so ANY invocation fails the test
Exact Rerun A
→ succeeds from X alone
→ reports X's feature states, spec hash, and captured revisions
```

---

## 12. Historical provenance surfaces

`GET /shot-revisions/{id}/continuity` and `GET /generations/{id}/continuity`
extend (never replace):

```text
v1 → nulls + empty lists                          [unchanged]
v2 → dependencies only, rebuild-and-compare       [unchanged]
v3 → reconstruct continuity-spec schema 2 from the IMMUTABLE ROWS:
       dependencies:
         shot_revision_entity_dependencies
         ⋈ entity_revisions (kind/number/hash — immutable history)
       feature_states:
         shot_revision_feature_states rows ARE the authority
         — feature_key/kind/value_type/unit/value_json/value_hash/
           anchor are captured duplicates; NEVER re-derived from
           today's ContinuityFeature, transitions, or anchors
       per feature row:
         re-parse value_json
         → re-canonicalize against the CAPTURED value_type
         → require recomputed hash == stored value_hash
       then:
         canonicalize the reconstructed spec
         → exact bytes AND hash equality with continuity_spec
         → exact SET equality between spec feature_states and rows
     any failure → INTERNAL_INVARIANT_VIOLATION
```

`source_transition_id`s are returned as audit metadata only.
Reconstruction never consults current transitions, approvals, topology,
or the live Feature schema (APR-013 + APR-014 + APR-023).

---

## 13. M6 byte preservation (hard gate)

```text
schema-1 fixture under M7C → identical bytes/hash → same revision reuse
schema-2 fixture (zero effective states) → identical bytes/hash → reuse
schema-2 convergence after set→clear → same revision              [kept]
```

The existing canonical fixtures and convergence tests must remain green
without modification (except the contracted §10.5 polarity flips).

---

## 14. Concurrency matrix

```text
transition PATCH vs capture        → coherent before/after, never hybrid
Feature soft-delete vs capture     → coherent (distinct case: the fenced
                                    deletion guards hold; the capture read
                                    sees the Feature either fully present
                                    or fully absent)
transition soft-delete vs capture  → coherent
narrative reorder vs capture       → coherent ranks from the same read
Entity approval vs capture         → coherent (M6 property, retained)
identical concurrent schema-3 captures → one revision; loser validates
                                          winner semantically and returns it
different concurrent captures     → both persist, distinct numbers
```

APR-033 is normative here: any race the source gate claims as FORCED
must use barrier/event synchronization at the actual contested seam —
the M7B instrumented-`BEGIN IMMEDIATE` pattern — and never a sleep. A
forced-race proof that cannot demonstrate the competitor reached the
seam does not count as forced.

---

## 15. Historical isolation matrix

Each must leave prior ShotRevision bytes AND child rows untouched:

```text
edit transition      delete transition     re-anchor transition
rename Feature       delete Feature (after legal transition removal)
reorder topology     approve newer EntityRevision
recreate equivalent transition at the same anchor
```

The last line is the provenance-equivalence proof: history unchanged AND
current capture converges onto the same revision.

---

## 16. Migration posture

**No migration is required.** Verified against `main`:

```text
shot_revisions.continuity_spec_json/hash     — since 0006
shot_revision_feature_states (+ constraints) — created by 0008, rows empty
```

M7C is code-only. If implementation discovers otherwise, STOP and bring
the discrepancy back before writing any migration — a new migration is not
authorized by this plan.

Source-gate assertions:

```text
Alembic head remains 0008
no migration files changed
ORM/migration table parity for the affected historical tables
remains unchanged
```

---

## 17. Scope exclusions (hard boundary)

```text
NO relation/predicate behavior     (grammar frozen; relations always [])
NO RelationTransition logic
NO M7D UI; NO transition-authoring UI; NO frontend changes
NO visual anchors / realization    (M8/M9)
NO changes to Exact Rerun semantics beyond the proof
NO new durable error codes         (one code is REMOVED, §10.1)
NO migration                       (§16)
```

---

## 18. Source-gate proof matrix

```text
SCHEMA SELECTION
  zero deps → exact schema 1 bytes
  deps + zero effective → exact schema 2 bytes + spec 1
  effective states → schema 3 + spec 2 + exact immutable rows
  no empty schema-3 representation
  set→clear converges back onto schema-2 revision

CANONICALIZATION
  exact spec-v2 byte fixtures (single/multiple features, all value types)
  canonical order (entity_id, feature_kind, feature_id) — incl. a case
    where display order differs from canonical order
  reordered DB rows cannot affect bytes
  value_hash correctness (SHA-256 of canonical scalar bytes)

PROVENANCE EQUIVALENCE
  same-anchor recreation → same hash → same revision reused
  source_transition_id changes only → hash unchanged; audit row keeps A
  anchor moves → hash changes

CAPTURE
  one-read coherence races (§14), including Feature soft-delete ↔ capture
  concurrent identical schema-3 captures converge; winner validated
  reuse-integrity on an EXISTING winner: missing/extra/wrong child, bad
    value hash, wrong anchor, wrong semantic schema, wrong spec bytes
    → INTERNAL_INVARIANT_VIOLATION
    → never reuse-decline-and-recapture, never repair
  capture writes parent before children (FK ordering)

STRUCTURAL SINGULARITY
  spy on build_capturable_snapshot: working-hash path AND
    capture-persistence path both invoke it at the same database moment
  AST scan: no snapshot/spec builder outside continuity/snapshots.py
  AST scan: no Generation path resolves current M7 state independently

NO-MIGRATION
  Alembic head remains 0008; no migration files changed;
  ORM/migration parity unchanged

READINESS
  matrix §10.2 in full, including the flipped row
  NARRATIVE_STATE_CAPTURE_UNAVAILABLE gone from code and behavior
  transition mutation changes working hash with Shot row unchanged

HISTORICAL ISOLATION (§15) — all rows

EXACT RERUN — resolver-disabled proof (§11)

M6 PRESERVATION (§13) — fixtures byte-identical

PROVENANCE SURFACES (§12) — v3 rebuild-and-compare; corruption
  (missing/extra child, wrong value bytes, wrong anchor, malformed spec)
  → INTERNAL_INVARIANT_VIOLATION, never current-state fallback
```

---

## 19. Evidence and closure

```text
archive      SoloRing-M7C-r1.zip via
             git -c core.autocrlf=false -c core.eol=lf archive … HEAD
             (accepted Windows packaging rule)
backend      full suite ×2
M7C tests    dedicated file; count reported
frontend     carried forward if blobs unchanged (no changes anticipated)
tsc/build    clean (only if frontend touched; otherwise carried)
migration    no new migration (§16 restated in the report)
```

M7C closes only on the user's source gate over the archive. A passing
gate authorizes publication of M7C only — **not M7D**.

---

## 20. Engineering sequence

```text
M7C-1  canonical grammar: spec-v2 builder + ordering + fixtures (pure)
M7C-2  capture path: read-phase return, v3 selection, fenced writes,
       gate removal, readiness flip
M7C-3  provenance surfaces + reuse-integrity validation
M7C-4  full proof matrix: byte preservation, temporal headline,
       rerun isolation, concurrency, corruption gates
M7C-5  evidence: suite ×2, archive, delta, report
        ↓
      M7C SOURCE GATE (user)
        ↓
      M7C CLOSED → publication → M7D (separately authorized)
```

---

## 21. The resulting architecture

```text
CreativeEntity → immutable EntityRevision → explicit approval
        ↓
Shot working dependencies + FeatureTransitions on narrative boundaries
        ↓
ONE resolver at Shot/start (inclusive eligibility)
        ↓
ONE canonical builder (schema 1 | 2 | 3)
        ↓
ONE fenced write unit → immutable ShotRevision
  ├── Intent
  ├── Asset References
  ├── Semantic Dependency Snapshot        (schema ≥ 2)
  └── Feature-State Snapshot              (schema 3)
            ↓
      continuity_spec_hash (schema-aware)
            ↓
        Generation → Exact Rerun → Take
```

History never asks the present what happened.
