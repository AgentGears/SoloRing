# SoloRing M7D — Controlled Relations and Continuity UI Implementation Plan

**Status:** Revision 2 — review corrections + final tightenings applied (2026-08-19); **implementation NOT authorized by this document**
**Milestone:** M7D — Controlled Relations + Continuity UI
**Predecessor:** M7C CLOSED + published (`main@9cde886eda8b9b90919e9f245b8d806a1d2194f9`)
**Successor boundary:** M8+ — visual realization (deliberately deferred; NOTHING in this
plan may introduce visual identity)

M7D completes the M7 relation half and the M7 user surface: the dormant
`ContinuityPredicate` / `ContinuityRelation` / `RelationTransition` machinery
becomes real, effective relation state resolves at `Shot/start` through the
existing canonical ordering, the already-frozen `relations` field of
continuity-spec schema 2 is populated WITHOUT changing the grammar, capture
persists into the already-existing `shot_revision_relation_states` table, and
the first continuity authoring/inspection UI lands — read-and-author only,
never M8 realization.

M7D **extends M7C; it does not create a parallel continuity system.** Every
M7C singularity is reused, not duplicated:

```text
ONE narrative ordering            (narrative/order.py — untouched)
ONE coherent current-state read   (the explicit-BEGIN read unit — extended)
ONE canonical continuity builder  (build_capturable_snapshot — extended)
ONE schema-3 representation       (snapshot form 3 + spec 2 — unchanged shape)
ONE fenced ShotRevision unit      (_persist_revision_fenced — extended)
ONE historical authority          (captured-row-only reconstruction — extended)
```

---

## 1. Objective

M7C established:

```text
effective Feature state at Shot/start
        ↓
ONE consistent read → ONE canonical builder → ONE fenced write
        ↓
schema-3 ShotRevision + shot_revision_feature_states = historical fact
```

M7D adds the relation half and the user surface:

```text
ContinuityPredicate (Project-scoped identity)
        ↓
ContinuityRelation (subject —predicate→ object, Project-scoped)
        ↓
RelationTransition (state ∈ {active, inactive} on narrative boundaries)
        ↓
effective relation state at Shot/start (canonical ordering)
        ↓
same current-state materialization (one read unit, one builder)
        ↓
schema-3 continuity capture (relations field of spec 2)
        ↓
shot_revision_relation_states (immutable captured rows)
        ↓
historical provenance (captured-row-only reconstruction)
        ↓
M7 continuity authoring/inspection UI
```

### Governing invariants (M7, restated for relations)

> **Narrative relation state is resolved from mutable story topology only
> before capture. Once captured into a ShotRevision, the resolved relation
> state is historical fact and is never resolved again.**

> **A relation's effective state at a Shot is classified by endpoint
> completeness: both endpoints in the Shot's current semantic dependency
> set → effective; exactly one → continuity is INCOMPLETE
> (`CONTINUITY_RELATION_ENDPOINT_REQUIRED` — not-ready, NULL hash, blocked
> capture/generation); neither → irrelevant. Incomplete current state is
> never conflated with canonical absence.**

### Exit criterion

Effective relation states resolve through the one canonical ordering and are
captured into immutable schema-3 ShotRevisions with exact
`shot_revision_relation_states` rows; reuse-integrity covers the relation
semantic set; M6 v1/v2 AND M7C-era spec-2 bytes (empty `relations`) are
preserved exactly; Exact Rerun succeeds with BOTH resolvers disabled; a Shot
with an active relation touching exactly one dependency endpoint is
explicitly not-ready (`CONTINUITY_RELATION_ENDPOINT_REQUIRED`) with NULL
hash/differs and blocked capture/generation; the
full M7 surface (Features, FeatureTransitions, Predicates, Relations,
RelationTransitions, effective state, revision provenance) is authorable and
inspectable in the web UI; no M8 capability exists anywhere in the delta.

---

## 2. Architecture-pattern applicability (binding set)

The register is not a backlog; only the patterns owned by this problem bind.
The Architecture Pattern Register is a standalone project architecture
artifact that is deliberately NOT committed to the repository; its M7D
mapping is PRIMARY: APR-010, 011, 012, 013, 015, 017, 030, 031, 044, 050,
051. The M7C invariants remain binding as INHERITED. **The register is not
added to the M7D repository delta** — it stays an architecture-review
artifact unless repository governance is separately decided.

### 2.1 PRIMARY M7D patterns

| Pattern | Binding instantiation in this plan |
|---|---|
| **APR-010** resolve temporal state directly at the target narrative position; never depend on operational replay | §7: the relation resolver evaluates winners at the target Shot/start rank through the canonical ordering; no replay of transition history from any origin |
| **APR-011** boundary inclusion semantics must be explicit and tested; M7 rule `transition_rank <= Shot/start rank` | §6.3, §7, §21.4: inclusive eligibility is stated, uses `boundaries_through` semantics, and is pinned by explicit boundary-position tests (target /start eligible; target /end not) |
| **APR-012** one resolver / canonical builder | §7, §8–§10: `continuity/state.py` gains the ONE relation resolver beside the ONE feature resolver; `build_capturable_snapshot` remains the only snapshot/spec builder; no consumer re-implements either |
| **APR-013** current-history isolation | §9, §11, §16: capture resolves current relation state in one read; history is written once and never re-resolved; historical endpoints reconstruct only from immutable rows |
| **APR-015** explicit readiness | §12: TWO explicit semantic not-ready conditions after M7D — `NARRATIVE_CONTEXT_REQUIRED` and `CONTINUITY_RELATION_ENDPOINT_REQUIRED`; each forces `continuity_state_ready = false`, NULL hash/differs, blocked capture/generation; nothing fabricated |
| **APR-017** legal state never needs UUID/timestamp/row-order tie-breakers; ambiguous/corrupt state fails | §7: rank ties are impossible by construction; an ambiguous winner or stored corruption raises `INTERNAL_INVARIANT_VIOLATION` — never an identity-based tiebreak |
| **APR-030** fenced derived writes | §10: persistence remains one connection + `BEGIN IMMEDIATE` (reuse → allocate → parent insert → M6 children → M7 feature children → M7 relation children → COMMIT) |
| **APR-031** coherent semantic reads | §9: shot, references, dependencies, approvals, transitions of both kinds, ordering, and both resolutions from ONE WAL snapshot |
| **APR-044** feature-film scale may increase rows processed, not SQL round trips per item | §19: fixed per-resolution query COUNT regardless of entity/relation/transition counts; count-identity gate at 2,500-shot scale |
| **APR-050** UI is a projection/manipulation surface over SoloRing authority; never the authority | §18: the UI renders and submits through the documented endpoints; server canonicalization/validation is the sole authority; client-side checks are mirrors only |
| **APR-051** unresolved state must be represented honestly; never fabricate readiness, hashes, comparisons, or provenance | §12, §18: endpoint-required renders as an explicit named condition with NULL hash/differs; "unresolved" copy, never fabricated values |

### 2.2 INHERITED M7C invariants still binding

| Pattern | Binding instantiation in this plan |
|---|---|
| **APR-014** resolved state becomes historical fact | §10: the in-memory relation resolution is the single source for spec bytes and child rows |
| **APR-016** no empty higher-schema alternative | §8.3: zero effective Feature states AND zero effective relation states with dependencies is EXACTLY schema 2; no empty schema-3 exists |
| **APR-020** immutable execution inputs | §10, §14: Generations point at the captured revision; rerun copies history; neither reads current transitions of either kind |
| **APR-022** semantic provenance equivalence | §8.4: canonical relation bytes include the anchor triple but exclude `source_transition_id`; equivalent recreated relation transitions converge |
| **APR-023** fail closed on incomplete provenance | §10.4, §11: relation semantic child mismatch and malformed history raise `INTERNAL_INVARIANT_VIOLATION`; no repair, no current-state fallback |
| **APR-025** Exact Rerun isolation | §14: rerun provably succeeds with BOTH resolvers disabled |
| **APR-032** identical capture convergence | §10, §15: `UNIQUE(shot_id, snapshot_hash)` + in-unit reuse lookup; loser validates the winner semantically and returns it |
| **APR-040** inspection/capture parity | §7, §9, §11: the strict current-state endpoint and the capture path use the same resolvers and the same canonical ordering |
| **APR-033** race proofs prove the intended interleaving | §15: forced races use barrier/event synchronization at the actual contested seam; sleep-based synchronization is categorically rejected |

### 2.3 Audit method

APR-072 (test naming) governs the source gate as general audit methodology.

---

## 3. Source-fit audit against `main@9cde886`

The plan is written against the code that exists. Verified seams:

| Existing (0008/M7A/M7A.5/M7B/M7C) | Location | M7D action |
|---|---|---|
| All four relation tables already migrated | `continuity/models.py:520–778` (`continuity_predicates`, `continuity_relations`, `continuity_relation_transitions`, `shot_revision_relation_states`); DDL live in `alembic/versions/0008_narrative_continuity_state.py:195–420` | fill them; **NO migration required** (§17) |
| Predicate key grammar shared with feature keys | `continuity/values.py:43` — `KEY_RE` documented as "§4.3 machine semantic key (features) and §37 predicate key share this" | reuse `is_valid_key`; no second grammar |
| Spec-v2 builder hardcodes dormant relations | `continuity/snapshots.py:129–140` — `build_continuity_spec_v2` emits `"relations": []` | extend signature to accept relation states; populate (§8); grammar unchanged |
| Read path already enforces the relations container | `api/continuity.py:189–193` — spec-2 `relations` must be an array or `INTERNAL_INVARIANT_VIOLATION` | unchanged; now exercised by non-empty content |
| Feature resolver as template | `continuity/state.py::resolve_effective_feature_state` | add `resolve_effective_relation_state` in the same module, same connection discipline (§7) |
| Capture read unit | `domain/revisions.py::_snapshot_one_read` (:34–88) | resolve relation state in the SAME unit (§9) |
| Fenced persistence + reuse integrity | `domain/revisions.py::_persist_revision_fenced`, `_validate_reuse_integrity`, `_expected_feature_rows` (:105–341) | add `_expected_relation_rows`, relation inserts, relation validation (§10) |
| Historical rebuild-and-compare | `api/continuity.py::_revision_continuity` (:103–345) — `_CapturedFeatureState` adapter, per-row `historical_canonicalize_value`, byte+hash equality | add `_CapturedRelationState` adapter + per-row predicate-key grammar check (§11) |
| Transition CRUD/PATCH matrix template | `continuity/transitions.py` (create/PATCH prospective-row/delete/list, anchor validation through `load_narrative_ordering`) | mirror for relation transitions with `state` replacing operation+value (§6) |
| Anchor lifecycle guards (feature transitions only) | `domain/shots.py:402–418` (Shot delete), `narrative/sequences.py:~222` (Sequence delete), `narrative/scenes.py:~249` (Scene delete), `narrative/scenes.py:~370–385` (Shot unassign), `domain/projects.py:119–134` (cascade tombstoning) | every guard gains the parallel `continuity_relation_transitions` check; cascade extends (§13) |
| Entity delete guard | `continuity/entities.py::delete_entity` — blocks on working dependency (:293) and active features (:314) | add active-relation guard (subject or object) (§13.3) |
| Working hash through THE builder | `domain/shots.py::read_shot_detail` (:273–345) — `effective_working_snapshot_hash(shot, refs, resolved, outcome.states)` | thread relation states through the same builder (§12.4) |
| Exact Rerun | `generation/rerun.py` — `_create_rerun_fenced` copies historical spec fields; no resolver/capture invocation | no change; extend the disabled-resolver proof to BOTH resolvers (§14) |
| Continuity-state endpoint | `api/continuity.py:542–597` — one consistent read, returns `feature_states` | add `relation_states` to the same response (§12.3) |
| Frontend: zero continuity API consumers | `apps/web` — no `/continuity` calls; continuity reaches the UI only via `ShotDetail` fields consumed by `WorkingStatePanel`, `ApprovedTakePanel`, `RevisionList` (`app/shots/[id]/page.tsx:90–123`) | build the authoring/inspection surface fresh (§18) |

Two deliberate asymmetries to pin (both are 0008-frozen facts, not choices
reopened by this plan):

1. **Predicate keys are tombstone-inclusive unique and never recycled
   (`uq_continuity_predicates_project_id_key`, no partial WHERE) — and
   predicates have NO supersession lineage column.** Feature identity has
   lineage (`supersedes_feature_id`); predicate identity does not. A deleted
   predicate key is dead forever; its semantic successor is a new key.
2. **Relation identity is active-only unique
   (`uq_continuity_relations_active_identity` WHERE deleted_at IS NULL).**
   Soft-deleting a Relation FREES the duplicate slot: the same
   (project, subject, predicate, object) coordinate may be recreated as a NEW
   relation with a NEW `relation_id`. Contrast feature keys (never
   recyclable). Consequently a recreated relation is a NEW semantic identity:
   its capture bytes differ (new `relation_id` in the canonical order), and
   convergence applies to equal bytes only — this is the deliberate
   active-slot semantics of 0008 §38, not an oversight.

Also pinned: `ContinuityRelation` has NO `updated_at` and NO mutable columns
(0008) — therefore **relations have no PATCH**; their lifecycle is
create → (transitions) → soft-delete.

---

## 4. ContinuityPredicate — identity and lifecycle (frozen)

### 4.1 Identity

- Predicate identity is `(project_id, key)` — Project-scoped, exactly as
  `continuity_predicates` (models.py:520–555) freezes it.
- `key`: the shared machine grammar `[a-z][a-z0-9_]{0,63}` via
  `values.is_valid_key` — the ONE key grammar in the codebase.
- Tombstone-inclusive uniqueness (`uq_continuity_predicates_project_id_key`):
  a deleted key is never recycled for the Project's lifetime (0008 §37).
- **No supersession lineage.** Predicate rename of MEANING is expressed by
  minting a new key; the dead key stays dead. (`supersedes_*` exists only in
  feature identity.)
- `name` / `description` are mutable display metadata; no semantic effect —
  the same rule as feature name/description (M7A §4.2).

### 4.2 API surface

```text
GET    /projects/{project_id}/continuity-predicates      → list (active only, ORDER BY key)
POST   /projects/{project_id}/continuity-predicates      → 201 create
GET    /continuity-predicates/{predicate_id}             → read (active)
PATCH  /continuity-predicates/{predicate_id}             → display metadata only (name/description)
DELETE /continuity-predicates/{predicate_id}             → 204 soft-delete
```

- Create validates: active Project; `key` grammar and `name` non-empty
  after strip via the EXISTING generic validation contract (422);
  tombstone-inclusive key conflict → `CONTINUITY_PREDICATE_KEY_CONFLICT`
  (409).
- PATCH is the feature-PATCH pattern exactly: partial field presence,
  omitted → preserve, explicit null → clear description; `key` is NOT
  patchable (immutable identity). Field validation uses the generic
  validation contract (422).
- DELETE: soft; blocked while any ACTIVE relation references the predicate
  → `CONTINUITY_PREDICATE_IN_USE` (409); idempotent for already-tombstoned;
  never-existed/non-UUID → the generic validation contract (pinned
  resolution below — NO predicate-specific 404 code exists in the frozen
  vocabulary and none is manufactured). Historical
  `shot_revision_relation_states` rows never block deletion.
- All mutations are one fenced `BEGIN IMMEDIATE` unit with in-unit active
  verification, through monkeypatchable seams (the M6A/M7A lesson).

### 4.3 Predicate error codes (frozen by D-1 resolution)

The M7D predicate vocabulary is exactly two codes from the frozen M7 table:
`CONTINUITY_PREDICATE_KEY_CONFLICT` (409, key-lifetime conflict) and
`CONTINUITY_PREDICATE_IN_USE` (409, active relation references the
predicate). Malformed predicate authoring fields (key grammar, name form)
use the EXISTING generic validation contract (422). Unresolved predicate
ids on the predicate surface use the generic validation contract as well —
**no seventh M7D code is manufactured for a predicate-specific 404**, and
the proposed draft codes `INVALID_CONTINUITY_PREDICATE` and
`CONTINUITY_PREDICATE_NOT_FOUND` are REMOVED and must not appear anywhere
in the implementation. Inside RELATION construction, a missing/tombstoned
or cross-Project predicate makes the relation structurally invalid →
`INVALID_CONTINUITY_RELATION` (§5.1).

---

## 5. ContinuityRelation — identity and endpoint semantics (frozen)

### 5.1 Identity

- Relation identity is the quadruple
  `(project_id, subject_entity_id, predicate_id, object_entity_id)` under
  active-only uniqueness (0008 §38). `relation_id` (UUID) is the row
  identity carried into capture bytes and history.
- `subject_entity_id ≠ object_entity_id` (CHECK, 422 on create).
- Endpoints and predicate must be ACTIVE and belong to the SAME Project as
  the relation at creation:
  - endpoint entity missing/tombstoned → `ENTITY_NOT_FOUND` (404, existing
    code — endpoints ARE entities, governed by the existing Entity
    vocabulary);
  - predicate missing/tombstoned, cross-Project subject/object, cross-Project
    predicate, self relation (subject = object), or any other structurally
    invalid relation → `INVALID_CONTINUITY_RELATION` (422);
  - `CONTINUITY_ANCHOR_PROJECT_MISMATCH` is NOT repurposed for relations —
    it remains specifically an anchor error.
- Duplicate active identity (same quadruple) → `CONTINUITY_RELATION_CONFLICT`
  (409).
- **No PATCH, no display metadata** (0008 has no mutable columns): lifecycle
  is create → transitions → soft-delete. Deletion is blocked while active
  RelationTransitions exist (in-use); historical captured rows never block;
  idempotent for already-tombstoned.

### 5.2 API surface

```text
GET    /projects/{project_id}/continuity-relations           → list (active only)
POST   /projects/{project_id}/continuity-relations           → 201 create
GET    /continuity-relations/{relation_id}                   → read (active)
DELETE /continuity-relations/{relation_id}                   → 204 soft-delete
```

List supports optional `subject_entity_id` / `object_entity_id` /
`predicate_id` filters (backed by the existing subject/object partial
indexes). Every mutation is one fenced `BEGIN IMMEDIATE` unit.

### 5.3 Endpoint-dependency semantics (frozen — the D-1 load-bearing correction)

- **At authoring time:** endpoints are validated for existence, activity,
  and same-Project only. Relation creation does NOT require either endpoint
  to be a semantic dependency of any Shot — relations are Project-level
  working state, exactly as Features are Entity-level working state.
- **At resolution time (the effectiveness classification):** for an ACTIVE
  relation with a winning ACTIVE transition at the target narrative
  position, endpoint completeness against the Shot's current deduplicated
  M6 dependency set classifies the outcome:

```text
neither endpoint in dependencies   → irrelevant to this Shot
both endpoints in dependencies     → effective relation → capture normally
exactly one endpoint in dependencies
                                   → continuity INCOMPLETE
                                   → CONTINUITY_RELATION_ENDPOINT_REQUIRED
```

  The one-endpoint case is NEVER silent non-participation and never a
  fabricated capture: **incomplete current state ≠ canonical absence**. The
  condition makes the Shot continuity-state-not-ready with NULL
  `working_snapshot_hash` / NULL `working_state_differs_from_approved`,
  blocks capture and Generation-from-current-Shot, and the UI surfaces the
  missing endpoint explicitly (§18.2.5). Historical Generations and Exact
  Rerun are unaffected — they consume already-captured revisions (§14).

- **No hidden dependency is created automatically.** Completing the state
  is an explicit user act: add the missing endpoint as a semantic
  dependency, or deactivate/clear/delete the relation. This is strictly
  safer than either secretly injecting the endpoint or silently dropping a
  known active relation.
- **At dependency-mutation time:** removing an endpoint from a Shot's
  semantic dependencies remains LEGAL and is never blocked by relations —
  but its consequence is the not-ready condition above when an active
  effective relation loses exactly one endpoint:

```text
remove Bag dependency while Eva --carries→ Bag is active
→ dependency mutation succeeds
→ current Shot becomes continuity-state-not-ready
→ next capture / Generation-from-current-Shot blocked
(ENDPOINT_REQUIRED)
```

  Replace-semantics stays exactly as
  `dependencies.replace_semantic_dependencies` froze it.

---

## 6. RelationTransition — operations and anchor rules (frozen)

### 6.1 Shape

`continuity_relation_transitions` (0008): `relation_id`, `anchor_type ∈
{sequence, scene, shot}`, `anchor_id`, `boundary ∈ {start, end}`, `state ∈
{active, inactive}`, soft-delete. Active-only unique coordinate
`(relation_id, anchor_type, anchor_id, boundary)`. **No value columns** —
the state vocabulary replaces set/clear-with-value; `active` is presence,
`inactive` is canonical absence.

### 6.2 API surface

```text
GET    /continuity-relations/{relation_id}/transitions        → list (active, ORDER BY created_at, id)
POST   /continuity-relations/{relation_id}/transitions        → 201 create
PATCH  /continuity-relation-transitions/{transition_id}       → prospective-row update
DELETE /continuity-relation-transitions/{transition_id}       → 204 soft-delete (idempotent)
```

Create/PATCH follow the M7B feature-transition matrix EXACTLY, with `state`
in place of operation+value:

- Anchor validation is THE existing authority:
  `_validate_anchor_in_ordering`-equivalent logic (shared, factored once —
  APR-012) checking existence, activity, same-Project (via the relation's
  Project), complete topology, unassigned-Shot rejection, and presence in
  the canonical ordering via `load_narrative_ordering`. Shot anchors of
  other Projects → Project-mismatch 409; unassigned Shot anchor → 422.
- PATCH prospective-row semantics: `anchor_type`/`anchor_id`/`boundary`/
  `state` omitted → preserve; there is no value matrix (nothing to
  inherit/clear); anchor-or-state change re-validates the anchor and the
  coordinate (conflict 409 when another active transition occupies the
  target coordinate); no-op PATCH is legal and updates nothing but
  `updated_at`.
- Errors reuse the M7B transition codes as-is where semantics are identical:
  `INVALID_CONTINUITY_ANCHOR`, `CONTINUITY_ANCHOR_PROJECT_MISMATCH`,
  `CONTINUITY_TRANSITION_CONFLICT`. Delete uses the conflict-for-unknown /
  idempotent-for-tombstoned policy (frozen vocabulary has no
  transition-not-found code).

### 6.3 Anchor rules

Identical to M7B feature transitions, because the anchor contract is shared:
any active `sequence`/`scene`/`shot` of the same Project present in the
canonical boundary stream; `/start` and `/end` both anchorable; eligibility
for a target Shot is decided ONLY by the resolver (inclusive
`rank ≤ shot_start_rank`), never at authoring.

---

## 7. Effective relation-state resolution at Shot/start

`continuity/state.py` gains — beside `resolve_effective_feature_state`, not
inside it — the ONE relation resolver:

```python
async def resolve_effective_relation_state(
    conn: AsyncConnection, shot_id: str
) -> RelationResolutionOutcome
```

- Runs on the caller's connection inside the caller's consistent read
  (APR-031) — the same discipline every feature-resolution consumer already
  uses. No resolver ever opens its own connection.
- Pipeline — resolves temporal state DIRECTLY at the target narrative
  position (APR-010), inclusive boundary semantics (APR-011), no
  identity tie-breakers (APR-017):

```text
Shot row (project_id, deleted_at, scene_id)
→ deduplicated dependency entity ids
→ active relations of the Shot's Project TOUCHING the dependency subgraph:
  subject ∈ deps OR object ∈ deps
  (predicate active — guaranteed by the §13 guard chain; violation → invariant)
→ active RelationTransitions of those relations
→ canonical ordering (load_narrative_ordering — the only authority)
→ target rank = ordering.shot_start_rank(shot_id)
→ eligible: transition rank ≤ target rank (boundaries_through semantics)
→ highest-ranked eligible transition per relation wins
  (rank ties impossible by construction; ambiguity → INTERNAL_INVARIANT_VIOLATION)
→ classify each relation by its winning state:
    winner inactive, or no eligible winner → absent (canonical absence)
    winner active + both endpoints ∈ deps  → effective relation state
    winner active + exactly one endpoint ∈ deps
                                          → endpoint requirement
    winner active + neither endpoint ∈ deps → irrelevant
      (unreachable after OR-selection — retained as explicit total
       classification, never silently skipped)
→ effective states sorted by (subject_entity_id, predicate_key,
  object_entity_id, relation_id)
```

- Stored-corruption handling mirrors the feature resolver: a transition
  anchored outside the canonical stream, an ambiguous winner, or a relation
  row whose predicate/endpoints/predicate_key disagree with its own guarded
  invariants → `INTERNAL_INVARIANT_VIOLATION` (500), never a silent skip,
  never client error.
- `RelationResolutionOutcome`: `shot_id`, `assigned`,
  `relevant_relation_data` (≥1 active transition on a relation touching the
  dependency subgraph via OR — such a relation may become effective OR
  endpoint-required after assignment, so both count as relevant),
  `relation_states` tuple of frozen dataclasses carrying `relation_id`,
  `subject_entity_id`, `predicate_id`, `predicate_key`, `object_entity_id`,
  and the `source_transition_id` + anchor triple (audit-only fields kept
  OUT of canonical bytes — §8.4), plus `endpoint_requirements`: one §12.4
issue element per exactly-one-endpoint winner — ALL of them, never
whichever row loaded first — each carrying the full relation identity plus
`present_entity_id`/`missing_entity_id`, deterministically ordered by
`(subject_entity_id, predicate_key, object_entity_id, relation_id)`.
- Unassigned Shot: outcome carries the relevance condition; strict
  consumers raise `NARRATIVE_CONTEXT_REQUIRED` themselves (existing
  pattern). Endpoint classification requires a narrative position, so it is
  evaluated only for ASSIGNED Shots; an unassigned Shot with a
  would-be-endpoint-required relation reports `NARRATIVE_CONTEXT_REQUIRED`
  first, and the endpoint requirement surfaces once assigned.

### 7.1 Readiness combination (one projection, TWO not-ready rows)

`readiness_projection` consumes BOTH outcomes on the same read unit.
After M7D there are exactly TWO semantic not-ready conditions:

```text
unassigned Shot + relevant temporal data (feature OR relation)
→ NARRATIVE_CONTEXT_REQUIRED

assigned Shot + ≥1 active relation with exactly one dependency endpoint
→ CONTINUITY_RELATION_ENDPOINT_REQUIRED
```

For both rows: `continuity_state_ready = false`, the issue is carried in
`readiness_issues`, `working_snapshot_hash = NULL`,
`working_state_differs_from_approved = NULL`, capture is blocked, and
Generation-from-current-Shot is blocked (the read unit raises before any
builder invocation). An endpoint requirement produces NO capture at all —
incomplete current state is never captured as if it were canonical
absence. Historical Generation / Exact Rerun are unaffected (§14).
Ready-with-relations and ready-without-relations are both simply ready.

---

## 8. Continuity-spec relations grammar (schema 2 UNCHANGED) and canonical bytes

### 8.1 The frozen field is only now populated

`build_continuity_spec_v2(resolved, feature_states)` becomes
`build_continuity_spec_v2(resolved, feature_states, relation_states=())`.
The output grammar does not change: top-level `schema_version: 2`,
`dependencies`, `feature_states`, `relations` — the field has been frozen
and emitted as `[]` since M7C. M7D populates it. **No schema version bump,
no new key, no reordering of existing keys.**

### 8.2 Entry grammar + canonical order

Each relations entry (insertion order = canonical serialization order):

```json
{
  "subject_entity_id": "…",
  "relation_id": "…",
  "predicate_id": "…",
  "predicate_key": "…",
  "object_entity_id": "…",
  "source_anchor": {"anchor_type": "…", "anchor_id": "…", "boundary": "…"}
}
```

Canonical entry order — the order reserved by schema 2 (M7 §25) and directed
for M7D:

```text
(subject_entity_id, predicate_key, object_entity_id, relation_id)
```

`relation_id` is the final tiebreaker only; it can never override semantic
ordering. The builder re-sorts from resolver/display order (APR-012: sort
happens in the ONE builder, never in consumers). Display order for API
responses is `(subject_entity_id, predicate_key, object_entity_id)` without
the id tiebreak — the divergence is named here exactly as M7C named the
feature display/canonical divergence, so it cannot drift into hashing.

### 8.3 Schema selection — total rule, relation-extended

```text
zero dependencies                                        → schema 1 (exact legacy; spec NULL)
deps + zero effective Feature states
     + zero effective relation states                    → schema 2 (EXACT M6 form; spec 1)
one or more effective Feature states
OR one or more effective relation states                 → schema 3 + spec 2
```

No empty schema-3 representation exists (APR-016 extension): a Shot whose
every state cleared — features AND relations alike — keeps the exact
schema-2 form. Selection considers EFFECTIVE states only; an
endpoint-required Shot never reaches selection at all because the read unit
raises first (§7.1) — an incomplete current state is never captured, under
any schema.

### 8.4 Provenance equivalence (APR-022)

Canonical relation bytes include: the endpoint/predicate identity fields,
`relation_id`, `predicate_key`, and the source anchor triple. Canonical
bytes EXCLUDE: `source_transition_id` (audit-only), all timestamps, creator
identity. Two resolutions that agree on semantic identity + anchors produce
identical bytes and converge (APR-032). Recreating a soft-deleted transition
at the same coordinate converges onto the same revision; recreating a
soft-deleted RELATION does not (new `relation_id` ⇒ new bytes ⇒ new
revision) — pinned in §3 asymmetry 2 as the deliberate 0008 semantics.

---

## 9. Capture read phase — ONE consistent read, extended once

`_snapshot_one_read` (domain/revisions.py:34) gains exactly one step inside
the existing explicit-BEGIN unit:

```text
BEGIN
→ shot row
→ references
→ resolve_working_dependencies          (M6, unchanged)
→ resolve_effective_feature_state       (M7B/M7C, unchanged)
→ resolve_effective_relation_state      (M7D, NEW — same connection, same snapshot)
→ NARRATIVE_CONTEXT_REQUIRED raise (unassigned + relevant data of either kind)
→ CONTINUITY_RELATION_ENDPOINT_REQUIRED raise (assigned + ≥1 exactly-one-endpoint
  active relation) — capture blocked BEFORE any builder invocation
COMMIT
→ return (shot, refs, resolved, feature_states, relation_states)
```

No second connection, no second read unit, no re-resolution between read and
write (APR-031/013). The strict current-state endpoint
(`GET /shots/{id}/continuity-state`) uses the SAME two resolvers on its own
consistent read unit (APR-040 parity).

---

## 10. Capture canonicalization + write phase (fenced unit, extended)

### 10.1 Builder invocation

`capture_revision` threads `relation_states` into
`build_capturable_snapshot(shot, refs, resolved, feature_states,
relation_states)`; spec bytes/hash via the unchanged
`continuity_spec_bytes`; snapshot hash via the unchanged
`canonical_hash(snapshot)`.

### 10.2 Working hash

`effective_working_snapshot_hash` gains the same parameter; `read_shot_detail`
(domain/shots.py:273) calls it with both state tuples. M6-F15 semantics
extend: mutating relation state (transition create/PATCH/delete, relation
create/delete, predicate lifecycle where it changes effectiveness) changes
the effective working hash with NO Shot-row mutation. Null-readiness
behavior (hash NULL when not ready — for EITHER §7.1 condition) unchanged.

### 10.3 Fenced unit

`_persist_revision_fenced` gains, in the SAME `BEGIN IMMEDIATE`:

```text
BEGIN IMMEDIATE
→ reuse lookup by (shot_id, snapshot_hash)
→ existing? → validate (§10.4) → return
→ MAX(revision_number)+1
→ INSERT shot_revisions (parent first)
→ INSERT M6 dependency rows
→ INSERT M7 feature-state rows
→ INSERT M7 relation-state rows            (NEW — last, same captured value)
→ COMMIT
```

Relation-state row inserts write exactly the frozen
`shot_revision_relation_states` columns: `(shot_revision_id, relation_id,
subject_entity_id, predicate_id, predicate_key, object_entity_id,
source_transition_id, source_anchor_type, source_anchor_id,
source_boundary)`.

### 10.4 Reuse-integrity extension (fail closed, APR-023)

`_validate_reuse_integrity` validates, after the existing parent/dep/feature
chain, the stored relation semantic set against `_expected_relation_rows`:

```text
(relation_id, subject_entity_id, predicate_id, predicate_key,
 object_entity_id, source_anchor_type, source_anchor_id, source_boundary)
```

NEVER `source_transition_id` (APR-022). Missing, extra, or wrong rows — any
disagreement — is `INTERNAL_INVARIANT_VIOLATION`. Prohibited outcomes
unchanged: never reuse-decline-and-recapture, never repair/refill, never
silent omission.

---

## 11. Historical provenance — captured-row-only reconstruction (extended)

`_revision_continuity` (api/continuity.py:103) extends the schema-3 path:

- Load `shot_revision_relation_states` rows for the revision.
- Per row, captured-row-only validation: `predicate_key` must satisfy the
  ONE key grammar (`values.is_valid_key` — pure regex; today's predicate
  table is never consulted, mirroring the enum freeze note). Relation rows
  carry no value payload, so there is no per-value canonicalization; the
  byte-level rebuild below is the master check.
- `_CapturedRelationState` row-shape adapter feeds
  `build_continuity_spec_v2`; the rebuilt spec must match the stored
  `continuity_spec_json` bytes AND `continuity_spec_hash` exactly, else
  `INTERNAL_INVARIANT_VIOLATION`.
- The response gains `relations` (from the rebuilt spec) and extends
  `source_transition_audit` with relation entries
  (`relation_id`, `source_transition_id`).
- Legacy compat is automatic and MUST be proven: a pre-M7D spec-2 row set
  (zero relation rows) rebuilds with `relations: []` — byte-identical to
  what M7C wrote. The existing container check (`relations` must be an
  array) already guards the shape.

Historical endpoints NEVER invoke either resolver, never read current
relation/predicate tables for truth (FK joins for display are permitted only
where the frozen response shape already allows entity revision joins — and
M7D adds none), and never re-derive ordering.

---

## 12. Readiness, error contract, and API extensions

### 12.1 Error normalization

Every internal-integrity failure in the new paths uses the EXISTING
`INTERNAL_INVARIANT_VIOLATION` (errors.py:100) — schema-3 relation reuse
mismatch, impossible persisted history, read-time relation provenance
corruption, resolver stored-corruption. NO near-duplicate code (the
M7-contract naming correction, user-confirmed).

### 12.2 The six M7D codes (frozen by D-1 resolution — complete table)

```text
CONTINUITY_PREDICATE_KEY_CONFLICT       409  predicate key lifetime conflict
CONTINUITY_PREDICATE_IN_USE             409  active Relation references the Predicate
INVALID_CONTINUITY_RELATION             422  self relation / cross-Project endpoint /
                                             cross-Project or unresolvable predicate /
                                             otherwise structurally invalid relation
CONTINUITY_RELATION_CONFLICT            409  duplicate active relation identity
CONTINUITY_RELATION_IN_USE              409  Relation has active RelationTransitions
CONTINUITY_RELATION_ENDPOINT_REQUIRED   409  readiness/capture invariant: active relation
                                             at target with exactly one dependency endpoint
```

The draft's proposed `INVALID_CONTINUITY_PREDICATE` and
`CONTINUITY_PREDICATE_NOT_FOUND` are REMOVED — they do not exist in the
frozen vocabulary and must not be introduced. No seventh M7D code exists.
`CONTINUITY_ANCHOR_PROJECT_MISMATCH` remains specifically an ANCHOR error
and is never repurposed for relation endpoints. Codes already existing and
reused as-is: `ENTITY_NOT_FOUND` (relation endpoints are Entities),
`VALIDATION_ERROR` (malformed predicate authoring fields; unresolved
predicate ids on the predicate surface), `INVALID_CONTINUITY_ANCHOR`,
`CONTINUITY_ANCHOR_PROJECT_MISMATCH`, `CONTINUITY_TRANSITION_CONFLICT`,
`NARRATIVE_CONTEXT_REQUIRED`, `SEMANTIC_DEPENDENCY_*`,
`INTERNAL_INVARIANT_VIOLATION`.

### 12.3 Current-state endpoint

`GET /shots/{shot_id}/continuity-state` response gains `relation_states`
(entries in display order, same field set as the spec entry plus
`source_transition_id`) beside `feature_states`. For an endpoint-required
Shot the endpoint RAISES `CONTINUITY_RELATION_ENDPOINT_REQUIRED` (409) with
`details` carrying the FULL deterministically-ordered issue set (§12.4
element shape) — mirroring the existing `NARRATIVE_CONTEXT_REQUIRED` raise;
the error envelope is the strict-consumer contract, never a partial body,
never an arbitrary first missing endpoint.

### 12.4 ShotRead / frontend compat — the `readiness_issues` contract

`ShotRead` gains exactly ONE additive field: `readiness_issues: list = []`
(default-empty — the M7B additive-compat pattern). The element shape is
frozen:

```text
readiness_issues
→ default-empty additive field
→ populated ONLY from authoritative current-state resolution
  (read_shot_detail's readiness projection on its one consistent read)
→ NEVER historical provenance; NEVER fabricated client-side
→ represents BOTH current not-ready classes:

  NARRATIVE_CONTEXT_REQUIRED element:
    error_code, shot_id

  CONTINUITY_RELATION_ENDPOINT_REQUIRED element (one per incomplete
  active relation — ALL issues, never whichever row loaded first):
    error_code, relation_id,
    subject_entity_id, predicate_id, predicate_key, object_entity_id,
    present_entity_id, missing_entity_id
```

Deterministic ordering: endpoint-required issues sort by the canonical
relation order `(subject_entity_id, predicate_key, object_entity_id,
relation_id)`; a `NARRATIVE_CONTEXT_REQUIRED` issue (unassigned Shot,
§7.1 precedence) stands alone. The element carries enough identity for the
UI to name the missing endpoint WITHOUT re-resolving anything (APR-050 —
projection over authority; APR-051 — unresolved state explicit, never a
guessed value).

The strict endpoint (`GET /shots/{id}/continuity-state`, §12.3) raises ONE
`CONTINUITY_RELATION_ENDPOINT_REQUIRED` (409) whose `details` carries the
same FULL ordered issue set — never an arbitrary first missing endpoint.

All existing `ShotRead` fields and panels (`WorkingStatePanel`,
`ApprovedTakePanel`, `RevisionList`) keep rendering unchanged; new UI is
additive (§18).

---

## 13. Lifecycle guards (complete inventory)

### 13.1 Predicate deletion

`DELETE /continuity-predicates/{id}`: blocked (409 in-use) while ANY active
relation references the predicate. Historical captured rows never block.
Project cascade may tombstone (below).

### 13.2 Relation deletion

`DELETE /continuity-relations/{id}`: blocked (409 in-use) while the relation
has ANY active transition. Idempotent for tombstoned; conflict for unknown.
Deletion frees the active identity slot (§3 asymmetry 2).

### 13.3 Entity deletion

`delete_entity` gains a third guard beside dependency-in-use and
active-features: entity referenced as subject OR object by any ACTIVE
relation → `ENTITY_IN_USE` (409, existing code, new reason detail). This
keeps the guard chain that the resolver's corruption assumptions rely on
(active relation ⇒ active endpoints ⇒ active predicate).

### 13.4 Endpoint dependency removal

NOT guarded (§5.3): relations never block
`PUT /shots/{id}/semantic-dependencies`. The mutation succeeds; when an
active effective relation loses exactly one endpoint, the consequence is
the `CONTINUITY_RELATION_ENDPOINT_REQUIRED` not-ready condition on the
next resolution — never a blocked write, never a hidden dependency, never
a silent drop. Capture history is unaffected.

### 13.5 Anchor lifecycle (four guards + cascade, each extended)

Every existing feature-transition anchor check gains a parallel
relation-transition check in the SAME fenced unit:

| Guard | Location (main@9cde886) | Extension |
|---|---|---|
| Shot delete | `domain/shots.py:402` | also block on active `continuity_relation_transitions` anchored at the Shot |
| Sequence delete | `narrative/sequences.py:~222` | same, anchored at the Sequence |
| Scene delete | `narrative/scenes.py:~249` | same, anchored at the Scene |
| Shot unassign (scene PATCH) | `narrative/scenes.py:~370–385` | same, for member shots |
| Project cascade | `domain/projects.py:119–134` | **correction B:** the cascade removes the ENTIRE relation working state under the same fenced unit and the same `db_now` — active RelationTransitions → tombstone, then active Relations → tombstone, then active Predicates → tombstone (see below) |

**Why the cascade must tombstone Relations and Predicates too (correction
B):** leaving `ContinuityPredicate`/`ContinuityRelation` rows active while
their Project's Entities are tombstoned would falsify the plan's own
invariant chain — `active Relation → active subject → active object →
active Predicate` — immediately after a perfectly legal Project deletion.
The cascade therefore tombstones, in order, under one fence and one
timestamp: active RelationTransitions, active Relations, active
Predicates, plus the existing Features/FeatureTransitions/Entities/
topology behavior. Ordinary in-use guards are bypassed during the cascade
for the same reason M7A/M7B already bypass working-state guards there: the
complete Project working state is leaving activity together. Historical
`shot_revision_relation_states` rows remain untouched. This needs explicit
source-gate coverage (§21.10): after a legal Project deletion, the
invariant chain must still hold over ALL remaining active rows.

All use the existing `CONTINUITY_ANCHOR_IN_USE` (409). Reorder remains LEGAL
(the M7B decision: ephemeral ranks move; boundary identities and capture
history do not).

---

## 14. Generation and Exact Rerun

- Generation capture (`generation/service.py:148` → `capture_revision`)
  needs no new call sites: relation states flow through the extended
  capture automatically.
- Exact Rerun (`generation/rerun.py::_create_rerun_fenced`) copies the
  source Generation's historical spec fields and invokes no resolver and no
  capture — verified unchanged by the M7C audit and re-verified for M7D
  planning. The M7C resolver-disabled proof extends: rerun must provably
  succeed with **BOTH** `resolve_effective_feature_state` AND
  `resolve_effective_relation_state` disabled (APR-025). The disabled
  functions, if called, raise — proving non-invocation mechanically, not by
  reading code.
- `CONTINUITY_RELATION_ENDPOINT_REQUIRED` never affects history: it blocks
  only NEW capture / Generation-from-current-Shot (the read unit raises
  before the builder); historical Generations and Exact Rerun consume the
  already-captured revision and remain fully available.

---

## 15. Concurrency matrix

Barrier-forced races at the real seams (APR-033; sleep-based proofs
categorically rejected). The open-read seam is the explicit-BEGIN read unit
in `_snapshot_one_read` / the continuity-state endpoint, through the
relation-resolution step (the M7C `_open_read_race` helper pattern):
the competitor's REAL mutation transaction executes via the instrumented
`BEGIN IMMEDIATE` seam while the read is open; capture observes BEFORE,
the next capture observes AFTER.

| # | Race | Forced by | Required outcome |
|---|---|---|---|
| R1 | RelationTransition PATCH commits mid-read | barrier inside the resolver seam | capture coherent (all-BEFORE); next capture AFTER; convergence when bytes equal |
| R2 | RelationTransition soft-delete commits mid-read | same | current capture sees the BEFORE-active relation; next capture sees it absent/inactive. (An EFFECTIVE relation cannot itself be soft-deleted mid-read — it necessarily has a winning active transition, so §13.2 blocks the delete; the deletable object at this seam is the transition.) |
| R3 | RelationTransition CREATE(active) commits mid-read on an EXISTING relation | same | current capture BEFORE; next capture AFTER; schema 2→3 exactly when that relation becomes effective. (Relation CREATE alone has no effective narrative state and can NEVER promote the schema — it needs an active transition.) |
| R4 | Semantic-dependency replace commits mid-read, removing exactly one endpoint of an active effective relation | same | dependency mutation SUCCEEDS; current capture BEFORE; next capture/generation blocked `CONTINUITY_RELATION_ENDPOINT_REQUIRED` (§5.3 consequence) |
| R5 | Narrative reorder commits mid-read | same | capture retains OLD ordering; next observes NEW |
| R6 | Relation DELETE ↔ RelationTransition CREATE (write-side guard race) | fenced-write seam, two connections, one barrier | either DELETE wins → transition create rejects the non-active relation, or create wins → Relation DELETE rejects `CONTINUITY_RELATION_IN_USE`; NEVER a tombstoned relation with an active transition |
| R7 | Predicate DELETE ↔ Relation CREATE (write-side guard race) | same | either predicate delete wins → relation create fails `INVALID_CONTINUITY_RELATION`, or relation create wins → predicate delete fails `CONTINUITY_PREDICATE_IN_USE`; NEVER an active Relation under a tombstoned Predicate |
| R8 | Concurrent identical captures (two tasks, one barrier) | `BEGIN IMMEDIATE` instrumentation | exactly one insert; both return the same revision (APR-032) |
| R9 | Concurrent different captures | same | two sequential revisions; numbers strictly ordered |
| R10 | Reuse with corrupted relation rows (UPDATE-then-restore loop; never DELETE) | direct row corruption between captures | `INTERNAL_INVARIANT_VIOLATION`; post-loop 200 positive control |
| R11 | Transition-coordinate create vs create (two connections) | fenced-write seam | exactly one wins; loser gets the 409 conflict |

The relation-less Predicate deletion is a harmless lifecycle event, not a
load-bearing concurrency slot: it remains covered as an ordinary
sequential regression in §21.1.

Also extended: the M7C spy/AST singularity scans now assert ONE relation
resolver and ONE builder entry point (no `relations` serialization outside
the builder).

---

## 16. Historical isolation matrix

| Proof | Requirement |
|---|---|
| Capture-then-mutate | LEGAL mutation sequences only (APR-072 honesty): `capture → transition PATCH` directly; and for the deeper teardown `capture → deactivate/delete relation transition → delete relation → delete predicate` (each step legal because the previous one released the in-use guard) — stored bytes, spec hash, and relation-state rows unchanged. Any proof mutating a guarded object out of order must instead be labeled a Project-cascade test, which legitimately bypasses ordinary in-use guards |
| Read-path isolation | historical endpoint never invokes resolvers / current tables for truth (spy proof) |
| Legacy M7C bytes | revisions captured pre-M7D still return 200 with identical projections after the M7D code ships |
| Captured-row authority | altering today's predicate/relation/transitions never rewrites history; only row-level corruption is detected (and fails closed) |

---

## 17. Migration posture

**None.** Alembic head remains `0008_narrative_continuity_state`. All four
relation tables exist with live constraints since M7A (verified in
`alembic/versions/0008…:195–420` and `continuity/models.py:520–778`).
ORM/migration parity is already enforced by the M7A constraint-parity tests;
M7D adds no columns, no indexes, no constraints. Any implementation step
that appears to need a migration STOPs and reports (the M7C STOP rule,
repeated verbatim as a directive).

---

## 18. Frontend — M7 continuity authoring/inspection UI (boundary-frozen)

### 18.1 Boundary

Authoring + inspection for the M7 surface ONLY. Explicitly excluded (M8
hard boundary): any visual realization, image/asset generation triggers,
visual identity propagation, style transfer, lookdev. No new backend
capability may be added to serve the UI beyond §4–§13.

### 18.2 Surface (apps/web, existing architecture: server components +
scalar props + small client islands; vitest/tsc/prod-build gates)

1. **Entity detail — Feature authoring** (fills the M7A gap): list/create/
   patch(name,description)/delete Features per Entity; enum/typed value
   metadata display; supersession lineage display.
2. **Entity detail — FeatureTransition authoring** (fills the M7B gap):
   per-Feature transition list + create/patch/delete with the exact omitted
   ≠ null form contract (client-side mirrored validation, server-authority
   respected — 422/409 rendering verbatim).
3. **Project continuity — Predicates**: list/create/patch(name,description)/
   delete.
4. **Project continuity — Relations**: list (subject/predicate/object with
   entity + predicate names), create (endpoint + predicate pickers),
   delete; per-relation transition authoring (§6.2 matrix).
5. **Shot detail — current continuity state**: readiness banner rendering
   BOTH not-ready conditions — `NARRATIVE_CONTEXT_REQUIRED` and
   `CONTINUITY_RELATION_ENDPOINT_REQUIRED` with the missing endpoint NAMED
   (via `readiness_issues`, §12.4) and the remediation path visible (add
   the dependency or deactivate the relation); effective Feature states;
   effective Relation states (subject —predicate_key→ object); source
   anchors.
6. **Shot detail — revision provenance**: per-revision continuity
   inspection (dependencies, feature states, relations, transition audit)
   from the historical endpoint.

Null-safety discipline follows the M7B compat pattern (unresolved → explicit
"unresolved" copy, never fabricated values). No continuity data reaches the
UI except through the documented endpoints; `WorkingStatePanel` /
`ApprovedTakePanel` / `RevisionList` remain untouched.

### 18.3 Frontend evidence

Vitest suite for every new component (authoring matrices, conflict/422/409
rendering, null-safety), `tsc` clean, production build clean. Backend-driven
contract tests may mock only at the fetch boundary (existing house pattern).

---

## 19. Query-shape gate at feature-film scale

The relation resolver must be set-oriented and count-independent (the M7B
7-vs-7 discipline):

- Shape: [dep-ids query] + [relations-of-the-Project-touching-the-deps
  query — `subject_entity_id IN dependency_ids OR object_entity_id IN
  dependency_ids`, the SAME OR predicate as the resolver (§7); endpoint
  classification is NOT a query filter — temporal winner resolution
  determines inactive/absent → irrelevant, active + both → effective,
  active + exactly one → endpoint-required issue] +
  [transitions-by-relation-ids query] + ordering load — a FIXED count of
  queries regardless of entity/relation/transition counts, using the
  existing partial indexes (`ix_continuity_relations_subject/object`,
  `ix_continuity_relation_transitions_relation`).
- Gate: at 2,500-shot / 2,500-dependency / 500-relation / 1,000-transition
  scale vs a 48-shot baseline, the per-resolution query COUNT is identical
  (7 vs 7 or better), asserted mechanically; wall-clock reported as
  evidence, not as a gate.
- Same discipline for the authoring list endpoints (bounded, indexed).

---

## 20. Scope exclusions (hard boundary)

- NO M8: no visual realization of any kind, no generation triggers beyond
  the existing pipeline, no visual identity.
- NO migration (head stays `0008`).
- NO change to continuity-spec schema 2 grammar beyond populating the
  frozen `relations` field; no schema-4; no snapshot form changes.
- NO second resolver, builder, ordering, hash, or historical authority.
- NO change to M6 v1/v2 selection or bytes; NO change to M7C feature
  capture semantics.
- NO relation PATCH (0008 has no mutable columns).
- NO error codes beyond the six frozen M7D codes (§12.2) and the existing
  vocabulary; no near-duplicates.
- Carried cleanups (canon.py unused import/param; busy-translation helpers
  → `db/sqlite.py`) remain OUT of M7D unless separately directed.

---

## 21. Source-gate proof matrix

Backend (new file `tests/test_m7d_relations.py` + extensions where seams
require):

1. Predicate CRUD: key grammar via the generic validation contract
   (valid/invalid matrix — NO predicate-specific validation code exists),
   tombstone-inclusive key conflict (`CONTINUITY_PREDICATE_KEY_CONFLICT`),
   non-recycle after delete, PATCH display-only + `key` immutable, DELETE
   `CONTINUITY_PREDICATE_IN_USE` / idempotent / unknown via the generic
   contract; relation-less predicate deletion as a sequential lifecycle
   regression.
2. Relation CRUD: `INVALID_CONTINUITY_RELATION` matrix (self relation,
   cross-Project endpoint, cross-Project predicate, missing/tombstoned
   predicate), `ENTITY_NOT_FOUND` for unresolvable endpoints,
   duplicate-active `CONTINUITY_RELATION_CONFLICT`, delete
   `CONTINUITY_RELATION_IN_USE` / idempotent, NO PATCH route (405 asserted).
3. RelationTransition create/PATCH matrix: anchor validation through the
   canonical ordering (all anchor types, cross-Project, unassigned Shot),
   coordinate conflicts, state flip, no-op PATCH.
4. Resolver: eligibility inclusivity (target /start eligible, /end not —
   APR-011), endpoint-classification matrix (neither → irrelevant; both →
   effective; exactly one → `CONTINUITY_RELATION_ENDPOINT_REQUIRED` with
   NULL hash/differs and blocked capture/generation), inactive-wins
   absence, winner selection, display order, unassigned + relevance →
   `NARRATIVE_CONTEXT_REQUIRED` (feature-only, relation-only, both;
   unassigned precedence over endpoint classification), dependency-removal
   consequence (mutation succeeds; Shot flips not-ready). The §12.4
   `readiness_issues` contract proven mechanically: ALL endpoint issues
   returned (multi-relation incompleteness), deterministic canonical
   ordering, exact element shape, `present`/`missing` fields correct, the
   strict 409 carrying the same ordered set, default-empty when ready.
5. Spec bytes: exact-bytes fixtures for populated relations (multiple
   predicates/entities; canonical order incl. `relation_id` tiebreak;
   anchor triples), schema-selection identity for relation-only states
   (2→3 promotion), empty-relations byte-identity with M7C output.
6. Capture: relation-state rows persisted exactly; parent+children atomic;
   hash changes on relation mutation with no Shot-row change (M6-F15
   extension); M6 v1/v2 byte preservation re-run; M7C feature-path
   regression.
7. Reuse integrity: relation-set corruption matrix (UPDATE-restore loop;
   enum of field corruptions incl. predicate_key) → invariant; positive
   control after restore.
8. Historical: rebuilt relations projection + transition audit; pre-M7D
   legacy revision 200 + byte-identical projection; relations-container
   corruption → invariant.
9. Rerun: succeeds with BOTH resolvers disabled (mechanical raise-spies).
10. Guards: §13.3 entity guard (subject and object variants); §13.5 all
    four anchor guards + the corrected Project cascade (RelationTransitions
    → Relations → Predicates tombstoned under one fence/one `db_now`;
    historical rows untouched) with the invariant-chain postcondition —
    after a legal Project deletion, `active Relation ⇒ active subject ⇒
    active object ⇒ active Predicate` still holds over all remaining
    active rows; dependency removal NOT blocked (flips not-ready instead).
11. Concurrency: R1–R11 (§15) barrier-forced; singularity spy+AST scans
    extended.
12. Scale: §19 count-identity gate.
13. APR-072: every test name states what is mechanically proven; sequential
    tests never carry race names.

Frontend: §18.3.

---

## 22. Evidence and closure

- Full backend suite ×2 consecutive green (expected ≥ 864 + new).
- Dedicated M7D file green; `python -m compileall` independently reproduced.
- Frontend: vitest + tsc + production build green.
- FULL-tree zip `SoloRing-M7D-rN.zip` (never a delta), delivered with SHA-256
  and file count; ledger regenerated from the written archive.
- Honest gap list in every delivery report; "No gaps." only when true.

---

## 23. Engineering sequence

Authorized slice-by-slice only (each slice lands runnable + tested):

- **M7D-1** Predicates + Relations services/API (§4–§5) + tests (21.1–21.2).
- **M7D-2** RelationTransitions + effective relation resolver + combined
  readiness + continuity-state response (§6–§7, §12) + tests (21.3–21.4).
- **M7D-3** Capture extension: builder population, schema rule, fenced
  persistence, reuse integrity, working hash, historical read path, byte
  preservation (§8–§11) + tests (21.5–21.8).
- **M7D-4** Lifecycle guards + cascade + concurrency matrix + scale gate +
  rerun proof (§13–§15, §19) + tests (21.9–21.12).
- **M7D-5** Frontend authoring/inspection UI (§18) + frontend evidence.

Each slice: branch `m7d/<slice>`, no push/PR until the source gate closes,
squash-only publication per the standing git policy.

---

## 24. Decisions — RESOLVED (2026-08-19 review; record)

- **D-1 — frozen M7 error codes: RESOLVED.** The six remaining M7 codes are
  exactly `CONTINUITY_PREDICATE_KEY_CONFLICT`, `CONTINUITY_PREDICATE_IN_USE`,
  `INVALID_CONTINUITY_RELATION`, `CONTINUITY_RELATION_CONFLICT`,
  `CONTINUITY_RELATION_IN_USE`, `CONTINUITY_RELATION_ENDPOINT_REQUIRED`
  (routing table in §12.2). The draft's `INVALID_CONTINUITY_PREDICATE` and
  `CONTINUITY_PREDICATE_NOT_FOUND` are removed and must never appear.
  `CONTINUITY_ANCHOR_PROJECT_MISMATCH` stays anchor-only. No seventh M7D
  code. The presence of `CONTINUITY_RELATION_ENDPOINT_REQUIRED` drove the
  load-bearing correction: endpoint completeness is a readiness/capture
  invariant (§5.3, §7, §7.1), not silent non-participation.
- **D-2 — APR register: RESOLVED.** The register is the standalone project
  architecture artifact (deliberately not committed). §2 binds the actual
  M7D mapping — PRIMARY 010/011/012/013/015/017/030/031/044/050/051,
  INHERITED M7C invariants, APR-072 as audit method. The register is NOT
  added to the repository delta.
- **D-3 — UI scope: CONFIRMED as the FULL M7 surface.** M7D-5 includes
  Feature definitions, FeatureTransitions, Predicates, Relations,
  RelationTransitions, current effective Feature + Relation state, and
  historical Feature + Relation provenance. The M8 hard boundary stays:
  no visual anchors, no images/reference realization, no model
  conditioning, no continuity rendering.
- **D-4 — Relation PATCH: CONFIRMED ABSENT.** Relation identity is
  (project, subject, predicate, object, relation_id); 0008 supplies no
  mutable display fields; POST / GET / DELETE only. Changing subject,
  predicate, or object means delete-old + create-new = a NEW relation
  identity. Relation temporal state mutates through RelationTransition
  PATCH. No migration.

Remaining before implementation authorization: the document-level freeze
pass only.

---

## 25. The resulting architecture

```text
                        ┌──────────────────────────────────────────┐
                        │ ONE canonical narrative ordering          │
                        │ narrative/order.py (untouched)            │
                        └───────────────┬──────────────────────────┘
                                        │
              ┌─────────────────────────┴─────────────────────────┐
              │ ONE consistent read unit (explicit BEGIN)          │
              │ deps + features + relations + ordering             │
              └───────────┬─────────────────────────┬─────────────┘
                          │                         │
             ONE feature resolver         ONE relation resolver
             (state.py, unchanged)         (state.py, NEW — touch-OR selection
                                           → winner at Shot/start
                                           → endpoint classification)
                          │                         │
                          └────────────┬────────────┘
                                       │
              not-ready: NARRATIVE_CONTEXT_REQUIRED
              or CONTINUITY_RELATION_ENDPOINT_REQUIRED
              → NULL hash/differs, capture + generation blocked
              (incomplete current state ≠ canonical absence)
                                       │
                        ONE canonical builder (extended)
                        schema 1 | 2 | 3 — spec 2, relations populated
                                       │
                        ONE fenced write unit (extended)
                        parent → M6 deps → feature states → relation states
                                       │
                        immutable ShotRevision history
                                       │
              Generation / Exact Rerun (history only, both resolvers unneeded)
                                       │
              Historical provenance (captured-row-only, both kinds)
                                       │
              M7 authoring/inspection UI (M8 boundary respected)
```

M7 closes with M7D: Features and Relations — the two halves of narrative
state — share one ordering, one read, one builder, one write unit, one
history, and one user surface. Visual identity remains exactly where the
milestone sequence put it: M8, unauthorized.
