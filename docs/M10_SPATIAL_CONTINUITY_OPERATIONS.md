# M10 Spatial Continuity — Operations Guide

This document describes what the M10 spatial/cinematic continuity
system does, what it deliberately does not do, and how an operator runs
it day to day — including backup/restore and failure triage. It is
pinned by `tests/test_m10f_docs.py`; cosmetic prose may change, the
load-bearing claims may not drift from source.

## What M10 claims — and does not claim

SoloRing's spatial authority answers: *where is everything, where is the
camera, and what continuity must hold between shots?* It proves
**request/provenance continuity authority and deterministic D0 control
realization**. It does **not** promise that a generative model will
produce identical pixels across reruns; "feature-film continuity" in the
M10 sense means durable authority + deterministic derived controls, not
pixel-perfect generation.

## Coordinate and camera conventions

- World coordinates are millimeters; rotations are microdegrees
  (`rotation_udeg` triplets yaw/pitch/roll).
- The identity camera looks down world −Z.
- Cameras are full pinhole specs: `focal_length_um`,
  `sensor_width_um`/`sensor_height_um`, `projection`, and `keyframes`
  (each keyframe carries a `time_ms` + transform).
- Normalization: microdegree yaw wraps +180° → −180°; physically
  equivalent but numerically distinct Euler tuples stay distinct in
  storage.
- Axis side is computed server-side only; clients display it.

## World authority

- A `SpatialWorld` belongs to one Location entity. One active world per
  Location.
- World edits (frame membership, values, axes) do not touch history
  until a `SpatialWorldRevision` is captured; approval is an
  expected-pointer CAS (`expected_approved_revision_id`).
- A **required** world applies to every shot whose dependencies include
  its Location; **optional** worlds apply only when a plan names them.
- `required ↔ optional` flips change resolution/capture immediately.

## Temporal staging (effective staging)

- Staging is resolved per shot boundary by direct random access —
  computing Shot N's staging never replays Shots 1..N−1.
- `SpatialTransition`s anchor at sequence/scene/shot starts and ends;
  `set` and `clear` operations; the same coordinate may be re-set only
  after the previous transition is deleted.
- An explicit handoff at Shot N/end is the authority for Shot N+1/start.
  Deleting or re-rendering a Take never changes spatial authority.

## ShotSpatialPlan authority

- The plan (camera + blocking + optional axis constraint) is the
  per-shot execution intent. Its canonical bytes/hashes are frozen at
  put time; updates require the exact `expected_plan_hash`.
- Blocking keyframes at time 0 must equal the effective persistent
  staging transform exactly.
- Axis constraints declare `camera_side: positive|negative`; the
  resolver decides left/on/violation from geometry.

## Capture semantics (schema 5)

- A ShotRevision is schema 5 exactly when effective M10 authority is
  non-empty; schemas 1–4 remain readable forever and are never
  fabricated upward.
- The captured snapshot embeds the canonical spatial pack; child
  projection rows (`shot_revision_spatial_worlds`, …) must agree with
  the embedded pack byte-for-byte.
- Current edits after a capture never rewrite the captured revision.

## Package / logical schema compatibility (corrected in M10F)

- The **certified schema-3 spatial package** now declares its ordinary
  `prompt → node 3/positive_prompt` and `video → node 80/images`
  contract (PD-1C). Every new capture from this release — logical v1,
  v2, or v3 — imports exactly one `video:0` on terminal success.
- With empty captured M10 authority, a schema-3-capable package emits
  an **exact logical v1** (empty M8) or **logical v2** (non-empty M8,
  M9-ready) WorkflowSpec — never an empty v3, never a silent drop of
  authority (PD-1A).
- A logical v1/v2 Generation that retains a schema-3 package executes
  through one canonical **lower-logical execution view**: a true
  lower-schema manifest projection plus a deterministic
  spatial-ControlNet-free template projection. Physical Blob access is
  always hash-derived; the stored `blobs.path` value is metadata and is
  never followed as a filesystem locator (PD-2).
- Historical M10E schema-3 Generations captured against the outputless
  manifest stay outputless forever; nothing backfills them.

## Model realization vs production authority

- Model realization (M9) and spatial realization (M10) are independent
  blocks in workflow-spec v3; M9 absence never fabricates a realization.
- Derived D0 controls are deterministic (class D0): same spec + same
  materializer runtime → same Blob bytes. Identical concurrent
  registrations converge; divergent ones fail
  `DERIVED_SPATIAL_NONDETERMINISTIC`.
- Generated media is downstream evidence. It never becomes
  SpatialWorldRevision, staging, ShotSpatialPlan, M7, or M8 authority.

## Common blockers and what they mean

- `SPATIAL_SHOT_PLAN_REQUIRED` — a required world applies but the shot
  has no plan.
- `SPATIAL_WORLD_APPROVAL_REQUIRED` / `SPATIAL_WORLD_STATE_REQUIRED` —
  capture blocked until the world state/approval is fixed.
- `SPATIAL_AXIS_CONSTRAINT_VIOLATION` — blocking violates the declared
  axis side.
- `SPATIAL_REALIZATION_UNSUPPORTED` — staging exceeds the frozen
  3-stream control capacity (world + at most two staged entities), or a
  non-spatial package was selected while spatial authority exists.
- `SPATIAL_TRACK_STATE_REQUIRED` — a required track has no effective
  state at this shot.

## Backup and restore

The supported posture is the default local layout —
`database_url` unset, DB at `<data_dir>/soloring.db`, Blob root
`<data_dir>/blobs`, workflow artifacts under
`<data_dir>/workflow-artifacts`. Anything else fails closed before any
staging directory is created.

```bash
python scripts/m10f_backup_restore.py backup  --data-dir <data> --dest <path>
python scripts/m10f_backup_restore.py restore --from <backup>   --dest <new-data>
```

- Exit codes: 0 success, 2 unsupported posture, 1 other failure.
- A backup contains `soloring.db`, every historically live Blob, every
  retained workflow artifact, and a canonical `backup-manifest.json`.
  Staging/tmp directories, executor uploads, the installed workflow
  package, model installations, and live attestations are excluded —
  they are not history.
- Blob liveness is the exact six-path relational inventory
  (assets, generation inputs, derived artifacts, derived inputs, and
  both immutable M8 visual-provenance tables).
- **A database-only backup is incomplete by definition** once history
  references physical bytes: every retained Blob and workflow artifact
  byte is copied and stream-verified before and after copy.
- Restore targets a fresh, absent data root; publication is one
  same-filesystem rename of a fully verified staging directory.
- A hard crash may leave a `.<dest>.soloring-restore-<uuid>.staging`
  sibling. It is never authoritative. An unmodified retry succeeds with
  a new staging directory; remove orphans by hand only after checking
  no restore is running.
- Exact Rerun after restore reuses identical durable identities with
  zero D0 rematerialization.

## No garbage collection

There is deliberately no Blob/deleted-derived-artifact GC. Retention is
proved by exact liveness, backup inclusion, integrity checks, no
production delete path, and fail-closed behavior when someone deletes a
retained Blob externally (execution fails
`DERIVED_SPATIAL_BLOB_MISSING`; nothing rematerializes).

## Why current executor state is not backup content

The installed workflow package, model files, and live deployment
attestations describe the *current* environment, not history. History
is the retained content-addressed artifacts; a restored instance
executes from those bytes and will fail closed if the live environment
drifts from the captured fingerprint — executability and durable
identity are separate concerns.
