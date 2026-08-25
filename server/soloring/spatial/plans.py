"""M10D-1 ShotSpatialPlan persistence, ownership validation, and CAS
lifecycle (M10D plan §§6, 14-15; frozen r3 §19, §74).

The pure document grammar lives in spatial/schemas.py (the ONE parser,
evolved in place — normalized returned transforms, plan-specific error
identity). This service owns the fenced write unit: active Shot +
duration context, current-row CAS on exact plan_hash, write-time
ownership validation (active same-Project world whose Location is a
current dependency; active in-world blocking Tracks of current
dependencies; active in-world axis), and the shot_spatial_plans row.
Mutable readiness facts (state/approval/staging/blocking agreement) are
deliberately NOT write-time conditions (§14): a plan may be authored
before world approval is complete.
"""
from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.spatial.schemas import parse_shot_plan, plan_hash


def _invalid(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.SPATIAL_SHOT_PLAN_INVALID, message,
                         status_code=422)


def _conflict(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.SPATIAL_SHOT_PLAN_CONFLICT, message,
                         status_code=409)


async def _load_active_shot(conn, shot_id: str) -> dict:
    row = (await conn.execute(text(
        "SELECT id, project_id, duration_ms, deleted_at FROM shots "
        "WHERE id = :s"), {"s": shot_id})).mappings().first()
    if row is None or row["deleted_at"] is not None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"Shot {shot_id} not found.")
    return dict(row)


async def _load_current(conn, shot_id: str) -> dict | None:
    row = (await conn.execute(text(
        "SELECT plan_hash, plan_json FROM shot_spatial_plans "
        "WHERE shot_id = :s"), {"s": shot_id})).mappings().first()
    return dict(row) if row is not None else None


async def _validate_ownership(conn, shot: dict, canonical: dict) -> None:
    """Write-time ownership (§14) — active world of this Project whose
    Location is a current dependency; active in-world blocking Tracks of
    current dependencies; active in-world optional axis."""
    world = (await conn.execute(text(
        "SELECT id, project_id, location_entity_id, deleted_at "
        "FROM spatial_worlds WHERE id = :w"),
        {"w": canonical["spatial_world_id"]})).mappings().first()
    if world is None or world["deleted_at"] is not None:
        raise _invalid("Selected SpatialWorld is missing or deleted.")
    if world["project_id"] != shot["project_id"]:
        raise _invalid("Selected SpatialWorld belongs to another Project.")
    location_dep = (await conn.execute(text(
        "SELECT 1 FROM shot_entity_dependencies WHERE shot_id = :s "
        "AND entity_id = :e"),
        {"s": shot["id"], "e": world["location_entity_id"]})).first()
    if location_dep is None:
        raise _invalid("Selected world's Location Entity is not a current "
                       "semantic dependency of this Shot.")

    dep_ids = set((await conn.execute(text(
        "SELECT entity_id FROM shot_entity_dependencies "
        "WHERE shot_id = :s"), {"s": shot["id"]})).scalars().all())

    track_ids = [b["spatial_track_id"] for b in canonical["blocking"]]
    if track_ids:
        ph = ", ".join(f":t{i}" for i in range(len(track_ids)))
        params = {f"t{i}": t for i, t in enumerate(track_ids)}
        rows = (await conn.execute(text(
            f"SELECT id, spatial_world_id, entity_id, deleted_at "
            f"FROM spatial_tracks WHERE id IN ({ph})"), params)
        ).mappings().all()
        by_id = {r["id"]: r for r in rows}
        for tid in track_ids:
            tr = by_id.get(tid)
            if tr is None or tr["deleted_at"] is not None:
                raise _invalid(f"Blocking Track {tid} is missing or "
                               "deleted.")
            if tr["spatial_world_id"] != world["id"]:
                raise _invalid(f"Blocking Track {tid} belongs to a "
                               "different SpatialWorld.")
            if tr["entity_id"] not in dep_ids:
                raise _invalid(f"Blocking Track {tid} binds an Entity "
                               "that is not a current semantic "
                               "dependency of this Shot.")

    axis = canonical["axis_constraint"]
    if axis is not None:
        ax = (await conn.execute(text(
            "SELECT id, spatial_world_id, deleted_at FROM spatial_axes "
            "WHERE id = :a"), {"a": axis["spatial_axis_id"]})).first()
        if ax is None or ax[2] is not None:
            raise _invalid("axis_constraint references a missing or "
                           "deleted SpatialAxis.")
        if ax[1] != world["id"]:
            raise _invalid("axis_constraint belongs to a different "
                           "SpatialWorld.")


async def put_spatial_plan(session: AsyncSession, shot_id: str, *,
                           expected_plan_hash: str | None,
                           plan_raw: dict) -> dict:
    """PUT with exact CAS semantics (§15.1-15.3, §15.5): create on
    null-expectation + absent row; replace on exact current hash; a
    canonically identical candidate is a true no-op returning the
    existing hash."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            shot = await _load_active_shot(conn, shot_id)
            current = await _load_current(conn, shot_id)

            if expected_plan_hash is None:
                if current is not None:
                    raise _conflict(
                        "A ShotSpatialPlan already exists for this Shot; "
                        "provide its exact expected_plan_hash to update.")
            else:
                if current is None or current["plan_hash"] != \
                        expected_plan_hash:
                    raise _conflict(
                        "expected_plan_hash does not match the current "
                        "ShotSpatialPlan (stale, null, or absent).")

            # canonicalize against the CURRENT duration (pure grammar
            # authority; PlanSchemaInvalid → 422 SPATIAL_SHOT_PLAN_INVALID)
            canonical = parse_shot_plan(plan_raw,
                                        duration_ms=shot["duration_ms"])
            new_hash = plan_hash(canonical)

            if current is not None and current["plan_hash"] == new_hash:
                await conn.exec_driver_sql("COMMIT")  # true no-op
                return {"plan_hash": new_hash, "plan": canonical,
                        "created": False}

            await _validate_ownership(conn, shot, canonical)
            plan_json = canonical_json_bytes(canonical).decode("utf-8")
            if current is None:
                await conn.execute(text(
                    "INSERT INTO shot_spatial_plans (shot_id, "
                    "spatial_world_id, plan_json, plan_hash, created_at, "
                    "updated_at) VALUES (:s, :w, :j, :h, strftime("
                    "'%Y-%m-%dT%H:%M:%fZ','now'), strftime("
                    "'%Y-%m-%dT%H:%M:%fZ','now'))"),
                    {"s": shot_id, "w": canonical["spatial_world_id"],
                     "j": plan_json, "h": new_hash})
            else:
                await conn.execute(text(
                    "UPDATE shot_spatial_plans SET spatial_world_id = :w, "
                    "plan_json = :j, plan_hash = :h, updated_at = strftime("
                    "'%Y-%m-%dT%H:%M:%fZ','now') WHERE shot_id = :s"),
                    {"s": shot_id, "w": canonical["spatial_world_id"],
                     "j": plan_json, "h": new_hash})
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                f"spatial plan put failed: {exc}", 500) from exc
    return {"plan_hash": new_hash, "plan": canonical, "created": True}


async def delete_spatial_plan(session: AsyncSession, shot_id: str, *,
                              expected_plan_hash: str | None) -> None:
    """DELETE with exact CAS semantics (§15.4). Never touches history."""
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _load_active_shot(conn, shot_id)
            current = await _load_current(conn, shot_id)
            if current is None:
                if expected_plan_hash is not None:
                    raise _conflict(
                        "No current ShotSpatialPlan exists but a non-null "
                        "expected_plan_hash was supplied.")
                await conn.exec_driver_sql("COMMIT")  # idempotent 204
                return
            if expected_plan_hash != current["plan_hash"]:
                raise _conflict(
                    "expected_plan_hash does not match the current "
                    "ShotSpatialPlan.")
            await conn.execute(text(
                "DELETE FROM shot_spatial_plans WHERE shot_id = :s"),
                {"s": shot_id})
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                f"spatial plan delete failed: {exc}", 500) from exc


async def get_current_plan(session: AsyncSession,
                           shot_id: str) -> dict | None:
    """Current stored plan projection for authoring/inspection: exact
    stored canonical bytes and hash; no re-resolution."""
    current = await _load_current_raw(session, shot_id)
    if current is None:
        return None
    return {"plan_hash": current["plan_hash"],
            "plan_json": current["plan_json"],
            "spatial_world_id": current["spatial_world_id"]}


async def _load_current_raw(session, shot_id: str) -> dict | None:
    row = (await session.execute(text(
        "SELECT plan_hash, plan_json, spatial_world_id "
        "FROM shot_spatial_plans WHERE shot_id = :s"),
        {"s": shot_id})).mappings().first()
    return dict(row) if row is not None else None


__all__ = ["put_spatial_plan", "delete_spatial_plan", "get_current_plan"]
