"""M10C-2 SpatialTransition authority service (M10C plan §7, frozen r3 §17).

Explicit narrative-boundary placement events: one active transition per
(track, anchor_type, anchor_id, boundary) coordinate, exact set|clear
aggregate transform semantics (set = six values, clear = none), numeric
authority reused from soloring.spatial.math, anchors validated by the
canonical M7 authority (continuity.transitions._validate_anchor_in_ordering
— imported, never re-implemented; error identity translated to the frozen
spatial vocabulary at this boundary). Every write is one fenced unit.
"""
from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.continuity.transitions import _validate_anchor_in_ordering
from soloring.domain.ids import new_uuid, is_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.spatial.math import normalize_udeg, validate_int

ANCHOR_TYPES = ("sequence", "scene", "shot")
BOUNDARIES = ("start", "end")
OPERATIONS = ("set", "clear")


def _err(code: str, message: str, status: int = 422) -> SoloRingError:
    return SoloRingError(code, message, status_code=status)


def _invalid(message: str) -> SoloRingError:
    return _err(ErrorCode.SPATIAL_TRANSITION_INVALID, message)


class _Unset:
    """PATCH sentinel: omitted (preserve) vs explicit null (requested)."""


UNSET = _Unset()


def _transform_columns(translation_mm: object, rotation_udeg: object,
                       ) -> tuple[int, int, int, int, int, int]:
    """Validate one complete set-transform into its six column values."""
    if not isinstance(translation_mm, (list, tuple)) or \
            len(translation_mm) != 3:
        raise _invalid("translation_mm must be a 3-vector.")
    if not isinstance(rotation_udeg, (list, tuple)) or len(rotation_udeg) != 3:
        raise _invalid("rotation_udeg must be a 3-vector.")
    try:
        x, y, z = (validate_int(v, "translation") for v in translation_mm)
        yaw, pitch, roll = (normalize_udeg(v) for v in rotation_udeg)
    except ValueError as exc:
        raise _invalid(f"transform: {exc}") from exc
    return x, y, z, yaw, pitch, roll


async def _load_track(conn, track_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT id, spatial_world_id, entity_id, requirement, deleted_at "
        "FROM spatial_tracks WHERE id = :t"),
        {"t": track_id})).mappings().first()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_TRANSITION_INVALID,
                        f"SpatialTrack {track_id} not found.")
    return dict(row)


async def _load_transition(conn, transition_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT id, spatial_track_id, anchor_type, anchor_id, boundary, "
        "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
        "deleted_at FROM spatial_transitions WHERE id = :i"),
        {"i": transition_id})).mappings().first()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_TRANSITION_INVALID,
                        f"SpatialTransition {transition_id} not found.")
    return dict(row)


async def _validate_anchor(conn, project_id: str, anchor_type: str,
                           anchor_id: str) -> None:
    """Canonical M7 anchor authority, translated to spatial vocabulary."""
    try:
        await _validate_anchor_in_ordering(
            conn, project_id, anchor_type, anchor_id)
    except SoloRingError as exc:
        raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID, exc.message,
                   exc.status_code) from exc


async def _coordinate_taken(conn, track_id: str, anchor_type: str,
                            anchor_id: str, boundary: str,
                            *, exclude: str | None = None) -> bool:
    sql = ("SELECT id FROM spatial_transitions WHERE spatial_track_id = :t "
           "AND anchor_type = :at AND anchor_id = :a AND boundary = :b "
           "AND deleted_at IS NULL")
    params: dict = {"t": track_id, "at": anchor_type, "a": anchor_id,
                    "b": boundary}
    if exclude is not None:
        sql += " AND id <> :x"
        params["x"] = exclude
    return (await conn.execute(text(sql), params)).first() is not None


async def _world_project_active(conn, world_id: str) -> str:
    """The owning world's Project — failing CLOSED if the world is
    missing or tombstoned: transition authority is never authored
    beneath a deleted SpatialWorld (world-delete guard normally
    prevents this; this also covers direct-DB corruption)."""
    row = (await conn.execute(text(
        "SELECT project_id, deleted_at FROM spatial_worlds "
        "WHERE id = :w"), {"w": world_id})).first()
    if row is None:
        raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                   f"Owning SpatialWorld {world_id} not found.", 404)
    if row[1] is not None:
        raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                   "Cannot author transitions beneath a deleted "
                   "SpatialWorld.", 409)
    return row[0]


async def create_transition(session: AsyncSession, track_id: str, *,
                            anchor_type: str, anchor_id: str,
                            boundary: str, operation: str,
                            translation_mm=None, rotation_udeg=None) -> dict:
    """Author ONE explicit placement event as a single fenced write."""
    if anchor_type not in ANCHOR_TYPES:
        raise _invalid(f"anchor_type must be one of {list(ANCHOR_TYPES)}.")
    if boundary not in BOUNDARIES:
        raise _invalid(f"boundary must be one of {list(BOUNDARIES)}.")
    if operation not in OPERATIONS:
        raise _invalid(f"operation must be one of {list(OPERATIONS)}.")
    if not is_uuid(anchor_id):
        raise _invalid(f"Invalid anchor_id {anchor_id!r}.")
    if operation == "set":
        if translation_mm is None or rotation_udeg is None:
            raise _invalid("operation=set requires a complete transform "
                           "(translation_mm and rotation_udeg).")
        cols = _transform_columns(translation_mm, rotation_udeg)
    else:  # clear
        if translation_mm is not None or rotation_udeg is not None:
            raise _invalid("operation=clear carries no transform values.")
        cols = (None,) * 6
    transition_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            track = await _load_track(conn, track_id)
            if track["deleted_at"] is not None:
                raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                           "Cannot author a transition on a deleted "
                           "SpatialTrack.", 409)
            project_id = await _world_project_active(
                conn, track["spatial_world_id"])
            await _validate_anchor(conn, project_id, anchor_type, anchor_id)
            if await _coordinate_taken(conn, track_id, anchor_type, anchor_id,
                                       boundary):
                raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                           f"An active transition already occupies "
                           f"({anchor_type}, {anchor_id}, {boundary}) for "
                           "this Track.", 409)
            await conn.execute(text(
                "INSERT INTO spatial_transitions (id, spatial_track_id, "
                "anchor_type, anchor_id, boundary, operation, x_mm, y_mm, "
                "z_mm, yaw_udeg, pitch_udeg, roll_udeg, created_at, "
                "updated_at) VALUES (:i,:t,:at,:a,:b,:op,:x,:y,:z,:yaw,"
                ":pitch,:roll,strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"i": transition_id, "t": track_id, "at": anchor_type,
                 "a": anchor_id, "b": boundary, "op": operation,
                 "x": cols[0], "y": cols[1], "z": cols[2],
                 "yaw": cols[3], "pitch": cols[4], "roll": cols[5]})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            if isinstance(exc, IntegrityError) and \
                    "uq_str_active_coordinate" in str(exc):
                raise _err(
                    ErrorCode.SPATIAL_TRANSITION_INVALID,
                    "An active transition already occupies this coordinate.",
                    409) from exc
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"transition creation failed: {exc}", 500) from exc
    return {"id": transition_id}


async def get_transition(session: AsyncSession, transition_id: str) -> dict:
    row = (await session.execute(text(
        "SELECT id, spatial_track_id, anchor_type, anchor_id, boundary, "
        "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
        "created_at, updated_at, deleted_at FROM spatial_transitions "
        "WHERE id = :i"), {"i": transition_id})).mappings().one_or_none()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_TRANSITION_INVALID,
                        f"SpatialTransition {transition_id} not found.")
    return dict(row)


async def list_transitions(session: AsyncSession,
                           track_id: str) -> list[dict]:
    """Active transitions of one track in a stable coordinate order."""
    rows = (await session.execute(text(
        "SELECT id, spatial_track_id, anchor_type, anchor_id, boundary, "
        "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
        "created_at, updated_at FROM spatial_transitions "
        "WHERE spatial_track_id = :t AND deleted_at IS NULL "
        "ORDER BY anchor_type, anchor_id, boundary, id"),
        {"t": track_id})).mappings().all()
    return [dict(r) for r in rows]


async def patch_transition(session: AsyncSession, transition_id: str, *,
                           anchor_type=UNSET, anchor_id=UNSET,
                           boundary=UNSET, operation=UNSET,
                           translation_mm=UNSET, rotation_udeg=UNSET) -> None:
    """PATCH one COMPLETE prospective transition (M10C plan §7.6).

    Omitted fields preserve; the resulting aggregate must always be one
    of the two legal forms (set = six values, clear = none). Anchor/
    boundary changes revalidate the complete prospective coordinate.
    """
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = await _load_transition(conn, transition_id)
            if row["deleted_at"] is not None:
                raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                           "Cannot patch a deleted SpatialTransition.", 409)

            # prospective coordinate
            p_at = row["anchor_type"] if anchor_type is UNSET else anchor_type
            p_aid = row["anchor_id"] if anchor_id is UNSET else anchor_id
            p_b = row["boundary"] if boundary is UNSET else boundary
            for name, val, domain in (("anchor_type", p_at, ANCHOR_TYPES),
                                      ("boundary", p_b, BOUNDARIES)):
                if val not in domain:
                    raise _invalid(f"{name} must be one of {list(domain)}.")
            if not is_uuid(p_aid):
                raise _invalid(f"Invalid anchor_id {p_aid!r}.")

            # prospective operation
            p_op = row["operation"] if operation is UNSET else operation
            if p_op not in OPERATIONS:
                raise _invalid(f"operation must be one of {list(OPERATIONS)}.")

            # prospective transform — build from patches over current
            cur_t = (row["x_mm"], row["y_mm"], row["z_mm"])
            cur_r = (row["yaw_udeg"], row["pitch_udeg"], row["roll_udeg"])
            p_t = translation_mm
            p_r = rotation_udeg

            if p_op == "clear":
                # explicit nulls are legal (they ARE the aggregate's null
                # values); any non-null transform with clear is illegal
                for v in (p_t, p_r):
                    if v is not UNSET and v is not None:
                        raise _invalid("operation=clear carries no "
                                       "transform values.")
                cols = (None,) * 6
            else:  # prospective set
                if p_t is UNSET:
                    p_t = cur_t if None not in cur_t else None
                if p_r is UNSET:
                    p_r = cur_r if None not in cur_r else None
                if p_t is None or p_r is None:
                    raise _invalid("operation=set requires a complete "
                                   "transform (translation_mm and "
                                   "rotation_udeg).")
                cols = _transform_columns(p_t, p_r)

            anchor_changed = (p_at != row["anchor_type"] or
                              p_aid != row["anchor_id"] or
                              p_b != row["boundary"])
            nothing_changed = (
                not anchor_changed and p_op == row["operation"] and
                cols == (row["x_mm"], row["y_mm"], row["z_mm"],
                         row["yaw_udeg"], row["pitch_udeg"],
                         row["roll_udeg"]))
            if nothing_changed:
                await conn.exec_driver_sql("COMMIT")
                return

            track = await _load_track(conn, row["spatial_track_id"])
            project_id = await _world_project_active(
                conn, track["spatial_world_id"])
            await _validate_anchor(conn, project_id, p_at, p_aid)
            if await _coordinate_taken(conn, row["spatial_track_id"], p_at,
                                       p_aid, p_b, exclude=transition_id):
                raise _err(ErrorCode.SPATIAL_TRANSITION_INVALID,
                           f"An active transition already occupies "
                           f"({p_at}, {p_aid}, {p_b}) for this Track.", 409)
            await conn.execute(text(
                "UPDATE spatial_transitions SET anchor_type = :at, "
                "anchor_id = :a, boundary = :b, operation = :op, "
                "x_mm = :x, y_mm = :y, z_mm = :z, yaw_udeg = :yaw, "
                "pitch_udeg = :pitch, roll_udeg = :roll, updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :i"),
                {"at": p_at, "a": p_aid, "b": p_b, "op": p_op,
                 "x": cols[0], "y": cols[1], "z": cols[2],
                 "yaw": cols[3], "pitch": cols[4], "roll": cols[5],
                 "i": transition_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"transition patch failed: {exc}", 500) from exc


async def delete_transition(session: AsyncSession, transition_id: str) -> None:
    """Soft-delete; the coordinate is freed for a NEW identity (§7.7)."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = await _load_transition(conn, transition_id)
            if row["deleted_at"] is not None:
                return  # idempotent
            await conn.execute(text(
                "UPDATE spatial_transitions SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :i"),
                {"i": transition_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"transition delete failed: {exc}", 500) from exc


__all__ = ["create_transition", "get_transition", "list_transitions",
           "patch_transition", "delete_transition", "UNSET",
           "ANCHOR_TYPES", "BOUNDARIES", "OPERATIONS"]
