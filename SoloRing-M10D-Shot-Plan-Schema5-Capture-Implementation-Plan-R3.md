# SoloRing M10D — Shot Plan, Complete Spatial Resolution, and Schema-5 Capture Implementation Plan

**Status:** Revision 3 — authorized implementation contract — **implementation authorized 2026-08-25**; publication/tagging NOT authorized
**Milestone:** M10D — Shot Plan + Schema-5 Capture
**Preconditions:** M10A CLOSED; M10B CLOSED; M10C CLOSED
**Predecessor source:** `M10C @ 318ff5c12f4cea870d132bc3f9a8ba3944f866d7`
**Predecessor tree:** `d396b78a0212bc6b673c1a4a4de8237a3b4d45a7`
**Frozen architecture:** SoloRing M10 r3 remains authoritative.
**Successor boundary:** M10E owns spatial realization, D0 materialization, workflow-spec schema 3, worker translation, and M10 Exact Rerun integration.
**Authorization boundary:** This document authorizes no implementation, push, PR, merge, tag, release, branch-protection change, M10E work, or publication.

The current repository branch is mechanically pinned to the M10C closing commit above.  Frozen r3 assigns M10D exactly the ShotSpatialPlan, ONE complete resolver, current spatial API/hash, schema-5 capture, historical provenance, Shot UI, and coherent-read race work described here. 

---

## Authorization record (2026-08-25)

R3 accepted as the implementation target. Review requirements adopted as binding implementation guidance, not plan revisions:

* **W1 — inherited ShotRevision batching (REVIEW FOCUS):** permitted only as a call-shape optimization; schemas 1-4 parent bytes, immutable child contents, positions, convergence behavior, and reuse-integrity semantics must remain unchanged. Matrix 143/144 are the controlling proof.
* **W2 — ShotRead composition (REVIEW FOCUS):** every ShotRead producer routes through the existing composed read convention established by M8; create/list/patch responses must not silently fall back to defaulted spatial fields.
* **W3 — parser exception compatibility (PINNED):** plan-specific exception derived from the existing SchemaInvalid family, carrying SPATIAL_SHOT_PLAN_INVALID.
* **Precision notes (BINDING):** the normalization repair is ShotSpatialPlan-only — M10C staging transforms are already normalized production authority and must not be reinterpreted by the pack parser. Current-duration revalidation operates idempotently over already-canonical stored plan bytes; duration mutation changes readiness, never the stored plan hash.

No R4 requirement.

---

# 0. R3 pre-authorization resolution record

R3 closes the remaining R2 source-fit contradictions without reopening frozen M10 r3 scope. It is a standalone implementation contract, not an addendum: where R2 and R3 differ, R3 is the only pre-authorization target.

The repository ground truth at the pinned predecessor is authoritative where prose review and prior plan wording disagreed:

```text
M10C predecessor commit:
318ff5c12f4cea870d132bc3f9a8ba3944f866d7

M10 authority migration:
server/alembic/versions/0010_m10_spatial_cinematic_continuity.py
blob SHA:
28fa5eb14fe48edb8c00c9cab7d414b91ce10ca1

existing canonical M10 document grammar:
server/soloring/spatial/schemas.py
blob SHA:
37dfde1da5568acf8570daf96be6528f0aaaa2e1

existing ShotRevision capture writer:
server/soloring/domain/revisions.py
blob SHA:
576f27a9912e2f1940e1c7b499b60d85ee2e2761

existing M8 historical child writer:
server/soloring/visual/capture.py
blob SHA:
b54155acd29ccf81120987435805b29b3d11e5ac

existing historical ShotRevision continuity API:
server/soloring/api/continuity.py
blob SHA:
c2270aa737f162072c04aa9b8d6bf90b961a4312

current Generation creation seam:
server/soloring/generation/service.py
blob SHA:
6bf8515b803bdef506e23cfbcf78d8c26631f4b8
```

Mechanically confirmed source-fit facts:

* `shot_revision_spatial_worlds` **does contain** `requirement`; R3 retains it.
* `shot_revision_spatial_track_states` **does contain** `requirement` and `position`; R3 retains them.
* `shot_revision_spatial_track_states` has **no `is_staged` column**; R3 does not invent one. Every row in this table is already an effective staged Track projection.
* M10D adds no migration and may not change those physical shapes.
* the frozen error vocabulary already contains `SPATIAL_SHOT_PLAN_INVALID`, `SPATIAL_SHOT_PLAN_CONFLICT`, and `SPATIAL_REALIZATION_UNSUPPORTED`; R3 adds no durable error identity.
* `server/soloring/spatial/schemas.py` already owns the pure frozen-r3 grammars for `SpatialWorldRevision`, `ShotSpatialPlan`, and `SpatialContinuityPack`; M10D evolves this authority **in place** and may not introduce a second full ShotSpatialPlan grammar.
* closed M10A source and fixtures establish the schema-1 wire representation for an absent axis constraint as an **explicit present key with `null` value**. R3 preserves those canonical bytes: omitted `axis_constraint` is invalid; `"axis_constraint": null` is the canonical absence form.
* the existing ShotSpatialPlan parser validates normalized rotation legality but does not yet guarantee that normalized transforms replace the caller's raw values in the returned canonical document. M10D must repair that in the existing parser so equivalent wrapped rotations converge byte-for-byte.
* the existing shared `SchemaInvalid` path reports `SPATIAL_WORLD_INVALID` even for ShotSpatialPlan grammar failures. M10D must specialize plan parse failures to `SPATIAL_SHOT_PLAN_INVALID` **without** creating a parallel grammar and while retaining `SchemaInvalid`-family catch compatibility for predecessor tests.
* the current historical authority surface is `GET /shot-revisions/{revision_id}/continuity`; M10D extends that response with captured spatial provenance rather than creating a competing historical endpoint.
* the existing ShotRevision writer persists predecessor dependency, Feature-state, Relation-state, and M8 visual child collections with cardinality-sensitive per-row `execute()` loops. Because R3 retains a whole-capture APR-044 statement-count gate, M10D explicitly includes a semantics-preserving batching refactor for those inherited ShotRevision child writers as well as the new M10 children.
* the current Generation creation seam is `server/soloring/generation/service.py::create_generation_request`; R3 pins the temporary pre-M10E schema-5 fence immediately after coherent ShotRevision capture/reuse and before package **semantic validation**, Generation input mapping, workflow-spec assembly, or Generation persistence. Existing Stage-0 raw Comfy release-byte capture/storage may already have occurred and is not reclassified as semantic package acceptance.
* M10B working-state storage already has a uniqueness fence for one bound Entity per `SpatialWorldState`; M10D still independently verifies immutable approved revision projections and detects fixed/Track conflicts during complete Shot resolution.

R3 additionally retains and freezes the valid R2 hardening:

1. current-duration revalidation of stored camera/blocking keyframes;
2. exact active target-Shot/end lookup semantics;
3. approved-axis corruption handling;
4. prerequisite-aware issue accumulation;
5. mandatory historical immutable-world cross-checks;
6. an unconditional pre-M10E schema-5 Generation fence;
7. full capture races for duration mutation, semantic dependency-set mutation, and narrative reorder;
8. captured requirement corruption/policy-history proofs;
9. exact physical M10 ShotRevision child projections from migration `0010`.

No vertical screen-direction vocabulary, cache, denormalized Shot hash, convenience diff/preview API, new index, new migration, realization compiler, D0 materialization, or M10E execution logic is added by R3.
---

# 1. Objective

M10D closes the **production-authority side of spatial continuity at Shot scope**.

M10A established the domain/storage/runtime foundation. M10B established reusable approved SpatialWorld authority. M10C established random-access temporal placement for movable Entities.

M10D composes those authorities into one complete capturable value:

```text
M7 exact semantic EntityRevisions
        +
M10B approved reusable SpatialWorldRevision
        +
M10C effective temporal staging
        +
ShotSpatialPlan
    camera
    blocking
    axis constraint
    screen-direction intent
        ↓
ONE complete current spatial resolver
        ↓
SpatialContinuityPack
        ↓
spatial readiness + spatial hash
        ↓
working Shot snapshot hash
        ↓
ShotRevision schema 5
        ↓
immutable historical spatial provenance
```

The defining question is:

> **For this exact Shot, under the exact current semantic EntityRevisions, which approved physical world is authoritative, where are persistent movable Entities at Shot/start, what Shot-local camera/blocking/axis constraints apply, and what exact immutable spatial authority must be captured?**

M10D is the first phase permitted to answer that question as one canonical value.

---

# 2. Governing authority boundary

The authority direction remains:

```text
semantic production truth
        ↓
approved reusable spatial authority
        +
explicit persistent temporal staging
        +
explicit Shot-local cinematic authority
        ↓
immutable captured ShotRevision
        ↓
M10E execution-specific spatial realization
        ↓
executor
```

Never:

```text
rendered frame
depth image
camera solve
tracking output
Comfy graph
ControlNet response
UI playback
model interpretation
current package
        ↓
changes M10 production authority automatically
```

A rendered Shot may reveal that authored spatial authority is poor. It may motivate an explicit production edit. It never becomes the edit.

The frozen M10 hierarchy explicitly separates SpatialContinuityPack authority from downstream realization. 

---

# 3. M10D scope

## 3.1 Included

M10D implements:

1. In-place evolution and reuse of the existing authoritative ShotSpatialPlan schema-1 parser/canonicalizer in `server/soloring/spatial/schemas.py`.
2. ShotSpatialPlan create/update/delete CAS lifecycle.
3. Strict recursive request schemas.
4. Exact camera optics and pose validation.
5. Sparse camera-keyframe authority.
6. Sparse blocking-keyframe authority.
7. Active Track/world/dependency binding validation.
8. Shot/start blocking agreement.
9. Explicit Shot/end handoff agreement.
10. Arbitrary-precision axis-side enforcement.
11. Screen-direction production-intent capture.
12. Applicable SpatialWorld selection.
13. Exact Location EntityRevision → SpatialWorldState resolution.
14. Approved immutable SpatialWorldRevision verification.
15. Fixed-frame/fixed-frame and fixed-frame/Track placement conflict detection.
16. Fixed-frame EntityRevision consistency.
17. Reuse of M10C random-access staging.
18. ONE complete current spatial resolver.
19. Canonical SpatialContinuityPack schema 1.
20. `spatial_continuity_hash`.
21. Current `GET /shots/{id}/spatial-continuity`.
22. Computed ShotRead spatial fields.
23. Working Shot snapshot hash integration.
24. ShotRevision schema-5 selection.
25. Immutable M10 ShotRevision child persistence.
26. Reuse-integrity validation.
27. Captured-row-only historical spatial inspection.
28. Current-vs-captured Shot spatial UI.
29. Full schema-1..5 compatibility cube.
30. Real coherent-read capture races.
31. Corruption/fail/restore loops.
32. Byte-level determinism gates.
33. Current-resolution and schema-5-capture scale gates.
34. Full predecessor regression preservation.

This matches the frozen §80 phase contract. 

## 3.2 Explicitly excluded

M10D does **not** implement:

* RealizationProfile schema 2 spatial capability.
* workflow manifest/package schema 3 spatial bindings.
* workflow-spec schema 3.
* the pure M10 spatial realization compiler.
* D0 box-depth materialization.
* derived spatial Blob creation.
* `derived_spatial_artifacts`.
* `generation_derived_spatial_inputs`.
* spatial worker translation.
* M10 Exact Rerun realization.
* package capacity handling.
* runtime-fingerprint selection at Generation execution.
* Comfy structured/derived spatial binding.
* GPU source-fit.
* rich 3D/DCC editing.
* mesh/NeRF/splat authority.
* interpolation authority between sparse keyframes.
* per-frame spatial database state.
* entity instancing.
* multiple simultaneous selected SpatialWorlds.
* automatic Location/world carry-forward.
* automatic initial Track placement.
* automatic camera solve adoption.
* new database migration.
* M10 publication/tagging.

Those execution concerns belong to M10E; M10F owns final adversarial whole-milestone closure. 

---

# 4. Source-fit baseline

M10D must extend existing authority seams rather than create parallel systems.

## 4.1 M10C staging stays the temporal authority

Current M10C already provides:

```python
resolve_effective_staging(
    conn,
    *,
    shot_id,
    spatial_world_id,
    resolved_entity_revisions,
)
```

It:

* uses a caller-owned coherent connection;
* resolves directly at target Shot/start;
* never replays earlier Shots;
* retains exact EntityRevision;
* retains winning SpatialTransition provenance;
* sorts states by `(entity_id, spatial_track_id)`;
* raises `NARRATIVE_CONTEXT_REQUIRED` correctly;
* produces canonical staging bytes.

M10D **must call this authority**. It must not reproduce M10C winner logic inside `resolver.py`.

The predecessor handoff explicitly reserves approved-world composition and the complete resolver for M10D. 

## 4.2 Existing capture path is extended, not forked

The existing ShotRevision architecture already has the required house pattern:

```text
one coherent current read
↓
one frozen in-memory capture value
↓
BEGIN IMMEDIATE write phase
↓
converge by snapshot hash
↓
append immutable child rows
↓
validate exact reuse integrity
```

M10D extends the existing single snapshot builder and revision capture seam with `spatial_pack`.

There must not be:

```text
build_m10_snapshot()
build_spatial_revision_separately()
capture_spatial_after_shot_revision()
```

as competing capture authorities.

## 4.3 Historical API precedent

The existing continuity historical reader reconstructs authority from immutable captured rows and fails invariant on malformed historical representations rather than consulting current working state.

M10D follows exactly that model.

## 4.4 Error vocabulary already exists

All frozen M10D error identities already live in `ErrorCode`; M10D therefore adds **no error-code aliases**.

## 4.5 Canonical M10 document grammar is pre-existing authority

The predecessor already has one pure byte-bearing M10 grammar module:

```text
server/soloring/spatial/schemas.py
```

It owns:

```text
parse_world_revision / world_revision_hash
parse_shot_plan / plan_hash
parse_continuity_pack / pack_hash
canonical_json_bytes
```

M10D must extend this module **in place** where schema-1 ShotSpatialPlan canonicalization/error identity is incomplete. `spatial/plans.py` owns persistence, Shot/Project/dependency validation, CAS, and current-context validation; it does not become a second document grammar.

The M10C `plan_reference.py` reader remains deliberately narrower than both and is unchanged in authority.

## 4.6 Existing historical API is extended, not forked

Historical ShotRevision authority already has one public surface:

```text
GET /shot-revisions/{revision_id}/continuity
```

M10D extends its server-owned projection with captured spatial authority. No sibling `/shot-revisions/{revision_id}/spatial-continuity` endpoint is introduced by M10D.

## 4.7 Database

M10A already created the authority and schema-5 projection tables required by M10D.

Therefore:

> **M10D adds no Alembic migration.**

R3 source-fit against the pinned predecessor mechanically confirms the existing `0010_m10_spatial_cinematic_continuity.py` projection shapes M10D must write:

```text
shot_revision_spatial_worlds
    shot_revision_id
    spatial_continuity_hash
    spatial_world_id
    spatial_world_state_id
    spatial_world_revision_id
    spatial_world_revision_hash
    location_entity_id
    location_entity_revision_id
    requirement

shot_revision_spatial_track_states
    shot_revision_id
    position
    spatial_track_id
    entity_id
    entity_revision_id
    requirement
    x_mm, y_mm, z_mm
    yaw_udeg, pitch_udeg, roll_udeg
    source_transition_id
    source_anchor_type
    source_anchor_id
    source_boundary

shot_revision_spatial_plans
    shot_revision_id
    plan_hash
    plan_json
```

There is no `is_staged` column. `position` is already part of the frozen Track child key/projection. Every Track child row is staged by table meaning.

Any implementation attempt that discovers a supposedly necessary new authority table or column is a source-gate stop requiring contract review, not permission to improvise schema.

---

# 5. Canonical sub-milestones

Use these names consistently in commits, tests, reports, and closure records:

```text
M10D-1 — ShotSpatialPlan authority and CAS

M10D-2 — Approved-world composition and ONE complete resolver

M10D-3 — Camera, blocking, axis, and SpatialContinuityPack

M10D-4 — Current API, working hash, and Shot spatial UI

M10D-5 — ShotRevision schema-5 capture and historical provenance

M10D-6 — Coherence races, corruption, determinism, scale, and closure
```

No second numbering system is introduced.

---

# 6. M10D-1 — ShotSpatialPlan authority and CAS

## 6.1 Home

Canonical document grammar — existing authority, evolved in place:

```text
server/soloring/spatial/schemas.py
```

Plan persistence/CAS/ownership service:

```text
server/soloring/spatial/plans.py
```

Transport:

```text
server/soloring/api/spatial_plans.py
```

Register through the existing FastAPI router composition.

The M10C module:

```text
server/soloring/spatial/plan_reference.py
```

remains a **minimal deletion-reference reader**.

`plan_reference.py` must not be silently widened into full M10D plan authority. `plans.py` must not implement a second pure schema grammar. Track deletion continues using the narrow reference reader so an unrelated camera/optics defect cannot change reference-detection semantics.

---

# 7. ShotSpatialPlan schema 1

Canonical semantic shape:

```json
{
  "schema_version": 1,
  "spatial_world_id": "...",
  "camera": {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [
      {
        "time_ms": 0,
        "transform": {
          "translation_mm": [0, 1650, 4200],
          "rotation_udeg": [0, 0, 0]
        }
      }
    ]
  },
  "blocking": [
    {
      "spatial_track_id": "...",
      "screen_direction": "left_to_right",
      "keyframes": [
        {
          "time_ms": 0,
          "transform": {
            "translation_mm": [-900, 0, 1800],
            "rotation_udeg": [0, 0, 0]
          }
        }
      ]
    }
  ],
  "axis_constraint": {
    "spatial_axis_id": "...",
    "camera_side": "positive"
  }
}
```

This is the frozen schema.

Canonical absence/collection rules are frozen by the closed M10A schema authority and preserved in R3:

```text
axis_constraint has no authored constraint
→ canonical key is PRESENT
→ "axis_constraint": null

axis_constraint key omitted
→ SPATIAL_SHOT_PLAN_INVALID

blocking has no entries
→ canonical "blocking": []

screen_direction
→ required in every blocking entry
→ "unspecified" is the explicit no-direction-intent value
```

There is no omitted `axis_constraint` form and no omitted `blocking` form in schema 1. Golden fixtures preserve these existing bytes; M10D does not choose a new representation.

---

# 8. Existing pure plan grammar — in-place canonical evolution

M10D does **not** create a second `canonicalize_shot_spatial_plan()` implementation.

The one pure document entrypoint remains:

```python
from soloring.spatial.schemas import parse_shot_plan, plan_hash

canonical_plan = parse_shot_plan(raw, duration_ms=shot_duration_ms)
canonical_hash = plan_hash(canonical_plan)
```

The existing `parse_shot_plan()` must be evolved in place to satisfy all frozen schema-1 identity guarantees:

1. exact closed field sets remain enforced recursively;
2. `axis_constraint` remains a required top-level key whose value may be `None`;
3. blocking entries remain canonically sorted by `spatial_track_id`;
4. every camera/blocking keyframe transform is replaced in the returned document by the normalized `Transform.canonical_value()` produced by the existing M10 math authority;
5. `+180000000` microdegrees therefore canonicalizes to `-180000000` in returned plan bytes/hash, not merely in a discarded validation temporary;
6. the returned plan is the value embedded by `parse_continuity_pack()`; the pack validator must not validate a normalized plan and then retain the caller's unnormalized raw plan;
7. plan parse failures carry the frozen durable code `SPATIAL_SHOT_PLAN_INVALID` with status 422;
8. predecessor world parsing retains its existing world-domain error identity;
9. predecessor tests that intentionally catch `schemas.SchemaInvalid` remain valid through base-class/subclass compatibility or an equivalent source-compatible mechanism.

No new serializer is introduced. Canonical bytes/hash still use `domain.canonical` through the existing M10 schema module.

Pure document parsing has no database access. Shot/Project/dependency ownership checks and CAS remain service-layer responsibilities in `spatial/plans.py`.

## 8.1 Recursive strictness

Every Pydantic request-bearing transport schema, including nested structures, uses:

```python
model_config = ConfigDict(extra="forbid")
```

This applies to:

* PUT wrapper.
* camera object.
* transform.
* camera keyframe.
* blocking entry.
* blocking keyframe.
* axis constraint.
* DELETE CAS body.

Unknown fields are rejected both by transport models and by the pure `spatial/schemas.py` closed-field grammar; the backend never silently ignores future-looking input.

---

# 9. Numeric authority

Reuse existing M10 integer/rotation authority.

Translation:

```text
signed JavaScript-safe integer millimeters
```

Rotation:

```text
signed integer microdegrees
normalize each component independently to:

[-180000000, +180000000)
```

Thus:

```text
+180000000 → -180000000
```

No floats.

No numeric strings.

No equivalent-Euler reduction.

No normalization by client implementation.

The server owns canonical numbers. The canonical parser must **return** normalized transforms; validation that computes normalization and then discards it is insufficient because plan bytes/hash are authority.

---

# 10. Camera authority

## 10.1 Coordinate convention

Schema 1 remains:

```text
right-handed
+X = world right
+Y = world up
+Z = world back / depth-positive
canonical forward = -Z
absolute world-space poses
```

Parent SpatialFrames remain organizational only.

## 10.2 Rotation convention

Camera/object rotation uses the frozen active local→world intrinsic Y-X-Z convention:

```text
R = Ry(yaw) · Rx(pitch) · Rz(roll)
```

Column vectors.

Identity camera looks along local/world `-Z`.

No implementation may substitute a library's default Euler order without proving it is byte-for-byte/mathematically identical.

## 10.3 Projection

Schema 1 supports exactly:

```text
projection = "perspective"
```

Optics are strictly positive JS-safe integer micrometers:

```text
focal_length_um > 0
sensor_width_um > 0
sensor_height_um > 0
```

No free-text `Shot.lens` inference.

No distortion, lens shift, skew, anamorphic parameter, focus distance, aperture, or raster resolution enters M10 authority.

## 10.4 Frozen pinhole reference mapping

The M10 camera contract uses one exact pure reference mapping. For camera local→world rotation `R`, camera world translation `t`, and a world point `P_world`:

```text
P_camera = R^T · (P_world - t)
P_camera = (x, y, z)
```

A point is projectable only when:

```text
z < 0
```

With focal length `f = focal_length_um`, the ideal sensor-plane coordinates relative to the principal point are:

```text
sensor_x_um = f * x / (-z)
sensor_y_um = f * y / (-z)
```

where the `x/z` and `y/z` ratios are unitless even though world/camera translations are authored in millimeters. Principal point is sensor center; skew is zero. `z == 0` and `z > 0` are non-projectable.

Raster coordinates, clipping policy, field-of-view convenience values, and floating execution approximations are derived/non-authoritative and never enter canonical identity. Golden math fixtures use this mapping; M10D must not introduce a second pinhole convention.

---

# 11. Camera keyframes

Rules:

```text
at least one
first time_ms == 0
strictly increasing
no duplicate time_ms
integer time_ms
```

When:

```text
Shot.duration_ms != NULL
```

every keyframe satisfies:

```text
0 <= time_ms <= duration_ms
```

When:

```text
Shot.duration_ms == NULL
```

the only legal camera keyframe is:

```text
time_ms = 0
```

A sparse list means:

> exact authoritative constraints exist at these authored keyframes.

It does **not** mean:

> SoloRing knows the authoritative camera pose at every frame between them.

M10D must not introduce:

```text
interpolation
linear
spline
Bezier
velocity
tangent
easing
frame-N pose
```

into production authority.

Schema 1 proves exact camera authority at authored keyframes only.

## 11.1 Current-duration readiness revalidation

`Shot.duration_ms` is mutable after a plan is authored. Therefore the stored plan's canonical bytes/hash are **not** sufficient to prove current applicability.

The ONE complete current resolver must revalidate the stored canonical plan through the existing `spatial.schemas.parse_shot_plan(..., duration_ms=current_duration)` authority against the exact current `Shot.duration_ms` from the same coherent read. This mechanically revalidates **every camera and blocking keyframe**:

```text
current duration != NULL
→ every keyframe: 0 <= time_ms <= current duration

current duration == NULL
→ every camera/blocking keyframe must be time_ms == 0
```

If a duration mutation makes a previously valid stored plan out of range:

```text
SPATIAL_SHOT_PLAN_INVALID
spatial_continuity_ready = false
working_snapshot_hash = NULL
```

The stored `plan_json` and `plan_hash` do **not** change merely because Shot duration changed. Current readiness changes because the plan is no longer valid in its current Shot context.

This revalidation occurs on current API resolution, working-hash resolution, and ShotRevision capture because all three use the same resolver.

---

# 12. Blocking entries

Each blocking entry references one active SpatialTrack.

Write-time binding validation requires:

```text
Track.deleted_at IS NULL
Track.spatial_world_id == plan.spatial_world_id
Track.entity_id belongs to current Shot dependency set
```

At most one blocking entry may reference a given `spatial_track_id`.

Blocking keyframes obey the same time-domain rules as camera keyframes and must begin at `time_ms=0`.

`screen_direction` is required in every blocking entry. Its vocabulary is exactly:

```text
left_to_right
right_to_left
stationary
unspecified
```

`unspecified` is an explicit authored value, not an omitted/default field.

No synonyms.

No vertical directions.

No pixel-motion derivation.

No axis↔screen-direction inference.

The frozen contract requires blocking Tracks to be active and current dependencies. 

---

# 13. Canonical array ordering

Canonical JSON object keys use SoloRing's existing canonical serializer.

Array semantics require explicit handling.

Freeze:

```text
camera.keyframes:
    input must already be strictly increasing by time_ms;
    canonical order = time_ms ascending

blocking:
    canonical order = spatial_track_id ascending

blocking[].keyframes:
    input must already be strictly increasing by time_ms;
    canonical order = time_ms ascending
```

Therefore two requests that differ only in:

```text
JSON object key order
whitespace
blocking-entry order
```

produce identical canonical plan bytes/hash.

A request whose keyframe time order is malformed is rejected rather than “helpfully” reordered into validity.

This prevents author input formatting from becoming authority while preserving explicit chronological validation.

---

# 14. Plan ownership validation

Plan write service obtains in one fenced write transaction:

```text
active Shot
Shot Project
Shot duration
current exact semantic dependency identities
candidate selected SpatialWorld
blocking Track identities
optional axis identity
```

Write-time checks:

* selected SpatialWorld active;
* world belongs to Shot Project;
* selected world's Location Entity is a current Shot dependency;
* each blocking Track active;
* each Track belongs selected world;
* each Track Entity is current Shot dependency;
* optional axis identity is active and belongs selected world;
* all pure plan/range rules pass.

The service does **not** require the currently selected world to already have:

* a matching SpatialWorldState;
* an approved SpatialWorldRevision;
* current Track readiness;
* blocking t=0 agreement;
* valid current axis membership.

Those mutable readiness facts are evaluated by the complete resolver.

This allows a filmmaker to author a Shot plan before world approval is complete without pretending the Shot is production-ready.

Every write-time mutable ownership condition is nevertheless revalidated at current resolution. Current resolution additionally revalidates all camera/blocking keyframe ranges against the exact current `Shot.duration_ms` under §11.1; a stored plan that became out-of-range is `SPATIAL_SHOT_PLAN_INVALID` without rewriting its stored bytes/hash.

---

# 15. Exact CAS lifecycle

Frozen semantics are literal. 

## 15.1 PUT request

Recommended transport:

```python
class SpatialPlanPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_hash: str | None
    plan: ShotSpatialPlanInput
```

Route:

```text
PUT /shots/{shot_id}/spatial-plan
```

## 15.2 Create

```text
expected_plan_hash = null
current plan absent
→ create
```

If current plan exists:

```text
SPATIAL_SHOT_PLAN_CONFLICT
409
```

## 15.3 Update

```text
expected_plan_hash == exact current plan_hash
→ candidate canonicalized
→ replace atomically
```

Anything else:

```text
SPATIAL_SHOT_PLAN_CONFLICT
409
```

If candidate canonical bytes equal current canonical bytes, the operation may be a true no-op returning the existing hash; it must not manufacture a new authority identity.

## 15.4 DELETE request

Recommended:

```python
class SpatialPlanDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_plan_hash: str | None
```

Route:

```text
DELETE /shots/{shot_id}/spatial-plan
```

Existing plan:

```text
expected exact current hash
→ delete

null/stale/different
→ SPATIAL_SHOT_PLAN_CONFLICT
```

No existing plan:

```text
expected null
→ idempotent 204

expected non-null
→ SPATIAL_SHOT_PLAN_CONFLICT
```

Deleting current plan never modifies:

```text
shot_revisions
shot_revision_spatial_plans
historical packs
Generations
```

## 15.5 Transaction

All plan writes:

```text
BEGIN IMMEDIATE
↓
load current row + current write-time dependencies
↓
validate expected hash
↓
canonicalize/validate candidate if PUT
↓
ownership validation
↓
INSERT/UPDATE/DELETE
↓
COMMIT
```

No read-then-write session split.

---

# 16. M10D-2 — ONE complete current spatial resolver

Primary home:

```text
server/soloring/spatial/resolver.py
```

Recommended interface:

```python
async def resolve_spatial_continuity(
    conn: AsyncConnection,
    *,
    shot_id: str,
    resolved_dependencies: Sequence[ResolvedDependency],
) -> SpatialResolutionOutcome:
    ...
```

`resolved_dependencies` are the exact M7 semantic dependency values already resolved in the same coherent read.

The resolver must **not** ask later:

```text
"What EntityRevision is current now?"
```

It receives the exact answer from upstream.

---

# 17. Resolution outcome

Recommended immutable value:

```python
@dataclass(frozen=True)
class SpatialIssue:
    code: str
    layer: str
    message: str
    details: Mapping[str, object]


@dataclass(frozen=True)
class SpatialResolutionOutcome:
    shot_id: str

    ready: bool
    pack: dict | None
    spatial_continuity_hash: str | None

    issues: tuple[SpatialIssue, ...]

    selected_world: ...
    approved_world_revision: ...
    staging: ...
    plan: ...
    axis_status: ...
```

Corruption is **not** an issue row.

Corruption raises immediately:

```text
INTERNAL_INVARIANT_VIOLATION
```

Issue rows represent legitimate but currently unresolved production state.

A helper may provide strict capture behavior:

```python
def require_spatial_ready(
    outcome: SpatialResolutionOutcome,
) -> None:
    ...
```

It raises the first blocker under frozen precedence while preserving the full issue set in `details`.

---

# 18. Applicable SpatialWorld selection

Implement frozen §22 exactly. 

Using current M7 dependencies:

1. Collect active **required** SpatialWorlds whose Location Entity is a dependency.
2. Read current ShotSpatialPlan.
3. More than one required applicable world:

```text
SPATIAL_CONTEXT_AMBIGUOUS
```

No primary-location heuristic.

4. Exactly one required world:

   * plan must exist;
   * plan must select that world.

No plan:

```text
SPATIAL_SHOT_PLAN_REQUIRED
```

Plan selecting another world:

```text
SPATIAL_SHOT_PLAN_INVALID
```

5. Zero required worlds + current plan:

   * selected world may be optional;
   * its Location must remain a current dependency.

6. Zero required worlds + no current plan:

```text
ready = true
pack = None
spatial_continuity_hash = None
issues = []
```

No optional world is automatically selected.

7. Plan selects a world whose Location ceased to be a dependency:

```text
SPATIAL_SHOT_PLAN_INVALID
```

Never silent ignore.

Multiple optional worlds are legal; one explicit plan selects at most one.

---

# 19. Exact world-state resolution

For the selected world:

```text
exact current Location EntityRevision
        ↓
(world_id, location_entity_revision_id)
        ↓
SpatialWorldState
        ↓
approved_revision_id
        ↓
immutable SpatialWorldRevision
```

## 19.1 Missing state

```text
SPATIAL_WORLD_STATE_REQUIRED
```

## 19.2 State exists but no approval

```text
SPATIAL_WORLD_APPROVAL_REQUIRED
```

The former strictly precedes the latter.

## 19.3 Corruption

Immediate invariant failure for:

* approved pointer targeting wrong state;
* approved revision wrong world;
* stored revision snapshot malformed;
* snapshot hash mismatch;
* revision child frame projection mismatch;
* revision child axis projection mismatch;
* missing/extra child;
* wrong position;
* nested hash inconsistency.

No readiness alias is allowed for corruption.

---

# 20. Verified immutable world reader

Extend:

```text
server/soloring/spatial/revisions.py
```

with one reusable immutable reader, conceptually:

```python
async def load_verified_world_revision(
    conn: AsyncConnection,
    *,
    spatial_world_state_id: str,
    spatial_world_revision_id: str,
) -> VerifiedSpatialWorldRevision:
    ...
```

It must:

1. load immutable revision row;
2. verify exact state ownership;
3. parse `snapshot_json`;
4. canonicalize it;
5. verify `snapshot_hash`;
6. batch-load immutable frame children;
7. batch-load immutable axis children;
8. verify exact child projections and positions;
9. return one immutable verified value.

The complete resolver must not independently implement a second SpatialWorldRevision parser.

---

# 21. Placement authority

After approved-world loading, evaluate frozen §10.3 against the **effective approved revision**, not all world states globally. 

For each bound Entity:

```text
0 or 1 fixed frame placement
```

Multiple fixed-frame placements for the same Entity:

```text
SPATIAL_ENTITY_PLACEMENT_CONFLICT
```

Then reuse M10C staging for current dependent Entities.

If:

```text
fixed frame for Entity E
+
applicable SpatialTrack for Entity E
```

then:

```text
SPATIAL_ENTITY_PLACEMENT_CONFLICT
```

No priority rule.

No “Track wins.”

No “frame wins.”

No latest timestamp.

Placement conflict has precedence over EntityRevision mismatch for the same effective Entity.

---

# 22. Fixed bound EntityRevision consistency

For each approved fixed frame with:

```text
bound_entity_id = E
bound_entity_revision_id = R
```

if `E` is a current Shot semantic dependency:

```text
R == exact M7 resolved EntityRevision
```

otherwise:

```text
SPATIAL_ENTITY_REVISION_MISMATCH
```

If `E` is not a Shot dependency, its captured bound revision remains legitimate world-internal provenance.

M10D must not:

* inject it into Shot dependencies;
* change it to today's approved revision;
* omit it from the world snapshot.

---

# 23. M10C staging reuse

Build:

```python
resolved_entity_revisions = {
    dep.entity_id: dep.entity_revision_id
    for dep in resolved_dependencies
}
```

Then:

```python
staging = await resolve_effective_staging(
    conn,
    shot_id=shot_id,
    spatial_world_id=selected_world.id,
    resolved_entity_revisions=resolved_entity_revisions,
)
```

M10D reads the M10C outcome.

For required absent tracks, M10D converts the structural M10C absence into deterministic:

```text
SPATIAL_TRACK_STATE_REQUIRED
```

issues.

No second transition winner calculation.

---

# 24. Required-track issue representation

For inspection, use one deterministic issue per missing required Track or one aggregate with a canonical ordered member set.

Preferred form:

```json
{
  "code": "SPATIAL_TRACK_STATE_REQUIRED",
  "layer": "track_requirement",
  "details": {
    "spatial_track_id": "...",
    "entity_id": "...",
    "reason": "clear"
  }
}
```

Order:

```text
(entity_id, spatial_track_id)
```

This gives filmmakers an actionable issue list while preserving one frozen error identity.

---

# 25. Shot/end transition lookup

M10C's effective Shot/start resolver correctly excludes target Shot/end.

M10D nevertheless needs target Shot/end `set` to validate explicit blocking handoff.

Do this with **one set-oriented query**, not a per-Track loop. The handoff query is scoped only to Tracks that have blocking entries in the current canonical plan:

```text
active transitions
WHERE deleted_at IS NULL
AND spatial_track_id IN blocking_track_ids
AND anchor_type = 'shot'
AND anchor_id = target_shot
AND boundary = 'end'
```

If `blocking_track_ids` is empty, no handoff query is required.

Shot/end transitions on Tracks without blocking entries are downstream persistent declarations only; they do not affect current-Shot handoff readiness. Required/optional Shot/start absence remains M10C staging responsibility.

Validate stored operation/aggregate shape fail-closed. If more than one active row somehow exists at one Track/Shot/end coordinate despite predecessor uniqueness constraints, fail invariant rather than choosing a winner.

This query does not call narrative rank and does not reimplement effective-state resolution. It retrieves only exact target-Shot/end events required by the blocking handoff rule.

---

# 26. M10D-3 — blocking agreement

For every blocking entry:

```text
corresponding effective Track at Shot/start must be staged
```

Otherwise:

```text
SPATIAL_BLOCKING_STATE_MISMATCH
```

At:

```text
time_ms = 0
```

the blocking transform must exactly equal M10C effective persistent transform.

Component-by-component integer equality.

No float tolerance.

No Euler equivalence substitution.

A staged Track without a blocking entry remains valid:

```text
persistent staging only
```

M10D does not synthesize a blocking document.

Frozen §21 defines this boundary. 

---

# 27. Explicit Shot/end handoff

For an active target Shot/end `set` on a Track that has a blocking entry:

```text
Shot.duration_ms must be non-NULL
```

and blocking must contain an exact keyframe:

```text
time_ms == Shot.duration_ms
```

whose transform exactly equals the Shot/end transition.

Otherwise:

```text
SPATIAL_BLOCKING_STATE_MISMATCH
```

Legal cells:

```text
Shot/end set + no blocking
→ allowed
→ persistent downstream declaration only

blocking + no Shot/end set
→ allowed
→ Shot-local motion does not redefine downstream state

Shot/end clear
→ does not apply to current Shot
→ no final blocking match required
```

No UI motion path may silently become a Shot/end transition.

---

# 28. Axis constraint

Schema 1 axis constraint:

```json
{
  "spatial_axis_id": "...",
  "camera_side": "positive"
}
```

Allowed side values:

```text
positive
negative
```

The axis must be included in the exact approved SpatialWorldRevision.

A stable world-level axis that is absent from the approved revision is insufficient.

If absent:

```text
SPATIAL_SHOT_PLAN_INVALID
```

or the exact frozen axis-plan invalid condition as mapped by §55; do not introduce another code.

---

# 29. Axis arithmetic

Use Python arbitrary-precision integers.

For approved axis endpoints A/B and camera position C:

```text
cross =
    (Bx - Ax) * (Cz - Az)
    -
    (Bz - Az) * (Cx - Ax)
```

Rules:

```text
positive side → cross > 0
negative side → cross < 0
cross == 0 → violation
```

Every authored camera keyframe is checked.

One violating keyframe is enough for:

```text
SPATIAL_AXIS_CONSTRAINT_VIOLATION
```

No float.

No epsilon.

No SQLite 64-bit arithmetic for the predicate.

No client-side override.

The mandatory frozen tests explicitly include values whose intermediate product exceeds signed 64-bit range. 

---

# 30. Coincident axis geometry

If approved revision endpoint frames A and B have identical X/Z coordinates:

```text
Ax == Bx
AND
Az == Bz
```

the axis is degenerate for schema-1 side evaluation.

At the M10D boundary this condition is discovered inside a **verified immutable approved SpatialWorldRevision**. It is therefore corruption, not an editable readiness defect:

```text
INTERNAL_INVARIANT_VIOLATION
```

No `SPATIAL_AXIS_INVALID` fallback is permitted at current M10D resolution for this case. Normal M10B working/capture validation is upstream; M10D independently refuses to calculate a meaningless side from corrupted immutable authority.

---

# 31. Screen direction

Screen direction remains:

```text
explicit production intent
```

not:

```text
pixel-analysis result
```

M10D:

* validates its closed vocabulary;
* captures it in ShotSpatialPlan;
* includes it in SpatialContinuityPack;
* shows it in current/historical inspection.

M10D does **not**:

* verify rendered motion;
* derive it from axis;
* block because current M9 executor cannot consume it.

Consumption/explicit omission is M10E scope.

---

# 32. SpatialContinuityPack schema 1

When non-empty spatial authority is coherent, build exactly one canonical pack:

```json
{
  "schema_version": 1,
  "spatial_world": {
    "spatial_world_id": "...",
    "requirement": "required",
    "spatial_world_state_id": "...",
    "spatial_world_revision_id": "...",
    "spatial_world_revision_hash": "...",
    "location_entity_id": "...",
    "location_entity_revision_id": "...",
    "world_snapshot": {
      "schema_version": 1
    }
  },
  "staging": [
    {
      "spatial_track_id": "...",
      "entity_id": "...",
      "entity_revision_id": "...",
      "requirement": "required",
      "transform": {
        "translation_mm": [0, 0, 0],
        "rotation_udeg": [0, 0, 0]
      },
      "source_transition": {
        "spatial_transition_id": "...",
        "anchor_type": "shot",
        "anchor_id": "...",
        "boundary": "end"
      }
    }
  ],
  "shot_plan": {
    "schema_version": 1
  }
}
```

This is the frozen pack family.

The builder's final value is passed through the existing `spatial.schemas.parse_continuity_pack()` authority, and the pack hash is produced by the existing `pack_hash()`/SoloRing canonical serializer. M10D does not introduce a second pack grammar. The evolved pack parser must embed the **returned normalized ShotSpatialPlan value** from `parse_shot_plan()`, not discard it after validation.

No duplicate top-level `spatial_continuity_hash` is embedded inside the pack; the hash is computed **over** the canonical pack.

---

# 33. Pack canonical integrity

Canonical staging order:

```text
(entity_id, spatial_track_id)
```

World snapshot inside pack must be exactly the immutable approved revision's canonical snapshot value.

Mechanical checks:

```text
canonical_json(pack.spatial_world.world_snapshot)
==
canonical bytes represented by SpatialWorldRevision.snapshot_json
```

and:

```text
SHA-256(canonical_json(world_snapshot))
==
spatial_world_revision_hash
```

World requirement is hash-bearing.

Track requirement is hash-bearing.

Exact EntityRevision is hash-bearing.

Winning Transition provenance is hash-bearing.

Plan is hash-bearing.

Axis declaration is hash-bearing.

Screen direction is hash-bearing.

---

# 34. Spatial hash

Compute:

```text
spatial_continuity_hash =
SHA-256(canonical_json(SpatialContinuityPack))
```

using the existing SoloRing canonical serializer.

No separate M10 JSON encoder.

No database-row hash.

No hash of a subset.

When no applicable M10 authority exists:

```text
pack = null
spatial_continuity_hash = null
ready = true
```

An empty synthetic pack is forbidden.

---

# 35. Deterministic issue precedence

Corruption always aborts first.

For legitimate unresolved current state, M10 issue precedence is:

```text
1  world selection / ambiguity
2  exact SpatialWorldState
3  approved immutable revision
4  placement authority
5  fixed EntityRevision consistency
6  required Track state
7  Shot plan / blocking
8  axis constraint
```

Frozen global capture precedence remains:

```text
M7
→ M8
→ M10 production
→ package
→ M9 realization
→ M10 realization
→ execution
```

And within M10:

```text
SPATIAL_WORLD_STATE_REQUIRED
before
SPATIAL_WORLD_APPROVAL_REQUIRED
```

and:

```text
SPATIAL_ENTITY_PLACEMENT_CONFLICT
before
SPATIAL_ENTITY_REVISION_MISMATCH
```

## 35.1 Prerequisite-aware issue accumulation

A full deterministic issue set contains every **independently evaluable** issue, not speculative derivative failures whose authoritative prerequisites do not exist.

Resolution dependency order is:

```text
world selection
    ↓
exact SpatialWorldState
    ↓
approved verified SpatialWorldRevision
    ↓
placement authority
    ↓
fixed EntityRevision consistency
    ↓
M10C staging / required Track state
    ↓
plan + blocking
    ↓
axis constraint
```

Rules:

* if world selection fails, do not fabricate state/approval/placement/axis issues for an unselected world;
* if exact state is absent, report `SPATIAL_WORLD_STATE_REQUIRED` and do not also report approval/placement/revision/axis issues that require that state;
* if approved revision is absent, report `SPATIAL_WORLD_APPROVAL_REQUIRED` and do not evaluate immutable placement/axis geometry;
* if an Entity has ambiguous placement authority, report `SPATIAL_ENTITY_PLACEMENT_CONFLICT` and suppress revision-mismatch evaluation for that Entity until placement becomes singular;
* independent issues at the same reachable layer may all be emitted in deterministic order.

`require_spatial_ready()` still raises the first blocker under frozen precedence while preserving only the semantically reachable issue set in `details`.

---

# 36. Issue ordering

Issue-array order must be deterministic, not lexicographic by error-code string.

Recommended key:

```text
(
    frozen_precedence_rank,
    entity_id_or_empty,
    spatial_world_id_or_empty,
    spatial_track_id_or_empty,
    spatial_axis_id_or_empty,
)
```

No timestamps.

No UUID-as-semantic-winner; stable IDs may only order multiple otherwise equal issue records after semantic precedence is fixed.

Every issue must identify its layer explicitly, e.g.:

```text
world_selection
world_requirement
world_state
world_approval
placement
entity_revision
track_requirement
plan
blocking
axis
```

The word `requirement` alone is not adequate diagnostics.

---

# 37. M10D-4 — current API

Add:

```text
GET /shots/{shot_id}/spatial-continuity
```

The endpoint owns one explicit coherent current read.

Composition:

```text
BEGIN
↓
active Shot
↓
M7 exact semantic dependencies/revisions
↓
ONE M10 resolver
↓
current projection
↓
COMMIT
```

It never opens:

```text
session A for M7
session B for world
session C for staging
```

---

# 38. Current spatial endpoint response

Return server-owned projection containing:

```text
shot_id
m7 readiness summary

ready
spatial_continuity_hash
issues

applicable/selected world
world requirement
exact Location EntityRevision

approved SpatialWorldRevision id/hash
approved frames
approved axes

effective staging
exact EntityRevision per staged Track
winning SpatialTransition provenance

current ShotSpatialPlan hash
camera
blocking
Shot/end handoff status
axis constraint + server evaluation
screen-direction declarations
```

When no M10 authority applies:

```json
{
  "ready": true,
  "spatial_continuity_hash": null,
  "issues": [],
  "spatial_continuity": null
}
```

No current endpoint labels any current result:

```text
captured
historical
used by Generation
```

unless it is reading a ShotRevision.

---

# 39. Upstream M7/M8 semantics

M10 depends on M7 exact semantic state.

If M7 is unresolved:

```text
M10 resolver does not fabricate inputs
spatial_continuity_ready = false
```

The endpoint exposes the upstream condition honestly.

M8 and M10 are sibling authority layers after M7.

Therefore:

```text
M8 blocked
does NOT authorize M10 to fabricate state
```

but current M10 may still be resolved for inspection after M7 is coherent.

For capture:

```text
M8 blocker precedes M10 blocker
```

according to frozen global precedence.

---

# 40. ShotRead fields

Extend only the response schema:

```python
spatial_continuity_ready: bool = False
spatial_continuity_hash: str | None = None
spatial_continuity_issues: list[...] = []
```

No columns are added to `shots`.

The default `False` prevents an incompletely populated server model from pretending spatial readiness was evaluated.

Frozen r3 explicitly requires computed-only Shot fields. 

---

# 41. Single current Shot read unit

Extend the existing Shot-detail current read.

It must evaluate, in one coherent transaction:

```text
M7
M8
M10
working snapshot hash
approved-Take comparison
```

M10 inspection may complete even when M8 is blocked, but:

```text
working_snapshot_hash
```

is non-null only when the complete capturable production state is ready under predecessor precedence.

Frontend never recomputes this.

---

# 42. Working snapshot builder integration

Extend the existing single canonical builder to accept:

```python
spatial_pack: Mapping[str, object] | None = None
```

Conceptually:

```python
build_capturable_snapshot(
    shot,
    refs,
    dependencies,
    feature_states=(),
    relation_states=(),
    visual_pack=None,
    spatial_pack=None,
)
```

No second builder.

No post-hash augmentation.

No:

```python
snapshot = build_old(...)
snapshot["spatial_continuity"] = spatial
rehash_somewhere_else(...)
```

The builder itself owns schema selection and final bytes.

---

# 43. Working-hash behavior

Changing any hash-bearing current M10 fact changes the working Shot hash, without modifying the Shot row itself.

Must mechanically prove changes to at least:

* selected approved world revision;
* world requirement;
* fixed bound exact EntityRevision;
* SpatialTrack requirement;
* effective winning transition;
* exact staged EntityRevision;
* current ShotSpatialPlan;
* camera keyframe;
* blocking keyframe;
* axis constraint;
* screen direction.

When a change makes required M10 unresolved:

```text
working_snapshot_hash = NULL
```

It must not silently fall back to lower-schema current bytes.

---

# 44. Shot spatial UI

Extend the existing Shot detail surface.

M10D requires reliable form/table authoring, not a DCC.

Show:

```text
Current spatial continuity
```

with distinct sections for:

* applicable/selected world;
* exact Location revision;
* world requirement;
* approved world revision/hash;
* current effective staging;
* exact staged EntityRevisions;
* source Transitions;
* working Shot spatial plan;
* camera optics;
* camera keyframes;
* blocking;
* Shot/end handoff;
* axis constraint;
* screen direction;
* readiness issues;
* current spatial hash.

---

# 45. Plan editor

The editor sends real CAS requests.

It maintains the last server-returned:

```text
plan_hash
```

Every save sends:

```text
expected_plan_hash = displayed/current server hash
```

On:

```text
SPATIAL_SHOT_PLAN_CONFLICT
```

the UI does not automatically overwrite.

It instructs production to refresh/reconcile.

No automatic retry.

---

# 46. UI authority discipline

Frontend may:

* display human-friendly degrees alongside canonical microdegrees;
* display meters alongside canonical millimeters;
* perform advisory form previews.

But submitted authority remains explicit server-normalized integers.

Client calculations must never determine:

* world selection;
* EntityRevision;
* transition winner;
* canonical plan hash;
* pack hash;
* axis validity;
* blocking validity;
* readiness precedence.

A client preview that disagrees with server results loses.

---

# 47. Current vs captured UI

Current view labels:

```text
Current spatial continuity
Working Shot spatial plan
Approved reusable world
Current effective staging
```

Historical view labels:

```text
Captured spatial continuity
Captured world revision
Captured staging
Captured Shot plan
```

Never show:

```text
Current world
```

under a heading implying:

```text
Used by this historical Generation
```

If a current comparison appears beside history, label it:

```text
Current — not used by this captured revision
```

---

# 48. M10D-5 — ShotRevision schema 5

Schema selection becomes the total lattice:

```text
zero semantic dependencies
→ exact schema 1

dependencies
+ no effective M7
+ no M8
+ no M10
→ exact schema 2

non-empty effective M7
+ no M8
+ no M10
→ exact schema 3

non-empty M8
+ no M10
→ exact schema 4

ANY non-empty M10 SpatialContinuityPack
→ schema 5
```

Schema 5 does **not** require M8.

This is a wrapper over whichever lower semantic state is otherwise applicable.

---

# 49. Schema-5 canonical shape

```json
{
  "schema_version": 5,
  "intent": { "...": "..." },
  "references": [],
  "continuity": { "...": "..." },
  "visual_reference_pack": { "...": "..." },
  "spatial_continuity": {
    "schema_version": 1
  }
}
```

Rules:

```text
visual_reference_pack
→ present iff non-empty M8 authority

spatial_continuity
→ mandatory and non-empty for schema 5
```

Existing M7 continuity grammar, including `relations`, remains unchanged inside schema 5.

No schema-5-specific reformatting of M7 bytes.

---

# 50. Impossible schema cells

Fail invariant on any attempt to produce:

```text
schema 5 + empty/missing spatial_continuity

non-empty M10 + schema 1/2/3/4

zero semantic dependencies + non-empty M10

schema 4 + non-empty M10

schema 5 whose embedded M8 bytes differ from canonical M8 input

schema 5 whose embedded M10 bytes differ from canonical M10 pack
```

No “best effort” fallback.

---

# 51. Lower-schema byte preservation

When:

```text
spatial_pack is None
```

M10D must preserve predecessor canonical bytes exactly.

Mandatory regression cells:

```text
schema 1 pre-M10 bytes identical
schema 2 pre-M10 bytes identical
schema 3 pre-M10 bytes identical
schema 4 pre-M10 bytes identical
```

No extra:

```text
"spatial_continuity": null
```

is inserted into schemas 1–4.

No empty schema 5.

---

# 52. Coherent capture read

The ShotRevision read phase freezes all current authority in **one** SQLite read transaction:

```text
Shot intent + refs
M7 exact semantic state
M8 current production authority
M10 applicable-world selection
approved immutable world
M10C staging
ShotSpatialPlan
camera/blocking/axis validity
```

One frozen in-memory object crosses into the write phase.

No M10 resolver call is permitted after that current read ends.

---

# 53. Capture write phase

Then:

```text
BEGIN IMMEDIATE
```

and use the existing convergence rule:

```text
(shot_id, snapshot_hash)
```

If existing revision found:

```text
validate complete reuse integrity
return existing revision
```

If new:

```text
allocate revision
insert shot_revisions
insert predecessor immutable children
insert M10 immutable children
commit
```

No retry-by-timestamp.

No second current resolution.

No current world re-read to reconstruct missing frozen values.

---

# 54. Immutable M10 child projection

Schema-5 ShotRevision must have:

```text
exactly 1 shot_revision_spatial_worlds row

0..N shot_revision_spatial_track_states rows

exactly 1 shot_revision_spatial_plans row
```

Schemas 1–4:

```text
zero rows in all three M10 ShotRevision child families
```

These are normalized integrity projections.

They do not replace the embedded pack.

---

# 55. Captured spatial world row

Persist exact:

```text
shot_revision_id
spatial_continuity_hash
spatial_world_id
requirement
spatial_world_state_id
spatial_world_revision_id
spatial_world_revision_hash
location_entity_id
location_entity_revision_id
```

Every field must project exactly from the embedded SpatialContinuityPack. The `requirement` column is confirmed present in the closed `0010` migration and remains part of this normalized historical integrity projection.

No current lookups are used to fill it.

---

# 56. Captured track rows

One row per **effective staged Track**, sorted:

```text
(entity_id, spatial_track_id)
```

`position` equals canonical index.

Persist the exact frozen `0010` projection:

```text
position
spatial_track_id
entity_id
entity_revision_id
requirement
x_mm
y_mm
z_mm
yaw_udeg
pitch_udeg
roll_udeg
source_transition_id
source_anchor_type
source_anchor_id
source_boundary
```

There is no `is_staged` column. The presence of the immutable child row itself means the Track was effectively staged in the captured pack.

Do not capture an absent optional Track as a fake transform.

Do not synthesize origin.

---

# 57. Captured plan row

Exactly one row for schema 5:

```text
shot_revision_id
plan_hash
plan_json
```

`plan_json` is the exact canonical current ShotSpatialPlan bytes captured in the pack.

Must satisfy:

```text
SHA-256(plan_json canonical bytes)
==
plan_hash
```

and:

```text
parsed captured plan
==
snapshot.spatial_continuity.shot_plan
```

---

# 58. Set-oriented child writes

Historical child persistence must not create one SQL round trip per Track.

Use:

```text
one executemany / batch write per child table class
```

not:

```python
for track in staging:
    await conn.execute(...)
```

as repeated database round trips.

Rows may scale.

SQL statement classes/count must not.

## 58.1 Whole-ShotRevision persistence batching required by the M10D scale gate

The complete schema-5 capture gate measures the existing ShotRevision persistence path, not only newly introduced M10 tables. At the pinned predecessor, inherited child writers still issue cardinality-sensitive per-row `execute()` calls for semantic dependencies, Feature states, Relation states, and M8 visual anchor/item rows.

M10D therefore explicitly permits and requires a **semantics-preserving persistence refactor** of those inherited ShotRevision child writers where their row counts vary in the representative fixture:

```text
shot_revision_entity_dependencies
→ one batch/executemany write class

shot_revision_feature_states
→ one batch/executemany write class

shot_revision_relation_states
→ one batch/executemany write class

shot_revision_visual_anchors
→ one batch/executemany write class

shot_revision_visual_anchor_items
→ one batch/executemany write class

shot_revision_spatial_worlds
→ one single-row write class

shot_revision_spatial_track_states
→ one batch/executemany write class

shot_revision_spatial_plans
→ one single-row write class
```

This refactor may change **database call shape only**. It may not change:

* canonical snapshot/spec/pack bytes;
* child table contents;
* positions or ordering semantics;
* source/audit fields;
* reuse-integrity comparisons;
* schemas 1–4 selection or bytes;
* error precedence;
* transactional boundaries.

Batch parameter ordering must be deterministic even where the database table key makes semantic row order set-like. The source collections are first placed in their existing canonical persistence order, then sent as one batch.

APR-072 applies: a whole-capture constant-statement claim is forbidden unless these inherited cardinality-sensitive loops are actually removed from the measured path.

---

# 59. Reuse integrity

When `(shot_id, snapshot_hash)` converges onto an existing ShotRevision, validate **all** M10 projections.

Schema 5:

1. embedded `spatial_continuity` canonical bytes/hash valid;
2. exactly one world child;
3. world child equals pack;
4. track child count equals staged pack entries;
5. positions contiguous;
6. each Track row exactly equals its canonical entry;
7. exact EntityRevision matches;
8. exact requirement matches;
9. exact transform matches;
10. exact source Transition/anchor provenance matches;
11. exactly one plan child;
12. plan bytes/hash equal pack;
13. nested world snapshot hashes to captured world revision hash.

Mismatch:

```text
INTERNAL_INVARIANT_VIOLATION
```

Never:

```text
reuse declined
→ silently create another revision
```

Never repair.

---

# 60. Historical spatial provenance API

Extend the existing historical ShotRevision authority endpoint:

```text
GET /shot-revisions/{revision_id}/continuity
```

The existing response gains one server-owned captured spatial projection, conceptually:

```json
{
  "shot_revision_id": "...",
  "snapshot_schema_version": 5,
  "snapshot_hash": "...",
  "dependencies": [],
  "feature_states": [],
  "relations": [],
  "visual": null,
  "spatial": {
    "spatial_continuity_hash": "...",
    "spatial_continuity": {"schema_version": 1},
    "world": {},
    "staging": [],
    "shot_plan": {}
  }
}
```

Exact response naming may follow the existing `_revision_continuity()` projection style, but the route is frozen: M10D does not introduce a competing `/shot-revisions/{revision_id}/spatial-continuity` historical endpoint.

## 60.1 Schema 1–4

Return the existing historical response with the captured spatial projection absent/null under one frozen response convention:

```text
spatial = null
```

for schema 1–4. Do not infer absence from current M10 state.

Never invoke current M10 resolution.

## 60.2 Schema 5

Read:

```text
shot_revisions.snapshot_json/hash
shot_revision_spatial_worlds
shot_revision_spatial_track_states
shot_revision_spatial_plans
```

Reconstruct and cross-validate captured authority.

The embedded pack is self-contained for interpretation.

The referenced immutable `SpatialWorldRevision` and its immutable frame/axis children **must** nevertheless be cross-checked on every schema-5 historical read. Missing revision/child rows, hash disagreement, or projection disagreement is `INTERNAL_INVARIANT_VIOLATION`. This is immutable provenance verification, not a current-approval lookup, and current mutable state remains unnecessary to interpret the pack.

---

# 61. Historical-reader forbidden current tables

Historical spatial inspection must not use current mutable authority from:

```text
shot_spatial_plans
spatial_world_states
spatial_world_state_frames
spatial_world_state_axes
spatial_tracks
spatial_transitions
current Entity approval-pointer lookup
current M10 resolver
```

Mutable world/frame/axis identity rows may not be required to interpret captured semantics; any optional display metadata must be clearly non-authoritative and must not affect response authority bytes/hash.

A table/query spy must prove this denylist. Immutable historical reads may use `shot_revisions`, the three `shot_revision_spatial_*` tables, `spatial_world_revisions`, `spatial_world_revision_frames`, and `spatial_world_revision_axes` for captured-byte/projection verification.

Changing any current authority after capture must not change the historical response.

---

# 62. Historical corruption loop

For every applicable immutable projection:

```text
capture valid schema 5
↓
record successful historical read
↓
directly corrupt one historical field
↓
historical read fails INTERNAL_INVARIANT_VIOLATION
↓
restore exact stored value
↓
historical read succeeds identically
```

No fallback to current state.

---

# 63. Generation safety boundary before M10E

M10D creates schema-5 authority but does **not** yet install execution realization.

Therefore the M10D→M10E interval uses one explicit, unconditional fail-closed guard:

```text
would-be/captured ShotRevision schema_version == 5
(or equivalently non-empty captured M10 SpatialContinuityPack)
→ SPATIAL_REALIZATION_UNSUPPORTED
→ no Generation row is queued/persisted
```

There is **no package-capability inspection in M10D**. RealizationProfile schema 2, package/manifest spatial capability, workflow-spec schema 3, D0 materialization, and spatial compiler logic belong to M10E and therefore cannot be conditions for allowing execution during M10D.

## 63.1 Source-fit call site

At the pinned predecessor, new Generation creation is owned by:

```text
server/soloring/generation/service.py
create_generation_request(...)
```

R3 pins the temporary guard immediately after coherent ShotRevision capture/reuse returns the captured revision and **before** package semantic validation, Generation input mapping, workflow-spec assembly, or repository persistence:

```text
M7/M8/M10 current authority resolution + ShotRevision capture/reuse
        ↓
PRE-M10E SCHEMA-5 FENCE
        ↓ only schemas 1–4 continue
existing M9 package/realization path
```

The guard should be one named integration seam, conceptually:

```python
def assert_pre_m10e_spatial_execution_fence(revision) -> None:
    ...
```

M10E must explicitly subsume/replace the unconditional schema-5 branch with real spatial capability + compiler handling while preserving the same fail-closed default for unsupported hard M10 authority. It must not silently delete the safety property.

The temporary M10D guard must not:

* build workflow-spec schema 3;
* inspect a hypothetical M10-capable package;
* choose a spatial package;
* materialize D0;
* bind Comfy nodes;
* create derived spatial Blobs.

This fence is part of M10D closure and is mechanically tested through the real Generation creation path. Schema 1–4 predecessor Generation behavior must remain unchanged.

---

# 64. M10D-6 — coherent-read race contract

M10D closes the full authority/capture race class that M10C could only preview locally.

A valid result is always:

```text
complete BEFORE
OR
complete AFTER
```

Never:

```text
old EntityRevision
+ new world approval
+ old transitions
+ new plan
```

No mixed snapshot.

---

# 65. Race mechanics

Every race proof uses:

* two real asynchronous tasks/connections;
* real production mutation service;
* an `asyncio.Event`/barrier at the actual production read seam;
* SQLite WAL snapshot behavior;
* no `sleep()` ordering;
* no mocked resolver result;
* no manual fake “old/new” IDs passed around instead of executing mutation.

APR-033 and APR-072 apply.

---

# 66. Required race families

For each mutable hash-bearing dependency, prove BEFORE and AFTER.

## 66.1 ShotSpatialPlan edit

BEFORE:

```text
capture pins coherent snapshot
→ plan CAS update commits
→ capture stores complete old plan/pack
```

AFTER:

```text
plan update commits
→ capture begins
→ complete new plan/pack
```

Also DELETE vs capture.

## 66.2 SpatialWorld approval

BEFORE:

```text
old approved revision visible to pinned read
→ approval changes
→ capture contains old revision only
```

AFTER contains new.

## 66.3 World working membership/value edit

A working frame/axis edit without new approval:

```text
must NOT alter current approved-world pack
```

Then:

```text
edit
→ capture new SpatialWorldRevision
→ approve
```

becomes a real pack change.

This mechanically distinguishes Working from Approved authority.

## 66.4 SpatialTransition edit

Complete old staging or complete new staging.

Reuse M10C mutation services.

## 66.5 Exact dependent EntityRevision approval

Use the real M7/M6 Entity approval path.

This is the full frozen class-6 proof:

```text
exact semantic EntityRevision
+
fixed-frame cross-check
+
Track EntityRevision
+
whole SpatialContinuityPack
+
schema-5 capture
```

must be one coherent state.

M10C's preview proof is predecessor evidence, not a substitute.

## 66.6 SpatialWorld requirement flip

World requirement is hash-bearing.

Complete old requirement or complete new requirement.

## 66.7 SpatialTrack requirement flip

Track requirement is hash-bearing.

Complete old requirement/readiness or complete new.

## 66.8 Narrative reorder

Promote narrative topology reorder to a full M10D capture race. A reorder may change M7 rank and therefore the winning M10C SpatialTransition without changing any Transition row.

Prove BEFORE/AFTER through:

```text
narrative rank
→ winning SpatialTransition
→ effective staging transform/provenance
→ SpatialContinuityPack
→ schema-5 snapshot/hash
```

M10C's existing topology race remains predecessor evidence but is not a substitute for the composed schema-5 proof.

## 66.9 Shot duration mutation

Use the real Shot mutation path to change `duration_ms` across the validity boundary of existing camera/blocking keyframes.

BEFORE captures the complete old valid/invalid current context; AFTER captures the complete new context. If the new duration makes the stored plan invalid, capture blocks with `SPATIAL_SHOT_PLAN_INVALID`; it never mixes old duration with new plan readiness.

## 66.10 Semantic dependency-set mutation

Use the real semantic-dependency mutation path to add/remove a Shot dependency while capture is contested.

The result must be complete BEFORE or AFTER across:

```text
applicable world selection
blocking Track ownership
M10C applicable staging
fixed-frame EntityRevision checks
placement conflicts
SpatialContinuityPack
schema-5 snapshot/hash
```

This is distinct from EntityRevision approval: dependency membership itself changes which M10 authorities apply.

---

# 67. Capture-barrier seam

Prefer to place the mechanical barrier at the actual common capture read seam—not inside a test-only duplicate of capture logic.

If a test hook is necessary, it must:

* default to `None`;
* never affect production semantics;
* fire only after the first read has established the coherent SQLite snapshot;
* let the production capture function continue normally.

A race proved against a bespoke test composition rather than the public capture path does not close the gate.

---

# 68. Corruption matrix

M10D must at minimum cover:

1. SpatialWorldRevision `snapshot_json`.
2. SpatialWorldRevision `snapshot_hash`.
3. immutable revision frame position/value.
4. immutable revision axis endpoint/position.
5. approved pointer → revision from wrong state.
6. malformed current stored ShotSpatialPlan.
7. stored plan hash/JSON disagreement.
8. ShotRevision spatial world child hash/id.
9. ShotRevision Track EntityRevision.
10. ShotRevision Track transform.
11. ShotRevision Track source Transition provenance.
12. ShotRevision plan hash.
13. ShotRevision plan bytes.
14. schema-5 embedded spatial pack mutated.
15. embedded world snapshot mutated.
16. nested world revision hash disagreement.
17. extra/missing M10 child.
18. child canonical position gap.
19. illegal schema5-without-spatial shape.
20. captured `shot_revision_spatial_worlds.requirement`.
21. captured `shot_revision_spatial_track_states.requirement`.

For each:

```text
corrupt
→ relevant read/reuse/capture fails
→ restore exact value
→ positive control succeeds
```

This is the frozen corruption discipline. 

---

# 69. Determinism gates

Mandatory byte-level tests:

1. Plan JSON object key order difference → same bytes/hash.
2. Plan whitespace difference → same bytes/hash.
3. Blocking-entry input order difference → same canonical bytes/hash.
4. Canonical camera keyframe input → stable bytes.
5. Canonical blocking keyframe input → stable bytes.
6. SpatialWorldRevision verified bytes stable.
7. Staging source DB order shuffled → existing M10C byte identity preserved.
8. Pack source collection order shuffled → identical pack bytes/hash.
9. Issue-source DB order shuffled → identical issue ordering.
10. Schema-5 semantic source row order shuffled → identical snapshot bytes/hash.
11. Schema-5 M8 present/absent cells deterministically selected.
12. Numerically distinct normalized Euler tuples remain distinct.
13. Requirement changes change hashes.
14. Exact EntityRevision changes change hashes.
15. No authored axis constraint produces the frozen present `"axis_constraint": null` bytes; omitted `axis_constraint` is rejected.
16. Empty blocking is exactly `"blocking": []`; missing `screen_direction` inside a blocking entry is rejected.
17. Rotation tuples differing only by frozen wrap normalization (for example `+180000000` vs `-180000000`) produce identical canonical plan bytes/hash.
18. `parse_continuity_pack()` retains the normalized returned plan value; unnormalized caller rotations cannot survive into pack bytes.
19. Post-capture current world-requirement flip leaves historical schema-5 response byte-identical.
20. Post-capture current Track-requirement flip leaves historical schema-5 response byte-identical.
21. Semantics-preserving predecessor child-write batching leaves schema-1..4 parent bytes and child row projections identical to pre-refactor fixtures.
22. Historical spatial reconstruction through `/shot-revisions/{id}/continuity` is byte-identical regardless of current mutable M10 edits.

No deterministic test may rely on database-return order or timestamp sorting.

---

# 70. Camera golden fixtures

At minimum:

```text
identity camera
+90 yaw
-90 yaw
+90 pitch
-90 pitch
+90 roll
-90 roll
combined Y-X-Z case
+180 normalized to -180
```

Pinhole pure fixtures:

```text
point on optical axis
point right of center
point left
point up
point down
point at z >= 0 → non-projectable under pinhole helper
```

M10D does not create pixel coordinates because raster dimensions are execution-side.

---

# 71. Axis golden fixtures

Mandatory:

```text
A = [0,0,0]
B = [1000,0,0]
C = [0,0,1000]

cross = +1,000,000
```

Then:

* reflected C negative;
* exact line zero violation;
* later camera keyframe crosses forbidden side;
* coincident endpoint geometry rejected;
* values generating >64-bit intermediate still sign-correct.

No floating tolerance.

---

# 72. Blocking fixtures

Explicitly pin:

```text
t0 exact match → pass
t0 one-mm mismatch → blocker
t0 one-udeg mismatch → blocker
blocking Track absent at Shot/start → blocker

Shot/end set + blocking + duration NULL → blocker
Shot/end set + blocking + missing final keyframe → blocker
Shot/end set + blocking + exact final → pass

Shot/end set + no blocking → pass
blocking + no Shot/end transition → pass
Shot/end clear + blocking → no endpoint match requirement
```

No test should imply Shot-local animation automatically creates downstream state.

---

# 73. Current API determinism

Resolve the same Shot:

```text
before unrelated API visits
after arbitrary earlier Shot visits
after staging inspector visits
after historical inspector visits
```

Result bytes/hash must be identical.

API visitation order is not authority.

---

# 74. Scale gate — current resolution

Small fixture and representative fixture use the same real:

```text
GET /shots/{id}/spatial-continuity
```

production path.

Representative target should include approximately:

```text
2,500 Shots
multiple Sequences
multiple Scenes
60+ approved frames
multiple axes
recurring Characters
recurring Props
recurring Vehicles
required + optional worlds
required + optional Tracks
multiple effective staged Tracks
multiple semantic dependencies
multiple effective Feature states
multiple effective Relation states
multiple M8 visual anchors/items in the M8-present cell
all narrative anchor classes
Shot/end handoff
multi-entry blocking
axis constraint
M8 present in one fixture cell
unrelated world/track/transition noise
```

The target Shot—not merely unrelated project volume—must exercise the large dependency/spatial dimension.

---

# 75. Current-resolution SQL gate

Measure complete endpoint statement classes, including:

```text
Shot
M7 dependencies/revisions
narrative ordering
applicable worlds
current plan
exact state/approval
immutable revision
immutable frames
immutable axes
applicable Tracks
relevant Transitions
target Shot/end events
```

Pass:

```text
small statement class/count
==
representative statement class/count
```

for equivalent semantic branch shape.

Rows may increase.

Bytes may increase.

Round trips may not increase per frame/axis/track/transition/keyframe.

Frozen M10 requires this rows-not-round-trips behavior. 

---

# 76. Scale gate — schema-5 capture

Separately measure first-time:

```text
ShotRevision capture
```

on small and representative legal targets.

The comparison fixtures must have the same semantic branch shape: if the representative case populates dependencies, Feature states, Relation states, M8 anchors/items, and M10 spatial children, the small paired case must populate those same table classes with fewer rows. Separate M8-absent cells may be measured separately but cannot be substituted for the M8-present whole-path proof.

Include the **complete** first-time ShotRevision capture path:

```text
all current read queries
shot_revision parent insert
one dependency-child batch class
one Feature-state-child batch class when that table is populated
one Relation-state-child batch class when that table is populated
one visual-anchor batch class when M8 is populated
one visual-anchor-item batch class when M8 items are populated
one spatial-world child write class
one spatial-track batch class
one spatial-plan write class
```

Pass, for equivalent semantic branch shape with larger row cardinalities:

```text
same SQL statement classes/count
```

Rows/parameter sets may grow. Round trips may not grow per dependency, Feature state, Relation state, visual anchor/item, frame, axis, Track, Transition, or keyframe.

The gate is a whole-capture claim. It is not satisfied by batching only `shot_revision_spatial_track_states` while inherited predecessor child writers remain per-row.

Do not wait for M10F to discover cardinality-sensitive ShotRevision persistence.

M10F will later repeat the complete first-Generation gate across M10E realization; M10D proves the authority/capture portion now. Frozen final closure explicitly reserves full first-Generation SQL proof for M10F. 

---

# 77. Size evidence

For the representative schema-5 fixture record:

```text
SpatialWorldRevision snapshot bytes
SpatialContinuityPack bytes
schema-5 full snapshot bytes
frame count
axis count
staged Track count
blocking Track count
camera keyframe count
blocking keyframe count
duplicated embedded world-snapshot bytes
```

No arbitrary byte-size pass/fail threshold.

The embedded world snapshot is a deliberate archival/self-contained portability tradeoff, not a performance accident. 

---

# 78. API transport discipline

Every new request model uses:

```python
ConfigDict(extra="forbid")
```

including nested plan structures.

No M10D-specific aliases such as:

```text
CAMERA_INVALID
BLOCKING_INVALID
WORLD_NOT_READY
PLAN_STALE
AXIS_SIDE_INVALID
SPATIAL_CAPTURE_NOT_READY
```

Use the frozen identities already present in `errors.py`.

---

# 79. Acceptance matrix

## ShotSpatialPlan / CAS — 1–22

1. Valid plan create with `expected_plan_hash=null`.
2. Create over existing plan conflicts.
3. Exact-hash update succeeds.
4. Stale-hash update conflicts.
5. Null expected hash on existing update conflicts.
6. Same canonical candidate under exact expected hash converges/no-ops.
7. Exact-hash DELETE succeeds.
8. Null expected hash on existing DELETE conflicts.
9. Stale expected hash on DELETE conflicts.
10. Nonexistent + null DELETE is idempotent.
11. Nonexistent + non-null DELETE conflicts.
12. Extra top-level PUT field rejected.
13. Extra nested camera field rejected.
14. Extra nested blocking field rejected.
15. Unknown schema version rejected.
16. Selected world cross-Project rejected.
17. Selected world Location not current dependency rejected.
18. Blocking Track tombstoned rejected.
19. Blocking Track wrong world rejected.
20. Blocking Track Entity not dependency rejected.
21. Axis identity wrong world rejected.
22. Plan mutation leaves historical rows untouched.

## Camera / canonicalization — 23–36

23. `projection="perspective"` accepted.
24. Other projection rejected.
25. Non-positive focal length rejected.
26. Non-positive sensor dimension rejected.
27. Non-integer optics rejected.
28. First camera keyframe not zero rejected.
29. Duplicate camera times rejected.
30. Decreasing times rejected.
31. Time greater than duration rejected.
32. NULL duration permits only time zero.
33. Translation JS-safe bounds enforced.
34. Rotation normalization exact.
35. Object-key/formatting differences produce identical bytes/hash.
36. Blocking-entry order differences produce identical bytes/hash.

## Blocking / handoff — 37–48

37. Duplicate blocking Track rejected.
38. Valid screen direction accepted for all four frozen values.
39. Unknown screen direction rejected.
40. Blocking t0 equals persistent staging → pass.
41. Blocking t0 translation mismatch → blocker.
42. Blocking t0 rotation mismatch → blocker.
43. Blocking Track has no Shot/start state → blocker.
44. Effective staged Track with no blocking → valid static staging.
45. Shot/end set + blocking + NULL duration → blocker.
46. Shot/end set + missing/mismatched final keyframe → blocker.
47. Shot/end set + exact final keyframe → pass.
48. Shot/end set without blocking / Shot-end clear cases obey frozen exception.

## World / complete resolver — 49–66

49. > 1 required applicable worlds → `SPATIAL_CONTEXT_AMBIGUOUS`.
50. Exactly one required world + no plan → `SPATIAL_SHOT_PLAN_REQUIRED`.
51. Required world + plan selecting another world → invalid.
52. Zero required worlds + optional plan selection valid.
53. Zero required worlds + no plan → ready/null hash/no pack.
54. Optional worlds are never auto-selected.
55. Plan Location removed from dependency set → invalid.
56. Exact Location EntityRevision selects exact state.
57. Missing state → `SPATIAL_WORLD_STATE_REQUIRED`.
58. Existing state with no approval → `SPATIAL_WORLD_APPROVAL_REQUIRED`.
59. Missing-state precedence beats approval-required.
60. Wrong-state approved pointer → invariant.
61. Immutable world snapshot/hash corruption → invariant.
62. Two fixed placements for one Entity → placement conflict.
63. Fixed placement + Track → placement conflict.
64. Placement conflict precedes revision mismatch.
65. Fixed bound EntityRevision mismatch → revision mismatch.
66. Bound world-internal Entity not a Shot dependency remains valid provenance.

## Staging / axis / pack — 67–79

67. M10D uses M10C exact staging result.
68. Required absent Track yields deterministic blocker.
69. Optional absent Track remains valid.
70. Exact staged EntityRevision retained.
71. Winning SpatialTransition provenance retained.
72. Axis absent from approved revision rejected.
73. Positive-side golden case passes.
74. Reflected side fails.
75. Camera exactly on axis fails.
76. Camera crosses side at later keyframe fails.
77. > 64-bit intermediate sign remains exact.
78. Pack staging canonical order `(entity_id, spatial_track_id)`.
79. Shuffled source inputs produce byte-identical pack/hash.

## Current API / working hash — 80–88

80. ShotRead spatial fields are populated server-side.
81. No M10 DB column added to Shot.
82. Current endpoint no-authority state is ready/hash-null.
83. Current endpoint returns full deterministic M10 issue set.
84. Current and historical labels remain distinct.
85. Plan change changes current working hash.
86. Transition change changes working hash.
87. World approval/requirement change changes working hash.
88. M10 blocker makes effective working snapshot non-capturable/null without lower-schema fallback.

## Schema 5 / history — 89–103

89. Pre-M10 schema-1 bytes unchanged.
90. Pre-M10 schema-2 bytes unchanged.
91. Pre-M10 schema-3 bytes unchanged.
92. Pre-M10 schema-4 bytes unchanged.
93. Schema 5 over schema-2 semantic base works.
94. Schema 5 over schema-3 semantic base works.
95. Schema 5 with non-empty M8 works.
96. Schema 5 without M8 works.
97. Empty/missing schema-5 spatial block fails invariant.
98. Schema 5 persists exactly one world child.
99. Schema 5 persists canonical Track child rows.
100. Schema 5 persists exactly one plan child.
101. Repeat unchanged capture converges.
102. Reuse-integrity corruption fails rather than recaptures.
103. Historical inspector reconstructs without current mutable M10 reads.

## Races / scale — 104–117

104. Plan edit vs capture BEFORE.
105. Plan edit vs capture AFTER.
106. Plan delete vs capture BEFORE/AFTER.
107. World approval change BEFORE.
108. World approval change AFTER.
109. Working world edit alone does not change approved pack.
110. Newly captured+approved world revision changes pack coherently.
111. Transition edit BEFORE/AFTER.
112. EntityRevision approval BEFORE/AFTER.
113. World requirement BEFORE/AFTER.
114. Track requirement BEFORE/AFTER.
115. Small vs ~2,500 current endpoint statement classes/count identical.
116. Matched small vs representative complete schema-5 capture statement classes/count identical.
117. Representative schema/pack/world byte metrics recorded.

## R3 pre-authorization/source-fit additions — 118–144

118. No authored axis constraint canonicalizes as explicit `"axis_constraint": null`; omitted `axis_constraint` is rejected.
119. Empty blocking is canonical `[]`; blocking entry without explicit `screen_direction` is rejected.
120. Stored valid plan + current duration shrink below a camera keyframe → `SPATIAL_SHOT_PLAN_INVALID`, stored plan hash unchanged.
121. Stored valid plan + current duration becomes NULL while any camera/blocking keyframe is later than t0 → invalid current readiness, stored plan hash unchanged.
122. Shot duration mutation vs capture BEFORE.
123. Shot duration mutation vs capture AFTER.
124. Narrative reorder vs schema-5 capture BEFORE.
125. Narrative reorder vs schema-5 capture AFTER.
126. Semantic dependency-set mutation vs capture BEFORE.
127. Semantic dependency-set mutation vs capture AFTER.
128. Tombstoned target Shot/end Transition is ignored; only `deleted_at IS NULL` events for blocking Tracks participate in handoff validation.
129. Coincident X/Z endpoints discovered in a verified approved SpatialWorldRevision fail `INTERNAL_INVARIANT_VIOLATION`.
130. Schemas 1–4 continue through the pre-M10E Generation path with predecessor behavior unchanged.
131. Schema 5 through pre-M10E Generation → `SPATIAL_REALIZATION_UNSUPPORTED`, zero queued/persisted Generation, no workflow-spec schema 3, no D0/derived spatial materialization.
132. Corrupt captured world `requirement` child → invariant failure; restore succeeds.
133. Corrupt captured Track `requirement` child → invariant failure; restore succeeds.
134. Current world requirement flip after capture does not change historical response.
135. Current Track requirement flip after capture does not change historical response.
136. Missing exact SpatialWorldState suppresses derivative approval/placement/revision/axis issues that cannot be evaluated.
137. Placement conflict for an Entity suppresses revision-mismatch evaluation for that Entity until singular placement authority exists.
138. ShotSpatialPlan input rotation `+180000000` and canonical `-180000000` converge to identical returned plan bytes/hash through the existing `spatial.schemas.parse_shot_plan` authority.
139. `parse_continuity_pack()` embeds the normalized returned ShotSpatialPlan; raw unnormalized rotation values cannot survive after successful pack parsing.
140. Invalid ShotSpatialPlan grammar fails with durable `SPATIAL_SHOT_PLAN_INVALID` while remaining catch-compatible with the predecessor `schemas.SchemaInvalid` family; SpatialWorld grammar error identity remains unchanged.
141. Historical schema-5 spatial authority is exposed by extending `GET /shot-revisions/{revision_id}/continuity`; no sibling historical spatial endpoint is added.
142. Matched small/representative schema-5 captures with the same populated child-table classes but increased dependency/Feature/Relation/visual/spatial row cardinality preserve identical SQL statement classes/count through set-oriented inherited and new child writes.
143. Semantics-preserving child-write batching leaves schemas 1–4 canonical parent bytes and normalized historical child projections unchanged.
144. Whole-capture SQL tests fail if any measured predecessor or M10 child collection regresses to one database round trip per row.

APR-072 applies literally to every matrix title and assertion.

---

# 80. Critical production proofs

## 80.1 Hotel-lobby reverse angle

Use one exact approved Lobby SpatialWorldRevision.

Shot A:

```text
camera on positive side
Eva + desk clerk staged
front desk / columns / elevator-bank fixed landmarks
```

Shot B:

```text
different camera keyframe(s)
same approved world revision
same fixed landmark geometry
explicit axis rule
```

Prove:

```text
same world authority
+
different ShotSpatialPlan camera
→ different spatial hash
while reusable world hash remains identical
```

No Generation is allowed to redefine the lobby.

## 80.2 Moving character handoff

Continue the M10C proof:

```text
Shot 20/end explicit set:
Eva → front desk

Shot 21/start:
M10C direct staging = front desk
```

M10D additionally proves:

```text
Shot 20 blocking final keyframe
==
Shot 20/end transition
```

when blocking is present.

Then Shot 21 schema-5 pack captures the inherited explicit placement without reading Shot 20's Take.

## 80.3 Location revision replacement

```text
Lobby EntityRevision 3
→ approved SpatialWorldRevision W3

semantic Location approval changes to Rev 4
→ W3 no longer applies

no Rev-4 SpatialWorldState
→ SPATIAL_WORLD_STATE_REQUIRED

new explicit Rev-4 state/revision/approval
→ W4 applies
```

No carry-forward.

---

# 81. Definition of Done

M10D closes only when all of the following are true:

### Plan authority

* The existing `server/soloring/spatial/schemas.py` remains the ONE full ShotSpatialPlan parser/canonicalizer and is evolved in place; no second grammar exists.
* M10C's minimal plan-reference reader remains narrowly scoped.
* Recursive request schemas reject undeclared fields.
* Plan canonical bytes use the standard SoloRing serializer.
* Returned plan transforms are normalized canonical values; wrap-equivalent rotations converge byte-for-byte.
* ShotSpatialPlan grammar failures use `SPATIAL_SHOT_PLAN_INVALID` without changing SpatialWorld grammar error identity.
* Plan hash is server-derived.
* Full create/update/delete CAS table is exact.
* Stale CAS never overwrites.
* Plan deletion never touches history.
* Camera optics follow frozen pinhole contract.
* Camera keyframe range/order is exact.
* Sparse keyframes make no interpolation claim.
* Blocking Track references are active and ownership-valid.
* Blocking order is canonical and empty blocking is exactly `[]`.
* No authored axis constraint is canonical explicit `"axis_constraint": null`; omission is rejected.
* `screen_direction` is required in every blocking entry and the frozen four-value vocabulary is exact.

### Complete resolution

* Exactly one complete current M10 spatial resolver exists.
* It consumes the caller's coherent connection.
* It consumes exact M7 EntityRevision inputs.
* It uses M10C staging rather than duplicating temporal resolution.
* It applies frozen applicable-world selection.
* Optional worlds are never implicitly selected.
* Exact Location revision selects exact state.
* Missing state and missing approval remain distinct.
* Immutable approved world bytes/children are mechanically verified.
* Fixed/fixed and fixed/Track conflicts fail.
* Placement conflict precedes EntityRevision mismatch.
* Fixed bound revisions cross-check semantic revisions.
* Required Track absence blocks.
* Optional Track absence is canonical.
* Current `Shot.duration_ms` revalidates all camera/blocking keyframe ranges on every resolution.
* Prerequisite-aware issue accumulation never fabricates derivative blockers.
* No earlier Shot is replayed.

### Camera/blocking/axis

* Blocking t0 agrees exactly with persistent staging.
* Shot/end handoff is exact where required.
* Shot/end without blocking remains legal.
* Blocking without Shot/end remains Shot-local only.
* Shot/end clear semantics remain unchanged.
* Axis exists in exact approved revision.
* Axis arithmetic uses arbitrary-precision server integers.
* Exact-on-axis fails.
* Coincident X/Z axis endpoints in verified approved history are invariant corruption.
* Every camera keyframe is checked.
* The pure pinhole fixture uses the frozen `R^T(P-t)` and `f*x/(-z), f*y/(-z)` mapping.
* Screen direction remains declared intent, not pixel-derived authority.

### Pack/hash/current API

* SpatialContinuityPack schema 1 has one canonical builder.
* Embedded world snapshot agrees exactly with immutable revision.
* Staging order is canonical.
* `spatial_continuity_hash` covers the entire pack.
* No applicable authority gives `ready=true/hash=null`.
* No empty pack exists.
* ShotRead exposes only computed M10 fields.
* Current endpoint returns server-owned readiness/issue/hash.
* UI never recomputes authority.
* Current and captured labels cannot be confused.
* M10 facts participate in the single working Shot snapshot hash.

### Schema-5 capture

* Single existing Shot snapshot builder owns schema-5 selection.
* Schemas 1–4 remain byte-identical when M10 absent.
* Any non-empty M10 selects schema 5.
* M8 may be absent or present in schema 5.
* Empty schema 5 is impossible.
* Coherent read freezes M6/M7/M8/M10 together.
* No current M10 resolver runs after the read snapshot closes.
* M10 child rows are immutable projections.
* Child writes are set-oriented.
* Inherited dependency/Feature/Relation/M8 ShotRevision child writers are batch-refactored where necessary so the complete schema-5 capture path satisfies APR-044 without changing schemas 1–4 semantics.
* Existing revision convergence validates full M10 integrity.
* Corruption never triggers repair-by-recapture.
* Historical reads use captured/immutable data only.
* Historical schema-5 reads mandatorily cross-check the referenced immutable SpatialWorldRevision and immutable children.
* Historical spatial provenance extends `GET /shot-revisions/{revision_id}/continuity`; no competing historical route exists.
* Historical query spies enforce the current-table denylist.
* Captured world/Track requirement corruption fails closed and post-capture requirement flips do not rewrite history.
* Current edits never rewrite history.

### Concurrency / evidence

* Plan races use real CAS mutation.
* World approval races use real approval mutation.
* EntityRevision race uses real Entity approval.
* Transition/requirement races use real M10 services.
* Narrative reorder, Shot duration, and semantic dependency-set races are full M10D BEFORE/AFTER capture proofs.
* BEFORE/AFTER tests use actual barriers at production seams.
* No sleep-based pseudo-races.
* Corruption loops restore exact bytes.
* Determinism is byte-level.
* Current resolution is bounded-query at representative scale.
* Schema-5 capture is bounded-query at representative scale.
* Full predecessor backend suite remains green.
* Full frontend suite remains green.
* `tsc --noEmit` clean.
* production build clean.
* `compileall` clean.
* supplied evidence and independently reproduced evidence remain separately classified.

### Scope

* No new migration.
* No new M10 error aliases.
* No workflow-spec schema 3.
* No spatial realization compiler.
* No D0 materialization.
* No worker/Exact Rerun M10 integration.
* The only Generation-path change is the temporary unconditional schema-5 fail-closed fence; no M10E realization is implemented.
* Existing Stage-0 raw Comfy release-byte capture/storage may occur before that fence; no package semantic validation, workflow assembly, GenerationInput persistence, or Generation persistence occurs after a schema-5 revision reaches the fence.
* No rich 3D editor.
* No interpolation authority.
* No M10E/F implementation.
* No publication/tagging.

---

# 82. Implementation sequence

## M10D-1 — ShotSpatialPlan authority and CAS

Deliver:

```text
in-place evolution of server/soloring/spatial/schemas.py
    preserve one grammar
    explicit-null axis absence
    returned transform normalization
    plan-specific frozen error identity
    normalized plan retained by pack parser
recursive strict request schemas
canonical bytes/hash
write-time ownership validation
PUT CAS
DELETE CAS
plan transport tests
plan determinism fixtures
```

**Gate:** Shot-local spatial authority can be safely authored and CAS-protected.

## M10D-2 — Approved-world composition and ONE complete resolver

Deliver:

```text
verified immutable world-revision reader
applicable-world selection
exact Location revision/state/approval lookup
fixed placement conflict
fixed EntityRevision check
M10C staging composition
deterministic issue model/precedence
```

**Gate:** One target Shot resolves one coherent approved spatial world and persistent placement state.

## M10D-3 — Camera, blocking, axis, and SpatialContinuityPack

Deliver:

```text
camera math fixtures
blocking t0 validation
Shot/end handoff
axis integer predicate
pack builder
pack hash
pack byte determinism
```

**Gate:** complete non-empty M10 production authority becomes one canonical hashable pack.

## M10D-4 — Current API, working hash, and Shot spatial UI

Deliver:

```text
GET /shots/{id}/spatial-continuity
ShotRead fields
single current Shot read integration
working snapshot hash integration
Shot plan editor
current spatial inspector
honest issue rendering
```

**Gate:** production can author and inspect current complete M10 authority without client-side authority logic.

## M10D-5 — ShotRevision schema-5 capture and historical provenance

Deliver:

```text
schema-5 snapshot builder extension
schema lattice compatibility cube
coherent capture read
immutable M10 child rows
reuse integrity
extend existing /shot-revisions/{id}/continuity with captured spatial projection
captured-row-only verification
current-vs-captured UI
```

**Gate:** non-empty M10 authority is immutable historical ShotRevision state.

## M10D-6 — Coherence races, corruption, determinism, scale, and closure

Deliver:

```text
full M10D race family including narrative reorder, duration, and dependency-set mutation
corrupt/fail/restore loops including captured requirement fields
plan/pack/schema determinism + frozen explicit-null axis fixture + rotation-normalization convergence
current endpoint small-vs-representative SQL gate
schema-5 capture small-vs-representative whole-path SQL gate
semantics-preserving batching of inherited + M10 ShotRevision child writers
representative byte metrics
pre-M10E schema-5 Generation fence + schemas 1–4 predecessor control
predecessor regression suites
frontend/typecheck/build
compileall
exact source/delta review
```

**Gate:** M10D definition of done is mechanically established.

---

# 83. M10E handoff

At M10D closure:

```text
M7 exact semantic authority
+
M8 optional captured visual authority
+
M10 approved reusable world
+
M10 effective temporal staging
+
M10 Shot-local camera/blocking/axis
        ↓
ONE SpatialContinuityPack
        ↓
immutable ShotRevision schema 5
        ↓
captured normalized M10 historical rows
```

M10E then begins strictly downstream:

```text
captured M10 authority only
        ↓
pure spatial realization compiler
        ↓
profile/package/manifest spatial capability
        ↓
content-only D0 specs
        ↓
derived immutable Blobs/provenance
        ↓
workflow-spec schema 3
        ↓
worker historical execution
        ↓
Exact Rerun historical Blob reuse
```

M10E may not call the current M10 resolver to reconstruct a historical Generation.

---

# 84. Closure posture

```text
M10A                                      CLOSED
M10B                                      CLOSED
M10C                                      CLOSED
M10C authoritative source                 318ff5c12f4cea870d132bc3f9a8ba3944f866d7

M10D plan revision                        R3
M10D implementation                       NOT AUTHORIZED

M10E                                      NOT AUTHORIZED
M10F                                      NOT AUTHORIZED

publication/tagging                       NOT AUTHORIZED
```

R3 is the pre-authorization contract. Implementation authorization requires the R3 source-fit assertions and acceptance matrix—including items 118–144—to be accepted as the exact implementation target.

**M10D's defining invariant is:**

> **One coherent current read must produce one canonical SpatialContinuityPack, and one schema-5 ShotRevision must preserve that pack without consulting mutable current spatial state ever again.**

