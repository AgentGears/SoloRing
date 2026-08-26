"""Canonical M10 authority document schemas (frozen r3 §13/§20/§26).

Pure byte-bearing validators for SpatialWorldRevision snapshots,
ShotSpatialPlan documents, and SpatialContinuityPack values. Canonical bytes
use the existing SoloRing serializer (domain.canonical) — no JCS, no second
serializer. Strict recursive unknown-field rejection; JavaScript-safe
integers; normalized microdegree rotations via spatial.math.
"""
from __future__ import annotations

from typing import Any

from soloring.domain.canonical import canonical_hash, canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.math import (
    CameraOptics,
    Transform,
    normalize_udeg,
    validate_int,
)

WORLD_REVISION_SCHEMA_VERSION = 1
PLAN_SCHEMA_VERSION = 1
PACK_SCHEMA_VERSION = 1

SCREEN_DIRECTIONS = ("left_to_right", "right_to_left", "stationary", "unspecified")
CAMERA_SIDES = ("positive", "negative")

_KEY_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")


class SchemaInvalid(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.SPATIAL_WORLD_INVALID, message, status_code=422)


class PlanSchemaInvalid(SchemaInvalid):
    """ShotSpatialPlan grammar failure carrying the frozen durable
    SPATIAL_SHOT_PLAN_INVALID identity (M10D §8.7) while remaining a
    SchemaInvalid subclass — predecessor catch compatibility holds."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = ErrorCode.SPATIAL_SHOT_PLAN_INVALID


def _bad(message: str) -> SchemaInvalid:
    return SchemaInvalid(message)


def _bad_plan(message: str) -> PlanSchemaInvalid:
    return PlanSchemaInvalid(message)


def _require_dict(value: Any, what: str) -> dict:
    if not isinstance(value, dict):
        raise _bad(f"{what} must be an object.")
    return value


def _require_list(value: Any, what: str) -> list:
    if not isinstance(value, list):
        raise _bad(f"{what} must be an array.")
    return value


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise _bad(f"{what} must be a non-empty string.")
    return value


def _semantic_key(value: Any, what: str) -> str:
    value = _require_str(value, what)
    if not (1 <= len(value) <= 128) or value[0] not in _KEY_CHARS - {".", "-"} \
            or any(c not in _KEY_CHARS for c in value):
        raise _bad(f"{what} violates the canonical key grammar.")
    return value


def _exact_keys(doc: dict, allowed: set[str], what: str) -> None:
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise _bad(f"{what} has unknown fields {unknown}; the field set is closed.")


def _require_keys(doc: dict, required: set[str], what: str) -> None:
    """Canonical closed grammar: required keys must be PRESENT (explicit
    null is the canonical absence form for nullable fields — omission is
    a grammar failure, never a KeyError (M10D §7)."""
    missing = sorted(required - set(doc))
    if missing:
        raise _bad(f"{what} is missing required fields {missing}; "
                   "canonical absence is an explicit present key with a "
                   "null value.")


def _transform(raw: Any, what: str) -> Transform:
    raw = _require_dict(raw, what)
    _exact_keys(raw, {"translation_mm", "rotation_udeg"}, what)
    t = _require_list(raw.get("translation_mm"), f"{what}.translation_mm")
    r = _require_list(raw.get("rotation_udeg"), f"{what}.rotation_udeg")
    if len(t) != 3 or len(r) != 3:
        raise _bad(f"{what} translation/rotation must be 3-vectors.")
    for v in t:
        if not isinstance(v, int) or isinstance(v, bool):
            raise _bad(f"{what}.translation_mm must contain integers only.")
    for v in r:
        if not isinstance(v, int) or isinstance(v, bool):
            raise _bad(f"{what}.rotation_udeg must contain integers only.")
    try:
        return Transform(tuple(t), tuple(r))
    except ValueError as exc:
        raise _bad(f"{what}: {exc}") from exc


def _half_extents(raw: Any, what: str) -> tuple[int, int, int] | None:
    if raw is None:
        return None
    h = _require_list(raw, what)
    if len(h) != 3 or any(not isinstance(v, int) or isinstance(v, bool)
                          or v <= 0 for v in h):
        raise _bad(f"{what} must be three strictly positive integers or null.")
    return (h[0], h[1], h[2])


# --------------------------------------------------------------------------
# SpatialWorldRevision canonical schema 1 (§13)
# --------------------------------------------------------------------------

_COORDINATE_SYSTEM = {
    "handedness": "right",
    "right_axis": "+x",
    "up_axis": "+y",
    "depth_positive_axis": "+z",
    "forward_axis": "-z",
    "linear_unit": "millimeter",
    "rotation_unit": "microdegree",
    "rotation_semantics": "active_local_to_world_intrinsic_yxz",
    "vector_convention": "column",
    "camera_forward_axis": "-z",
}


def parse_world_revision(raw: Any) -> dict:
    """Validate one SpatialWorldRevision canonical snapshot; return it
    normalized (canonical frame/axis order, normalized rotations)."""
    doc = _require_dict(raw, "SpatialWorldRevision")
    _exact_keys(doc, {
        "schema_version", "spatial_world_id", "location_entity_id",
        "location_entity_revision_id", "coordinate_system", "frames", "axes",
    }, "SpatialWorldRevision")
    if doc["schema_version"] != WORLD_REVISION_SCHEMA_VERSION:
        raise _bad("SpatialWorldRevision schema_version must be 1.")
    for field in ("spatial_world_id", "location_entity_id",
                  "location_entity_revision_id"):
        _require_str(doc[field], f"SpatialWorldRevision.{field}")
    if doc["coordinate_system"] != _COORDINATE_SYSTEM:
        raise _bad("SpatialWorldRevision.coordinate_system is frozen; "
                   "any change requires a new schema version.")

    frames_raw = _require_list(doc["frames"], "SpatialWorldRevision.frames")
    frames: list[dict] = []
    seen_ids: set[str] = set()
    seen_keys: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    for i, fr in enumerate(frames_raw):
        what = f"frames[{i}]"
        fr = _require_dict(fr, what)
        _exact_keys(fr, {
            "spatial_frame_id", "frame_key", "parent_spatial_frame_id",
            "bound_entity_id", "bound_entity_revision_id", "transform",
            "half_extents_mm",
        }, what)
        fid = _require_str(fr["spatial_frame_id"], f"{what}.spatial_frame_id")
        key = _semantic_key(fr["frame_key"], f"{what}.frame_key")
        if fid in seen_ids:
            raise _bad(f"{what}: duplicate spatial_frame_id {fid!r}.")
        if key in seen_keys:
            raise _bad(f"{what}: duplicate frame_key {key!r}.")
        seen_ids.add(fid)
        seen_keys[key] = fid
        parent = fr["parent_spatial_frame_id"]
        if parent is not None:
            _require_str(parent, f"{what}.parent_spatial_frame_id")
        parents[fid] = parent
        bound = fr["bound_entity_id"]
        bound_rev = fr["bound_entity_revision_id"]
        if (bound is None) != (bound_rev is None):
            raise _bad(f"{what}: bound entity and revision must be set together.")
        if bound is not None:
            _require_str(bound, f"{what}.bound_entity_id")
            _require_str(bound_rev, f"{what}.bound_entity_revision_id")
        t = _transform(fr["transform"], f"{what}.transform")
        he = _half_extents(fr["half_extents_mm"], f"{what}.half_extents_mm")
        frames.append({
            "spatial_frame_id": fid,
            "frame_key": key,
            "parent_spatial_frame_id": parent,
            "bound_entity_id": bound,
            "bound_entity_revision_id": bound_rev,
            "transform": t.canonical_value(),
            "half_extents_mm": list(he) if he else None,
        })

    # parent inclusion + acyclicity over the SNAPSHOT graph (stable frames
    # may reference parents that predecease them; within one immutable
    # snapshot every referenced parent must be present and acyclic)
    for fid, parent in parents.items():
        if parent is None:
            continue
        if parent not in seen_ids:
            raise _bad(f"frames: parent {parent!r} absent from the snapshot.")
        walker, hops = parent, 0
        while walker is not None:
            hops += 1
            if hops > len(parents):
                raise _bad("frames: organizational parent graph is cyclic.")
            walker = parents.get(walker)

    axes_raw = _require_list(doc["axes"], "SpatialWorldRevision.axes")
    axes: list[dict] = []
    axis_ids: set[str] = set()
    for i, ax in enumerate(axes_raw):
        what = f"axes[{i}]"
        ax = _require_dict(ax, what)
        _exact_keys(ax, {
            "spatial_axis_id", "axis_key", "a_frame_id", "b_frame_id",
        }, what)
        aid = _require_str(ax["spatial_axis_id"], f"{what}.spatial_axis_id")
        key = _semantic_key(ax["axis_key"], f"{what}.axis_key")
        if aid in axis_ids:
            raise _bad(f"{what}: duplicate spatial_axis_id {aid!r}.")
        axis_ids.add(aid)
        a = _require_str(ax["a_frame_id"], f"{what}.a_frame_id")
        b = _require_str(ax["b_frame_id"], f"{what}.b_frame_id")
        if a == b:
            raise _bad(f"{what}: endpoints must differ.")
        for endpoint in (a, b):
            if endpoint not in seen_ids:
                raise _bad(f"{what}: endpoint {endpoint!r} not an included frame.")
        axes.append({
            "spatial_axis_id": aid,
            "axis_key": key,
            "a_frame_id": a,
            "b_frame_id": b,
        })

    frames.sort(key=lambda f: (f["frame_key"], f["spatial_frame_id"]))
    axes.sort(key=lambda a: (a["axis_key"], a["spatial_axis_id"]))
    doc = {**doc, "frames": frames, "axes": axes}
    return doc


def world_revision_hash(doc: dict) -> str:
    return canonical_hash(doc)


# --------------------------------------------------------------------------
# ShotSpatialPlan canonical schema 1 (§20)
# --------------------------------------------------------------------------

def parse_shot_plan(raw: Any, *, duration_ms: int | None) -> dict:
    """Validate one ShotSpatialPlan; duration_ms is the Shot's current
    duration (NULL => only t=0 keyframes are legal).

    The RETURNED document is canonical authority: every camera/blocking
    keyframe transform is replaced by the normalized Transform canonical
    value (M10D §8.4-8.5) — wrap-equivalent rotations converge on
    identical returned bytes/hash. Plan grammar failures carry
    SPATIAL_SHOT_PLAN_INVALID (PlanSchemaInvalid)."""
    try:
        return _parse_shot_plan_impl(raw, duration_ms=duration_ms)
    except PlanSchemaInvalid:
        raise
    except SchemaInvalid as exc:
        raise PlanSchemaInvalid(exc.message) from exc


def _parse_shot_plan_impl(raw: Any, *, duration_ms: int | None) -> dict:
    doc = _require_dict(raw, "ShotSpatialPlan")
    _require_keys(doc, {
        "schema_version", "spatial_world_id", "camera", "blocking",
        "axis_constraint",
    }, "ShotSpatialPlan")
    _exact_keys(doc, {
        "schema_version", "spatial_world_id", "camera", "blocking",
        "axis_constraint",
    }, "ShotSpatialPlan")
    if doc["schema_version"] != PLAN_SCHEMA_VERSION:
        raise _bad("ShotSpatialPlan schema_version must be 1.")
    _require_str(doc["spatial_world_id"], "ShotSpatialPlan.spatial_world_id")

    cam = _require_dict(doc["camera"], "camera")
    _require_keys(cam, {
        "projection", "focal_length_um", "sensor_width_um",
        "sensor_height_um", "keyframes",
    }, "camera")
    _exact_keys(cam, {
        "projection", "focal_length_um", "sensor_width_um", "sensor_height_um",
        "keyframes",
    }, "camera")
    if cam["projection"] != "perspective":
        raise _bad("camera.projection supports 'perspective' only in schema 1.")
    try:
        CameraOptics(cam["focal_length_um"], cam["sensor_width_um"],
                     cam["sensor_height_um"])
    except (ValueError, TypeError) as exc:
        raise _bad(f"camera optics: {exc}") from exc
    cam_kfs_raw = _require_list(cam["keyframes"], "camera.keyframes")
    if not cam_kfs_raw:
        raise _bad("camera.keyframes must contain at least one keyframe.")
    cam_kfs = _keyframes(cam_kfs_raw, "camera.keyframes", duration_ms)

    blocking_raw = _require_list(doc["blocking"], "blocking")
    blocking: list[dict] = []
    seen_tracks: set[str] = set()
    for i, entry in enumerate(blocking_raw):
        what = f"blocking[{i}]"
        entry = _require_dict(entry, what)
        _require_keys(entry, {"spatial_track_id", "screen_direction",
                              "keyframes"}, what)
        _exact_keys(entry, {"spatial_track_id", "screen_direction", "keyframes"},
                    what)
        tid = _require_str(entry["spatial_track_id"], f"{what}.spatial_track_id")
        if tid in seen_tracks:
            raise _bad(f"{what}: duplicate blocking track {tid!r}.")
        seen_tracks.add(tid)
        direction = entry["screen_direction"]
        if direction not in SCREEN_DIRECTIONS:
            raise _bad(f"{what}.screen_direction must be one of "
                       f"{list(SCREEN_DIRECTIONS)}.")
        kfs_raw = _require_list(entry["keyframes"], f"{what}.keyframes")
        if not kfs_raw:
            raise _bad(f"{what}.keyframes must contain at least one keyframe.")
        kfs = _keyframes(kfs_raw, f"{what}.keyframes", duration_ms)
        blocking.append({
            "spatial_track_id": tid,
            "screen_direction": direction,
            "keyframes": kfs,
        })
    blocking.sort(key=lambda b: b["spatial_track_id"])

    axis = doc["axis_constraint"]
    axis_out: dict | None = None
    if axis is not None:
        axis = _require_dict(axis, "axis_constraint")
        _require_keys(axis, {"spatial_axis_id", "camera_side"},
                      "axis_constraint")
        _exact_keys(axis, {"spatial_axis_id", "camera_side"}, "axis_constraint")
        aid = _require_str(axis["spatial_axis_id"],
                           "axis_constraint.spatial_axis_id")
        if axis["camera_side"] not in CAMERA_SIDES:
            raise _bad("axis_constraint.camera_side must be positive|negative.")
        axis_out = {"spatial_axis_id": aid,
                    "camera_side": axis["camera_side"]}
    return {
        "schema_version": doc["schema_version"],
        "spatial_world_id": doc["spatial_world_id"],
        "camera": {
            "projection": cam["projection"],
            "focal_length_um": cam["focal_length_um"],
            "sensor_width_um": cam["sensor_width_um"],
            "sensor_height_um": cam["sensor_height_um"],
            "keyframes": cam_kfs,
        },
        "blocking": blocking,
        "axis_constraint": axis_out,
    }


def _keyframes(kfs: list, what: str, duration_ms: int | None) -> list[dict]:
    """Validate keyframe ordering/duration rules and RETURN canonical
    keyframes with normalized transforms (M10D §8.4)."""
    out: list[dict] = []
    last_time = None
    for i, kf in enumerate(kfs):
        kwhat = f"{what}[{i}]"
        kf = _require_dict(kf, kwhat)
        _require_keys(kf, {"time_ms", "transform"}, kwhat)
        _exact_keys(kf, {"time_ms", "transform"}, kwhat)
        t = kf["time_ms"]
        if not isinstance(t, int) or isinstance(t, bool) or t < 0:
            raise _bad(f"{kwhat}.time_ms must be a non-negative integer.")
        if i == 0 and t != 0:
            raise _bad(f"{what}: the first keyframe must be exactly time_ms=0.")
        if last_time is not None and t <= last_time:
            raise _bad(f"{what}: times must be strictly increasing and unique.")
        last_time = t
        if duration_ms is not None and t > duration_ms:
            raise _bad(f"{what}: time_ms exceeds the Shot duration.")
        if duration_ms is None and t != 0:
            raise _bad(f"{what}: only time_ms=0 keyframes are valid when the "
                       "Shot duration is NULL.")
        tf = _transform(kf["transform"], f"{kwhat}.transform")
        out.append({"time_ms": t, "transform": tf.canonical_value()})
    return out


def plan_hash(doc: dict) -> str:
    return canonical_hash(doc)


# --------------------------------------------------------------------------
# SpatialContinuityPack canonical schema 1 (§26)
# --------------------------------------------------------------------------

def parse_continuity_pack(raw: Any) -> dict:
    """Validate one SpatialContinuityPack, cross-checking the embedded world
    snapshot against its declared revision hash, the embedded requirement,
    staging canonical order, and the embedded plan bytes."""
    doc = _require_dict(raw, "SpatialContinuityPack")
    _exact_keys(doc, {"schema_version", "spatial_world", "staging", "shot_plan"},
                "SpatialContinuityPack")
    if doc["schema_version"] != PACK_SCHEMA_VERSION:
        raise _bad("SpatialContinuityPack schema_version must be 1.")

    world = _require_dict(doc["spatial_world"], "spatial_world")
    _exact_keys(world, {
        "spatial_world_id", "requirement", "spatial_world_state_id",
        "spatial_world_revision_id", "spatial_world_revision_hash",
        "location_entity_id", "location_entity_revision_id", "world_snapshot",
    }, "spatial_world")
    if world["requirement"] not in ("required", "optional"):
        raise _bad("spatial_world.requirement must be required|optional.")
    for field in ("spatial_world_id", "spatial_world_state_id",
                  "spatial_world_revision_id", "location_entity_id",
                  "location_entity_revision_id"):
        _require_str(world[field], f"spatial_world.{field}")
    declared = _require_str(world["spatial_world_revision_hash"],
                            "spatial_world.spatial_world_revision_hash")
    snapshot = parse_world_revision(world["world_snapshot"])
    if canonical_hash(snapshot) != declared:
        raise _bad("spatial_world.world_snapshot does not hash to the declared "
                   "spatial_world_revision_hash.")
    if snapshot["spatial_world_id"] != world["spatial_world_id"]:
        raise _bad("world_snapshot identity disagrees with the pack world.")

    staging_raw = _require_list(doc["staging"], "staging")
    staging: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for i, st in enumerate(staging_raw):
        what = f"staging[{i}]"
        st = _require_dict(st, what)
        _exact_keys(st, {
            "spatial_track_id", "entity_id", "entity_revision_id",
            "requirement", "transform", "source_transition",
        }, what)
        tid = _require_str(st["spatial_track_id"], f"{what}.spatial_track_id")
        eid = _require_str(st["entity_id"], f"{what}.entity_id")
        _require_str(st["entity_revision_id"], f"{what}.entity_revision_id")
        if st["requirement"] not in ("required", "optional"):
            raise _bad(f"{what}.requirement must be required|optional.")
        if (eid, tid) in seen:
            raise _bad(f"{what}: duplicate staging entity/track.")
        seen.add((eid, tid))
        _transform(st["transform"], f"{what}.transform")
        tr = _require_dict(st["source_transition"], f"{what}.source_transition")
        _exact_keys(tr, {
            "spatial_transition_id", "anchor_type", "anchor_id", "boundary",
        }, f"{what}.source_transition")
        _require_str(tr["spatial_transition_id"],
                     f"{what}.source_transition.spatial_transition_id")
        if tr["anchor_type"] not in ("sequence", "scene", "shot"):
            raise _bad(f"{what}.source_transition.anchor_type invalid.")
        _require_str(tr["anchor_id"], f"{what}.source_transition.anchor_id")
        if tr["boundary"] not in ("start", "end"):
            raise _bad(f"{what}.source_transition.boundary invalid.")
        staging.append(st)
    staging.sort(key=lambda s: (s["entity_id"], s["spatial_track_id"]))

    # The pack is byte-level canonical authority; Shot-duration cross-checks
    # belong to the readiness resolver (§20.5), so validate the plan's own
    # internal grammar with its maximal legal duration (the last keyframe).
    # The NORMALIZED returned plan is what the pack retains (M10D §32):
    # unnormalized caller rotations cannot survive pack parsing. Staging
    # transforms are M10C production authority and pass through unchanged.
    plan = doc["shot_plan"]
    times = [k["time_ms"] for k in plan["camera"]["keyframes"]]
    duration = max(times) if times else 0
    for entry in plan.get("blocking", []):
        times.extend(k["time_ms"] for k in entry["keyframes"])
        duration = max(duration, max(
            k["time_ms"] for k in entry["keyframes"]))
    plan_out = parse_shot_plan(plan, duration_ms=duration if duration else None)
    return {**doc, "staging": staging, "shot_plan": plan_out}


def pack_hash(doc: dict) -> str:
    return canonical_hash(doc)


__all__ = [
    "WORLD_REVISION_SCHEMA_VERSION", "PLAN_SCHEMA_VERSION",
    "PACK_SCHEMA_VERSION", "SCREEN_DIRECTIONS", "CAMERA_SIDES",
    "SchemaInvalid", "parse_world_revision", "world_revision_hash",
    "parse_shot_plan", "plan_hash", "parse_continuity_pack", "pack_hash",
    "canonical_json_bytes",
]
