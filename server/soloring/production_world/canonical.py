"""Canonical M13 schema-1 spatial-interpretation grammar (frozen R3 §4).

One shared value object produces interpretation_json, interpretation_hash,
and every scalar projection column; no endpoint can write projections
independently. Verified readers re-canonicalize and require field-exact
equality with the stored bytes/hash and the exact M11 parent hashes.
"""

from __future__ import annotations

import hashlib
import re

from soloring.domain.canonical import canonical_json_bytes, canonical_json_str
from soloring.errors import (
    SoloRingError,
    internal_invariant,
    validation_error,
)
from soloring.spatial.math import (
    JS_SAFE_MAX,
    JS_SAFE_MIN,
    UDEG_MIN,
    Transform,
)

# Frozen §4.3: the fixed schema-1 coordinate contract (server-owned; the
# caller submits only the realization-local→subject-local transform).
COORDINATE_SYSTEM: dict = {
    "handedness": "right",
    "right_axis": "+x",
    "up_axis": "+y",
    "depth_positive_axis": "+z",
    "forward_axis": "-z",
    "linear_unit": "millimeter",
    "rotation_unit": "microdegree",
    "rotation_semantics": "active_local_to_world_intrinsic_yxz",
    "vector_convention": "column",
    "linear_scale_num": 1,
    "linear_scale_den": 1,
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_INTERPRETATION_KEYS = {
    "schema_version", "production_revision_id", "production_revision_hash",
    "retained_blob_hash", "coordinate_system", "origin_semantics",
    "realization_local_to_subject_local",
}


def interpretation_value(
    *, production_revision_id: str, production_revision_hash: str,
    retained_blob_hash: str, transform: Transform,
) -> dict:
    """Build the one canonical schema-1 value from one Transform object."""
    return {
        "schema_version": 1,
        "production_revision_id": production_revision_id,
        "production_revision_hash": production_revision_hash,
        "retained_blob_hash": retained_blob_hash,
        "coordinate_system": dict(COORDINATE_SYSTEM),
        "origin_semantics": "subject_local",
        "realization_local_to_subject_local": transform.canonical_value(),
    }


def interpretation_hash(value: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def interpretation_json(value: dict) -> str:
    return canonical_json_str(value)


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_interpretation(value: object) -> tuple[dict, Transform]:
    """Exact grammar gate over a parsed interpretation value.

    Returns (canonical value, Transform). Raises ValueError-style
    validation_error on any malformed input; never silently normalizes —
    a stored rotation of exactly +180000000 is corruption because the
    canonical half-open domain is [-180000000, +180000000).
    """
    if not isinstance(value, dict) or set(value) != _INTERPRETATION_KEYS:
        raise validation_error(
            "interpretation keys must be exactly "
            "{schema_version, production_revision_id, "
            "production_revision_hash, retained_blob_hash, "
            "coordinate_system, origin_semantics, "
            "realization_local_to_subject_local}")
    if value["schema_version"] != 1 or not _is_plain_int(
            value["schema_version"]):
        raise validation_error("interpretation schema_version != 1")
    if (not isinstance(value["production_revision_id"], str)
            or _UUID_RE.match(value["production_revision_id"]) is None):
        raise validation_error(
            "interpretation production_revision_id must be a canonical "
            "lowercase UUID")
    for key in ("production_revision_hash", "retained_blob_hash"):
        if (not isinstance(value[key], str)
                or _HEX64.match(value[key]) is None):
            raise validation_error(
                f"interpretation {key} must be 64 lowercase hex digits")
    if value["coordinate_system"] != COORDINATE_SYSTEM:
        raise validation_error(
            "interpretation coordinate_system must equal the fixed "
            "schema-1 M10 contract")
    if value["origin_semantics"] != "subject_local":
        raise validation_error(
            "interpretation origin_semantics must be 'subject_local'")
    tr = value["realization_local_to_subject_local"]
    if not isinstance(tr, dict) or set(tr) != {
            "translation_mm", "rotation_udeg"}:
        raise validation_error(
            "realization_local_to_subject_local must be exactly "
            "{translation_mm, rotation_udeg}")
    for key in ("translation_mm", "rotation_udeg"):
        vec = tr[key]
        if not isinstance(vec, list) or len(vec) != 3:
            raise validation_error(
                f"realization_local_to_subject_local.{key} must have "
                "exactly 3 values")
        for v in vec:
            if not _is_plain_int(v):
                raise validation_error(
                    f"realization_local_to_subject_local.{key} must "
                    "contain integers")
            if not (JS_SAFE_MIN <= v <= JS_SAFE_MAX):
                raise validation_error(
                    f"realization_local_to_subject_local.{key} outside "
                    "JavaScript-safe integer domain")
    for v in tr["rotation_udeg"]:
        if not (UDEG_MIN <= v < UDEG_MIN + 360_000_000):
            raise validation_error(
                "realization_local_to_subject_local.rotation_udeg is not "
                "canonically normalized (half-open [-180000000, "
                "+180000000); exactly +180000000 canonicalizes to "
                "-180000000 at authoring time and is corruption if stored)")
    transform = Transform(
        translation_mm=tuple(tr["translation_mm"]),
        rotation_udeg=tuple(tr["rotation_udeg"]),
    )
    return interpretation_value(
        production_revision_id=value["production_revision_id"],
        production_revision_hash=value["production_revision_hash"],
        retained_blob_hash=value["retained_blob_hash"],
        transform=transform,
    ), transform


def verify_stored_interpretation(
    *, interpretation_json: str, interpretation_hash: str,
    x_mm: int, y_mm: int, z_mm: int,
    yaw_udeg: int, pitch_udeg: int, roll_udeg: int,
    row_production_revision_id: str,
    parent_snapshot_hash: str, parent_blob_hash: str,
) -> dict:
    """The complete §4.4 verified-reader checklist over one stored row.

    Raises internal_invariant on any inconsistency — stored immutable
    corruption is never a friendly readiness issue (frozen §12).
    """
    import json as _json

    try:
        parsed = _json.loads(interpretation_json)
    except (TypeError, ValueError) as exc:
        raise internal_invariant(
            "stored interpretation JSON is not parseable") from exc
    try:
        canonical, transform = parse_interpretation(parsed)
    except SoloRingError as exc:
        # Stored malformed grammar is corruption, never a friendly
        # validation failure (frozen §12).
        raise internal_invariant(
            f"stored interpretation grammar is corrupt: {exc.message}"
        ) from exc
    if canonical_json_str(canonical) != interpretation_json:
        raise internal_invariant(
            "stored interpretation JSON is not the canonical serialization")
    if hashlib.sha256(
            canonical_json_bytes(canonical)).hexdigest() != interpretation_hash:
        raise internal_invariant(
            "stored interpretation hash does not match canonical bytes")
    if canonical["production_revision_id"] != row_production_revision_id:
        raise internal_invariant(
            "stored interpretation names a different Production Revision")
    if canonical["production_revision_hash"] != parent_snapshot_hash:
        raise internal_invariant(
            "stored interpretation production_revision_hash differs from "
            "production_revisions.snapshot_hash")
    if canonical["retained_blob_hash"] != parent_blob_hash:
        raise internal_invariant(
            "stored interpretation retained_blob_hash differs from "
            "production_revision_closures.blob_hash")
    tx, ty, tz = transform.translation_mm
    ry, rp, rr = transform.rotation_udeg
    if (x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg) != (
            tx, ty, tz, ry, rp, rr):
        raise internal_invariant(
            "stored interpretation scalar projections are not exact "
            "projections of the canonical value")
    return canonical
