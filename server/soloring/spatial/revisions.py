"""M10B immutable world-revision capture + approval CAS (frozen r3 §§12-15).

Two-phase compare-and-freeze (§12): coherent read of EVERY hash-bearing
dependency → canonical snapshot/hash → fenced writer re-reads and re-hashes
the identical dependency set → mismatch aborts SPATIAL_WORLD_CAPTURE_
CONFLICT with no BEFORE/AFTER hedge → converge on existing (state, hash)
only after stored-byte/child validation → else MAX(revision_number)+1.

Approval (§15) is expected-pointer CAS under the same fencing.
"""
from __future__ import annotations

import contextlib
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import db_now_sql
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.spatial import schemas as S

_COORDINATE_SYSTEM = {
    "handedness": "right", "right_axis": "+x", "up_axis": "+y",
    "depth_positive_axis": "+z", "forward_axis": "-z",
    "linear_unit": "millimeter", "rotation_unit": "microdegree",
    "rotation_semantics": "active_local_to_world_intrinsic_yxz",
    "vector_convention": "column", "camera_forward_axis": "-z",
}


def _err(code: str, message: str, status: int = 409) -> SoloRingError:
    return SoloRingError(code, message, status_code=status)


async def _load_candidate(conn, state_id: str) -> dict:
    """Coherent load of EVERY hash-bearing dependency (§12-1)."""
    state = (await conn.execute(text(
        "SELECT s.id, s.spatial_world_id, s.location_entity_revision_id, "
        "s.approved_revision_id, w.location_entity_id, w.project_id "
        "FROM spatial_world_states s JOIN spatial_worlds w "
        "ON w.id = s.spatial_world_id WHERE s.id = :s"),
        {"s": state_id})).mappings().one_or_none()
    if state is None:
        raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                   "State not found.", 404)
    frames = (await conn.execute(text(
        "SELECT m.spatial_frame_id, f.key AS frame_key, "
        "f.parent_spatial_frame_id, m.bound_entity_id, "
        "m.bound_entity_revision_id, m.x_mm, m.y_mm, m.z_mm, m.yaw_udeg, "
        "m.pitch_udeg, m.roll_udeg, m.half_x_mm, m.half_y_mm, m.half_z_mm "
        "FROM spatial_world_state_frames m JOIN spatial_frames f "
        "ON f.id = m.spatial_frame_id "
        "WHERE m.spatial_world_state_id = :s"),
        {"s": state_id})).mappings().all()
    axes = (await conn.execute(text(
        "SELECT sa.spatial_axis_id, a.key AS axis_key, sa.a_frame_id, "
        "sa.b_frame_id FROM spatial_world_state_axes sa "
        "JOIN spatial_axes a ON a.id = sa.spatial_axis_id "
        "WHERE sa.spatial_world_state_id = :s"),
        {"s": state_id})).mappings().all()
    return {"state": dict(state), "frames": [dict(r) for r in frames],
            "axes": [dict(r) for r in axes]}


def _build_canonical(candidate: dict) -> dict:
    frames = [{
        "spatial_frame_id": f["spatial_frame_id"],
        "frame_key": f["frame_key"],
        "parent_spatial_frame_id": f["parent_spatial_frame_id"],
        "bound_entity_id": f["bound_entity_id"],
        "bound_entity_revision_id": f["bound_entity_revision_id"],
        "transform": {"translation_mm": [f["x_mm"], f["y_mm"], f["z_mm"]],
                      "rotation_udeg": [f["yaw_udeg"], f["pitch_udeg"],
                                        f["roll_udeg"]]},
        "half_extents_mm": (None if f["half_x_mm"] is None else
                            [f["half_x_mm"], f["half_y_mm"], f["half_z_mm"]]),
    } for f in candidate["frames"]]
    axes = [{
        "spatial_axis_id": a["spatial_axis_id"],
        "axis_key": a["axis_key"],
        "a_frame_id": a["a_frame_id"],
        "b_frame_id": a["b_frame_id"],
    } for a in candidate["axes"]]
    doc = {
        "schema_version": 1,
        "spatial_world_id": candidate["state"]["spatial_world_id"],
        "location_entity_id": candidate["state"]["location_entity_id"],
        "location_entity_revision_id":
            candidate["state"]["location_entity_revision_id"],
        "coordinate_system": dict(_COORDINATE_SYSTEM),
        "frames": frames,
        "axes": axes,
    }
    return S.parse_world_revision(doc)


async def capture_revision(session: AsyncSession, state_id: str) -> dict:
    """§12 two-phase capture. Returns revision identity; never partial."""
    # Phase 1: coherent read + freeze + canonicalize + hash
    async with session.bind.connect() as conn:
        candidate = await _load_candidate(conn, state_id)
    canonical = _build_canonical(candidate)
    snapshot_json = canonical_json_str(canonical)
    snapshot_hash = canonical_hash(canonical)

    # Phase 2: fenced writer — re-read the SAME dependency set and re-hash
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            current = await _load_candidate(conn, state_id)
            current_canonical = _build_canonical(current)
            current_hash = canonical_hash(current_canonical)
            if current_hash != snapshot_hash:
                raise _err(ErrorCode.SPATIAL_WORLD_CAPTURE_CONFLICT,
                           "Working world state changed between freeze and "
                           "fenced capture; aborting with no BEFORE/AFTER "
                           "hedge.")
            # convergence check on (state, snapshot_hash)
            existing = (await conn.execute(text(
                "SELECT id, revision_number FROM spatial_world_revisions "
                "WHERE spatial_world_state_id = :s AND snapshot_hash = :h"),
                {"s": state_id, "h": snapshot_hash})).mappings().one_or_none()
            if existing is not None:
                # §14 reuse validation: stored bytes must equal candidate
                stored = (await conn.execute(text(
                    "SELECT snapshot_json FROM spatial_world_revisions "
                    "WHERE id = :r"), {"r": existing["id"]})).scalar()
                if stored != snapshot_json or \
                        canonical_hash(json.loads(stored)) != snapshot_hash:
                    raise internal_invariant(
                        "Stored revision bytes disagree with the converging "
                        "candidate; immutable history is corrupt.")
                children = (await conn.execute(text(
                    "SELECT COUNT(*) FROM spatial_world_revision_frames "
                    "WHERE spatial_world_revision_id = :r"),
                    {"r": existing["id"]})).scalar()
                if children != len(canonical["frames"]):
                    raise internal_invariant(
                        "Stored revision child projection disagrees with "
                        "the canonical snapshot.")
                await conn.exec_driver_sql("COMMIT")
                return {"id": existing["id"],
                        "revision_number": existing["revision_number"],
                        "snapshot_hash": snapshot_hash, "converged": True}
            number = (await conn.execute(text(
                "SELECT COALESCE(MAX(revision_number), 0) + 1 FROM "
                "spatial_world_revisions WHERE spatial_world_state_id = :s"),
                {"s": state_id})).scalar()
            revision_id = _new_id()
            await conn.execute(text(
                "INSERT INTO spatial_world_revisions (id, "
                "spatial_world_state_id, revision_number, snapshot_json, "
                "snapshot_hash, created_at) VALUES (:id,:s,:n,:j,:h,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": revision_id, "s": state_id, "n": number,
                 "j": snapshot_json, "h": snapshot_hash})
            for position, f in enumerate(canonical["frames"]):
                await conn.execute(text(
                    "INSERT INTO spatial_world_revision_frames ("
                    "spatial_world_revision_id, position, spatial_frame_id, "
                    "frame_key, parent_spatial_frame_id, bound_entity_id, "
                    "bound_entity_revision_id, x_mm, y_mm, z_mm, yaw_udeg, "
                    "pitch_udeg, roll_udeg, half_x_mm, half_y_mm, half_z_mm)"
                    " VALUES (:r,:pos,:fid,:fk,:pf,:be,:ber,:x,:y,:z,:yaw,"
                    ":pitch,:roll,:hx,:hy,:hz)"),
                    {"r": revision_id, "pos": position,
                     "fid": f["spatial_frame_id"], "fk": f["frame_key"],
                     "pf": f["parent_spatial_frame_id"],
                     "be": f["bound_entity_id"],
                     "ber": f["bound_entity_revision_id"],
                     "x": f["transform"]["translation_mm"][0],
                     "y": f["transform"]["translation_mm"][1],
                     "z": f["transform"]["translation_mm"][2],
                     "yaw": f["transform"]["rotation_udeg"][0],
                     "pitch": f["transform"]["rotation_udeg"][1],
                     "roll": f["transform"]["rotation_udeg"][2],
                     "hx": (f["half_extents_mm"][0]
                            if f["half_extents_mm"] else None),
                     "hy": (f["half_extents_mm"][1]
                            if f["half_extents_mm"] else None),
                     "hz": (f["half_extents_mm"][2]
                            if f["half_extents_mm"] else None)})
            for position, a in enumerate(canonical["axes"]):
                await conn.execute(text(
                    "INSERT INTO spatial_world_revision_axes ("
                    "spatial_world_revision_id, position, spatial_axis_id, "
                    "axis_key, a_frame_id, b_frame_id) VALUES "
                    "(:r,:pos,:aid,:ak,:fa,:fb)"),
                    {"r": revision_id, "pos": position,
                     "aid": a["spatial_axis_id"], "ak": a["axis_key"],
                     "fa": a["a_frame_id"], "fb": a["b_frame_id"]})
            await conn.exec_driver_sql("COMMIT")
            return {"id": revision_id, "revision_number": number,
                    "snapshot_hash": snapshot_hash, "converged": False}
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise internal_invariant(
                f"revision capture failed: {exc}") from exc


def _new_id() -> str:
    from soloring.domain.ids import new_uuid
    return new_uuid()


# --------------------------------------------------------------------------
# Approval CAS (§15)
# --------------------------------------------------------------------------

async def approve_revision(session: AsyncSession, state_id: str, *,
                           revision_id: str,
                           expected_approved_revision_id: str | None
                           ) -> dict:
    """Expected-pointer CAS; idempotent when target == current (§15)."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            state = (await conn.execute(text(
                "SELECT approved_revision_id FROM spatial_world_states "
                "WHERE id = :s"), {"s": state_id})).mappings().one_or_none()
            if state is None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "State not found.", 404)
            rev = (await conn.execute(text(
                "SELECT spatial_world_state_id, snapshot_hash, "
                "snapshot_json FROM spatial_world_revisions WHERE id = :r"),
                {"r": revision_id})).mappings().one_or_none()
            if rev is None:
                raise _err(ErrorCode.SPATIAL_WORLD_REVISION_NOT_FOUND,
                           f"Revision {revision_id} not found.", 404)
            if rev["spatial_world_state_id"] != state_id:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           "Revision belongs to a different state.", 409)
            # §14 integrity at the approval gate
            if canonical_hash(json.loads(rev["snapshot_json"])) != \
                    rev["snapshot_hash"]:
                raise internal_invariant(
                    "Revision snapshot bytes fail their stored hash.")
            current = state["approved_revision_id"]
            if current == revision_id:
                await conn.exec_driver_sql("COMMIT")  # idempotent
                return {"approved_revision_id": current,
                        "idempotent": True}
            if current != expected_approved_revision_id:
                raise _err(ErrorCode.SPATIAL_WORLD_APPROVAL_CONFLICT,
                           f"Expected approval pointer "
                           f"{expected_approved_revision_id!r} is stale; "
                           f"current is {current!r}.")
            await conn.execute(text(
                "UPDATE spatial_world_states SET approved_revision_id = :r,"
                " updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
                {"r": revision_id, "s": state_id})
            await conn.exec_driver_sql("COMMIT")
            return {"approved_revision_id": revision_id,
                    "idempotent": False}
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise internal_invariant(f"approval failed: {exc}") from exc


async def unapprove(session: AsyncSession, state_id: str, *,
                    expected_approved_revision_id: str | None) -> dict:
    """Unapprove with the same expected-current contract (§15)."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            state = (await conn.execute(text(
                "SELECT approved_revision_id FROM spatial_world_states "
                "WHERE id = :s"), {"s": state_id})).mappings().one_or_none()
            if state is None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "State not found.", 404)
            current = state["approved_revision_id"]
            if current is None:
                await conn.exec_driver_sql("COMMIT")
                return {"approved_revision_id": None, "idempotent": True}
            if current != expected_approved_revision_id:
                raise _err(ErrorCode.SPATIAL_WORLD_APPROVAL_CONFLICT,
                           f"Expected approval pointer "
                           f"{expected_approved_revision_id!r} is stale; "
                           f"current is {current!r}.")
            await conn.execute(text(
                "UPDATE spatial_world_states SET approved_revision_id = "
                "NULL, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
                {"s": state_id})
            await conn.exec_driver_sql("COMMIT")
            return {"approved_revision_id": None, "idempotent": False}
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise internal_invariant(f"unapproval failed: {exc}") from exc


__all__ = ["capture_revision", "approve_revision", "unapprove"]
