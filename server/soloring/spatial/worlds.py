"""M10B world authority services (frozen r3 §§8-11, 16).

SpatialWorld CRUD/policy, SpatialWorldState management, SpatialFrame/
SpatialAxis authoring, explicit state membership/value — every write a
fenced unit; every ownership rule enforced beyond bare FK existence.
Revision capture and approval live in revisions.py; the working-set
services here are the only mutation surface below them.
"""
from __future__ import annotations

import contextlib
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import db_now_sql
from soloring.domain.ids import new_uuid, is_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.spatial.math import (
    normalize_udeg,
    validate_int,
)

REQUIREMENTS = ("required", "optional")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_HALF_NONE = (None, None, None)


def _err(code: str, message: str, status: int = 422) -> SoloRingError:
    return SoloRingError(code, message, status_code=status)


def _semantic_key(value: object, what: str) -> str:
    if not isinstance(value, str) or not KEY_RE.fullmatch(value):
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                   f"{what} violates the canonical key grammar "
                   "^[a-z0-9][a-z0-9._-]{0,127}$.")
    return value


def _norm_text(value: object, what: str, *, required: bool = True) -> str | None:
    if value is None:
        if required:
            raise _err(ErrorCode.SPATIAL_WORLD_INVALID, f"{what} is required.")
        return None
    if not isinstance(value, str):
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID, f"{what} must be a string.")
    v = value.strip()
    if required and not v:
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID, f"{what} must not be empty.")
    return v or None


def _requirement(value: object, what: str) -> str:
    if value not in REQUIREMENTS:
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                   f"{what} must be one of {list(REQUIREMENTS)}.")
    return value


def _transform_fields(
    translation_mm: object, rotation_udeg: object, what: str
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    if not isinstance(translation_mm, (list, tuple)) or len(translation_mm) != 3:
        raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                   f"{what}.translation_mm must be a 3-vector.")
    if not isinstance(rotation_udeg, (list, tuple)) or len(rotation_udeg) != 3:
        raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                   f"{what}.rotation_udeg must be a 3-vector.")
    try:
        t = tuple(validate_int(v, f"{what}.translation") for v in translation_mm)
        r = tuple(normalize_udeg(v) for v in rotation_udeg)
    except ValueError as exc:
        raise _err(ErrorCode.SPATIAL_FRAME_INVALID, f"{what}: {exc}") from exc
    return t, r  # type: ignore[return-value]


def _half_extents(value: object, what: str):
    if value is None:
        return _HALF_NONE
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                   f"{what}.half_extents_mm must be a 3-vector or null.")
    for v in value:
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                       f"{what}.half_extents_mm must be strictly positive "
                       "integers.")
    return tuple(value)


async def _verify_active_project(conn, project_id: str) -> None:
    row = (await conn.execute(text(
        "SELECT id FROM projects WHERE id = :p AND deleted_at IS NULL"),
        {"p": project_id})).first()
    if row is None:
        raise not_found(ErrorCode.PROJECT_NOT_FOUND,
                        f"Project {project_id} not found.")


async def _load_world_for_update(conn, world_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT w.id, w.project_id, w.location_entity_id, w.key, w.name, "
        "w.requirement, w.deleted_at FROM spatial_worlds w WHERE w.id = :w"),
        {"w": world_id})).mappings().first()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_WORLD_REVISION_NOT_FOUND,
                        f"SpatialWorld {world_id} not found.")
    return dict(row)


async def _verify_location_entity(conn, project_id: str, entity_id: str) -> None:
    row = (await conn.execute(text(
        "SELECT kind FROM creative_entities "
        "WHERE id = :e AND project_id = :p AND deleted_at IS NULL"),
        {"e": entity_id, "p": project_id})).first()
    if row is None:
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                   f"Location Entity {entity_id} is not an active Entity of "
                   "this Project.", 404)
    if row[0] != "location":
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                   f"Owning Entity must be kind 'location', got {row[0]!r}.")


# --------------------------------------------------------------------------
# SpatialWorld CRUD (§8)
# --------------------------------------------------------------------------

async def create_world(session: AsyncSession, project_id: str, *, key: str,
                       name: str, description: str | None,
                       requirement: str, location_entity_id: str) -> dict:
    """Create ONE SpatialWorld as a single fenced write (§8)."""
    if not is_uuid(project_id):
        raise not_found(ErrorCode.PROJECT_NOT_FOUND,
                        f"Project {project_id} not found.")
    key = _semantic_key(key, "SpatialWorld.key")
    name_v = _norm_text(name, "SpatialWorld.name")
    desc_v = _norm_text(description, "SpatialWorld.description", required=False)
    _requirement(requirement, "SpatialWorld.requirement")
    if not is_uuid(location_entity_id):
        raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                   "location_entity_id must be a uuid.")
    world_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_project(conn, project_id)
            await _verify_location_entity(conn, project_id, location_entity_id)
            dupe = (await conn.execute(text(
                "SELECT id FROM spatial_worlds WHERE project_id=:p AND key=:k"),
                {"p": project_id, "k": key})).first()
            if dupe is not None:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           f"key {key!r} already exists in this Project "
                           "(tombstone-inclusive; keys never recycle).", 409)
            active = (await conn.execute(text(
                "SELECT id, key FROM spatial_worlds "
                "WHERE location_entity_id = :e AND deleted_at IS NULL"),
                {"e": location_entity_id})).first()
            if active is not None:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           f"Entity already has active world {active[1]!r} "
                           "(one active world per Location in schema 1).", 409)
            await conn.execute(text(
                "INSERT INTO spatial_worlds (id, project_id, "
                "location_entity_id, key, name, description, requirement, "
                "created_at, updated_at) VALUES (:id,:p,:e,:k,:n,:d,:r,"
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": world_id, "p": project_id, "e": location_entity_id,
                 "k": key, "n": name_v, "d": desc_v, "r": requirement})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"world creation failed: {exc}", 500) from exc
    return {"id": world_id, "key": key, "requirement": requirement}


async def patch_world(session: AsyncSession, world_id: str, *,
                       name: str | None = None,
                       description: str | None = None,
                       requirement: str | None = None) -> None:
    """Mutable display metadata + explicit requirement policy edit.

    key is immutable (§8). requirement change is an explicit production-
    policy edit and is included in race proofs (§61-9).
    """
    sets, params = [], {"w": world_id}
    if name is not None:
        params["n"] = _norm_text(name, "SpatialWorld.name")
        sets.append("name = :n")
    if description is not None:
        params["d"] = _norm_text(
            description, "SpatialWorld.description", required=False)
        sets.append("description = :d")
    if requirement is not None:
        params["r"] = _requirement(requirement, "SpatialWorld.requirement")
        sets.append("requirement = :r")
    if not sets:
        return
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            world = await _load_world_for_update(conn, world_id)
            if world["deleted_at"] is not None:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           "Cannot patch a deleted SpatialWorld.", 409)
            await conn.execute(text(
                f"UPDATE spatial_worlds SET {', '.join(sets)}, "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :w"), params)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"world patch failed: {exc}", 500) from exc


async def delete_world(session: AsyncSession, world_id: str) -> None:
    """Required worlds must be downgraded to optional first (§8/§57)."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            world = await _load_world_for_update(conn, world_id)
            if world["deleted_at"] is not None:
                return  # idempotent
            if world["requirement"] == "required":
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           "A required SpatialWorld cannot be deleted "
                           "directly; change it to optional first.", 409)
            plan = (await conn.execute(text(
                "SELECT shot_id FROM shot_spatial_plans WHERE spatial_world_id = :w"),
                {"w": world_id})).first()
            if plan is not None:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           "World is selected by an active ShotSpatialPlan.",
                           409)
            states = (await conn.execute(text(
                "SELECT COUNT(*) FROM spatial_world_states "
                "WHERE spatial_world_id = :w"), {"w": world_id})).scalar()
            if states:
                raise _err(ErrorCode.SPATIAL_WORLD_INVALID,
                           "World has permanent SpatialWorldState identity "
                           "(schema 1: no state delete lifecycle).", 409)
            await conn.execute(text(
                "UPDATE spatial_worlds SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :w"),
                {"w": world_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"world delete failed: {exc}", 500) from exc


# --------------------------------------------------------------------------
# SpatialWorldState (§9) — permanent identity per (world, Location rev)
# --------------------------------------------------------------------------

async def create_state(session: AsyncSession, world_id: str, *,
                       location_entity_revision_id: str) -> dict:
    if not is_uuid(location_entity_revision_id):
        raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                   "location_entity_revision_id must be a uuid.")
    state_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            world = await _load_world_for_update(conn, world_id)
            rev = (await conn.execute(text(
                "SELECT er.entity_id FROM entity_revisions er "
                "WHERE er.id = :r"), {"r": location_entity_revision_id})
                ).first()
            if rev is None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "Location EntityRevision not found.", 404)
            if rev[0] != world["location_entity_id"]:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "EntityRevision belongs to a different Entity "
                           "than the world's Location.")
            existing = (await conn.execute(text(
                "SELECT id FROM spatial_world_states "
                "WHERE spatial_world_id = :w AND "
                "location_entity_revision_id = :r"),
                {"w": world_id, "r": location_entity_revision_id})).first()
            if existing is not None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "State for this (world, Location revision) "
                           "already exists (permanent identity).", 409)
            await conn.execute(text(
                "INSERT INTO spatial_world_states (id, spatial_world_id, "
                "location_entity_revision_id, created_at, updated_at) "
                "VALUES (:id,:w,:r,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": state_id, "w": world_id,
                 "r": location_entity_revision_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"state creation failed: {exc}", 500) from exc
    return {"id": state_id}


# --------------------------------------------------------------------------
# SpatialFrame (§10) — stable identity + state membership/value
# --------------------------------------------------------------------------

async def create_frame(session: AsyncSession, world_id: str, *, key: str,
                       name: str, parent_spatial_frame_id: str | None,
                       bound_entity_id: str | None) -> dict:
    key = _semantic_key(key, "SpatialFrame.key")
    name_v = _norm_text(name, "SpatialFrame.name")
    frame_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            world = await _load_world_for_update(conn, world_id)
            dupe = (await conn.execute(text(
                "SELECT id FROM spatial_frames "
                "WHERE spatial_world_id = :w AND key = :k"),
                {"w": world_id, "k": key})).first()
            if dupe is not None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           f"frame key {key!r} already exists in this world "
                           "(tombstone-inclusive).", 409)
            if parent_spatial_frame_id is not None:
                parent = (await conn.execute(text(
                    "SELECT spatial_world_id FROM spatial_frames "
                    "WHERE id = :p"), {"p": parent_spatial_frame_id})).first()
                if parent is None:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Parent frame not found.", 404)
                if parent[0] != world_id:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Parent belongs to a different world.")
                if parent_spatial_frame_id == frame_id:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Frame cannot be its own parent.")
            if bound_entity_id is not None:
                be = (await conn.execute(text(
                    "SELECT project_id FROM creative_entities "
                    "WHERE id = :e AND deleted_at IS NULL"),
                    {"e": bound_entity_id})).first()
                if be is None:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Bound Entity not found/inactive.", 404)
                if be[0] != world["project_id"]:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Bound Entity belongs to another Project.")
            await conn.execute(text(
                "INSERT INTO spatial_frames (id, spatial_world_id, key, "
                "name, parent_spatial_frame_id, bound_entity_id, "
                "created_at, updated_at) VALUES (:id,:w,:k,:n,:p,:b,"
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": frame_id, "w": world_id, "k": key, "n": name_v,
                 "p": parent_spatial_frame_id, "b": bound_entity_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"frame creation failed: {exc}", 500) from exc
    return {"id": frame_id, "key": key}


async def _assert_frame_cycle_free(conn, world_id: str) -> None:
    """The stable parent graph must be acyclic (§10.1)."""
    rows = (await conn.execute(text(
        "SELECT id, parent_spatial_frame_id FROM spatial_frames "
        "WHERE spatial_world_id = :w"), {"w": world_id})).mappings().all()
    parents = {r["id"]: r["parent_spatial_frame_id"] for r in rows}
    for fid in parents:
        walker, hops = fid, 0
        while walker is not None:
            hops += 1
            if hops > len(parents) + 1:
                raise _err(ErrorCode.SPATIAL_FRAME_CYCLE,
                           "Frame parent graph is cyclic.", 409)
            walker = parents.get(walker)


async def delete_frame(session: AsyncSession, frame_id: str) -> None:
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            frame = (await conn.execute(text(
                "SELECT spatial_world_id, key FROM spatial_frames "
                "WHERE id = :f"), {"f": frame_id})).first()
            if frame is None:
                raise not_found(ErrorCode.SPATIAL_FRAME_INVALID,
                                f"Frame {frame_id} not found.")
            child = (await conn.execute(text(
                "SELECT id FROM spatial_frames "
                "WHERE parent_spatial_frame_id = :f AND deleted_at IS NULL"),
                {"f": frame_id})).first()
            if child is not None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame is a parent of active child frames.", 409)
            member = (await conn.execute(text(
                "SELECT spatial_world_state_id FROM "
                "spatial_world_state_frames WHERE spatial_frame_id = :f"),
                {"f": frame_id})).first()
            if member is not None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame has state membership rows.", 409)
            endpoint = (await conn.execute(text(
                "SELECT spatial_world_state_id FROM "
                "spatial_world_state_axes WHERE a_frame_id = :f "
                "OR b_frame_id = :f"), {"f": frame_id})).first()
            if endpoint is not None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame is a state-axis endpoint.", 409)
            await conn.execute(text(
                "UPDATE spatial_frames SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :f"),
                {"f": frame_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"frame delete failed: {exc}", 500) from exc


# --------------------------------------------------------------------------
# State membership/value: PUT frame value into a state (§10.2)
# --------------------------------------------------------------------------

async def put_state_frame(session: AsyncSession, state_id: str,
                          frame_id: str, *, translation_mm, rotation_udeg,
                          half_extents_mm, bound_entity_revision_id=None
                          ) -> None:
    """Insert-or-replace the state value of one included frame."""
    t, r = _transform_fields(translation_mm, rotation_udeg, "state frame")
    he = _half_extents(half_extents_mm, "state frame")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            state = (await conn.execute(text(
                "SELECT spatial_world_id FROM spatial_world_states "
                "WHERE id = :s"), {"s": state_id})).first()
            if state is None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "State not found.", 404)
            frame = (await conn.execute(text(
                "SELECT spatial_world_id, parent_spatial_frame_id, "
                "bound_entity_id FROM spatial_frames WHERE id = :f "
                "AND deleted_at IS NULL"), {"f": frame_id})).mappings().first()
            if frame is None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame not found or deleted.", 404)
            if frame["spatial_world_id"] != state[0]:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame belongs to a different world.")
            if frame["parent_spatial_frame_id"] is not None:
                parent_member = (await conn.execute(text(
                    "SELECT 1 FROM spatial_world_state_frames "
                    "WHERE spatial_world_state_id = :s AND "
                    "spatial_frame_id = :p"),
                    {"s": state_id,
                     "p": frame["parent_spatial_frame_id"]})).first()
                if parent_member is None:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Included child requires its parent in the "
                               "same state (§10.2).", 409)
            bound_entity_id = frame["bound_entity_id"]
            if bound_entity_id is None:
                if bound_entity_revision_id is not None:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Frame binds no Entity; revision must be "
                               "null.")
                be_id, be_rev = None, None
            else:
                if bound_entity_revision_id is None:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "Bound frame requires bound_entity_revision_id.")
                rev = (await conn.execute(text(
                    "SELECT entity_id FROM entity_revisions WHERE id = :r"),
                    {"r": bound_entity_revision_id})).first()
                if rev is None or rev[0] != bound_entity_id:
                    raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                               "bound_entity_revision_id does not belong to "
                               "the frame's bound Entity.", 404)
                be_id, be_rev = bound_entity_id, bound_entity_revision_id
            # one-placement backstop (DB partial unique also enforces)
            if be_id is not None:
                other = (await conn.execute(text(
                    "SELECT spatial_frame_id FROM "
                    "spatial_world_state_frames WHERE "
                    "spatial_world_state_id = :s AND bound_entity_id = :b "
                    "AND spatial_frame_id <> :f"),
                    {"s": state_id, "b": be_id, "f": frame_id})).first()
                if other is not None:
                    raise _err(ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT,
                               "Entity already bound to another frame in "
                               "this state.", 409)
            await conn.execute(text(
                "INSERT INTO spatial_world_state_frames ("
                "spatial_world_state_id, spatial_frame_id, bound_entity_id, "
                "bound_entity_revision_id, x_mm, y_mm, z_mm, yaw_udeg, "
                "pitch_udeg, roll_udeg, half_x_mm, half_y_mm, half_z_mm, "
                "updated_at) VALUES (:s,:f,:b,:br,:x,:y,:z,:yaw,:pitch,"
                ":roll,:hx,:hy,:hz,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(spatial_world_state_id,"
                "spatial_frame_id) DO UPDATE SET bound_entity_id=:b, "
                "bound_entity_revision_id=:br, x_mm=:x, y_mm=:y, z_mm=:z, "
                "yaw_udeg=:yaw, pitch_udeg=:pitch, roll_udeg=:roll, "
                "half_x_mm=:hx, half_y_mm=:hy, half_z_mm=:hz, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"),
                {"s": state_id, "f": frame_id, "b": be_id, "br": be_rev,
                 "x": t[0], "y": t[1], "z": t[2],
                 "yaw": r[0], "pitch": r[1], "roll": r[2],
                 "hx": he[0], "hy": he[1], "hz": he[2]})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"state-frame put failed: {exc}", 500) from exc


async def delete_state_frame(session: AsyncSession, state_id: str,
                             frame_id: str) -> None:
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            child = (await conn.execute(text(
                "SELECT sf.id FROM spatial_frames sf "
                "JOIN spatial_world_state_frames m ON "
                "m.spatial_frame_id = sf.id WHERE sf.parent_spatial_frame_id"
                " = :f AND m.spatial_world_state_id = :s"),
                {"f": frame_id, "s": state_id})).first()
            if child is not None:
                raise _err(ErrorCode.SPATIAL_FRAME_INVALID,
                           "Frame has included children in this state.", 409)
            axis = (await conn.execute(text(
                "SELECT spatial_axis_id FROM spatial_world_state_axes "
                "WHERE spatial_world_state_id = :s AND (a_frame_id = :f "
                "OR b_frame_id = :f)"),
                {"s": state_id, "f": frame_id})).first()
            if axis is not None:
                raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                           "Frame is a state-axis endpoint.", 409)
            await conn.execute(text(
                "DELETE FROM spatial_world_state_frames WHERE "
                "spatial_world_state_id = :s AND spatial_frame_id = :f"),
                {"s": state_id, "f": frame_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"state-frame delete failed: {exc}", 500) from exc


# --------------------------------------------------------------------------
# SpatialAxis (§11) — stable identity + state endpoints
# --------------------------------------------------------------------------

async def create_axis(session: AsyncSession, world_id: str, *, key: str,
                      name: str) -> dict:
    key = _semantic_key(key, "SpatialAxis.key")
    name_v = _norm_text(name, "SpatialAxis.name")
    axis_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _load_world_for_update(conn, world_id)
            dupe = (await conn.execute(text(
                "SELECT id FROM spatial_axes WHERE spatial_world_id = :w "
                "AND key = :k"), {"w": world_id, "k": key})).first()
            if dupe is not None:
                raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                           f"axis key {key!r} already exists "
                           "(tombstone-inclusive).", 409)
            await conn.execute(text(
                "INSERT INTO spatial_axes (id, spatial_world_id, key, name,"
                " created_at, updated_at) VALUES (:id,:w,:k,:n,strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": axis_id, "w": world_id, "k": key, "n": name_v})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"axis creation failed: {exc}", 500) from exc
    return {"id": axis_id, "key": key}


async def put_state_axis(session: AsyncSession, state_id: str, axis_id: str,
                         *, a_frame_id: str, b_frame_id: str) -> None:
    if a_frame_id == b_frame_id:
        raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                   "Axis endpoints must differ (§11).")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            state = (await conn.execute(text(
                "SELECT spatial_world_id FROM spatial_world_states "
                "WHERE id = :s"), {"s": state_id})).first()
            if state is None:
                raise _err(ErrorCode.SPATIAL_WORLD_STATE_INVALID,
                           "State not found.", 404)
            axis = (await conn.execute(text(
                "SELECT spatial_world_id FROM spatial_axes WHERE id = :a "
                "AND deleted_at IS NULL"), {"a": axis_id})).first()
            if axis is None or axis[0] != state[0]:
                raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                           "Axis not found or belongs to another world.", 404)
            for endpoint in (a_frame_id, b_frame_id):
                member = (await conn.execute(text(
                    "SELECT 1 FROM spatial_world_state_frames WHERE "
                    "spatial_world_state_id = :s AND spatial_frame_id = :f"),
                    {"s": state_id, "f": endpoint})).first()
                if member is None:
                    raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                               f"Endpoint frame {endpoint} is not included "
                               "in this state (§11).", 409)
            # degenerate axis: identical endpoint X/Z positions (§11.1)
            pts = (await conn.execute(text(
                "SELECT x_mm, z_mm FROM spatial_world_state_frames WHERE "
                "spatial_world_state_id = :s AND spatial_frame_id IN (:a,:b)"),
                {"s": state_id, "a": a_frame_id, "b": b_frame_id})).all()
            if len(pts) == 2 and pts[0][0] == pts[1][0] and \
                    pts[0][1] == pts[1][1]:
                raise _err(ErrorCode.SPATIAL_AXIS_INVALID,
                           "Axis endpoint X/Z positions coincide.", 409)
            await conn.execute(text(
                "INSERT INTO spatial_world_state_axes ("
                "spatial_world_state_id, spatial_axis_id, a_frame_id, "
                "b_frame_id, updated_at) VALUES (:s,:a,:fa,:fb,strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                "ON CONFLICT(spatial_world_state_id, spatial_axis_id) DO "
                "UPDATE SET a_frame_id=:fa, b_frame_id=:fb, "
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"),
                {"s": state_id, "a": axis_id, "fa": a_frame_id,
                 "fb": b_frame_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"state-axis put failed: {exc}", 500) from exc


async def delete_state_axis(session: AsyncSession, state_id: str,
                            axis_id: str) -> None:
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await conn.execute(text(
                "DELETE FROM spatial_world_state_axes WHERE "
                "spatial_world_state_id = :s AND spatial_axis_id = :a"),
                {"s": state_id, "a": axis_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"state-axis delete failed: {exc}", 500) from exc


__all__ = [
    "create_world", "patch_world", "delete_world", "create_state",
    "create_frame", "delete_frame", "put_state_frame", "delete_state_frame",
    "create_axis", "put_state_axis", "delete_state_axis",
]
