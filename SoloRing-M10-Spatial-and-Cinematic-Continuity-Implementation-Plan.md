# SoloRing M10 — Spatial + Cinematic Continuity Implementation Plan

**Status:** r3 frozen architecture / implementation contract — **IMPLEMENTATION NOT AUTHORIZED**  
**Predecessor baseline:** **M9 @ `36ca78ad3b4c9377f746b31b2db4350b5684fc22`**  
**Predecessor tag:** `M9`  
**Predecessor tree:** `3d81473f8bf40381d5dca7341175a9c445a14be2`  
**Authoritative predecessor artifact:** `SoloRing-M9-r6.zip` — SHA-256 `779e7193e48df907db2b1a9291d92940e17ea0ae7e337d00fb3fae9cce144e7c`  
**Frozen predecessor M9 contract:** SHA-256 `52f3d028a4738b061cc7ab8341abd6b5c078c8f61677e5f160b4a6204197cda6`  
**Authorization boundary:** M10 architecture is frozen by this document. M10A-0, M10A-1, and the §114 final source-fit are completed evidence inputs. **M10 implementation, publication, tagging, branch-protection change, GitHub Release, and post-M10 milestone work remain NOT AUTHORIZED.**

---

---

# r3 integration-resolution record

r2 preserves r1's governing architecture and closes the review defects that could make immutable spatial bytes ambiguous or incomplete. Material changes are:

- exact right-handed world/camera basis and matrix-defined active local→world intrinsic Y-X-Z rotation semantics;
- explicit statement that normalized Euler tuple identity, not physical-equivalence reduction, is authoritative;
- camera pinhole/local-basis contract + mathematical golden fixtures;
- frame-local extent semantics;
- explicit state membership/value for frames **and axes** (`spatial_world_state_axes`), raising migration `0010` to 15 tables;
- stable organizational parent stored on SpatialFrame; no transform inheritance;
- one effective placement authority per Entity plus fixed-frame EntityRevision ↔ Shot EntityRevision validation;
- exact EntityRevision captured in staging history;
- fenced world-capture drift recheck and no revision-number retry hedge;
- exact ShotSpatialPlan create/update/delete CAS cells;
- closed Shot/end blocking handoff for missing/NULL duration;
- arbitrary-precision axis arithmetic and canonical axis ordering;
- exact immutable/current table PK/FK/UNIQUE/CHECK shapes sufficient for ORM/migration parity review;
- fail-closed downgrade preflight + no automatic migration backfill;
- explicit package/profile/manifest/workflow-spec v1/v2/v3 cross-product;
- independent M9 visual + M10 spatial compilers with deterministic composition;
- hard-vs-advisory spatial execution semantics;
- mandatory M10 runtime-fingerprint source-fit and inherited M9 derived-artifact STOP rule;
- expanded requirement/current-revision race suite;
- embedded world snapshot retained intentionally and measured at representative scale;
- form/table authoring UI as schema-1 scope; rich 3D editor deferred;
- authority and realization DoDs tracked separately, while both remain required for M10 milestone closure.

r2 explicitly rejects automatic origin transitions, automatic M7 relation→geometry inference, per-frame interpolation authority, speculative geometry Asset widening, denormalized Shot hashes/caches, arbitrary performance thresholds, and authority-only relabeling of an incomplete M10 milestone.


r3 preserves r2's production-authority architecture and integrates two completed pre-freeze source-fit programs:

```text
M10A-0 frozen procedure
    SHA-256 ee0cd655d15420dd95ac4cc920f6582ca96054ba695f8dd7d3be1aa5ad59e7f2
    execution disposition STOP_DERIVED_ARTIFACT_CONTRACT_REQUIRED

M10A-1 frozen contract
    SHA-256 b286baafab2bcdedf622d114d5ff443720c114e98aa847b423012a46b81719ed
    execution disposition PASS_TO_M10_R3
```

r3 closes the remaining contract seams: historical World requirement capture; workflow-spec/runtime sequencing; exact pinhole projection; immutable semantic keys; complete hash-dependency fencing; a DB placement backstop; permanent SpatialWorldState identity; active-track blocking validation; embedded-plan cross-validation; derived-execution migration `0011`; owner-free Blob provenance; sibling derived Generation inputs; D0-only initial materialization; finite-raster survivability semantics; and a mandatory live/GPU source-fit gate before final freeze.

The previously reported prefix `1667f4d5…` belongs to the **M10A-0** final report, not M10A-1. The completed §114 run subsequently recorded the full exact M10A-0/M10A-1 digests in its external companion evidence tree. Those exact external files are not mounted in this authoring sandbox, so this plan's mechanical certification covers the plan bytes; the §114 evidence bundle remains a separately certified companion record at `C:\AI\M10R3-evidence` with its 91-file `SHA256SUMS`. No full digest is invented or reconstructed from a prefix here.

Derived artifacts remain execution state below M10 authority. No source-fit result transfers authority upward.

---

# 0. Milestone mandate

M10 installs SoloRing's **authoritative spatial and cinematic continuity layer**.

M7 answers:

> What is semantically true at this narrative boundary?

M8 answers:

> What approved visual material defines the required appearance for that exact semantic/design state?

M10 answers:

> Where are the reusable world, staged entities, and camera constraints, and what spatial/cinematic facts must remain stable across shots and viewpoints?

M9 was implemented earlier because the visual-realization path was available first. Milestone numbering does **not** define authority direction. After M10, the governing production flow is:

```text
                         M7 semantic authority
                         /                  \
                        /                    \
               M8 visual authority      M10 spatial/cinematic authority
                        \                    /
                         \                  /
                      immutable ShotRevision capture
                                 ↓
                    model/executor realization layer
                                 ↓
                              executor
```

M10 spatial truth is **above** model-specific realization. A depth map, camera-conditioning tensor, pose control, 3D renderer, mesh, NeRF, Gaussian splat, ControlNet payload, custom Comfy node, or generated frame may realize M10 authority; none of those mechanisms is allowed to redefine it.

The defining invariant is:

> **Spatial facts are production authority. Spatial realization is execution. Execution output never becomes spatial authority automatically.**

---

# 1. Architectural exit criterion

M10 closes only when SoloRing can mechanically prove all of the following for a representative feature-film-scale Project:

1. a reusable Location can have at most one explicit active **SpatialWorld** identity in schema 1;
2. an exact Location `EntityRevision` resolves to an explicitly approved immutable **SpatialWorldRevision** whose frame/axis membership is itself explicit;
3. that revision carries a deterministic metric world graph of stable frame identities, state-specific transforms/extents, state-specific cinematic-axis membership/endpoints, and a completely frozen coordinate/camera convention without depending on a rendering technology;
4. the same canonical M10 bytes have one exact mathematical interpretation across independent implementations; no handedness, local-camera-basis, Euler-composition, axis-sign, extent-space, or arithmetic-width choice is left to an adapter;
5. one story-world Entity cannot acquire two simultaneous M10 placement authorities in the same effective world, and any fixed-frame EntityRevision used by a Shot is mechanically consistent with the exact semantic EntityRevision captured for that Shot;
6. movable dependent Entities resolve random-access effective spatial state from narrative-boundary transitions without replaying prior Shots;
7. a Shot can carry an explicit, validated camera/blocking/cinematic plan tied to the applicable SpatialWorld;
8. persistent Shot-start staging, Shot-local blocking, and any explicit Shot/end persistent transition agree under a closed rule; rendered/UI motion never becomes downstream state implicitly;
9. the current spatial resolver reports readiness before capture/execution and never invents a lower-authority fallback;
10. `ShotRevision` freezes the exact world revision, effective staging including exact active `EntityRevision`, camera/blocking plan, and cinematic constraints used by the render;
11. current world approvals, membership, spatial transitions, Entity revisions, requirements, or Shot-plan edits can create a new future but cannot reinterpret historical ShotRevisions or Generations;
12. Exact Rerun remains a pure durable historical copy and performs zero current M10 authority resolution;
13. when a workflow package claims spatial realization capability, one deterministic compiler produces the captured spatial execution request and the worker translates only explicit captured bindings;
14. when the selected package cannot realize required M10 execution components, Generation creation fails **before queueing** rather than silently ignoring authority or hiding it in prompt text;
15. any new spatial custom node, control model, conversion algorithm, or other materially determinative runtime dependency is either already covered by the captured M9 execution fingerprint or is added to a frozen M10 historical runtime fingerprint before use;
16. any materialized spatial execution bytes obey the separately frozen M10A-1 provenance/determinism/retention/rerun contract; initial M10 permits D0 byte-deterministic derivatives only;
17. feature-film-scale data increases row/byte volume, not SQL round trips per frame/track/world object; the small-vs-representative proof covers current resolution and first Generation persistence;
18. all concurrency proofs are mechanically forced with real Events/barriers at transaction/read/capture seams and contain no sleeps;
19. no M10 execution path writes M7/M8/M10 creative authority as a side effect of generation;
20. M10 makes no false claim that a successful model request guarantees pixel-perfect geometry, interpolation, camera motion, screen direction, arbitrary-view obedience, or distinguishability of spatial deltas below the frozen raster survivability class;
21. the final selected executor path passes live registration + functional GPU smoke before r3 freezes, including exact model/control-weight hashes, required derived-layer capacity, hidden-write audit, and exact media/tensor grammar;
22. complete M10A-0/M10A-1 evidence hashes are mechanically recorded in the final r3 freeze record.

M10's **authority-layer DoD** and **realization-layer DoD** are tracked separately for diagnosis, but both are required for the M10 milestone to close. If M10A cannot prove one explicit viable spatial execution path, authority work may be retained as completed work under separate authorization, but **M10 remains open** and cannot be tagged/published as complete.

---

# 2. Binding Architecture Pattern Register matrix

M10 is governed directly by the following registered patterns:

| Pattern | M10 binding |
|---|---|
| APR-010 | Spatial track state resolves random-access from canonical narrative ordering; no operational replay. |
| APR-011 | Shot/start includes transitions at Shot/start and prior boundaries; Shot/end does not apply to the Shot itself. |
| APR-015 | Spatial readiness is explicit before ShotRevision capture or Generation creation. |
| APR-017 | Ambiguous winning transitions, frame identity conflicts, or duplicate authority fail; UUID/timestamp tie-breakers are forbidden. |
| APR-042 | Any later optimized spatial computation must retain a correctness reference path; schema 1 introduces no risky optimization merely to satisfy this pattern. |
| APR-044 | Current resolution and capture use bounded query classes independent of frame/track cardinality. |
| APR-060 | Semantic production fact remains upstream; spatial realization never defines semantic truth. |
| APR-063 | M10 creates an authoritative representation of relevant stable spatial facts without selecting a mesh/NeRF/Gaussian-splat technology as the authority schema. |
| APR-065 | M10 uses sparse Shot-local keyframes and narrative boundaries; it does **not** create per-frame database state or claim a frame-N interpolation authority contract. |
| APR-068 | Tracking/roto may later measure/propose geometry, but cannot silently write or redefine M10 authority. |

M10 also inherits the established SoloRing house patterns for canonical bytes/hashes, coherent reads, append-only capture, `BEGIN IMMEDIATE` write fencing, CAS-style mutable approval changes, exact-rerun isolation, artifact/source gates, and fail-closed corruption handling.

---

# 3. Frozen predecessor source-fit audit

The M9-published tree is the source-fit baseline for M10. The following facts are mechanically true at `M9 @ 36ca78ad…` and constrain this plan.

### 3.1 Storage/migration baseline

- Alembic head is `0009_m8_visual_identity`.
- There are no `spatial_*` authority tables.
- `ShotRevision` has canonical `snapshot_json/hash` plus M7 continuity columns; M8 visual authority is embedded in snapshot schema 4 and normalized in M8 child tables.
- Therefore M10 has a genuine relational requirement and **does require migration `0010_m10_spatial_cinematic_continuity`**.

### 3.2 Current Shot camera fields are creative text, not spatial authority

`shots` currently stores nullable free-text:

```text
framing
camera_motion
lens
```

These remain creative intent. They are not parsed into geometry, focal length, camera pose, screen direction, or trajectory. M10 must not infer numeric camera authority from them.

### 3.3 Existing semantic state is sufficient to bind spatial state

M7 already provides:

- explicit CreativeEntity identity and exact EntityRevision approval;
- Shot semantic dependencies;
- canonical Project narrative ordering;
- sequence/scene/shot start/end anchors;
- random-access transition resolution;
- immutable capture provenance.

M10 reuses this temporal coordinate system instead of creating a competing timeline.

### 3.4 Existing visual authority remains separate

M8 provides state-specific approved appearance packs. M10 must not put appearance bytes, LoRAs, embeddings, or model-specific image weighting into the spatial authority schema.

A front desk may have:

```text
M8: exact approved visual appearance
M10: exact authoritative position/orientation/extent in the lobby
```

Both are needed; neither substitutes for the other.

### 3.5 Current M9 package has no spatial execution contract

The published M9 Hunyuan package supports visual realization through M8 `entity` / `feature_value` rules. The current manifest/profile grammar has no authoritative camera/world/staging source class.

Therefore M10 may not claim that the existing Hunyuan package enforces spatial authority. A spatial-capable execution contract must be source-fit and explicitly declared before M10 can claim live spatial realization.

### 3.6 Existing Asset provenance is not a generic 3D-artifact registry

`Asset.kind` is currently closed to `reference|output`. M10 schema 1 therefore does **not** smuggle meshes, point clouds, NeRF checkpoints, or other geometry artifacts into existing Asset semantics.

If an implementation source-fit audit proves that a technology-specific geometry artifact is required for the first live M10 executor path, that is a **plan-change event** requiring a separately frozen provenance contract. It is not permission to widen `Asset.kind` ad hoc.

---

# 4. Core semantic distinctions

### SpatialWorld

Stable identity of one authoritative reusable physical world associated with one Location CreativeEntity.

Example:

```text
CreativeEntity: Grand Hotel Lobby (location)
SpatialWorld:   grand-hotel-lobby-world
```

One active SpatialWorld per Location Entity is allowed in schema 1. Location design evolution belongs to `EntityRevision`; spatial layout evolution for an exact Location revision belongs to `SpatialWorldState` + `SpatialWorldRevision`.

### SpatialWorldState

State-specific binding:

```text
SpatialWorld
+ exact Location EntityRevision
→ mutable working world state
→ approved immutable SpatialWorldRevision
```

If Lobby revision 3 becomes revision 4, the approved world for revision 3 does **not** automatically carry forward.

### SpatialFrame

Stable, named coordinate landmark inside one SpatialWorld. Examples:

```text
entrance
front-desk-center
elevator-bank
north-column-03
stair-landing
```

A frame may optionally bind to one fixed story-world Entity identity. Its state-specific frame value may bind the exact EntityRevision of that Entity.

### SpatialTrack

Stable spatial concern for one movable CreativeEntity inside one SpatialWorld. In schema 1 there is at most one active track per `(world_id, entity_id)`.

### SpatialTransition

Narrative-boundary mutation of a SpatialTrack's effective world-space transform. Like M7 FeatureTransition, it is temporal production authority, not animation playback history.

### ShotSpatialPlan

Mutable Shot-local cinematic layout authority containing:

- selected SpatialWorld;
- perspective camera optics;
- sparse exact camera keyframes;
- optional per-track blocking keyframes;
- optional axis-of-action constraint;
- optional explicit screen-direction instruction.

It is not a prompt fragment.

### SpatialContinuityPack

Canonical current/captured authority value combining:

- the exact approved SpatialWorldRevision;
- effective SpatialTrack state at the Shot/start boundary;
- the validated ShotSpatialPlan.

### Spatial realization

A downstream model/executor-specific request compiled from a captured SpatialContinuityPack. It can never mutate the pack or redefine its facts.

---

# 5. One-way authority hierarchy

The final M10 hierarchy is:

```text
M7 semantic identity/state
        ↓
exact Location/Entity revisions
        ↓
┌─────────────────────────┬─────────────────────────┐
│ M8 visual authority     │ M10 spatial authority   │
│ appearance              │ world/layout/camera     │
└─────────────────────────┴─────────────────────────┘
        ↓                         ↓
        └──────── immutable ShotRevision ────────┘
                              ↓
              model-specific realization layer
                              ↓
                           executor
```

Forbidden authority transfers include:

- model-generated depth → automatically becomes SpatialWorld authority;
- camera solve/tracking output → automatically updates ShotSpatialPlan;
- current workflow package → reinterprets historical spatial capture;
- first successful reverse-angle Generation → silently becomes canonical lobby geometry;
- M8 reference ordering → defines physical placement;
- free-text `lens` / `camera_motion` → automatically parsed into M10 numeric state;
- arbitrary M7 Relation predicate → automatically interpreted as geometry.

Tracking, reconstruction, or generation may produce **proposals** for explicit user adoption later. Proposal/adoption is separate from authority.

---

# 6. M10 schema-1 coordinate, transform, and camera contract

M10 requires deterministic coordinates without floating-point identity ambiguity. This section is load-bearing: once schema-5 history exists, no executor or UI may reinterpret these bytes.

### 6.1 Global world basis

Schema 1 freezes:

```text
handedness: right-handed
+X: world right
+Y: world up
+Z: world back/depth-positive
canonical world forward: -Z
linear unit: millimeter
rotation representation: yaw/pitch/roll integer microdegrees
```

`forward` is never used as an ambiguous axis alias in canonical bytes. The canonical world basis is exactly `(+X,+Y,+Z)` above.

All transforms are **absolute world-space poses**. Frame parent relationships are organizational only and never participate in matrix composition in schema 1.

### 6.2 Exact rotation mathematics

Canonical rotation tuple:

```text
rotation_udeg = [yaw_udeg, pitch_udeg, roll_udeg]
```

Semantics are frozen as:

```text
vector convention: column vectors
rotation action: active
pose direction: local → world
Euler family: intrinsic Y-X-Z Tait-Bryan sequence
positive angle: right-hand rule about the positive local axis of that intrinsic step
matrix: R = Ry(yaw) · Rx(pitch) · Rz(roll)
world point from local point: p_world = R · p_local + t
```

The reference matrices are:

```text
Ry(a) = [[ cos a, 0, sin a],
         [     0, 1,     0],
         [-sin a, 0, cos a]]

Rx(a) = [[1,      0,       0],
         [0,  cos a, -sin a],
         [0,  sin a,  cos a]]

Rz(a) = [[ cos a, -sin a, 0],
         [ sin a,  cos a, 0],
         [     0,      0, 1]]
```

The matrix formula defines meaning. Prose order is explanatory only.

### 6.3 Camera-local basis

A camera transform uses the same local→world pose convention.

At identity rotation:

```text
camera local +X = image right
camera local +Y = image up
camera local -Z = optical/view forward
camera local +Z = behind camera
```

Therefore an identity camera at the origin looks toward world `-Z`.

Schema 1 camera projection is an ideal pinhole perspective camera with:

```text
focal_length_um  > 0 integer
sensor_width_um  > 0 integer
sensor_height_um > 0 integer
```

No lens distortion, sensor shift, anamorphic squeeze, focus distance, depth of field, shutter model, or rolling shutter is authoritative in schema 1. Adding any of those later is a versioned camera-schema change.

For camera-local `P=[x,y,z]^T`, ideal projection is defined only for `z < 0`:

```text
sensor_x_um = focal_length_um * x / (-z)
sensor_y_um = focal_length_um * y / (-z)
principal point = sensor center
skew = 0
```

`z == 0` and `z > 0` are not projectable. Raster dimensions/origin/pixel-center semantics are execution-derivation parameters captured in `DerivedSpatialArtifactSpec`, never camera authority.

### 6.4 Canonical integer transform

```json
{
  "translation_mm": [1200, 0, -3500],
  "rotation_udeg": [90000000, 0, 0]
}
```

All six values are signed JSON integers within the JavaScript-safe integer domain. No floats, NaN, Infinity, exponent strings, decimal strings, unit aliases, implicit degrees, or implicit meters are accepted.

Each rotation component is normalized independently into:

```text
[-180000000, +180000000)
```

Thus exactly `+180000000` canonicalizes to `-180000000`.

The normalized integer tuple itself is authoritative. SoloRing **does not claim physical-orientation equivalence canonicalization** across distinct accepted Euler tuples. If two distinct tuples map to the same physical orientation, they remain different authored authority and may hash differently. This avoids pretending that gimbal-equivalence reduction exists when schema 1 has not frozen such an algorithm.

### 6.5 Optional extents

A state-specific frame value may carry:

```json
"half_extents_mm": [1800, 600, 500]
```

or `null`.

Each extent must be a strictly positive integer. The triple is interpreted as **frame-local half dimensions centered at the frame origin**. Together with the frame's absolute orientation it defines an oriented coarse occupancy box. Extents are not a world-axis-aligned AABB and are not surface geometry, collision geometry, or appearance.

Millimeter precision is deliberate for schema-1 coarse spatial authority. Finer surface/prop geometry is outside this schema rather than encoded by changing authority units opportunistically.

### 6.6 No scale transform

Schema 1 defines no transform scale. Physical size is represented through authored dimensions/extents or a future geometry-authority schema, never by an executor-dependent scale matrix.

### 6.7 Golden mathematical fixtures

Before migration/ORM implementation is accepted, one shared backend/frontend fixture file pins at minimum:

1. identity pose: local camera forward `[0,0,-1]` → world `[0,0,-1]`;
2. yaw `+90°`: exact expected world basis under `R=Ry·Rx·Rz`;
3. yaw `-90°`;
4. pitch `+90°` and `-90°` as accepted authored tuples with exact matrix expectations;
5. roll `+90°`;
6. one combined non-commuting yaw/pitch/roll case;
7. `+180° → -180°` tuple normalization;
8. two physically equivalent-but-numerically-distinct Euler tuples remain distinct canonical authority if such a pair is admitted;
9. one camera-space point projected under the pinhole convention;
10. one extent corner transformed from frame-local to world coordinates.

Tests may use floating trigonometry only to verify these known fixture matrices within test-only numeric tolerance. Production identity/hashing never uses floating matrix bytes.

---

# 7. Migration 0010 — frozen relational contract

M10 introduces **`0010_m10_spatial_cinematic_continuity`**. It creates new tables/indexes only; it does not rebuild populated predecessor tables merely to add milestone symmetry.

r3 retains **15** authority tables because frame/axis membership is explicit per `SpatialWorldState`:

```text
spatial_worlds
spatial_world_states
spatial_frames
spatial_world_state_frames
spatial_axes
spatial_world_state_axes
spatial_world_revisions
spatial_world_revision_frames
spatial_world_revision_axes
spatial_tracks
spatial_transitions
shot_spatial_plans
shot_revision_spatial_worlds
shot_revision_spatial_track_states
shot_revision_spatial_plans
```

No M10 authority column is added to `shots`, `shot_revisions`, `generations`, `assets`, or M7/M8 authority tables. Shot M10 authority history is carried by canonical JSON plus normalized M10 child rows.

Derived execution provenance is isolated in migration `0011_m10_derived_spatial_execution` (§102), keeping migration `0010` authority-only.

### 7.1 Exact mutable/current table shapes

#### `spatial_worlds`

```text
id                  String(36) PK
project_id          String(36) NOT NULL FK projects.id RESTRICT
location_entity_id  String(36) NOT NULL FK creative_entities.id RESTRICT
key                 TEXT NOT NULL
name                TEXT NOT NULL
description         TEXT NULL
requirement         TEXT NOT NULL CHECK required|optional
created_at          TEXT NOT NULL
updated_at          TEXT NOT NULL
deleted_at          TEXT NULL
```

Constraints/index intent:

```text
UNIQUE(project_id, key)                         -- tombstone-inclusive
UNIQUE(location_entity_id) WHERE deleted_at IS NULL
INDEX(project_id, deleted_at)
INDEX(location_entity_id, deleted_at)
```

#### `spatial_world_states`

```text
id                           String(36) PK
spatial_world_id             String(36) NOT NULL FK spatial_worlds.id RESTRICT
location_entity_revision_id  String(36) NOT NULL FK entity_revisions.id RESTRICT
approved_revision_id         String(36) NULL FK spatial_world_revisions.id RESTRICT
created_at                   TEXT NOT NULL
updated_at                   TEXT NOT NULL
```

Identity is permanent and unique:

```text
UNIQUE(spatial_world_id, location_entity_revision_id)
INDEX(spatial_world_id)
INDEX(approved_revision_id)
```

There is no schema-1 state tombstone lifecycle; the exact world/revision identity remains addressable permanently.

#### `spatial_frames`

```text
id                       String(36) PK
spatial_world_id         String(36) NOT NULL FK spatial_worlds.id RESTRICT
key                      TEXT NOT NULL
name                     TEXT NOT NULL
parent_spatial_frame_id  String(36) NULL FK spatial_frames.id RESTRICT
bound_entity_id          String(36) NULL FK creative_entities.id RESTRICT
created_at               TEXT NOT NULL
updated_at               TEXT NOT NULL
deleted_at               TEXT NULL
```

```text
UNIQUE(spatial_world_id, key)   -- tombstone-inclusive
INDEX(spatial_world_id, deleted_at)
INDEX(bound_entity_id)
```

Parent identity is stable world-level organizational metadata. It never composes transforms.

#### `spatial_world_state_frames`

This table is simultaneously **state membership** and the mutable value for an included frame:

```text
spatial_world_state_id      String(36) NOT NULL FK spatial_world_states.id RESTRICT
spatial_frame_id            String(36) NOT NULL FK spatial_frames.id RESTRICT
bound_entity_id             String(36) NULL FK creative_entities.id RESTRICT
bound_entity_revision_id    String(36) NULL FK entity_revisions.id RESTRICT
x_mm y_mm z_mm              INTEGER NOT NULL
yaw_udeg pitch_udeg roll_udeg INTEGER NOT NULL
half_x_mm half_y_mm half_z_mm INTEGER NULL
updated_at                  TEXT NOT NULL
PRIMARY KEY(spatial_world_state_id, spatial_frame_id)
UNIQUE(spatial_world_state_id, bound_entity_id)
    WHERE bound_entity_id IS NOT NULL
```

Checks:

```text
(bound_entity_id IS NULL AND bound_entity_revision_id IS NULL)
OR
(bound_entity_id IS NOT NULL AND bound_entity_revision_id IS NOT NULL)

all half-extents NULL
OR all three > 0
```

Service validation requires `bound_entity_id` to equal the stable SpatialFrame binding and `bound_entity_revision_id` to belong to that exact Entity. The denormalized identity exists solely to make the one-fixed-placement-per-Entity rule race-proof at the DB layer.

All transform/range rules requiring JavaScript-safe integer validation are service/schema rules because SQLite INTEGER CHECKs alone do not prove the JSON-domain contract.

#### `spatial_axes`

Stable axis identity only:

```text
id               String(36) PK
spatial_world_id String(36) NOT NULL FK spatial_worlds.id RESTRICT
key              TEXT NOT NULL
name             TEXT NOT NULL
created_at       TEXT NOT NULL
updated_at       TEXT NOT NULL
deleted_at       TEXT NULL
UNIQUE(spatial_world_id, key)    -- tombstone-inclusive
INDEX(spatial_world_id, deleted_at)
```

#### `spatial_world_state_axes`

This is explicit state membership plus state-specific endpoint selection:

```text
spatial_world_state_id String(36) NOT NULL
spatial_axis_id        String(36) NOT NULL
a_frame_id             String(36) NOT NULL
b_frame_id             String(36) NOT NULL
updated_at             TEXT NOT NULL
PRIMARY KEY(spatial_world_state_id, spatial_axis_id)
CHECK(a_frame_id <> b_frame_id)
FK spatial_world_state_id → spatial_world_states.id RESTRICT
FK spatial_axis_id        → spatial_axes.id RESTRICT
FK (spatial_world_state_id, a_frame_id)
   → spatial_world_state_frames(spatial_world_state_id, spatial_frame_id) RESTRICT
FK (spatial_world_state_id, b_frame_id)
   → spatial_world_state_frames(spatial_world_state_id, spatial_frame_id) RESTRICT
```

The composite endpoint FKs mechanically prevent a state axis from targeting a frame absent from that same state.

#### `spatial_tracks`

```text
id               String(36) PK
spatial_world_id String(36) NOT NULL FK spatial_worlds.id RESTRICT
entity_id        String(36) NOT NULL FK creative_entities.id RESTRICT
requirement      TEXT NOT NULL CHECK required|optional
created_at       TEXT NOT NULL
updated_at       TEXT NOT NULL
deleted_at       TEXT NULL
UNIQUE(spatial_world_id, entity_id) WHERE deleted_at IS NULL
INDEX(spatial_world_id, deleted_at)
INDEX(entity_id, deleted_at)
```

#### `spatial_transitions`

```text
id               String(36) PK
spatial_track_id String(36) NOT NULL FK spatial_tracks.id RESTRICT
anchor_type      TEXT NOT NULL CHECK sequence|scene|shot
anchor_id        String(36) NOT NULL
boundary         TEXT NOT NULL CHECK start|end
operation        TEXT NOT NULL CHECK set|clear
x_mm y_mm z_mm   INTEGER NULL
yaw_udeg pitch_udeg roll_udeg INTEGER NULL
created_at       TEXT NOT NULL
updated_at       TEXT NOT NULL
deleted_at       TEXT NULL
```

DB CHECK freezes transform nullability:

```text
operation='set'   → all six transform columns NOT NULL
operation='clear' → all six transform columns NULL
```

```text
UNIQUE(spatial_track_id, anchor_type, anchor_id, boundary)
    WHERE deleted_at IS NULL
INDEX(spatial_track_id, deleted_at)
INDEX(anchor_type, anchor_id, boundary, deleted_at)
```

Polymorphic anchor ownership/topology is service-validated against the same Project.

#### `shot_spatial_plans`

```text
shot_id           String(36) PK FK shots.id RESTRICT
spatial_world_id  String(36) NOT NULL FK spatial_worlds.id RESTRICT
plan_json         TEXT NOT NULL
plan_hash         TEXT NOT NULL CHECK length(plan_hash)=64
created_at        TEXT NOT NULL
updated_at        TEXT NOT NULL
INDEX(spatial_world_id)
```

There is no tombstone row. Current-plan delete removes this mutable row only; immutable ShotRevision history remains.

### 7.2 Exact immutable table shapes

#### `spatial_world_revisions`

```text
id                       String(36) PK
spatial_world_state_id   String(36) NOT NULL FK spatial_world_states.id RESTRICT
revision_number          INTEGER NOT NULL CHECK revision_number > 0
snapshot_json            TEXT NOT NULL
snapshot_hash            TEXT NOT NULL CHECK length(snapshot_hash)=64
created_at               TEXT NOT NULL
UNIQUE(spatial_world_state_id, revision_number)
UNIQUE(spatial_world_state_id, snapshot_hash)
INDEX(spatial_world_state_id)
```

No update/delete API exists.

#### `spatial_world_revision_frames`

```text
spatial_world_revision_id String(36) NOT NULL FK spatial_world_revisions.id RESTRICT
position                  INTEGER NOT NULL CHECK position >= 0
spatial_frame_id          String(36) NOT NULL FK spatial_frames.id RESTRICT
frame_key                 TEXT NOT NULL
parent_spatial_frame_id   String(36) NULL FK spatial_frames.id RESTRICT
bound_entity_id           String(36) NULL FK creative_entities.id RESTRICT
bound_entity_revision_id  String(36) NULL FK entity_revisions.id RESTRICT
x_mm y_mm z_mm            INTEGER NOT NULL
yaw_udeg pitch_udeg roll_udeg INTEGER NOT NULL
half_x_mm half_y_mm half_z_mm INTEGER NULL
PRIMARY KEY(spatial_world_revision_id, position)
UNIQUE(spatial_world_revision_id, spatial_frame_id)
UNIQUE(spatial_world_revision_id, frame_key)
```

The same all-null/all-positive extent CHECK applies.

#### `spatial_world_revision_axes`

```text
spatial_world_revision_id String(36) NOT NULL FK spatial_world_revisions.id RESTRICT
position                  INTEGER NOT NULL CHECK position >= 0
spatial_axis_id           String(36) NOT NULL FK spatial_axes.id RESTRICT
axis_key                  TEXT NOT NULL
a_frame_id                String(36) NOT NULL
b_frame_id                String(36) NOT NULL
PRIMARY KEY(spatial_world_revision_id, position)
UNIQUE(spatial_world_revision_id, spatial_axis_id)
UNIQUE(spatial_world_revision_id, axis_key)
CHECK(a_frame_id <> b_frame_id)
FK (spatial_world_revision_id, a_frame_id)
   → spatial_world_revision_frames(spatial_world_revision_id, spatial_frame_id) RESTRICT
FK (spatial_world_revision_id, b_frame_id)
   → spatial_world_revision_frames(spatial_world_revision_id, spatial_frame_id) RESTRICT
```

#### `shot_revision_spatial_worlds`

Exactly one row exists for every schema-5 ShotRevision and zero rows for schemas 1–4:

```text
shot_revision_id             String(36) PK FK shot_revisions.id RESTRICT
spatial_continuity_hash       TEXT NOT NULL CHECK length(...)=64
spatial_world_id              String(36) NOT NULL FK spatial_worlds.id RESTRICT
spatial_world_state_id        String(36) NOT NULL FK spatial_world_states.id RESTRICT
spatial_world_revision_id     String(36) NOT NULL FK spatial_world_revisions.id RESTRICT
spatial_world_revision_hash   TEXT NOT NULL CHECK length(...)=64
location_entity_id            String(36) NOT NULL FK creative_entities.id RESTRICT
location_entity_revision_id   String(36) NOT NULL FK entity_revisions.id RESTRICT
requirement                   TEXT NOT NULL CHECK required|optional
```

#### `shot_revision_spatial_track_states`

```text
shot_revision_id      String(36) NOT NULL FK shot_revisions.id RESTRICT
position              INTEGER NOT NULL CHECK position >= 0
spatial_track_id      String(36) NOT NULL FK spatial_tracks.id RESTRICT
entity_id             String(36) NOT NULL FK creative_entities.id RESTRICT
entity_revision_id    String(36) NOT NULL FK entity_revisions.id RESTRICT
requirement           TEXT NOT NULL CHECK required|optional
x_mm y_mm z_mm        INTEGER NOT NULL
yaw_udeg pitch_udeg roll_udeg INTEGER NOT NULL
source_transition_id String(36) NOT NULL FK spatial_transitions.id RESTRICT
source_anchor_type    TEXT NOT NULL CHECK sequence|scene|shot
source_anchor_id      String(36) NOT NULL
source_boundary       TEXT NOT NULL CHECK start|end
PRIMARY KEY(shot_revision_id, position)
UNIQUE(shot_revision_id, spatial_track_id)
```

The requirement value is captured at ShotRevision time; later requirement flips do not rewrite history.

#### `shot_revision_spatial_plans`

Exactly one row exists for every schema-5 ShotRevision:

```text
shot_revision_id String(36) PK FK shot_revisions.id RESTRICT
plan_hash        TEXT NOT NULL CHECK length(plan_hash)=64
plan_json        TEXT NOT NULL
```

The row is a normalized integrity projection of `spatial_continuity.shot_plan`, not a current-plan reference. Historical read/reuse requires canonical equality between the embedded plan and `plan_json`, plus `SHA-256(plan_json) == plan_hash`; disagreement is corruption.

### 7.3 ORM/migration parity gate

The ORM and hand-written migration must have exact table, index, FK, UNIQUE, partial-UNIQUE, CHECK, nullability, and on-delete parity under strict metadata comparison. The parity gate explicitly proves that revision-axis composite FKs target the declared UNIQUE `(spatial_world_revision_id, spatial_frame_id)` key rather than assuming the target is the table PK. Schema source-fit may change physical index names before freeze only if both ORM and migration names are changed together and the semantic constraints above remain exact.

### 7.4 Downgrade is fail-closed

`0010 → 0009` must run a complete preflight **before any DDL** and refuse if M10 cannot be proven unused.

At minimum refusal occurs when:

- any M10 table contains any row, including soft-deleted rows;
- any `shot_revisions.snapshot_json` is malformed/unreadable or declares schema version `>=5`;
- any `generations.workflow_spec_json` is malformed/unreadable or declares workflow-spec schema version `>=3`.

Only a provably unused M10 schema may be dropped in reverse dependency order. M10 production authority/history is never intentionally destroyed by downgrade.

### 7.5 Existing-data/backfill rule

Migration `0010` creates **no automatic SpatialWorld, state, frame, track, transition, plan, or schema-5 history** for existing projects.

Existing Shots remain behaviorally unchanged when no applicable M10 authority has been authored:

```text
spatial_continuity_ready = true
spatial_continuity_hash  = null
new ShotRevision follows exact predecessor schema 1–4 lattice
```

When production deliberately authors a `required` world or track, affected future readiness may begin blocking. That is an explicit production-policy change, not migration backfill. Base M10 includes no bulk auto-authoring or fabricated origin transitions.

---

# 8. `spatial_worlds` authority contract

A SpatialWorld is a stable reusable spatial-authority identity for exactly one Location CreativeEntity.

Creation/update invariants:

- owning Entity is active, same Project, and kind `location`;
- `key` is immutable after creation; `name`/`description` remain mutable display metadata;
- at most one active SpatialWorld per Location in schema 1;
- `(project_id,key)` is tombstone-inclusive and never recycled;
- `requirement` is exactly `required|optional`;
- changing `requirement` is an explicit production-policy edit included in current-read race proofs;
- a required world cannot be deleted directly: production must explicitly change it to optional first, then satisfy ordinary deletion guards;
- optional-world deletion is blocked while an active ShotSpatialPlan selects it or other active current references would become dangling;
- historical rows remain pinned by restrictive FKs.

Semantics:

```text
required
→ if this Location is a current Shot semantic dependency, a coherent M10 world/plan is required

optional
→ the world contributes M10 authority only when a ShotSpatialPlan explicitly selects it
```

Schema 1 accepts the product consequence that a Shot with more than one applicable **required** Location world is blocked as `SPATIAL_CONTEXT_AMBIGUOUS`. There is no primary-location heuristic and no per-Shot weakening of a required world. Multi-world composite Shots are deferred.

---

# 9. `spatial_world_states` contract

A SpatialWorldState binds one exact Location `EntityRevision` to mutable working spatial membership/values and one explicit approved immutable revision.

Creation validates:

```text
EntityRevision.entity_id == SpatialWorld.location_entity_id
EntityRevision and SpatialWorld belong to the same Project
```

Same-Project-but-wrong-Entity and cross-Project bindings are invalid.

The `(world, location revision)` identity is unique tombstone-inclusively. A Location revision change never auto-creates or auto-approves another state.

Schema 1 has no ordinary SpatialWorldState delete/recreate lifecycle. The state row is permanent identity; membership and approval may change under their explicit contracts.

The approval pointer is mutable production state changed only through expected-pointer CAS under `BEGIN IMMEDIATE`.

State membership is **explicit**:

- an included frame exists only because a `spatial_world_state_frames` row exists;
- an included axis exists only because a `spatial_world_state_axes` row exists;
- absence means absence, not defaulting, inheritance, or an invalid-but-assumed value.

This closes the r1 ambiguity over whether every world-level frame/axis implicitly belonged to every Location revision.

---

# 10. SpatialFrame identity and state membership/value

### 10.1 Stable `spatial_frames`

A SpatialFrame is a stable named landmark identity inside one SpatialWorld.

Stable fields include:

```text
world
key/name
optional parent_spatial_frame_id
optional bound_entity_id
```

`SpatialFrame.key` is immutable after creation; `name` is mutable display metadata. A former key is never reassigned to a different frame identity.

`parent_spatial_frame_id` is organizational metadata only. The world-level parent graph must be acyclic; parent != child; parent belongs to the same SpatialWorld. Parent changes may create a different future SpatialWorldRevision because the immutable graph records organizational provenance, but **never** alter transform mathematics through composition.

A frame may bind one fixed story-world Entity identity. Cross-Project bound Entities are rejected.

### 10.2 `spatial_world_state_frames` = explicit membership + state-specific value

A frame participates in one Location revision only when its state-frame row exists.

The state value carries:

```text
exact bound_entity_id + bound_entity_revision_id when the stable frame binds an Entity
absolute world transform
optional frame-local half extents
```

Rules:

- frame and state belong to the same SpatialWorld;
- if the stable frame has a parent, an included child requires that parent to be included in the same state;
- if the stable frame binds an Entity, state `bound_entity_id` equals that stable binding and `bound_entity_revision_id` is non-NULL and belongs to exactly that Entity;
- if the stable frame has no bound Entity, both state binding columns are NULL;
- no frame or bound revision is synthesized from M7/M8 state;
- frame capture ordering is exactly `(frame.key, frame.id)`.

### 10.3 One placement authority per Entity

Schema 1 does not support two simultaneous instances of one CreativeEntity identity.

For any effective approved world used by a Shot:

- at most one included frame may bind a given `bound_entity_id`;
- if an included frame binds Entity E, there must not also be an applicable active SpatialTrack for Entity E in that same effective world;
- multiple fixed-frame bindings or frame+track placement for the same Entity are `SPATIAL_ENTITY_PLACEMENT_CONFLICT`.

The constraint is evaluated against effective state, not globally across all Location revisions, so an Entity may be fixed in one world state and movable in another without inventing a duplicate identity.

### 10.4 Exact EntityRevision cross-check at Shot resolution

If an included fixed frame's bound Entity is a current Shot semantic dependency:

```text
frame.bound_entity_revision_id
==
Shot's resolved exact EntityRevision for that Entity
```

Mismatch is `SPATIAL_ENTITY_REVISION_MISMATCH` and blocks current capture/generation. If the bound Entity is not a Shot semantic dependency, the captured frame revision remains valid world-internal provenance and is not silently substituted.

---

# 11. Cinematic axes

`SpatialAxis` is a stable cinematic-axis identity. Endpoint membership is state-specific through `spatial_world_state_axes`.

`SpatialAxis.key` is immutable after creation; `name` is mutable display metadata. Two distinct named axes may intentionally share endpoint geometry; named identity is not collapsed by endpoint equality.

For one state-axis row:

```text
a_frame_id != b_frame_id
both endpoint frames are explicitly included in the same SpatialWorldState
axis identity and state belong to the same SpatialWorld
```

Capture ordering is exactly:

```text
(axis.key, axis.id)
```

### 11.1 Ground-plane side predicate

Schema 1 deliberately uses the world X/Z ground plane only.

For axis endpoints A and B and camera world position C:

```text
cross = (Bx-Ax)*(Cz-Az) - (Bz-Az)*(Cx-Ax)
```

Evaluation occurs in **server-side arbitrary-precision integer arithmetic**. It must not be delegated to SQLite INTEGER multiplication, JavaScript `Number`, float32, or float64.

```text
cross > 0 → positive
cross < 0 → negative
cross = 0 → on-axis and therefore violates either side constraint
```

No physical "left"/"right" synonym is canonicalized into the stored sign. The positive/negative labels are defined by the equation and golden numeric fixture.

An included axis is invalid if its endpoint X/Z positions coincide. Schema 1 imposes no additional arbitrary minimum axis length: millimeter-distinct endpoints are deterministic authority, though UI may warn about near-degenerate authoring without changing readiness.

Golden fixture:

```text
A = [0,0,0]
B = [1000,0,0]
C = [0,0,1000]
→ cross = +1_000_000
→ positive
```

### 11.2 Schema-1 axis limitation

Axis endpoints are fixed SpatialFrames from the approved world revision. An axis whose endpoints follow moving SpatialTracks is **not representable** in schema 1. Dynamic-endpoint axes require a future versioned spatial/cinematic schema; the base implementation must not infer them from character tracks.

---

# 12. Working world capture → SpatialWorldRevision

A SpatialWorldRevision is an immutable canonical capture of one exact `SpatialWorldState` membership/value graph.

Capture uses a two-phase compare-and-freeze contract:

1. coherent read transaction loads **every hash-bearing dependency**: world/state identity; included state-frame rows; stable frame key/parent/bound-Entity metadata; bound EntityRevision identities; included state-axis rows; stable axis keys; endpoints; and validation dependencies;
2. validate complete membership, parent inclusion, ownership, endpoints, one-placement rules, transforms/extents, and canonical order;
3. freeze the complete candidate in memory;
4. canonicalize and hash;
5. enter `BEGIN IMMEDIATE`;
6. reread the exact same hash-bearing dependency set under the fenced writer;
7. rebuild/re-hash the entire current canonical candidate;
8. if current hash differs from frozen hash, abort `SPATIAL_WORLD_CAPTURE_CONFLICT`; no auto-retry and no BEFORE/AFTER choice;
9. converge on existing `(state_id,snapshot_hash)` only after stored-byte/child validation;
10. otherwise allocate `MAX(revision_number)+1`, insert revision + normalized children, commit.

Writer serialization makes a revision-number collision an `INTERNAL_INVARIANT_VIOLATION`, not a timestamp/retry winner.


---

# 13. SpatialWorldRevision canonical schema 1

Canonical value:

```json
{
  "schema_version": 1,
  "spatial_world_id": "...",
  "location_entity_id": "...",
  "location_entity_revision_id": "...",
  "coordinate_system": {
    "handedness": "right",
    "right_axis": "+x",
    "up_axis": "+y",
    "depth_positive_axis": "+z",
    "forward_axis": "-z",
    "linear_unit": "millimeter",
    "rotation_unit": "microdegree",
    "rotation_semantics": "active_local_to_world_intrinsic_yxz",
    "vector_convention": "column",
    "camera_forward_axis": "-z"
  },
  "frames": [
    {
      "spatial_frame_id": "...",
      "frame_key": "front-desk-center",
      "parent_spatial_frame_id": null,
      "bound_entity_id": null,
      "bound_entity_revision_id": null,
      "transform": {
        "translation_mm": [0, 0, 4200],
        "rotation_udeg": [0, 0, 0]
      },
      "half_extents_mm": [2200, 600, 550]
    }
  ],
  "axes": [
    {
      "spatial_axis_id": "...",
      "axis_key": "desk-conversation-axis",
      "a_frame_id": "...",
      "b_frame_id": "..."
    }
  ]
}
```

Canonical arrays are sorted before serialization:

```text
frames → (frame_key, spatial_frame_id)
axes   → (axis_key, spatial_axis_id)
```

The exact stored `snapshot_json` bytes are the exact hashed bytes. Names/descriptions/timestamps/approval pointers are excluded from canonical identity; stable semantic keys and exact authority/provenance identities are included.

The full coordinate-system declaration is hash-bearing. A future transform convention therefore cannot silently reinterpret an old revision; it requires a new schema.

---

# 14. SpatialWorldRevision immutable child projection

Normalized immutable child tables are written from the **same in-memory canonical value** as `snapshot_json`.

`spatial_world_revision_frames` carries canonical position, frame identity/key, stable parent, bound Entity/revision, transform integers, and optional extents.

`spatial_world_revision_axes` carries canonical position, axis identity/key, and exact endpoint frame identities.

On identical-revision convergence/reuse, implementation must verify before returning the existing revision that:

1. stored `snapshot_json` hashes to stored `snapshot_hash`;
2. stored `snapshot_json` bytes equal the candidate canonical bytes for that hash;
3. normalized frame/axis rows exactly project the stored canonical snapshot, including positions;
4. axis endpoint child rows reference frame child rows present in the same revision.

Any mismatch is:

```text
INTERNAL_INVARIANT_VIOLATION
```

Never repair, recapture under a new number, or silently replace corrupted immutable history.

Mandatory corruption proof:

```text
capture
→ corrupt immutable snapshot or child projection
→ identical capture/reuse fails invariant
→ restore exact bytes/row
→ positive-control reuse converges to same revision id
```

---

# 15. World approval / unapproval

Approval is explicit and state-specific:

```text
SpatialWorldState.approved_revision_id
```

Approval request carries:

```text
revision_id
expected_approved_revision_id
```

and executes under `BEGIN IMMEDIATE`.

Semantics:

- target revision must belong to the exact state;
- approving an already-current revision is idempotent if the requested revision equals current, before stale-expected rejection;
- otherwise the current pointer must equal `expected_approved_revision_id` exactly, including NULL;
- one serialized expected-pointer transition wins;
- stale expected pointer → `SPATIAL_WORLD_APPROVAL_CONFLICT`;
- unapproval uses the same expected-current contract and may intentionally make current Shots unready;
- no approval operation mutates immutable revision bytes or historical ShotRevisions.

The implementation may use select+compare+update under the fenced transaction or an equivalent conditional UPDATE, but the externally visible CAS semantics above are exact and fixture-pinned.

---

# 16. SpatialTrack contract

A `SpatialTrack` declares persistent narrative spatial state for one movable CreativeEntity inside one SpatialWorld.

Schema 1 active uniqueness is:

```text
(spatial_world_id, entity_id)
```

A second active track request for the same Entity/world is rejected deterministically as `SPATIAL_ENTITY_INSTANCING_UNSUPPORTED`; the partial unique index is the race-proof backstop and raw database errors must be translated.

This deliberately means a single CreativeEntity identity cannot stand for two simultaneous copies. Productions needing twins/copies/duplicate props must use distinct story-world Entity identities or a future instance schema.

Track creation/update validates same Project ownership. `requirement` is `required|optional` and changing it is an explicit production-policy mutation covered by race proofs.

A required track cannot be deleted directly; downgrade it explicitly to optional first, then remove/tombstone active transitions and satisfy ordinary reference guards.

Track requirement contributes readiness only when:

```text
track Entity is a current Shot semantic dependency
AND
track world is the selected applicable SpatialWorld
```

At current Shot resolution, an active track for Entity E conflicts with an included fixed frame binding E in the selected approved world revision (`SPATIAL_ENTITY_PLACEMENT_CONFLICT`).

---

# 17. SpatialTransition contract

`spatial_transitions` mirrors M7's random-access temporal pattern.

Shape:

```text
set   → all six transform columns NOT NULL
clear → all six transform columns NULL
```

Active uniqueness:

```text
(track_id, anchor_type, anchor_id, boundary)
```

Anchors are validated against the same Project and canonical narrative topology.

Temporal inclusion is exactly the M7 rule:

```text
transition_rank <= target Shot/start rank
```

Therefore:

- target Shot/start applies to that Shot;
- target Shot/end does not;
- prior Shot/end applies downstream.

Sequence/scene/shot boundary ranks are shared with the M7 canonical rank implementation; M10 must not reimplement a subtly different ordering function.

The inherited Project-local boundary stream is exactly:

```text
for Sequence ordered by position:
    Sequence/start
    for Scene in Sequence ordered by position:
        Scene/start
        for active assigned Shot ordered by scene_position:
            Shot/start
            Shot/end
        Scene/end
    Sequence/end
```

Ranks are monotonically assigned in that emission order. Therefore Scene/start strictly precedes its first Shot/start, Shot/start strictly precedes that Shot/end, and child ends strictly precede container end; ties do not exist. Boundary-coincident transition fixtures must prove this inherited ordering rather than inventing an M10 rank model.

Equivalent winning-rank multiplicity is corruption. The active unique index prevents same-coordinate duplicates in normal writes, and source-gate corruption fixtures prove there is no ID/timestamp tie-break.

Authoring guidance: boundary-coincident coordinates that would be semantically redundant or confusing (for example a Scene/start and its first Shot/start for the same track) are legal only if the canonical rank model distinguishes them; production should prefer one explicit transition at the intended boundary. No resolver visitation order supplies a winner.

---

# 18. Random-access effective spatial-state resolver

ONE resolver computes effective staging for a target Shot inside the caller's coherent read transaction.

Input:

```text
Shot id
selected SpatialWorld
M7 semantic dependency identities + exact EntityRevisions
canonical narrative ordering
active SpatialTracks + requirements
active SpatialTransitions
```

Algorithm:

1. deduplicate dependent Entity identities and retain each exact current `EntityRevision`;
2. load active tracks in the selected world for those identities in one set-oriented query;
3. load active transitions for those tracks in one set-oriented query;
4. if relevant transition data exists and the Shot lacks narrative position, return inherited `NARRATIVE_CONTEXT_REQUIRED`;
5. rank through the shared canonical M7 narrative rank function;
6. choose the single highest eligible transition per track;
7. `set` → effective transform; `clear`/no winner → absent;
8. required track with no effective `set` → `SPATIAL_TRACK_STATE_REQUIRED`;
9. optional track with no effective `set` → canonical absence;
10. for every effective state, attach the exact current semantic `entity_revision_id` from step 1;
11. validate no effective track duplicates fixed-frame placement for the same Entity in the selected approved world;
12. sort captured effective states by `(entity_id, spatial_track_id)`.

The resolver never operationally visits earlier Shots and never reads a current Entity revision after the coherent semantic/spatial snapshot is pinned.

---

# 19. ShotSpatialPlan storage and CAS lifecycle

M10 stores one mutable canonical plan document per Shot in `shot_spatial_plans`.

The plan is validated/canonicalized server-side and:

```text
plan_hash = SHA-256(canonical_json(plan))
```

Clients never author `plan_hash`.

### 19.1 Exact CAS cells

PUT create:

```text
expected_plan_hash = null
no existing plan   → create
existing plan      → SPATIAL_SHOT_PLAN_CONFLICT
```

PUT update:

```text
expected_plan_hash = exact current hash → replace atomically
anything else                          → conflict
```

DELETE existing:

```text
expected_plan_hash is required and must equal exact current hash
stale/null mismatch → conflict
```

DELETE nonexistent:

```text
expected_plan_hash = null     → idempotent 204/no-op
non-null expected hash        → SPATIAL_SHOT_PLAN_CONFLICT
```

All current-plan mutations execute through server-owned canonical validation and are included in race proofs.

Plan storage remains JSON intentionally: it is one Shot-local aggregate edited/captured atomically, while reusable world/track authority remains relational. Base M10 does not normalize camera/blocking keyframes into mutable relational rows.

---

# 20. ShotSpatialPlan canonical schema 1

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

### 20.1 Projection and optics

Schema 1 supports `projection="perspective"` only, interpreted by §6.3's pinhole camera contract. Focal length and sensor dimensions are strictly positive JavaScript-safe integer micrometers. Existing free-text `Shot.lens` is neither parsed nor cross-inferred.

### 20.2 Camera keyframes

- at least one keyframe;
- first keyframe exactly `time_ms=0`;
- strictly increasing unique integer times;
- `0 <= time_ms <= Shot.duration_ms` when duration is non-NULL;
- if duration is NULL, only `time_ms=0` is valid;
- transforms use §6 exact absolute world pose semantics.

Sparse keyframes are **constraints**, not an interpolation contract. No `linear`, Bezier, spline, velocity, tangent, or easing field exists in schema 1. Any executor interpolation is captured execution policy and cannot be reported as authoritative frame-N state.

### 20.3 Blocking

- one blocking entry per `spatial_track_id` at most;
- track is active (`deleted_at IS NULL`), belongs to the selected world, and binds a current dependent Entity;
- first blocking keyframe exactly `time_ms=0`;
- times obey the camera-time rules;
- transforms obey §6;
- screen direction vocabulary is exactly:

```text
left_to_right | right_to_left | stationary | unspecified
```

Schema 1 intentionally models horizontal narrative screen direction only. Vertical screen direction, image-plane path shapes, and automatic pixel-derived verification are deferred.

### 20.4 Axis constraint

At most one axis constraint exists in schema 1. The axis must be included in the selected approved SpatialWorldRevision, not merely exist as a world-level identity. Every camera keyframe must satisfy the declared side using §11 arbitrary-precision integer arithmetic.

### 20.5 Write-time vs readiness-time validation

Pure document/range/ownership errors are rejected at plan write time. Rules dependent on mutable current staging, current approved world revision, current EntityRevision, current Shot/end transitions, or current requirement policy are also revalidated by the ONE readiness resolver. A plan can therefore become unready after another legitimate production edit without being rewritten.

---

# 21. Shot plan vs effective persistent spatial state

A Shot plan cannot silently contradict persistent staging.

For every blocking entry:

```text
blocking track has an effective set state at Shot/start
blocking keyframe time 0 transform == effective track transform
```

If an applicable effective track has no blocking entry, it is captured as statically staged at its effective transform; no synthetic current row is created.

Shot-local motion does **not** automatically mutate downstream continuity.

### 21.1 Explicit Shot/end handoff

If an active Shot/end `set` SpatialTransition exists for a track that also has a blocking entry:

```text
Shot.duration_ms must be non-NULL
blocking must contain a keyframe exactly at time_ms = duration_ms
that final keyframe transform must exactly equal the Shot/end transition transform
```

Any missing duration, missing final keyframe, or mismatch is `SPATIAL_BLOCKING_STATE_MISMATCH`.

If the track has **no blocking entry**, a Shot/end transition is valid persistent narrative authority by itself; M10 does not pretend the ShotSpatialPlan describes a motion path it did not author.

A Shot/end `clear` transition never applies to the Shot itself and does not require a final blocking transform. It affects downstream Shots under M7 boundary semantics.

This closes the r1 NULL-duration/final-keyframe loophole and prevents UI/render playback from becoming temporal authority.

---

# 22. Applicable SpatialWorld selection

Schema 1 allows one selected SpatialWorld per Shot.

Resolution rules:

1. collect active **required** SpatialWorlds whose Location Entity is a current M7 semantic dependency;
2. read ShotSpatialPlan if present;
3. more than one required world → `SPATIAL_CONTEXT_AMBIGUOUS`;
4. exactly one required world:
   - ShotSpatialPlan is required;
   - plan `spatial_world_id` equals that world;
5. zero required worlds + plan:
   - selected world may be optional;
   - selected world's Location Entity is a current Shot dependency;
6. zero required worlds + no plan:
   - no effective M10 authority;
   - spatial readiness true;
   - spatial hash NULL;
7. plan selecting a world whose Location is no longer a dependency → `SPATIAL_SHOT_PLAN_INVALID` current state, never silent ignore.

Multiple optional worlds may exist; an explicit plan chooses at most one.

Accepted schema-1 product consequence: a threshold/doorway/composite Shot depending on two required Location worlds is blocked until production remodels the Shot or a future multi-world schema exists. Required policy is never weakened globally or locally as an automatic workaround.

---

# 23. State-specific world resolution and revision consistency

For the selected SpatialWorld, the resolver obtains the exact current Location `EntityRevision` from the same coherent M7 dependency snapshot.

Then:

```text
(world_id, location_entity_revision_id)
→ exact active SpatialWorldState
→ exact approved SpatialWorldRevision
```

Precedence is strict:

```text
missing matching state
→ SPATIAL_WORLD_STATE_REQUIRED

state exists but approved_revision_id is NULL
→ SPATIAL_WORLD_APPROVAL_REQUIRED
```

The second code is never used as an alias for missing state.

Approved-pointer corruption, hash mismatch, child-projection mismatch, wrong-state revision, or unreadable canonical bytes are invariant failures rather than readiness issues.

After loading the approved revision, the resolver also validates:

- fixed-frame/track one-placement-authority rule;
- any fixed bound Entity that is a Shot dependency uses the exact same EntityRevision captured by M7;
- every axis endpoint exists in the revision frame set;
- every plan axis exists in the revision axis set.

No current world-state row is substituted for the immutable approved revision.

---

# 24. Spatial readiness composition

Current readiness is layered:

```text
M7 semantic readiness
        ↓
M8 visual readiness (independent sibling authority)
        ↓
M10 spatial readiness
        ↓
model/package realization readiness
```

M10 must not run when M7 semantic state is unresolved because exact Location/Entity revision context is unavailable.

M8 and M10 are sibling production-authority layers after M7. An M8 blocker does not authorize M10 to fabricate state, but M10 may still be resolved for inspection after M7 succeeds. Combined capture/generation preserves blocker precedence:

```text
M7 blockers
→ M8 blockers
→ M10 blockers
→ model/package realization blockers
```

The API retains the full deterministically ordered issue set even though the first blocker defines the top-level failure response.

---

# 25. ONE current spatial resolver

There is exactly one authoritative current builder for:

- Shot detail spatial readiness;
- `GET /shots/{id}/spatial-continuity`;
- working snapshot hash;
- ShotRevision capture;
- M10 current inspector;
- preview input to any spatial realization readiness compiler.

UI never reimplements world selection, track transition resolution, axis-side checks, or pack hashing.

The resolver consumes a caller-owned `AsyncConnection` inside one coherent SQLite read transaction so M7 dependencies, world approval, transitions, and Shot plan cannot be mixed across snapshots.

---

# 26. SpatialContinuityPack canonical schema 1

The ONE current resolver returns a canonical pack only when non-empty M10 authority is coherent.

High-level shape:

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
    "world_snapshot": { "schema_version": 1, "...": "..." }
  },
  "staging": [
    {
      "spatial_track_id": "...",
      "entity_id": "...",
      "entity_revision_id": "...",
      "requirement": "required",
      "transform": {
        "translation_mm": [0,0,0],
        "rotation_udeg": [0,0,0]
      },
      "source_transition": {
        "spatial_transition_id": "...",
        "anchor_type": "shot",
        "anchor_id": "...",
        "boundary": "end"
      }
    }
  ],
  "shot_plan": { "schema_version": 1, "...": "..." }
}
```

Canonical staging order is `(entity_id, spatial_track_id)`.

### 26.1 Embedded world snapshot is intentionally self-contained

The full approved world snapshot remains embedded in every non-empty captured pack. The immutable SpatialWorldRevision already provides historical isolation; embedding additionally provides self-contained ShotRevision inspection/export/archive without a live relational join. This is a deliberate archival/portability tradeoff.

Mechanical integrity requires:

```text
canonical_json(pack.spatial_world.world_snapshot)
==
exact canonical bytes represented by SpatialWorldRevision.snapshot_json

SHA-256(canonical_json(world_snapshot))
==
spatial_world_revision_hash

pack.spatial_world.requirement
==
shot_revision_spatial_worlds.requirement
==
SpatialWorld.requirement observed at capture
```

The immutable revision row remains separately retained, so both self-contained history and cross-provenance are available.

The §60 scale fixture records actual schema-5 snapshot byte sizes and duplicated world-snapshot volume as evidence, but r3 sets no arbitrary byte threshold. A future normalization change would require a new ShotRevision schema, never silent reinterpretation.

`spatial_continuity_hash = SHA-256(canonical_json(pack))` using the same SoloRing canonical serializer as predecessors.

---

# 27. Current Shot API projection

`ShotRead` gains additive **computed** fields only:

```text
spatial_continuity_ready: bool = false
spatial_continuity_hash: str | null
spatial_continuity_issues: list = []
```

No M10 readiness/hash column is added to `shots`. Default false prevents an unpopulated server model from masquerading as resolved readiness; the server projection explicitly sets the real value on reads.

`GET /shots/{id}/spatial-continuity` returns server-owned projection data:

- M7 readiness summary;
- selected/applicable world identity and requirement layer;
- exact current Location EntityRevision;
- approved immutable world revision/hash;
- included frame/axis summaries from the approved revision;
- effective staging tracks with exact EntityRevision + winning source transition;
- camera optics/keyframes;
- blocking tracks/keyframes;
- axis constraint status;
- screen-direction declarations;
- complete deterministic ordered issues;
- spatial continuity hash only when fully resolvable;
- when no applicable M10 authority exists: `ready=true`, `hash=null`, empty spatial pack.

No current endpoint labels working/current data as historically captured authority.

---

# 28. Readiness blocker semantics

M10 production readiness blocks before expensive execution when required/current-selected authority is unresolved.

Core production blockers include:

```text
SPATIAL_CONTEXT_AMBIGUOUS
SPATIAL_SHOT_PLAN_REQUIRED
SPATIAL_WORLD_STATE_REQUIRED
SPATIAL_WORLD_APPROVAL_REQUIRED
SPATIAL_TRACK_STATE_REQUIRED
SPATIAL_ENTITY_PLACEMENT_CONFLICT
SPATIAL_ENTITY_REVISION_MISMATCH
SPATIAL_SHOT_PLAN_INVALID
SPATIAL_BLOCKING_STATE_MISMATCH
SPATIAL_AXIS_CONSTRAINT_VIOLATION
```

`SPATIAL_WORLD_CAPTURE_CONFLICT`, approval/plan CAS conflicts, and instancing errors are mutation-operation conflicts, not ordinary readiness rows unless the resulting current state is itself invalid.

Optional world/track absence is canonical absence only under exact optional rules. Once an optional world is explicitly selected by a ShotSpatialPlan, its state/approval/plan/staging must be coherent; explicit selection cannot degrade silently.

Realization blockers such as `SPATIAL_REALIZATION_UNSUPPORTED` are reported separately from production readiness and never rewrite `spatial_continuity_ready`.

---

# 29. Working snapshot hash integration

The Shot's effective working hash includes current M10 authority whenever a non-empty SpatialContinuityPack applies.

The single capturable snapshot builder accepts:

```text
semantic dependencies + exact EntityRevisions
feature states
relation states
visual pack
spatial pack
```

If current required M7/M8/M10 production state is unresolved, current working hash is NULL and the Shot is not capturable.

Changing any hash-bearing M10 fact without touching the Shot row changes the effective working hash, including:

- approved SpatialWorldRevision;
- state frame/axis membership through a newly approved revision;
- bound EntityRevision captured in fixed frames;
- effective SpatialTransition winner;
- exact staged EntityRevision;
- ShotSpatialPlan camera/blocking values;
- axis constraint;
- track/world requirement captured into the pack.

Current-vs-approved-Take comparison therefore remains honest. Requirement or policy changes do not mutate old ShotRevision hashes; they alter only the current capturable future.

---

# 30. ShotRevision schema 5 lattice and compatibility cube

M10 extends the canonical ShotRevision snapshot lattice without creating an empty higher schema.

Published lower schemas remain byte-identical:

```text
schema 1  zero semantic dependencies
schema 2  semantic dependencies, no effective M7 Feature/Relation state, no M8 visual, no M10 spatial
schema 3  non-empty effective M7 Feature/Relation state, no M8 visual, no M10 spatial
schema 4  non-empty M8 visual authority, no M10 spatial authority
schema 5  ANY non-empty M10 SpatialContinuityPack
```

Schema 5 may sit over a semantic base equivalent to predecessor schema 2 or 3 and may contain M8 visual authority or not.

Canonical shape:

```json
{
  "schema_version": 5,
  "intent": {...},
  "references": [...],
  "continuity": {...},
  "visual_reference_pack": {...},
  "spatial_continuity": {...}
}
```

`visual_reference_pack` is omitted when M8 authority is empty. `spatial_continuity` is always present and non-empty in schema 5.

Mandatory selection cube:

| semantic dependencies | effective M7 state | M8 visual | M10 spatial | ShotRevision schema |
|---:|---:|---:|---:|---:|
| none | none | none | none | 1 |
| yes | empty | none | none | 2 |
| yes | non-empty | none | none | 3 |
| yes | empty or non-empty | non-empty | none | 4 |
| yes | empty or non-empty | empty or non-empty | non-empty | 5 |

Impossible/corrupt cells:

- zero semantic dependencies + non-empty M8 or M10 authority;
- non-empty M10 authority emitted as schema 1–4;
- schema 5 with null/empty `spatial_continuity`;
- required unresolved M10 production state followed by lower-schema fallback;
- schema 4/5 nested M8 bytes differing from canonical M8 builder;
- schema 5 nested M10 bytes differing from canonical M10 builder.

Constructing an impossible cell is `INTERNAL_INVARIANT_VIOLATION`, never an automatic downgrade.

---

# 31. Historical M10 child capture

Schema-5 ShotRevision persistence writes the normalized tables frozen in §7.2 from the same in-memory SpatialContinuityPack used to produce `snapshot_json`.

### `shot_revision_spatial_worlds`

One row pins:

```text
spatial_continuity_hash
world/state/revision ids
world revision hash
Location entity + exact Location EntityRevision
```

### `shot_revision_spatial_track_states`

One canonical-position row per effective captured staging state pins:

```text
track id
Entity id
exact EntityRevision id active for the Shot
requirement_at_capture
exact transform
winning SpatialTransition id + anchor coordinates
```

This is intentionally stronger than r1: spatial staging history is self-contained with respect to the exact semantic design revision occupying that transform.

### `shot_revision_spatial_plans`

One row pins exact canonical plan bytes/hash.

Every child projection is cross-validated against embedded schema-5 bytes on capture/reuse/history reads where integrity is asserted. Current M10 rows are never consulted to reconstruct missing historical child values.

---

# 32. Coherent ShotRevision capture

ShotRevision capture extends the established coherent-read contract.

One read transaction must establish:

```text
Shot + references
M6 dependencies + exact EntityRevisions
M7 effective Feature state
M7 effective Relation state
M8 current visual pack
M10 current spatial pack
```

The transaction freezes these values in memory before write persistence.

No second current M10 resolver call is allowed after the capture snapshot has been established.

The write phase uses `BEGIN IMMEDIATE`, converges on `(shot_id,snapshot_hash)`, persists all semantic/visual/spatial child rows from the same frozen value, and fail-closed validates existing rows on reuse.

---

# 33. Historical isolation

After a schema-5 ShotRevision is captured, later current mutations cannot alter its meaning, including:

- SpatialWorld requirement edit;
- Location EntityRevision approval/current-revision change;
- dependent fixed/movable EntityRevision change;
- SpatialWorldState approval/unapproval;
- frame/axis membership/value edit;
- frame parent/bound-Entity metadata edit;
- new SpatialWorldRevision;
- SpatialTrack requirement edit;
- SpatialTransition edit;
- ShotSpatialPlan edit/delete;
- current M8 approval change;
- current workflow/profile/package/runtime replacement.

Historical projection reads captured ShotRevision bytes/normalized child rows and immutable world-revision data only where required for integrity checks. It never substitutes current world approval, current EntityRevision, current requirement, current plan, or current package state.

---

# 34. Exact Rerun remains historical copy only

Exact Rerun semantics do not change.

A rerun of a **workflow-spec schema-3** M10-aware Generation copies:

```text
source Generation durable workflow_spec_json/hash
source GenerationInputs
```

verbatim into the fresh execution attempt under the published M9 rerun contract.

It does **not**:

- call current M10 resolver;
- read current worlds/states/frame memberships/axis memberships/tracks/transitions/plans/requirements/approvals;
- read current EntityRevision to reinterpret captured staging;
- call current M10 spatial compiler;
- inspect the current installed spatial-capable package/profile/runtime fingerprint.

Mandatory source gate:

1. monkeypatch current M10 resolver to raise;
2. monkeypatch current spatial realization compiler to raise;
3. SQL read spy forbids current M10 authority-table reads;
4. mutate current world/plan/requirements/EntityRevision/profile/package/runtime aggressively;
5. rerun still copies exact historical spec/inputs and verifies against captured runtime identity only.

---

# 35. Historical spatial provenance API

The revision-continuity/history API gains a `spatial` block for ShotRevision schema 5:

```text
captured spatial_continuity_hash
captured world/state/revision identities
captured world revision hash
captured Location Entity + exact Location EntityRevision
captured effective staging + exact staged EntityRevision + source anchors
captured requirement-at-capture values
captured camera optics/keyframes
captured blocking
captured axis/screen-direction intent
captured spatial realization/package/runtime fingerprint when a Generation exists
current applicable comparison (informational only)
```

Current comparison uses the ONE current resolver. If current semantic context is unresolved, current applicability is honestly unavailable; it is never guessed from captured identifiers.

Historical fields remain available even when current identities are soft-deleted or current requirement policy differs.

---

# 36. M7 Relation boundary

M10 does not automatically assign metric geometry semantics to arbitrary M7 predicates.

For example, a relation key such as:

```text
stands-left-of
```

is not sufficient for M10 to infer an offset, world transform, axis, blocking rule, or contradiction check. Current M7 relations do not carry the formally frozen metric predicate required to do that mechanically.

Therefore r3 deliberately performs **no generic M7-relation ↔ M10-transform consistency validation**. Adding such validation without a typed geometric relation contract would merely turn relation vocabulary into hidden geometry code.

A future relation type may define an exact metric predicate, coordinate space, tolerance/integer rule, and error semantics; only then may M10 cross-validate it. Until then, explicit M10 world/track/plan authority is the sole metric source.

---

# 37. M8 visual boundary

M10 frames and tracks never replace M8 visual identity.

A spatial frame bound to a Prop Entity may pin:

```text
Prop EntityRevision identity
position/orientation/extent
```

but does not carry its approved visual images.

M8 remains the appearance authority. M10 may reference Entity/EntityRevision identities for spatial binding, but it must not import M8 item role/weight semantics into the world graph.

---

# 38. Tracking / reconstruction boundary

Tracking, roto, photogrammetry, camera solve, depth estimation, SLAM, NeRF reconstruction, Gaussian splat reconstruction, or model-generated geometry may later assist M10 authoring.

Base rule:

```text
measurement/reconstruction output
→ proposal
→ explicit production adoption
→ M10 authority
```

Never:

```text
measurement output
→ automatic authoritative world/plan mutation
```

Schema 1 contains no automatic ingest path from executor outputs.

---

# 39. No surface-geometry overclaim

The M10 schema-1 world graph is the authoritative representation of **relevant stable spatial facts**:

- world coordinate frames;
- placements/orientations;
- coarse extents;
- staging;
- camera optics/poses;
- axis/screen-direction intent.

It deliberately does not claim to encode every visible surface point.

Therefore M10 can prove:

> This Generation was requested against this exact authoritative layout, staging state, and camera plan.

M10 cannot by itself prove:

> Every pixel of every arbitrary view is geometrically identical to a traditional CG set render.

A later technology-specific geometric realization can strengthen that claim without becoming the production-truth schema.

---

# 40. Spatial realization capability gate

M10 may not silently pass non-empty spatial authority through a workflow package that cannot consume its **hard execution components**.

The published M9 Hunyuan v4 package has no spatial binding. Therefore:

```text
non-empty M10 authority
+ package without frozen spatial capability contract
→ Generation creation blocked before queueing
```

M10A source-fit happens **before significant M10B–D implementation momentum**. It must characterize at least one real explicit spatial-conditioning path before M10 can claim a viable route to closure.

The plan does not pre-authorize meshes, depth maps, pose images, camera tensors, ControlNet, renderer-specific scene files, custom 3D nodes, or any other mechanism.

If the first viable path requires materialized derived bytes, implementation STOPS before introducing them and revises this plan with the M9-derived provenance checklist:

```text
source authority hash
conversion algorithm + version
all input artifact hashes
canonical parameters
output Blob hash
retention/liveness rules
historical rerun reconstruction/verification
corruption behavior
runtime dependency identity
```

If no production executor can consume M10's hard components without authority loss or hidden graph heuristics, M10E remains blocked and **M10 remains open**. The authority contract is not weakened to manufacture milestone completion.

---

# 41. M10 evolution of the realization layer

M10 extends the published M9 execution boundary without moving authority downward.

After source-fit:

- `RealizationProfile` evolves to **profile schema 2** with an optional `spatial` capability block;
- workflow manifest/package evolves to **manifest/package schema 3** with explicit spatial target(s);
- workflow-spec evolves to **workflow-spec schema 3** only when non-empty spatial realization exists;
- existing profile/package/workflow-spec schemas remain accepted byte-for-byte.

The exact spatial binding fields depend on the real executor path and are frozen in M10A before implementation of M10E.

M10 does **not** introduce per-Shot execution-profile selection inside `ShotSpatialPlan`. Package/profile selection remains governed by the existing M9 Generation-creation configuration and capture seams. Spatial production authority never chooses its executor.

---

# 42. Spatial capability profile — hard vs advisory semantics

The eventual profile schema explicitly declares the spatial document schema and which execution components are consumed.

Schema-1 production components are classified as:

```text
hard execution components:
  world graph
  effective staging
  camera optics/keyframes
  blocking keyframes when present

production validity constraint:
  axis_constraint

advisory cinematic execution intent:
  screen_direction
```

Rules:

- any present **hard** component not explicitly supported → `SPATIAL_REALIZATION_UNSUPPORTED`;
- `axis_constraint` is evaluated upstream against authoritative camera keyframes; the executor need not receive the axis identity merely to re-prove a constraint already satisfied, though a package may consume it explicitly;
- `screen_direction` may be unconsumed only when the profile declares that limitation explicitly and the compiler emits a deterministic captured omission record such as `screen_direction_not_consumed`; silent dropping is forbidden;
- omission never changes M10 production authority and never implies pixel-level compliance;
- whole-item atomicity applies: no truncating frames/tracks/keyframes to fit arbitrary executor capacity without a frozen deterministic contract.

This distinction prevents non-enforceable advisory intent from making every executor unusable while still making authority loss visible.

---

# 43. Explicit spatial executor binding

The first spatial-capable manifest binds captured spatial execution through explicit node/field contracts only, conceptually:

```json
{
  "spatial_bindings": [
    {
      "binding_key": "primary_spatial",
      "node": "...",
      "field": "...",
      "format": "soloring.spatial.v1"
    }
  ]
}
```

Exact grammar is frozen from real source-fit in M10A.

Forbidden:

- find the first camera/depth/control node;
- class-name substring heuristics;
- filename heuristics;
- prompt injection of camera/world numbers;
- installed-node recency/order tie-breakers;
- current-graph introspection to reinterpret historical binding.

Missing or mismatched explicit target fails before submission.

---

# 44. ONE spatial realization compiler and deterministic visual+spatial composition

After M10A freezes the package contract, there is ONE pure spatial compiler:

```python
compile_spatial_realization(
    captured_spatial_authority,
    profile,
    manifest,
) -> SpatialRealizationResult
```

It has zero database, filesystem, network, Settings, current Shot, current M10, current package, or Comfy dependencies.

It returns:

- `ready`;
- complete deterministic ordered issues;
- exact spatial execution document when ready;
- explicit binding metadata;
- explicit advisory omissions;
- no partial replacement authority when blocked.

The M9 visual compiler and M10 spatial compiler are **independent pure functions**:

```text
visual compiler reads captured M8 authority only
spatial compiler reads captured M10 authority only
```

Neither may read or mutate the other's production-authority document.

Combined realization readiness is:

```text
visual_ready AND spatial_ready
```

for whichever non-empty blocks are applicable. The workflow-spec builder is the single deterministic composition seam and canonicalizes the merged `realization` + `spatial_realization` blocks in fixed schema order.

A golden fixture with both non-empty M8 and M10 authority must produce byte-identical workflow-spec schema 3 under shuffled source ordering.

---

# 45. Workflow-spec schema 3 compatibility lattice

Workflow-spec family names are always qualified to avoid confusion with ShotRevision/manifest/profile schemas.

Existing exact paths:

```text
workflow-spec v1 = no M9 visual realization, no M10 spatial realization
workflow-spec v2 = non-empty M9 visual realization, no M10 spatial realization
workflow-spec v3 = non-empty M10 spatial realization (M9 visual block may also be non-empty)
```

Canonical v3 high-level form:

```json
{
  "schema_version": 3,
  "...existing captured package/request fields...": "...",
  "model": {"...": "..."},
  "realization": {"...optional M9 block...": "..."},
  "spatial_realization": {
    "schema_version": 1,
    "spatial_continuity_hash": "...",
    "document": {"...": "..."},
    "advisory_omissions": [],
    "runtime_fingerprint": {"...M10A-frozen shape...": "..."}
  }
}
```

No empty workflow-spec v3 exists.

Mandatory cross-product fixtures:

| Package/manifest | Profile | M8 | M10 | Result |
|---|---|---:|---:|---|
| v1 legacy | v1 | empty | empty | exact workflow-spec v1 |
| v2 visual | v1 | non-empty | empty | exact workflow-spec v2 |
| v3 spatial-capable | v2 | empty | empty | exact workflow-spec v1 |
| v3 spatial-capable | v2 | non-empty | empty | exact workflow-spec v2 |
| v3 spatial-capable | v2 | empty | non-empty | workflow-spec v3, no fake M9 block |
| v3 spatial-capable | v2 | non-empty | non-empty | workflow-spec v3 with both independent blocks |
| v1/v2 non-spatial | any valid | any | non-empty | `SPATIAL_REALIZATION_UNSUPPORTED` |

A v3 manifest's spatial target may be unused when M10 authority is empty; the emitted request must still be exact lower-schema v1/v2, not an empty v3 shell.

---

# 46. Model/package readiness vs M10 readiness

M10 production readiness and model realization readiness are separate:

```text
spatial_continuity_ready
```

means the production world/staging/camera authority is coherent.

```text
spatial_realization_ready
```

means the selected current workflow package can consume that captured authority without dropping required components.

A Shot can therefore be:

```text
M7 ready        yes
M8 ready        yes
M10 ready       yes
M10 realization no
```

This is an honest package limitation, not permission to weaken world authority.

---

# 47. Generation creation integration

For a normal new Generation after M10:

1. capture one coherent workflow-package release identity at the M9 Stage-0 seam;
2. resolve production readiness and freeze one coherent in-memory M7/M8/M10 ShotRevision candidate;
3. validate package/profile/manifest/materializer capabilities;
4. compile M9 visual and M10 spatial realization independently from the frozen candidate;
5. build canonical content-only `DerivedSpatialArtifactSpec` values for required materialized roles;
6. resolve exact structured-spatial binding identity and materializer runtime fingerprints;
7. materialize/converge D0 derived artifacts outside the DB writer transaction;
8. verify published Blob bytes and derived provenance candidates;
9. assemble existing `GenerationInputs` plus sibling `generation_derived_spatial_inputs`;
10. build final workflow-spec v1/v2/v3 exactly once after every identity-bearing input exists;
11. canonicalize/hash workflow-spec exactly once;
12. enter final `BEGIN IMMEDIATE`, rerun canonical current M10 resolution, require exact `spatial_continuity_hash` equality with the frozen source;
13. persist ShotRevision/M10 children + Generation + existing/derived input relations atomically;
14. queue only after durable capture.

Heavy materialization never holds the writer. Drift is `DERIVED_SPATIAL_CAPTURE_CONFLICT`; there is no BEFORE/AFTER attachment heuristic. SQL-shape proof covers relational persistence; materializer work is outside SQL accounting.


---

# 48. Worker historical isolation and runtime identity

The worker executes captured Generation state only.

For workflow-spec v3 it verifies:

- captured workflow/package artifact integrity;
- exact workflow-spec hash;
- existing M9 model/environment fingerprint;
- M10 spatial binding presence and schema/hash cross-agreement;
- explicit structured-camera/spatial binding identity where applicable;
- derived artifact spec/provenance/Blob identities;
- materializer runtime fingerprints;
- any model/control/custom-node/conversion dependencies materially required by the spatial path.

M10A must explicitly answer:

> Does the existing M9 captured environment identity uniquely identify every new component that can materially change spatial translation/execution?

If yes, the v3 runtime fingerprint may reference/prove that inherited identity. If no, M10A freezes an additive historical fingerprint covering the missing items, such as:

```text
spatial binding implementation version/hash
custom-node revision/hash
spatial control-model weight hash
conversion/representation algorithm version
other material runtime artifact hashes
```

The worker writes only explicitly declared executor fields. It never calls the current M10 resolver/compiler or reads current spatial authority.

Current world/profile/package/node changes while a Generation is queued cannot alter its submitted request.

---

# 49. Exact Rerun workflow-spec-v3 contract

Exact Rerun copies historical workflow-spec v3, existing `GenerationInputs`, and `generation_derived_spatial_inputs` verbatim.

It does not re-resolve M10, rebuild derivative specs, rematerialize by default, use current package/materializer/runtime state, upgrade schema, or regenerate omissions.

Before executor submission, historical derived input validation reaches physical Blob bytes and requires SHA-256 equality with captured provenance. Missing/corrupt historical derived bytes fail closed. Automatic regeneration from current M10 state is forbidden.


---

# 50. Spatial UI — World editor (schema-1 scope)

M10 UI adds a reliable server-owned Spatial World workspace reachable from Location entities.

Schema-1 UI is intentionally **form/table oriented**, not a miniature Blender/Maya/3D DCC.

It exposes:

- world key/name/required-vs-optional policy and consequences;
- exact current Location EntityRevision;
- state-specific included frame table;
- integer position/orientation/extents editor with coordinate-convention help;
- optional bound Entity + exact state-specific revision;
- stable organizational parent hierarchy;
- state-specific included axis table + endpoints;
- server-computed working snapshot hash;
- revision history;
- approve/unapprove with expected pointer;
- current approved revision/hash;
- explicit working-vs-approved labels;
- validation messages for missing parent membership, placement conflicts, revision mismatch, axis problems, and capture conflicts.

UI never computes canonical transforms, world hashes, axis-side authority, or approval applicability client-side. A future visual 3D editor may generate candidate form values, but server validation remains authoritative.

---

# 51. Spatial UI — Track/timeline editor

For each SpatialWorld, the UI exposes server-backed SpatialTracks for movable dependent Entities.

Required controls:

- create/delete track with schema-1 instancing limitation explained;
- required/optional policy and explicit downgrade-before-delete behavior;
- list narrative transitions in canonical M7 order;
- create/edit/tombstone `set|clear` transition;
- show anchor type/id/boundary;
- show effective state preview at a selected Shot;
- show exact current semantic EntityRevision attached to effective staging;
- show fixed-frame placement conflict if the selected approved world also binds that Entity.

No playback traversal becomes authority. Effective state always comes from the server resolver.

---

# 52. Spatial UI — Shot Spatial + Camera panel

Shot detail gains a form/table-oriented Spatial + Camera panel rendering server-owned state:

- selected/applicable world and exact Location revision;
- world/track requirement layer labels;
- spatial production readiness + full issues;
- approved world revision/hash;
- effective staging with exact EntityRevision and source transition;
- numeric pinhole optics;
- sparse camera keyframes;
- sparse blocking keyframes;
- Shot/end handoff status;
- axis constraint and server-computed side status;
- screen-direction advisory declarations;
- current spatial hash;
- spatial realization readiness separately from production readiness;
- explicit advisory omission status when a package cannot consume screen direction;
- warning that preview is current inspection, not reserved capture.

Plan editing sends candidate values to the server with expected plan hash. Frontend does no authoritative transform normalization, axis multiplication, world selection, or hash construction.

---

# 53. Historical UI

ShotRevision/Generation inspectors display:

- captured SpatialWorld / Location revision;
- captured world revision/hash;
- captured staging and source boundaries;
- captured camera/blocking/axis/screen-direction state;
- captured spatial realization document/package when present;
- current applicable spatial state only as separately labeled informational comparison.

Historical views never relabel current authority as “what this Generation used.”

---

# 54. Error vocabulary principles

M10 uses a closed milestone-specific vocabulary plus inherited predecessor errors.

Rules:

- malformed/invalid client-authored identity/document shape → 422;
- missing/contradictory current production authority → 409;
- expected-pointer/hash conflict → 409;
- unsupported schema-1 instance request → 409 with a stable M10 code rather than raw UNIQUE errors;
- not-found identity → 404 where a dedicated route lookup needs it;
- current package/spatial execution capability mismatch → 409 unless an existing deployment-availability error is the correct layer;
- immutable stored corruption → `INTERNAL_INVARIANT_VIOLATION`;
- no friendly corruption aliases;
- inherited M7/M8/M9/package/executor errors retain published meaning.

Issue rows/details must identify the failed layer (`world_requirement`, `track_requirement`, `plan`, `spatial_realization`, etc.) rather than relying on the overloaded word `requirement`.

---

# 55. M10-owned error table — r3 integration freeze candidate

| Code | HTTP | Meaning |
|---|---:|---|
| `SPATIAL_WORLD_INVALID` | 422 | SpatialWorld shape, Location kind, ownership, key, or update invalid. |
| `SPATIAL_WORLD_STATE_INVALID` | 422 | State exact world/Location-revision binding invalid. |
| `SPATIAL_WORLD_CAPTURE_CONFLICT` | 409 | Working state changed between frozen read and fenced capture verification. |
| `SPATIAL_FRAME_INVALID` | 422 | Frame identity/parent/value/extent/bound-Entity contract invalid. |
| `SPATIAL_FRAME_CYCLE` | 409 | Stable organizational parent graph is cyclic. |
| `SPATIAL_AXIS_INVALID` | 422 | Axis identity/membership/endpoints invalid. |
| `SPATIAL_WORLD_REVISION_NOT_FOUND` | 404 | Requested immutable world revision absent. |
| `SPATIAL_WORLD_APPROVAL_CONFLICT` | 409 | Expected current approval pointer is stale. |
| `SPATIAL_TRACK_INVALID` | 422 | Track ownership/requirement/target shape invalid. |
| `SPATIAL_ENTITY_INSTANCING_UNSUPPORTED` | 409 | A second active track for the same world/Entity is not representable in schema 1. |
| `SPATIAL_TRANSITION_INVALID` | 422 | Transition anchor/operation/transform contract invalid. |
| `SPATIAL_SHOT_PLAN_INVALID` | 422 | Camera/blocking/world/axis plan document or ownership invalid. |
| `SPATIAL_SHOT_PLAN_CONFLICT` | 409 | Expected current plan hash is stale or nonexistent/current expectations disagree. |
| `SPATIAL_CONTEXT_AMBIGUOUS` | 409 | More than one required world applies to one schema-1 Shot. |
| `SPATIAL_SHOT_PLAN_REQUIRED` | 409 | Required world applies but no ShotSpatialPlan selects it. |
| `SPATIAL_WORLD_STATE_REQUIRED` | 409 | Exact Location revision has no matching SpatialWorldState. |
| `SPATIAL_WORLD_APPROVAL_REQUIRED` | 409 | Matching state exists but has no approved world revision. |
| `SPATIAL_TRACK_STATE_REQUIRED` | 409 | Required applicable track has no effective `set` state. |
| `SPATIAL_ENTITY_PLACEMENT_CONFLICT` | 409 | One effective Entity has multiple placement authorities (fixed/fixed or fixed/track). |
| `SPATIAL_ENTITY_REVISION_MISMATCH` | 409 | Fixed-frame bound EntityRevision conflicts with the Shot's exact semantic EntityRevision. |
| `SPATIAL_BLOCKING_STATE_MISMATCH` | 409 | Blocking t=0 or required Shot/end handoff contradicts persistent spatial state. |
| `SPATIAL_AXIS_CONSTRAINT_VIOLATION` | 409 | Camera lies on/crosses forbidden axis side. |
| `SPATIAL_REALIZATION_UNSUPPORTED` | 409 | Selected package/profile cannot consume required hard M10 execution components. |
| `SPATIAL_REALIZATION_BINDING_INVALID` | 422 | Package/profile/manifest spatial binding or runtime-fingerprint contract invalid. |

Validation must map to exactly one row above. Source-fit may prove that an inherited package/deployment error is the correct layer for a failure not owned by M10; it may not create a near-duplicate M10 alias.

---

# 56. Error precedence

Current readiness / new Generation precedence is:

```text
Stage-0 package raw-capture integrity when no coherent package snapshot exists
→ M7 semantic blockers
→ M8 visual-production blockers
→ M10 spatial-production blockers
    world selection
    exact world state
    world approval/integrity
    entity placement authority
    entity revision consistency
    required track state
    plan/blocking/axis validity
→ package structural/semantic validation
→ M9 visual-realization blockers
→ M10 spatial-realization blockers
→ combined input/cardinality/executor/deployment validation
```

Within M10 production blockers, `SPATIAL_WORLD_STATE_REQUIRED` strictly precedes `SPATIAL_WORLD_APPROVAL_REQUIRED`: a missing state is never described as an unapproved state.

APIs may return the full deterministically ordered issue set for inspection, but any single raised blocking response must use this precedence.

Immutable corruption discovered at any stage fails immediately as invariant corruption and is never demoted into a friendly readiness code.


`SPATIAL_ENTITY_PLACEMENT_CONFLICT` precedes `SPATIAL_ENTITY_REVISION_MISMATCH` when both apply to the same effective Entity.

---

# 57. Deletion, tombstones, and retention

Restrictive FKs and explicit service guards preserve historical provenance.

- SpatialWorldRevision and ShotRevision M10 child rows are append-only and have no delete API.
- A `required` SpatialWorld cannot be deleted until production explicitly changes it to `optional`.
- A `required` SpatialTrack cannot be deleted until production explicitly changes it to `optional`.
- optional SpatialWorld deletion is blocked while any current ShotSpatialPlan selects it or active current child identity cannot be safely tombstoned;
- SpatialWorldState has no ordinary delete operation in schema 1; state identity is permanent;
- frame deletion is blocked while any state-frame membership exists, any stable child frame names it as parent, or any current state-axis endpoint needs it;
- axis deletion is blocked while any state-axis membership or current ShotSpatialPlan references it;
- track deletion is blocked while active SpatialTransitions or current blocking entries reference it;
- current ShotSpatialPlan delete obeys §19 CAS and never touches historical plan rows.

There is no M10 garbage collector in the base plan. Historical ShotRevision/Generation provenance is a permanent live root.

Service guards may use project-wide queries for explicit destructive administration; §59's bounded hot-path contract applies to target resolution/capture/Generation, not to rare deletion scans. No denormalized "in use" cache is introduced preemptively.

---

# 58. No automatic carry-forward or hidden temporal-spatial dimension

M10 deliberately refuses convenience behavior that would rewrite production meaning.

No automatic carry-forward across:

- Location EntityRevision change;
- SpatialWorldState replacement;
- new SpatialWorldRevision;
- SpatialTrack creation;
- requirement flips;
- ShotSpatialPlan replacement;
- model/package changes.

A new Location revision needs its own explicit world state/revision approval before required M10 readiness succeeds.

### 58.1 Day/night, weather, damage, seasonal and destruction states

M10 does not create a hidden `time_of_day` or `weather` axis in SpatialWorldState.

- purely visual day/night/weather variation belongs to semantic/visual authority as appropriate and does not require a new spatial state merely because lighting changes;
- a condition that materially changes authoritative layout/occupancy/staging substrate (destroyed wall, moved desk layout, flooded floor, seasonal structure change) is represented by an explicit semantic/design change—normally a new exact Location `EntityRevision`—followed by an explicit SpatialWorldState/approval;
- no executor-observed change promotes itself into a new Location revision or world state.

This keeps M10 bound to exact production design state rather than introducing an unversioned environmental timeline.

---

# 59. Bounded SQL/query-shape contract

M10 freezes **shape**, not an arbitrary numeric latency/query ceiling.

For one target Shot, current resolution/capture uses a bounded set of set-oriented query classes independent of project/frame/track cardinality, including:

```text
Shot + current M7 dependency/revision/narrative context
applicable worlds + current ShotSpatialPlan
exact SpatialWorldState + approved revision
immutable revision frame/axis child sets
applicable tracks for dependent Entities
all relevant transitions for those tracks
```

No per-frame, per-axis, per-track, per-transition, per-keyframe, or prior-Shot query loop is allowed.

Proof form:

```text
small legal target
vs
representative ~2,500-Shot target
same exact production resolution/capture path
→ same SQL statement-class/count
```

Write-path proof separately measures **first-time**:

```text
POST /shots/{id}/generations
```

on comparable fresh small and representative targets, including reads and writes for ShotRevision, M10 historical child rows, Generation, and existing GenerationInputs. Counts must be equal even though the representative database contains the full scale matrix.

The representative target should persist multiple spatial track states so row count differs while round-trip count remains bounded.

Record wall time and, where useful, `EXPLAIN QUERY PLAN` diagnostics as evidence. Do not freeze planner text or arbitrary milliseconds/memory ceilings; SQLite plan text can change with version/data distribution. Acceptance is query-shape/count plus required index/parity proof, not brittle planner-string equality.

---

# 60. Representative feature-film-scale fixture

The designated M10 scale fixture is one ~2,500-Shot Project containing at minimum:

- recurring Location entities with historical revisions;
- one required SpatialWorld used across hundreds of Shots;
- multiple SpatialWorldStates across exact Location revisions;
- 60+ stable frame identities with state-specific membership/value changes;
- multiple stable cinematic-axis identities with state-specific membership/endpoints;
- fixed frames bound to Prop/Vehicle entities in at least one state;
- the same Entity movable by SpatialTrack in a different non-conflicting state;
- recurring Character/Prop/Vehicle SpatialTracks;
- transitions anchored at sequence/scene/shot start/end;
- required/optional tracks, clears, later re-entry, and requirement flips;
- ShotSpatialPlans with static and multi-keyframe cameras;
- multi-track blocking and explicit Shot/end handoff success/failure;
- axis-side success, on-axis, and violation cases;
- all current M10 production blocker classes;
- M8 visual authority simultaneously present for the main target family;
- M9 visual realization simultaneously present for at least one M10-capable package fixture;
- workflow-spec v1/v2/v3 compatibility cells from §45;
- schema-5 capture and workflow-spec-v3 Generation history;
- noise worlds/tracks/transitions unrelated to the designated target.

The target family must exercise the complete frozen readiness/realization matrix **inside the representative database**, not in disconnected toy fixtures.

Scale evidence records:

```text
frame/axis/track/transition counts
schema-5 canonical snapshot bytes
embedded world_snapshot bytes
aggregate duplicated world_snapshot bytes for representative captured targets
small vs representative SQL counts
first-Generation persistence row counts
```

These are evidence metrics, not arbitrary pass/fail size thresholds.

---

# 61. Mechanical race suite

Every race uses genuine concurrent operations plus Events/barriers at real production seams. No sleeps.

Required classes:

1. world frame/axis membership/value edit vs world-revision capture — complete BEFORE/AFTER or explicit capture conflict, never hybrid;
2. world approval change vs ShotRevision capture;
3. SpatialTransition edit vs current resolver/capture;
4. ShotSpatialPlan edit/delete vs capture;
5. Location EntityRevision approval/current-revision change vs spatial resolution;
6. dependent bound/movable EntityRevision change vs spatial resolution/capture;
7. competing world approvals — expected-pointer one winner;
8. approval vs unapproval;
9. SpatialWorld `required↔optional` flip vs resolver/capture;
10. SpatialTrack `required↔optional` flip vs resolver/capture;
11. package/profile replacement vs spatial realization preview;
12. worker execution vs current world/profile/package/runtime changes;
13. Exact Rerun vs current spatial edits/profile/package changes;
14. stable frame parent/bound-Entity metadata edit vs world-revision capture — one whole value or `SPATIAL_WORLD_CAPTURE_CONFLICT`;
15. derived materialization vs current M10 edit — final hash equality or `DERIVED_SPATIAL_CAPTURE_CONFLICT`;
16. duplicate equivalent D0 materialization — converge on one verified Blob;
17. derived publish vs Generation fence loss — unreferenced derivative, never hybrid history;
18. Exact Rerun vs derived-artifact GC attempt — historical liveness wins;
19. worker vs current materializer/package replacement — historical identities only.

Events fire at actual `BEGIN IMMEDIATE` entry/commit, coherent-read establishment, descriptor/profile capture, immutable ShotRevision capture, historical artifact read, or equivalent production seams—not test-only wrapper approximations.

Every read-vs-write class proves both complete BEFORE and complete AFTER serializations where meaningful. CAS/capture-conflict classes prove the exact allowed conflict outcome instead of accepting a mixed document.

---

# 62. Complete BEFORE / AFTER proof standard

Every read-vs-write race class proves both allowed serializations where meaningful:

```text
competitor completes before reader establishes snapshot
→ reader sees complete AFTER

reader establishes snapshot before competitor completes
→ reader sees complete BEFORE
```

No mixed document/world/approval/transition state is accepted.

A race test that merely mutates state in a synchronous callback is not a concurrency proof.

---

# 63. Corruption matrix

M10 source gate intentionally corrupts and then restores at least:

- SpatialWorldRevision `snapshot_json` bytes;
- SpatialWorldRevision `snapshot_hash`;
- immutable revision frame row/position;
- immutable revision axis row/endpoint;
- approved pointer targeting a revision from another state;
- ShotRevision spatial world child row/hash;
- ShotRevision spatial track state EntityRevision/transform/source-transition row;
- ShotRevision spatial plan hash/bytes;
- captured schema-5 `spatial_continuity` bytes vs nested world hash;
- workflow-spec-v3 spatial realization hash/document agreement;
- workflow-spec-v3 spatial runtime fingerprint agreement;
- package spatial binding target/format agreement.

Derived-execution corruption additionally covers spec/hash, runtime-fingerprint/hash, provenance→Blob identity, physical Blob bytes, `generation_derived_spatial_inputs`, workflow-spec artifact references, and structured-camera binding identity.

For each applicable cell:

```text
corrupt
→ relevant read/reuse/capture/execution fails closed
→ restore exact stored value
→ positive control succeeds/converges
```

No repair-by-recapture, current-state reconstruction, or friendly corruption alias is allowed.

---

# 64. Determinism gates

Mandatory deterministic fixtures cover:

- §6 transform/camera mathematical golden cases;
- shuffled input ordering for frame/state/axis capture → identical SpatialWorldRevision bytes/hash;
- axis ordering exactly `(axis.key, axis.id)`;
- shuffled track/transition database return order → identical effective staging bytes;
- axis side evaluation using arbitrary-precision integer arithmetic;
- plan key order / JSON formatting differences → identical canonical plan bytes/hash;
- SpatialContinuityPack shuffled source input → identical bytes/hash;
- ShotRevision schema lattice shuffled source rows → identical snapshot bytes;
- combined non-empty M8 + M10 workflow-spec-v3 fixture → identical bytes under shuffled source ordering;
- physically equivalent but numerically distinct accepted Euler tuples remain distinct if the tuples differ after component normalization;
- requirement values and exact EntityRevision provenance are hash-bearing where captured.

No determinism test may obtain stability by sorting on timestamps or relying on database row-return order.

---

# 65. Boundary semantics tests

Explicit temporal tests must pin:

```text
sequence/start
scene/start
shot/start
shot/end
scene/end
sequence/end
```

For a target Shot:

- transition at same Shot/start applies;
- transition at same Shot/end does not;
- prior Shot/end applies;
- clear produces canonical absence;
- re-set after clear restores state;
- unassigned Shot with relevant spatial transition data inherits `NARRATIVE_CONTEXT_REQUIRED` rather than inventing order.

---

# 66. Axis constraint tests

Required fixtures:

- §11 golden A/B/C example → positive;
- reflected C → negative;
- C on exact line → `SPATIAL_AXIS_CONSTRAINT_VIOLATION`;
- coincident X/Z endpoint coordinates in an included approved-world candidate → invalid capture;
- axis identity exists at world level but is absent from current state → cannot be selected by plan;
- state axis endpoint frame absent → rejected mechanically by composite FK/service validation;
- camera starts on allowed side and later keyframe crosses to forbidden side → violation;
- large JavaScript-safe coordinates whose cross-product exceeds 64-bit range still produce correct sign via arbitrary-precision server arithmetic;
- frontend/client calculations, if displayed, are advisory only and cannot override server result.

Dynamic-track endpoint axes are explicitly absent from schema-1 tests because they are deferred, not silently approximated.

---

# 67. Camera/blocking tests

Required fixtures:

- identity camera looks along world `-Z` under §6 basis;
- positive/negative yaw/pitch/roll golden orientations;
- optics values zero/negative/float → plan invalid;
- first camera keyframe must be t=0;
- camera/blocking times strictly increasing and unique;
- duration NULL permits only t=0 keyframes;
- blocking t=0 exact match to effective track → ready;
- mismatch → `SPATIAL_BLOCKING_STATE_MISMATCH`;
- Shot/end `set` + blocking + NULL duration → blocker;
- Shot/end `set` + blocking + non-NULL duration but no exact final keyframe → blocker;
- exact final blocking keyframe matches Shot/end set → ready;
- exact final blocking keyframe disagrees → blocker;
- Shot/end `set` with no blocking entry → valid persistent state declaration;
- no blocking entry → static effective staging remains captured;
- screen direction remains independent advisory intent; no client/server pixel inference;
- free-text `lens` or `camera_motion` conflicts do not trigger parser inference; numeric M10 plan remains authority.

---

# 68. No per-frame authority in schema 1

APR-065 remains a study boundary.

M10 schema 1 stores sparse keyframes but does not define authoritative interpolation between them. It therefore must not expose an API claiming:

```text
get exact authoritative camera transform at frame N
```

unless N is an explicitly authored keyframe/boundary.

A future frame-addressable schema may define interpolation, sample rate, rounding, and motion representation after a concrete use case requires it.

---

# 69. M10 / M9 compatibility and package/spec matrix

Published M9 history remains immutable.

- historical workflow-spec v1/v2 Generations execute unchanged;
- profile/package schema-1/2 predecessor packages remain valid under their frozen contracts;
- M10 does not rewrite existing Generation or ShotRevision rows;
- M10 does not migrate historical ShotRevision schemas 1–4 into schema 5;
- new Generation from an existing Shot captures schema 5 only when current M10 authority is actually non-empty;
- Exact Rerun never upgrades schema;
- §45 cross-product fixtures prove v3-capable packages still emit byte-exact lower workflow-spec v1/v2 when M10 is empty;
- the existing M9 visual compiler remains unchanged in semantic authority and receives only captured M8 authority;
- M10's spatial compiler is independent and receives only captured M10 authority.

A package/profile/manifest version number never implies that higher-schema output must be emitted. **Non-empty captured authority**, not installed capability, selects the higher workflow-spec schema.

---

# 70. M10 / M8 compatibility

M8 current and historical contracts remain byte-stable for Shots with no M10 authority.

When M10 authority is present:

- existing M8 pack bytes/hash are embedded unchanged inside schema 5;
- M8 normalized child rows are written/validated exactly as before;
- M10 never changes M8 facet/anchor approval semantics;
- M10 execution cannot write M8 authority.

A schema-5 snapshot with both M8 and M10 authority must prove that both nested blocks are individually byte-identical to their canonical builders.

---

# 71. M10 / M7 compatibility

M7 continuity-spec schema 1/2 remains unchanged.

M10 does not add spatial fields to `continuity_spec_json`; spatial state is a distinct production-authority block in ShotRevision snapshot schema 5.

SpatialTransition temporal coordinates reuse M7 narrative ordering but are not ContinuityFeature values.

This prevents metric transforms/camera data from polluting the semantic Feature grammar.

---

# 72. No authority transfer source gate

Static audit:

- spatial realization/compiler/worker/tracking-import modules must not import write-capable M10 authority services except narrowly whitelisted pure value/read modules;
- scan INSERT/UPDATE/DELETE destinations with self-proving positive/negative regex fixtures.

Dynamic SQL mutation spy covers:

```text
spatial readiness preview
new Generation creation
worker execution
Exact Rerun
tracking/reconstruction proposal processing when present
```

and forbids execution-caused writes to all mutable M10 authority tables:

```text
spatial_worlds
spatial_world_states
spatial_frames
spatial_world_state_frames
spatial_axes
spatial_world_state_axes
spatial_tracks
spatial_transitions
shot_spatial_plans
```

A deliberate forbidden `UPDATE spatial_worlds ...` under the spy is mandatory positive control.

ShotRevision historical child INSERTs during normal capture are explicitly allowed immutable persistence, not authority mutation.

Any tracking/reconstruction integration may write only proposal/staging-import workspace defined by a separately authorized contract; adoption into M10 authority remains an explicit user action through normal M10 write APIs.

---

# 73. Current-table query spy for history

Exact Rerun and worker execution of a captured workflow-spec-v3 Generation must show zero reads of current authority tables:

```text
spatial_worlds
spatial_world_states
spatial_frames
spatial_world_state_frames
spatial_axes
spatial_world_state_axes
spatial_tracks
spatial_transitions
shot_spatial_plans
```

Historical immutable tables, captured ShotRevision JSON, GenerationInputs, and captured artifact-store/package bytes may be read.

The spy has a positive control proving it catches a forbidden current SELECT before the historical zero-read assertion is accepted.

---

# 74. API surface — r3 contract direction

Proposed routes:

```text
POST   /projects/{project_id}/spatial-worlds
GET    /projects/{project_id}/spatial-worlds
GET    /spatial-worlds/{world_id}
PATCH  /spatial-worlds/{world_id}
DELETE /spatial-worlds/{world_id}

POST   /spatial-worlds/{world_id}/states
GET    /spatial-world-states/{state_id}

POST   /spatial-worlds/{world_id}/frames
PATCH  /spatial-frames/{frame_id}
DELETE /spatial-frames/{frame_id}
PUT    /spatial-world-states/{state_id}/frames/{frame_id}
DELETE /spatial-world-states/{state_id}/frames/{frame_id}

POST   /spatial-worlds/{world_id}/axes
PATCH  /spatial-axes/{axis_id}
DELETE /spatial-axes/{axis_id}
PUT    /spatial-world-states/{state_id}/axes/{axis_id}
DELETE /spatial-world-states/{state_id}/axes/{axis_id}

POST   /spatial-world-states/{state_id}/revisions
GET    /spatial-world-states/{state_id}/revisions
GET    /spatial-world-revisions/{revision_id}
PUT    /spatial-world-states/{state_id}/approval
DELETE /spatial-world-states/{state_id}/approval

POST   /spatial-worlds/{world_id}/tracks
PATCH  /spatial-tracks/{track_id}
DELETE /spatial-tracks/{track_id}
POST   /spatial-tracks/{track_id}/transitions
PATCH  /spatial-transitions/{transition_id}
DELETE /spatial-transitions/{transition_id}

GET    /shots/{shot_id}/spatial-continuity
PUT    /shots/{shot_id}/spatial-plan
DELETE /shots/{shot_id}/spatial-plan
```

Every write response returns server-authoritative identity/hash needed for the next CAS operation.

Base r3 does **not** add clone/diff convenience APIs, a generic JSON authoring endpoint, profile selection inside the Shot plan, or a rich 3D editor API. Those may be added later without changing authority semantics after core implementation proves need.

---

# 75. Canonical key grammars

Use the established lowercase semantic key grammar where possible:

```text
^[a-z0-9][a-z0-9._-]{0,127}$
```

Applies to:

- SpatialWorld.key;
- SpatialFrame.key;
- SpatialAxis.key.

Names are display metadata and do not substitute for keys.

Keys are case-sensitive canonical lowercase under validation and are never recycled after tombstoning.

---

# 76. Required service invariants

Service-layer validation proves semantic ownership beyond bare FK existence.

At minimum:

- SpatialWorld Project == Location Entity Project and Entity kind == location;
- Location EntityRevision belongs to exactly that world Location Entity and Project;
- frame/axis/state/track all belong to the same SpatialWorld when related;
- parent frame belongs to same world and stable parent graph is acyclic;
- included child frame's parent is also included in that state;
- state-axis endpoints are included frames in the exact same state;
- bound Entity belongs to world Project;
- bound EntityRevision belongs to bound Entity;
- fixed-frame EntityRevision matches Shot's exact semantic EntityRevision when that Entity is a Shot dependency;
- one effective Entity has at most one placement authority;
- track Entity belongs to same Project and active duplicate track requests translate to `SPATIAL_ENTITY_INSTANCING_UNSUPPORTED`;
- transition anchor belongs to same Project and valid canonical narrative topology;
- Shot plan world Location is a current Shot dependency;
- blocking track belongs to plan world and current dependent Entity;
- plan axis is included in the exact approved world revision;
- approved revision belongs to exact state;
- historical child IDs/hashes/positions exactly agree with nested canonical snapshot.

Same-Project-but-wrong-Entity and cross-Project references are never accepted merely because an FK exists.

---

# 77. M10A — domain/schema/source-fit + derived-execution integration slice

M10A begins from completed M10A-0 and M10A-1 evidence rather than an unknown executor.

After final r3 freeze it implements:

1. §6 math fixtures;
2. authority migration 0010;
3. derived-execution migration 0011;
4. canonical authority + derived schemas;
5. D0 materializer plumbing only for final-r3-frozen artifact kinds;
6. existing Blob semantics unchanged;
7. existing Asset/GenerationInput semantics unchanged;
8. sibling `generation_derived_spatial_inputs`;
9. package/profile/manifest schema evolution;
10. worker physical-Blob verification and historical isolation;
11. v1/v2 compatibility;
12. 0011→0010→0009 fail-closed downgrade gates.

Before r3 itself freezes, §114 closes live registration, GPU smoke, exact weights/commits, media/tensor grammar, control capacity, structured-camera production compatibility, and hidden-write behavior. Implementation may not discover those facts later.


---

# 78. M10B — world authority slice

Scope:

- SpatialWorld CRUD/policy;
- exact state creation per Location EntityRevision;
- stable frames + organizational parent DAG;
- explicit state-frame membership/value;
- stable axes + explicit state-axis membership/endpoints;
- one-placement-authority validation;
- canonical world revision capture with fenced drift recheck;
- immutable child projection/reuse integrity;
- approve/unapprove CAS;
- form/table-oriented world editor UI;
- corruption loop and race proofs.

Gate:

```text
Location rev A approved world A
→ Location approval changes to rev B
→ old world A does not apply
→ B needs explicit state membership/revision approval
```

No rich 3D editor is required for M10B closure.

---

# 79. M10C — temporal staging slice

Scope:

- SpatialTrack CRUD/policy;
- SpatialTransition create/edit/tombstone;
- random-access effective resolver;
- narrative-boundary semantics;
- current staging inspector;
- required/optional track readiness;
- deterministic capture projection;
- feature-film scale track/transition query gate.

Gate:

```text
same target Shot resolved directly
== result obtained regardless of prior API visitation order
```

---

# 80. M10D — Shot plan + schema-5 capture slice

Scope:

- ShotSpatialPlan canonical validation and full create/update/delete CAS lifecycle;
- exact pinhole optics + §6 camera pose semantics;
- sparse camera/blocking constraints with no interpolation authority;
- blocking/start/end persistent-state agreement;
- arbitrary-precision axis constraint;
- screen-direction advisory instruction;
- ONE spatial resolver;
- ShotRead computed fields + spatial endpoint;
- working-hash integration;
- ShotRevision schema-5 full compatibility cube;
- immutable spatial child persistence/reuse validation;
- historical spatial provenance API;
- form/table-oriented Shot spatial UI and current-vs-captured inspector.

Gate includes complete coherent-read BEFORE/AFTER races across plan/world membership/approval/transition/EntityRevision/requirement changes.

ShotRead spatial readiness/hash/issues remain computed server projections. No M10 hash/status column is added to `shots`.

---

# 81. M10E — model/executor spatial realization slice

M10E implements only the final-r3-frozen execution contract:

- independent pure spatial compiler;
- content-only D0 derivative specs;
- separate runtime fingerprint;
- derived Blob publish/convergence;
- immutable `derived_spatial_artifacts`;
- immutable `generation_derived_spatial_inputs`;
- workflow-spec v3 built only after all identities exist;
- explicit structured-camera and derived-artifact bindings only;
- worker historical state only;
- Exact Rerun Blob reuse without rematerialization;
- hard capacity/runtime/binding failures before queueing;
- explicit screen-direction omission only when allowed.

No graph heuristic, prompt fallback, current-state materialization, or extension-local cache authority.


---

# 82. M10F — adversarial closure/source gate

M10F runs the full frozen proof suite:

- exact migration/ORM parity and fail-closed downgrade preflight;
- transform/camera mathematical golden fixtures;
- complete r3 error mappings;
- immutable world/ShotRevision corruption→fail→restore loops;
- all races in §61, with real barriers and no sleeps;
- small-vs-representative current-resolution SQL counts;
- small-vs-representative first-Generation SQL counts including M10 historical persistence;
- representative schema-5 snapshot-size evidence;
- exact-rerun/worker current-table query spies;
- static + dynamic no-authority-transfer audit;
- ShotRevision schema-1..5 compatibility cube;
- workflow-spec v1..3/package/profile/manifest lattice;
- package/runtime replacement coherence;
- historical worker isolation;
- frontend no-client-recompute tests;
- operator/authoring documentation fixtures for coordinate convention, state membership, requirements, and current-vs-historical views;
- full backend suite twice;
- full frontend tests/typecheck/build;
- compileall;
- archive fidelity against exact audited commit;
- frozen plan bytes/hash inside archive.

Publication, M10 tag, GitHub Release, branch-protection changes, and later milestones remain separately authorized.

---

# 83. Critical proof — hotel lobby reverse angle

The canonical feature-film demonstration uses one Lobby Location across multiple Shots.

Production setup:

- Lobby Location EntityRevision 3;
- required SpatialWorld;
- approved world revision containing entrance, front desk, elevator-bank, columns, and conversation axis;
- Eva/desk-clerk tracks with effective staging;
- M8 approved appearance for lobby/Eva/desk clerk;
- Shot A camera on positive axis side;
- Shot B reverse-angle camera either intentionally remains on the allowed side or explicitly changes continuity rule.

Proof:

1. both ShotRevisions capture the same exact world revision hash where layout is intended unchanged;
2. staging source transitions are inspectable;
3. each camera pose/optics is exact and captured;
4. current later world edits do not rewrite either Shot;
5. a spatial-capable package receives exact captured M10 documents;
6. a package without spatial capability blocks rather than silently relying on prompt wording.

This proves requested continuity authority, not automatic pixel success.

---

# 84. Critical proof — moving character continuity

Example:

```text
Shot 20/start: Eva at lobby entrance
Shot 20/end:   explicit transition sets Eva near front desk
Shot 21/start: resolver must return front-desk transform directly
```

The proof resolves Shot 21 without ever resolving/playing Shot 20 first.

Then change Shot 20's rendered Take or current blocking UI without changing the explicit Shot/end SpatialTransition. Shot 21 spatial authority remains unchanged.

This proves production state is explicit rather than inferred from generated motion.

---

# 85. Critical proof — Location revision change

Lobby EntityRevision 3 has approved SpatialWorldRevision A.

Approve Lobby EntityRevision 4.

Expected:

```text
world requirement persists
state binding for rev3 does not transfer
rev4 without state/approval → spatial not ready
```

Creating a rev4 state by copying rev3 working values is allowed only as an explicit authoring action; capture/approval produces new state/revision identity.

---

# 86. Critical proof — current-state mutation vs history

Capture Generation G from schema-5 ShotRevision R with world revision W1 and camera plan P1.

Then mutate:

- world working frames;
- approve W2;
- change a SpatialTransition;
- change ShotSpatialPlan to P2;
- replace spatial-capable package/profile.

Historical Generation G and R must still report W1/P1 and execute from the captured spec.

New Generate may use W2/P2 only after current readiness succeeds.

---

# 87. Critical proof — unsupported executor

With a required non-empty M10 pack and the published M9 Hunyuan v4 package:

```text
spatial_continuity_ready = true
spatial_realization_ready = false
Generation creation = blocked
```

The error must say the selected package cannot realize captured spatial authority. It must not:

- drop the spatial block;
- downgrade workflow-spec schema;
- inject camera text into prompt;
- generate anyway with a warning.

---

# 88. Critical proof — tracking does not become authority

Any future test helper/proposal adapter that imports a camera solve or tracking result must end in an unapproved proposal/working edit.

It cannot update:

```text
SpatialWorldState.approved_revision_id
SpatialTransition authoritative state
historical ShotRevision
```

automatically.

If no tracking integration is implemented in M10, the source gate proves there is no such path and keeps APR-068 as a boundary invariant.

---

# 89. UI honesty requirements

UI labels must distinguish:

```text
Working world
Approved world
Current effective staging
Working Shot plan
Captured ShotRevision spatial authority
Current spatial realization readiness
Captured Generation spatial realization
```

Never label a current world/profile as what a historical Generation used.

Never imply readiness preview reserves the current world/package. Generate re-captures under the coherent creation path.

---

# 90. Output-claim boundary

M10 can prove request conformance:

> the exact captured world/staging/camera authority was translated into the exact declared spatial execution mechanism.

M10 does not prove by request conformance alone:

- generated pixels perfectly obey geometry;
- identity survives every occlusion;
- every frame is physically correct;
- tracking-derived corrections are canonical;
- every arbitrary viewpoint is identical to a deterministic CG renderer.

Take approval remains the human/production acceptance decision. Successful output is never automatically promoted to M8 or M10 authority.

---

# 91. Rejected/deferred base-plan enhancements and accepted schema-1 limits

Do **not** add merely because M10 exists:

- mesh/NeRF/Gaussian-splat database schema as core authority;
- generic 3D Asset kind without source-fit provenance contract;
- automatic photogrammetry/SLAM/tracking authority ingestion;
- per-frame spatial database rows;
- authoritative linear/Bezier/spline interpolation between sparse keyframes;
- skeletal animation/rigging system;
- physics simulation;
- automatic collision solver as authority;
- automatic camera planner/director;
- AI-selected best axis;
- automatic M7 Relation→geometry parsing or contradiction inference without a future relation type carrying a formally frozen geometric predicate;
- client-side transform/axis computation as authority;
- world resolver cache/materialized hash column without demonstrated performance need;
- distributed world-state service;
- multi-world composite Shots in schema 1;
- multiple simultaneous instances of one CreativeEntity identity in one effective world;
- dynamic axis endpoints following SpatialTracks;
- vertical/top-to-bottom screen-direction vocabulary in schema 1;
- per-Shot executor/profile selection inside ShotSpatialPlan;
- automatic default/origin SpatialTransition when a track becomes required;
- automatic output-to-world promotion;
- automatic carry-forward of world state across Location revisions;
- speculative clone/diff APIs or rich 3D editor before core authority workflows need them.

Accepted consequences:

```text
two required Location worlds on one Shot → blocked
second simultaneous same-Entity instance → unsupported
non-keyframe time → no authoritative transform claim
required track with no explicit effective set → blocked
required world/track policy may retroactively block future Generation readiness after explicit authoring change
```

Those are deliberate schema-1 limits, not implementation gaps.

---

# 92. Source-fit STOP conditions

Implementation must STOP and revise the plan if the frozen predecessor tree, migration implementation, or M10A source audit proves any of these assumptions false:

1. migration `0010` cannot add §7's tables/constraints without unsafe predecessor rebuild;
2. §6 mathematical convention cannot be implemented consistently across server/client fixture consumers;
3. current narrative ordering cannot provide stable shared anchors/ranks for SpatialTransitions;
4. exact Location/Entity revision context cannot be resolved coherently with ShotRevision capture;
5. schema-5 snapshot cannot preserve predecessor lower schemas byte-for-byte;
6. the first real spatial executor requires materialized derived bytes without a separately frozen deterministic Blob/provenance/retention/rerun contract;
7. executor requires hidden graph heuristics, prompt encoding, or current graph discovery instead of explicit captured bindings;
8. a real spatial package cannot consume all hard M10 execution components without silently dropping authority;
9. existing M9 execution identity does not pin new spatial runtime dependencies and no exact additive fingerprint can be frozen;
10. current worker architecture cannot verify/translate historical spatial bindings without reading current M10 authority;
11. feature-film-scale target resolution/Generation requires per-track/per-frame/per-keyframe SQL fan-out;
12. one needed authority fact cannot be represented without introducing a new semantic/spatial layer or silently reinterpreting an existing schema;
13. a proposed optimization requires denormalized current authority or cache invalidation that cannot be proven equivalent to the canonical resolver.

Priority:

```text
P0 milestone/source-contract STOP:
  unsafe migration
  ambiguous transform mathematics
  no explicit viable executor path
  executor authority loss/heuristics
  missing runtime identity
  derived-artifact contract required

P1 implementation STOP until corrected:
  historical isolation failure
  query-shape fan-out
  schema-lattice byte drift
  unrepresentable authority fact
```

A STOP triggers review. It is never permission for an ad hoc workaround.

---

# 93. Definition of Done — authority layer

- [ ] migration 0010 implements §7 exact 15-table contract and ORM metadata exactly matches.
- [ ] downgrade refuses before DDL whenever M10 authority/history cannot be proven absent.
- [ ] §6 coordinate/rotation/camera mathematics fixture-pinned with no ambiguous aliases.
- [ ] one active SpatialWorld per Location schema-1 invariant enforced.
- [ ] exact state membership for frames and axes enforced.
- [ ] parent DAG is organizational only and deterministic.
- [ ] state axis endpoints are exact included frames.
- [ ] extent frame-local semantics fixture-pinned.
- [ ] fixed-frame/track duplicate placement authority is impossible in an effective world.
- [ ] fixed bound EntityRevision ↔ exact Shot EntityRevision cross-check enforced.
- [ ] immutable world revisions capture/reuse fail closed and stale working capture conflicts explicitly.
- [ ] approval/unapproval expected-pointer semantics race-proven.
- [ ] SpatialTracks/Transitions resolve random-access with shared M7 rank function.
- [ ] captured staging includes exact active EntityRevision and requirement-at-capture.
- [ ] required/optional world/track readiness exact.
- [ ] ShotSpatialPlan CAS lifecycle exact for create/update/delete.
- [ ] pinhole camera/blocking/axis contracts exact.
- [ ] Shot/end blocking handoff rule closes NULL-duration/missing-final-keyframe cases.
- [ ] no free-text camera/lens/relation inference.
- [ ] ONE current spatial resolver used everywhere.
- [ ] ShotRead/spatial endpoint are computed server-owned projections; no current hash column added to Shot.
- [ ] working hash includes M10 when applicable.
- [ ] ShotRevision schema-5 compatibility cube has no empty higher schema.
- [ ] embedded world snapshot cross-hashes to exact SpatialWorldRevision.
- [ ] historical child projections match embedded canonical bytes.
- [ ] existing projects receive no fabricated M10 backfill.
- [ ] current vs historical spatial state visually explicit.

Authority-layer completion alone is recordable as slice progress but does **not** close M10 without §94.

---

# 94. Definition of Done — realization/execution layer

- [ ] M10A source-characterizes at least one real explicit spatial-capable execution path before milestone closure.
- [x] generic derived spatial artifact provenance/determinism/retention/rerun contract frozen by M10A-1.
- [ ] complete mechanically certified M10A-1 evidence/report hashes recorded.
- [ ] initial selected derivative path remains D0; D1 unused.
- [ ] live registration + functional GPU smoke passes before final r3 freeze.
- [ ] exact new model/control weight hashes and runtime commits frozen.
- [ ] composited depth alone is not accepted as full staging transport; required Entity placement uses independent/non-occluding representation.
- [ ] resolution-bound raster survivability class frozen.
- [ ] profile-schema-2 / manifest-package-schema-3 exact binding grammar frozen from source-fit.
- [ ] package/profile/manifest/workflow-spec cross-product fixtures from §45 pass.
- [ ] package lacking spatial capability blocks non-empty M10 hard execution components.
- [ ] hard vs advisory capability semantics exact; screen-direction omission is explicit and captured if unsupported.
- [ ] ONE pure spatial realization compiler.
- [ ] M9 visual and M10 spatial compilers remain independent and deterministically composed.
- [ ] workflow-spec v3 only for non-empty spatial realization.
- [ ] workflow-spec v1/v2 bytes remain exact lower paths even under v3-capable package.
- [ ] M10 runtime fingerprint proves every material spatial dependency not already covered by M9 identity.
- [ ] worker binds only explicit captured spatial targets.
- [ ] no graph heuristics/prompt fallback.
- [ ] worker reads zero current M10 authority.
- [ ] Exact Rerun copies workflow-spec-v3 specification verbatim.
- [ ] request-conformance claim remains distinct from pixel/geometry/interpolation success claim.

If this checklist cannot be completed because no viable executor exists, M10 remains open; the authority layer is not relabeled as complete M10.

---

# 95. Definition of Done — proof/evidence/operations

- [ ] all M10-owned errors fixture-pinned with positive/negative controls.
- [ ] corruption→fail→restore loops pass for immutable world + ShotRevision projections.
- [ ] all §61 races prove complete serializations/conflicts with no sleeps.
- [ ] representative ~2,500-Shot matrix exercises full target family.
- [ ] small == representative SQL statement class/count for current resolution.
- [ ] small == representative first-Generation SQL statement count on comparable first-capture states.
- [ ] no per-track/per-frame/per-keyframe SQL fan-out.
- [ ] representative snapshot/world-duplication byte metrics recorded.
- [ ] dynamic no-authority-transfer spy has forbidden-write positive control.
- [ ] historical read spy has forbidden-current-read positive control.
- [ ] axis arithmetic >64-bit intermediate fixture passes.
- [ ] combined M8+M10 workflow-spec-v3 shuffled-order golden fixture passes.
- [ ] backend full suite passes twice.
- [ ] frontend tests/typecheck/build pass.
- [ ] compileall passes.
- [ ] authoring/operator docs explain coordinate/camera convention, state membership, requirement consequences, schema-1 limitations, recovery from blockers, and current-vs-captured history.
- [ ] backup/restore includes all M10 authority plus historically live derived provenance/Blob bytes.
- [ ] D0 repeatability N>=3 identical source/spec/runtime → exact Blob SHA equality.
- [ ] derived Blob publish convergence race proven.
- [ ] physical derived Blob corruption→fail→restore proven.
- [ ] Exact Rerun derived-input spy proves zero current M10 reads and zero rematerialization.
- [ ] materializer/worker/GC no-authority-transfer spy has positive control.
- [ ] archive regeneration from audited commit is byte-identical.
- [ ] frozen M10 plan hash inside archive is byte-identical.

---

# 96. M10 handoff state

At M10 closure SoloRing should be able to state:

> For this ShotRevision, these exact semantic/design revisions were active; these exact M8 references defined approved appearance; this exact M10 world revision defined the stable spatial layout; these exact staging transitions defined where movable entities were; this exact camera/blocking/axis plan defined the intended cinematic view; and this exact model/executor request attempted to realize those captured authorities. Current edits cannot rewrite that history.

This is the feature-film continuity handoff from production authority to later editorial/finishing systems.

---

# 97. Relationship to future editorial / finishing

M10 is not the final production platform.

After M10, future work may include:

- tracking/roto-based corrections;
- compositing/paint;
- color management/grading;
- frame-addressable VFX state;
- editorial timelines;
- audio;
- conform/mastering/delivery;
- stronger geometric/surface representations;
- automatic continuity QC that reports but does not redefine authority.

Those areas remain unnumbered/unplanned until separately authorized.

---

# 98. r3 integrated architectural decisions

r3 preserves the r2 authority decisions and adds source-fit-backed execution decisions. A future change before implementation requires a reviewed plan revision; after frozen history exists it requires a versioned architecture change.

1. **Authority substrate:** technology-neutral metric world graph, not mesh/NeRF/splat/depth authority.
2. **World cardinality:** at most one active SpatialWorld per Location; exact Location EntityRevision selects explicit state.
3. **State membership:** frames and axes are explicitly included per SpatialWorldState; no implicit all-world membership.
4. **Transforms:** absolute world poses; parent frames organizational only; exact active local→world intrinsic Y-X-Z matrix convention from §6.
5. **World/camera basis:** right-handed +X right, +Y up, +Z depth-positive/back; canonical forward and camera view axis are `-Z`.
6. **Authored Euler identity:** per-component normalized integer tuple is authority; physically equivalent different tuples are not silently collapsed.
7. **Units:** integer millimeters + microdegrees; frame-local integer-mm coarse half extents; no float identity and no scale matrix.
8. **Placement multiplicity:** one effective placement authority per CreativeEntity identity; duplicate simultaneous instances deferred.
9. **Track cardinality:** one active track per `(world,entity)`; exact EntityRevision attached at Shot capture.
10. **World cardinality per Shot:** one selected world; multi-world composites hard-block/deferred.
11. **Sparse keyframes:** no authoritative interpolation between authored times.
12. **Axes:** static-frame endpoints, exact arbitrary-precision X/Z side predicate; dynamic track endpoints deferred.
13. **Screen direction:** horizontal advisory production intent, not pixel-derived validation; unsupported executor consumption must be explicit/captured.
14. **Shot plan:** canonical atomic JSON + exact create/update/delete CAS lifecycle.
15. **Shot/end handoff:** blocking track + Shot/end set requires non-null duration and exact final blocking keyframe match.
16. **ShotRevision schema 5:** any non-empty M10 pack; no empty schema 5; embedded world snapshot remains self-contained and cross-hashed.
17. **Workflow-spec schema 3:** only non-empty M10 spatial realization; v3-capable package emits exact v1/v2 lower schema when M10 empty.
18. **Compiler composition:** independent pure M9 visual + M10 spatial compilers, merged deterministically at one workflow-spec builder.
19. **Unsupported executor:** hard execution-component mismatch blocks; no prompt fallback.
20. **Runtime identity:** M10 extends captured execution fingerprint whenever new spatial dependencies are not already pinned by M9.
21. **Derived artifacts:** no materialized spatial bytes without a separately frozen provenance/determinism/retention/rerun contract.
22. **No generic 3D Asset widening** in the base plan.
23. **No automatic backfill/carry-forward/default-origin transitions.**
24. **M7 relation boundary:** no automatic relation→geometry parsing or contradiction checking without a future formally geometric relation contract.
25. **Temporal/environment variants:** spatially material Location changes use exact semantic/design revision + explicit state; visual-only day/night/weather does not invent M10 state.
26. **UI scope:** reliable server-owned form/table authoring first; rich 3D editor deferred.
27. **Milestone closure:** authority DoD and realization DoD are separate ledgers, but both are required to close/tag M10.
28. **World requirement history:** world requirement is captured in schema-5 authority.
28a. **DB placement backstop:** state-frame membership carries denormalized bound Entity identity solely to enforce one fixed placement per Entity with a partial UNIQUE.
29. **Semantic keys:** World/Frame/Axis keys are immutable.
30. **World-state identity:** no ordinary state delete/recreate lifecycle.
31. **Derived storage:** migration 0011 + owner-free Blob + immutable provenance; no Asset fabrication.
32. **Generation input split:** existing M9 inputs unchanged; derived spatial inputs use an explicit sibling relation.
33. **Derived identity:** content-only spec hash + separate runtime-fingerprint hash.
34. **Initial determinism:** D0 only; D1 deferred.
35. **Raster honesty:** finite raster controls have a resolution-bound execution-equivalence class.
36. **Occlusion:** a single composite is insufficient for every staged Entity; independent/non-occluding Entity representation is required.
37. **Camera:** initial package selects derived Path B; no separate structured-camera binding is claimed.
38. **Materialization:** heavy work outside writer; final authority revalidation is mandatory.
39. **Exact Rerun:** historical derived bytes are reused, not regenerated from current state.
40. **Final source-fit:** live/GPU/weights/capacity/cache/media grammar close before final r3 freeze.

These are no longer open r1 review questions.

---

# 99. Proposed implementation sequence after completed pre-freeze source-fit

```text
M10A-0 COMPLETE → STOP_DERIVED_ARTIFACT_CONTRACT_REQUIRED
M10A-1 COMPLETE → PASS_TO_M10_R3
M10 r3 §114 final empirical gate COMPLETE
    → live registration/GPU smoke/weights/capacity/media grammar PASS
M10 r3 ARCHITECTURE FREEZE
M10A → math + 0010/0011 + execution-contract implementation
M10B → world authority
M10C → temporal staging
M10D → Shot plan + schema-5 capture
M10E → structured + D0 derived realization / worker / Exact Rerun
M10F → adversarial closure/source gate
```

§114 occurs before implementation authorization. Implementation may not choose a different artifact grammar, model weight, control capacity, custom node, or cache policy.


---

# 100. Authorization boundary

This r3 document is the **frozen M10 architecture / implementation contract**, but it does not authorize implementation. The §114 evidence bundle is a separately certified companion record.

It does not authorize:

- creating branch `m10/...`;
- migration/source implementation;
- package/profile changes;
- Comfy/custom-node/model/control-model installation;
- derived geometry/depth/pose artifact introduction;
- publication;
- tag `M10`;
- branch-protection changes;
- GitHub Release;
- future editorial/finishing planning;
- carried housekeeping work.

Before implementation authorization, r3 must pass §120, including the remaining §114 live/GPU source-fit and evidence-certification gates. Any accepted correction produces a new candidate. Only the exact reviewed final bytes are then mechanically frozen with SHA-256 and become the implementation contract.

The predecessor baseline remains immutable and must always be cited exactly:

> **Predecessor baseline: M9 @ `36ca78ad3b4c9377f746b31b2db4350b5684fc22`**

The tag `M9` never moves.

---

---

# 101. M10A-0 / M10A-1 empirical evidence input

r3 treats the following as source-fit evidence inputs, not production authority.

## 101.1 M10A-0 established facts

The completed source-fit reported:

- published M9 baseline and four-artifact package/fingerprint seams verified;
- current production ComfyUI/GGUF runtime pinned and whitelist-restricted;
- core camera-control support exists but the pinned core arbitrary-camera surface is insufficient for unrestricted authored keyframes;
- an external CameraCtrl family exposes an explicit arbitrary camera trajectory STRING grammar containing per-frame intrinsics plus 3×4 world-to-camera extrinsics;
- core VACE/FunControl/ControlNet-style mechanisms consume materialized control media;
- no reviewed mechanism consumes the complete M10 world/staging/blocking graph as structured numeric authority;
- prompt/graph heuristics are not viable;
- materialized derived bytes are required for the missing hard-component transport.

Terminal disposition:

```text
STOP_DERIVED_ARTIFACT_CONTRACT_REQUIRED
```

## 101.2 M10A-1 established facts

The completed derived-artifact characterization reported:

- M9 `blobs` is owner-free and suitable as the physical content-addressed byte substrate;
- M9 `generation_inputs` is Asset-backed and must remain semantically unchanged;
- a D0 reference CPU materializer identified as `soloring.boxdepth.rasterizer` version `1.0.0` produced byte-identical outputs across repeated in-process, cross-process, wall-clock, shuffled-order, and canonical-roundtrip probes;
- visible spatial authority differentials including millimeter, microdegree, micrometer-optics, and millisecond timing changes altered reference derivative bytes in the exercised fixture;
- a single composited depth channel can erase fully occluded staged Entities;
- per-Entity independent layers preserve placement information hidden by composite occlusion in the exercised fixture;
- finite raster resolution cannot guarantee that every arbitrarily small image-parallel metric change alters sampled bytes;
- reverse-angle behavior was exercised at the derivative grammar/reference-materializer level;
- source-pinned `WanVideoControlnetApply.control_images` resolves through the published M9 exact binding-validation seam;
- live external-node registration and functional GPU/model execution were not performed.

Terminal disposition:

```text
PASS_TO_M10_R3
```

## 101.3 Evidence certification requirement

The final r3 freeze record must contain full exact digests for:

```text
M10A-0 evidence manifest
M10A-0 final report
M10A-1 evidence manifest
M10A-1 final report
§114 final live/GPU source-fit evidence manifest/report
```

No truncated digest is sufficient.

---

# 102. Migration 0011 — derived spatial execution provenance

Migration `0010` remains the 15-table production-authority migration.

Migration `0011_m10_derived_spatial_execution` adds exactly two execution/provenance tables:

```text
derived_spatial_artifacts
generation_derived_spatial_inputs
```

No `Asset.kind` change. No nullable rewrite of `generation_inputs.asset_id`. No derived columns on M10 authority tables.

## 102.1 `derived_spatial_artifacts`

```text
id                                String(36) PK
project_id                        String(36) NOT NULL FK projects.id RESTRICT

spec_schema_version               INTEGER NOT NULL CHECK = 1
spec_json                         TEXT NOT NULL
spec_hash                         TEXT NOT NULL CHECK length=64

spatial_continuity_schema_version INTEGER NOT NULL CHECK = 1
spatial_continuity_hash           TEXT NOT NULL CHECK length=64

artifact_kind                     TEXT NOT NULL
artifact_schema_version           INTEGER NOT NULL CHECK > 0
algorithm_id                      TEXT NOT NULL
algorithm_version                 TEXT NOT NULL

runtime_fingerprint_json          TEXT NOT NULL
runtime_fingerprint_hash          TEXT NOT NULL CHECK length=64

determinism_class                 TEXT NOT NULL CHECK = 'D0'

blob_hash                         TEXT NOT NULL FK blobs.hash RESTRICT
media_type                        TEXT NOT NULL
created_at                        TEXT NOT NULL

UNIQUE(project_id, spec_hash, runtime_fingerprint_hash)
UNIQUE(id, blob_hash)
INDEX(spec_hash, runtime_fingerprint_hash)
INDEX(project_id, spatial_continuity_hash)
INDEX(blob_hash)
```

`spec_json` is canonical `DerivedSpatialArtifactSpec`. `runtime_fingerprint_json` is canonical but not part of `spec_hash`.

Immutable projection checks require:

```text
SHA-256(spec_json canonical bytes) == spec_hash
parsed source schema/hash == spatial_continuity_schema_version/hash columns
parsed artifact kind/schema == artifact_kind/artifact_schema_version columns
parsed algorithm id/version == algorithm_id/algorithm_version columns
SHA-256(runtime_fingerprint_json canonical bytes) == runtime_fingerprint_hash
runtime materializer algorithm id/version == spec derivation algorithm id/version
parsed output media_type == media_type column
physical Blob SHA-256 == blob_hash
```

For D0 there are **two distinct constraints**:

```text
project provenance uniqueness:
same project + spec_hash + runtime_fingerprint_hash
→ at most one project-owned provenance row

global deterministic-result functional dependency:
same spec_hash + runtime_fingerprint_hash
→ exactly one blob_hash across every Project
```

The second rule is deliberately global even though provenance rows remain Project-owned.

SQLite schema 1 enforces the global rule in the content-addressed convergence transaction under `BEGIN IMMEDIATE`:

1. query all existing `derived_spatial_artifacts` rows for `(spec_hash, runtime_fingerprint_hash)` without Project filtering;
2. if any exist, every row must name one identical `blob_hash`;
3. a differing Blob is `DERIVED_SPATIAL_NONDETERMINISTIC` / invariant failure and the new row is not inserted;
4. if the global Blob already exists and verifies physically, a new Project may insert its own provenance row referencing that same Blob;
5. only then persist the Project-owned provenance row.

The §118 duplicate-materialization race proves this check under real barriers. A future multi-writer database backend must provide an equivalent global serialization primitive or normalize this functional dependency into a dedicated global result table before claiming parity.

`shot_revision_id` is not derivation identity. The exact historical ShotRevision is bound by the Generation and cross-validated against `spatial_continuity_hash`.

## 102.2 `generation_derived_spatial_inputs`

```text
generation_id               String(36) NOT NULL FK generations.id RESTRICT
input_key                   TEXT NOT NULL
position                    INTEGER NOT NULL CHECK >= 0
artifact_role               TEXT NOT NULL
derived_spatial_artifact_id String(36) NOT NULL
blob_hash                   TEXT NOT NULL CHECK length=64

PRIMARY KEY(generation_id, input_key, position)

FK (derived_spatial_artifact_id, blob_hash)
   → derived_spatial_artifacts(id, blob_hash) RESTRICT
FK blob_hash → blobs.hash RESTRICT

UNIQUE(generation_id, artifact_role, position)
INDEX(derived_spatial_artifact_id)
INDEX(blob_hash)
```

Service validation proves:

```text
Generation → ShotRevision → Shot → Project
==
DerivedSpatialArtifact.project_id
```

and:

```text
Generation's ShotRevision spatial_continuity_hash
==
DerivedSpatialArtifact.spatial_continuity_hash
```

## 102.3 Downgrade

`0011 → 0010` performs a fail-closed preflight before DDL and refuses if:

- either 0011 table has rows;
- any historical workflow-spec references derived spatial provenance;
- malformed workflow-spec bytes prevent proving absence.

Only an unused 0011 schema can be dropped. `0010 → 0009` is not attempted while 0011 is applied.

---

# 103. Canonical DerivedSpatialArtifactSpec schema 1

Canonical derivation identity is content-based M10 authority, not a DB row id.

Base shape:

```json
{
  "schema_version": 1,
  "artifact_kind": "<closed-kind>",
  "artifact_schema_version": 1,
  "source": {
    "spatial_continuity_schema_version": 1,
    "spatial_continuity_hash": "<sha256>"
  },
  "derivation": {
    "algorithm_id": "<closed-id>",
    "algorithm_version": "<immutable-version>",
    "parameters": {}
  },
  "output_contract": {
    "media_type": "<closed>",
    "encoding": "<closed>",
    "width": 0,
    "height": 0,
    "frame_count": 0,
    "time_base_num": 0,
    "time_base_den": 0
  }
}
```

Rules:

- no ShotRevision id;
- no Generation id;
- no UUID/timestamp/hostname/temp path;
- no runtime fingerprint;
- no mutable package/install path;
- every default derivation parameter is explicit;
- integer/rational domains in canonical identity unless a concrete schema freezes another exact representation;
- existing SoloRing canonical serializer;
- `spec_hash = SHA-256(exact canonical JSON bytes)`.

Different specs may legitimately converge to identical physical Blob bytes. Spec/provenance identity is not Blob identity.

For the candidate depth role family, `derivation.parameters` must distinguish projection scope explicitly. Before final freeze it will contain a closed shape equivalent to:

```json
{
  "scope": "world|entity",
  "entity_id": null,
  "placement_source_kind": null,
  "placement_source_id": null,
  "proxy_geometry": null,
  "sampling": {},
  "projection": {}
}
```

For `scope=entity`, the Entity and exact placement-source identity are non-null. Different Entity layers therefore cannot accidentally share one semantic spec merely because their raster bytes happen to match.

---

# 104. Materializer runtime fingerprint schema

Runtime identity is separate from the derivation spec.

Initial shape:

```json
{
  "schema_version": 1,
  "materializer": {
    "algorithm_id": "<same semantic algorithm id>",
    "algorithm_version": "<same version>",
    "implementation_sha256": "<sha256>"
  },
  "runtime": {
    "python": "<exact if material>",
    "numpy": "<exact if material>",
    "platform_contract": "<closed>"
  },
  "external_components": [
    {
      "kind": "<closed>",
      "name": "<closed>",
      "version_or_commit": "<immutable>",
      "sha256": "<sha256-or-null only when immutable source identity is sufficient>"
    }
  ]
}
```

Initial M10 uses D0 only:

```text
same spec_hash
+ same runtime_fingerprint_hash
→ same physical Blob SHA-256
```

Cross-runtime byte equality is not claimed.

---

# 105. Initial D0-only policy

Although M10A-1 defines a reviewed D1 class, initial M10 does not use it.

```text
determinism_class = D0
```

D1 requires a future reviewed plan revision.

The production materializer must eliminate identity-significant timestamps, random UUIDs, stochastic sampling, unordered traversal, mutable settings, uncontrolled encoder metadata, network-dependent content, and hidden extension caches.

Source gate repeats identical source/spec/runtime materialization at least three times and requires exact Blob SHA equality.

---

# 106. Spatial raster execution survivability class

Exact M10 authority is richer than a finite raster.

r3 therefore separates:

```text
authority identity
    exact spatial_continuity_hash

execution derivative identity
    exact spec/runtime/blob provenance

raster distinguishability
    finite resolution-bound survivability/equivalence class
```

The selected raster contract does not assert:

```text
different M10 authority → always different raster bytes
```

For fixed derivation/runtime, two different authority states may produce identical Blob bytes when their differences do not alter any sampled output value.

This does not merge authority: source/spec hashes and historical provenance remain different.

A complete hard **component** may not be omitted. The survivability contract applies to finite sampling precision inside an explicitly transported component.

---

# 107. Candidate depth-derived role family

The M10A-1 characterization supports a depth-like coarse spatial representation as the initial candidate family.

Logical roles:

```text
spatial.world_depth
spatial.entity_depth
```

Final artifact kind names/media grammar remain §114 freeze-gate outputs.

## 107.1 `spatial.world_depth`

View-dependent derivative of authored world occupancy:

- exact approved SpatialWorldRevision;
- exact camera/sample times;
- state frames with authored `half_extents_mm` contribute coarse oriented occupancy;
- appearance is excluded;
- no fine surface is fabricated for frameless landmarks.

A frame without extents may remain important to camera/axis/plan validity upstream without becoming visible geometry.

## 107.2 `spatial.entity_depth`

One independent view-dependent placement layer for one exact effective Entity placement.

Purpose: prevent another foreground object from erasing the Entity's spatial signal in a single z-composited control stream.

Canonical ordering:

```text
(entity_id, placement_source_kind, placement_source_id)
```

The proxy-geometry rule for movable Entities is an explicit §115 execution contract because M10 track authority contains pose, not authoritative surface geometry.

---

# 108. Occlusion and per-Entity layers

A single composited depth stream is insufficient for staging-component coverage when a required Entity is fully occluded.

Initial rule:

```text
every required current dependent Entity with effective M10 placement
must have an independently addressable non-occluded execution channel
```

Preferred candidate: repeated `spatial.entity_depth` roles.

A future alternative packing is allowed only after reviewed source-fit proves deterministic Entity identity/order, complete occlusion-independent representation, explicit package capacity, and no silent placement loss.

If representative required Entity count exceeds source-proven executor capacity, r3 does not freeze that path.

---

# 109. Initial camera execution disposition — derived Path B

The §114 production smoke did **not** validate a separate structured-camera binding with the selected Wan2.1 + depth-ControlNet path.

Initial M10 therefore freezes **Path B**:

```text
captured M10 camera optics + camera keyframes
→ deterministic derivation-time camera sampling
→ world/entity depth-control frames rendered from that exact sampled camera
→ explicit WanVideoControlnet control_images binding
```

There is no independent `spatial.camera` structured executor input in the initial package.

Camera remains a hard M10 production component because it changes the exact derivative specification and every view-dependent derived frame. The finite raster survivability rule of §106 applies: distinct exact camera states may occasionally sample to identical raster bytes, but their authority/spec provenance remains distinct.

This choice does **not** declare structured camera impossible. A future package/profile version may add Path A only after a separately reviewed source-fit proves a production-compatible exact binding and updates the workflow/package grammar. It does not require an M10 authority-schema change.

No free-text camera prompt and no preset-only substitution are permitted.

---

# 110. Workflow-spec schema 3 — derived integration

Workflow-spec v3 remains selected by non-empty M10 spatial realization.

Target spatial block:

```json
{
  "spatial_realization": {
    "schema_version": 1,
    "spatial_continuity_hash": "<sha256>",
    "structured_bindings": [],
    "derived_artifacts": [
      {
        "input_key": "<manifest input key>",
        "position": 0,
        "artifact_role": "spatial.world_depth",
        "derived_spatial_artifact_id": "<id>",
        "spec_hash": "<sha256>",
        "runtime_fingerprint_hash": "<sha256>",
        "blob_hash": "<sha256>"
      }
    ],
    "advisory_omissions": []
  }
}
```

The exact final JSON grammar is frozen after §114 live source-fit.

Already closed:

- runtime/provenance identities exist before workflow-spec construction;
- no provisional workflow-spec mutation;
- binaries are referenced rather than embedded;
- workflow-spec hash covers all identities;
- v1/v2 lower-schema bytes remain exact when M10 is empty;
- Exact Rerun copies the historical block verbatim.

---

# 111. Profile/package/manifest evolution

M10 keeps executor/package selection in the M9 realization layer. There is no per-Shot package override in `ShotSpatialPlan`.

Final selected package uses:

```text
RealizationProfile schema 2
workflow-package descriptor schema 3
manifest schema 3
```

Required capability concepts:

```text
structured spatial roles
derived artifact roles
role cardinality/capacity
accepted byte/tensor grammar
exact node/field binding
runtime requirements
advisory omission capability
```

Manifest mapping remains exact:

```text
logical role → node id → field name
```

Repeated `spatial.entity_depth` ordering/cardinality is explicit. No graph heuristics.

---

## 111.1 Initial source-proven package limits

The §114 smoke establishes a **conservative supported profile**, not an extrapolated maximum.

Initial profile:

```text
executor family:
    Wan2.1 T2V 1.3B + TheDenk depth ControlNet
wrapper commit:
    088128b
ComfyUI commit:
    b963f4ad210a42841ab23dfc28a84143a0cce227

derived control stream capacity:
    max_control_streams = 3

canonical role allocation:
    1 × spatial.world_depth
    up to 2 × spatial.entity_depth

smoked raster:
    width = 832
    height = 480
    pixel-frame count = 17
    control sampling = every pixel frame / stride 1

wrapper execution facts:
    scheduler = unipc
    T2V uses WanVideoEmptyEmbeds
    VAE decode uses WanVideoDecode
    UMT5 must be the fp16 path for the smoked wrapper surface
```

`max_control_streams = 3` is intentionally frozen because **three** simultaneous streams were functionally proven and capacity-to-failure above three was not explored. This is not a claim that the executor cannot support more.

Consequences:

```text
world stream + 0..2 required Entity streams → supported by initial profile
world stream + 3+ required Entity streams → SPATIAL_REALIZATION_UNSUPPORTED / capacity block
```

No stream truncation or Entity omission is allowed.

The exact physical depth→uint8 conversion, background sentinel, proxy-box parameters, model/control full SHA-256 values, and disposable workflow fixtures are normative parts of the externally certified §114 evidence bundle. Their full values were not supplied to this sandbox, so this document does not fabricate them from the reported prefixes. Implementation must import those exact values from the companion evidence record before code is accepted by the M10A source gate.

---

# 112. Derived materialization transaction seam

Heavy materialization occurs outside the DB writer:

```text
coherent current authority read
→ freeze ShotRevision candidate
→ compute spatial_continuity_hash
→ build content-only derivative specs
→ materialize + publish D0 Blobs
→ final BEGIN IMMEDIATE
→ rerun canonical M10 resolver
→ recompute current spatial_continuity_hash
→ require exact equality
→ persist ShotRevision + Generation aggregate
```

On drift:

```text
DERIVED_SPATIAL_CAPTURE_CONFLICT
```

No attachment to an inferred BEFORE or AFTER state.

Published-but-unreferenced derivative bytes remain non-authoritative and follow §117 retention policy.

---

# 113. Exact Rerun and historical derived bytes

Exact Rerun copies:

```text
workflow-spec
existing GenerationInputs
generation_derived_spatial_inputs
model/package/runtime identities
```

It validates derivative provenance plus physical Blob SHA-256.

It does not run the current M10 resolver, rebuild specs, run the materializer, choose current controls/packages, or inspect current M10 authority.

Current materializer absence is not fatal if historical derived bytes and executor package remain executable.

---

# 114. Final r3 empirical freeze evidence — PASSED

The authorized final source-fit was executed after architecture review. The review reported **no architecture blockers** and the empirical gate passed.

## 114.1 Live registration — PASS

Disposable executor:

```text
ComfyUI commit
    b963f4ad210a42841ab23dfc28a84143a0cce227

selected wrapper commit
    088128b

policy shape
    disable all custom nodes
    explicit selected-wrapper whitelist
```

The disposable executor registered 993 classes. `WanVideoControlnet` / `WanVideoControlnetApply` registered live with the seven source-verified inputs, including `control_images`. No unexpected plugin was reported.

The production executor remained separate and untouched.

## 114.2 Functional GPU smoke — PASS

Hardware:

```text
RTX 3080 Ti
```

Selected path:

```text
Wan2.1 T2V 1.3B
+ TheDenk depth ControlNet
+ three chained control streams:
    world composite
    Eva independent layer
    DeskClerk independent layer
```

Fixed-seed runs:

```text
A  full controls
B  no controls
C  DeskClerk moved +1 m
```

All final corrected runs produced genuine 17-frame 832×480 generations with pairwise-distinct output hashes. Display prefixes reported by the source-fit are:

```text
A  2478d513…
B  4762d44b…
C  f9659bfd…
```

These prefixes are descriptive only; the full hashes live in the companion evidence bundle.

The source-fit explicitly disclosed and rejected invalid intermediate smoke attempts, including a stale save-node link that had saved one-frame control images while pruning the sampler subgraph. The final PASS was issued only after frame-count/output verification and a clean rerun.

This proves a non-vacuous conditioning effect. It does not prove pixel-perfect obedience.

## 114.3 Runtime/model pins — PASS as companion evidence

The external evidence bundle records full hashes for the selected base/control/text/VAE artifacts and both runtime commits.

Reported display prefixes:

```text
base model       be531024…
controlnet       b7c6835f…
UMT5 fp16        7b8850f1…
VAE              2fc39d31…
```

The full digests are normative in the external `SHA256SUMS`; this plan does not invent missing suffixes.

## 114.4 Hidden-write audit — PASS

Before/after tree audits reported:

```text
wrapper tree  266 files  byte-identical
model tree     41 files  byte-identical
```

No fused-model writes, download-on-first-run behavior, generated extension cache, or unrecorded model conversion was observed.

## 114.5 Media/tensor grammar — PASS for the frozen initial profile

The smoke established these binding facts:

- `control_images` is the exact ControlNet transport;
- control media must cover the **full pixel-frame video** for the smoked path;
- stride/subsampling that under-produces latent-time control states is invalid;
- initial frozen profile uses 17 control frames at 832×480;
- exact depth→uint8 conversion and proxy raster byte grammar are pinned by the external materializer/evidence record;
- the wrapper's relevant execution facts include `unipc`, `WanVideoEmptyEmbeds`, `WanVideoDecode`, explicit VAE precision behavior, and fp16 UMT5.

No unspecified library default may replace the evidence-pinned grammar.

## 114.6 Survivability — PASS with explicit limitation

M10A-1 differential evidence demonstrated:

- visible millimeter/microdegree/micrometer-optics changes can survive into derivative bytes in the exercised fixture;
- fully occluded Entity placement disappears from one composited depth channel;
- independent Entity layers restore non-occluded transport;
- no finite raster guarantees byte-distinguishability for every arbitrarily small image-plane delta.

§106 is therefore the frozen representational claim.

## 114.7 Capacity — PASS, conservatively frozen at 3

The source-fit proved three simultaneous chained depth-control streams.

Capacity-to-failure above three was **not** explored.

Initial package/profile capacity is therefore frozen as:

```text
max_control_streams = 3
```

This is a conservative supported ceiling, not a measured hardware maximum. A later package version may raise it only after additional source-fit evidence.

## 114.8 Evidence certification — external companion record

The source-fit reports:

```text
C:\AI\M10R3-evidence
91-file SHA256SUMS
```

and states that the complete M10A-0/M10A-1 digests were recorded there.

Those files are not mounted in this authoring environment. Accordingly:

- the plan bytes/freeze record below are mechanically certified here;
- the §114 evidence bundle is accepted as the externally certified companion record described by the user's execution report;
- no truncated hash prefix is promoted to a full digest in this plan.

## 114.9 Camera disposition closure

The structured-camera production binding was not smoked.

Initial M10 therefore selects §109 **Derived Path B**. The exact M10 camera is consumed during deterministic rendering of the view-dependent depth-control sequences. No independent structured-camera claim is made.

## 114.10 Out-of-scope/non-performed work

Not required for the initial frozen contract:

- capacity-to-failure above 3 streams;
- structured-camera Path A;
- pixel-quality judgment.

These are not hidden gaps: the initial profile is explicitly bounded to the proven derived path and proven capacity.

---

# 115. Proxy geometry boundary

Movable SpatialTracks carry exact pose but no authoritative surface geometry/extents.

A depth-like entity derivative therefore uses execution-only proxy geometry unless an approved source provides geometry under a separately frozen contract.

Rules:

- proxy geometry is part of `DerivedSpatialArtifactSpec`;
- never M10 authority;
- no current model/vision inference chooses it at materialization time;
- closed/versioned policy;
- policy change changes spec/algorithm identity;
- historical UI labels it execution proxy geometry.

Initial proxy policy is the exact execution-only box-depth proxy used by the passed M10A-1/§114 evidence fixtures and pinned by the companion materializer/evidence record. Its dimensions/byte grammar are derivation parameters, not M10 authority, and must be copied exactly into the implementation contract/source fixtures before M10A code is accepted.

If a later production path requires fine shape unavailable from current authority or a reviewed execution-only source, STOP with `STOP_NEW_AUTHORITY_LAYER_REQUIRED` or design a separate execution-geometry contract.

---

# 116. Axis and screen-direction execution disposition

Axis constraint remains upstream production validity. No derived raster is required solely to restate the axis line.

If a future executor has an explicit axis-conditioning channel, a later profile may bind it; schema 1 does not require this.

`screen_direction` remains advisory:

```text
supported → explicit captured binding
unsupported → captured omission screen_direction_not_consumed
```

No output-pixel analyzer becomes authority.

---

# 117. Derived artifact retention / backup

Historically referenced derivative bytes are permanent live roots in initial M10.

Liveness path:

```text
Generation
→ generation_derived_spatial_inputs
→ derived_spatial_artifacts
→ blobs
```

Initial retention:

```text
historically referenced derived Blob → never GC
unreferenced temporary candidate → delete
unreferenced published derivative → retain until a future GC contract
```

Project backup/export includes relational provenance and every historically live physical Blob. Database-only backup is incomplete once 0011 history exists.

---

# 118. Derived execution race additions

Mechanical Events/barriers, no sleeps:

1. authority edit during materialization;
2. package change during materialization;
3. runtime installation change during materialization;
4. duplicate identical D0 materialization;
5. same spec/runtime attempting a different Blob;
6. Blob publish vs final Generation fence loss;
7. worker vs current package/materializer replacement;
8. Exact Rerun vs current M10 edit;
9. Exact Rerun vs current runtime removal;
10. historical validation vs attempted GC.

Every trace yields one coherent identity set or explicit conflict.

---

# 119. Derived no-authority-transfer gate

Static and dynamic proof covers materializer, Blob publisher, provenance service, worker, executor translator, Exact Rerun, and future GC.

Forbidden writes include all M7/M8/M10 authority/current tables.

A deliberate positive-control forbidden write proves the spy is non-vacuous.

Derived media is never automatically promoted into SpatialWorldRevision, track state, ShotSpatialPlan, M7 relation, or M8 visual authority.

---

# 120. r3 final freeze checklist — COMPLETE

Architecture/source-fit freeze gates:

- [x] M10A-0 companion evidence externally certified;
- [x] M10A-1 companion evidence externally certified;
- [x] §114 live registration passed;
- [x] §114 functional GPU smoke passed;
- [x] model/control/runtime identities recorded in the external evidence bundle;
- [x] hidden-write/cache audit passed;
- [x] initial artifact/tensor grammar bounded to the source-proven 17-frame 832×480 stride-1 profile and external exact byte grammar;
- [x] derived control-stream capacity frozen conservatively at 3;
- [x] survivability/equivalence limitation frozen;
- [x] proxy-geometry policy bound to the evidence-pinned execution-only box-depth policy;
- [x] camera disposition frozen to derived Path B; no initial structured-camera claim;
- [x] migration 0010 includes world-requirement history and placement DB backstop;
- [x] migration 0011 authority/execution separation and relational shape reviewed;
- [x] global D0 same-spec/runtime→same-Blob convergence rule restored across Projects;
- [x] workflow-spec-v3 initial spatial block reconciled with no structured-camera binding;
- [x] package/profile/manifest capability requirements reconciled with max 3 derived streams;
- [x] M10 + derived error vocabularies remain closed and corruption stays fail-closed;
- [x] downgrade preflight covers 0011 then 0010;
- [x] canonical JSON inheritance remains pinned to the predecessor serializer;
- [x] final plan bytes/hash mechanically certified in the freeze record.

This checklist freezes **architecture and source-fit only**.

It does **not** authorize implementation. M10A–F implementation, repository mutation, migrations, package installation, publication, and tagging remain separate explicit authorization boundaries.

---

# 121. Revised M10 error/provenance vocabulary requirement

M10 retains the existing `SPATIAL_*` production/readiness vocabulary.

Derived execution uses the M10A-1 family:

```text
DERIVED_SPATIAL_SPEC_INVALID
DERIVED_SPATIAL_KIND_UNSUPPORTED
DERIVED_SPATIAL_RUNTIME_UNPINNABLE
DERIVED_SPATIAL_NONDETERMINISTIC
DERIVED_SPATIAL_MATERIALIZATION_FAILED
DERIVED_SPATIAL_OUTPUT_INVALID
DERIVED_SPATIAL_PROVENANCE_MISMATCH
DERIVED_SPATIAL_BLOB_MISSING
DERIVED_SPATIAL_BLOB_CORRUPT
DERIVED_SPATIAL_CAPTURE_CONFLICT
DERIVED_SPATIAL_BINDING_INVALID
DERIVED_SPATIAL_HARD_COMPONENT_LOSS
```

HTTP mappings and near-duplicate precedence remain governed by §55 plus the frozen M10A-1 derived family. Corruption is invariant failure; runtime/materialization unavailability must not masquerade as invalid production authority.

---

# 122. Accepted initial execution limitations

Initial M10 may honestly state:

- M10 authority remains exact metric production truth;
- raster conditioning is view-dependent and finite-resolution;
- different exact authority states may map to identical raster bytes;
- fully occluded staged Entities require independent/non-occluding representation;
- interpolation between sparse authority keyframes is derivation policy;
- proxy geometry for movable entities is execution state, not authoritative shape;
- model output may still violate controls;
- initial M10 makes no separate structured-camera claim; camera is consumed through the evidence-pinned derived depth-control path;
- multi-world Shots, duplicate Entity instances, dynamic axes, fine surface geometry, lens distortion, and per-frame authority remain deferred.

These limitations never authorize silent fallback.

---

# 123. Final r3 handoff statement

Once §120 is complete and implementation later passes M10A–F, SoloRing may state:

> For this Generation, the exact M7/M8/M10 production authority was captured immutably; the exact D0 derived spatial artifacts were produced from that captured authority under pinned algorithms/runtime identities; every materialized byte used by the executor is content-addressed and historically retained; Exact Rerun does not consult current spatial state or rematerialize by default; and execution output cannot rewrite production authority.

That is the intended feature-film continuity handoff: exact production truth above, exact historically auditable realization below, and no hidden authority transfer.

