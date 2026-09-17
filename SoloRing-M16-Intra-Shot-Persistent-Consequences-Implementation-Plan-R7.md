# SoloRing M16 — Intra-Shot Persistent Consequences
## G5 Source-Fit + Implementation Plan R7

**Date:** 2026-09-17  
**Status:** R7 freeze candidate — direct-review working-hash contradiction correction (successor revision; frozen R6 remains the immutable referent for M16-P0 through the M16-D third correction); G5 architecture closed for plan design; **NOT implementation authorization**  
**R7 delta record:** 57 lines / 3863 bytes / SHA-256 `d6a8d6a94dc20776bf53395fc6b65c9d5b266a8de6476f02800ae978e0aff5aa`  
**Predecessor plan:** frozen R6 — SHA-256 `cef6a82b4101df1f61a814e54df9d9d8fcffea1a14335ee8ef1c479eeadf839d` (127,396 B / 2,791 L)  
**Milestone:** M16 — Intra-Shot Persistent Consequences  
**Published predecessor:** M15 / **EVOLVE THE WORLD** @ `30ea135f3b2339491e9b36eaee2d0d8bc4ab8585`  
**Predecessor tree:** `db21568a3522a5ed2fa6fab44d1f9741d6d71ad2`  
**Predecessor parent:** `3d166bb320f3686e913faf1fa613bd05429320f7`  
**Predecessor annotated tag:** `M15`  
**Predecessor annotated tag object:** `4c83eaaaee9c1099512ce01ed9567d737ebee1c9` (**unsigned**)  
**Predecessor Release:** GitHub Release `388490752`  
**Predecessor PR-head CI:** `#79 / 34851439162` — success  
**Predecessor post-merge CI:** `#80 / 34855331701` — success  
**Current migration head:** `0016_m15_revision_compatibility`  
**Proposed M16 migration:** `0017_m16_intra_shot_consequences`

**Normative foundation**

| Artifact | SHA-256 |
|---|---|
| Architecture Pattern Register v2.5 | `1da9fe2b957a19015d275b076732bc1c42c7f0cf789dc4b05647fcf0914a69a0` |
| Product & Production Architecture v1.6 | `d93125ceed1e24dcbc86e88e5dfb42b02d7352bec5240ef9d75a5423c1a24077` |
| Capability & Ownership Map v1.6 | `e6411f8725f706f11168585490e5fd9525a63e85a5756552964745eec6e51d88` |
| Gap & Dependency Graph v1.6 | `b3ec6ee1b2bddeec9ba18ce393da87e041592bb42fa9a478980c28666031457c` |
| Implementation Roadmap v1.4 | `1e478a5b6ca49e7e56594a2e241938fa3c96a1fdc3bb39b49f2e033d3c64ed40` |
| Full-Sequence Product Pressure Test v1.6 rerun | `215ee3e5037690d82ccec15925999f7d1cea2b2bb890138995c90d82724971e9` |

**Freeze rule:** A freeze review MUST `obtain the exact six artifacts → hash their bytes → compare against the pinned SHA-256 values → fail if any byte identity differs`. A reviewer who lacks the artifacts records `EVIDENCE_SET_INCOMPLETE` — not `NORMATIVE_PIN_INVALID` — and MUST NOT substitute older APR / Architecture / Map / Graph / Roadmap / Pressure-Test revisions merely because those are locally available.

---

# 0. Executive decision

M16 implements the first production-grade authority contract for a continuity-significant state change that happens **inside** one Shot while preserving a distinct, explicit decision about what persists after the Shot.

The architecture is:

```text
canonical Shot/start state
        ↓
sparse Shot-relative state event at 0 < time_ms < duration_ms
        ↓
deterministic intra-Shot state fold
        ↓
terminal pre-boundary state at Shot/end−
        ↓
optional explicit persistence review/adoption
        ↓
existing owning-domain Shot/end transition
        ↓
ordinary downstream M7/M13 state resolver
```

The event answers **when the state changes inside the Shot**. The existing boundary-transition domain answers **what subsequent story-time inherits**.

M16 does **not** create a second persistent-state engine. Entity feature handoffs reuse `continuity_feature_transitions`; entity relation handoffs reuse `continuity_relation_transitions`; Production Instance feature handoffs reuse `production_instance_feature_transitions`. The persistent transition remains A2 authority. Intra-Shot event timing is the new A7-side authority described by APR-102.

M16 also freezes a candidate/evidence path for generated or analyzed event proposals. A proposal is not authority. Approving a Take remains canon selection only and does not create, adopt, or modify an intra-Shot event or persistent state.

M16 closes when SoloRing can prove, for both an entity-bound and an instance-bound subject:

> The Shot captures its true start state, applies a sparse deterministic event only after time zero, preserves the resulting terminal state separately from Shot/start truth, explicitly adopts any downstream-persistent consequence into the existing Shot/end transition domain, resolves that state in later Shots, and leaves prior ShotRevisions/Generations/Takes exactly unchanged.

The milestone does **not** claim that the current generative executor is able to visually realize arbitrary event timing. M16 is the authority/capture/review handoff required before the later Performance/Dialogue execution program can consume exact temporal authority.

---

# 1. G5 disposition

## 1.1 Proposed gate result

**Proposed disposition: G5 CLOSED FOR PLAN DESIGN.**

All seven roadmap questions have source-fit answers that can be implemented without introducing a conflicting authority domain.

This R6 is a **freeze candidate**. G5 architecture is closed for plan design, but this document is not a frozen implementation contract until explicitly accepted/frozen. M16 implementation remains unauthorized.

## 1.2 G5-1 — Shot-relative timing representation

The authoritative time coordinate is:

```text
time_ms: plain JSON integer
```

Rules:

```text
1 <= time_ms < duration_ms
```

There are no authoritative aliases in frames, floating seconds, wall-clock time, edit-timeline time, or executor sample index.

`bool` is not an integer for grammar purposes. Floating-point JSON numbers are invalid even when mathematically integral.

Events at exactly `time_ms = 0` are invalid. Shot/start is owned by the existing Shot/start boundary transition/resolver.

Events at exactly `time_ms = duration_ms` are also invalid in M16 v1. The duration endpoint is the Shot/end boundary; a change that exists only at that boundary belongs in the existing Shot/end transition domain. A genuine intra-Shot event is strictly interior to the Shot interval.

Events sharing one millisecond use an explicit nonnegative integer `ordinal`. Active event coordinates are unique by:

```text
(shot_id, time_ms, ordinal)
```

Semantic order is exactly:

```text
(time_ms ASC, ordinal ASC)
```

UUID, creation timestamp, SQL row order, and API arrival order never break ties.

## 1.3 G5-2 — Authoritative Shot duration

The duration source is the existing `shots.duration_ms` field for current working-state validation and the exact captured ShotRevision `intent.duration_ms` for historical evaluation.

Published source permits:

```text
duration_ms = NULL
or
duration_ms >= 0
```

M16 does **not** globally tighten that predecessor contract.

Instead:

```text
no active M16 events
    → existing NULL/0/positive duration semantics remain legal

>=1 active M16 event
    → duration_ms MUST be a plain integer > 0
    → each event MUST satisfy 1 <= time_ms < duration_ms
```

Therefore M16 authoring never commits an active event against `duration_ms = NULL` or `0`: event create/patch is rejected, and a duration patch that would produce that state conflicts. If corrupted/unsupported direct database state nevertheless contains active events with unusable duration, the resolver fails closed with `INTRA_SHOT_DURATION_REQUIRED`.

No migration backfills invented durations.

## 1.4 G5-3 — Shot/start versus genuine intra-Shot semantics

Shot/start remains exactly the existing current-state resolution boundary.

For a target Shot:

```text
state_at(0) = exact M7/M13 resolved Shot/start state
```

No M16 event may alter `state_at(0)`.

For `0 < t < duration_ms`:

```text
state_at(t)
  = deterministic fold of active events with event.time_ms <= t
    over the exact resolved Shot/start state
```

The terminal intra-Shot state is:

```text
terminal_state = state_at(duration_ms - epsilon)
```

Operationally, this is the fold after all valid M16 events, because every event is strictly earlier than `duration_ms`.

The explicit Shot/end transition is then a separate boundary fact. If persistence is intended, its semantic result must equal the terminal state exactly.

## 1.5 G5-4 — Terminal-state equality

Equality is canonical semantic equality, not row-id or UI-label equality.

M16 v1 supports three state-event target kinds:

```text
ENTITY_FEATURE
ENTITY_RELATION
PRODUCTION_INSTANCE_FEATURE
```

This covers the roadmap/architecture cases:

```text
Eva injury / wardrobe / condition              → ENTITY_FEATURE
item leaves a character's possession           → ENTITY_RELATION
chair-07 configuration / damage / state         → PRODUCTION_INSTANCE_FEATURE
```

For `ENTITY_FEATURE` and `PRODUCTION_INSTANCE_FEATURE`, equality is exact over:

```text
same exact feature identity
same presence/absence state
if present:
    same canonical value JSON
    same canonical value hash
    same captured value type/unit semantics
```

For `ENTITY_RELATION`, equality is exact over:

```text
same exact relation identity
same active/inactive terminal state
```

If an event is marked `persistence_mode = REQUIRE_HANDOFF`, it must be the terminal event for that exact target in the active event set. A later event on the same target makes the earlier persistence marker invalid rather than silently redefining its consequence.

The required handoff is the active existing transition at:

```text
anchor_type = shot
anchor_id   = this Shot id
boundary    = end
```

with the exact same feature/relation/instance-feature identity and terminal semantic state.

No fuzzy comparison, enum-label alias, unit coercion, semantic model interpretation, or “close enough” value is accepted.

## 1.6 G5-5 — Readiness versus capture fence

M16 extends the existing current-state read/capture seam; it does not invent an independent canonicalizer and it does **not** silently redefine predecessor readiness fields.

The resolution order is:

```text
existing Shot/current-state read snapshot
        ↓
M7 entity feature + relation Shot/start resolution
        ↓
M8 visual readiness
        ↓
M10 spatial readiness
        ↓
M13 Production World + Production Instance Shot/start state when selected
        ↓
M16 event resolver/fold/handoff validator
        ↓
one canonical Shot snapshot builder
        ↓
working snapshot hash / ShotRevision capture
```

If an earlier predecessor domain is not ready, M16 does not fabricate a derived interpretation from incomplete start state. Existing predecessor issue precedence remains intact.

M16 introduces a dedicated projection:

```text
intra_shot_ready
intra_shot_issues[]
intra_shot_duration_ms
events[]
terminal_targets[]
handoffs[]
```

Published `continuity_state_ready` keeps its predecessor M7 meaning. M16 does not broaden that field to depend on M13 and thereby invert the existing resolver layering. Instead, the working-snapshot/capture gate requires all applicable predecessor layers **and** `intra_shot_ready`; when M16 is not ready there is no authoritative working snapshot hash.

M16 current readiness fails closed for at least:

```text
INTRA_SHOT_DURATION_REQUIRED
INTRA_SHOT_TIME_OUT_OF_RANGE
INTRA_SHOT_EVENT_COORDINATE_CONFLICT
INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH
INTRA_SHOT_TARGET_INVALID
INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL
INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED
INTRA_SHOT_HANDOFF_REQUIRED
INTRA_SHOT_HANDOFF_MISMATCH
```

The same pure M16 resolution object is consumed by:

```text
Shot detail/readiness
working snapshot hash
ShotRevision capture
historical-capture projection tests
UI status
```

Capture does not have a second interpretation.

## 1.7 G5-6 — Persistent-consequence adoption is independent of Take approval

The existing Take approval contract is preserved literally:

```text
approve Take
    → set shots.approved_take_id
    → never rewrite creative/continuity state
```

M16 adds no call from the Take approval endpoint into event or persistence services.

Two lawful workflows exist.

### Authored-authority path

```text
author event
    ↓
if transient: event may be capture-ready immediately
if REQUIRE_HANDOFF: event is not capture-ready until handoff adoption/agreement
    ↓
explicit Adopt persistence
    ↓
existing Shot/end transition created or exact existing one accepted
    ↓
future capture includes event + handoff
```

### Post-Take proposal path

```text
Generation/Take from an older immutable ShotRevision
    ↓
analysis/user proposes event timing + consequence
    ↓
proposal remains evidence only
    ↓
Take may be approved or rejected independently
    ↓
explicit consequence review
    ├─ Ignore
    ├─ Adopt event only (transient)
    └─ Adopt event + persistence
          ↓
      authoritative event + exact Shot/end handoff created atomically
```

Adopting after a Take was generated does not rewrite that Take or its Generation. The working Shot may then differ from the approved Take's captured ShotRevision, which is exactly the existing `working_state_differs_from_approved` model.

## 1.8 G5-7 — Provenance for downstream-proposed timing/consequences

A downstream proposal is immutable evidence and pins at minimum:

```text
proposal id
Shot id
canonical proposal JSON + SHA-256
source kind
source ShotRevision id + snapshot hash
source Generation id when Generation-backed
source Take id when Take-backed
proposer kind: human | analyzer
analyzer id + version when proposer kind = analyzer
analyzer parameter hash when proposer kind = analyzer
created_at
```

The canonical `proposal_json` is the retained proposal output and follows the frozen Proposal Grammar v1 in §4.9. One proposal represents exactly one candidate event. An analysis that proposes several events emits several immutable proposal rows sharing the same exact source ShotRevision basis; §12.3 provides an atomic multi-proposal review path so adopting the first candidate does **not** make sibling candidates stale merely because M16 authority was created earlier in the same review transaction.

M16 v1 does not accept an opaque analyzer-output hash whose bytes are not retained anywhere. Canonical `proposal_json` is limited to **65,536 UTF-8 bytes**. If a later analyzer needs larger retained evidence, it must use an existing retained Blob/Asset path or a separately reviewed storage extension.

For Generation/Take-backed proposals:

```text
proposal.source_shot_revision_id
    MUST equal Generation.shot_revision_id

proposal.source_shot_revision_hash
    MUST equal the immutable ShotRevision.snapshot_hash

Take.shot_id
Generation.shot_id
proposal.shot_id
    MUST agree

if source_take_id is present:
    Take.generation_id MUST equal source_generation_id
```

`source_kind = imported` means evidence entered from outside SoloRing's Generation/Take lineage while still being interpreted against one exact existing source ShotRevision. Imported evidence therefore has no Generation/Take ids but still pins `source_shot_revision_id/hash`; it is not an unversioned or current-state proposal.

For `proposer_kind = analyzer`, `analyzer_id`, `analyzer_version`, and `analyzer_parameters_hash` are always required. An analyzer with no parameters hashes canonical `{}`. There is no subjective “materially determinative” exception.

Proposal creation validates time against the source ShotRevision's captured duration, never today's Shot duration.

Proposal existence does not affect readiness, capture, working snapshot identity, or downstream state.

Adoption revalidates against current authority and fails stale rather than silently rebasing a proposal onto changed truth. The v1 no-rebase basis is explicit: before any adopted event is created, the transaction requires the current effective working snapshot hash to equal the proposal set's pinned source ShotRevision snapshot hash. A NULL/unready current working hash is stale for adoption. Because `duration_ms` is part of the Shot snapshot intent, this equality also proves that the current duration has not drifted from the source duration; adoption still rechecks each candidate time against the current duration defensively.

For a batch of sibling proposals, the source-basis equality check runs **once at transaction start**, before any event/handoff mutation. The full prospective event set containing every selected adopted candidate is then validated atomically. This is the M16-v1 answer to multi-event analysis of one Take; M16 does not impose a one-event-per-capture-cycle workflow.

# 2. Source-fit findings against published M15

## 2.1 SF-01 — Existing duration authority is usable without a predecessor schema change

Published M15 source already has `Shot.duration_ms` as nullable integer with database/API domain `NULL or >= 0`.

M16 therefore needs no alteration of `shots` and no duration backfill. It only adds the conditional readiness rule that active genuine intra-Shot events require a positive duration.

**Disposition:** FIT.

## 2.2 SF-02 — Existing Shot/start state resolution is the correct start boundary

The published M7 resolver already resolves active transitions by canonical narrative rank with inclusive eligibility through target Shot/start. Prior Shot/end transitions therefore feed downstream Shot/start state while target Shot/end does not project backward into the Shot start.

M16 must fold over that result rather than modifying its rank law.

**Disposition:** FIT; reuse required.

## 2.3 SF-03 — Existing transition tables are the correct persistent handoff owners

The published source already provides:

```text
continuity_feature_transitions
continuity_relation_transitions
production_instance_feature_transitions
```

Each supports a Shot/end anchor. M16 does not need an additional persistent-handoff table.

M16 adoption must use shared authoring/canonicalization helpers for those existing tables so the API path and M16 path cannot acquire independent transition semantics.

**Disposition:** FIT; reuse required.

## 2.4 SF-04 — Capture already has the required one-read-snapshot seam

Published ShotRevision capture resolves the Shot, semantic dependencies, M7 state, visual state, spatial state, and M13 production-world state from one explicit SQLite read snapshot before constructing the canonical captured value.

M16 must join that same read unit. It must not perform an event query after the canonical builder or on another connection.

**Disposition:** FIT; extension required.

## 2.5 SF-05 — ShotRevision snapshot history is the correct A7 extension point; M7 continuity-spec ownership must stay narrow

Published `shot_revisions` already owns the canonical immutable Shot snapshot (`snapshot_json` / `snapshot_hash`) and the M6/M7 continuity sub-spec (`continuity_spec_json` / `continuity_spec_hash`).

The continuity sub-spec is specifically the predecessor A1/A2 entity-dependency/Feature/relation contract. M16 event timing is A7 authority and can also target M13 Production Instance state. Therefore M16 must **not** widen `continuity_spec_json` into a cross-domain A7 container.

M16 extends the outer Shot snapshot instead:

```text
published lower snapshot schema 1–6
        +
non-empty top-level intra_shot block
        ↓
outer snapshot schema 7
```

The existing continuity spec remains exactly schema 1/2. Historical M16 evidence is stored in dedicated immutable A7 companion rows sufficient to rebuild the top-level `intra_shot` block without consulting current state.

**Disposition:** FIT; outer Shot snapshot extension + dedicated immutable A7 companion required.

## 2.6 SF-06 — Take approval is already correctly isolated

Published `approve_take()` selects canon by assigning `shots.approved_take_id` and explicitly states that approval never rewrites creative state.

M16 must leave that endpoint behavior unchanged.

**Disposition:** FIT; negative regression required.

## 2.7 SF-07 — Pre-existing recovery succession defect is a P0 implementation prerequisite

Published recovery accepts restore head `0016_m15_revision_compatibility`, but its restore verification dispatch still falls through the generic `else:  # 0014` branch for 0014/0015/0016 and verifies only M11/M12/M13 world state.

Consequently, M15's own compatibility/update immutable evidence is not re-derived during restore verification at head 0016.

M16 must **not** advance recovery directly from this state to a nominal 0017 verifier. The first implementation slice must close head-specific recovery succession:

```text
0014 → verify through M13
0015 → verify M13 + M14 observation history
0016 → verify M13 + M14 + M15 compatibility/update history
0017 → verify all predecessor history + M16 event/proposal/review history
```

This is a pre-existing predecessor defect discovered by source fit. It is not an M16 product-semantic change, but it blocks M16 historical-closure certification if left unresolved.

**Disposition:** BLOCKING SOURCE-FIT CORRECTION — include as M16-P0 before M16 data-plane closure.

## 2.8 SF-08 — Adjacent M15 exact-retry response defect must not be copied

Published M15 `apply_revision_update()` still reconstructs an exact-retry response with:

```text
translator_id = None
translator_version = None
translator_parameters_hash = None
```

while retaining only `translator_output_hash` from the committed item.

This is adjacent to M16 because M16 should reuse the **transaction/idempotency pattern**, not the result-projection bug.

It does not block G5 or M16 event authority, but repository-wide review debt is not literally zero while it remains.

**Disposition:** NON-BLOCKING M16 SOURCE-FIT WARNING; separate correction authorization recommended.

## 2.9 SF-09 — Published historical continuity inspection stops before the current outer snapshot schema

The published historical continuity inspector accepts continuity-spec schemas 1/2, but its outer ShotRevision snapshot guard still accepts only snapshot schema versions 1–5 even though published M13 capture can emit schema 6 Production World snapshots.

M16 must not layer schema-7 history on top of an inspector that rejects published schema-6 history. M16-C therefore includes a predecessor-compatibility correction:

```text
schema 1–5 → preserve exact existing historical behavior
schema 6   → accept and validate the published M13 outer shape
schema 7   → accept only the new M16 event-bearing shape
```

The correction must remain historical-only: it may not reconstruct schema-6/7 meaning from current Production World or current M16 state.

**Disposition:** BLOCKING HISTORICAL-INSPECTOR CORRECTION BEFORE M16-C CLOSURE.

## 2.10 SF-10 — Event-bearing ShotRevisions require an explicit execution fence

Published generation orchestration has explicit handling for predecessor snapshot schemas, including schema-6 observation execution. No published workflow package consumes M16 Shot-relative event authority.

Therefore an event-bearing M16 ShotRevision may be captured and reviewed, but it must not silently execute through a lower-schema workflow that ignores the event timing.

M16 adds a generation-creation fence before any Generation row is persisted:

```text
snapshot schema 7 with non-empty intra_shot authority
    → INTRA_SHOT_REALIZATION_UNSUPPORTED (409)
    → no Generation publication / queueing
```

This is an orchestration fence, not event realization. Executor pins, Comfy graphs, materializers, and workflow artifact formats remain unchanged in M16.

**Disposition:** FIT WITH REQUIRED FAIL-CLOSED GENERATION FENCE.

---

# 3. Authority boundaries

## 3.1 What M16 owns

M16 owns:

```text
A7-side sparse Shot-relative timing authority for state-changing events
C2-side proposal/review/adoption operation records
capture/history projection of that event authority
```

APR-102 is the load-bearing authority pattern: A7 answers **when inside the Shot**; A2 continues to answer **what story-time persists across a boundary**.

## 3.2 What M16 does not own

M16 does not replace:

```text
M7 CreativeEntity feature state
M7 CreativeEntity relation state
M13 Production Instance feature state
M10/M13 spatial authority
M12 occurrence identity
M14 observation/execution authority
M15 Production Revision compatibility/evolution authority
Take approval / canon selection
```

M16 relies on the published M15 invariant that a compatible Production Revision update preserves stable occurrence identity and existing Production Instance feature/transition rows. A PI-feature event is therefore anchored to the same occurrence/feature identity across a lawful M15 revision update; M16 never re-mints the occurrence or shadows it with CreativeEntity state.

## 3.3 Generated pixels remain evidence

Generated pixels, analyzer output, and imported evidence may propose:

```text
time
before/after state
persistence suggestion
```

They may not create an authoritative event or persistent transition automatically.

Take approval remains canon selection only. Proposal review and persistent-consequence adoption are separate explicit authority operations.

# 4. Canonical event grammar v1

## 4.1 Shared strict integer domain

Every M16 integer that crosses JSON (`time_ms`, `ordinal`, positions/counts where applicable) is a **plain JSON integer**, not `bool`, float, numeric string, Decimal wrapper, or exponent form.

Unless a narrower field rule applies:

```text
0 <= value <= 9_007_199_254_740_991
```

(the JavaScript-safe integer maximum). `time_ms` has the stricter interior rule in §1.2; `ordinal >= 0`.

## 4.2 Supported target kinds

Exactly:

```text
entity_feature
entity_relation
production_instance_feature
```

No spatial trajectory, body pose, deformation curve, arbitrary action label, universal relationship ontology, dialogue alignment, or executor control stream is introduced by M16.

## 4.3 Event identity semantics

Three identities remain distinct:

```text
event UUID       = durable working-authoring row identity
event_hash       = canonical semantic content identity of the current row
(time_ms,ordinal)= ordering coordinate inside one Shot
```

PATCH preserves the event UUID but recomputes semantic JSON/hash. A captured ShotRevision records the source event UUID as audit provenance, but source UUID is not a semantic tie-breaker and does not participate in the outer Shot snapshot hash.

If an event created by `proposal_adoption` is later semantically patched (time, ordinal, target, before, after, or persistence mode), the current row becomes authored authority:

```text
source_kind       = authored
source_proposal_id = NULL
```

The immutable review row and any prior captured ShotRevision retain the original proposal provenance. Display-only edits do not exist on the M16 event row.

Two different working event UUIDs with identical canonical semantics are allowed at different times in repository history. ShotRevision convergence is semantic (§14.4), not based on whichever working UUID happened to produce the bytes first.

## 4.4 Canonical state grammar

### Feature state

Canonical absence:

```json
{"present":false}
```

Canonical presence:

```json
{
  "present": true,
  "value": <canonical value>,
  "value_hash": "<64-lowercase-hex>"
}
```

The value is canonicalized against the exact live feature schema during current authoring/resolution. Captured target identity freezes `value_type` and `unit`; captured history re-canonicalizes from those immutable fields and never consults today's feature schema.

### Relation state

```json
{"active":false}
```

or:

```json
{"active":true}
```

## 4.5 Canonical semantic event value

```json
{
  "schema_version": 1,
  "time_ms": 3100,
  "ordinal": 0,
  "target": {
    "kind": "entity_feature",
    "id": "<feature UUID>"
  },
  "before": {"present": true, "value": "none", "value_hash": "..."},
  "after": {"present": true, "value": "fresh", "value_hash": "..."},
  "persistence_mode": "require_handoff"
}
```

The event hash is SHA-256 of canonical JSON bytes for exactly this semantic value. Database IDs other than the explicit target id, timestamps, labels, source proposal ids, and transition ids are not semantic tie-breakers.

## 4.6 Before-state precondition and persistence mode

Every authoritative event carries an exact `before` state. During the deterministic fold:

```text
folded current target state == event.before
```

must hold before applying `event.after`.

`before` and `after` must differ semantically. No-op events are invalid.

Persistence mode is exactly:

```text
transient
require_handoff
```

If `require_handoff` is selected:

- this event must be the final event for its exact target;
- the Shot must have a valid narrative Shot/end boundary;
- an exact active Shot/end transition must exist for capture readiness;
- that transition must semantically equal the event's terminal `after` state.

If a later event is authored on the same target, an earlier `require_handoff` marker makes the **prospective set invalid**. The write is rejected with `INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL`; the user must first PATCH the earlier event to `transient` or otherwise change the set deliberately. The UI must surface that recovery action rather than a dead-end error.

If `transient` is selected, M16 imposes no handoff equality requirement. An independently authored Shot/end transition may still exist because A2 owns boundary state separately; it may represent a distinct boundary-only change. M16 never interprets mere coordinate coincidence as persistence adoption.

## 4.7 Captured target-identity grammar v1

Every captured schema-7 event carries a canonical `target_identity` object. This is part of the immutable `intra_shot` semantic block and therefore part of `ShotRevision.snapshot_hash`.

Entity feature:

```json
{
  "kind": "entity_feature",
  "feature_id": "<uuid>",
  "entity_id": "<uuid>",
  "feature_key": "<frozen key>",
  "feature_kind": "<frozen M7 kind>",
  "value_type": "<boolean|enum|integer|decimal|text>",
  "unit": null
}
```

Entity relation:

```json
{
  "kind": "entity_relation",
  "relation_id": "<uuid>",
  "subject_entity_id": "<uuid>",
  "predicate_id": "<uuid>",
  "predicate_key": "<frozen key>",
  "object_entity_id": "<uuid>"
}
```

Subject/object direction is semantic and is never normalized by swapping endpoints.

Production Instance feature:

```json
{
  "kind": "production_instance_feature",
  "feature_id": "<uuid>",
  "composition_id": "<uuid>",
  "occurrence_id": "<uuid>",
  "authority_subject_kind": "production_instance",
  "feature_key": "<frozen key>",
  "feature_kind": "<frozen M7-equivalent kind>",
  "value_type": "<boolean|enum|integer|decimal|text>",
  "unit": null
}
```

`unit` is either null or the exact captured unit. Historical feature value validation uses these captured fields only. Relation history uses the captured predicate identity/key and directional endpoints only; current relation/predicate rows are never required for semantic reconstruction.

`authority_subject_kind` is a captured-JSON field mapped one-to-one from the predecessor relational source `composition_occurrence_authority_subjects.subject_kind`, preserving the predecessor's closed semantic vocabulary (`creative_entity` | `production_instance`). It does not rename the predecessor database column and does not create a second authority-subject classification. The §27 source-fit validator must check this exact mapping.

## 4.8 Captured handoff grammar v1

Transition row UUID is **audit provenance**, not handoff semantic identity. The captured semantic handoff embedded in `intra_shot` is:

Feature / Production Instance feature:

```json
{
  "domain": "entity_feature",
  "target": {"kind":"entity_feature","id":"<feature uuid>"},
  "anchor": {"anchor_type":"shot","anchor_id":"<shot uuid>","boundary":"end"},
  "operation": "set",
  "state": {"present":true,"value":"fresh","value_hash":"..."}
}
```

`operation` is exactly predecessor `set|clear`; `clear` corresponds to canonical `{"present":false}`.

Entity relation:

```json
{
  "domain": "entity_relation",
  "target": {"kind":"entity_relation","id":"<relation uuid>"},
  "anchor": {"anchor_type":"shot","anchor_id":"<shot uuid>","boundary":"end"},
  "state": "active"
}
```

Relation `state` is exactly predecessor `active|inactive`; M16 does not invent a set/clear alias for relation transitions.

## 4.9 Canonical Proposal Grammar v1

One proposal represents exactly one candidate event:

```json
{
  "schema_version": 1,
  "candidate_event": {
    "time_ms": 3100,
    "ordinal": 0,
    "target": {"kind":"entity_feature","id":"<feature uuid>"},
    "before": {"present":true,"value":"none","value_hash":"..."},
    "after": {"present":true,"value":"fresh","value_hash":"..."}
  },
  "persistence_suggestion": "persist"
}
```

`persistence_suggestion` is exactly:

```text
transient
persist
```

It is evidence, not authority. `persist` does not become `require_handoff` unless the reviewer explicitly chooses `adopt_persistence`; `adopt_event_only` always creates a `transient` authoritative event and the UI must state that the persistence suggestion is being discarded.

Proposal JSON does not contain authoritative event UUID, transition UUID, Take approval state, current Shot pointer, or mutable review result. Canonical JSON bytes are limited to 65,536 bytes.

Multi-event analysis is represented by multiple single-event proposals with the same source ShotRevision basis. They may be reviewed atomically through the batch adoption contract in §12.3.

# 5. Deterministic fold

## 5.1 Inputs

The fold consumes one immutable/current read value:

```text
Shot id
Shot duration_ms
exact resolved Shot/start entity feature state
exact resolved Shot/start relation state
exact resolved Shot/start Production Instance feature state when applicable
active M16 event rows
active existing Shot/end transitions for event targets
```

At most **10,000 active M16 events** may exist for one Shot. A write that would exceed this bound fails with `INTRA_SHOT_EVENT_LIMIT_EXCEEDED` before mutation.

## 5.2 Algorithm

1. If no active events, return `ready=true`, empty M16 projection, and do not require duration.
2. Require a plain integer `duration_ms > 0` when events exist.
3. Load all active events set-oriented.
4. Rebuild canonical event values and verify every duplicated stored event/state column against canonical JSON/hash.
5. Require unique `(time_ms, ordinal)`; UUID/timestamp order is irrelevant.
6. Require every `time_ms` in `[1, duration_ms - 1]`.
7. Resolve/verify every event target and its durable subject against the Shot's actual predecessor context:
   - entity feature owner must be an explicit current semantic dependency;
   - entity relation requires both directional endpoint entities in the dependency subgraph;
   - Production Instance feature must belong to a selected M13 `production_instance` occurrence captured by the current Production World.
8. Initialize fold state from exact Shot/start resolution.
9. Sort by `(time_ms, ordinal)`.
10. For each event, require folded state equals `before`; replace with `after`.
11. For each target, identify the terminal event.
12. Reject `require_handoff` on any nonterminal event for that target.
13. For a terminal persistent event, require a valid Shot/end narrative anchor and load the exact owning-domain active Shot/end transition.
14. Require exact target identity and exact terminal semantic equality under the predecessor transition vocabulary.
15. Return canonical ordered events, terminal target projection, handoff evidence, a canonical event-set hash, and readiness issues.

No database write occurs in the resolver.

The event-set hash is SHA-256 of canonical JSON bytes for:

```json
{
  "schema_version": 1,
  "shot_id": "<uuid>",
  "duration_ms": 5000,
  "events": [<canonical Event Grammar v1 values in canonical order>]
}
```

It is a current-authority/idempotency coordinate; the captured `intra_shot` block remains the ShotRevision semantic representation.

## 5.3 Structural event-set validity versus capture readiness

M16 deliberately distinguishes **authoring validity** from **capture readiness**.

Structural event-set validity includes:

```text
active event count <= 10,000
positive usable duration while events exist
interior time range
unique (time_ms, ordinal)
legal/active target and durable-subject membership
canonical before/after grammar
before != after
exact before-state chain agreement
require_handoff only on the terminal event for that target
```

Create/patch/delete and duration mutation may commit only if the prospective active event set remains structurally valid.

Therefore an active event combined with NULL/zero duration is **not a lawful authored state through M16 APIs**. POST/PATCH is rejected, and a duration PATCH that would create that condition conflicts. If the resolver nevertheless encounters it because of corruption or unsupported direct database mutation, it fails closed with `INTRA_SHOT_DURATION_REQUIRED`.

Capture readiness adds cross-domain handoff requirements:

```text
all predecessor layers ready
+ structural event-set valid
+ every require_handoff event has a valid Shot/end anchor
+ exact active owning-domain handoff exists
+ handoff semantic value equals terminal event state
```

This allows the intentional authored workflow:

```text
create valid require_handoff event
→ Shot becomes INTRA_SHOT_HANDOFF_REQUIRED / not capture-ready
→ filmmaker explicitly adopts persistence
→ exact A2 handoff created/adopted
→ Shot becomes capture-ready
```

A missing handoff is therefore a readiness blocker, not a reason to reject creation of an otherwise structurally valid event.

## 5.4 Complexity and frozen scale limits

Production queries must be set-oriented. No per-event SELECT loop is permitted.

Frozen v1 resource contracts:

```text
MAX_ACTIVE_EVENTS_PER_SHOT = 10,000
M16 resolver SQL statements = <= 20, independent of N for 1 <= N <= 10,000
GET event list page default = 100, maximum = 500
GET proposal list page default = 100, maximum = 500
proposal_json canonical UTF-8 bytes <= 65,536
proposal review batch proposals <= 10,000
```

The 10,000-event stress fixture uses minimal legal scalar values and must resolve without N+1 queries while staying within the exact SQL-statement ceiling. The service may reject a request above the hard count/byte limits; it may not degrade into unbounded materialization or per-event database traffic.

# 6. Persistence handoff mapping

## 6.1 Entity feature

Event target:

```text
continuity_features.id
```

Eligibility:

```text
feature is active
feature.owner entity is an explicit semantic dependency of this Shot
feature belongs to this Project
```

Handoff target:

```text
continuity_feature_transitions.feature_id = exact same feature id
anchor_type = shot
anchor_id   = this Shot id
boundary    = end
```

Terminal present state maps to predecessor `operation=set` plus exact canonical value. Terminal absence maps to predecessor `operation=clear`. No alternate transition representation may be treated as equivalent.

For a persistent event the Shot must be assigned into canonical narrative ordering so the Shot/end coordinate exists. A transient event may remain Shot-relative on an otherwise unassigned Shot only if its entity start state is still resolvable and no persistent handoff is claimed.

## 6.2 Entity relation

Event target:

```text
continuity_relations.id
```

Eligibility:

```text
relation identity is exact and historically durable
subject entity is an explicit Shot semantic dependency
object entity is an explicit Shot semantic dependency
predicate identity/key and subject/object direction remain exact
```

Handoff target:

```text
continuity_relation_transitions.relation_id = exact same relation id
anchor_type = shot
anchor_id   = this Shot id
boundary    = end
state       = active | inactive
```

Terminal active/inactive must equal the exact predecessor relation-transition `state`. Subject/object endpoints are directional and cannot be swapped to manufacture equivalence.

Both relation endpoints must belong to the Shot's semantic dependency subgraph for an authoritative intra-Shot relation event to be capture-ready. Persistent adoption additionally requires the Shot/end narrative coordinate to exist.

A relation/transition may later be soft-deleted or edited in current state without changing a prior ShotRevision's captured semantics. Historical meaning comes from captured target/handoff duplicates, not today's row values.

## 6.3 Production Instance feature

Event target:

```text
production_instance_features.id
```

Eligibility:

```text
feature is active
feature belongs to one exact occurrence
that occurrence is present in the selected current M13 binding
its M13 authority subject is exactly production_instance
its current Production World is ready
```

Handoff target:

```text
production_instance_feature_transitions.feature_id = exact same feature id
anchor_type = shot
anchor_id   = this Shot id
boundary    = end
operation   = set | clear
```

The feature must resolve to an M13 Production Instance authority subject/occurrence that is part of the current Shot's production-world context. The event's `before` state is authored against that exact current selected binding/context and is revalidated again at capture; changing the M13 selection may therefore invalidate the event chain rather than silently rebasing it.

No CreativeEntity fallback is allowed for an occurrence whose M13 authority subject is `production_instance`, and no shadow Production Instance event is allowed for a `creative_entity` authority subject.

Persistent adoption additionally requires the Shot/end narrative coordinate to exist.

# 7. Storage plan — migration 0017

M16 uses **five additive tables** and does not rebuild predecessor tables. The immutable parent table gives the A7 `intra_shot` block its own historical canonical identity instead of overloading the M7 continuity-spec columns.

## 7.1 `shot_intra_shot_events`

Working authoritative event rows.

Required columns:

```text
id UUID PK
shot_id UUID FK shots.id

time_ms INTEGER NOT NULL CHECK > 0
ordinal INTEGER NOT NULL CHECK >= 0

target_kind TEXT NOT NULL
entity_feature_id UUID NULL FK continuity_features.id
entity_relation_id UUID NULL FK continuity_relations.id
production_instance_feature_id UUID NULL FK production_instance_features.id

before_state_json TEXT NOT NULL
before_state_hash TEXT NOT NULL length=64
after_state_json TEXT NOT NULL
after_state_hash TEXT NOT NULL length=64

persistence_mode TEXT NOT NULL
source_kind TEXT NOT NULL                 # authored | proposal_adoption
source_proposal_id UUID NULL FK shot_intra_shot_event_proposals.id

event_json TEXT NOT NULL
event_hash TEXT NOT NULL length=64

created_at TEXT NOT NULL
updated_at TEXT NOT NULL
deleted_at TEXT NULL
```

Constraints:

- a database CHECK enforces exactly one target FK populated and consistent with `target_kind`;
- `persistence_mode IN ('transient','require_handoff')`;
- `source_kind IN ('authored','proposal_adoption')`;
- proposal source presence iff `source_kind='proposal_adoption'`;
- **partial** active unique index `(shot_id,time_ms,ordinal) WHERE deleted_at IS NULL`;
- M16 service exposes no hard-delete path; authoritative events are soft-deleted only;
- `time_ms`/`ordinal` obey the strict safe-integer service grammar in §4.1.

Cross-table time-vs-duration validation remains service-level because SQLite CHECK cannot safely own it.

## 7.2 `shot_revision_intra_shot_specs`

Immutable A7 parent companion for one event-bearing ShotRevision.

Required columns:

```text
shot_revision_id UUID PK FK shot_revisions.id
schema_version INTEGER NOT NULL CHECK = 1
duration_ms INTEGER NOT NULL CHECK > 0
spec_json TEXT NOT NULL
spec_hash TEXT NOT NULL length=64
```

The canonical value is exactly the top-level `intra_shot` block embedded in outer Shot snapshot schema 7. It is rebuilt from child rows and compared byte/hash-exactly; it is never reconstructed from current working events or current handoff transitions.

No row exists for an event-free ShotRevision.

## 7.3 `shot_revision_intra_shot_events`

Immutable captured event rows, child-owned by `shot_revision_intra_shot_specs`.

Required columns:

```text
shot_revision_id UUID
position INTEGER NOT NULL CHECK >= 0
source_event_id UUID FK shot_intra_shot_events.id

time_ms INTEGER NOT NULL
ordinal INTEGER NOT NULL CHECK >= 0
target_kind TEXT NOT NULL
captured_target_identity_json TEXT NOT NULL
captured_target_identity_hash TEXT NOT NULL length=64
captured_before_state_json TEXT NOT NULL
captured_before_state_hash TEXT NOT NULL length=64
captured_after_state_json TEXT NOT NULL
captured_after_state_hash TEXT NOT NULL length=64
persistence_mode TEXT NOT NULL

event_json TEXT NOT NULL
event_hash TEXT NOT NULL length=64

entity_feature_transition_id UUID NULL FK continuity_feature_transitions.id ON DELETE RESTRICT
entity_relation_transition_id UUID NULL FK continuity_relation_transitions.id ON DELETE RESTRICT
production_instance_feature_transition_id UUID NULL FK production_instance_feature_transitions.id ON DELETE RESTRICT
captured_handoff_json TEXT NULL
captured_handoff_hash TEXT NULL

source_proposal_id UUID NULL FK shot_intra_shot_event_proposals.id

PRIMARY KEY (shot_revision_id, position)
UNIQUE (shot_revision_id, source_event_id)
FK shot_revision_id -> shot_revision_intra_shot_specs.shot_revision_id
```

Rows contain enough captured semantics to reconstruct and re-fold the A7 intra-Shot spec without consulting current feature definitions, relation definitions, event rows, or transitions.

For transient events all handoff fields are null. For persistent events exactly one transition-id column is populated and captured handoff JSON/hash is mandatory.

`source_event_id`, `source_proposal_id`, and transition row UUIDs are **audit provenance only**. They are retained from the first successful publication of that ShotRevision and are not part of semantic ShotRevision convergence (§14.4). A current source event/transition may later be soft-deleted, re-anchored, or semantically edited without invalidating historical meaning. Physical deletion of a row still referenced by immutable history is prevented by FK `RESTRICT`; ordinary services already use soft deletion/updates.

## 7.4 `shot_intra_shot_event_proposals`

Immutable single-candidate evidence rows.

Required columns:

```text
id UUID PK
shot_id UUID FK shots.id
source_kind TEXT                         # generation | take | imported
source_shot_revision_id UUID FK shot_revisions.id
source_shot_revision_hash TEXT NOT NULL length=64
source_generation_id UUID NULL FK generations.id
source_take_id UUID NULL FK takes.id
proposer_kind TEXT                       # human | analyzer
analyzer_id TEXT NULL
analyzer_version TEXT NULL
analyzer_parameters_hash TEXT NULL
proposal_json TEXT NOT NULL
proposal_hash TEXT NOT NULL length=64
created_at TEXT NOT NULL
```

Source rules:

```text
source_kind = generation
    → source_generation_id required; source_take_id null
source_kind = take
    → source_generation_id required; source_take_id required
source_kind = imported
    → generation/take ids null; exact source ShotRevision id/hash still required
```

Proposer rules:

```text
proposer_kind = human
    → analyzer fields null
proposer_kind = analyzer
    → analyzer_id + analyzer_version + analyzer_parameters_hash required
    → empty parameter set hashes canonical {}
```

Generation/Take source coherence and exact source ShotRevision id/hash are verified transactionally.

`proposal_json` must match Proposal Grammar v1, contains exactly one candidate event, and is limited to 65,536 canonical UTF-8 bytes. `proposal_hash` is SHA-256 of those canonical bytes.

No update/delete path exists. A corrected proposal is a new row.

## 7.5 `persistent_consequence_reviews`

Append-only review/adoption operation record.

Required columns:

```text
id UUID PK
shot_id UUID FK shots.id
source_kind TEXT                      # event | proposal
source_event_id UUID NULL FK shot_intra_shot_events.id
source_proposal_id UUID NULL FK shot_intra_shot_event_proposals.id
source_hash TEXT NOT NULL

decision TEXT NOT NULL
review_basis_hash TEXT NOT NULL length=64 UNIQUE
result_event_id UUID NULL FK shot_intra_shot_events.id
entity_feature_transition_id UUID NULL FK continuity_feature_transitions.id
entity_relation_transition_id UUID NULL FK continuity_relation_transitions.id
production_instance_feature_transition_id UUID NULL FK production_instance_feature_transitions.id

operation_json TEXT NOT NULL
operation_hash TEXT NOT NULL length=64
created_at TEXT NOT NULL
```

Decision domains are source-specific:

```text
proposal source:
    adopt_event_only
    adopt_persistence
    ignore

event source:
    adopt_persistence
    decline_persistence
```

Rules:

- source event/proposal XOR;
- `adopt_event_only` valid only for proposal source and always creates a transient event;
- proposal `ignore` creates no authority;
- event `decline_persistence` is an authority edit from the exact reviewed `require_handoff` event hash to `transient`; it creates no A2 transition and records the resulting event hash;
- `adopt_persistence` requires one result event and exactly one owning-domain transition id for a persistent event;
- add partial unique indexes on `(source_event_id, source_hash)` and `(source_proposal_id, source_hash)` for non-NULL sources so one immutable source hash cannot acquire competing decisive reviews;
- after an event hash has already received `adopt_persistence`, later regret is an ordinary fenced PATCH producing a new event hash; it is **not** a second review of the same source hash;
- operation hash is immutable evidence, never a mutable status row;
- concurrent identical retries converge on the unique review basis and return the exact committed result.

### 7.5.1 Exact review-basis grammar

`review_basis_hash` is SHA-256 of canonical JSON bytes. Event-source basis (R7):

```json
{
  "schema_version": 1,
  "source": {"kind":"event","id":"...","hash":"..."},
  "decision": "adopt_persistence",
  "expected_event_set_hash": "...",
  "expected_handoff": {
    "target": {"kind":"entity_feature","id":"..."},
    "anchor": {"anchor_type":"shot","anchor_id":"...","boundary":"end"},
    "semantic_hash": "..."
  }
}
```

For `decline_persistence`, `expected_handoff` is null.

R7 removes `expected_working_snapshot_hash` from the event-source basis — removed, never replaced by another value. Direct event review is fenced by current M16 authority, not by a capturable whole-Shot snapshot: the source event hash identifies the exact semantic event being reviewed; the event-set hash commits the complete current M16 event set and duration; and under the same `BEGIN IMMEDIATE` the service re-resolves current predecessor Shot/start authority and performs the complete prospective fold before any A2 mutation, so a stale start-state dependency still fails. §9.2 defines the working snapshot hash as unavailable exactly while an unresolved `require_handoff` exists — the direct-adoption precondition — so no whole-Shot working-snapshot value can participate in this basis. The proposal-source construction is deliberately different and is defined next.

Proposal-source basis adds the proposal's exact source ShotRevision identity and the candidate-event hash derived from Proposal Grammar v1. For a proposal `ignore`, current working/event-set hashes may be null because no authority is created. This paragraph is descriptive only; §7.5.2 defines the sole exact `review_basis_hash` construction for every proposal-source review.

### 7.5.2 Atomic batch proposal basis

A multi-proposal review computes one `batch_basis_hash` over:

```json
{
  "schema_version": 1,
  "shot_id": "...",
  "source_shot_revision_id": "...",
  "source_shot_revision_hash": "...",
  "expected_working_snapshot_hash": "...",
  "expected_event_set_hash": "...",
  "reviews": [
    {"proposal_id":"...","proposal_hash":"...","decision":"adopt_persistence"}
  ]
}
```

`reviews` are sorted by proposal UUID only for basis canonicalization; event semantics still sort by `(time_ms,ordinal)`. Each committed review row stores an operation document containing the shared `batch_basis_hash`, and its own `review_basis_hash` is the canonical hash of `{batch_basis_hash, proposal_id, proposal_hash, decision}`. The transaction is all-or-none, so an exact retry observes either the complete committed batch or no committed batch.

For **every** proposal-source review — single-proposal route or batch — this §7.5.2 construction is the sole normative construction of `review_basis_hash`:

```text
review_basis_hash
=
SHA-256(
  canonical_json_bytes({
    "batch_basis_hash": <exact batch_basis_hash>,
    "proposal_id": <exact proposal UUID>,
    "proposal_hash": <exact proposal hash>,
    "decision": <exact frozen decision token>
  })
)
```

The single-proposal review route is exactly a one-item batch; there is no second single-review root grammar. The exact source ShotRevision identity and candidate-event hash are committed through the frozen `batch_basis_hash` construction and are therefore transitively committed by `review_basis_hash`; they are not duplicated as additional top-level fields unless a future schema revision explicitly changes the grammar. Any implementation, migration fixture, API serializer, or test that computes a proposal-source `review_basis_hash` with a different field set, field nesting, serializer, or root grammar is non-conforming.

# 8. Intra-Shot spec schema 1 and outer Shot snapshot schema 7

M16 adds a versioned A7 `intra_shot` block at the **outer Shot snapshot** layer. Published M6/M7 continuity-spec schemas remain unchanged.

## 8.1 No-empty-higher-schema law

If a Shot has zero active M16 events, capture must emit exactly the predecessor M15 snapshot bytes and continuity-spec bytes it would have emitted.

No empty `intra_shot` block, no `shot_revision_intra_shot_specs` row, and no outer snapshot schema 7 are added.

This is a byte-level regression gate.

## 8.2 Intra-Shot spec schema 1

When at least one active M16 event exists, the canonical A7 block is:

```json
{
  "schema_version": 1,
  "duration_ms": 5000,
  "events": [
    {
      "time_ms": 3100,
      "ordinal": 0,
      "target": {"kind":"entity_feature","id":"..."},
      "target_identity": {...captured target-identity grammar v1...},
      "before": {...},
      "after": {...},
      "persistence_mode": "require_handoff",
      "handoff": {...captured handoff grammar v1...}
    }
  ]
}
```

`duration_ms` is duplicated deliberately. Historical validation requires it to equal the captured ShotRevision `intent.duration_ms`; disagreement is corruption.

`target_identity` is semantic captured history, not display metadata. It freezes feature type/unit or relation directional/predicate identity so historical validation never needs current schema rows.

For transient events `handoff` is exactly null. For persistent events it is the canonical semantic handoff from §4.8; transition row UUID is not embedded in the semantic block.

## 8.3 Outer snapshot schema 7 lattice

Published snapshot schema versions 1–6 remain byte/grammar frozen.

An event-bearing capture is:

```text
exact legal predecessor semantic fields
+ exact predecessor continuity block, if any
+ exact predecessor visual/spatial/production_world blocks, if any
+ non-empty top-level intra_shot schema-1 block
→ outer snapshot schema_version = 7
```

Explicit lattice dependencies:

```text
entity_feature / entity_relation event
    → exact target owner/endpoints must be represented by the captured semantic-dependency plane

production_instance_feature event
    → schema-7 snapshot MUST contain the exact predecessor schema-6 Production World plane
    → missing production_world for a PI event is an invariant failure, never an empty substitute
```

Rules:

- event-free capture remains byte-identical schema 1–6;
- schema 7 is illegal without a non-empty `intra_shot.events` array;
- schema 7 preserves the exact predecessor `continuity` value; M16 does not mint continuity-spec schema 3;
- schema 7 never silently lowers to schema 1–6 for execution;
- schema 7 with Production World carries the exact published spatial/production-world packs; it does not create a second world representation.

## 8.4 Historical reconstruction and re-fold

Historical inspection must:

1. preserve continuity-spec schemas 1/2 exactly;
2. accept/validate published outer snapshot schemas 1–6 under their predecessor semantics;
3. accept outer schema 7 only with a non-empty `intra_shot` block and one `shot_revision_intra_shot_specs` parent row;
4. rebuild each captured target identity from immutable child columns/JSON and verify canonical bytes/hash;
5. rebuild the intra-Shot schema-1 block from `shot_revision_intra_shot_events`;
6. require rebuilt block bytes/hash to equal `shot_revision_intra_shot_specs.spec_json/spec_hash`;
7. require the rebuilt block to equal the top-level `snapshot_json.intra_shot` value exactly;
8. re-canonicalize captured event/before/after/handoff JSON using captured-row-only grammars;
9. require exact canonical bytes and hashes, including all duplicated scalar columns;
10. require captured event positions contiguous from zero and in canonical `(time_ms, ordinal)` order;
11. extract the exact captured Shot/start state for every event target from the **same immutable ShotRevision**:
    - entity feature from captured continuity feature state + captured target identity;
    - entity relation from captured continuity relation state + captured target identity;
    - PI feature from captured `production_world.instance_feature_states` + captured target identity;
12. re-run the deterministic before/after fold from those captured start states and require every captured `before` to match;
13. require every persistent captured handoff semantic value to equal the re-folded terminal target state and to use exact Shot/end anchor/owning-domain vocabulary;
14. compare the full outer `snapshot_json/hash` under the existing historical hash check;
15. never query current `shot_intra_shot_events`, current feature/relation/PI definitions, current transitions, current Production World selection, current Shot duration, current proposals/reviews, or current Take approval.

If a captured source event or transition is now soft-deleted or edited, historical inspection still succeeds from immutable captured semantics. Missing current audit-source rows are not consulted semantically; physical deletion is prevented by FK RESTRICT while the historical row exists.

# 9. Current readiness and ShotRead integration

## 9.1 One projection

The current M16 status projection returns:

```text
intra_shot_ready
intra_shot_issues[]
duration_ms
events[]
terminal_targets[]
handoffs[]
```

This projection is produced only by the shared M16 resolver.

## 9.2 Preserve predecessor readiness semantics

Published `ShotRead.continuity_state_ready` remains the M7 semantic-state signal. M16 does not make it depend on later M13 state.

Add dedicated fields:

```text
intra_shot_ready: bool = False
intra_shot_issues: list = []
```

The schema default is fail-closed (`False`); the real Shot-detail path always populates the server projection, including `True` for the event-free case. An unpopulated serializer may never fabricate M16 readiness.

The authoritative working snapshot is available only when every predecessor layer required by the Shot is ready and M16 is ready. Therefore an M16 blocker nulls `working_snapshot_hash` / `working_state_differs_from_approved` exactly as other capture-blocking authority gaps do, without falsifying the older field meanings.

A dedicated `GET /shots/{shot_id}/intra-shot` endpoint exposes richer event/terminal detail for UI without turning the browser into a second resolver.

## 9.3 Working hash

The existing working snapshot hash must change when authoritative M16 event/handoff meaning changes.

Proposal rows and ignored proposals do not change the working hash.

When M16 readiness is false, consumers must not hash an incomplete/fabricated canonical state.

# 10. Authoring API

## 10.1 Read

```text
GET /shots/{shot_id}/intra-shot?limit=100&cursor=...
```

Returns authoritative active events, terminal fold, current handoff match status, event-set hash, and issues. Default page size is 100; maximum is 500. The server projection, not the browser, remains the authority.

## 10.2 Create authoritative event

```text
POST /shots/{shot_id}/intra-shot/events
```

Strict typed body, `extra=forbid`, strict integer fields (`bool`, float, numeric strings rejected), and safe-integer limits.

Under `BEGIN IMMEDIATE`, the server:

- verifies Shot and target identity;
- validates canonical before/after state;
- validates current duration/time;
- enforces the 10,000-active-event ceiling;
- builds the **entire prospective active event set** including the new event;
- validates coordinate uniqueness and target eligibility;
- reruns the complete **structural** prospective fold so an insertion cannot invalidate a later event's `before` state silently;
- rejects an earlier `require_handoff` marker if the new event would make it nonterminal;
- stores canonical event JSON/hash only if the full event set remains structurally coherent.

The service does not auto-create persistent handoff merely because `require_handoff` is requested. Missing/invalid handoff remains a separate readiness blocker and such a working state may remain capture-blocked until explicit persistence adoption.

## 10.3 Patch authoritative event

```text
PATCH /intra-shot/events/{event_id}
```

May change time, ordinal, before/after state, or persistence mode only through full prospective-set revalidation under `BEGIN IMMEDIATE`.

Any semantic patch to a proposal-adopted event converts current provenance to `source_kind=authored`, `source_proposal_id=NULL` as §4.3 specifies. Historical review/proposal evidence is not rewritten.

Any patch that makes the event set contradictory or ambiguous is rejected atomically.

A historical ShotRevision is never rewritten.

## 10.4 Delete authoritative event

```text
DELETE /intra-shot/events/{event_id}
```

Soft-deletes current authority only, but deletion also validates the **remaining prospective event set** before commit. Deleting an earlier event may not leave a later event whose stored `before` state is now false.

Deletion does not delete an adopted Shot/end transition automatically. That transition is A2 authority and must be edited through an explicit continuity operation. The UI must show that a remaining Shot/end transition is independent boundary authority even when its former intra-Shot timing event is deleted.

## 10.5 Shot-duration mutation fence

`PATCH /shots/{shot_id}` is extended only when `duration_ms` is supplied.

The duration mutation and active-event validation run under one writer fence. A new duration may not make any existing active event time illegal. Setting duration to NULL/0 or to a value `<= max(active_event.time_ms)` conflicts while active M16 events exist.

This closes the duration/event race without globally tightening the predecessor `shots.duration_ms` schema.

# 11. Proposal API

## 11.1 Ingest proposal

```text
POST /shots/{shot_id}/intra-shot/proposals
```

The endpoint is an evidence-ingestion boundary, not authority authoring.

It validates Proposal Grammar v1 and the 65,536-byte canonical limit. For Generation/Take-backed proposals it verifies:

- exact source ShotRevision exists and its snapshot hash equals the supplied pinned hash;
- Generation pins that ShotRevision;
- Take, if supplied, belongs to that Generation and Shot;
- proposal time is valid against captured source duration;
- source/proposer/analyzer provenance fields obey the declared grammar;
- analyzer parameter hash is present for every analyzer proposal;
- proposal JSON/hash are canonical.

For `source_kind=imported`, Generation/Take ids are absent but exact source ShotRevision id/hash remains mandatory.

Human-authored review of a generated/Take result is represented with `proposer_kind=human`; machine-derived analysis uses `proposer_kind=analyzer` and pins analyzer identity/version/parameter hash.

It does **not** consult `shots.approved_take_id` as an acceptance criterion.

## 11.2 List proposals/reviews

```text
GET /shots/{shot_id}/intra-shot/proposals?limit=100&cursor=...
```

Default page size 100, maximum 500. Shows exact proposal provenance plus append-only review decisions and stale/no-rebase reason where applicable.

# 12. Persistence review/adoption API

## 12.1 Direct event adoption

```text
POST /intra-shot/events/{event_id}/persistence/adopt
```

Uses `BEGIN IMMEDIATE`.

The request carries exactly the expected source event hash and the expected current event-set hash (R7). No prior ShotRevision capture is required: the authored-authority flow `author event → adopt persistence → future capture` is lawful.

The transaction:

1. probes the exact committed-review retry by its immutable source coordinates (source event id + hash + decision, unique under the reviews uniqueness index) first;
2. re-verifies current Shot/event set and expected basis;
3. recomputes terminal fold;
4. verifies this event is the terminal event for the target;
5. verifies the Shot/end narrative anchor exists;
6. derives the exact required Shot/end transition semantic value;
7. re-reads the transition coordinate under the same writer fence;
8. if no active transition exists, creates one through the shared owning-domain transition helper;
9. if an active exact-equal transition already exists, adopts it without duplicating;
10. if a different active transition exists, fails 409 and never overwrites it;
11. writes the immutable review operation record;
12. commits event/transition/review outcome atomically.

## 12.2 Direct event decline persistence

```text
POST /intra-shot/events/{event_id}/persistence/decline
```

This endpoint is valid only for an unreviewed current `require_handoff` **source event hash**. It changes that same working event to `transient` under one fenced/hash-checked prospective-set revalidation and records decision `decline_persistence` with the resulting event hash.

It does not delete or rewrite an existing Shot/end transition. That transition remains independent A2 boundary authority.

If the exact source event hash already has a decisive `adopt_persistence` review, later regret is an ordinary PATCH to `persistence_mode=transient`, which produces a new current event hash. M16 never writes a second competing decisive review against the already-reviewed source hash.

## 12.3 Proposal review — single and atomic batch

Single-proposal convenience route:

```text
POST /intra-shot/proposals/{proposal_id}/review
```

is a one-item invocation of the batch primitive:

```text
POST /shots/{shot_id}/intra-shot/proposals/review-batch
```

Body:

```json
{
  "reviews": [
    {
      "proposal_id": "<uuid>",
      "expected_proposal_hash": "<sha256>",
      "decision": "adopt_persistence"
    }
  ]
}
```

Decision per proposal:

```text
adopt_event_only
adopt_persistence
ignore
```

Rules:

- 1..10,000 proposals per batch;
- every proposal belongs to the same Shot;
- every authority-creating proposal in the batch pins the **same** source ShotRevision id/hash;
- all source/proposal hashes are verified before mutation;
- if any decision creates authority, the current effective working snapshot hash is read once at transaction start and must equal that shared source ShotRevision hash;
- a NULL current working hash is stale;
- all adopted candidate events are added to one full prospective event set and validated together before any insert;
- `adopt_event_only` creates a transient event regardless of `persistence_suggestion`;
- `adopt_persistence` creates a `require_handoff` event plus exact A2 handoff through the shared helper;
- `ignore` records review only and may be recorded for a stale proposal because it creates no authority;
- event rows, any handoffs, and every review row commit atomically or roll back together.

This allows two or more proposals derived from one Take/Generation/ShotRevision to be adopted in one transaction without the first adopted event making its siblings stale. M16 still does not rebase a proposal from an older source ShotRevision onto later working truth.

## 12.4 Idempotency

Exact retry returns the exact committed semantic result, including:

```text
source proposal/event identity + hash
decision
review_basis_hash
batch_basis_hash when applicable
result event id + hash
result transition kind + id + exact semantic hash
operation id + hash
```

No evidence fields are reconstructed as null on retry. Concurrent identical requests converge on the unique basis/bases.

Before returning idempotent success, the retry path re-verifies that each recorded result event still has the committed event hash and each recorded transition still has the committed semantic value. A later edit/tombstone produces a conflict rather than a false retry success.

A batch retry must find the complete expected set of review rows with the same `batch_basis_hash`; a strict subset is invariant corruption because the original transaction is atomic.

A later capture or unrelated whole-Shot change never manufactures a new direct-review basis: direct retries are located by immutable source coordinates and validated against committed-result drift only.

# 13. Shared transition-helper requirement

M16 must not directly duplicate feature/relation/PI transition authoring rules already exposed by continuity/production-world services.

Before wiring adoption, factor or expose connection-scoped internal helpers that accept a **caller-owned `AsyncConnection` transaction** and a verified exact transition request. They perform:

```text
target existence/ownership validation
anchor validation against canonical narrative ordering
feature/PI value canonicalization with exact set|clear vocabulary
relation state validation with exact active|inactive vocabulary
active-coordinate conflict check
create behavior
optional exact-equal convergence behavior
```

The helper never begins, commits, or rolls back a nested transaction when called by M16.

Predecessor API semantics remain stable:

```text
ordinary existing POST transition route
    → strict create; occupied coordinate remains conflict

M16 persistence adoption
    → create-or-exact-match convergence allowed
    → different occupied value remains conflict
```

Event + transition + review adoption therefore has one atomicity boundary: the M16 `BEGIN IMMEDIATE` transaction. No helper may commit independently.

This is a source-fit requirement, not optional cleanup.

# 14. Capture integration

## 14.1 One read snapshot

M16 event rows and required handoff transitions are read on the same explicit SQLite read snapshot as all other ShotRevision inputs, including the exact captured duration and predecessor start-state planes.

No post-snapshot query may influence the captured M16 value.

## 14.2 Capture fence

Capture fails before ShotRevision insertion when M16 is not ready.

Persistent event without exact handoff is therefore a hard capture blocker.

A proposal without adoption is irrelevant to the capture fence.

The capture-versus-duration race is covered by SQLite snapshot isolation: capture sees either the coherent pre-patch duration+events or the coherent post-patch state, never a hybrid. A duration mutation that would invalidate committed events is independently prohibited by §10.5.

## 14.3 Snapshot builder

Extend the one canonical builder with an optional resolved `intra_shot` pack.

Rules:

- no events → byte-identical predecessor output and predecessor schema 1–6;
- events → preserve exact predecessor continuity/visual/spatial/production-world values, add top-level `intra_shot`, and set outer Shot snapshot schema 7;
- M16 does **not** change `continuity_spec_json/hash` schemas 1/2;
- event order fixed by `(time_ms, ordinal)`;
- each captured event includes frozen `target_identity` and, when persistent, semantic `handoff` from §4.8;
- source event/proposal/transition IDs are audit provenance only and do not become accidental semantic tie-breakers;
- duration is repeated and equality-checked;
- PI-feature event requires the exact predecessor schema-6 production-world plane;
- the builder never changes the grammar of published snapshot schema versions 1–6.

## 14.4 Reuse/convergence — semantic value wins over audit source identity

Existing `UNIQUE(shot_id, snapshot_hash)` convergence remains authoritative.

On a convergence/reuse path, M16 verifies:

```text
existing shot_revision_intra_shot_specs spec_json/hash
existing child semantic positions/time/ordinal/target_identity/before/after/persistence/handoff
outer snapshot.intra_shot
```

against the would-be semantic capture.

The following are **not** semantic convergence keys and are not required to equal the would-be current capture:

```text
source_event_id
source_proposal_id
transition row UUID
```

If a later working event/transition with different UUIDs produces byte-identical semantic ShotRevision content, the existing ShotRevision is reused. Its immutable audit provenance remains the provenance of the **first successful publication** of that ShotRevision; M16 does not rewrite history to make audit ids reflect the later equivalent authoring path.

Missing/extra/mismatched semantic companion rows are invariant corruption, never repaired implicitly.

# 15. Historical isolation, generation fence, and Exact Rerun

## 15.1 Historical reads

A historical ShotRevision consumes only:

```text
stored ShotRevision snapshot/continuity bytes
immutable shot_revision_intra_shot_specs/events rows
captured predecessor history rows/packs in that same ShotRevision
```

It does not consume current:

```text
Shot duration
event rows
proposal rows
review rows
feature/relation/Production Instance definitions
boundary transition values/status
Production World selection
approved Take pointer
```

Historical semantic verification includes the captured-state re-fold in §8.4. Current source event/transition soft-delete or edits do not affect old history.

## 15.2 Generation fence for schema 7

M16 does not teach current workflow packages how to realize event timing.

Generation creation parses the captured ShotRevision **before any Generation-side write or derived publication**. If it is outer snapshot schema 7 with non-empty M16 authority — including an all-transient event set — it raises:

```text
INTRA_SHOT_REALIZATION_UNSUPPORTED   HTTP 409
```

The refusal occurs before:

```text
Generation row insertion
GenerationInput insertion
derived spatial/observation artifact publication
workflow package publication/queueing
worker submission
```

No lower-schema fallback, event stripping, prompt-only approximation, or executor-specific interpretation is allowed.

This outcome is a terminal policy/capability refusal: halt/escalate to the filmmaker/producer. It is not an interference-budget retry condition.

## 15.3 Exact Rerun

Generation already pins exact `shot_revision_id`.

M16 does not add a current-state lookup in worker/executor code.

An Exact Rerun of a pre-M16 or pre-adoption Generation remains pinned to its old ShotRevision and cannot inherit later event/persistence authority.

Because M16 v1 refuses new schema-7 Generation publication, there is no schema-7 Exact Rerun path to fake before an executor contract exists. Schema-7 historical inspection remains supported.

## 15.4 Historical endpoint

Extend the existing ShotRevision historical inspector with:

```text
intra_shot_schema_version
captured_duration_ms
events[]
terminal_handoffs[]
first-publication source proposal/event provenance audit
```

The P0 predecessor correction makes the same endpoint accept/validate already-published outer schema 6 **before** schema 7 is layered. No current-state reconstruction is permitted.

No new “latest” historical route is permitted.

# 16. Recovery / backup

## 16.1 M16-P0 predecessor historical-closure repairs

M16-P0 contains **two explicit predecessor-remediation corrections** and no M16 product-table work.

### P0-A — Recovery succession

Before advertising recovery support for head 0017, repair restore dispatch so each supported historical head is verified to its actual authority depth:

```text
0011 → predecessor M10F policy
0012 → + M11 production state
0013 → + M12 composition state
0014 → + M13 world/history state
0015 → + M14 observation history
0016 → + M15 compatibility/update history
0017 → + M16 event/proposal/review history
```

At minimum add explicit `_verify_m14_observation_state()` and `_verify_m15_compatibility_state()` functions and never route 0015/0016 through a generic “0014 or later” fall-through.

Corruption tests deliberately alter canonical/historical fields in M14 and M15 rows and prove restore rejects the staged DB at the appropriate head.

### P0-B — Published schema-6 historical inspector

Before adding schema 7, correct the existing historical continuity inspector so:

```text
schema 1–5 → exact existing behavior
schema 6   → accepted and validated from immutable M13 history
```

The correction is historical-only and must not reconstruct schema 6 from current Production World state. Dedicated regressions prove schema 1–5 behavior remains unchanged and published schema 6 is inspectable.

These are predecessor historical-closure repairs discovered by M16 source fit. They are explicitly allowed boundary exceptions; SF-08's M15 exact-retry translator-response defect is **not** part of M16-P0 and remains separately authorized debt.

## 16.2 M16 head

Advance recovery head to:

```text
0017_m16_intra_shot_consequences
```

M16 adds no Blob foreign key in R6. The physical Blob-FK inventory remains exactly the published M14/M15 **8 paths** unless implementation evidence proves a reviewed architecture change; the 0017 structural test pins exactly 8.

Recovery verifies:

- authoritative working event canonical JSON/hash;
- immutable captured target identity/event/before/after/handoff canonical JSON/hash;
- proposal grammar/hash/size and source coherence;
- review operation canonical JSON/hash, exact review-basis grammar (event-source per the §7.5.1 R7 field set — a missing or extra field, including any `expected_working_snapshot_hash`, is corruption), and result references;
- intra-Shot spec schema-1 reconstruction for every captured M16 ShotRevision and equality with the outer schema-7 block;
- captured-state historical re-fold and terminal handoff equality;
- audit transition/source ids may point to soft-deleted/edited current rows, but physical references remain FK-coherent; historical semantics come from captured duplicates rather than today's values.

# 17. UI contract

## 17.1 Shot event timeline

Add a Shot-local event panel showing:

```text
duration
Shot/start state summary
event markers by millisecond
event target + before/after state
persistence requested/transient
handoff status
terminal state preview
```

The browser renders server projections. It does not compute readiness, fold state, handoff equality, or terminal semantics independently.

Client controls must prevent submitting time zero/time-at-duration as an ordinary affordance, but server validation remains authoritative.

When an upstream transition/binding edit invalidates an event `before`, the server issue must identify the event id/coordinate, stored `before`, and newly expected start/fold state. The UI shows that reason rather than a generic “not ready.”

An event-free Shot renders `intra_shot_ready=true` from the server projection.

## 17.2 Persistent consequence review

Show proposal/event consequence review separately from Take approval controls.

Proposal actions:

```text
Adopt persistence
Adopt event only
Ignore proposal
```

Direct event actions:

```text
Adopt persistence
Decline persistence     # only for an unreviewed require_handoff source hash
```

The `Adopt event only` confirmation explicitly states that any proposal persistence suggestion will **not** persist downstream; the resulting event is transient.

If a transient terminal event and an independent Shot/end transition disagree, show both values and label the Shot/end transition as separate A2 boundary authority rather than implying continuity agreement.

If an earlier `require_handoff` marker prevents a later same-target event, show the legal recovery action: PATCH the earlier marker to transient or change the event set.

The UI must not make Take selection a prerequisite for review and must not suggest that Take approval already adopted the consequence.

## 17.3 Proposal batch/staleness UX

Sibling proposals sharing one source ShotRevision can be selected and reviewed atomically through the batch route. The UI shows the shared source revision and exact no-rebase basis.

When a proposal is stale, display whether the current working snapshot differs from its source and require re-analysis/new proposal or direct authoring. Do not offer silent rebase.

A proposal `ignore` may still be recorded when stale because it creates no authority. Re-deciding an already-reviewed immutable proposal requires a new proposal row; decisive reviews are append-only.

## 17.4 Downstream preview

For an adopted persistent consequence, show the ordinary downstream state projection for a later Shot using the same M7/M13 resolver that production capture uses.

No client-side simulation of downstream state.

# 18. API/error vocabulary

Add stable error codes:

```text
INTRA_SHOT_DURATION_REQUIRED
INTRA_SHOT_TIME_OUT_OF_RANGE
INTRA_SHOT_EVENT_COORDINATE_CONFLICT
INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH
INTRA_SHOT_TARGET_INVALID
INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL
INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED
INTRA_SHOT_HANDOFF_REQUIRED
INTRA_SHOT_HANDOFF_MISMATCH
INTRA_SHOT_EVENT_LIMIT_EXCEEDED
INTRA_SHOT_PROPOSAL_TOO_LARGE
INTRA_SHOT_PROPOSAL_STALE
INTRA_SHOT_REVIEW_CONFLICT
INTRA_SHOT_REALIZATION_UNSUPPORTED
```

Validation errors for malformed request grammar remain ordinary validation errors. The codes above describe domain/readiness/conflict/execution-capability outcomes.

No raw SQLite/JSON/Pydantic exception becomes public API behavior.

# 19. Concurrency and race discipline

All multi-row authority writes use SQLite `BEGIN IMMEDIATE` before their first authoritative read.

Required race classes and outcomes:

1. **event create vs duration patch** — event wins ⇒ duration update rejects if invalidating; duration wins ⇒ event validates against new duration;
2. **event patch vs competing event patch at same coordinate** — at most one prospective set commits;
3. **event delete vs later same-target event** — delete rejects if it would falsify the later `before`, unless the competing update first makes the remaining chain valid;
4. **persistence adoption vs event edit** — adoption rechecks source/event-set hashes; stale side conflicts;
5. **persistence adoption vs existing Shot/end transition edit** — adoption re-reads under the writer fence; exact match converges, changed value conflicts, never overwrites;
6. **proposal batch adoption vs current Shot change** — source working-hash check is evaluated before mutation; exactly one coherent basis wins;
7. **proposal batch adoption vs duplicate retry** — complete batch converges; partial committed batch is impossible/invariant corruption;
8. **ShotRevision capture vs event/handoff mutation** — capture sees one coherent SQLite read snapshot;
9. **ShotRevision capture vs duration patch** — capture sees one coherent duration/event set; no hybrid;
10. **Take approval vs persistence adoption** — both may commit independently: approval touches canon selection only; adoption touches event/review/transition only.

No operation uses “last writer wins” for authority conflicts.

# 20. Migration discipline

Migration 0017 is additive.

Upgrade:

- creates exactly the five M16 tables and named indexes/constraints;
- includes the target-FK XOR CHECK and partial active-coordinate unique index;
- does not alter/rebuild `shots`, `shot_revisions`, M7 tables, M13 tables, or M15 tables;
- adds no Blob FK; exact Blob-FK inventory remains 8;
- does not backfill events/proposals/reviews;
- does not invent duration or persistence state.

Downgrade:

- runs a fail-closed preflight before any DDL;
- refuses if any M16 table contains any row;
- drops tables child-first only when all are empty.

Historical predecessor data is never deleted to make downgrade succeed.

# 21. Implementation slices

## M16-P0 — Predecessor historical-closure repairs

Deliver **before migration 0017/product data-plane work**:

- explicit 0015/0016 recovery dispatch;
- M14 immutable observation verifier;
- M15 compatibility/update verifier;
- focused corruption tests;
- published outer-schema-6 historical inspector correction;
- schema-1–5 historical behavior regressions;
- no M16 table or product endpoint changes.

Exit:

```text
restore at 0014 verifies through M13 only
restore at 0015 verifies through M14
restore at 0016 verifies through M15
corrupted M14/M15 immutable evidence fails restore
historical inspector accepts published schema 6
schema 1–5 historical behavior unchanged
```

## M16-A — Migration + event/proposal grammar and lifecycle foundation

Deliver:

- migration 0017;
- ORM registration;
- event/state/target-identity/handoff/proposal canonicalizers;
- strict safe-integer and size/count bounds;
- strict API schemas;
- event authoring CRUD with full prospective-set validation;
- proposal-adopted event edit provenance rule;
- duration patch/event writer fence;
- exact review-basis/batch-basis canonical builders;
- direct source-fit tests for time/duration/coordinate/target grammar.

No adoption UI yet.

## M16-B — Deterministic resolver + readiness/handoff equality

Deliver:

- shared pure/set-oriented resolver;
- event-set hash;
- entity feature fold;
- entity relation fold;
- Production Instance feature fold;
- terminal-event/persistence validation;
- existing transition-domain handoff comparison;
- current Shot readiness integration;
- exact query-count/event-count bounds.

## M16-C — Immutable capture + historical isolation

Deliver:

- intra-Shot spec schema 1 + immutable parent companion + outer Shot snapshot schema 7;
- predecessor continuity-spec schemas 1/2 remain byte/grammar frozen;
- same-read-snapshot capture integration;
- `shot_revision_intra_shot_specs` + `shot_revision_intra_shot_events` persistence;
- semantic convergence / first-publication audit-provenance rule;
- historical captured-state re-fold;
- generation-creation schema-7 fail-closed fence before any Generation-side write;
- Exact Rerun/current-state-isolation regressions;
- recovery 0017 verification.

## M16-D — Proposal + explicit consequence review/adoption

Deliver:

- immutable Proposal Grammar v1 ingestion;
- exact source ShotRevision id/hash + Generation/Take/imported provenance;
- human/analyzer provenance with unconditional parameter hash;
- shared connection-scoped transition authoring helper;
- fenced direct event adopt/decline operations;
- atomic multi-proposal batch review/adoption;
- unique review-basis/batch-basis idempotency + exact retry evidence;
- stale proposal/current authority conflicts;
- proof that Take approval is independent.

## M16-E — Product surface + source gate + closure

Deliver:

- Shot event timeline;
- consequence review controls and batch review;
- downstream state preview;
- entity-bound source-gate proof;
- instance-bound source-gate proof;
- multi-proposal source-gate proof;
- scale/race/recovery suite;
- M16 proof-map/baseline/boundary/source-fit validators;
- full backend/frontend certification.

# 22. Proof map — exact frozen cell universe

R6 freezes **162 proof cells**. `scripts/m16_validate_proof_map.py` must hard-code this exact cell set and family counts; it may not infer the universe dynamically from whatever tests happen to exist.

Owner grammar:

```text
PY <pytest-file>::<exact test function>
STRUCT <validator-file>::<exact check function>
FE <frontend-test-file>#<exact M16 cell marker>
```

At implementation closure every owner must exist, every `PY` owner must collect, every `FE` marker must exist in the named frontend test file and be exercised by `npm test`, no owner may be `pending`, and no extra/duplicate/unknown cell may appear.

Family counts:

| Family | Count |
|---|---:|
| BASE | 6 |
| PRE | 6 |
| MIG | 7 |
| GRAMMAR | 10 |
| IDENTITY | 6 |
| DURATION | 5 |
| START | 4 |
| FOLD | 8 |
| HANDOFF | 9 |
| ENTITY | 5 |
| RELATION | 5 |
| INSTANCE | 6 |
| READY | 7 |
| CAPTURE | 8 |
| HIST | 11 |
| PROPOSAL | 10 |
| ADOPT | 11 |
| TAKE | 5 |
| RACE | 9 |
| RECOVERY | 8 |
| EXEC | 5 |
| UI | 6 |
| SCALE | 5 |
| **TOTAL** | **162** |

## BASE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:BASE:01` | published M15 peeled commit/tree/tag object/Release ids are exact | `STRUCT scripts/m16_validate_baseline.py::test_base_01` |
| `M16:BASE:02` | M15 tag is annotated and verification reason is unsigned, not falsely described as signed | `STRUCT scripts/m16_validate_baseline.py::test_base_02` |
| `M16:BASE:03` | migration head before M16 is exactly 0016_m15_revision_compatibility | `STRUCT scripts/m16_validate_baseline.py::test_base_03` |
| `M16:BASE:04` | PR-head CI #79 and post-merge CI #80 identities are recorded baseline evidence | `STRUCT scripts/m16_validate_baseline.py::test_base_04` |
| `M16:BASE:05` | predecessor tree contains no M16 tables/migration 0017 | `STRUCT scripts/m16_validate_baseline.py::test_base_05` |
| `M16:BASE:06` | baseline validator rejects any predecessor identity drift | `STRUCT scripts/m16_validate_baseline.py::test_base_06` |

## PRE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:PRE:01` | 0015 restore dispatch invokes M14 semantic verification | `PY tests/test_m16_predecessor_repairs.py::test_pre_01` |
| `M16:PRE:02` | 0016 restore dispatch invokes M14 plus M15 semantic verification | `PY tests/test_m16_predecessor_repairs.py::test_pre_02` |
| `M16:PRE:03` | corrupt M14 observation evidence fails restore at 0015+ | `PY tests/test_m16_predecessor_repairs.py::test_pre_03` |
| `M16:PRE:04` | corrupt M15 assessment/use/update evidence fails restore at 0016+ | `PY tests/test_m16_predecessor_repairs.py::test_pre_04` |
| `M16:PRE:05` | historical inspector accepts valid published outer schema 6 without current-state reconstruction | `PY tests/test_m16_predecessor_repairs.py::test_pre_05` |
| `M16:PRE:06` | historical schema 1–5 behavior remains unchanged after P0 correction | `PY tests/test_m16_predecessor_repairs.py::test_pre_06` |

## MIG

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:MIG:01` | 0017 upgrade creates exactly five M16 tables | `PY tests/test_m16_migration.py::test_mig_01` |
| `M16:MIG:02` | ORM and migration schema/index/FK sets are identical | `PY tests/test_m16_migration.py::test_mig_02` |
| `M16:MIG:03` | target-kind FK XOR CHECK is present and enforced | `PY tests/test_m16_migration.py::test_mig_03` |
| `M16:MIG:04` | active coordinate uniqueness is partial WHERE deleted_at IS NULL | `PY tests/test_m16_migration.py::test_mig_04` |
| `M16:MIG:05` | captured transition/source history FKs use restrictive physical deletion semantics | `PY tests/test_m16_migration.py::test_mig_05` |
| `M16:MIG:06` | downgrade refuses when any M16 table has any row | `PY tests/test_m16_migration.py::test_mig_06` |
| `M16:MIG:07` | empty downgrade/upgrade roundtrip preserves predecessor data and Blob-FK inventory exactly 8 | `PY tests/test_m16_migration.py::test_mig_07` |

## GRAMMAR

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:GRAMMAR:01` | bool/float/numeric-string rejected for time_ms | `PY tests/test_m16_grammar.py::test_grammar_01` |
| `M16:GRAMMAR:02` | bool/float/numeric-string rejected for ordinal | `PY tests/test_m16_grammar.py::test_grammar_02` |
| `M16:GRAMMAR:03` | safe-integer overflow rejected | `PY tests/test_m16_grammar.py::test_grammar_03` |
| `M16:GRAMMAR:04` | time zero rejected | `PY tests/test_m16_grammar.py::test_grammar_04` |
| `M16:GRAMMAR:05` | time equal to duration rejected | `PY tests/test_m16_grammar.py::test_grammar_05` |
| `M16:GRAMMAR:06` | time greater than duration rejected | `PY tests/test_m16_grammar.py::test_grammar_06` |
| `M16:GRAMMAR:07` | negative ordinal rejected | `PY tests/test_m16_grammar.py::test_grammar_07` |
| `M16:GRAMMAR:08` | malformed target-kind/FK XOR rejected | `PY tests/test_m16_grammar.py::test_grammar_08` |
| `M16:GRAMMAR:09` | malformed/noncanonical before/after state rejected | `PY tests/test_m16_grammar.py::test_grammar_09` |
| `M16:GRAMMAR:10` | before equal to after rejected as no-op | `PY tests/test_m16_grammar.py::test_grammar_10` |

## IDENTITY

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:IDENTITY:01` | event UUID remains stable across lawful working PATCH while event_hash changes | `PY tests/test_m16_identity.py::test_identity_01` |
| `M16:IDENTITY:02` | event_hash excludes audit proposal/source timestamps | `PY tests/test_m16_identity.py::test_identity_02` |
| `M16:IDENTITY:03` | semantic patch of proposal-adopted event converts current provenance to authored/null proposal | `PY tests/test_m16_identity.py::test_identity_03` |
| `M16:IDENTITY:04` | captured entity-feature target identity freezes owner/key/kind/value_type/unit | `PY tests/test_m16_identity.py::test_identity_04` |
| `M16:IDENTITY:05` | captured relation target identity freezes directional endpoints and predicate identity/key | `PY tests/test_m16_identity.py::test_identity_05` |
| `M16:IDENTITY:06` | captured PI target identity freezes composition/occurrence/production_instance subject and value schema | `PY tests/test_m16_identity.py::test_identity_06` |

## DURATION

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:DURATION:01` | event-free Shot with NULL duration remains legal and M16-ready | `PY tests/test_m16_duration.py::test_duration_01` |
| `M16:DURATION:02` | event-free Shot with zero duration remains legal and M16-ready | `PY tests/test_m16_duration.py::test_duration_02` |
| `M16:DURATION:03` | event creation against NULL/zero duration is rejected, not stored as ordinary not-ready authority | `PY tests/test_m16_duration.py::test_duration_03` |
| `M16:DURATION:04` | duration PATCH cannot become NULL/zero or <= max event time while events exist | `PY tests/test_m16_duration.py::test_duration_04` |
| `M16:DURATION:05` | positive duration plus interior event remains structurally valid | `PY tests/test_m16_duration.py::test_duration_05` |

## START

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:START:01` | target Shot/start predecessor transition is included in start state | `PY tests/test_m16_start_state.py::test_start_01` |
| `M16:START:02` | target Shot/end transition is not projected backward to Shot/start | `PY tests/test_m16_start_state.py::test_start_02` |
| `M16:START:03` | prior Shot/end transition projects into downstream Shot/start | `PY tests/test_m16_start_state.py::test_start_03` |
| `M16:START:04` | M16 events never change state_at(0) | `PY tests/test_m16_start_state.py::test_start_04` |

## FOLD

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:FOLD:01` | semantic order is exactly time_ms then ordinal | `PY tests/test_m16_fold.py::test_fold_01` |
| `M16:FOLD:02` | same-time independent targets are deterministic | `PY tests/test_m16_fold.py::test_fold_02` |
| `M16:FOLD:03` | same-time same-target chain follows explicit ordinal | `PY tests/test_m16_fold.py::test_fold_03` |
| `M16:FOLD:04` | before-state mismatch identifies exact event/expected state and fails | `PY tests/test_m16_fold.py::test_fold_04` |
| `M16:FOLD:05` | UUID/timestamp/insertion permutation cannot alter fold order | `PY tests/test_m16_fold.py::test_fold_05` |
| `M16:FOLD:06` | terminal state equals exact final folded state | `PY tests/test_m16_fold.py::test_fold_06` |
| `M16:FOLD:07` | nonterminal require_handoff marker makes prospective set invalid | `PY tests/test_m16_fold.py::test_fold_07` |
| `M16:FOLD:08` | event-set hash is canonical and changes iff event-set semantic meaning/duration changes | `PY tests/test_m16_fold.py::test_fold_08` |

## HANDOFF

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:HANDOFF:01` | transient event needs no handoff | `PY tests/test_m16_handoff.py::test_handoff_01` |
| `M16:HANDOFF:02` | persistent terminal entity-feature event accepts exact set/clear handoff | `PY tests/test_m16_handoff.py::test_handoff_02` |
| `M16:HANDOFF:03` | persistent relation event accepts exact active/inactive handoff and no set/clear alias | `PY tests/test_m16_handoff.py::test_handoff_03` |
| `M16:HANDOFF:04` | persistent PI-feature event accepts exact set/clear handoff | `PY tests/test_m16_handoff.py::test_handoff_04` |
| `M16:HANDOFF:05` | missing handoff is capture-readiness blocker but not structural-authoring rejection | `PY tests/test_m16_handoff.py::test_handoff_05` |
| `M16:HANDOFF:06` | target mismatch is blocked | `PY tests/test_m16_handoff.py::test_handoff_06` |
| `M16:HANDOFF:07` | semantic value mismatch is blocked | `PY tests/test_m16_handoff.py::test_handoff_07` |
| `M16:HANDOFF:08` | exact-equal preexisting handoff converges without duplicate | `PY tests/test_m16_handoff.py::test_handoff_08` |
| `M16:HANDOFF:09` | conflicting active handoff is never overwritten | `PY tests/test_m16_handoff.py::test_handoff_09` |

## ENTITY

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:ENTITY:01` | entity feature owner must be explicit Shot semantic dependency | `PY tests/test_m16_entity.py::test_entity_01` |
| `M16:ENTITY:02` | entity feature event preserves Shot/start then changes state at event time | `PY tests/test_m16_entity.py::test_entity_02` |
| `M16:ENTITY:03` | entity feature captured target type/unit is historical and current schema edits do not alter history | `PY tests/test_m16_entity.py::test_entity_03` |
| `M16:ENTITY:04` | adopted entity-feature Shot/end transition feeds later Shot | `PY tests/test_m16_entity.py::test_entity_04` |
| `M16:ENTITY:05` | current terminal state is never projected to Shot/start | `PY tests/test_m16_entity.py::test_entity_05` |

## RELATION

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:RELATION:01` | relation event uses exact relation/predicate identity and directional endpoints | `PY tests/test_m16_relation.py::test_relation_01` |
| `M16:RELATION:02` | both relation endpoints must be Shot dependencies | `PY tests/test_m16_relation.py::test_relation_02` |
| `M16:RELATION:03` | relation activation/deactivation fold is deterministic | `PY tests/test_m16_relation.py::test_relation_03` |
| `M16:RELATION:04` | persistent relation handoff exact active/inactive state survives downstream | `PY tests/test_m16_relation.py::test_relation_04` |
| `M16:RELATION:05` | later soft-delete/edit of current relation/transition does not alter captured historical meaning | `PY tests/test_m16_relation.py::test_relation_05` |

## INSTANCE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:INSTANCE:01` | PI event resolves exact stable occurrence and production_instance authority subject | `PY tests/test_m16_instance.py::test_instance_01` |
| `M16:INSTANCE:02` | PI event requires occurrence in selected current M13 binding | `PY tests/test_m16_instance.py::test_instance_02` |
| `M16:INSTANCE:03` | PI before-state is revalidated if current binding selection changes | `PY tests/test_m16_instance.py::test_instance_03` |
| `M16:INSTANCE:04` | PI event captures schema-6 production-world plane as required lower authority | `PY tests/test_m16_instance.py::test_instance_04` |
| `M16:INSTANCE:05` | adopted PI feature Shot/end transition feeds same occurrence downstream | `PY tests/test_m16_instance.py::test_instance_05` |
| `M16:INSTANCE:06` | CreativeEntity fallback/shadow PI event is rejected | `PY tests/test_m16_instance.py::test_instance_06` |

## READY

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:READY:01` | structurally invalid event set is rejected by authoring write | `PY tests/test_m16_readiness.py::test_ready_01` |
| `M16:READY:02` | valid require_handoff event may exist while capture is blocked for missing handoff | `PY tests/test_m16_readiness.py::test_ready_02` |
| `M16:READY:03` | predecessor not-ready condition remains a blocker without changing predecessor field semantics | `PY tests/test_m16_readiness.py::test_ready_03` |
| `M16:READY:04` | M16 issue ordering/content is deterministic | `PY tests/test_m16_readiness.py::test_ready_04` |
| `M16:READY:05` | Shot detail and capture consume the same M16 resolver result grammar | `PY tests/test_m16_readiness.py::test_ready_05` |
| `M16:READY:06` | working_snapshot_hash and differs flag are unavailable when M16 is not ready | `PY tests/test_m16_readiness.py::test_ready_06` |
| `M16:READY:07` | event-free real Shot detail reports intra_shot_ready=true | `PY tests/test_m16_readiness.py::test_ready_07` |

## CAPTURE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:CAPTURE:01` | events/handoffs/duration/start-state planes are read inside one SQLite snapshot | `PY tests/test_m16_capture.py::test_capture_01` |
| `M16:CAPTURE:02` | post-read event or handoff mutation cannot contaminate captured value | `PY tests/test_m16_capture.py::test_capture_02` |
| `M16:CAPTURE:03` | capture-vs-duration patch yields coherent pre or post state, never hybrid | `PY tests/test_m16_capture.py::test_capture_03` |
| `M16:CAPTURE:04` | event-free capture is byte-identical to predecessor schema 1–6 fixture | `PY tests/test_m16_capture.py::test_capture_04` |
| `M16:CAPTURE:05` | event-bearing capture preserves predecessor continuity spec and emits outer schema 7 | `PY tests/test_m16_capture.py::test_capture_05` |
| `M16:CAPTURE:06` | captured target_identity is included in semantic intra_shot block | `PY tests/test_m16_capture.py::test_capture_06` |
| `M16:CAPTURE:07` | persistent captured handoff excludes transition UUID from semantic block | `PY tests/test_m16_capture.py::test_capture_07` |
| `M16:CAPTURE:08` | persistent event without exact handoff cannot capture | `PY tests/test_m16_capture.py::test_capture_08` |

## HIST

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:HIST:01` | continuity-spec schema 1/2 historical behavior remains exact | `PY tests/test_m16_history.py::test_hist_01` |
| `M16:HIST:02` | published outer schema 6 is accepted and validated historically | `PY tests/test_m16_history.py::test_hist_02` |
| `M16:HIST:03` | schema-7 block is rebuilt solely from immutable M16 rows plus same-revision predecessor history | `PY tests/test_m16_history.py::test_hist_03` |
| `M16:HIST:04` | parent spec bytes/hash equal rebuilt children and outer snapshot block | `PY tests/test_m16_history.py::test_hist_04` |
| `M16:HIST:05` | captured target identity canonical bytes/hash are verified | `PY tests/test_m16_history.py::test_hist_05` |
| `M16:HIST:06` | historical re-fold starts from captured entity feature/relation/PI Shot-start state | `PY tests/test_m16_history.py::test_hist_06` |
| `M16:HIST:07` | historical re-fold verifies every before chain and terminal state | `PY tests/test_m16_history.py::test_hist_07` |
| `M16:HIST:08` | captured persistent handoff equals re-folded terminal target state | `PY tests/test_m16_history.py::test_hist_08` |
| `M16:HIST:09` | current event/duration/transition/definition edits do not change historical read | `PY tests/test_m16_history.py::test_hist_09` |
| `M16:HIST:10` | different current source UUIDs with identical semantic capture converge to existing ShotRevision and preserve first-publication audit provenance | `PY tests/test_m16_history.py::test_hist_10` |
| `M16:HIST:11` | missing/extra/corrupt captured event/target/handoff row fails invariant | `PY tests/test_m16_history.py::test_hist_11` |

## PROPOSAL

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:PROPOSAL:01` | Proposal Grammar v1 accepts exactly one candidate event plus non-authoritative persistence suggestion | `PY tests/test_m16_proposals.py::test_proposal_01` |
| `M16:PROPOSAL:02` | proposal canonical bytes above 65,536 are rejected | `PY tests/test_m16_proposals.py::test_proposal_02` |
| `M16:PROPOSAL:03` | proposal validates time against source ShotRevision captured duration | `PY tests/test_m16_proposals.py::test_proposal_03` |
| `M16:PROPOSAL:04` | Generation-backed proposal pins exact Generation ShotRevision id/hash | `PY tests/test_m16_proposals.py::test_proposal_04` |
| `M16:PROPOSAL:05` | Take-backed proposal pins coherent Take/Generation/Shot/ShotRevision lineage | `PY tests/test_m16_proposals.py::test_proposal_05` |
| `M16:PROPOSAL:06` | imported proposal has no Generation/Take ids but still pins exact source ShotRevision | `PY tests/test_m16_proposals.py::test_proposal_06` |
| `M16:PROPOSAL:07` | analyzer proposal always pins id/version/parameter hash including canonical empty parameters | `PY tests/test_m16_proposals.py::test_proposal_07` |
| `M16:PROPOSAL:08` | proposal existence does not alter working hash/readiness or create transition | `PY tests/test_m16_proposals.py::test_proposal_08` |
| `M16:PROPOSAL:09` | stale proposal adoption never silently rebases onto current truth | `PY tests/test_m16_proposals.py::test_proposal_09` |
| `M16:PROPOSAL:10` | proposal ignore may be recorded while stale because it creates no authority | `PY tests/test_m16_proposals.py::test_proposal_10` |

## ADOPT

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:ADOPT:01` | direct event adoption creates or exact-matches handoff atomically with review | `PY tests/test_m16_adoption.py::test_adopt_01` |
| `M16:ADOPT:02` | direct decline_persistence changes unreviewed require_handoff event to transient and records result hash | `PY tests/test_m16_adoption.py::test_adopt_02` |
| `M16:ADOPT:03` | previously adopted source hash cannot receive competing decline review; later regret requires PATCH/new hash | `PY tests/test_m16_adoption.py::test_adopt_03` |
| `M16:ADOPT:04` | proposal adopt_event_only always creates transient event even when suggestion says persist | `PY tests/test_m16_adoption.py::test_adopt_04` |
| `M16:ADOPT:05` | proposal adopt_persistence creates event + exact handoff atomically | `PY tests/test_m16_adoption.py::test_adopt_05` |
| `M16:ADOPT:06` | proposal ignore creates no authority | `PY tests/test_m16_adoption.py::test_adopt_06` |
| `M16:ADOPT:07` | multi-proposal same-source batch checks working source basis once before mutation | `PY tests/test_m16_adoption.py::test_adopt_07` |
| `M16:ADOPT:08` | batch prospective fold includes every selected adopted proposal and existing event | `PY tests/test_m16_adoption.py::test_adopt_08` |
| `M16:ADOPT:09` | batch rollback leaves no partial event/transition/review rows | `PY tests/test_m16_adoption.py::test_adopt_09` |
| `M16:ADOPT:10` | review_basis_hash and batch_basis_hash follow exact canonical roots | `PY tests/test_m16_adoption.py::test_adopt_10` |
| `M16:ADOPT:11` | exact retry returns exact non-null committed evidence and detects later result drift | `PY tests/test_m16_adoption.py::test_adopt_11` |
| `M16:ADOPT:21` | R7 direct grammar: the two-field adopt succeeds from `working_snapshot_hash == null`, then the Shot becomes M16-ready and obtains its ordinary authoritative working snapshot hash | `PY tests/test_m16_adoption.py::test_adopt_21` |
| `M16:ADOPT:22` | direct review basis/operation grammar carries no working-snapshot field; exact §7.5.1 R7 roots | `PY tests/test_m16_adoption.py::test_adopt_22` |

## TAKE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:TAKE:01` | Take approval continues to mutate only approved_take_id/current predecessor review metadata | `PY tests/test_m16_take_isolation.py::test_take_01` |
| `M16:TAKE:02` | Take approval cannot create event/proposal review/handoff | `PY tests/test_m16_take_isolation.py::test_take_02` |
| `M16:TAKE:03` | rejecting Take does not undo adopted persistence | `PY tests/test_m16_take_isolation.py::test_take_03` |
| `M16:TAKE:04` | persistence adoption does not approve Take | `PY tests/test_m16_take_isolation.py::test_take_04` |
| `M16:TAKE:05` | already captured Take/Generation remains pinned to old ShotRevision after M16 authority changes | `PY tests/test_m16_take_isolation.py::test_take_05` |

## RACE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:RACE:01` | event create versus duration patch has only legal serialized outcomes | `PY tests/test_m16_races.py::test_race_01` |
| `M16:RACE:02` | event coordinate patch race commits at most one conflicting coordinate | `PY tests/test_m16_races.py::test_race_02` |
| `M16:RACE:03` | event delete versus dependent later event cannot leave false before-chain | `PY tests/test_m16_races.py::test_race_03` |
| `M16:RACE:04` | event edit versus persistence adoption detects stale source/event-set basis | `PY tests/test_m16_races.py::test_race_04` |
| `M16:RACE:05` | handoff edit versus adoption exact-match-or-conflict, never overwrite | `PY tests/test_m16_races.py::test_race_05` |
| `M16:RACE:06` | proposal batch versus current Shot change either uses exact source basis or conflicts | `PY tests/test_m16_races.py::test_race_06` |
| `M16:RACE:07` | concurrent identical proposal-batch retries converge completely | `PY tests/test_m16_races.py::test_race_07` |
| `M16:RACE:08` | capture versus event/handoff mutation sees one coherent snapshot | `PY tests/test_m16_races.py::test_race_08` |
| `M16:RACE:09` | Take approval versus adoption has no hidden ordering dependency | `PY tests/test_m16_races.py::test_race_09` |

## RECOVERY

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:RECOVERY:01` | 0017 restore verifies M13+M14+M15+M16 semantic history | `PY tests/test_m16_recovery.py::test_recovery_01` |
| `M16:RECOVERY:02` | working event canonical hash corruption fails | `PY tests/test_m16_recovery.py::test_recovery_02` |
| `M16:RECOVERY:03` | proposal grammar/hash/source corruption fails | `PY tests/test_m16_recovery.py::test_recovery_03` |
| `M16:RECOVERY:04` | review operation/review-basis/result corruption fails | `PY tests/test_m16_recovery.py::test_recovery_04` |
| `M16:RECOVERY:05` | captured target/event/handoff/spec corruption fails | `PY tests/test_m16_recovery.py::test_recovery_05` |
| `M16:RECOVERY:06` | captured-state re-fold mismatch fails recovery | `PY tests/test_m16_recovery.py::test_recovery_06` |
| `M16:RECOVERY:07` | 0011–0016 historical heads remain accepted with exact head-specific policies | `PY tests/test_m16_recovery.py::test_recovery_07` |
| `M16:RECOVERY:08` | 0017 Blob-FK inventory is exactly 8 and no M16 Blob FK exists | `PY tests/test_m16_recovery.py::test_recovery_08` |

## EXEC

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:EXEC:01` | any non-empty schema-7 intra_shot authority including all-transient events is refused | `PY tests/test_m16_generation_fence.py::test_exec_01` |
| `M16:EXEC:02` | schema-7 refusal occurs before Generation/GenerationInput insertion | `PY tests/test_m16_generation_fence.py::test_exec_02` |
| `M16:EXEC:03` | schema-7 refusal occurs before derived spatial/observation publication or queueing | `PY tests/test_m16_generation_fence.py::test_exec_03` |
| `M16:EXEC:04` | schema-7 is never lowered/stripped/converted to prompt text or sent to lower worker | `PY tests/test_m16_generation_fence.py::test_exec_04` |
| `M16:EXEC:05` | pre-M16 Exact Rerun remains pinned to captured old ShotRevision and does not read current M16 state | `PY tests/test_m16_generation_fence.py::test_exec_05` |

## UI

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:UI:01` | timeline displays server-projected time/start/terminal/handoff state | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:01` |
| `M16:UI:02` | UI prevents ordinary submission at time zero/end while retaining server validation | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:02` |
| `M16:UI:03` | before-state mismatch displays event coordinate/stored before/expected state | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:03` |
| `M16:UI:04` | proposal review is visually separate from Take approval | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:04` |
| `M16:UI:05` | adopt_event_only explicitly warns persistence suggestion is discarded | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:05` |
| `M16:UI:06` | stale proposal, transient-vs-boundary divergence, and nonterminal-persistence recovery actions are server-derived and visible | `FE apps/web/src/__tests__/IntraShotPanel.test.tsx#M16:UI:06` |

## SCALE

| Cell | Frozen claim | Exact owner |
|---|---|---|
| `M16:SCALE:01` | event write above 10,000 active events is rejected with stable code | `PY tests/test_m16_scale.py::test_scale_01` |
| `M16:SCALE:02` | M16 resolver uses <=20 SQL statements for 1 through 10,000 events | `PY tests/test_m16_scale.py::test_scale_02` |
| `M16:SCALE:03` | 10,000 minimal legal events resolve without N+1 target/handoff queries | `PY tests/test_m16_scale.py::test_scale_03` |
| `M16:SCALE:04` | event/proposal list default page 100 and max 500 are enforced | `PY tests/test_m16_scale.py::test_scale_04` |
| `M16:SCALE:05` | proposal review batch accepts up to 10,000 and rejects larger body count | `PY tests/test_m16_scale.py::test_scale_05` |


# 23. Source-gate acceptance scenarios

## 23.1 Entity-bound injury

Given:

```text
Shot duration = 5000 ms
Eva exact semantic dependency
injury feature start = uninjured
```

Prove:

```text
t=0               uninjured
3100 ms event      uninjured → fresh_injury
3099 ms            uninjured
3100+ ms           fresh_injury
Shot/end−          fresh_injury
```

Before persistence adoption, a direct authoritative `require_handoff` event is structurally valid but capture-blocked if no handoff exists. Take approval alone creates no persistent state.

After explicit persistence adoption:

```text
Shot/end feature transition = fresh_injury
later Shot/start = fresh_injury
```

Historical source ShotRevision/Generation/Take stays unchanged. A newly captured schema-7 ShotRevision is authoritative history but current M16 workflows do not execute it; Generation creation fails closed with `INTRA_SHOT_REALIZATION_UNSUPPORTED` until a later event-aware execution contract is implemented.

## 23.2 Instance-bound chair

Given:

```text
chair-07 stable M12/M13 occurrence identity
M13 authority subject = production_instance
configuration feature start = upright
positive Shot duration
```

Prove:

```text
interior event          upright → fallen
Shot/end−               fallen
explicit PI handoff     fallen
later Shot              same chair-07 occurrence resolves fallen
```

No occurrence re-mint, Production Revision replacement, or CreativeEntity substitution is used to obtain continuity. A lawful M15 Production Revision update that preserves the occurrence/state rows does not change the event target identity.

## 23.3 Multi-event post-Take proposal batch

Given one captured source ShotRevision/Generation/Take and two analyzer proposals sharing that exact source basis:

```text
proposal A: injury at 3100 ms, persist
proposal B: wardrobe_condition at 4200 ms, persist
```

Prove in one `review-batch` transaction:

```text
current working snapshot == shared source hash at transaction start
both proposal hashes/source lineages verified before mutation
prospective event set contains A + B together
both before-chains valid
each required handoff is created/exact-matched
both review rows carry one shared batch_basis_hash
all event/handoff/review rows commit atomically
```

The first adopted proposal cannot make the second proposal stale inside the same batch. A later separate proposal still pinned to the old source becomes stale after the batch changes current authority.

# 24. Required failure scenarios

The final implementation is incomplete unless all are executable failures or fail-closed invariant checks as applicable:

1. time-zero event rejected;
2. time-at-Shot-end event rejected;
3. safe-integer overflow/bool/float timing rejected;
4. event creation with missing/zero duration rejected;
5. event outside duration rejected;
6. event count above 10,000 rejected;
7. duration patch cannot invalidate an existing event set;
8. event before-state contradicts Shot/start/fold state;
9. inserting/deleting an event cannot leave a later event with a false `before` state;
10. same active event coordinate duplicated;
11. entity feature event targets a non-dependent Entity;
12. relation event lacks both directional dependency endpoints or mismatches predicate identity;
13. PI event points to wrong occurrence/authority subject or stale binding context;
14. same target has `require_handoff` marker before a later target event;
15. persistent event on an unassigned Shot cannot fabricate a Shot/end handoff;
16. persistent event missing handoff;
17. handoff semantic mismatch;
18. handoff target/vocabulary mismatch;
19. proposal JSON above 65,536 canonical bytes rejected;
20. malformed/multi-candidate Proposal Grammar v1 rejected;
21. analyzer proposal without parameter hash rejected;
22. proposal from mismatched Generation/Take/ShotRevision id/hash rejected;
23. imported proposal without exact source ShotRevision rejected;
24. stale proposal cannot silently rebase;
25. mixed-source authority-creating proposal batch rejected;
26. batch with one invalid candidate commits no event/handoff/review row;
27. Take approval cannot create event or handoff;
28. persistence adoption cannot approve Take;
29. proposal `ignore` cannot create authority;
30. event `decline_persistence` cannot be written as no-authority review; it must produce a new transient event hash;
31. already-adopted source event hash cannot acquire a competing decline review;
32. proposal-adopted event semantic PATCH cannot retain proposal_adoption current provenance;
33. current event/handoff/definition changes cannot mutate historical ShotRevision;
34. published schema-6 historical continuity remains inspectable without current state;
35. outer schema-7 `intra_shot` cannot disagree with immutable M16 companion rows;
36. corrupted captured target identity or re-fold chain fails historical inspection;
37. semantically identical capture from different source UUIDs cannot create a divergent ShotRevision solely because audit ids differ;
38. schema-7 history cannot consult current state;
39. any non-empty schema-7 ShotRevision cannot silently execute through a lower-schema workflow;
40. schema-7 refusal must occur before Generation/derived-artifact/queue side effects;
41. Exact Rerun cannot consult current M16 state;
42. corrupted M14 recovery evidence at head 0015 fails after P0;
43. corrupted M15 recovery evidence at head 0016 fails after P0;
44. 0017 recovery Blob-FK inventory drift from exact 8 paths fails structural verification.

# 25. Scope exclusions

M16 R6 explicitly does not implement:

```text
per-frame database state
continuous story clock
body/facial rig animation
Vocal Performance / Dialogue timing
universal Performance Revision
simulation engine
spatial trajectory event curves
material/lighting state timing
a universal relation ontology
executor-specific event conditioning
automatic event extraction as authority
automatic persistence from approved pixels
NLE/editorial timeline semantics
```

Those capabilities may consume M16's exact timing/handoff contract later.

---

# 26. Implementation boundary / expected source surface

Expected new or directly modified areas are limited to:

```text
server/alembic/versions/0017_m16_intra_shot_consequences.py
server/soloring/continuity/...
server/soloring/production_world/...       # shared PI transition helper only as needed
server/soloring/domain/revisions.py        # same-read capture extension
server/soloring/continuity/snapshots.py    # one canonical Shot snapshot builder
server/soloring/generation/service.py       # schema-7 fail-closed publication fence only
server/soloring/api/continuity.py or dedicated intra_shot.py
server/soloring/api/schemas/...
server/soloring/recovery/backup.py
server/soloring/db/models.py
server/soloring/errors.py
apps/web/src/... Shot/Review continuity surfaces
tests/test_m16_*.py
scripts/m16_validate_baseline.py
scripts/m16_validate_proof_map.py
scripts/m16_validate_boundary.py
scripts/m16_validate_source_fit.py
.github/workflows/ci.yml                    # add M16 validators only; no trigger broadening
```

Changes to executor model pins, Comfy launch policy, workflow artifact formats, M14 observation materialization, or M15 compatibility semantics are outside ordinary M16 scope. The generation-service change is a refusal fence only; it does not add event realization.

Exactly **two predecessor-remediation exceptions** are authorized by the frozen plan boundary once the plan itself is accepted:

```text
P0-A  recovery head dispatch + M14/M15 semantic verification correction
P0-B  historical inspector acceptance/validation of already-published schema 6
```

They must land before 0017 data-plane closure and must be classified narrowly by `m16_validate_boundary.py`. SF-08's M15 exact-retry translator-response defect is explicitly **not** authorized by M16 and remains separate debt.

# 27. Validator contract

## `m16_validate_baseline.py`

Must prove exact:

```text
M15 tag object     4c83eaaaee9c1099512ce01ed9567d737ebee1c9
M15 peeled commit  30ea135f3b2339491e9b36eaee2d0d8bc4ab8585
M15 tree           db21568a3522a5ed2fa6fab44d1f9741d6d71ad2
M15 Release        388490752
migration head     0016_m15_revision_compatibility
```

It must identify the tag as annotated and must not require it to be cryptographically signed.

## `m16_validate_proof_map.py`

Must hard-code exactly **162** cells and the §22 family counts. It must reject:

```text
missing cell
extra/unknown cell
duplicate cell
duplicate exact owner
pending/TODO owner
owner path absent
PY owner not collectable
FE owner marker absent
```

The validator never discovers the expected universe from tests; the plan's frozen cell set is the authority.

## `m16_validate_boundary.py`

Must fail any unauthorized changed path or forbidden subsystem vocabulary. It must explicitly classify P0-A and P0-B separately rather than widening predecessor boundary allowlists broadly.

It must allow the generation-service file only for the fail-closed schema-7 fence and tests; any event realization/workflow/executor mutation is a boundary failure.

## `m16_validate_source_fit.py`

Must prove:

- existing Shot duration remains nullable/nonnegative globally;
- M16 code does not tighten predecessor Shot API/DB schema;
- target XOR/active partial-index grammar matches migration and ORM;
- M16 handoffs target exact existing M7/M13 transition domains and exact predecessor vocabularies;
- the captured `authority_subject_kind` field maps one-to-one from `composition_occurrence_authority_subjects.subject_kind`, preserving the predecessor's exact closed vocabulary;
- Take approval endpoint contains no M16 adoption call;
- event-free predecessor canonical snapshot fixtures remain byte-identical;
- event-bearing capture uses top-level `intra_shot` schema 1 + outer snapshot schema 7 and cannot be lowered;
- captured target identity is in schema-7 semantic bytes;
- predecessor `continuity_spec_json/hash` remain schema 1/2 and byte-compatible;
- historical inspector accepts published schema 6 before schema 7 and does not query current Production World;
- generation creation refuses every non-empty schema 7 before **all** Generation-side writes/publications;
- Proposal Grammar v1 is single-candidate and size-bounded;
- analyzer parameter hash is unconditional for analyzer proposals;
- P0 recovery dispatch is explicit per head through 0016;
- 0017 Blob-FK inventory remains exactly 8;
- executor/materializer sources are unchanged unless a later reviewed plan revision explicitly authorizes them.

# 28. Closure battery and exact command manifest

A final M16 head may claim closure only after all gates run on that **exact unchanged head**. Earlier/red/cancelled/superseded runs are non-certifying.

## 28.1 Required semantic gates

1. M16-P0 predecessor repair suite green.
2. M16 baseline validator green.
3. All predecessor proof maps/boundaries green.
4. M16 proof map exactly 162/162, zero pending cells.
5. M16 boundary/source-fit validators green.
6. Migration upgrade/downgrade/fail-closed/parity tests green.
7. Entity-bound source-gate scenario green.
8. Instance-bound source-gate scenario green.
9. Multi-proposal batch source-gate scenario green.
10. 44 required-failure scenarios green.
11. Race/idempotency suite green.
12. Historical re-fold + schema-6 compatibility + Exact Rerun suite green.
13. Schema-7 generation fail-closed fence/zero-side-effect suite green.
14. Recovery per-head dispatch + corruption + exact-8-Blob-FK suite green.
15. Scale/query-count suite green.
16. Full backend suite twice on the exact head.
17. Frontend tests/typecheck/production build/security audits green.
18. Final source review reconciled with every non-outdated finding dispositioned.
19. Exact branch head/tree/test identities recorded before any merge authorization.

## 28.2 Exact repository-root backend command sequence

The M16 CI/job and local certification use the published predecessor commands plus the M16 validators. From repository root:

```bash
python scripts/m10f_validate_proof_map.py
python scripts/m11_validate_proof_map.py
python scripts/m12_validate_proof_map.py
python scripts/m13_validate_proof_map.py
python scripts/m13_validate_boundary.py
python scripts/hygiene_validate_proof_map.py
python scripts/hygiene_validate_boundary.py
python scripts/next_security_validate_proof_map.py
python scripts/next_security_validate_boundary.py
python scripts/m14_validate_baseline.py
python scripts/m14_validate_proof_map.py
python scripts/m14_validate_boundary.py
python scripts/m14_validate_source_fit.py
python scripts/m15_validate_proof_map.py
python scripts/m16_validate_baseline.py
python scripts/m16_validate_proof_map.py
python scripts/m16_validate_boundary.py
python scripts/m16_validate_source_fit.py
python -c "from pathlib import Path; assert not Path('m10f-scale-pkgs').exists(), 'repo-root residue present'"
python -m pytest -q tests server/tests/test_post_m15_recovery_hardening.py
python -c "from pathlib import Path; assert not Path('m10f-scale-pkgs').exists(), 'repo-root residue present after backend suite'"
```

The complete block above is then run a **second time** on the same exact head for the required backend ×2 certification. Focused suites may run earlier, but they do not replace these two final full runs.

## 28.3 Exact frontend command sequence

From `apps/web`:

```bash
npm ci
python ../../scripts/next_security_validate.py --pins-only
npm test
npx next typegen
npx tsc --noEmit
SOLORING_API_ORIGIN=http://127.0.0.1:65534 npm run build
npm audit --omit=dev --json > /tmp/m16-nsec-audit.json || true
python ../../scripts/hygiene_validate_npm_audit.py /tmp/m16-nsec-audit.json
python ../../scripts/next_security_validate.py /tmp/m16-nsec-audit.json
```

CI may substitute `$RUNNER_TEMP` for `/tmp`; the audit JSON consumed by both validators must be the same bytes from the same `npm audit` invocation.

No later source correction inherits certification from an earlier head.

# 29. Product exit claim

After all gates above close, the maximum justified claim is:

> **SoloRing can represent continuity-significant state changes at exact sparse times inside a Shot, preserve the exact Shot-start truth, deterministically derive the Shot's terminal state, atomically review multiple same-source proposals, and explicitly adopt agreeing Shot/end consequences into downstream entity- or Production-Instance continuity without making Take approval or generated pixels the author of production state.**

M16 does not by itself prove arbitrary animation/performance execution of that event timing. Authoring any active M16 event makes a new capture schema 7, and current generation creation deliberately refuses schema-7 authority. Therefore M16 is an authority/capture/review foundation; rendering value for event-aware timing requires a later reviewed A7 execution milestone.

# 30. Authorization boundary

This document is a planning artifact and R6 freeze candidate.

Creating or reviewing this R6 does **not** authorize:

```text
M16 branch creation
P0 source corrections
source edits
migration 0017 creation
commits
PR publication
merge
M16 tag/release
```

If R6 is explicitly accepted/frozen, that freezes the implementation contract only. Implementation still begins **only after a separate explicit implementation authorization**. Generic continuation during plan review must not be interpreted as source-mutation authority.
