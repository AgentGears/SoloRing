"""M10C minimal read-only ShotSpatialPlan reference reader (M10C plan §6.6).

This module is NOT ShotSpatialPlan authority. It exists solely so the
SpatialTrack delete guard can decide — fail-closed — whether a current
``shot_spatial_plans.plan_json`` document's blocking entries reference a
SpatialTrack. Complete plan parsing/canonicalization/CAS belongs to M10D.

Conservative rule (M10C §6.6): if reference-absence cannot be PROVEN,
the answer is an invariant failure, never "not referenced". It parses
the frozen schema-1 plan document shape only (r3 §20) and inspects the
blocking collection; camera/axis content is none of its business.
"""
from __future__ import annotations

import json

from soloring.errors import ErrorCode, SoloRingError

PLAN_SCHEMA_VERSION = 1


def _unreadable(detail: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.INTERNAL_INVARIANT_VIOLATION,
        f"Stored ShotSpatialPlan document is unreadable as frozen schema 1: "
        f"{detail} — Track-reference absence cannot be proven; the delete "
        "guard fails closed.",
        status_code=500,
    )


def plan_blocking_references_track(
    plan_json: str, *, row_spatial_world_id: str, spatial_track_id: str
) -> bool:
    """True iff the plan's blocking entries provably reference the Track.

    Raises INTERNAL_INVARIANT_VIOLATION for any document that is not
    recognizably the frozen schema-1 plan shape, or whose embedded world
    identity disagrees with its storage row — ambiguity can never be
    read as "no reference".
    """
    try:
        doc = json.loads(plan_json)
    except (TypeError, ValueError) as exc:
        raise _unreadable(f"JSON parse failed ({exc})") from exc
    if not isinstance(doc, dict):
        raise _unreadable("top level is not an object")

    version = doc.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _unreadable(f"schema_version is not an integer: {version!r}")
    if version != PLAN_SCHEMA_VERSION:
        raise _unreadable(f"unknown schema_version {version!r}")

    world = doc.get("spatial_world_id")
    if not isinstance(world, str) or not world:
        raise _unreadable("spatial_world_id is not a readable string")
    if world != row_spatial_world_id:
        raise _unreadable(
            f"embedded spatial_world_id {world!r} disagrees with its "
            f"storage row {row_spatial_world_id!r}")

    blocking = doc.get("blocking")
    if not isinstance(blocking, list):
        raise _unreadable("blocking is not a collection")

    for item in blocking:
        if not isinstance(item, dict):
            raise _unreadable("blocking entry is not an object")
        ref = item.get("spatial_track_id")
        if not isinstance(ref, str) or not ref:
            raise _unreadable(
                "blocking entry lacks an unambiguous spatial_track_id")
        if ref == spatial_track_id:
            return True
    return False


__all__ = ["plan_blocking_references_track", "PLAN_SCHEMA_VERSION"]
