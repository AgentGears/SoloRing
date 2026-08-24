# SoloRing M10C — Temporal Staging Implementation Plan

**Status:** Authorized implementation contract — **implementation authorized 2026-08-25**; publication/tagging NOT authorized
**Milestone:** M10C — Temporal Staging
**Preconditions:** M10A CLOSED; M10B CLOSED
**Predecessor baseline:** M10B @ 4054e7e2a004beabbd0341d4a2bce683f22f3175
**Predecessor tree:** 7da717f391ac77a2d3752c223eae78ed2241568c
**Frozen architecture:** SoloRing M10 r3 remains authoritative. 
**Successor boundary:** M10D owns ShotSpatialPlan authority, approved-world composition, the complete current spatial resolver, spatial readiness/hash integration, and ShotRevision schema 5.
**Authorization boundary:** This document authorizes M10C implementation only. It authorizes no publication, tagging, release, branch-protection change, or M10D/M10E work.

---

## 1. Objective

M10C installs SoloRing's **persistent temporal staging authority** for movable story-world Entities.

At M10C completion:

```text
SpatialWorld
    ↓
SpatialTrack
    ↓
explicit SpatialTransition at narrative boundary
    ↓
random-access effective staging at arbitrary Shot/start
```

Example:

```text
Shot 20/start
Eva = lobby entrance

Shot 20/end
SpatialTransition(set):
Eva = near front desk

Shot 21/start
resolver directly returns:
Eva = near front desk
```

Resolving Shot 21 must not require resolving, rendering, loading, or replaying Shot 20 first.

M10C answers:

> **For one specified SpatialWorld, one target Shot, and the exact semantic EntityRevisions already resolved for that Shot, what persistent movable-Entity placements are effective at Shot/start, and which explicit SpatialTransitions made those placements true?**

M10C does not determine:

* which SpatialWorld is applicable to the Shot;
* which SpatialWorldState or SpatialWorldRevision is current;
* fixed-frame versus SpatialTrack placement conflicts;
* fixed-frame EntityRevision consistency;
* ShotSpatialPlan authority;
* camera/blocking/axis constraints;
* the final `SpatialContinuityPack`;
* the final spatial working hash;
* schema-5 ShotRevision capture.

Those are M10D responsibilities.

---

# 2. Governing authority

The M10C authority chain is:

```text
M7 semantic authority
        ↓
exact dependent EntityRevision identities
        ↓
SpatialTrack identity
        ↓
explicit SpatialTransition history
        ↓
canonical M7 narrative ordering
        ↓
effective temporal staging
        ↓
M10D complete spatial composition
        ↓
immutable ShotRevision
```

Never:

```text
rendered Take
UI playback
animation interpolation
model output
depth map
executor state
timestamp
UUID ordering
database iteration order
        ↓
persistent staging authority
```

Persistent downstream placement changes only through an explicit active `SpatialTransition`.

M10C applies the established direct temporal-resolution, coherent-read, fail-closed, no-invented-tiebreaker, UI-authority, and bounded-query rules from the Architecture Pattern Register. 

---

# 3. Milestone scope

## 3.1 Included

M10C implements:

1. `SpatialTrack` create/read/list/PATCH/delete.
2. `SpatialTransition` create/read/list/PATCH/delete.
3. Same-Project and active-parent validation.
4. Active `(SpatialWorld, Entity)` track uniqueness.
5. Exact `set|clear` transform semantics.
6. Canonical narrative-anchor validation.
7. Random-access effective staging at target Shot/start.
8. Exact semantic EntityRevision attachment.
9. Required/optional staging readiness.
10. Canonical absence after `clear`.
11. Deterministic capture-ready staging projection.
12. Byte-identical staging serialization under shuffled database return order.
13. Track/transition authoring UI.
14. Target-Shot staging inspection.
15. Mechanically forced concurrency proofs.
16. Complete boundary-semantics tests.
17. Representative ~2,500-Shot endpoint-level query-shape proof.
18. Full predecessor regression preservation.

## 3.2 Excluded

M10C does not implement:

* applicable-world selection;
* approved SpatialWorldRevision resolution;
* fixed-frame/track placement conflicts;
* fixed-frame EntityRevision cross-checking;
* ShotSpatialPlan mutation/CAS;
* camera optics or keyframes;
* blocking authority;
* Shot/end blocking handoff;
* cinematic-axis enforcement;
* the complete current M10 resolver;
* final spatial readiness or issue precedence;
* `SpatialContinuityPack` hashing;
* Shot working-hash integration;
* ShotRevision schema 5;
* `shot_revision_spatial_track_states`;
* historical spatial reconstruction;
* spatial realization;
* workflow-spec schema 3 integration;
* Generation integration;
* worker spatial translation;
* Exact Rerun M10 integration;
* D0 derivative generation;
* automatic origin transitions;
* automatic carry-forward;
* entity instancing;
* per-frame/interpolated authority;
* a new database migration.

---

# 4. Existing authority reused

## 4.1 Narrative ordering

M10C must reuse:

```text
server/soloring/narrative/order.py
```

as the single Project topology → boundary stream → rank authority.

Its existing semantics are:

```text
Sequence/start
    Scene/start
        Shot/start
        Shot/end
    Scene/end
Sequence/end
```

and effective-state eligibility is inclusive:

```text
transition_rank <= target_shot_start_rank
```

No M10C implementation may independently flatten narrative topology or derive alternative ranks.

## 4.2 M7 resolver pattern

M10C follows the existing M7 state-resolution architecture:

```text
caller-owned AsyncConnection
        ↓
one coherent SQLite read
        ↓
set-oriented source loading
        ↓
canonical narrative rank
        ↓
single effective winner
        ↓
explicit source provenance
        ↓
fail closed on impossible stored state
```

## 4.3 Existing schema

Migration `0010` already provides:

```text
spatial_tracks
spatial_transitions
shot_spatial_plans
```

with the frozen structural constraints.

Therefore:

> **M10C adds no migration.**

---

# 5. Canonical staging projection

M10C produces a deterministic capture-ready value for later M10D composition.

It does not persist a new historical row or staging hash.

## 5.1 Effective state

Recommended internal value:

```python
@dataclass(frozen=True)
class EffectiveSpatialTrackState:
    spatial_track_id: str
    entity_id: str
    entity_revision_id: str
    requirement: str

    x_mm: int
    y_mm: int
    z_mm: int
    yaw_udeg: int
    pitch_udeg: int
    roll_udeg: int

    source_transition_id: str
    source_anchor_type: str
    source_anchor_id: str
    source_boundary: str
```

Equivalent use of the established immutable transform value is acceptable.

## 5.2 Projection shape

Canonical projection:

```json
[
  {
    "spatial_track_id": "...",
    "entity_id": "...",
    "entity_revision_id": "...",
    "requirement": "required",
    "transform": {
      "translation_mm": [0, 0, -1200],
      "rotation_udeg": [0, 0, 0]
    },
    "source_transition_id": "...",
    "source_anchor_type": "shot",
    "source_anchor_id": "...",
    "source_boundary": "end"
  }
]
```

Sort before serialization by exactly:

```text
(entity_id, spatial_track_id)
```

Serialize using SoloRing's existing canonical JSON function:

```text
soloring.domain.canonical.canonical_json_bytes
```

No second M10-only JSON serializer is created.

## 5.3 Determinism contract

The gate is byte-level:

```text
same semantic state
+
different Track/Transition database return order
        ↓
exact same canonical staging bytes
```

Structural equivalence alone is insufficient.

---

# 6. M10C-1 — SpatialTrack lifecycle

## 6.1 Service

Implement in:

```text
server/soloring/spatial/tracks.py
```

Operations:

```python
create_track(...)
get_track(...)
list_tracks(...)
patch_track(...)
delete_track(...)
```

Routes:

```text
POST   /spatial-worlds/{world_id}/tracks
PATCH  /spatial-tracks/{track_id}
DELETE /spatial-tracks/{track_id}
```

## 6.2 Creation

One authority-preserving transaction:

```text
BEGIN IMMEDIATE
↓
load active SpatialWorld
↓
load active CreativeEntity
↓
verify same Project
↓
validate requirement
↓
verify no active (world, Entity) Track
↓
INSERT
↓
COMMIT
```

Active identity:

```text
(spatial_world_id, entity_id)
```

Duplicate active identity becomes:

```text
SPATIAL_ENTITY_INSTANCING_UNSUPPORTED
```

Raw uniqueness errors do not cross the service boundary.

## 6.3 Identity immutability

These are immutable:

```text
spatial_world_id
entity_id
```

PATCH mutates only:

```text
requirement
```

in schema 1.

A track cannot be retargeted to another world or Entity because doing so would reinterpret its transition history.

## 6.4 Requirement

Domain:

```text
required
optional
```

Requirement mutation:

* occurs under `BEGIN IMMEDIATE`;
* updates SQLite-owned `updated_at`;
* changes future current readiness;
* does not modify transition history;
* does not modify immutable history.

## 6.5 Delete policy

Required Track:

```text
DELETE
→ reject
```

Production must explicitly perform:

```text
required
→ optional
→ satisfy reference guards
→ delete
```

## 6.6 Reference guards

An optional Track cannot be deleted while:

```text
an active SpatialTransition references it
OR
a current ShotSpatialPlan blocking entry references it
```

The blocking-plan predicate is:

```text
plan spatial_world_id == track.spatial_world_id
AND
exists blocking entry where
    blocking[].spatial_track_id == track.id
```

### M10C read-only ShotSpatialPlan reference reader

No authoritative ShotSpatialPlan parser/canonicalizer exists yet; complete plan authority belongs to M10D.

M10C therefore implements a **minimal read-only structural reader** solely for this delete guard.

Its responsibilities are limited to safely determining whether an existing current `shot_spatial_plans.plan_json` references the Track.

It must:

```text
parse JSON
require a top-level object
recognize only frozen plan schema_version = 1
require a structurally readable spatial_world_id
require a structurally readable blocking collection
require every inspected blocking item to expose an unambiguous
    spatial_track_id
```

It may additionally validate top-level structural forms necessary to establish that the document is recognizably the frozen schema-1 plan document.

It must **not**:

* canonicalize a plan;
* compute or verify plan authority;
* validate camera mathematics;
* validate blocking-vs-staging semantics;
* validate axis constraints;
* become the M10D ShotSpatialPlan parser;
* write or repair a plan.

If the stored document is syntactically unreadable, has an unknown schema, or is structurally ambiguous such that Track-reference absence cannot be proven:

```text
INTERNAL_INVARIANT_VIOLATION
```

Deletion stops.

Conservative rule:

> **If M10C cannot prove that the current plan does not reference the Track, it must not delete the Track.**

A raw string search for Track IDs is forbidden.

## 6.7 No automatic initial state

Track creation never synthesizes:

```text
origin
identity transform
previous frame position
first generated position
```

A required Track without an effective `set` remains unresolved.

---

# 7. M10C-2 — SpatialTransition lifecycle

## 7.1 Service

Operations:

```python
create_transition(...)
get_transition(...)
list_transitions(...)
patch_transition(...)
delete_transition(...)
```

Routes:

```text
POST   /spatial-tracks/{track_id}/transitions
PATCH  /spatial-transitions/{transition_id}
DELETE /spatial-transitions/{transition_id}
```

## 7.2 Coordinate identity

Active coordinate:

```text
spatial_track_id
anchor_type
anchor_id
boundary
```

with active uniqueness on:

```text
(track_id, anchor_type, anchor_id, boundary)
```

Conflicts become the frozen transition-domain error; raw DB exceptions do not leak.

## 7.3 Narrative anchors

Allowed:

```text
anchor_type:
    sequence
    scene
    shot

boundary:
    start
    end
```

Every write verifies that the anchor:

* exists;
* is active;
* belongs to the Track world's Project;
* is a valid canonical narrative anchor.

## 7.4 Aggregate operation

Exactly two legal forms exist:

```text
set
→ all six transform columns non-NULL

clear
→ all six transform columns NULL
```

Partial transforms are impossible through the service.

## 7.5 Numeric contract

Reuse existing M10 math authority:

```text
translation:
signed JavaScript-safe integer millimeters

rotation:
signed integer microdegrees
normalized independently into
[-180000000, +180000000)
```

No float or numeric-string authority is accepted.

## 7.6 PATCH

PATCH operates on one prospective complete transition.

Transport semantics distinguish:

```text
field omitted
→ preserve

explicit null
→ real null when aggregate semantics allow it
```

Use `model_fields_set`/sentinel handling where needed.

Examples:

```text
set → clear
    all six transform columns become NULL

clear → set + complete transform
    legal

clear → set without complete transform
    reject

set → PATCH x_mm only
    other transform coordinates preserved
    complete prospective set revalidated
```

Anchor/boundary changes are validated as a complete prospective coordinate before mutation.

## 7.7 Delete/recreate

Deletion soft-deletes the transition.

A later transition may occupy the same active coordinate but receives a fresh identity.

Old transition IDs are never recycled.

---

# 8. M10C-3 — Random-access staging resolver

## 8.1 Home

Implement:

```text
server/soloring/spatial/staging.py
```

This is a temporal **subresolver**, not M10D's complete spatial resolver.

Recommended interface:

```python
async def resolve_effective_staging(
    conn: AsyncConnection,
    *,
    shot_id: str,
    spatial_world_id: str,
    resolved_entity_revisions: Mapping[str, str],
) -> StagingResolutionOutcome:
    ...
```

## 8.2 Frozen §18 split

M10C implements frozen §18 temporal resolution:

```text
steps 1–10
+
canonical sorting/projection step 12
```

Frozen §18 step 11:

```text
effective SpatialTrack
vs
fixed-frame placement authority
```

requires the selected approved SpatialWorldRevision and therefore remains explicitly deferred to M10D.

It is deferred, not removed.

## 8.3 Exact semantic inputs

`resolved_entity_revisions` is:

```text
dependent Entity ID
→ exact current semantic EntityRevision ID
```

already obtained inside the same coherent read context.

M10C does not independently ask later:

```text
"What is this Entity's current revision now?"
```

## 8.4 Relevant transition data

`relevant_transition_data = true` iff:

> At least one active SpatialTransition exists on an active SpatialTrack in the specified SpatialWorld whose Entity belongs to the supplied dependent-Entity set.

It excludes:

* unrelated Entities;
* other SpatialWorlds;
* tombstoned Tracks;
* tombstoned Transitions.

## 8.5 Algorithm

```text
1. Validate target active Shot and obtain Project context.

2. Deduplicate supplied dependent Entity IDs while retaining
   exactly one supplied EntityRevision per Entity.

3. Bulk-load active Tracks in requested world for those Entities.

4. Bulk-load active Transitions for those Track IDs.

5. Compute relevant_transition_data.

6. If relevant_transition_data and Shot has no narrative position:
       NARRATIVE_CONTEXT_REQUIRED.

7. For positioned Shot:
       load canonical M7 Project ordering.

8. target_rank = Shot/start rank.

9. Resolve every Transition's anchor through that ordering.

10. Eligible iff:
        transition_rank <= target_rank.

11. Per Track, choose exactly one highest-ranked eligible Transition.

12. Winning set:
        effective transform.

13. Winning clear:
        canonical absence.

14. No winner:
        canonical absence.

15. Required applicable Track + absence:
        SPATIAL_TRACK_STATE_REQUIRED.

16. Optional applicable Track + absence:
        valid absence.

17. Attach exact supplied EntityRevision.

18. Sort:
        (entity_id, spatial_track_id).

19. Build canonical capture-ready staging projection.
```

## 8.6 No replay

Forbidden:

```text
for previous Shot:
    resolve state
    carry result forward
```

The result is derived directly from explicit transitions and canonical narrative ranks.

## 8.7 Corrupt winner

If impossible stored state yields more than one winning transition at the same semantic rank:

```text
INTERNAL_INVARIANT_VIOLATION
```

Never resolve via:

```text
transition ID
UUID
created_at
updated_at
database row order
```

---

# 9. M10C-4 — Temporal correctness and races

## 9.1 Boundary semantics

Required:

```text
target Shot/start
→ included

target Shot/end
→ excluded from target Shot

previous Shot/end
→ included downstream

Sequence/start
→ precedes descendants

Scene/start
→ precedes first child Shot/start

last child Shot/end
→ precedes Scene/end

winning clear
→ absent

later set
→ restored
```

No anchor-specific precedence heuristic exists beyond canonical narrative rank.

## 9.2 Readiness

For applicable Tracks:

```text
required + no effective set
→ SPATIAL_TRACK_STATE_REQUIRED

optional + no effective set
→ valid absence
```

## 9.3 Required frozen races

### Transition change — AFTER

```text
transition change commits
↓
preview read begins
↓
complete AFTER state
```

### Transition change — BEFORE

```text
preview read snapshot established
↓
transition change commits
↓
complete BEFORE state
```

### Requirement flip — AFTER

```text
requirement flip commits
↓
preview read begins
↓
complete AFTER state
```

### Requirement flip — BEFORE

```text
preview read snapshot established
↓
requirement flip commits
↓
complete BEFORE state
```

## 9.4 M10C-added narrative reorder race

Narrative topology is also a staging dependency.

Prove:

```text
complete old ordering + compatible staging
OR
complete new ordering + compatible staging
```

never hybrid topology.

This is an M10C source-gate addition beyond the frozen race minimum.

## 9.5 Local EntityRevision coherence proof

M10D owns the full frozen:

```text
dependent EntityRevision change
vs
complete spatial resolution/capture
```

race.

M10C nevertheless must mechanically prove its local preview composition, not merely inspect code.

### Required proof

Use a real concurrent EntityRevision/approval mutation and a barrier at the actual preview read seam.

#### BEFORE

```text
preview establishes coherent read snapshot
↓
barrier releases competing EntityRevision mutation
↓
competitor commits new exact revision
↓
preview continues dependency/revision + staging reads
↓
preview must contain the complete old semantic EntityRevision
and staging projection from that same read snapshot
```

#### AFTER

```text
competing EntityRevision mutation commits
↓
preview establishes coherent read snapshot
↓
preview must contain the complete new EntityRevision
and staging projection
```

The proof must execute the real public preview composition and the real revision mutation path.

It must not satisfy this gate through:

* source inspection only;
* manually supplied fake revision IDs;
* mocked staging outcomes;
* sequential operations named “race.”

This is the M10C precursor to M10D's complete frozen class-6 race, not a substitute for it.

---

# 10. M10C-5 — Authoring and inspection

## 10.1 Track authoring

SpatialWorld workspace exposes:

```text
Entity
Track
Requirement
```

Actions:

```text
Create Track
Change requirement
Delete Track
```

## 10.2 Transition authoring

Per Track expose:

```text
anchor type
anchor
boundary
operation
translation
rotation
```

Authoring must support all six anchor-boundary classes:

```text
Sequence/start
Sequence/end
Scene/start
Scene/end
Shot/start
Shot/end
```

and both:

```text
set
clear
```

Frontend never computes narrative ranks.

## 10.3 Staging-preview coherent read

The public preview endpoint owns the complete coherent read:

```text
one AsyncConnection
one explicit coherent read
↓
verify active target Shot
↓
load semantic dependencies
↓
resolve exact current EntityRevision for each dependency
↓
call resolve_effective_staging on same connection
↓
build response
```

Forbidden:

```text
session A: semantic state
close
session B: staging
```

A semantic dependency lacking a valid exact current EntityRevision inherits the semantic layer's existing fail-closed behavior.

## 10.4 Inspection output

Show:

```text
Entity
exact EntityRevision
Track identity
required / optional
effective transform
winning SpatialTransition
source anchor type/id/boundary
```

Honest states:

```text
required state missing
optional state absent
no applicable Tracks
narrative context required
```

Label as:

```text
Current effective staging
```

not:

```text
Captured staging
Historical spatial authority
ShotRevision spatial state
```

## 10.5 Endpoint boundary

Prefer extending the existing SpatialWorld workspace when clean.

A dedicated endpoint may be used if necessary, for example:

```text
GET /spatial-worlds/{world_id}/staging?shot_id={shot_id}
```

It is strictly a current-state authoring/inspection projection.

M10C does not claim completion of the final:

```text
GET /shots/{shot_id}/spatial-continuity
```

contract.

---

# 11. API transport discipline

Every new M10C request model uses:

```python
model_config = ConfigDict(extra="forbid")
```

No request-bearing M10C route accepts undeclared fields.

This applies at minimum to request schemas for:

```text
POST   /spatial-worlds/{world_id}/tracks
PATCH  /spatial-tracks/{track_id}

POST   /spatial-tracks/{track_id}/transitions
PATCH  /spatial-transitions/{transition_id}
```

and any explicit DELETE request body if the final transport shape requires one.

The frontend must not rely on backend ignoring unknown fields.

## 11.1 Error vocabulary

M10C uses the frozen SoloRing/M10 error vocabulary.

It must not introduce aliases such as:

```text
SPATIAL_STAGING_MISSING
TRACK_NOT_READY
MOVABLE_ENTITY_REQUIRED
SPATIAL_POSITION_REQUIRED
```

when the frozen condition is already represented by:

```text
SPATIAL_TRACK_INVALID
SPATIAL_ENTITY_INSTANCING_UNSUPPORTED
SPATIAL_TRANSITION_INVALID
SPATIAL_TRACK_STATE_REQUIRED
NARRATIVE_CONTEXT_REQUIRED
INTERNAL_INVARIANT_VIOLATION
```

One production condition has one canonical error identity.

---

# 12. Fail-closed current-state defense

Direct-DB corruption tests cover at least:

```text
invalid transition operation
set with partial transform
clear with transform
invalid anchor type
invalid boundary
anchor absent from canonical topology
duplicate semantic coordinate with DB protections bypassed
invalid Track requirement
wrong-Project Track/Entity relationship
malformed ShotSpatialPlan inspected by delete guard
```

Impossible persisted state fails:

```text
INTERNAL_INVARIANT_VIOLATION
```

Never:

```text
ignore
choose one
treat optional
repair
assume no reference
```

---

# 13. Byte determinism gate

Fixture:

```text
same Shot
same exact EntityRevision inputs
same world
same active Tracks
same active Transitions
same narrative topology
↓
shuffle Track result order
shuffle Transition result order
↓
resolve twice
↓
canonical staging bytes
```

Assert:

```text
bytes_A == bytes_B
```

Also assert identical:

```text
canonical state order
EntityRevision IDs
winning Transition IDs
source anchor provenance
```

The test name must state byte identity if byte identity is what it proves.

---

# 14. Feature-film-scale gate

## 14.1 Rule

Feature-film scale increases:

```text
rows
bytes
objects
```

not per-item SQL round trips.

APR-044 governs this gate. 

No arbitrary latency ceiling is invented.

## 14.2 Small fixture

Include:

```text
several Shots
required + optional Tracks
Sequence transition
Scene transition
Shot/start transition
Shot/end transition
clear
later set
unrelated noise
```

## 14.3 Representative fixture

Approximately:

```text
2,500 Shots
multiple Sequences
multiple Scenes
recurring Characters
recurring Props
recurring Vehicles
SpatialWorld reused across many Shots
multiple applicable Tracks
required/optional Tracks
all anchor types
start/end boundaries
clear/re-entry
requirement variations
unrelated worlds/entities/transitions
```

## 14.4 Endpoint-level measurement

The query spy measures the complete public staging-preview path:

```text
Shot verification
semantic dependency loading
exact EntityRevision resolution
Track loading
Transition loading
canonical narrative ordering
response/projection work
```

The fixed SQL statement classes used by the canonical narrative-order loader are included.

Pass:

```text
small fixture statement classes/count
==
representative fixture statement classes/count
```

for the same semantic branch shape.

Rows returned may scale.

Forbidden:

```text
query per prior Shot
query per Track
query per Transition
query per EntityRevision
query per anchor
```

## 14.5 Record

Capture:

```text
Shot count
Sequence count
Scene count
dependent Entity count
Track count
Transition count
SQL statement classes/count
rows returned
canonical staging byte length
wall-clock observation
```

Wall-clock is evidence only.

---

# 15. Acceptance matrix

### Track authority

1. Valid Track creation.
2. Cross-Project Entity rejected.
3. Deleted SpatialWorld rejected.
4. Deleted Entity rejected.
5. Invalid requirement rejected.
6. Duplicate active Track translated.
7. Concurrent duplicate Track creation produces exactly one active winner.
8. Track identity cannot be retargeted.
9. Required Track cannot be deleted.
10. Optional Track with active Transition cannot be deleted.
11. Optional Track referenced by a plan blocking entry cannot be deleted.
12. Malformed plan encountered by delete guard fails invariant.
13. Legal optional unreferenced Track can be deleted.

### Transition authority

14. Sequence/start set.
15. Sequence/end set.
16. Scene/start set.
17. Scene/end set.
18. Shot/start set.
19. Shot/end set.
20. Clear on every legal anchor class.
21. Cross-Project anchor rejected.
22. Deleted/missing anchor rejected.
23. Active coordinate conflict rejected.
24. Incomplete set rejected.
25. Clear with transform rejected.
26. Set→clear.
27. Clear→set.
28. Omitted PATCH retains value.
29. Explicit-null semantics remain unambiguous.
30. Delete/recreate produces new identity.

### Resolver

31. Target Shot/start included.
32. Target Shot/end excluded.
33. Prior Shot/end included downstream.
34. Scene/start precedes first Shot/start.
35. Winning clear gives absence.
36. Later set restores placement.
37. Required absence blocks.
38. Optional absence succeeds.
39. Unrelated Entity excluded.
40. Other-world Track excluded.
41. Exact semantic EntityRevision emitted.
42. Unassigned + relevant temporal data → `NARRATIVE_CONTEXT_REQUIRED`.
43. Unassigned + no relevant temporal data does not invent blocker.
44. Corrupt ambiguous winner fails invariant.
45. No operational prior-Shot replay.

### Determinism and concurrency

46. Shuffled Track/Transition order → byte-identical staging.
47. Transition race BEFORE.
48. Transition race AFTER.
49. Requirement race BEFORE.
50. Requirement race AFTER.
51. Narrative reorder race BEFORE.
52. Narrative reorder race AFTER.
53. **Real EntityRevision mutation during live preview read proves coherent BEFORE/AFTER snapshot behavior with real barriers.**

Item 53 may not be closed by source inspection alone.

### Critical production proof

54. Shot 20/end places Eva near front desk.
55. Shot 21 resolves that exact placement directly.
56. Shot 20 is never resolved/replayed as a prerequisite.
57. Changing Shot 20 rendered Take does not alter Shot 21 staging.
58. UI playback/blocking changes alone do not alter persistent staging.

### UI/transport

59. Track creation performs real-shaped request.
60. Requirement PATCH performs real-shaped request.
61. Transition set/clear performs real-shaped request.
62. Extra request fields are rejected.
63. Preview displays exact EntityRevision.
64. Preview displays winning-transition provenance.
65. Required/optional absence are distinct.
66. Current staging is never presented as captured history.

### Scale

67. Small endpoint SQL shape recorded.
68. ~2,500-Shot endpoint SQL shape recorded.
69. Statement classes/count match.
70. Rows scale without per-item query fan-out.

APR-072 applies to every proof: test names and reports must state exactly what the mechanics establish. 

---

# 16. Implementation sequence

## M10C-1 — SpatialTrack lifecycle

Deliver:

```text
Track service/API
same-Project validation
active uniqueness
requirement mutation
delete guards
minimal read-only plan-reference reader
focused tests/races
```

**Gate:** Track authority complete.

## M10C-2 — SpatialTransition lifecycle

Deliver:

```text
Transition service/API
anchor validation
set/clear semantics
numeric validation
prospective PATCH
soft delete/recreate
transport strictness
```

**Gate:** Temporal mutations complete.

## M10C-3 — Effective staging resolver

Deliver:

```text
EffectiveSpatialTrackState
StagingResolutionOutcome
set-oriented resolution
exact EntityRevision input
required/optional semantics
canonical staging projection
canonical byte serialization
```

**Gate:** Arbitrary target Shot resolves directly and deterministically.

## M10C-4 — Temporal correctness and races

Deliver:

```text
boundary matrix
clear/re-entry
unassigned semantics
corruption defenses
Transition races
requirement races
narrative-reorder races
mechanical EntityRevision preview-coherence race
moving-character proof
```

**Gate:** Temporal correctness mechanically proven.

## M10C-5 — Authoring and inspection

Deliver:

```text
Track editor
Transition editor
coherent staging-preview composition
target-Shot inspector
source provenance
honest readiness/absence states
```

**Gate:** Production can author and inspect temporal staging without client authority logic.

## M10C-6 — Scale and closure

Deliver:

```text
small endpoint fixture
~2,500-Shot endpoint fixture
SQL spy
byte-order determinism
focused M10C suite
full predecessor suites
frontend suite
typecheck
production build
compileall
exact source/delta gate
```

**Gate:** Definition of Done satisfied.

---

# 17. Definition of Done

M10C closes only when:

* [ ] SpatialTrack ownership is Project-consistent.
* [ ] Active `(world,Entity)` uniqueness is race-safe.
* [ ] Duplicate Track errors use the frozen error identity.
* [ ] Track identity cannot be retargeted.
* [ ] Requirement mutation is explicit and fenced.
* [ ] Required deletion requires explicit downgrade.
* [ ] Active Transitions block Track deletion.
* [ ] Current plan blocking references block Track deletion.
* [ ] M10C has only a minimal read-only plan-reference reader.
* [ ] That reader cannot become ShotSpatialPlan authority.
* [ ] Ambiguous/malformed plan documents fail the delete guard closed.
* [ ] No origin/default transition is synthesized.
* [ ] Transition anchors reuse canonical M7 narrative ordering.
* [ ] `set` has exactly six transform values.
* [ ] `clear` has none.
* [ ] Existing M10 integer/rotation normalization is reused.
* [ ] PATCH validates one prospective aggregate.
* [ ] Transition coordinate conflicts are deterministic.
* [ ] Tombstone/recreate uses a new transition identity.
* [ ] Every M10C request schema rejects undeclared fields with `extra="forbid"`.
* [ ] No M10C-specific alias is introduced for an existing frozen error condition.
* [ ] Exactly one M10C staging subresolver exists.
* [ ] It runs on the caller's coherent connection.
* [ ] It consumes exact semantic EntityRevision inputs.
* [ ] `relevant_transition_data` follows the exact definition in this contract.
* [ ] It never replays prior Shots.
* [ ] Shot/start is inclusive.
* [ ] Target Shot/end is excluded.
* [ ] Prior Shot/end applies downstream.
* [ ] Clear means canonical absence.
* [ ] Required absence produces `SPATIAL_TRACK_STATE_REQUIRED`.
* [ ] Optional absence is valid.
* [ ] Exact EntityRevision and Transition provenance are retained.
* [ ] Effective states sort by `(entity_id, spatial_track_id)`.
* [ ] Capture-ready canonical staging bytes are defined.
* [ ] Shuffled source order gives byte-identical staging.
* [ ] No UUID/timestamp/database-order tiebreak exists.
* [ ] Preview semantic dependency, EntityRevision, and staging reads are one coherent read.
* [ ] EntityRevision preview coherence is proven with a real concurrent mutation and real barrier, not inspection alone.
* [ ] Transition races prove complete BEFORE/AFTER.
* [ ] Requirement races prove complete BEFORE/AFTER.
* [ ] Narrative reorder races prove complete BEFORE/AFTER.
* [ ] Narrative reorder race is recorded as an M10C-added proof.
* [ ] Full EntityRevision-vs-complete-spatial-resolution/capture remains M10D scope.
* [ ] Frozen §18 fixed-frame/Track conflict remains M10D scope.
* [ ] Shot 21 inherits explicit Shot 20/end placement without replay.
* [ ] Rendered output/UI motion cannot change persistent staging.
* [ ] UI authoring remains server-authoritative.
* [ ] UI does not compute winner/rank logic.
* [ ] UI distinguishes current staging from historical capture.
* [ ] Endpoint-level ~2,500-Shot query shape equals the small fixture's statement shape/count.
* [ ] Scale increases rows rather than per-item round trips.
* [ ] No migration is added.
* [ ] No ShotSpatialPlan authoring enters M10C.
* [ ] No schema-5 capture enters M10C.
* [ ] No realization/Generation/worker scope enters M10C.
* [ ] Full predecessor backend suite remains green.
* [ ] Frontend tests/typecheck/build remain green.
* [ ] `compileall` remains green.
* [ ] Supplied evidence and independently reproduced evidence remain distinct.

---

# 18. M10D handoff

M10C leaves:

```text
M7 exact semantic EntityRevisions
        +
M10C SpatialTracks
        +
explicit SpatialTransitions
        ↓
random-access effective staging
        ↓
canonical capture-ready staging bytes
```

M10D then composes:

```text
applicable SpatialWorld
        +
approved SpatialWorldRevision
        +
M10C staging
        ↓
fixed-frame / Track conflict
        +
fixed-frame EntityRevision consistency
        +
ShotSpatialPlan
        +
camera / blocking / axis constraints
        ↓
ONE complete current spatial resolver
        ↓
SpatialContinuityPack
        ↓
spatial readiness/hash
        ↓
ShotRevision schema 5
```

The authority boundary remains exact:

> **M10C defines persistent movable-Entity temporal placement. M10D is the first phase permitted to combine that placement with approved world geometry and Shot-local cinematic authority into a complete capturable M10 Shot state.**

```text
M10A    CLOSED
M10B    CLOSED

M10C    IMPLEMENTATION — AUTHORIZED 2026-08-25

M10D    NOT AUTHORIZED
M10E    NOT AUTHORIZED
```

The final pre-authorization contract now includes all three residual corrections from the last source review: strict `extra="forbid"` request schemas plus frozen error vocabulary, an explicitly owned minimal read-only ShotSpatialPlan reference reader for the Track delete guard, and a mechanically forced live EntityRevision-vs-preview coherence proof rather than an inspection-only claim.
