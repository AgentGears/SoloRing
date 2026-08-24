"""M10C-1 SpatialTrack authority service (M10C plan §6, frozen r3 §§16-17, §57).

SpatialTrack lifecycle: one active track per (SpatialWorld, Entity) in
schema 1 (no instancing), identity immutable after creation, requirement
the only mutation, delete gated by explicit downgrade + active-transition
and current-plan blocking-reference guards. Every write is one fenced
BEGIN IMMEDIATE unit; the partial unique index is the race backstop.
"""
from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.ids import new_uuid, is_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.spatial.plan_reference import plan_blocking_references_track

REQUIREMENTS = ("required", "optional")


def _err(code: str, message: str, status: int = 422) -> SoloRingError:
    return SoloRingError(code, message, status_code=status)


def _requirement(value: object, what: str) -> str:
    if value not in REQUIREMENTS:
        raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                   f"{what} must be one of {list(REQUIREMENTS)}.")
    return value


async def _load_world_active(conn, world_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT id, project_id FROM spatial_worlds "
        "WHERE id = :w AND deleted_at IS NULL"),
        {"w": world_id})).mappings().first()
    if row is None:
        raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                   f"SpatialWorld {world_id} not found or deleted.", 404)
    return dict(row)


async def _load_track(conn, track_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT id, spatial_world_id, entity_id, requirement, created_at, "
        "updated_at, deleted_at FROM spatial_tracks WHERE id = :t"),
        {"t": track_id})).mappings().first()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_TRACK_INVALID,
                        f"SpatialTrack {track_id} not found.")
    return dict(row)


async def create_track(session: AsyncSession, world_id: str, *,
                       entity_id: str, requirement: str) -> dict:
    """Create ONE SpatialTrack as a single fenced write (M10C §6.2).

    The active (world, Entity) coordinate is single-occupancy in schema 1:
    a second active track is SPATIAL_ENTITY_INSTANCING_UNSUPPORTED, never
    a leaked uniqueness exception.
    """
    if not is_uuid(entity_id):
        raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                   "entity_id must be a uuid.")
    _requirement(requirement, "SpatialTrack.requirement")
    track_id = new_uuid()

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            world = await _load_world_active(conn, world_id)
            entity = (await conn.execute(text(
                "SELECT project_id FROM creative_entities "
                "WHERE id = :e AND deleted_at IS NULL"),
                {"e": entity_id})).first()
            if entity is None:
                raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                           f"Entity {entity_id} not found or inactive.", 404)
            if entity[0] != world["project_id"]:
                raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                           "Track Entity belongs to another Project.")
            active = (await conn.execute(text(
                "SELECT id FROM spatial_tracks "
                "WHERE spatial_world_id = :w AND entity_id = :e "
                "AND deleted_at IS NULL"),
                {"w": world_id, "e": entity_id})).first()
            if active is not None:
                raise _err(ErrorCode.SPATIAL_ENTITY_INSTANCING_UNSUPPORTED,
                           "Entity already has an active SpatialTrack in "
                           "this world (schema 1: no simultaneous "
                           "instancing).", 409)
            await conn.execute(text(
                "INSERT INTO spatial_tracks (id, spatial_world_id, "
                "entity_id, requirement, created_at, updated_at) VALUES "
                "(:id,:w,:e,:r,strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
                {"id": track_id, "w": world_id, "e": entity_id,
                 "r": requirement})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            if isinstance(exc, IntegrityError) and \
                    "uq_st_active_world_entity" in str(exc):
                raise _err(
                    ErrorCode.SPATIAL_ENTITY_INSTANCING_UNSUPPORTED,
                    "Entity already has an active SpatialTrack in this "
                    "world (schema 1: no simultaneous instancing).", 409
                ) from exc
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"track creation failed: {exc}", 500) from exc
    return {"id": track_id, "requirement": requirement}


async def get_track(session: AsyncSession, track_id: str) -> dict:
    row = (await session.execute(text(
        "SELECT id, spatial_world_id, entity_id, requirement, created_at, "
        "updated_at, deleted_at FROM spatial_tracks WHERE id = :t"),
        {"t": track_id})).mappings().one_or_none()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_TRACK_INVALID,
                        f"SpatialTrack {track_id} not found.")
    return dict(row)


async def list_tracks(session: AsyncSession, world_id: str) -> list[dict]:
    """Active tracks of one world in canonical (entity_id, id) order."""
    rows = (await session.execute(text(
        "SELECT id, spatial_world_id, entity_id, requirement, created_at, "
        "updated_at FROM spatial_tracks WHERE spatial_world_id = :w "
        "AND deleted_at IS NULL ORDER BY entity_id, id"),
        {"w": world_id})).mappings().all()
    return [dict(r) for r in rows]


async def patch_track(session: AsyncSession, track_id: str, *,
                      requirement: str | None = None) -> None:
    """The only schema-1 mutation: explicit requirement policy edit.

    spatial_world_id/entity_id are identity-bearing and immutable (§6.3);
    retargeting would reinterpret the track's transition history.
    """
    if requirement is None:
        return
    _requirement(requirement, "SpatialTrack.requirement")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            track = await _load_track(conn, track_id)
            if track["deleted_at"] is not None:
                raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                           "Cannot patch a deleted SpatialTrack.", 409)
            await conn.execute(text(
                "UPDATE spatial_tracks SET requirement = :r, updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :t"),
                {"r": requirement, "t": track_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"track patch failed: {exc}", 500) from exc


async def delete_track(session: AsyncSession, track_id: str) -> None:
    """Soft-delete an optional, unreferenced track (§6.5/§6.6/§57).

    Blocked while required (explicit downgrade first), while any active
    SpatialTransition references it, or while any current plan blocking
    entry references it. Plan inspection is the read-only schema-1
    reader and fails CLOSED on unreadable documents.
    """
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            track = await _load_track(conn, track_id)
            if track["deleted_at"] is not None:
                return  # idempotent
            if track["requirement"] == "required":
                raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                           "A required SpatialTrack cannot be deleted "
                           "directly; change it to optional first.", 409)
            transition = (await conn.execute(text(
                "SELECT id FROM spatial_transitions "
                "WHERE spatial_track_id = :t AND deleted_at IS NULL"),
                {"t": track_id})).first()
            if transition is not None:
                raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                           "Track has active SpatialTransitions.", 409)
            plans = (await conn.execute(text(
                "SELECT plan_json FROM shot_spatial_plans "
                "WHERE spatial_world_id = :w"),
                {"w": track["spatial_world_id"]})).scalars().all()
            for plan_json in plans:
                # raises INTERNAL_INVARIANT_VIOLATION on unreadable docs
                if plan_blocking_references_track(
                        plan_json,
                        row_spatial_world_id=track["spatial_world_id"],
                        spatial_track_id=track_id):
                    raise _err(ErrorCode.SPATIAL_TRACK_INVALID,
                               "Track is referenced by a current "
                               "ShotSpatialPlan blocking entry.", 409)
            await conn.execute(text(
                "UPDATE spatial_tracks SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :t"),
                {"t": track_id})
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _err(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                       f"track delete failed: {exc}", 500) from exc


__all__ = ["create_track", "get_track", "list_tracks", "patch_track",
           "delete_track", "REQUIREMENTS"]
